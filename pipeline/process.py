"""Turn accumulated HRES `tp` into rainfall amounts over intervals and 24 h windows.

Conventions (see CLAUDE.md):
- Differences are taken in the file's own units (metres): values sit exactly on a 2**E grid,
  so the subtraction is exact; conversion to mm happens afterwards.
- Units come from the GRIB `units` attribute; anything unexpected raises.
- Times: GRIB2 times are UTC. cfgrib returns naive datetime64, so we attach UTC explicitly.
  IST (UTC+05:30) is only used for labels.
- Small negative amounts are GRIB packing noise (pipeline/packing.py); they are clipped to 0
  and counted, never hidden.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import xarray as xr

UTC = dt.timezone.utc
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")

TO_MM = {"m": 1000.0, "mm": 1.0, "kg m**-2": 1.0}  # 1 kg m-2 of water = 1 mm depth

# Candidate lowest map bins (mm). The chosen one must be at least 2x the worst packing error.
LOWEST_BIN_CANDIDATES = (0.5, 1.0, 2.0)


def mm_factor(units: str) -> float:
    try:
        return TO_MM[units]
    except KeyError:
        raise ValueError(f"Unexpected precipitation units {units!r}; refusing to guess") from None


def step_hours(da: xr.DataArray) -> np.ndarray:
    h = da.step.values / np.timedelta64(1, "h")
    if not np.allclose(h, np.round(h)):
        raise ValueError(f"Non-integer step hours: {h}")
    return np.round(h).astype(int)


@dataclass
class Amounts:
    mm: xr.DataArray          # dims (window, latitude, longitude), clipped at 0
    start_h: np.ndarray       # window start, hours after base time
    end_h: np.ndarray         # window end, hours after base time
    n_clipped: np.ndarray     # per window: how many grid points were negative before clipping
    min_raw_mm: np.ndarray    # per window: most negative raw value (packing noise size)


def difference(tp: xr.DataArray, start_h, end_h) -> Amounts:
    """Amount between pairs of steps: TP(end) - TP(start), in mm, clipped at 0."""
    factor = mm_factor(tp.attrs["units"])
    if tp.attrs.get("GRIB_stepType", "accum") != "accum":
        raise ValueError("tp is not an accumulation field")
    start_h, end_h = np.asarray(start_h, int), np.asarray(end_h, int)
    hours = step_hours(tp)
    missing = sorted(set(start_h.tolist() + end_h.tolist()) - set(hours.tolist()))
    if missing:
        raise ValueError(f"Steps {missing} h not in data (have {hours.tolist()})")
    idx = {h: i for i, h in enumerate(hours)}
    v = tp.values.astype(np.float64)
    raw = np.stack([v[idx[e]] - v[idx[s]] for s, e in zip(start_h, end_h)]) * factor
    n_clipped = (raw < 0).sum(axis=(1, 2))
    min_raw = raw.min(axis=(1, 2))
    mm = xr.DataArray(
        np.clip(raw, 0, None),
        dims=("window", "latitude", "longitude"),
        coords={"latitude": tp.latitude, "longitude": tp.longitude},
        attrs={"units": "mm", "source_units": tp.attrs["units"]},
    )
    return Amounts(mm, start_h, end_h, n_clipped, min_raw)


def deaccumulate(tp: xr.DataArray) -> Amounts:
    """Amount in each interval between consecutive steps (3 h for steps 0-144)."""
    h = step_hours(tp)
    return difference(tp, h[:-1], h[1:])


def ens_window_starts(last_step_h: int, length_h: int = 24, every_h: int = 12) -> np.ndarray:
    """Start hours of the ENS tpg* windows (0-24, 12-36, ...) that fit within the data."""
    return np.arange(0, last_step_h - length_h + 1, every_h)


def window_totals(tp: xr.DataArray, length_h: int = 24) -> Amounts:
    """24 h totals on the ENS windows: TP(t + 24) - TP(t)."""
    starts = ens_window_starts(int(step_hours(tp)[-1]), length_h)
    return difference(tp, starts, starts + length_h)


# ---------- time handling ----------

def base_time_utc(ds: xr.Dataset | xr.DataArray) -> dt.datetime:
    """Forecast reference time as a tz-aware UTC datetime (GRIB2 times are UTC)."""
    t = np.datetime64(ds.time.values, "s").astype(dt.datetime)
    return t.replace(tzinfo=UTC)


def ist_label(t_utc: dt.datetime) -> str:
    """e.g. 'Thu 13 Nov 05:30 IST'. Input must be tz-aware."""
    if t_utc.tzinfo is None:
        raise ValueError("naive datetime: attach a time zone first")
    return t_utc.astimezone(IST).strftime("%a %d %b %H:%M IST")


def window_label(base_utc: dt.datetime, start_h: int, end_h: int) -> str:
    a = base_utc + dt.timedelta(hours=int(start_h))
    b = base_utc + dt.timedelta(hours=int(end_h))
    return f"{ist_label(a)} → {ist_label(b)}"


# ---------- colour scale floor ----------

def lowest_bin(max_error_mm: float) -> float:
    """Smallest candidate bin that is at least twice the worst packing error."""
    for c in LOWEST_BIN_CANDIDATES:
        if c >= 2 * max_error_mm:
            return c
    raise ValueError(f"Packing error {max_error_mm} mm too large for the colour scale")
