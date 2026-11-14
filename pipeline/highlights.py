"""Story mode (feature 5): pick 4-5 interesting spots of this run, deterministically, from the STORED values (points.bin,
the numbers the panel shows), so the selection and the page's captions can never disagree.

Rules (approved by the user, 14 Nov), each over all 24 h windows and grid points inside the forecast area:
 1 heaviest       largest HRES 24 h total
 2 city           (moved up, user 14 Nov) see below
 3 disagreement   largest map-marked disagreement group (8-connected, >= map_min_cluster cells) at thresholds >= 10 mm
                  (lower thresholds only if there is none); spot = its point with the largest HRES total (wetter group)
                  or the largest ENS chance (drier group)
 4 contrast       a wet point (HRES >= 20 mm) inside a group of >= 3 cells with >= 20 mm, with a < 1 mm cell within 2 grid
                  points; the largest wet amount wins
   city           among labelled places with population >= 1 million inside India, the one + window with the highest ENS
                  chance of >= 10 mm (ties: larger HRES total)
 5 confident      the largest ENS chance of >= 50 mm, only if it is >= 30 %
Every spot must be >= 300 km from the spots already chosen; otherwise the rule's next-best candidate is taken.
"""
from __future__ import annotations

import math

import numpy as np

from disagree import clusters, keep_min_cluster

MIN_SEPARATION_KM = 300
WET_MM, DRY_MM, CONTRAST_CELLS, WET_GROUP = 20.0, 1.0, 2, 3
CITY_POP, CITY_X = 1_000_000, "10"
CONFIDENT_X, CONFIDENT_MIN = "50", 30.0


