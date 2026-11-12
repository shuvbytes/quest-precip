"""M2 visible check: clipping stats, IST window labels, the regional maximum, and check maps.

Usage: python pipeline/m2_check.py data/raw/hres_tp_YYYYMMDDHHz.grib2
Writes PNGs to outputs/checks/ (git-ignored).
"""
from __future__ import annotations

import sys
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.colors import BoundaryNorm, ListedColormap

matplotlib.use("Agg")

from packing import read_packing
from process import (base_time_utc, deaccumulate, difference, ist_label, lowest_bin,
                     step_hours, window_label, window_totals)
from region import crop

OUT = Path(__file__).resolve().parent.parent / "outputs" / "checks"


def draw(ax_title, field, bins, path, mark=None):
    cmap = ListedColormap(plt.get_cmap("YlGnBu")(np.linspace(0.15, 1, len(bins) - 1)))
    cmap.set_under((1, 1, 1, 0))  # below lowest bin: transparent (treated as "no rain")
    cmap.set_over("#7a0177")
    norm = BoundaryNorm(bins, cmap.N)
    fig = plt.figure(figsize=(7.5, 7))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND, facecolor="#f2efe9")
    ax.add_feature(cfeature.OCEAN, facecolor="#e6eef5")
    # Each value is the amount for the 0.25 deg cell centred on its lat/lon, so draw cells, not smoothed contours.
    m = ax.pcolormesh(field.longitude, field.latitude, field.values, cmap=cmap, norm=norm,
                      shading="nearest", transform=ccrs.PlateCarree())
    ax.coastlines("10m", linewidth=0.6)
    if mark:
        ax.plot(mark[1], mark[0], "rx", ms=10, mew=2, transform=ccrs.PlateCarree())
    ax.set_extent([65, 100, 5, 38], crs=ccrs.PlateCarree())
    ax.gridlines(draw_labels=True, linewidth=0.3, alpha=0.5)
    fig.colorbar(m, ax=ax, shrink=0.75, extend="max", label="mm")
    ax.set_title(ax_title, fontsize=9)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {path}")


def main(path: str) -> None:
    ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    tp = crop(ds["tp"]).load()
    base = base_time_utc(ds)
    hours = step_hours(tp)
    print(f"Run: {base:%Y-%m-%d %H:%M} UTC  = {ist_label(base)}   units in file: {tp.attrs['units']!r}")

    packs = read_packing(path)
    qmax_mm = max(p.quantum for p in packs) * 1000
    floor = lowest_bin(qmax_mm)
    print(f"Largest packing quantum this run: {qmax_mm:.4f} mm -> lowest map bin {floor} mm")

    three = deaccumulate(tp)
    print(f"\n3 h intervals: {len(three.start_h)}  clipped points total "
          f"{int(three.n_clipped.sum())} of {three.mm.size} "
          f"({100 * three.n_clipped.sum() / three.mm.size:.3f} %), most negative raw "
          f"{three.min_raw_mm.min():.4f} mm")
    above = (three.mm.values > 0) & (three.mm.values < floor)
    print(f"3 h amounts > 0 but below {floor} mm (shown as no rain): {int(above.sum())} "
          f"({100 * above.sum() / three.mm.size:.2f} %)")

    w = window_totals(tp)
    print("\n24 h windows (ENS windows, both layers):")
    for k, (s, e) in enumerate(zip(w.start_h, w.end_h)):
        print(f"  {s:3d}-{e:3d} h  {window_label(base, s, e)}   max {w.mm.values[k].max():6.1f} mm"
              f"   clipped {int(w.n_clipped[k])}")

    total = difference(tp, [0], [int(hours[-1])])
    f = total.mm.isel(window=0)
    iy, ix = np.unravel_index(int(np.argmax(f.values)), f.shape)
    lat, lon = float(f.latitude[iy]), float(f.longitude[ix])
    print(f"\nMax 0-{hours[-1]} h total: {f.values[iy, ix]:.1f} mm at {lat:.2f} N, {lon:.2f} E "
          f"(grid cell {lat-0.125:.3f}-{lat+0.125:.3f} N, {lon-0.125:.3f}-{lon+0.125:.3f} E)")
    print("  3 h amounts at that cell (mm), by window start hour:")
    series = three.mm.values[:, iy, ix]
    print("  " + "  ".join(f"{h}:{v:.0f}" for h, v in zip(three.start_h, series) if v >= 1))
    print("  neighbouring cells (mm), N at top:")
    print(np.array2string(f.values[iy - 2:iy + 3, ix - 2:ix + 3], precision=0, suppress_small=True))

    tag = f"{base:%Y%m%d%H}z"
    draw(f"ECMWF IFS HRES 24 h total, {window_label(base, 0, 24)}\n"
         f"run {base:%Y-%m-%d %H} UTC; cells < {floor} mm left blank (below packing noise)",
         w.mm.isel(window=0), [floor, 2.5, 5, 10, 20, 50, 100, 200], OUT / f"hres_24h_0-24_{tag}.png")
    draw(f"ECMWF IFS HRES total {window_label(base, 0, int(hours[-1]))}\n"
         f"max {f.values[iy, ix]:.0f} mm at {lat:.2f}N {lon:.2f}E (x)",
         f, [1, 5, 10, 25, 50, 100, 200, 300, 400, 500], OUT / f"hres_total_0-144_{tag}.png",
         mark=(lat, lon))


if __name__ == "__main__":
    main(sys.argv[1])
