# Sources of the basemap layers in `web/geo/`

All three files are built by `pipeline/make_geo.py`: clipped to the region + 6° (−1–44°N, 59–106°E), simplified with a 0.01° (~1 km)
tolerance, coordinates rounded to 0.001°. The rain data cells are 0.25° (~28 km), so this simplification is far
below what the map can resolve.

## `land.geojson` (land fill) and `coastline.geojson` (coast line)
- Source: **Natural Earth**, 10 m physical vectors, `ne_10m_land` and `ne_10m_coastline` (via cartopy's
  Natural Earth downloader). The coast is drawn from the coastline lines, not the land outline, so the clip
  edges never appear as lines.
- Licence: Natural Earth data is in the **public domain** ("All versions of Natural Earth raster + vector map
  data found on this website are in the public domain", naturalearthdata.com/about/terms-of-use).
- Contains no political boundaries.

## `india-boundary.geojson` — India's boundary, drawn as a line
- Source: **DataMeet India community**, `Country/india-composite.geojson` in https://github.com/datameet/maps,
  pinned to commit `b3fbbde595` (2022-05-11); SHA-256 of the downloaded file
  `5e44c39b18aa8fe57267d8018fa4ad4a10eaa3aa4cb7cb7382a1813ef8eb8c53` (checked by `make_geo.py`).
- What it is, quoted from `Country/README.md`: "Single feature shapefile for the land area of India including
  disputed territories in accorance with the Official boundary of India as per the Survey of India".
  Compiled from LSIB (U.S. Department of State HIU), the Alhasan Systems Pakistan admin boundaries dataset, and
  Natural Earth "Admin 0 Breakaway, Disputed Areas" (as listed in that README).

### Licence (verified 13 Nov 2026 from the repo at commit `b3fbbde595`)
Three statements exist in the repo; quoted exactly:
1. `Country/README.md`, section `india-composite.geojson` → "### License" → **"CC-0"**.
2. Repository `README.md`, "Data License": **"Unless explicitly stated, all datasets in this repository is shared
   under CC BY 4.0 license. Please mention and link to relevant dataset in the attribution, eg. *India boundaries
   by DataMeet India community (CC BY 4.0)*"**.
3. Repository `LICENSE` file: **MIT License**, "Copyright (c) 2020 DataMeet India community", granting rights to
   "this software and associated documentation files (the "Software")". GitHub's API also reports the repo licence
   as MIT.

Which applies: statement 2 says datasets are CC BY 4.0 *unless explicitly stated*, and statement 1 explicitly states
CC-0 for this file, so **CC-0 applies to `india-composite.geojson`**. The MIT licence covers the repository's
software, not its datasets. To be safe under any reading, we still give the attribution that statement 2 asks for
(it satisfies CC BY 4.0, and CC-0 permits it):

> India boundary: *India boundaries* (https://github.com/datameet/maps/blob/master/Country/india-composite.geojson)
> by DataMeet India community (http://datameet.org/), CC-0 per the dataset's README.

The app footer carries this attribution.

## Not used
No tile server or third-party basemap is used, so no other borders are drawn and no other attribution is needed.

## `states.geojson` — internal state/UT boundaries, drawn as thin grey lines (M8, 14 Nov 2026)
- Source: **DataMeet India community**, `States/Admin2.shp` in https://github.com/datameet/maps, pinned to the same
  commit `b3fbbde595` as the India outline; SHA-256 of each downloaded file checked by `make_geo.py`
  (`.shp` `b61ebc11a748…`, `.dbf` `4ec2f9b83263…`, full digests in `make_geo.ADMIN2_FILES`).
- What it is: 36 features, field `ST_NM` = the current 28 states and 8 union territories (Ladakh separate; "Dadra and
  Nagar Haveli and Daman and Diu" merged). File history: "Updated the States & UT to status as per Jan 2020" (2020-05-06),
  "Updated Ladhak & J&K boundry as per latest SOI Map" (2021-08-24), "Merged the two Ladhak features" (2021-10-25).
- **Licence: CC BY 4.0.** The `States/` folder has no README or licence of its own, so the repository's default applies,
  quoted from its `README.md` ("Data License"): **"Unless explicitly stated, all datasets in this repository is shared under
  CC BY 4.0 license. Please mention and link to relevant dataset in the attribution"**. Attribution given in the page
  footer: *State boundaries* (https://github.com/datameet/maps/tree/master/States) by DataMeet India community (CC BY 4.0).
  Modification: only edges shared by two states/UTs are kept (outer edges, i.e. coast and national border, are dropped so
  the official India outline above stays the only national border), simplified 0.01°, rounded to 0.001°.
- Not used: `Survey-of-India-Index-Maps/StateBoundary` in the same repo: pre-2019 units (no Ladakh; Dadra and Nagar Haveli
  and Daman and Diu separate) and its README states no licence.

## `places.json` — city, country and sea labels; place search; "Near <place>"
- Cities: **Natural Earth** 10 m `populated_places` (public domain, as above). Kept inside the map view (−1–44°N,
  59–106°E): national capitals, the capitals of all 36 Indian states/UTs (checked against an explicit list in
  `make_geo.CAPITALS`: each must exist in Natural Earth and lie in its state's polygon; Chandigarh, capital of Punjab and
  Haryana, lies in Chandigarh UT), places with population ≥ 300,000 and places with Natural Earth scale rank ≤ 6.
  Label density uses Natural Earth's `MIN_ZOOM`.
- Corrections to Natural Earth (listed, not silent): display names "Shimla" (NE "Simla"), "Dehradun" (NE "Dehra Dun") and "Visakhapatnam" (NE "Vishakhapatnam"),
  old names kept as search aliases; Yangon not marked as Myanmar's capital (Naypyidaw is). Natural Earth's own state
  field is not used (it puts Gandhinagar in "Dadra and Nagar Haveli"): for every place inside India's official boundary
  the state comes from DataMeet `States/Admin2` (point in polygon), so place names never contradict the boundary drawn.
  Elsewhere the country is Natural Earth's.
- Country and sea labels: hand-placed points (`make_geo.COUNTRIES`, `make_geo.SEAS`); each country label is checked to lie
  inside that country in Natural Earth `admin_0_countries` and away from India's official boundary; sea labels over water.
