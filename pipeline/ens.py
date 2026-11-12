"""Read ENS precipitation probabilities (stream enfo, type ep, tpg*) from GRIB.

Everything that gives a value its meaning is read from GRIB keys, not from parameter names:
threshold = scaledValueOfLowerLimit * 10**-scaleFactorOfLowerLimit, the window comes from
startStep/endStep, and units come from the `units` key. probabilityType 3 is
"probability of event above lower limit" (GRIB2 code table 4.9). ECMWF names these
"Total precipitation of at least X mm".
"""
from __future__ import annotations

from collections import defaultdict

import eccodes
import numpy as np
import xarray as xr

from region import crop


def _get(gid, key):
    return eccodes.codes_get(gid, key)


def read_ens_probs(path: str) -> xr.DataArray:
    fields = {}
    meta = defaultdict(set)
    lats = lons = None
    with open(path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                ptype = _get(gid, "probabilityType")
                if ptype != 3:
                    raise ValueError(f"probabilityType {ptype}, expected 3 (above lower limit)")
                thr = _get(gid, "scaledValueOfLowerLimit") * 10.0 ** -_get(gid, "scaleFactorOfLowerLimit")
                win = (int(_get(gid, "startStep")), int(_get(gid, "endStep")))
                # Values must be stored north->south, west->east, rows contiguous.
                assert (_get(gid, "iScansNegatively"), _get(gid, "jScansPositively"),
                        _get(gid, "jPointsAreConsecutive")) == (0, 0, 0)
                ni, nj = _get(gid, "Ni"), _get(gid, "Nj")
                if lats is None:
                    # jScansPositively = 0 (asserted above): row 0 is the NORTHERN edge, so latitude
                    # must descend. Sort explicitly; do not rely on the order eccodes returns.
                    lats = np.sort(eccodes.codes_get_array(gid, "distinctLatitudes"))[::-1]
                    lons = np.sort(eccodes.codes_get_array(gid, "distinctLongitudes"))
                    north = _get(gid, "latitudeOfFirstGridPointInDegrees")
                    assert np.isclose(lats[0], north), (lats[0], north)
                    assert len(lats) == nj and len(lons) == ni
                fields[(thr, win)] = eccodes.codes_get_values(gid).reshape(nj, ni)
                for k in ("units", "stepType", "dataDate", "dataTime", "shortName"):
                    meta[k].add(str(_get(gid, k)))
            finally:
                eccodes.codes_release(gid)

    for k in ("units", "stepType", "dataDate", "dataTime"):
        if len(meta[k]) != 1:
            raise ValueError(f"Mixed {k} in file: {meta[k]}")
    thresholds = sorted({t for t, _ in fields})
    windows = sorted({w for _, w in fields})
    missing = [(t, w) for t in thresholds for w in windows if (t, w) not in fields]
    if missing:
        raise ValueError(f"Missing threshold/window combinations: {missing}")

    data = np.stack([np.stack([fields[(t, w)] for w in windows]) for t in thresholds])
    lons_signed = np.where(lons > 180, lons - 360, lons)
    order = np.argsort(lons_signed)
    da = xr.DataArray(
        data[..., order],
        dims=("threshold", "window", "latitude", "longitude"),
        coords={
            "threshold": ("threshold", np.array(thresholds), {"units": "mm (24 h total)"}),
            "start_h": ("window", np.array([w[0] for w in windows])),
            "end_h": ("window", np.array([w[1] for w in windows])),
            "latitude": lats,
            "longitude": lons_signed[order],
        },
        attrs={
            "units": meta["units"].pop(),
            "stepType": meta["stepType"].pop(),
            "dataDate": meta["dataDate"].pop(),
            "dataTime": meta["dataTime"].pop(),
            "meaning": "probability that the 24 h total exceeds the threshold (probabilityType 3)",
        },
    )
    return da


def read_region(path: str) -> xr.DataArray:
    return crop(read_ens_probs(path))


def member_fraction_check(p: np.ndarray, members: int = 51) -> float:
    """Max distance of probabilities from the k/members grid, in units of one member.

    If ENS probabilities are 'k of 51 members', p * 51 / 100 is (nearly) an integer;
    packing can move it by up to half a quantum.
    """
    k = p * members / 100.0
    return float(np.abs(k - np.round(k)).max())