def _km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def select(manifest, arrays, places):
    """-> list of highlight dicts (manifest["highlights"]). arrays = read_points(...) (stored values)."""
    g, P = manifest["grid"], manifest["products"]
    D = P["disagreement"]
    keys = [f"{t:g}" for t in P["ens_prob"]["thresholds_mm"]]
    w24 = arrays["hres_24h"]                     # [window, lat, lon] mm
    ens = arrays["ens_prob"]                     # [threshold, window, lat, lon] %
    starts = [f["start_h"] for f in P["hres_24h"]["frames"]]
    nlat, nlon = g["nlat"], g["nlon"]
    ll = lambda r, c: (round(g["lat_north"] - r * g["dlat"], 2), round(g["lon_west"] + c * g["dlon"], 2))
    chosen = []

    def far_enough(lat, lon):
        return all(_km(lat, lon, h["lat"], h["lon"]) >= MIN_SEPARATION_KM for h in chosen)

    def take(rule, candidates, build):
        """candidates: iterable of (score, k, r, c, extra) best first; first one far enough is used."""
        for score, k, r, c, extra in candidates:
            lat, lon = ll(r, c)
            if far_enough(lat, lon):
                chosen.append({"rule": rule, "lat": lat, "lon": lon, "row": int(r), "col": int(c),
                               "t": starts[k], "window": int(k), **build(k, r, c, extra)})
                return True
        return False

    # 1 heaviest
    order = np.argsort(w24, axis=None)[::-1]
    def cand_heaviest():
        for i in order[:5000]:
            k, r, c = np.unravel_index(i, w24.shape)
            yield float(w24[k, r, c]), k, r, c, None
    take("heaviest", cand_heaviest(), lambda k, r, c, e: {"fill": "rain", "x": CONFIDENT_X, "hatch": True})

    # 2 major city (user, 14 Nov: chosen right after the heaviest stop, so the best city is not pushed
    # aside by later stops of the same storm; e.g. 14 Nov 00z: Visakhapatnam 52 % instead of Chennai 33 %) in India with the highest chance of >= 10 mm
    kx10 = keys.index(CITY_X)
    def cand_city():
        out = []
        for p in places:
            if p["kind"] not in ("city", "capital", "state_capital") or p["population"] < CITY_POP or not p["area"].endswith("India"):
                continue
            r = int(round((g["lat_north"] - p["lat"]) / g["dlat"]))
            c = int(round((p["lon"] - g["lon_west"]) / g["dlon"]))
            if not (0 <= r < nlat and 0 <= c < nlon):
                continue
            for k in range(w24.shape[0]):
                out.append(((float(ens[kx10, k, r, c]), float(w24[k, r, c])), k, r, c, p["name"]))
        return sorted(out, key=lambda t: (-t[0][0], -t[0][1], t[1]))
    take("city", cand_city(), lambda k, r, c, e: {"fill": "chance", "x": CITY_X, "hatch": True, "city": e})

    # 2 largest disagreement group at X >= 10 mm (fallback: lower X)
    def groups(xs):
        out = []
        for x in xs:
            for k, fr in enumerate(D["frames_by_threshold"][x]):
                for kind in ("wetter", "drier"):
                    if not fr["cells_" + kind]:
                        continue
                    mask = np.zeros(nlat * nlon, bool)
                    mask[fr["cells_" + kind]] = True
                    mask = keep_min_cluster(mask.reshape(nlat, nlon), D["map_min_cluster"])
                    sizes, lab = clusters(mask)
                    for gi, size in enumerate(sizes, start=1):
                        rr, cc = np.nonzero(lab == gi)
                        kx = keys.index(x)
                        vals = w24[k, rr, cc] if kind == "wetter" else ens[kx, k, rr, cc]
                        j = int(np.argmax(vals))
                        out.append((int(size), k, int(rr[j]), int(cc[j]), {"x": x, "kind": kind, "cells": int(size)}))
        return sorted(out, key=lambda t: (-t[0], t[1]))
    big = [x for x in keys if float(x) >= 10]
    if not take("disagreement", groups(big), lambda k, r, c, e: {"fill": "chance", "x": e["x"], "hatch": True,
                                                                  "kind": e["kind"], "cells": e["cells"]}):
        take("disagreement", groups([x for x in keys if float(x) < 10]),
             lambda k, r, c, e: {"fill": "chance", "x": e["x"], "hatch": True, "kind": e["kind"], "cells": e["cells"]})

    # 3 dry-vs-wet contrast
    def cand_contrast():
        out = []
        for k in range(w24.shape[0]):
            wet = w24[k] >= WET_MM
            sizes, lab = clusters(wet)
            dry = w24[k] < DRY_MM
            for r, c in zip(*np.nonzero(wet)):
                if sizes[lab[r, c] - 1] < WET_GROUP:
                    continue
                r0, r1, c0, c1 = max(0, r - CONTRAST_CELLS), r + CONTRAST_CELLS + 1, max(0, c - CONTRAST_CELLS), c + CONTRAST_CELLS + 1
                dr, dc = np.nonzero(dry[r0:r1, c0:c1])
                if len(dr):
                    # the nearest dry cell (ties: the first in row-major order)
                    d2 = (dr + r0 - r) ** 2 + (dc + c0 - c) ** 2
                    j = int(np.argmin(d2))
                    out.append((float(w24[k, r, c]), k, int(r), int(c), (int(dr[j] + r0), int(dc[j] + c0))))
        return sorted(out, key=lambda t: (-t[0], t[1]))
    take("contrast", cand_contrast(), lambda k, r, c, e: {"fill": "rain", "x": CITY_X, "hatch": False,
                                                          "dry_lat": ll(*e)[0], "dry_lon": ll(*e)[1]})

    # 5 most confident heavy rain
    kx50 = keys.index(CONFIDENT_X)
    e50 = ens[kx50]
    o50 = np.argsort(e50, axis=None)[::-1]
    def cand_conf():
        for i in o50[:5000]:
            k, r, c = np.unravel_index(i, e50.shape)
            if e50[k, r, c] < CONFIDENT_MIN:
                return
            yield float(e50[k, r, c]), k, r, c, None
    take("confident", cand_conf(), lambda k, r, c, e: {"fill": "chance", "x": CONFIDENT_X, "hatch": True})
    return chosen
