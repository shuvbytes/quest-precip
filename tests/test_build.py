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
    out = tmp_path_factory.mktemp("site") / "data"   # build.py copies web/ into out.parent
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


def test_disagreement_layer(built):
    out, m = built
    d = m["products"]["disagreement"]
    assert d["default_on"] is True and d["rule"]["p_unlikely"] == 25 and d["rule"]["p_likely"] == 75
    frames = [f for v in d["frames_by_threshold"].values() for f in v]
    assert len(frames) == 77
    assert d["map_min_cluster"] == 3 and d["min_zoom_for_marks"] == 6
    assert d["zoom_note"] == "Zoom in to see disagreement marks"
    for f in frames:
        assert (f["file"] is None) == (f["n_wetter_on_map"] + f["n_drier_on_map"] == 0)
        assert f["file"] is None or (out / f["file"]).exists()
        assert (f["file"] is None) == (f["file_bold"] is None)
        assert f["file_bold"] is None or (out / f["file_bold"]).exists()
        assert f["n_wetter"] == len(f["cells_wetter"]) >= f["n_wetter_on_map"]
        assert f["n_drier"] == len(f["cells_drier"]) >= f["n_drier_on_map"]
    if m["run"]["utc"] == "2026-11-12T00:00Z":
        # The Bay case from M3: HRES 369 mm vs ENS P(>=100) ~22 % in 108-132 h -> "wetter"
        g = m["grid"]
        idx = round((g["lat_north"] - 15.0) / g["dlat"]) * g["nlon"] + round((86.5 - g["lon_west"]) / g["dlon"])
        f = next(f for f in d["frames_by_threshold"]["100"] if f["start_h"] == 108)
        assert idx in f["cells_wetter"]


def _hatch_pixels_in_cell(out, f, g, idx):
    """Non-transparent hatch pixels drawn inside grid cell idx (row * nlon + col)."""
    import numpy as np
    from PIL import Image
    from render import Grid, hatch_grid
    if f["file"] is None:
        return 0
    hg = hatch_grid(Grid(g["lat_north"], g["lon_west"], g["dlat"], g["dlon"], g["nlat"], g["nlon"]))
    codes = np.asarray(Image.open(out / f["file"]))
    rows, cols = hg.resample_index()
    i, j = divmod(idx, g["nlon"])
    return int((codes[np.ix_(rows == i, cols == j)] > 0).sum())


def test_map_drops_small_clusters_but_point_panel_keeps_them(built):
    """Isolated flags: listed for the point panel, not hatched on the map. Big clusters: both."""
    import numpy as np
    from disagree import keep_min_cluster
    out, m = built
    g, d = m["grid"], m["products"]["disagreement"]
    checked = 0
    for f in (f for v in d["frames_by_threshold"].values() for f in v):
        for key in ("cells_wetter", "cells_drier"):
            mask = np.zeros(g["nlat"] * g["nlon"], bool)
            mask[f[key]] = True
            mask = mask.reshape(g["nlat"], g["nlon"])
            kept = keep_min_cluster(mask, d["map_min_cluster"])
            dropped = np.flatnonzero(mask & ~kept)
            if len(dropped) and f["file"]:
                assert _hatch_pixels_in_cell(out, f, g, int(dropped[0])) == 0
                checked += 1
            if kept.any():
                assert _hatch_pixels_in_cell(out, f, g, int(np.flatnonzero(kept)[0])) > 0
    assert checked > 0
    if m["run"]["utc"] == "2026-11-12T00:00Z":
        idx = round((g["lat_north"] - 15.0) / g["dlat"]) * g["nlon"] + round((86.5 - g["lon_west"]) / g["dlon"])
        f = next(f for f in d["frames_by_threshold"]["100"] if f["start_h"] == 108)
        assert _hatch_pixels_in_cell(out, f, g, idx) > 0      # Bay point, 26-cell cluster: drawn


def test_site_files_and_basemap_colours(built):
    """The built site is complete, and the page's basemap colours are the ones the palette test checks."""
    from palette import LAND, OCEAN
    out, m = built
    for f in ("index.html", "app.js", "style.css", "geo/land.geojson", "geo/india-boundary.geojson"):
        assert (out.parent / f).exists(), f
    assert m["basemap"]["land"] == LAND and m["basemap"]["sea"] == OCEAN
    assert m["region"] == {"lat_min": 5.0, "lat_max": 38.0, "lon_min": 65.0, "lon_max": 100.0}


def test_vendored_leaflet_matches_integrity_and_page_has_no_cdn():
    """The page loads Leaflet from vendor/, and the files match the integrity hashes in index.html
    (the browser refuses them otherwise, which would leave the map without its library)."""
    import base64
    import hashlib
    import re
    web = Path(__file__).resolve().parent.parent / "web"
    html = (web / "index.html").read_text()
    tags = re.findall(r"<(?:script|link)\b[^>]*integrity=[^>]*>", html, re.S)
    assert len(tags) == 2
    for tag in tags:
        src = re.search(r'(?:src|href)="([^"]+)"', tag).group(1)
        assert src.startswith("vendor/leaflet-1.9.4/"), src
        want = re.search(r'integrity="([^"]+)"', tag).group(1)
        got = "sha512-" + base64.b64encode(hashlib.sha512((web / src).read_bytes()).digest()).decode()
        assert got == want, src
    assert "cdnjs" not in re.sub(r"<!--.*?-->", "", html, flags=re.S)
    assert (web / "vendor/leaflet-1.9.4/LICENSE").exists()


def _first_bin(m, f):
    P = m["products"]
    if f["file"].startswith("frames/hres3h"):
        return P["hres_3h"]["bins"][0]
    if f["file"].startswith("frames/hres24h"):
        return P["hres_24h"]["bins"][0]
    return P["ens_prob"]["bins"][0]
