from pathlib import Path

import numpy as np
import pytest

from disagree import flags, neighbourhood_max


def test_neighbourhood_max_uses_only_real_neighbours():
    a = np.zeros((4, 4))
    a[0, 0] = 9
    m = neighbourhood_max(a)
    assert m[0, 0] == 9 and m[1, 1] == 9 and m[2, 2] == 0


def test_wetter_needs_whole_neighbourhood_below_25():
    h = np.zeros((5, 5)); h[2, 2] = 30
    p = np.full((5, 5), 10.0)
    wet, dry = flags(h, p, 10)
    assert wet[2, 2] and wet.sum() == 1 and not dry.any()
    p[1, 3] = 40                       # ensemble has the rain one cell away -> not a disagreement
    wet, _ = flags(h, p, 10)
    assert not wet.any()


def test_wetter_boundaries():
    h = np.full((3, 3), 10.0); p = np.full((3, 3), 24.9)
    assert flags(h, p, 10)[0][1, 1]            # HRES exactly X counts, P just under 25
    p[:] = 25.0
    assert not flags(h, p, 10)[0].any()        # P = 25 is not "below 25"


def test_drier_needs_hres_dry_in_whole_neighbourhood():
    h = np.zeros((5, 5)); p = np.zeros((5, 5)); p[2, 2] = 80
    _, dry = flags(h, p, 10)
    assert dry[2, 2] and dry.sum() == 1
    h[3, 3] = 12                               # HRES has >= X next door -> not a disagreement
    assert not flags(h, p, 10)[1].any()
    h[3, 3] = 0; p[2, 2] = 75.0
    assert flags(h, p, 10)[1][2, 2]            # 75 counts as "likely"


RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


@pytest.mark.skipif(not (list(RAW.glob("hres_tp_*")) and list(RAW.glob("ens_tpg_*"))), reason="no real data")
def test_real_run_counts_match_proposal():
    """Counts quoted in the proposal for run 2026-11-12 00z (X = 10 mm)."""
    import xarray as xr
    from ens import read_region
    from process import window_totals
    from region import crop
    h_path = sorted(RAW.glob("hres_tp_2026111200z*"))
    if not h_path:
        pytest.skip("proposal run not downloaded")
    tp = crop(xr.open_dataset(h_path[0], engine="cfgrib", backend_kwargs={"indexpath": ""})["tp"]).load()
    w = window_totals(tp)
    p = read_region(str(RAW / "ens_tpg_2026111200z.grib2")).sel(threshold=10)
    got = []
    for s in (0, 48, 120):
        k = list(w.start_h).index(s)
        kp = int(np.where(p.start_h.values == s)[0][0])
        wet, dry = flags(w.mm.values[k], p.values[kp], 10)
        got.append((int(wet.sum()), int(dry.sum())))
    assert got == [(33, 0), (26, 0), (165, 0)]
