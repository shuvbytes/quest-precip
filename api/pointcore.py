"""Point forecast logic shared by the API (api/app.py) and the panel check (pipeline/m6_check.py).

numpy only, so the API image stays small. Every rule mirrors the browser panel (web/app.js):
- nearest grid point, inside the image bounds (cell edges) only            -> gridPoint()
- values below a frame's lowest drawn legend step print as "< 0.5 mm" etc. -> fmtMm(), fmtPct()
- "nearby" = min-max over the 3x3 neighbouring grid points (fewer at edges) -> nearby(), nearbyText()
- disagreement flag from the manifest's cell lists; on the map only if its 8-connected group has >= map_min_cluster
  cells                                                                    -> cellFlag(), clusterSize()
- wetter sentence: "Heavy rain..." only when X >= heavy_from_mm             -> renderPointContent()
The page and this module are checked against each other field by field (pipeline/m6_check.py, 697/697).
"""
from __future__ import annotations

import math

import numpy as np


# ---------- decoding points.bin (layout from manifest["points"]) ----------

def decode(manifest: dict, raw: bytes) -> dict[str, np.ndarray]:
    """points.bin -> {name: array in its units (mm or %)}, little-endian as stated in the manifest."""
    P = manifest["points"]
    if P["byte_order"] != "little":
        raise ValueError(f"unexpected byte order {P['byte_order']!r}")
    if len(raw) != P["bytes"]:
        raise ValueError(f"points.bin is {len(raw)} bytes, manifest says {P['bytes']}")
    out = {}
    for a in P["arrays"]:
        dt = {"uint16": "<u2", "uint8": "u1"}[a["dtype"]]
        out[a["name"]] = np.frombuffer(raw, dt, count=int(np.prod(a["shape"])), offset=a["offset"]) \
            .reshape(a["shape"]) * a["scale"]
    return out


# ---------- selection ----------

