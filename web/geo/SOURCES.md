# Sources of the basemap layers in `web/geo/`

Both files are built by `pipeline/make_geo.py`: clipped to 4–39°N, 64–101°E, simplified with a 0.01° (~1 km)
tolerance, coordinates rounded to 0.001°. The rain data cells are 0.25° (~28 km), so this simplification is far
below what the map can resolve.

## `land.geojson` — land fill and coastline
- Source: **Natural Earth**, 10 m physical vectors, `ne_10m_land` (via cartopy's Natural Earth downloader).
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
