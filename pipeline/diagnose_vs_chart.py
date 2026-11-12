"""Diagnose differences between our 0.25 deg map and ECMWF's OpenCharts map (M2 follow-up).

Compares the open-data 0-144 h total at 0.25 deg with the open-data 0.1 deg field of the same run.
Usage: python pipeline/diagnose_vs_chart.py <0p25 file with step 144> <0p1 file with step 144>
"""
from __future__ import annotations

import sys

import numpy as np
import xarray as xr

from region import crop


def load144(path):
    da = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})["tp"]
    if "step" in da.dims:
        da = da.sel(step=np.timedelta64(144, "h"))
    assert da.attrs["units"] == "m"
    return crop(da).load() * 1000.0  # mm (units read above)


def at(da, lat, lon):
    return float(da.sel(latitude=lat, longitude=lon, method="nearest"))


def block(da, lat, lon, half):
    """Values of the 0.1 field inside the box lat±half, lon±half."""
    return da.sel(latitude=slice(lat + half, lat - half), longitude=slice(lon - half, lon + half)).values


def main(p25, p10):
    a, b = load144(p25), load144(p10)
    q = 2.0**-12 * 1000
    print(f"quantum of both fields at step 144: {q:.4f} mm -> possible values 0, {q:.3f}, {2*q:.3f}, ...")
    print("True totals below q/2 = 0.122 mm are stored as exactly 0 in BOTH open-data files.\n")

    print("== Q1 central India: 0-144 h total (mm) ==")
    for lat, lon in [(22, 78), (18, 76)]:
        bb = block(b, lat, lon, 0.125)
        print(f"  {lat}N {lon}E  0.25deg: {at(a, lat, lon):.3f}   0.1deg same point: {at(b, lat, lon):.3f}"
              f"   0.1deg cells in the 0.25 box: min {bb.min():.3f} max {bb.max():.3f}")
    box = a.sel(latitude=slice(24, 16), longitude=slice(74, 82)).values
    vals, counts = np.unique(np.round(box, 3), return_counts=True)
    print("  value histogram, 16-24N 74-82E (0.25deg):",
          ", ".join(f"{v:g} mm x{c}" for v, c in zip(vals[:6], counts[:6])))

    print("\n== Q2 south Tamil Nadu coast (mm) ==")
    for lat, lon in [(9.0, 78.0), (9.0, 78.25), (9.0, 78.5), (9.0, 78.75), (9.0, 79.0),
                     (8.75, 78.25), (8.5, 78.0), (9.25, 79.0)]:
        bb = block(b, lat, lon, 0.125)
        print(f"  {lat:5.2f}N {lon:5.2f}E  0.25deg {at(a, lat, lon):6.2f}   0.1deg box min/mean/max "
              f"{bb.min():6.2f} {bb.mean():6.2f} {bb.max():6.2f}")

    print("\n== Q3 Himalaya 26-32N 80-93E: 0.25deg cells >= 50 mm ==")
    h = a.sel(latitude=slice(32, 26), longitude=slice(80, 93))
    v = h.values
    ys, xs = np.where(v >= 50)
    print(f"  {len(ys)} cells >= 50 mm (of {v.size})")
    rows = []
    for y, x in zip(ys, xs):
        lat, lon = float(h.latitude[y]), float(h.longitude[x])
        nb = v[max(y-1, 0):y+2, max(x-1, 0):x+2].copy()
        nb_med = float(np.median(np.delete(nb.ravel(), nb.size // 2 if nb.size == 9 else 0)))
        bb = block(b, lat, lon, 0.125)
        rows.append((v[y, x], lat, lon, nb_med, at(b, lat, lon), bb.mean(), bb.max()))
    rows.sort(reverse=True)
    print(f"  {'0.25 val':>8s} {'lat':>6s} {'lon':>6s} {'8-nbr med':>9s} {'0.1 same pt':>11s}"
          f" {'0.1 box mean':>12s} {'0.1 box max':>11s}")
    for r in rows[:10]:
        print(f"  {r[0]:8.1f} {r[1]:6.2f} {r[2]:6.2f} {r[3]:9.1f} {r[4]:11.1f} {r[5]:12.1f} {r[6]:11.1f}")

    print("\n== Is a 0.25deg value a point sample or a box average? (whole region) ==")
    # Points shared by both grids: multiples of 0.5 deg.
    common_lat = a.latitude.values[np.isclose(a.latitude.values % 0.5, 0)]
    common_lon = a.longitude.values[np.isclose(a.longitude.values % 0.5, 0)]
    A = a.sel(latitude=common_lat, longitude=common_lon).values
    B = b.sel(latitude=common_lat, longitude=common_lon, method="nearest").values
    print(f"  shared points: {A.size};  |0.25 - 0.1| at same point: median {np.median(abs(A-B)):.3f} mm,"
          f" 99th pct {np.percentile(abs(A-B), 99):.3f} mm, max {abs(A-B).max():.2f} mm")
    means = np.array([[block(b, la, lo, 0.125).mean() for lo in common_lon] for la in common_lat])
    print(f"  |0.25 - mean of 0.1 cells in its box|: median {np.median(abs(A-means)):.3f} mm,"
          f" 99th pct {np.percentile(abs(A-means), 99):.3f} mm, max {abs(A-means).max():.2f} mm")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
