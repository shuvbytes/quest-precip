from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from process import ens_window_starts, window_totals

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
ENS = sorted(RAW.glob("ens_tpg_*.grib2"))
HRES = sorted(RAW.glob("hres_tp_*.grib2"))
needs = pytest.mark.skipif(not (ENS and HRES), reason="real ENS/HRES GRIB not downloaded")


@pytest.fixture(scope="module")
def probs():
    from ens import read_region
    return read_region(str(ENS[-1]))


@pytest.fixture(scope="module")
def hres24():
    from region import crop
    tp = crop(xr.open_dataset(HRES[-1], engine="cfgrib", backend_kwargs={"indexpath": ""})["tp"]).load()
    return window_totals(tp)


@needs
def test_units_thresholds_windows(probs):
    assert probs.attrs["units"] == "%"
    assert probs.threshold.values.tolist() == [1, 5, 10, 20, 25, 50, 100]
    starts = probs.start_h.values
    assert (probs.end_h.values - starts == 24).all()
    # The windows that overlap the HRES range are exactly the ones process.py builds for HRES.
    assert starts[starts + 24 <= 144].tolist() == ens_window_starts(144).tolist()


@needs
def test_probability_range_and_monotone_in_threshold(probs):
    v = probs.values
    assert v.min() >= 0 and v.max() <= 100
    # P(>= 5 mm) can never be below P(>= 10 mm), up to packing (0.5 % quantum for tpg25+)
    assert (np.diff(v, axis=0) <= 0.5 + 1e-6).all()


@needs
def test_orientation_matches_hres(probs, hres24):
    """Guard against a latitude flip: where HRES has >= 20 mm in the 0-24 h window, the ENS
    chance of >= 1 mm should mostly be high; a flipped grid fails this badly."""
    assert probs.latitude[0] > probs.latitude[-1]
    np.testing.assert_allclose(probs.latitude, hres24.mm.latitude)
    np.testing.assert_allclose(probs.longitude, hres24.mm.longitude)
    wet = hres24.mm.values[0] >= 20
    p1 = probs.sel(threshold=1).isel(window=0).values
    assert wet.sum() > 50
    assert np.median(p1[wet]) > 80
