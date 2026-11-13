"""Build the site data for one run: frame PNGs (M4 step 1), later the manifest and point file.

Usage: python pipeline/build.py <hres_tp file> <ens_tpg file> [out_dir]
Output (git-ignored): site_build/data/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import xarray as xr

from ens import read_region
from packing import read_packing
from palette import LAND, OCEAN, OUTSIDE, OUTSIDE_OPACITY, PROB, RAIN
from region import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN
from process import (BINS_3H, BINS_24H, base_time_utc, deaccumulate, interval_floor,
                     lowest_visible, window_totals)
from region import crop
from disagree import (HEAVY_FROM_MM, LEGEND, MAP_MIN_CLUSTER, MIN_ZOOM_FOR_MARKS, P_LIKELY, P_UNLIKELY, POINT_TEXT,
                      ZOOM_NOTE, flags, keep_min_cluster)
from render import Grid, render_hatch, render_png

PROB_BINS = (2, 10, 25, 50, 75, 90, 100)
HRES_MAX_H = 144
ROOT = Path(__file__).resolve().parent.parent
OUT_DEFAULT = ROOT / "site_build" / "data"
WEB = ROOT / "web"


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
            # Map: only clusters of >= MAP_MIN_CLUSTER cells. Point panel: every flagged cell.
            wet_map, dry_map = keep_min_cluster(wet), keep_min_cluster(dry)
            name = f"disagree_p{t:g}_{s:03d}-{e:03d}.png"
            drawn = bool(wet_map.any() or dry_map.any())
            name_bold = name.replace("disagree_", "disagree-bold_")
            if drawn:
                render_hatch(wet_map, dry_map, grid, out / "frames" / name, style="fine")
                render_hatch(wet_map, dry_map, grid, out / "frames" / name_bold, style="bold")
            frames["disagree"].append({
                "file": f"frames/{name}" if drawn else None,             # zoom >= min_zoom_for_marks
                "file_bold": f"frames/{name_bold}" if drawn else None,   # zoom <  min_zoom_for_marks
                "threshold_mm": float(t), "start_h": s, "end_h": e,
                "n_wetter": int(wet.sum()), "n_drier": int(dry.sum()),
                "n_wetter_on_map": int(wet_map.sum()), "n_drier_on_map": int(dry_map.sum()),
                # ALL flagged cells (row * nlon + col), for the point panel sentence
                "cells_wetter": np.flatnonzero(wet).tolist(),
                "cells_drier": np.flatnonzero(dry).tolist(),
            })
    return grid, three, w, frames


ATTRIBUTION = ("© European Centre for Medium-Range Weather Forecasts (ECMWF). Source: ECMWF Open Data "
               "(www.ecmwf.int). Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). "
               "Modified: cropped, de-accumulated, converted to mm, reprojected and coloured by this app; "
               "ECMWF does not endorse it.")


def write_points(three, w, p, out: Path):
    """points.bin, read by the point panel: named arrays back to back, little-endian, C order, no header.

    hres_3h  uint16, 0.1 mm  [48 frames, lat, lon]   3-hourly amounts (as on the map)
    hres_24h uint16, 0.1 mm  [11 windows, lat, lon]  TP(t+24) - TP(t), exactly the map's 24 h values (user, 13 Nov:
                                                     summing 3 h values could differ by up to 0.35 mm)
    ens_prob uint8,  %       [7 thresholds, 11 windows, lat, lon]
    Layout (offsets, shapes, scales) is described in the manifest ("points"); uint16 arrays come first so every
    array starts at an aligned offset.
    """
    def enc16(mm):
        v = np.round(np.asarray(mm) * 10.0)
        if v.min() < 0 or v.max() > 65535:
            raise ValueError("rain amount outside the uint16 0.1 mm range")
        return v.astype("<u2")

    e = np.round(p.values)
    if e.min() < 0 or e.max() > 100:
        raise ValueError("probability outside 0-100 %")
    arrays = [
        ("hres_3h", enc16(three.mm.values), 0.1, "mm", ["frame (= products.hres_3h.frames order)"]),
        ("hres_24h", enc16(w.mm.values), 0.1, "mm", ["window (= products.hres_24h.frames order)"]),
        ("ens_prob", e.astype(np.uint8), 1, "%", ["threshold (= products.ens_prob.thresholds_mm order)",
                                                  "window (= frames_by_threshold order)"]),
    ]
    path = out / "points.bin"
    entries, offset = [], 0
    with open(path, "wb") as f:
        for name, a, scale, units, lead_dims in arrays:
            f.write(a.tobytes(order="C"))
            entries.append({"name": name, "dtype": "uint16" if a.dtype.itemsize == 2 else "uint8", "scale": scale,
                            "units": units, "offset": offset, "shape": list(a.shape),
                            "dims": lead_dims + ["lat (north→south)", "lon (west→east)"]})
            offset += a.nbytes
    entry = {"file": "points.bin", "byte_order": "little", "bytes": path.stat().st_size,
             "load": "lazily, on the first click", "arrays": entries}
    return path, entry


def read_points(path: Path, entry):
    """Decode points.bin into {name: array in its units} — the same steps the browser does."""
    raw = Path(path).read_bytes()
    out = {}
    for a in entry["arrays"]:
        dt = "<u2" if a["dtype"] == "uint16" else np.uint8
        out[a["name"]] = (np.frombuffer(raw, dt, count=int(np.prod(a["shape"])), offset=a["offset"])
                          .reshape(a["shape"]) * a["scale"])
    return out


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
        # point API (M7b): the page asks it first and falls back to points.bin; env API_URL overrides (local checks)
        "api": {"url": os.environ.get("API_URL", API_URL), "timeout_ms": 3000, "name": "forecast API (Render)"},
        "time_note": "All times computed in UTC from the GRIB reference time; IST = UTC+05:30, used for labels only.",
        "region": {"lat_min": LAT_MIN, "lat_max": LAT_MAX, "lon_min": LON_MIN, "lon_max": LON_MAX},
        "basemap": {"land": LAND, "sea": OCEAN, "outside": OUTSIDE, "outside_opacity": OUTSIDE_OPACITY,
                    "note": "Colours from pipeline/palette.py; tests/test_palette.py checks the palest data colours against both."},
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
                "map_min_cluster": MAP_MIN_CLUSTER,
                "map_vs_point": (f"The map hatches only groups of at least {MAP_MIN_CLUSTER} touching flagged cells; "
                                 "the point panel reports every flagged cell (cells_wetter / cells_drier)."),
                "min_zoom_for_marks": MIN_ZOOM_FOR_MARKS,
                "zoom_note": ZOOM_NOTE,
                "initial_view": (f"Fit the region; if that needs a zoom below {MIN_ZOOM_FOR_MARKS} (small screens), "
                                 "show zoom_note while the zoom is below min_zoom_for_marks."),
                "pattern": {"wetter": "diagonal lines", "drier": "dots", "colours": "black with white edge"},
                "legend": LEGEND,
                "point_text": POINT_TEXT,
                "heavy_from_mm": HEAVY_FROM_MM,
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


API_URL = "https://quest-precip-api.onrender.com"   # point API on Render, free web service (api/, M7b)

VERSIONED = ("style.css", "app.js", "vendor/leaflet-1.9.4/leaflet.css", "vendor/leaflet-1.9.4/leaflet.js")


def copy_web(site_root: Path):
    """The page (web/) goes next to data/, so site_root is the complete static site.

    Cache busting: each script/stylesheet link in index.html gets ?v=<first 10 hex of its SHA-256>, so a changed
    file always has a new URL and a browser cannot keep using a stale cached copy (Safari, 13 Nov). Integrity
    hashes still apply to the file content, so they are unaffected.
    """
    import hashlib
    import re
    import shutil
    shutil.copytree(WEB, site_root, dirs_exist_ok=True)
    index = site_root / "index.html"
    html = index.read_text()
    for rel in VERSIONED:
        v = hashlib.sha256((site_root / rel).read_bytes()).hexdigest()[:10]
        html, n = re.subn(rf'(["\']){re.escape(rel)}(\?v=[0-9a-f]+)?(["\'])', rf"\g<1>{rel}?v={v}\g<3>", html)
        if n != 1:
            raise ValueError(f"expected exactly one reference to {rel} in index.html, found {n}")
    index.write_text(html)
    return site_root


def main(hres_path, ens_path, out=OUT_DEFAULT):
    out = Path(out)
    tp, p, base, packs = load(hres_path, ens_path)
    grid, three, w, frames = render_frames(tp, p, packs, out)
    ppath, pentry = write_points(three, w, p, out)
    mpath, _ = write_manifest(base, grid, frames, tp.attrs["units"], p.attrs["units"], out, points=pentry)
    print(f"wrote {mpath} ({mpath.stat().st_size / 1e3:.1f} kB)")
    print(f"wrote {ppath} ({ppath.stat().st_size:,} bytes)")
    site = copy_web(out.parent)
    print(f"copied web/ into {site}")
    print(f"Run {base:%Y-%m-%d %H:%M} UTC; grid {grid.nlat}x{grid.nlon}; image {grid.width}x{grid.height} px;"
          f" bounds {grid.bounds}")
    dis = frames["disagree"]
    print(f"  disagree : {sum(f['file'] is not None for f in dis)} hatch PNGs for {len(dis)} threshold/windows; "
          f"flagged (point panel) wetter {sum(f['n_wetter'] for f in dis)} / drier {sum(f['n_drier'] for f in dis)}; "
          f"on map (clusters >= {MAP_MIN_CLUSTER}) wetter {sum(f['n_wetter_on_map'] for f in dis)} / "
          f"drier {sum(f['n_drier_on_map'] for f in dis)}")
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
