import datetime as dt
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from packing import FieldPacking
from process import (BINS_3H, BINS_24H, UTC, base_time_utc, deaccumulate, difference,
                     ens_window_starts, interval_floor, ist_label, lowest_visible, mm_factor,
                     window_label, window_totals)

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def make_tp(values_m, step_h=3, units="m"):
    values_m = np.asarray(values_m, dtype=np.float32)
    n = values_m.shape[0]
    return xr.DataArray(
        values_m,
        dims=("step", "latitude", "longitude"),
        coords={
            "step": np.arange(n) * np.timedelta64(step_h, "h"),
            "latitude": np.arange(values_m.shape[1], dtype=float)[::-1],
            "longitude": np.arange(values_m.shape[2], dtype=float),
            "time": np.datetime64("2026-11-12T00:00"),
        },
        attrs={"units": units, "GRIB_stepType": "accum"},
    )


# ---- units ----

def test_mm_factor_reads_units():
    assert mm_factor("m") == 1000.0
    assert mm_factor("mm") == 1.0
    with pytest.raises(ValueError):
        mm_factor("inches")


# ---- de-accumulation ----

def test_deaccumulate_simple():
    acc = np.array([0.0, 0.001, 0.003, 0.003]).reshape(4, 1, 1)  # metres
    a = deaccumulate(make_tp(acc))
    np.testing.assert_allclose(a.mm.values.ravel(), [1.0, 2.0, 0.0], atol=1e-6)
    assert a.start_h.tolist() == [0, 3, 6] and a.end_h.tolist() == [3, 6, 9]


def test_negative_noise_is_clipped_and_counted():
    acc = np.array([[0.0, 0.0], [0.002, 0.0005], [0.002, 0.00038]]).reshape(3, 1, 2)
    a = deaccumulate(make_tp(acc))
    assert a.mm.values.min() >= 0
    assert a.n_clipped.tolist() == [0, 1]
    assert a.min_raw_mm[1] == pytest.approx(-0.12, abs=1e-4)


def test_unknown_step_raises():
    with pytest.raises(ValueError):
        difference(make_tp(np.zeros((3, 1, 1))), [0], [24])


# ---- 24 h windows ----

def test_ens_window_starts():
    assert ens_window_starts(144).tolist() == [0, 12, 24, 36, 48, 60, 72, 84, 96, 108, 120]


def test_window_equals_sum_of_3h_synthetic():
    rng = np.random.default_rng(0)
    acc = np.cumsum(rng.gamma(0.3, 0.002, size=(49, 4, 5)), axis=0)  # monotone, metres
    acc[0] = 0
    tp = make_tp(acc)
    w = window_totals(tp)
    three = deaccumulate(tp)
    for k, s in enumerate(w.start_h):
        sel = (three.start_h >= s) & (three.end_h <= s + 24)
        assert sel.sum() == 8
        np.testing.assert_allclose(w.mm.values[k], three.mm.values[sel].sum(axis=0), atol=1e-3)


@pytest.mark.skipif(not list(RAW.glob("hres_tp_*.grib2")), reason="no real GRIB downloaded")
def test_window_vs_3h_on_real_data():
    """On real data the clipped 3 h sum can only exceed TP(t+24)-TP(t), by at most
    the total clipped (packing noise); before clipping the two agree exactly."""
    from region import crop
    path = sorted(RAW.glob("hres_tp_*.grib2"))[-1]
    tp = crop(xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})["tp"]).load()
    v = tp.values.astype(np.float64) * 1000
    three = deaccumulate(tp)
    w = window_totals(tp)
    for k, s in enumerate(w.start_h):
        i0, i1 = s // 3, s // 3 + 8
        raw_sum = (v[i0 + 1:i1 + 1] - v[i0:i1]).sum(axis=0)          # telescoping, unclipped
        np.testing.assert_allclose(raw_sum, v[i1] - v[i0], atol=1e-9)
        clipped_sum = three.mm.values[i0:i1].sum(axis=0)
        excess = clipped_sum - w.mm.values[k]
        assert excess.min() >= -1e-9
        assert excess.max() <= 8 * 0.2441 + 1e-9  # at most 8 clips of <= one quantum each


# ---- time zones ----

def test_base_time_is_utc():
    t = base_time_utc(make_tp(np.zeros((2, 1, 1))))
    assert t == dt.datetime(2026, 11, 12, 0, tzinfo=UTC)


def test_ist_labels():
    base = dt.datetime(2026, 11, 12, 0, tzinfo=UTC)
    assert ist_label(base) == "Thu 12 Nov 05:30 IST"
    assert window_label(base, 24, 48) == "Fri 13 Nov 05:30 IST → Sat 14 Nov 05:30 IST"
    base12 = dt.datetime(2026, 11, 12, 12, tzinfo=UTC)
    assert window_label(base12, 0, 24) == "Thu 12 Nov 17:30 IST → Fri 13 Nov 17:30 IST"
    with pytest.raises(ValueError):
        ist_label(dt.datetime(2026, 11, 12))


# ---- colour scale floor ----

def _packs(step_E):
    return [FieldPacking(step=s, packing_type="grid_ccsds", bits=0 if E is None else 12,
                         E=E or 0, D=0, R=0.0, quantum=0.0 if E is None else 2.0**E)
            for s, E in step_E]


def test_interval_floor_uses_coarser_end():
    packs = _packs([(0, None), (3, -15), (6, -14), (24, -12)])
    f = interval_floor(packs, [0, 3, 0], [3, 6, 24], "m")
    np.testing.assert_allclose(f, [2 * 2**-15 * 1000, 2 * 2**-14 * 1000, 2 * 2**-12 * 1000])


def test_lowest_visible_normal_and_raised():
    assert lowest_visible(BINS_3H, 0.49) == (0.5, False)
    assert lowest_visible(BINS_3H, 0.98) == (1.0, True)     # coarse-quantum run: raised, flagged
    assert lowest_visible(BINS_24H, 0.49) == (1.0, False)
    assert BINS_24H[0] >= 1.0
    with pytest.raises(ValueError):
        lowest_visible(BINS_3H, 500)


@pytest.mark.skipif(not list(RAW.glob("hres_tp_*.grib2")), reason="no real GRIB downloaded")
def test_real_run_floors_below_legend():
    from packing import read_packing
    path = sorted(RAW.glob("hres_tp_*.grib2"))[-1]
    packs = read_packing(str(path))
    steps = [p.step for p in packs]
    f3 = interval_floor(packs, steps[:-1], steps[1:], "m")
    starts = ens_window_starts(steps[-1])
    f24 = interval_floor(packs, starts, starts + 24, "m")
    assert f3.max() <= BINS_3H[0] and f24.max() <= BINS_24H[0]
