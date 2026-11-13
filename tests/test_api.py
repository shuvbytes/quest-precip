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


# ---------- the FastAPI app (api/app.py), on local files ----------

@pytest.fixture()
def client(built, monkeypatch, tmp_path):
    """TestClient on a copy of the built data folder (so a test can change the manifest)."""
    import shutil
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import app as api
    out, _ = built
    d = tmp_path / "data"
    d.mkdir()
    for f in ("manifest.json", "points.bin"):
        shutil.copy(out / f, d / f)
    monkeypatch.setattr(api, "DATA_DIR", str(d))
    monkeypatch.setattr(api, "store", api.Store())
    api.store.refresh()
    assert api.store.data, api.store.last_error
    with TestClient(api.app) as c:
        c.data_dir = d
        yield c


@pytest.mark.parametrize("place", PLACES)
def test_api_point_matches_points_bin(client, data, place):
    m, _, ref = data
    lat, lon, glat, glon = PLACES[place]
    r = client.get("/point", params={"lat": lat, "lon": lon, "x": 100, "t": 60})
    assert r.status_code == 200, r.text
    j = r.json()
    g = m["grid"]
    row, col = round((g["lat_north"] - glat) / g["dlat"]), round((glon - g["lon_west"]) / g["dlon"])
    assert (j["grid_point"]["lat"], j["grid_point"]["lon"]) == (glat, glon)
    assert [e["mm"] for e in j["hres_3h"]] == [round(float(v), 1) for v in ref["hres_3h"][:, row, col]]
    assert [e["mm"] for e in j["hres_24h"]] == [round(float(v), 1) for v in ref["hres_24h"][:, row, col]]
    assert [e["pct"] for e in j["ens_chance"]["100"]] == [int(v) for v in ref["ens_prob"][-1, :, row, col]]
    assert j["run"]["utc"] == m["run"]["utc"] and j["run"]["generated_utc"] == m["generated_utc"]
    assert j["summary"]["start_h"] == 60 and j["summary"]["threshold_mm"] == 100
    assert "CC BY 4.0" in j["source"]["attribution"]


def test_api_health(client, built):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["run_utc"] == built[1]["run"]["utc"]


@pytest.mark.parametrize("params, says", [
    ({}, "lat: Field required"),
    ({"lat": "abc", "lon": 80}, "lat: Input should be a valid number"),
    ({"lat": 95, "lon": 80}, "lat: Input should be less than or equal to 90"),
    ({"lat": 13, "lon": -200}, "lon: Input should be greater than or equal to -180"),
    ({"lat": "nan", "lon": 80}, "lat: Input should be a finite number"),
    ({"lat": 13, "lon": 80, "x": 7}, "x must be one of 1, 5, 10, 20, 25, 50, 100"),
    ({"lat": 13, "lon": 80, "t": 5}, "t must be one of 0, 12, 24"),
])
def test_api_rejects_bad_input_with_a_clear_message(client, params, says):
    r = client.get("/point", params=params)
    assert r.status_code == 422 and r.json()["error"] == "invalid_request"
    assert says in r.json()["message"], r.json()["message"]


def test_api_outside_area_says_so(client):
    r = client.get("/point", params={"lat": 51.5, "lon": -0.1})
    assert r.status_code == 404 and r.json()["error"] == "outside_forecast_area"
    assert r.json()["message"] == ("No forecast here: (51.50, -0.10) is outside the forecast area, "
                                   "5–38°N, 65–100°E.")


def test_api_cors_only_for_the_site(client):
    ok = client.get("/point", params={"lat": 13, "lon": 80}, headers={"Origin": "https://shuvbytes.github.io"})
    assert ok.headers.get("access-control-allow-origin") == "https://shuvbytes.github.io"
    other = client.get("/point", params={"lat": 13, "lon": 80}, headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in other.headers
    pre = client.options("/point", headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 400


def test_api_reloads_when_a_new_build_appears(client):
    """A changed generated_utc in the manifest -> the next check loads it (as after a new run is deployed)."""
    import json
    import app as api
    f = client.data_dir / "manifest.json"
    m = json.loads(f.read_text())
    m["generated_utc"], m["run"]["utc"] = "2099-01-01T00:00Z", "2099-01-01T00:00Z"
    f.write_text(json.dumps(m))
    api.store.last_check = 0                           # pretend the last check is old
    client.get("/health")                              # schedules the refresh (runs after the response)
    assert client.get("/health").json()["run_utc"] == "2099-01-01T00:00Z"


def test_api_forced_check_loads_a_new_build_at_once(client):
    """/health?check=1 (called after each site deploy) loads a newer build in the same request."""
    import json
    import app as api
    f = client.data_dir / "manifest.json"
    m = json.loads(f.read_text())
    m["generated_utc"] = "2099-02-02T00:00Z"
    f.write_text(json.dumps(m))
    api.store.last_check -= 60                         # outside the 15 s gap between forced checks
    assert client.get("/health", params={"check": 1}).json()["generated_utc"] == "2099-02-02T00:00Z"


def test_api_gzips_point_answers(client):
    """Render's free plan includes 5 GB outbound a month: /point answers go out gzipped (~3 kB instead of ~37 kB)."""
    r = client.get("/point", params={"lat": 15, "lon": 86.5}, headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
