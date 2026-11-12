"""Build the site data for one run: frame PNGs (M4 step 1), later the manifest and point file.

Usage: python pipeline/build.py <hres_tp file> <ens_tpg file> [out_dir]
Output (git-ignored): site_build/data/
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import xarray as xr

from ens import read_region
from packing import read_packing
from palette import PROB, RAIN
from process import (BINS_3H, BINS_24H, base_time_utc, deaccumulate, interval_floor,
                     lowest_visible, window_totals)
from region import crop
from disagree import LEGEND, P_LIKELY, P_UNLIKELY, POINT_TEXT, flags
from render import Grid, render_hatch, render_png

PROB_BINS = (2, 10, 25, 50, 75, 90, 100)
HRES_MAX_H = 144
OUT_DEFAULT = Path(__file__).resolve().parent.parent / "site_build" / "data"


def load(hres_path, ens_path):
    ds = xr.open_dataset(hres_path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    tp = crop(ds["tp"]).load()
    base = base_time_utc(ds)
    p = read_region(ens_path)
    if f"{p.attrs['dataDate']} {int(p.attrs['dataTime']):04d}" != f"{base:%Y%m%d %H%M}":
        raise ValueError("HRES and ENS files are from different runs")
    p = p.isel(window=np.where(p.end_h.values <= HRES_MAX_H)[0])  # only windows HRES also covers
    np.testing.assert_allclose(p.latitude, tp.latitude)
    np.testing.assert_allclose(p.longitude, tp.longitude)
    return tp, p, base, read_packing(hres_path)


def render_frames(tp, p, packs, out: Path):
    grid = Grid.from_coords(tp.latitude.values, tp.longitude.values)
    units = tp.attrs["units"]
    frames = {"hres_3h": [], "hres_24h": [], "ens": [], "disagree": []}

    def record(product, a, k, s, e, bins, colours, floor, extra=None):
        lowest, raised = lowest_visible(bins, floor)
        name = f"{product}_{s:03d}-{e:03d}.png" if extra is None else f"ens_p{extra:g}_{s:03d}-{e:03d}.png"
        render_png(a, grid, bins, colours, lowest, out / "frames" / name)
        return {"file": f"frames/{name}", "start_h": int(s), "end_h": int(e),
                "floor": round(float(floor), 4), "lowest_drawn": lowest, "floor_raised": raised}

    three = deaccumulate(tp)
    f3 = interval_floor(packs, three.start_h, three.end_h, units)
    for k, (s, e) in enumerate(zip(three.start_h, three.end_h)):
        r = record("hres3h", three.mm.values[k], k, s, e, BINS_3H, RAIN, f3[k])
        r.update(max_mm=round(float(three.mm.values[k].max()), 1), clipped_points=int(three.n_clipped[k]))
        frames["hres_3h"].append(r)

    w = window_totals(tp)
    f24 = interval_floor(packs, w.start_h, w.end_h, units)
    for k, (s, e) in enumerate(zip(w.start_h, w.end_h)):
        r = record("hres24h", w.mm.values[k], k, s, e, BINS_24H, RAIN, f24[k])
        r.update(max_mm=round(float(w.mm.values[k].max()), 1), clipped_points=int(w.n_clipped[k]))
        frames["hres_24h"].append(r)

    for t in p.threshold.values:
        pt = p.sel(threshold=t)
        for k in range(pt.sizes["window"]):
            s, e = int(pt.start_h[k]), int(pt.end_h[k])
            floor = 2 * float(pt.quantum.values[k])
            r = record("ens", pt.values[k], k, s, e, PROB_BINS, PROB, floor, extra=t)
            r.update(threshold_mm=float(t), max_pct=round(float(pt.values[k].max()), 1))
            frames["ens"].append(r)

            # Disagreement for the same threshold and window (HRES 24 h from the same run)
            kh = int(np.where(w.start_h == s)[0][0])
            wet, dry = flags(w.mm.values[kh], pt.values[k], float(t))
            name = f"disagree_p{t:g}_{s:03d}-{e:03d}.png"
            if wet.any() or dry.any():
                render_hatch(wet, dry, grid, out / "frames" / name)
            frames["disagree"].append({
                "file": f"frames/{name}" if (wet.any() or dry.any()) else None,
                "threshold_mm": float(t), "start_h": s, "end_h": e,
                "n_wetter": int(wet.sum()), "n_drier": int(dry.sum()),
                # flat cell indices (row * nlon + col) so the point panel can say which applies
                "cells_wetter": np.flatnonzero(wet).tolist(),
                "cells_drier": np.flatnonzero(dry).tolist(),
            })
    return grid, three, w, frames


ATTRIBUTION = ("© European Centre for Medium-Range Weather Forecasts (ECMWF). Source: ECMWF Open Data "
               "(www.ecmwf.int). Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). "
               "Modified: cropped, de-accumulated, converted to mm, reprojected and coloured by this app; "
               "ECMWF does not endorse it.")


def write_points(three, p, out: Path):
    """points.bin: HRES 3 h amounts as uint16 (0.1 mm units) then ENS probabilities as uint8 (%).

    Little-endian, C order, no header; the layout is described in the manifest ("points").
    """
    h = np.round(three.mm.values * 10.0)
    e = np.round(p.values)
    if h.max() > 65535 or e.min() < 0 or e.max() > 100:
        raise ValueError("value outside encodable range")
    h16 = h.astype("<u2")
    e8 = e.astype(np.uint8)
    path = out / "points.bin"
    with open(path, "wb") as f:
        f.write(h16.tobytes(order="C"))
        f.write(e8.tobytes(order="C"))
    entry = {
        "file": "points.bin", "byte_order": "little", "bytes": path.stat().st_size,
        "load": "lazily, on the first click",
        "arrays": [
            {"name": "hres_3h", "dtype": "uint16", "scale": 0.1, "units": "mm", "offset": 0,
             "shape": list(h16.shape), "dims": ["frame (= products.hres_3h.frames order)", "lat (north→south)", "lon (west→east)"]},
            {"name": "ens_prob", "dtype": "uint8", "scale": 1, "units": "%", "offset": h16.nbytes,
             "shape": list(e8.shape),
             "dims": ["threshold (= products.ens_prob.thresholds_mm order)",
                      "window (= frames_by_threshold order)", "lat (north→south)", "lon (west→east)"]},
        ],
    }
    return path, entry


def read_points(path: Path, entry):
    """Decode points.bin back to (hres_3h mm, ens %) — the same steps the browser will do."""
    raw = Path(path).read_bytes()
    a, b = entry["arrays"]
    h = np.frombuffer(raw, "<u2", count=int(np.prod(a["shape"])), offset=a["offset"]).reshape(a["shape"]) * a["scale"]
    e = np.frombuffer(raw, np.uint8, count=int(np.prod(b["shape"])), offset=b["offset"]).reshape(b["shape"]) * b["scale"]
    return h, e


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")


def write_manifest(base, grid, frames, tp_units, ens_units, out: Path, points=None, generated_utc=None):
    import datetime as dt
    import json
    from process import UTC, ist_label, window_label

    generated_utc = generated_utc or dt.datetime.now(UTC)

    def add_times(f):
        a = base + dt.timedelta(hours=f["start_h"])
        b = base + dt.timedelta(hours=f["end_h"])
        return {**f, "start_utc": _iso(a), "end_utc": _iso(b), "label_ist": window_label(base, f["start_h"], f["end_h"])}

    ens_by_thr = {}
    for f in frames["ens"]:
        ens_by_thr.setdefault(f"{f['threshold_mm']:g}", []).append(add_times(f))
    dis_by_thr = {}
    for f in frames["disagree"]:
        dis_by_thr.setdefault(f"{f['threshold_mm']:g}", []).append(add_times(f))

    m = {
        "schema": 1,
        "run": {"utc": _iso(base), "ist": ist_label(base), "model": "ECMWF IFS (HRES + ENS), Open Data 0.25°"},
        "generated_utc": _iso(generated_utc),
        "time_note": "All times computed in UTC from the GRIB reference time; IST = UTC+05:30, used for labels only.",
        "grid": {"lat_north": grid.lat_n, "lon_west": grid.lon_w, "dlat": grid.dlat, "dlon": grid.dlon,
                 "nlat": grid.nlat, "nlon": grid.nlon,
                 "value_meaning": "Model value at the nearest grid point (0.25°, ~25 km spacing). "
                                  "Rain can vary a lot within that distance."},
        "image": {"bounds": grid.bounds, "width": grid.width, "height": grid.height,
                  "projection": "EPSG:3857 rows (for L.imageOverlay)", "resampling": "nearest grid point, no smoothing"},
        "products": {
            "hres_3h": {"title": "Rain in 3 hours (HRES, one model run)", "units": "mm",
                        "source_units": tp_units, "bins": list(BINS_3H), "colours": RAIN,
                        "over_colour_from": BINS_3H[-1],
                        "below_floor": "not drawn (within GRIB packing noise, 2 × quantum)",
                        "frames": [add_times(f) for f in frames["hres_3h"]]},
            "hres_24h": {"title": "Rain in 24 hours (HRES, one model run)", "units": "mm",
                         "source_units": tp_units, "bins": list(BINS_24H), "colours": RAIN,
                         "over_colour_from": BINS_24H[-1],
                         "definition": "TP(end) − TP(start); windows match the ENS probability windows",
                         "below_floor": "not drawn (below the first legend edge or 2 × quantum)",
                         "frames": [add_times(f) for f in frames["hres_24h"]]},
            "ens_prob": {"title": "Chance of at least X mm in 24 hours (ENS ensemble)", "units": "%",
                         "source_units": ens_units, "bins": list(PROB_BINS), "colours": PROB,
                         "top_edge_inclusive": True,
                         "definition": "GRIB probabilityType 3: probability that the 24 h total exceeds the "
                                       "threshold; ECMWF names it 'at least X mm'",
                         "thresholds_mm": [float(t) for t in ens_by_thr],
                         "frames_by_threshold": ens_by_thr},
            "disagreement": {
                "title": "Where the single detailed run and the ensemble disagree",
                "shown_in": "24 h mode, over the ENS probability layer",
                "default_on": True,
                "rule": {
                    "threshold": "X = the selected ENS threshold",
                    "wetter": f"HRES >= X at the point and ENS P(>=X) < {P_UNLIKELY:g} % at the point and all 8 neighbours",
                    "drier": f"ENS P(>=X) >= {P_LIKELY:g} % at the point and HRES < X at the point and all 8 neighbours",
                    "p_unlikely": P_UNLIKELY, "p_likely": P_LIKELY, "neighbourhood": "3x3",
                },
                "pattern": {"wetter": "diagonal lines", "drier": "dots", "colours": "black with white edge"},
                "legend": LEGEND,
                "point_text": POINT_TEXT,
                "cell_index": "row * nlon + col (row 0 = north)",
                "frames_by_threshold": dis_by_thr,
            },
        },
        "points": points,
        "source": {"provider": "ECMWF Open Data", "url": "https://www.ecmwf.int/en/forecasts/datasets/open-data",
                   "hres": "stream=oper type=fc param=tp, steps 0–144 h", "ens": "stream=enfo type=ep param=tpg*"},
        "attribution": ATTRIBUTION,
    }
    path = out / "manifest.json"
    path.write_text(json.dumps(m, indent=1, ensure_ascii=False))
    return path, m


def main(hres_path, ens_path, out=OUT_DEFAULT):
    out = Path(out)
    tp, p, base, packs = load(hres_path, ens_path)
    grid, three, w, frames = render_frames(tp, p, packs, out)
    ppath, pentry = write_points(three, p, out)
    mpath, _ = write_manifest(base, grid, frames, tp.attrs["units"], p.attrs["units"], out, points=pentry)
    print(f"wrote {mpath} ({mpath.stat().st_size / 1e3:.1f} kB)")
    print(f"wrote {ppath} ({ppath.stat().st_size:,} bytes)")
    print(f"Run {base:%Y-%m-%d %H:%M} UTC; grid {grid.nlat}x{grid.nlon}; image {grid.width}x{grid.height} px;"
          f" bounds {grid.bounds}")
    dis = frames["disagree"]
    print(f"  disagree : {sum(f['file'] is not None for f in dis)} hatch PNGs for {len(dis)} threshold/windows; "
          f"wetter cells {sum(f['n_wetter'] for f in dis)}, drier cells {sum(f['n_drier'] for f in dis)}")
    for name, fr in frames.items():
        if name == "disagree":
            continue
        sizes = [(out / f["file"]).stat().st_size for f in fr]
        raised = [f["file"] for f in fr if f["floor_raised"]]
        print(f"  {name:9s}: {len(fr):3d} PNGs, {sum(sizes)/1e3:7.1f} kB total "
              f"({min(sizes)/1e3:.1f}-{max(sizes)/1e3:.1f} kB each); floors "
              f"{min(f['floor'] for f in fr):.3f}-{max(f['floor'] for f in fr):.3f}; raised: {raised or 'none'}")
    return base, grid, three, w, p, frames


if __name__ == "__main__":
    main(*sys.argv[1:])
