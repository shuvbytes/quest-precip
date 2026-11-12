import datetime as dt
from pathlib import Path

import pytest

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
HRES = sorted(RAW.glob("hres_tp_*.grib2"))
ENS = sorted(RAW.glob("ens_tpg_*.grib2"))
pytestmark = pytest.mark.skipif(not (HRES and ENS), reason="real GRIB not downloaded")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    import io
    from contextlib import redirect_stdout
    from build import main
    out = tmp_path_factory.mktemp("site")
    with redirect_stdout(io.StringIO()):
        main(str(HRES[-1]), str(ENS[-1]), out)
    import json
    return out, json.loads((out / "manifest.json").read_text())


def all_frames(m):
    P = m["products"]
    yield from P["hres_3h"]["frames"]
    yield from P["hres_24h"]["frames"]
    for fr in P["ens_prob"]["frames_by_threshold"].values():
        yield from fr


def test_counts(built):
    _, m = built
    P = m["products"]
    assert len(P["hres_3h"]["frames"]) == 48
    assert len(P["hres_24h"]["frames"]) == 11
    assert sum(len(v) for v in P["ens_prob"]["frames_by_threshold"].values()) == 77


def test_ist_labels_equal_utc_plus_0530(built):
    _, m = built
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    run = dt.datetime.strptime(m["run"]["utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    assert m["run"]["ist"] == run.astimezone(ist).strftime("%a %d %b %H:%M IST")
    for f in all_frames(m):
        a = dt.datetime.strptime(f["start_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
        b = dt.datetime.strptime(f["end_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
        assert a == run + dt.timedelta(hours=f["start_h"]) and b == run + dt.timedelta(hours=f["end_h"])
        fmt = "%a %d %b %H:%M IST"
        assert f["label_ist"] == f"{a.astimezone(ist).strftime(fmt)} → {b.astimezone(ist).strftime(fmt)}"


def test_floors_and_files(built):
    out, m = built
    for f in all_frames(m):
        assert f["floor"] <= f["lowest_drawn"]
        assert f["floor_raised"] == (f["lowest_drawn"] != _first_bin(m, f))
        assert (out / f["file"]).exists()
    assert "CC BY 4.0" in m["attribution"] and "ECMWF" in m["attribution"]


def test_points_roundtrip(built):
    """Decoding points.bin gives back the original values within 0.1 mm / 1 %."""
    import numpy as np
    import xarray as xr
    from build import HRES_MAX_H, read_points
    from ens import read_region
    from process import deaccumulate
    from region import crop
    out, m = built
    h, e = read_points(out / "points.bin", m["points"])
    tp = crop(xr.open_dataset(HRES[-1], engine="cfgrib", backend_kwargs={"indexpath": ""})["tp"]).load()
    orig_h = deaccumulate(tp).mm.values
    p = read_region(str(ENS[-1]))
    orig_e = p.isel(window=np.where(p.end_h.values <= HRES_MAX_H)[0]).values
    assert h.shape == orig_h.shape and e.shape == orig_e.shape
    assert np.abs(h - orig_h).max() <= 0.1
    assert np.abs(e - orig_e).max() <= 1.0
    assert m["points"]["bytes"] == h.size * 2 + e.size


def _first_bin(m, f):
    P = m["products"]
    if f["file"].startswith("frames/hres3h"):
        return P["hres_3h"]["bins"][0]
    if f["file"].startswith("frames/hres24h"):
        return P["hres_24h"]["bins"][0]
    return P["ens_prob"]["bins"][0]
