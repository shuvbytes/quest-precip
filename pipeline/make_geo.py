"""DEV-ONLY, run once: build the static basemap layers in web/geo/ (committed; not per-run data).

- land.geojson: Natural Earth 10 m land (public domain), clipped to the region + 1 deg margin, simplified.
  Drawn as the land fill; its outline is the coastline. No political borders.
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
MARGIN = 1.0
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

    for name, geom, size in [("land.geojson", land, n_land), ("india-boundary.geojson", india, n_india)]:
        print(f"{name:24s} {geom.geom_type:13s} parts {len(getattr(geom, 'geoms', [geom])):4d}  "
              f"vertices {shapely.get_num_coordinates(geom):6d}  bounds {[round(b, 2) for b in geom.bounds]}  "
              f"valid {geom.is_valid}  {size / 1e3:.1f} kB")
    return land, india


if __name__ == "__main__":
    main()
