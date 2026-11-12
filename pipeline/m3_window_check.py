"""DEV-ONLY: is the ENS 0-24 h probability window aligned with the HRES 0-24 h window?

1. HRES 24 h and ENS P(>=1/5/10) at points in the central Bay (12-18N, 85-91E).
2. Raw GRIB keys of the ENS tpg10 0-24 message (date, time, steps, validity).
3. Correlation of ENS P(>=10) 0-24 h with HRES 24 h totals for every HRES window.
Usage: python pipeline/m3_window_check.py <hres_tp file> <ens_tpg file>
"""
from __future__ import annotations

import sys

import eccodes
import numpy as np
import xarray as xr

from ens import read_region
from process import base_time_utc, window_label, window_totals
from region import crop

POINTS = [(13.0, 86.0), (14.5, 88.0), (16.0, 87.0), (17.0, 89.5)]


def ranks(a):
    r = np.empty(a.size)
    r[np.argsort(a, kind="mergesort")] = np.arange(a.size)
    return r


def corr(a, b):
    a, b = a.ravel(), b.ravel()
    return float(np.corrcoef(a, b)[0, 1]), float(np.corrcoef(ranks(a), ranks(b))[0, 1])


def main(hres_path, ens_path):
    ds = xr.open_dataset(hres_path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    base = base_time_utc(ds)
    w = window_totals(crop(ds["tp"]).load())
    p = read_region(ens_path)
    k0 = int(np.where(p.start_h.values == 0)[0][0])

    print("== 1. Points in the central Bay, window 0-24 h ==")
    print(f"   {window_label(base, 0, 24)}")
    print(f"   {'point':>14s} {'HRES mm':>8s} {'P>=1':>6s} {'P>=5':>6s} {'P>=10':>6s} {'P>=20':>6s}"
          f"   {'max P>=10 within ±1°':>22s}")
    for lat, lon in POINTS:
        iy = int(np.argmin(abs(p.latitude.values - lat)))
        ix = int(np.argmin(abs(p.longitude.values - lon)))
        pr = [float(p.sel(threshold=t).values[k0, iy, ix]) for t in (1, 5, 10, 20)]
        nb = p.sel(threshold=10).values[k0, iy - 4:iy + 5, ix - 4:ix + 5]
        jy, jx = np.unravel_index(int(nb.argmax()), nb.shape)
        print(f"   {lat:5.2f}N {lon:6.2f}E {w.mm.values[0, iy, ix]:8.1f} "
              + " ".join(f"{v:6.1f}" for v in pr)
              + f"   {nb.max():5.1f} % at {float(p.latitude[iy-4+jy]):.2f}N {float(p.longitude[ix-4+jx]):.2f}E")
    band_h = w.mm.sel(latitude=slice(18, 12), longitude=slice(85, 91)).values[0]
    band_p = p.sel(threshold=10, latitude=slice(18, 12), longitude=slice(85, 91)).values[k0]
    m = band_h >= 20
    print(f"   band 12-18N 85-91E: {m.sum()} cells with HRES >= 20 mm; ENS P(>=10) there: "
          f"median {np.median(band_p[m]):.1f} %, 90th pct {np.percentile(band_p[m], 90):.1f} %")

    print("\n== 2. GRIB keys of the ENS tpg10 0-24 h message and HRES messages ==")
    keys = ["shortName", "dataDate", "dataTime", "stepRange", "startStep", "endStep", "stepUnits",
            "validityDate", "validityTime", "typeOfProcessedData", "type", "stream"]
    with open(ens_path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            if (eccodes.codes_get(gid, "shortName") == "tpg10"
                    and eccodes.codes_get(gid, "stepRange") == "0-24"):
                print("   ENS : " + ", ".join(f"{k}={eccodes.codes_get(gid, k, str)}" for k in keys))
            eccodes.codes_release(gid)
    with open(hres_path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            if eccodes.codes_get(gid, "endStep") in (0, 24):
                print("   HRES: " + ", ".join(f"{k}={eccodes.codes_get(gid, k, str)}" for k in keys))
            eccodes.codes_release(gid)

    print("\n== 3. ENS P(>=10) 0-24 h vs HRES 24 h totals for each HRES window (whole region) ==")
    target = p.sel(threshold=10).values[k0]
    print(f"   {'HRES window':>12s} {'Pearson':>8s} {'Spearman':>9s}   (HRES >= 10 mm) vs (P >= 50 %) agreement")
    for k, s in enumerate(w.start_h):
        r, rs = corr(target, w.mm.values[k])
        agree = ((w.mm.values[k] >= 10) == (target >= 50)).mean()
        print(f"   {s:4d}-{s+24:<4d} h {r:8.3f} {rs:9.3f}   {100*agree:5.1f} %")
    print("\n   Reverse check: HRES 0-24 h vs ENS P(>=10) for each ENS window")
    for k in range(p.sizes["window"]):
        s = int(p.start_h[k])
        r, rs = corr(p.sel(threshold=10).values[k], w.mm.values[0])
        print(f"   ENS {s:4d}-{s+24:<4d} h {r:8.3f} {rs:9.3f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
