"""The point API (api/): same values as points.bin and the same texts as the browser panel."""
import numpy as np
import pytest

PLACES = {"chennai": (13.0827, 80.2707, 13.00, 80.25), "bay": (15.00, 86.50, 15.00, 86.50),
          "dry": (22.00, 78.00, 22.00, 78.00)}


@pytest.fixture(scope="module")
def data(built):
    import pointcore as pc
    from build import read_points
    out, m = built
    return m, pc.decode(m, (out / "points.bin").read_bytes()), read_points(out / "points.bin", m["points"])


def test_decode_equals_build_reader(data):
    """The API's numpy-only decoder gives exactly what build.read_points (the pipeline's reader) gives."""
    m, api, ref = data
    assert set(api) == set(ref) == {"hres_3h", "hres_24h", "ens_prob"}
    for k in ref:
        np.testing.assert_array_equal(api[k], ref[k])


@pytest.mark.parametrize("place", PLACES)
def test_report_values_equal_points_bin(data, place):
    """Every number in the report equals the stored value at the nearest grid point (0.1 mm / whole %)."""
    import pointcore as pc
    m, _, ref = data
    lat, lon, glat, glon = PLACES[place]
    r = pc.point_report(m, data[1], lat, lon, "10", 0)
    g = m["grid"]
    row, col = round((g["lat_north"] - glat) / g["dlat"]), round((glon - g["lon_west"]) / g["dlon"])
    assert (r["grid_point"]["lat"], r["grid_point"]["lon"], r["grid_point"]["row"], r["grid_point"]["col"]) == \
        (glat, glon, row, col)
    assert [e["mm"] for e in r["hres_3h"]] == [round(float(v), 1) for v in ref["hres_3h"][:, row, col]]
    assert [e["mm"] for e in r["hres_24h"]] == [round(float(v), 1) for v in ref["hres_24h"][:, row, col]]
    for kx, x in enumerate(pc.threshold_keys(m)):
        assert [e["pct"] for e in r["ens_chance"][x]] == [int(v) for v in ref["ens_prob"][kx, :, row, col]]
    for k, e in enumerate(r["hres_24h"]):
        nb = ref["hres_24h"][k, max(0, row - 1):row + 2, max(0, col - 1):col + 2]
        assert (e["nearby_min_mm"], e["nearby_max_mm"]) == (round(float(nb.min()), 1), round(float(nb.max()), 1))
    assert r["value_meaning"] == m["grid"]["value_meaning"]


@pytest.mark.parametrize("place", PLACES)
def test_report_texts_equal_panel_texts(data, place):
    """The report's texts are the panel's texts (pointcore.panel_fields = what m6_check compares with the page)."""
    import pointcore as pc
    m, arrays, _ = data
    lat, lon, _, _ = PLACES[place]
    for x, t in (("10", 0), ("100", 60), ("1", 120)):
        r = pc.point_report(m, arrays, lat, lon, x, t)
        f = pc.panel_fields(m, arrays, r["grid_point"]["row"], r["grid_point"]["col"], x, t)
        assert [e["text"] for e in r["hres_3h"]] == [f[f"h3-{k}"] for k in range(len(r["hres_3h"]))]
        assert (r["summary"]["rain"], r["summary"]["nearby"], r["summary"]["chance"]) == \
            (f["sum-24h"], f["near-24h"], f["sum-ens"])
        assert r["summary"]["disagreement"] == f.get("disagree")


def test_flag_sentences_follow_threshold_wording(data):
    """Every flagged cell in the report carries the sentence for its threshold (Heavy only from 50 mm)."""
    import pointcore as pc
    m, arrays, _ = data
    D, g, n = m["products"]["disagreement"], m["grid"], 0
    for x in pc.threshold_keys(m):
        for k, fr in enumerate(D["frames_by_threshold"][x]):
            for idx in fr["cells_wetter"][:2]:
                row, col = divmod(idx, g["nlon"])
                lat, lon = g["lat_north"] - row * g["dlat"], g["lon_west"] + col * g["dlon"]
                e = pc.point_report(m, arrays, lat, lon, x, 0)["ens_chance"][x][k]["disagreement"]
                assert e["kind"] == "wetter"
                heavy = e["sentence"].endswith("Heavy rain is possible, not likely.")
                assert heavy == (float(x) >= 50), (x, e["sentence"])
                n += 1
    assert n > 0


def test_outside_area_is_none(data):
    import pointcore as pc
    m, arrays, _ = data
    assert pc.point_report(m, arrays, 40.0, 80.0, "10", 0) is None       # north of 38.125
    assert pc.point_report(m, arrays, 20.0, 101.0, "10", 0) is None      # east of 100.125
    assert pc.point_report(m, arrays, 38.1, 100.1, "10", 0) is not None  # inside the corner cell
