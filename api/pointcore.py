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


# ---------- "Near <place>" (M8 A): nearest listed place, same rule as the page (web/app.js nearText) ----------

NEAR_KM = 25                         # up to this distance: "Near Chennai (9 km)"; beyond: "420 km E of Chennai"
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
PLACE_KINDS = ("city", "capital", "state_capital")


def places_from_json(doc):
    """geo/places.json -> list of dicts (cities only; country and sea labels are not places to be near)."""
    rows = [dict(zip(doc["fields"], r)) for r in doc["places"]]
    return [r for r in rows if r["kind"] in PLACE_KINDS]


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial great-circle bearing from point 1 to point 2, degrees clockwise from north."""
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def near(places, lat, lon):
    """Nearest place to (lat, lon) and the panel's sentence for it."""
    best = min(places, key=lambda p: distance_km(lat, lon, p["lat"], p["lon"]))
    d = distance_km(lat, lon, best["lat"], best["lon"])
    b = bearing_deg(best["lat"], best["lon"], lat, lon)
    km, side = js_round(d), COMPASS[js_round(b / 45) % 8]
    text = f"Near {best['name']} ({km} km)" if d <= NEAR_KM else f"{km} km {side} of {best['name']}"
    return {"name": best["name"], "area": best["area"], "distance_km": round(d, 1), "bearing_deg": round(b, 1),
            "direction": side, "text": text}


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

def panel_fields(m, arrays, row, col, x_key, t, places=None):
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
    if places:
        exp["near"] = near(places, g["lat_north"] - row * g["dlat"], g["lon_west"] + col * g["dlon"])["text"]
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


def point_report(m, arrays, lat, lon, x_key, t, places=None):
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
        "near": near(places, glat, glon) if places else None,
        "value_meaning": g["value_meaning"],
        "units": {"rain": "mm", "chance": "%"},
        "summary": summary(m, arrays, row, col, x_key, t),
        "hres_3h": series("hres_3h", h3),
        "hres_24h": series("hres_24h", h24),
        "ens_chance": chances,
    }


# ---------- "Plan my day" (feature 4): twin of web/app.js planDay; every string is compared by m8_checks.py plan ----------

import datetime as _dt

_IST = _dt.timedelta(hours=5, minutes=30)
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _utc(iso):
    return _dt.datetime.strptime(iso, "%Y-%m-%dT%H:%MZ")


def _ist(t):
    return t + _IST


# A plan day is the 24 h from 23:30 IST the evening before to 23:30 IST (user, 14 Nov): the 3 h steps start at :30 IST
# (00/03.. UTC = 05:30/08:30.. IST; 12z runs too), so this is exactly 8 windows, the closest the grid allows to midnight-midnight.
_SHIFT = _dt.timedelta(minutes=30)


def _bounds(day):
    d0 = _dt.datetime.fromisoformat(day) - _IST - _SHIFT          # 23:30 IST the evening before, in UTC
    return d0, d0 + _dt.timedelta(days=1)


def plan_days(m):
    """IST days with at least one 3 h window inside their 23:30 -> 23:30 span, in order."""
    out = []
    for f in m["products"]["hres_3h"]["frames"]:
        d = (_ist(_utc(f["start_utc"])) + _SHIFT).date().isoformat()
        if d not in out:
            out.append(d)
    return out


def day_label(day):
    d = _dt.date.fromisoformat(day)
    return f"{_DAYS[d.weekday()]} {d.day:02d} {_MONTHS[d.month - 1]}"


def plan_day(m, arrays, row, col, day, x_key):
    """The 'Plan my day' block for one grid point, IST day (YYYY-MM-DD) and ENS threshold, as the page shows it."""
    P = m["products"]
    d0, d1 = _bounds(day)
    on_day = (_dt.datetime.fromisoformat(day)).date()
    dname = lambda t: _DAYS[_ist(t).weekday()]
    def hm(t):                                                    # "08:30", "23:30 (Sat)"
        return _ist(t).strftime("%H:%M") + ("" if _ist(t).date() == on_day else f" ({dname(t)})")
    entries = []
    for k, f in enumerate(P["hres_3h"]["frames"]):
        a, b = _utc(f["start_utc"]), _utc(f["end_utc"])
        if a >= d0 and b <= d1:
            v = float(arrays["hres_3h"][k, row, col])
            entries.append({"a": a, "b": b, "label": f"{hm(a)}–{hm(b)}", "text": fmt_mm(v, f["lowest_drawn"]),
                            "dry": v < f["lowest_drawn"]})
    # longest run of consecutive dry windows (earliest if tied)
    best, run = None, []
    for e in entries + [None]:
        if e is not None and e["dry"]:
            run.append(e)
            continue
        if run and (best is None or len(run) > len(best)):
            best = run
        run = []
    if entries and all(e["dry"] for e in entries):
        stretch = "Dry in every 3-hour window shown (each below the lowest amount shown)."
    elif best is None:
        stretch = "No dry 3-hour window on this day."
    else:
        stretch = f"Driest stretch: {hm(best[0]['a'])}–{hm(best[-1]['b'])} IST."
    # ENS 24 h window overlapping the day most (earliest if tied)
    kx = threshold_keys(m).index(x_key)
    ov = []
    for k, f in enumerate(P["ens_prob"]["frames_by_threshold"][x_key]):
        a, b = _utc(f["start_utc"]), _utc(f["end_utc"])
        ov.append(((min(b, d1) - max(a, d0)).total_seconds() / 3600, k, f))
    hours, k, f = max(ov, key=lambda t: (t[0], -t[1]))
    pct = fmt_pct(float(arrays["ens_prob"][kx, k, row, col]), f["lowest_drawn"])
    chance = f"Chance of ≥ {x_key} mm in the window {f['label_ist']}: {pct}."
    note = (f"The ensemble's 24-hour window covers {js_num(round(hours, 1))} of this day's 24 hours; "
            f"its windows do not follow calendar days.")
    covered = sum((e["b"] - e["a"]).total_seconds() / 3600 for e in entries)
    cover = "" if covered >= 24 else (f"The forecast covers only {js_num(round(covered, 1))} hours of this day "
                                      f"({hm(entries[0]['a'])}–{hm(entries[-1]['b'])} IST).")
    return {"day": day_label(day), "span": f"23:30 {dname(d0)} → 23:30 {dname(d1 - _dt.timedelta(minutes=1))} IST", "entries": [{k_: e[k_] for k_ in ("label", "text", "dry")} for e in entries],
            "stretch": stretch, "chance": chance, "note": note, "cover": cover}
