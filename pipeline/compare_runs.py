"""DEV-ONLY: where two runs put the Bay of Bengal heavy-rain system, compared in VALID time.

For every 24 h window valid in both runs, prints the location and value of the HRES 24 h maximum and of the ENS
P(>=X) maximum in the Bay box, for each run, and the distance between them.
Usage: python pipeline/compare_runs.py <hres A> <ens A> <hres B> <ens B> [X_mm]
"""
from __future__ import annotations

import datetime as dt
import sys

import numpy as np
import xarray as xr

from ens import read_region
from process import base_time_utc, window_label, window_totals
from region import crop

BAY = dict(latitude=slice(20, 5), longitude=slice(80, 95))


def km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = np.radians(la1), np.radians(la2)
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lo2 - lo1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(h))


def load(hres, ens):
    ds = xr.open_dataset(hres, engine="cfgrib", backend_kwargs={"indexpath": ""})
    base = base_time_utc(ds)
    w = window_totals(crop(ds["tp"]).load())
    p = read_region(ens)
    return base, w, p


def peak(field2d, lat, lon):
    i, j = np.unravel_index(int(np.nanargmax(field2d)), field2d.shape)
    return float(field2d[i, j]), (float(lat[i]), float(lon[j]))


def main(ha, ea, hb, eb, x="100"):
    x = float(x)
    runs = [load(ha, ea), load(hb, eb)]
    print(f"Bay box 5-20N 80-95E; HRES = 24 h total max; ENS = max P(>={x:g} mm). Valid windows in UTC (IST label).")
    starts = {}
    for r, (base, w, p) in enumerate(runs):
        for s in w.start_h:
            starts.setdefault(base + dt.timedelta(hours=int(s)), {})[r] = int(s)
    for valid in sorted(starts):
        if len(starts[valid]) < 2:
            continue
        print(f"\nvalid {valid:%d %b %H}Z-{valid + dt.timedelta(hours=24):%d %b %H}Z  "
              f"({window_label(runs[0][0], starts[valid][0], starts[valid][0] + 24)})")
        locs = {}
        for r, (base, w, p) in enumerate(runs):
            s = starts[valid][r]
            k = int(np.where(w.start_h == s)[0][0])
            hm = w.mm.isel(window=k).sel(**BAY)
            kp = int(np.where(p.start_h.values == s)[0][0])
            pm = p.sel(threshold=x).isel(window=kp).sel(**BAY)
            hv, hl = peak(hm.values, hm.latitude.values, hm.longitude.values)
            pv, pl = peak(pm.values, pm.latitude.values, pm.longitude.values)
            locs[r] = (hl, pl)
            print(f"  run {base:%d %b %HZ} (+{s:3d}-{s+24:3d} h): HRES max {hv:6.1f} mm at {hl[0]:5.2f}N {hl[1]:6.2f}E | "
                  f"ENS max P {pv:4.0f} % at {pl[0]:5.2f}N {pl[1]:6.2f}E | HRES-ENS {km(hl, pl):4.0f} km")
        print(f"  between runs: HRES peaks {km(locs[0][0], locs[1][0]):4.0f} km apart, ENS peaks "
              f"{km(locs[0][1], locs[1][1]):4.0f} km apart; new HRES vs old ENS {km(locs[1][0], locs[0][1]):4.0f} km")


if __name__ == "__main__":
    main(*sys.argv[1:])