def grid_point(m: dict, lat: float, lon: float):
    """Nearest grid point (row, col, lat, lon), or None outside the forecast area (image bounds = cell edges)."""
    g = m["grid"]
    (s, w), (n, e) = m["image"]["bounds"]
    if not (s <= lat <= n and w <= lon <= e):
        return None
    row = min(g["nlat"] - 1, max(0, int(round((g["lat_north"] - lat) / g["dlat"]))))
    col = min(g["nlon"] - 1, max(0, int(round((lon - g["lon_west"]) / g["dlon"]))))
    return row, col, g["lat_north"] - row * g["dlat"], g["lon_west"] + col * g["dlon"]


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance (km, mean Earth radius 6371 km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def window_index(frames, t):
    """Last frame starting at or before hour t (the page's frameIndex)."""
    return max((i for i, f in enumerate(frames) if f["start_h"] <= t), default=0)


# ---------- formatting (the panel's text rules) ----------

def js_num(v) -> str:
    """JavaScript Number(v).toString() for the values used here (0.5 -> '0.5', 1.0 -> '1')."""
    v = float(v)
    return str(int(v)) if v == int(v) else repr(v)


def js_round(v) -> int:
    """Math.round (halves round up, unlike Python's round)."""
    return int(np.floor(v + 0.5))


def fmt_mm(v, floor) -> str:
    return f"< {js_num(floor)} mm" if v < floor else f"{v:.1f} mm"


def fmt_pct(v, floor) -> str:
    return f"< {js_num(floor)} %" if v < floor else f"{js_round(v)} %"


def nearby_text(lo, hi, floor) -> str:
    if hi < floor:
        return f"nearby: all < {js_num(floor)} mm"
    return f"nearby: {('< ' + js_num(floor)) if lo < floor else f'{lo:.1f}'}–{hi:.1f} mm"


def nearby(arr2d, row, col):
    """(min, max) over the 3x3 neighbourhood that exists."""
    nb = arr2d[max(0, row - 1):row + 2, max(0, col - 1):col + 2]
    return float(nb.min()), float(nb.max())


def threshold_keys(m):
    return [js_num(t) for t in m["products"]["ens_prob"]["thresholds_mm"]]


def cluster_size(cells, idx, nlon):
    """Size of the 8-connected group of flagged cells containing idx (0 if idx is not flagged)."""
    cells = set(cells)
    if idx not in cells:
        return 0
    seen, stack = {idx}, [idx]
    while stack:
        i = stack.pop()
        r, c = divmod(i, nlon)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                cc = c + dc
                j = (r + dr) * nlon + cc
                if 0 <= cc < nlon and j not in seen and j in cells:
                    seen.add(j)
                    stack.append(j)
    return len(seen)


def cell_flag(m, x_key, k, idx):
    """{'kind': 'wetter'|'drier', 'on_map': bool} or None, for threshold key x_key and 24 h window k."""
    D = m["products"]["disagreement"]
    fr = D["frames_by_threshold"][x_key][k]
    for kind in ("wetter", "drier"):
        cells = fr["cells_" + kind]
        if idx in cells:
            return {"kind": kind, "on_map": cluster_size(cells, idx, m["grid"]["nlon"]) >= D["map_min_cluster"]}
    return None


def point_text_key(m, kind, x_key):
    D = m["products"]["disagreement"]
    return "wetter_heavy" if kind == "wetter" and float(x_key) >= D["heavy_from_mm"] else kind


def disagreement_sentence(m, kind, x_key, hres_mm, pct):
    t = m["products"]["disagreement"]["point_text"][point_text_key(m, kind, x_key)]
    return t.replace("{hres}", f"{hres_mm:.1f}").replace("{pct}", str(js_round(pct))).replace("{x}", x_key)


def not_on_map_text(m):
    return ("This point is not marked on the map: the map only marks groups of "
            f"{m['products']['disagreement']['map_min_cluster']} or more touching grid points.")


# ---------- the panel's fields, as {data-field: text} (used by m6_check to compare with the page) ----------

def panel_fields(m, arrays, row, col, x_key, t):
    """Every text the panel shows with a data-field, for 24 h mode at threshold x_key and start hour t."""
    P, g = m["products"], m["grid"]
    idx = row * g["nlon"] + col
    h3, h24, ens = arrays["hres_3h"], arrays["hres_24h"], arrays["ens_prob"]
    exp = {}
    for k, f in enumerate(P["hres_3h"]["frames"]):
        exp[f"h3-{k}"] = fmt_mm(h3[k, row, col], f["lowest_drawn"])
    for k, f in enumerate(P["hres_24h"]["frames"]):
        v = h24[k, row, col]
        exp[f"h24-{k}"] = f"< {js_num(f['lowest_drawn'])}" if v < f["lowest_drawn"] else f"{v:.1f}"
    keys = threshold_keys(m)
    for kx, x in enumerate(keys):
        for k, f in enumerate(P["ens_prob"]["frames_by_threshold"][x]):
            v = ens[kx, k, row, col]
            txt = f"< {js_num(f['lowest_drawn'])}" if v < f["lowest_drawn"] else f"{js_round(v)}"
            fl = cell_flag(m, x, k, idx)
            if fl:
                txt += " ▨" if fl["kind"] == "wetter" else " •"
            exp[f"ens-{x}-{k}"] = txt
    s = summary(m, arrays, row, col, x_key, t)
    exp.update({"sum-24h": s["rain"], "near-24h": s["nearby"], "sum-ens": s["chance"]})
    if s["disagreement"]:
        exp["disagree"] = s["disagreement"]
    return exp


def summary(m, arrays, row, col, x_key, t):
    """The panel's selected-window summary (24 h mode): the exact strings shown at the top of the panel."""
    P, g = m["products"], m["grid"]
    k = window_index(P["hres_24h"]["frames"], t)
    f = P["hres_24h"]["frames"][k]
    kx = threshold_keys(m).index(x_key)
    v = float(arrays["hres_24h"][k, row, col])
    lo, hi = nearby(arrays["hres_24h"][k], row, col)
    pct = float(arrays["ens_prob"][kx, k, row, col])
    ef = P["ens_prob"]["frames_by_threshold"][x_key][k]
    fl = cell_flag(m, x_key, k, row * g["nlon"] + col)
    return {
        "window": f["label_ist"], "start_h": f["start_h"], "end_h": f["end_h"], "threshold_mm": float(x_key),
        "rain": f"Rain in 24 hours (HRES): {fmt_mm(v, f['lowest_drawn'])}",
        "nearby": nearby_text(lo, hi, f["lowest_drawn"]),
        "chance": f"Chance of ≥ {x_key} mm (ENS): {fmt_pct(pct, ef['lowest_drawn'])}",
        "disagreement": disagreement_sentence(m, fl["kind"], x_key, v, pct) if fl else None,
        "disagreement_note": (None if not fl or fl["on_map"] else not_on_map_text(m)),
    }


# ---------- the API's full answer ----------

def _r1(v):
    return round(float(v), 1)


def point_report(m, arrays, lat, lon, x_key, t):
    """Everything the panel shows for (lat, lon), as numbers + the panel's exact texts. None if outside the area."""
    gp = grid_point(m, lat, lon)
    if gp is None:
        return None
    row, col, glat, glon = gp
    P, g = m["products"], m["grid"]
    idx = row * g["nlon"] + col
    h3, h24, ens = arrays["hres_3h"], arrays["hres_24h"], arrays["ens_prob"]

    def series(name, arr):
        out = []
        for k, f in enumerate(P[name]["frames"]):
            v = float(arr[k, row, col])
            lo, hi = nearby(arr[k], row, col)
            out.append({"start_utc": f["start_utc"], "end_utc": f["end_utc"], "label_ist": f["label_ist"],
                        "start_h": f["start_h"], "end_h": f["end_h"], "mm": _r1(v),
                        "text": fmt_mm(v, f["lowest_drawn"]), "lowest_shown_mm": f["lowest_drawn"],
                        "nearby_min_mm": _r1(lo), "nearby_max_mm": _r1(hi),
                        "nearby_text": nearby_text(lo, hi, f["lowest_drawn"])})
        return out

    chances = {}
    for kx, x in enumerate(threshold_keys(m)):
        rows = []
        for k, f in enumerate(P["ens_prob"]["frames_by_threshold"][x]):
            v = float(ens[kx, k, row, col])
            fl = cell_flag(m, x, k, idx)
            if fl:
                fl = {**fl, "sentence": disagreement_sentence(m, fl["kind"], x, float(h24[k, row, col]), v)}
            rows.append({"start_utc": f["start_utc"], "end_utc": f["end_utc"], "label_ist": f["label_ist"],
                         "start_h": f["start_h"], "end_h": f["end_h"], "pct": js_round(v),
                         "text": fmt_pct(v, f["lowest_drawn"]), "lowest_shown_pct": f["lowest_drawn"],
                         "disagreement": fl})
        chances[x] = rows
    return {
        "run": {"utc": m["run"]["utc"], "ist": m["run"]["ist"], "generated_utc": m["generated_utc"]},
        "requested": {"lat": lat, "lon": lon},
        "grid_point": {"lat": glat, "lon": glon, "row": row, "col": col,
                       "distance_km": round(distance_km(lat, lon, glat, glon), 2)},
        "value_meaning": g["value_meaning"],
        "units": {"rain": "mm", "chance": "%"},
        "summary": summary(m, arrays, row, col, x_key, t),
        "hres_3h": series("hres_3h", h3),
        "hres_24h": series("hres_24h", h24),
        "ens_chance": chances,
    }
