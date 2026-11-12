"""Region of interest (decided 12 Nov, see CLAUDE.md): India + surrounding seas."""
from __future__ import annotations

import xarray as xr

LAT_MIN, LAT_MAX = 5.0, 38.0
LON_MIN, LON_MAX = 65.0, 100.0


def crop(obj: xr.DataArray | xr.Dataset) -> xr.DataArray | xr.Dataset:
    """Crop to the region; works whether latitude is stored ascending or descending."""
    lat_desc = bool(obj.latitude[0] > obj.latitude[-1])
    lat_slice = slice(LAT_MAX, LAT_MIN) if lat_desc else slice(LAT_MIN, LAT_MAX)
    return obj.sel(latitude=lat_slice, longitude=slice(LON_MIN, LON_MAX))
