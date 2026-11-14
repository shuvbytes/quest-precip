"""DEV-ONLY, run once: build the static basemap layers in web/geo/ (committed; not per-run data).

- land.geojson: Natural Earth 10 m land (public domain), clipped to the region + 6 deg margin, simplified.
  Drawn as the land fill only (no outline). No political borders.
- coastline.geojson: Natural Earth 10 m coastline lines (public domain), same clip; drawn as a thin line.
- india-boundary.geojson: DataMeet `Country/india-composite.geojson` (India incl. disputed territories, "in
  accordance with" the Survey of India official boundary), simplified. Drawn as a line on top.
Usage: python pipeline/make_geo.py
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import cartopy.io.shapereader as shpreader
import shapely
from shapely.geometry import box, mapping, shape

from region import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "geo_src"
OUT = ROOT / "web" / "geo"
DATAMEET_COMMIT = "b3fbbde595"      # pinned so the boundary cannot change silently
DATAMEET_URL = f"https://raw.githubusercontent.com/datameet/maps/{DATAMEET_COMMIT}/Country/india-composite.geojson"
DATAMEET_SHA256 = "5e44c39b18aa8fe57267d8018fa4ad4a10eaa3aa4cb7cb7382a1813ef8eb8c53"
MARGIN = 6.0        # land drawn well beyond the data so panning never reaches its clipped edge
TOL = 0.01          # simplification tolerance in degrees (~1 km); the rain cells are 0.25 deg (~28 km)
DECIMALS = 3        # ~100 m


def _round(geom):
    return shapely.set_precision(geom, 10 ** -DECIMALS)


def _write(geom, path, props):
    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature", "properties": props, "geometry": mapping(geom)}]}
    path.write_text(json.dumps(fc, separators=(",", ":")))
    return path.stat().st_size


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clip = box(LON_MIN - MARGIN, LAT_MIN - MARGIN, LON_MAX + MARGIN, LAT_MAX + MARGIN)

    # Land: Natural Earth 10 m (cartopy downloads/caches it)
    land_path = shpreader.natural_earth(resolution="10m", category="physical", name="land")
    parts = [g.intersection(clip) for g in shpreader.Reader(land_path).geometries() if g.intersects(clip)]
    land = _round(shapely.union_all(parts).simplify(TOL, preserve_topology=True))
    n_land = _write(land, OUT / "land.geojson", {"source": "Natural Earth 10m land (public domain)"})

    # Coastline: Natural Earth 10 m coastline LINES. Using the land polygon's outline would also draw the
    # clip edges as lines that look like borders.
    coast_path = shpreader.natural_earth(resolution="10m", category="physical", name="coastline")
    lines = [g.intersection(clip) for g in shpreader.Reader(coast_path).geometries() if g.intersects(clip)]
    coast = _round(shapely.line_merge(shapely.union_all(lines)).simplify(TOL))
    n_coast = _write(coast, OUT / "coastline.geojson", {"source": "Natural Earth 10m coastline (public domain)"})

    # India boundary: DataMeet india-composite, pinned commit + checksum
    src = SRC / "india-composite.geojson"
    if not src.exists():
        SRC.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(DATAMEET_URL, src)
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    if digest != DATAMEET_SHA256:
        raise ValueError(f"india-composite.geojson checksum {digest} != pinned {DATAMEET_SHA256}")
    feats = json.loads(src.read_text())["features"]
    india = shapely.union_all([shape(f["geometry"]) for f in feats])
    india = _round(india.simplify(TOL, preserve_topology=True))
    n_india = _write(india, OUT / "india-boundary.geojson",
                     {"source": "DataMeet India community, Country/india-composite.geojson "
                                f"(commit {DATAMEET_COMMIT})"})

    for name, geom, size in [("land.geojson", land, n_land), ("coastline.geojson", coast, n_coast),
                             ("india-boundary.geojson", india, n_india)]:
        print(f"{name:24s} {geom.geom_type:13s} parts {len(getattr(geom, 'geoms', [geom])):4d}  "
              f"vertices {shapely.get_num_coordinates(geom):6d}  bounds {[round(b, 2) for b in geom.bounds]}  "
              f"valid {geom.is_valid}  {size / 1e3:.1f} kB")
    return land, india


# ---------------------------------------------------------------- M8 A: states + places

ADMIN2_FILES = {  # DataMeet States/Admin2 at the same pinned commit as the outline; SHA-256 of each file
    "shp": "b61ebc11a7487ce1c340d55fc9d0c1a2b63af1f73191fef691c11693c726130d",
    "shx": "dc428a44ed20384b02c3c5971f2b200b15d429923b6cc770cae940d0af21016a",
    "dbf": "4ec2f9b83263c85781bc9abf0d281d441b5e02377be124bda6b5d87bd9dc4ccd",
    "prj": "a02a27b1d1982c8516d83398e85a3c8b1aef1713c13ef4d84d7bde17430c07c4",
    "cpg": "3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824",
}
BORDER_BUFFER = 0.02    # deg (~2 km): state lines closer than this to the national outline are dropped

# Capital(s) of each of the 36 states/UTs in DataMeet Admin2 (names as in Natural Earth). Checked, not trusted:
# every name must exist in NE and fall inside that state's polygon.
CAPITALS = {
    "Andaman & Nicobar": ["Port Blair"], "Andhra Pradesh": ["Amaravati"], "Arunachal Pradesh": ["Itanagar"],
    "Assam": ["Dispur"], "Bihar": ["Patna"], "Chandigarh": ["Chandigarh"], "Chhattisgarh": ["Raipur"],
    "Dadra and Nagar Haveli and Daman and Diu": ["Daman"], "Delhi": ["New Delhi"], "Goa": ["Panaji"],
    "Gujarat": ["Gandhinagar"], "Haryana": ["Chandigarh"], "Himachal Pradesh": ["Simla"],
    "Jammu & Kashmir": ["Srinagar", "Jammu"], "Jharkhand": ["Ranchi"], "Karnataka": ["Bengaluru"],
    "Kerala": ["Thiruvananthapuram"], "Ladakh": ["Leh"], "Lakshadweep": ["Kavaratti"], "Madhya Pradesh": ["Bhopal"],
    "Maharashtra": ["Mumbai"], "Manipur": ["Imphal"], "Meghalaya": ["Shillong"], "Mizoram": ["Aizawl"],
    "Nagaland": ["Kohima"], "Odisha": ["Bhubaneswar"], "Puducherry": ["Puducherry"], "Punjab": ["Chandigarh"],
    "Rajasthan": ["Jaipur"], "Sikkim": ["Gangtok"], "Tamil Nadu": ["Chennai"], "Telangana": ["Hyderabad"],
    "Tripura": ["Agartala"], "Uttar Pradesh": ["Lucknow"], "Uttarakhand": ["Dehra Dun"], "West Bengal": ["Kolkata"],
}
# Natural Earth still marks Yangon as Myanmar's capital; it has been Naypyidaw (also in NE) since 2006
NOT_CAPITAL = {"Yangon"}
# Display names: current official spellings where Natural Earth uses older ones (old name kept as a search alias)
RENAME = {"Simla": "Shimla", "Dehra Dun": "Dehradun", "Vishakhapatnam": "Visakhapatnam"}
ALIASES = {"Mumbai": ["Bombay"], "Chennai": ["Madras"], "Kolkata": ["Calcutta"], "Bengaluru": ["Bangalore"],
           "Thiruvananthapuram": ["Trivandrum"], "Puducherry": ["Pondicherry"], "Kochi": ["Cochin"],
           "Varanasi": ["Benares", "Banaras"], "Prayagraj": ["Allahabad"], "Allahabad": ["Prayagraj"],
           "Gurgaon": ["Gurugram"], "Dispur": ["Guwahati"], "Odisha": [], "Vadodara": ["Baroda"], "Pune": ["Poona"]}
# Hand-placed labels (lat, lon), each checked below: countries well inside their own territory per Natural Earth and
# outside India's official boundary; seas over water.
COUNTRIES = {"Pakistan": (28.3, 66.8), "China": (31.5, 89.0), "Nepal": (28.3, 83.9), "Bhutan": (27.45, 90.4),
             "Bangladesh": (24.2, 90.2), "Myanmar": (21.5, 95.6), "Sri Lanka": (7.9, 80.7),
             "Afghanistan": (33.5, 66.0), "Thailand": (15.5, 101.5), "Maldives": (3.2, 73.0)}
SEAS = {"Bay of Bengal": (15.5, 88.0), "Arabian Sea": (15.5, 67.5), "Andaman Sea": (10.5, 97.0),
        "Laccadive Sea": (9.0, 74.5), "Indian Ocean": (1.5, 80.0)}


def _admin2():
    """DataMeet States/Admin2 polygons {state name: geometry}, files pinned by SHA-256."""
    import shapefile                                      # pyshp (ships with cartopy)
    d = SRC / "States"
    d.mkdir(parents=True, exist_ok=True)
    for ext, sha in ADMIN2_FILES.items():
        f = d / f"Admin2.{ext}"
        if not f.exists():
            urllib.request.urlretrieve(
                f"https://raw.githubusercontent.com/datameet/maps/{DATAMEET_COMMIT}/States/Admin2.{ext}", f)
        if hashlib.sha256(f.read_bytes()).hexdigest() != sha:
            raise ValueError(f"Admin2.{ext} checksum mismatch")
    r = shapefile.Reader(str(d / "Admin2"))
    return {rec["ST_NM"]: shape(sh.__geo_interface__).buffer(0) for rec, sh in zip(r.records(), r.shapes())}


def _india_outline():
    feats = json.loads((SRC / "india-composite.geojson").read_text())["features"]
    return shapely.union_all([shape(f["geometry"]) for f in feats]).buffer(0)


SHARED_TOL = 0.005      # deg (~500 m): a state's edge counts as shared if it lies this close to a neighbour


def build_states():
    """Internal state/UT boundaries only: edges that two states share. Outer edges (coast, national border) are never
    drawn, so no second, slightly different national border appears next to the official outline."""
    states = _admin2()
    names = list(states)
    shared = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = states[a], states[b]
            if not A.envelope.intersects(B.envelope.buffer(SHARED_TOL)):
                continue
            seg = A.boundary.intersection(B.buffer(SHARED_TOL))
            if not seg.is_empty and seg.length > 0:
                shared.append(seg)
    merged = shapely.line_merge(shapely.union_all(shared))
    merged = merged.simplify(TOL)
    parts = [g for g in getattr(merged, "geoms", [merged]) if g.geom_type == "LineString" and g.length > 0.02]
    internal = _round(shapely.MultiLineString(parts))
    size = _write(internal, OUT / "states.geojson",
                  {"source": f"DataMeet India community, States/Admin2 (commit {DATAMEET_COMMIT}), CC BY 4.0",
                   "note": "internal state/UT boundaries only (edges shared by two states/UTs)"})
    india = _india_outline()
    outside = internal.difference(india.buffer(0.01))
    print(f"states.geojson: {len(states)} states/UTs, {len(shared)} shared edges, {len(internal.geoms)} line parts, "
          f"{shapely.get_num_coordinates(internal)} vertices, {size / 1e3:.1f} kB; "
          f"length outside India's outline (+1 km): {outside.length:.3f} deg of {internal.length:.1f} deg")
    return states, internal


def build_places(states=None):
    import unicodedata
    from shapely.prepared import prep
    states = states or _admin2()
    india = _india_outline()
    # point-in-polygon on prepared, lightly simplified shapes (~200 m), computed once
    inside = {n: prep(g.simplify(0.002)) for n, g in states.items()}
    near = {n: prep(g.simplify(0.002).buffer(0.05)) for n, g in states.items()}
    view = box(LON_MIN - MARGIN, LAT_MIN - MARGIN, LON_MAX + MARGIN, LAT_MAX + MARGIN)
    ne = shpreader.Reader(shpreader.natural_earth(resolution="10m", category="cultural", name="populated_places"))
    recs = [r.attributes for r in ne.records()]
    inview = [a for a in recs if view.contains(shapely.Point(a["LONGITUDE"], a["LATITUDE"]))]
    # 1. capitals check
    byname = {}
    for a in inview:
        byname.setdefault(a["NAME"], []).append(a)
    capitals, missing = {}, []
    # Chandigarh is the capital of Punjab and Haryana but lies in Chandigarh UT, so "inside the state" cannot hold there
    in_other_ut = {("Chandigarh", "Punjab"), ("Chandigarh", "Haryana")}
    for st, names in CAPITALS.items():
        for nm in names:
            hits = [a for a in byname.get(nm, []) if near[st].contains(shapely.Point(a["LONGITUDE"], a["LATITUDE"]))]
            if hits or (nm, st) in in_other_ut:
                capitals.setdefault(nm, st)
            else:
                missing.append(f"{nm} ({st})")
    # 2. selection
    def keep(a):
        return (a["FEATURECLA"].startswith("Admin-0 capital") or a["NAME"] in capitals
                or a["POP_MAX"] >= 300_000 or a["SCALERANK"] <= 6)
    out, seen = [], set()
    for a in sorted(inview, key=lambda a: -a["POP_MAX"]):
        if not keep(a) or (a["NAME"], round(a["LATITUDE"], 1)) in seen:
            continue
        seen.add((a["NAME"], round(a["LATITUDE"], 1)))
        pt = shapely.Point(a["LONGITUDE"], a["LATITUDE"])
        # area from OUR layers, so it never contradicts the drawn boundary: inside a state polygon (~5 km tolerance,
        # for island and coastal points) or inside the official outline -> "<state>, India"; else Natural Earth's country
        st = next((n for n, g in inside.items() if g.contains(pt)), None) or \
            next((n for n, g in near.items() if g.contains(pt)), None)
        if st is None and india.contains(pt):
            st = min(states, key=lambda n: states[n].distance(pt))
        area = f"{st}, India" if st else a["ADM0NAME"]
        kind = ("capital" if (a["FEATURECLA"] == "Admin-0 capital" and not st and a["NAME"] not in NOT_CAPITAL)
                or a["NAME"] == "New Delhi"
                else "state_capital" if st and capitals.get(a["NAME"]) and
                (capitals[a["NAME"]] == st or a["NAME"] == "Chandigarh") else "city")
        name = RENAME.get(a["NAME"], a["NAME"])
        alias = sorted({x for x in (a["NAMEALT"] or "").split("|") if x and x != name}
                       | set(ALIASES.get(name, [])) | ({a["NAME"]} if name != a["NAME"] else set()))
        prio = {"capital": 0, "state_capital": 1, "city": 2}[kind]
        out.append([name, round(a["LATITUDE"], 3), round(a["LONGITUDE"], 3), kind, prio,
                    round(float(a["MIN_ZOOM"]), 1), int(a["POP_MAX"]), area, alias])
    # 3. countries and seas, checked
    ne0 = shpreader.Reader(shpreader.natural_earth(resolution="10m", category="cultural", name="admin_0_countries"))
    countries = {r.attributes["NAME"]: r.geometry for r in ne0.records()}
    land = shapely.union_all(list(countries.values()))
    labels = []
    for nm, (la, lo) in COUNTRIES.items():
        pt = shapely.Point(lo, la)
        assert countries[nm].contains(pt) or nm == "Maldives", f"{nm} label not inside {nm}"
        assert not india.buffer(0.3).contains(pt), f"{nm} label inside/near India's official boundary"
        labels.append([nm, la, lo, "country", 3, 0, 0, "", []])
    for nm, (la, lo) in SEAS.items():
        assert not land.contains(shapely.Point(lo, la)), f"{nm} label on land"
        labels.append([nm, la, lo, "sea", 4, 0, 0, "", []])
    doc = {"fields": ["name", "lat", "lon", "kind", "priority", "min_zoom", "population", "area", "aliases"],
           "source": "Natural Earth 10m populated places (public domain), selected and corrected by make_geo.py; "
                     "area from DataMeet States/Admin2 + india-composite for places inside India's official "
                     "boundary; country and sea labels hand-placed",
           "places": out + labels}
    path = OUT / "places.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    import gzip
    from collections import Counter
    print(f"places.json: {len(out)} places + {len(labels)} country/sea labels; {path.stat().st_size / 1e3:.1f} kB "
          f"({len(gzip.compress(path.read_bytes())) / 1e3:.1f} kB gzip); kinds {dict(Counter(p[3] for p in out))}")
    print(f"capitals found for {len(CAPITALS)} states/UTs; missing: {missing or 'none'}")
    return out, labels, missing


if __name__ == "__main__":
    import sys
    parts = sys.argv[1:] or ["base"]
    if "base" in parts:
        main()
    st = build_states()[0] if "states" in parts else None
    if "places" in parts:
        build_places(st)
