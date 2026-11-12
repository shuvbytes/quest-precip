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
from render import Grid, render_png

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
    frames = {"hres_3h": [], "hres_24h": [], "ens": []}

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
    return grid, three, w, frames


def main(hres_path, ens_path, out=OUT_DEFAULT):
    out = Path(out)
    tp, p, base, packs = load(hres_path, ens_path)
    grid, three, w, frames = render_frames(tp, p, packs, out)
    print(f"Run {base:%Y-%m-%d %H:%M} UTC; grid {grid.nlat}x{grid.nlon}; image {grid.width}x{grid.height} px;"
          f" bounds {grid.bounds}")
    for name, fr in frames.items():
        sizes = [(out / f["file"]).stat().st_size for f in fr]
        raised = [f["file"] for f in fr if f["floor_raised"]]
        print(f"  {name:9s}: {len(fr):3d} PNGs, {sum(sizes)/1e3:7.1f} kB total "
              f"({min(sizes)/1e3:.1f}-{max(sizes)/1e3:.1f} kB each); floors "
              f"{min(f['floor'] for f in fr):.3f}-{max(f['floor'] for f in fr):.3f}; raised: {raised or 'none'}")
    return base, grid, three, w, p, frames


if __name__ == "__main__":
    main(*sys.argv[1:])
