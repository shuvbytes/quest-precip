"""DEV-ONLY (needs cartopy from environment-dev.yml; not used by the pipeline or CI).

M3 visible check: ENS tpg* contents, P(>=10 mm) map beside the HRES 24 h total for the same
window, and ENS P(>=50) / P(>=100) around the Bay of Bengal maximum.
Usage: python pipeline/m3_check.py <hres_tp file> <ens_tpg file>
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

from ens import read_region
from process import BINS_24H, base_time_utc, window_label, window_totals
from region import crop

OUT = Path(__file__).resolve().parent.parent / "outputs" / "checks"
BAY = (15.00, 86.50)   # 505 mm HRES 0-144 h maximum (M2)
PROB_BINS = [2, 10, 25, 50, 75, 90, 100]


def panel(ax, field, bins, cmap_name, label, title, extend="neither"):
    cmap = ListedColormap(plt.get_cmap(cmap_name)(np.linspace(0.2, 1, len(bins) - 1)))
    cmap.set_under((1, 1, 1, 0))
    # Values >= the last edge (e.g. exactly 100 %, or > 200 mm) take the top colour.
    cmap.set_over(cmap(cmap.N - 1))
    ax.add_feature(cfeature.LAND, facecolor="#f2efe9")
    ax.add_feature(cfeature.OCEAN, facecolor="#e6eef5")
    m = ax.pcolormesh(field.longitude, field.latitude, field.values, cmap=cmap,
                      norm=BoundaryNorm(bins, cmap.N), shading="nearest", transform=ccrs.PlateCarree())
    ax.coastlines("10m", lw=0.6)
    ax.plot(BAY[1], BAY[0], "kx", ms=7, transform=ccrs.PlateCarree())
    ax.set_extent([65, 100, 5, 38], crs=ccrs.PlateCarree())
    ax.gridlines(draw_labels=["left", "bottom"], lw=0.3, alpha=0.5)
    plt.colorbar(m, ax=ax, orientation="horizontal", pad=0.06, shrink=0.85, label=label,
                 ticks=bins, format="%g", extend=extend)
    ax.set_title(title, fontsize=9)


def main(hres_path, ens_path):
    ds = xr.open_dataset(hres_path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    base = base_time_utc(ds)
    w = window_totals(crop(ds["tp"]).load())
    p = read_region(ens_path)
    run_ens = f"{p.attrs['dataDate']} {int(p.attrs['dataTime']):04d}"
    assert run_ens == f"{base:%Y%m%d %H%M}", f"ENS run {run_ens} != HRES run {base}"
    print(f"Run (both files): {base:%Y-%m-%d %H:%M} UTC; ENS units {p.attrs['units']!r}; "
          f"meaning: {p.attrs['meaning']}")

    print("\nRegional max probability (%) per window and threshold:")
    print(f"  {'window':8s} {'IST':48s}" + "".join(f"  >={int(t):<3d}" for t in p.threshold.values))
    for k in range(p.sizes["window"]):
        s, e = int(p.start_h[k]), int(p.end_h[k])
        mx = p.isel(window=k).max(dim=("latitude", "longitude")).values
        print(f"  {s:3d}-{e:<4d} {window_label(base, s, e):48s}" + "".join(f"  {v:5.0f}" for v in mx))

    # --- side-by-side map, window 0-24 ---
    lab = window_label(base, 0, 24)
    fig, axs = plt.subplots(1, 2, figsize=(14, 7), subplot_kw={"projection": ccrs.PlateCarree()})
    panel(axs[0], w.mm.isel(window=0), list(BINS_24H), "YlGnBu", "mm",
          f"HRES (one run): 24 h total\n{lab}", extend="max")
    panel(axs[1], p.sel(threshold=10).isel(window=0), PROB_BINS, "PuRd", "%",
          f"ENS (ensemble): chance of ≥ 10 mm in 24 h\n{lab}")
    fig.suptitle(f"ECMWF IFS, run {base:%Y-%m-%d %H} UTC. x = Bay of Bengal 0–144 h maximum", fontsize=10)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"m3_hres24_vs_p10_0-24_{base:%Y%m%d%H}z.png"
    fig.savefig(out, dpi=100, bbox_inches="tight")
    print(f"\nwrote {out}")

    # --- agreement between the two layers in window 0-24 ---
    h = w.mm.values[0]
    p10 = p.sel(threshold=10).isel(window=0).values
    print("\n0-24 h agreement, cells by HRES total vs ENS P(>=10 mm):")
    for lo, hi in [(0, 1), (1, 10), (10, 20), (20, 50), (50, 1e9)]:
        m = (h >= lo) & (h < hi)
        print(f"  HRES {lo:>3g}-{hi if hi < 1e9 else 'inf':>4} mm: {m.sum():5d} cells, ENS P(>=10) "
              f"median {np.median(p10[m]):5.1f} %, 10-90 pct {np.percentile(p10[m], 10):5.1f}-"
              f"{np.percentile(p10[m], 90):5.1f} %")

    # --- Bay check ---
    iy = int(np.argmin(abs(p.latitude.values - BAY[0])))
    ix = int(np.argmin(abs(p.longitude.values - BAY[1])))
    print(f"\nBay of Bengal maximum cell {BAY[0]:.2f}N {BAY[1]:.2f}E (grid point "
          f"{float(p.latitude[iy]):.2f}N {float(p.longitude[ix]):.2f}E) and its 3x3 neighbourhood:")
    print(f"  {'window':8s} {'IST':48s} {'HRES pt':>8s} {'HRES 3x3':>12s} {'P>=50 pt':>9s} "
          f"{'P>=50 3x3':>11s} {'P>=100 pt':>10s} {'P>=100 3x3':>11s}")
    for s in (96, 108, 120, 132):
        k = int(np.where(p.start_h.values == s)[0][0])
        nb = (slice(iy - 1, iy + 2), slice(ix - 1, ix + 2))
        p50 = p.sel(threshold=50).values[k]
        p100 = p.sel(threshold=100).values[k]
        hk = np.where(w.start_h == s)[0]
        if len(hk):
            hv = w.mm.values[hk[0]]
            hres_pt, hres_nb = f"{hv[iy, ix]:8.0f}", f"{hv[nb].min():5.0f}-{hv[nb].max():<5.0f}"
        else:
            hres_pt, hres_nb = f"{'n/a':>8s}", f"{'(> 144 h)':>12s}"
        print(f"  {s:3d}-{s+24:<4d} {window_label(base, s, s + 24):48s} {hres_pt} {hres_nb:>12s} "
              f"{p50[iy, ix]:9.0f} {p50[nb].min():5.0f}-{p50[nb].max():<5.0f} "
              f"{p100[iy, ix]:10.0f} {p100[nb].min():5.0f}-{p100[nb].max():<5.0f}")
    bay = p.sel(latitude=slice(20, 8), longitude=slice(80, 95))
    for t in (50, 100):
        b = bay.sel(threshold=t)
        k, yy, xx = np.unravel_index(int(b.values.argmax()), b.shape)
        print(f"  Bay (8-20N, 80-95E) max P(>={t}) = {b.values.max():.0f} % at "
              f"{float(b.latitude[yy]):.2f}N {float(b.longitude[xx]):.2f}E, window "
              f"{int(b.start_h[k])}-{int(b.end_h[k])} h")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
