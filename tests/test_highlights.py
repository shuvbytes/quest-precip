"""Story mode (feature 5): every highlight satisfies its rule, checked independently on the stored values."""
import json
from pathlib import Path

import numpy as np


def _load(built):
    from build import read_points
    out, m = built
    return m, read_points(out / "points.bin", m["points"]), m["highlights"]


def test_highlights_follow_the_rules(built):
    from disagree import clusters, keep_min_cluster
    from highlights import _km
    m, a, hs = _load(built)
    g, P = m["grid"], m["products"]
    keys = [f"{t:g}" for t in P["ens_prob"]["thresholds_mm"]]
    w24, ens = a["hres_24h"], a["ens_prob"]
    rules = [h["rule"] for h in hs]
    assert rules[:4] == ["heaviest", "city", "disagreement", "contrast"] and 4 <= len(hs) <= 5   # city second (user, 14 Nov)
    for i, h in enumerate(hs):                     # >= 300 km apart
        for j in hs[:i]:
            assert _km(h["lat"], h["lon"], j["lat"], j["lon"]) >= 300, (h["rule"], j["rule"])
        assert h["lat"] == round(g["lat_north"] - h["row"] * g["dlat"], 2) and h["t"] in [f["start_h"] for f in P["hres_24h"]["frames"]]
    by = {h["rule"]: h for h in hs}
    H = by["heaviest"]
    assert w24[H["window"], H["row"], H["col"]] == w24.max()               # the largest 24 h total in the run (first spot)
    Dg = by["disagreement"]
    assert float(Dg["x"]) >= 10
    fr = P["disagreement"]["frames_by_threshold"][Dg["x"]][Dg["window"]]
    idx = Dg["row"] * g["nlon"] + Dg["col"]
    assert idx in fr["cells_" + Dg["kind"]]
    biggest = 0
    for x in [k for k in keys if float(k) >= 10]:                          # no larger marked group at X >= 10 mm
        for f in P["disagreement"]["frames_by_threshold"][x]:
            for kind in ("wetter", "drier"):
                mask = np.zeros(g["nlat"] * g["nlon"], bool); mask[f["cells_" + kind]] = True
                kept = keep_min_cluster(mask.reshape(g["nlat"], g["nlon"]), P["disagreement"]["map_min_cluster"])
                sizes, _ = clusters(kept)
                biggest = max([biggest, *[int(v) for v in sizes]])
    assert Dg["cells"] == biggest
    C = by["contrast"]
    wet = w24[C["window"]] >= 20
    sizes, lab = clusters(wet)
    assert wet[C["row"], C["col"]] and sizes[lab[C["row"], C["col"]] - 1] >= 3
    dr, dc = round((g["lat_north"] - C["dry_lat"]) / g["dlat"]), round((C["dry_lon"] - g["lon_west"]) / g["dlon"])
    assert w24[C["window"], dr, dc] < 1 and max(abs(dr - C["row"]), abs(dc - C["col"])) <= 2
    Ci = by["city"]
    assert Ci["x"] == "10" and Ci["city"]
    places = json.loads((Path(__file__).resolve().parent.parent / "web" / "geo" / "places.json").read_text())
    rows = [dict(zip(places["fields"], r)) for r in places["places"]]
    p = next(r for r in rows if r["name"] == Ci["city"])
    assert p["population"] >= 1_000_000 and p["area"].endswith("India")
    if "confident" in by:
        F = by["confident"]
        assert ens[keys.index("50"), F["window"], F["row"], F["col"]] >= 30
