"""Print what a GRIB file says about itself: units, accumulation type, times, grid.

Nothing here assumes units or time zones; every value printed comes from the file.
Usage: python pipeline/inspect_grib.py data/raw/hres_tp_YYYYMMDDHHz.grib2
"""
from __future__ import annotations

import sys

import numpy as np
import xarray as xr

# Region agreed in CLAUDE.md: India + surrounding seas
LAT_MIN, LAT_MAX = 5.0, 38.0
LON_MIN, LON_MAX = 65.0, 100.0


def crop(da: xr.DataArray) -> xr.DataArray:
    # ECMWF 0.25 deg grids list latitude north -> south, so slice from max to min.
    lat_desc = bool(da.latitude[0] > da.latitude[-1])
    lat_slice = slice(LAT_MAX, LAT_MIN) if lat_desc else slice(LAT_MIN, LAT_MAX)
    return da.sel(latitude=lat_slice, longitude=slice(LON_MIN, LON_MAX))


def main(path: str) -> None:
    ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    print("== Dataset ==")
    print(ds)
    var = list(ds.data_vars)[0]
    da = ds[var]

    print("\n== Variable attributes (from GRIB) ==")
    for key in ["long_name", "units", "GRIB_shortName", "GRIB_stepType", "GRIB_stepUnits",
                "GRIB_gridType", "GRIB_iDirectionIncrementInDegrees",
                "GRIB_jDirectionIncrementInDegrees", "GRIB_typeOfLevel"]:
        print(f"  {key:36s} {da.attrs.get(key)}")

    print("\n== Time coordinates ==")
    print(f"  base time (`time`)        : {ds.time.values}  attrs={dict(ds.time.attrs)}")
    steps_h = (ds.step.values / np.timedelta64(1, "h")).astype(int)
    print(f"  steps (h)                 : {steps_h.tolist()}")
    print(f"  valid_time first / last   : {ds.valid_time.values[0]} / {ds.valid_time.values[-1]}")
    print("  (cfgrib returns naive datetime64; GRIB times are UTC by definition)")

    print("\n== Global grid ==")
    print(f"  shape {da.shape}  lat {float(da.latitude[0])} .. {float(da.latitude[-1])}"
          f"  lon {float(da.longitude[0])} .. {float(da.longitude[-1])}")

    sub = crop(da)
    print("\n== Cropped to region ==")
    print(f"  shape {sub.shape}  lat {float(sub.latitude[0])} .. {float(sub.latitude[-1])}"
          f"  lon {float(sub.longitude[0])} .. {float(sub.longitude[-1])}")
    vals = sub.values
    print(f"  raw values (units = {da.attrs.get('units')!r}):"
          f" min {np.nanmin(vals):.6g}  max {np.nanmax(vals):.6g}  NaNs {int(np.isnan(vals).sum())}")
    print("  regional max per step (raw units), first 6 and last:")
    per_step = np.nanmax(vals.reshape(vals.shape[0], -1), axis=1)
    for h, v in list(zip(steps_h, per_step))[:6] + [(steps_h[-1], per_step[-1])]:
        print(f"    step {h:3d} h : {v:.6g}")
    nondecreasing = bool(np.all(np.diff(vals, axis=0) >= -1e-6))
    print(f"  values never decrease with step (accumulated since start?): {nondecreasing}")
    print(f"  min step-to-step change: {np.diff(vals, axis=0).min():.3g}")


if __name__ == "__main__":
    main(sys.argv[1])
