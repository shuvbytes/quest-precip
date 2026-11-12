# CLAUDE.md — project memory

## Goal
QUEST Lab Full Stack AI pre-doc task (Shuvayan Dasgupta). Within 72 h of 12 Nov 2026 (target: done
night of 14 Nov IST), build and deploy a web app that fetches ECMWF Open Data precipitation forecasts,
processes them, and presents them through an innovative, honest UI. All work happens in Claude Code sessions.

## Working rules (from the user)
1. Plan first; ask the user about choices that are theirs.
2. Small steps, each ending in a check the user can see (printed values, plot, test, URL).
3. Never assume units or time zones: read them from the data and show them.
4. Commit after every working step, with a message explaining why.
5. Keep this file updated (goals, decisions, status, next steps).
User: comfortable with intermediate Python/numpy; new to web dev and deployment, so explain web decisions briefly.

## Decisions (12 Nov)
- Data: IFS HRES `tp` (stream oper, type fc), 0.25°, latest 00z/12z run, steps 0–144 (3-hourly).
  ENS probabilities `tpg*` (type ep) = **24 h windows** (0-24, 12-36, …), 0.25°.
- Region: India + seas, ~5–38°N, 65–100°E.
- Hosting: GitHub Pages (static, always on). Point forecasts are looked up **in the browser** from a
  precomputed grid file, so no server is needed. FastAPI on HF/Render is optional, only if time allows.
  Why: free HF Spaces sleep after 48 h, and the 2026 status of the free tier is unclear.
  (Updated later: FastAPI became a real milestone M7b; see below.)
- Pipeline: GitHub Actions cron twice a day → PNGs (reprojected to Web Mercator / EPSG:3857 so they line
  up in Leaflet) + manifest.json + point grid → published with `actions/upload-pages-artifact` +
  `actions/deploy-pages`. **No images or generated data in git, no gh-pages branch.** A failed run leaves the
  last good deploy live; the page shows "last updated" and the run time so staleness is visible.
- Point data (decided after M1): HRES 3-hourly as uint16 in 0.1 mm units; ENS probabilities as uint8 %;
  file lazy-loaded on first click. Size for the 133×141 grid: 18,753 × 48 × 2 B = 1.80 MB plus
  18,753 × 7 thresholds × 11 windows × 1 B = 1.44 MB ≈ 3.24 MB raw. The real compressed transfer size is reported in M4.
  (An earlier "1.5 MB" estimate was wrong: smaller box, no ENS.)
- 24 h mode: both layers use the ENS windows (00z run: 00–00 UTC = 05:30–05:30 IST; 12z: 17:30–17:30 IST).
  HRES 24 h total = TP(t+24) − TP(t). Labels state exact IST bounds, e.g. "Thu 13 Nov 05:30 IST → Fri 14 Nov
  05:30 IST", never a bare weekday. IMD rain day (08:30–08:30 IST) HRES view = stretch goal, labelled as a different window.
- FastAPI `/point` = milestone M7b (14 Nov afternoon). Try HF Spaces first (user's HF login was failing),
  Render as fallback. The browser lookup stays as the fallback if the API is asleep or down.
- Basemap: no political borders + India official boundary GeoJSON overlay (source cited).
- Times: UTC everywhere internally; IST only at display. Units: read from GRIB attrs, convert m → mm explicitly.
- Tooling: `gh` CLI installed and logged in (user confirmed) → used for repo creation / Pages in M7.
- Env: conda env `quest-precip` (Python 3.11, conda-forge eccodes/cfgrib). System Python 3.9 is not used.

## Milestones
- [x] M0 repo, env, this file (Python 3.11.18, eccodes 2.50.0, cfgrib 0.9.15.1, xarray 2026.9.0, ecmwf-opendata 0.3.35)
- [x] M1 download one HRES run; print units/stepType/base time/grid
- [ ] M2 de-accumulate to 3 h / 24 h mm; tests; one map. Also: prove the negative diffs come from GRIB packing
      (packing keys), set the lowest map bin above the quantisation noise, 24 h = TP(t+24) − TP(t) tested against
      summed 3 h amounts, locate the 505 mm max and compare with ECMWF's chart for this run.
- [ ] M3 ENS tpg* probabilities; P(≥10 mm) map
- [ ] M4 3857 PNGs + manifest + point grid; alignment check; real compressed transfer size
- [ ] M5 Leaflet front end locally
- [ ] M6 client-side point forecast panel (lazy-loaded)
- [ ] M7 GitHub Actions + Pages deploy via deploy-pages (public URL)
- [ ] M7b FastAPI /point on HF Spaces (Render fallback), 14 Nov afternoon
- [ ] M8 honesty/UX polish, "last updated", README
- [ ] Buffer (15 Nov AM): fixes, IMD-day stretch goal

## Data facts read from the GRIB (M1, run 2026-11-12 00z)
- `tp`: units `m`, `GRIB_stepType = accum` (accumulated since run start), GRIB edition 2, regular_ll 0.25°.
- Base time coordinate `time` = forecast_reference_time; cfgrib gives naive datetime64. GRIB2 reference
  times are UTC, so we attach UTC explicitly and convert to IST (UTC+05:30) only for display.
- Steps 0–144 h every 3 h (49 steps); `valid_time` = time + step.
- Global grid: lat 90 → -90 (descending), lon -180 → 179.75 (not 0–360).
- Region crop 5–38°N, 65–100°E → 133 × 141 points.
- Accumulated values sometimes **decrease** slightly between steps (min −0.000122 m = −0.12 mm), which is
  GRIB packing noise. M2 must clip negative interval totals to 0 and report how many were clipped.
- 6-day regional max 0.505 m (505 mm).

## Status
M0, M1 done (12 Nov). Run everything with `conda run -n quest-precip ...` or `conda activate quest-precip`.
Fetch: `python pipeline/fetch.py` (23.5 MB global GRIB in git-ignored `data/raw/`).
Inspect: `python pipeline/inspect_grib.py <file>`.

## Next steps
M2: de-accumulate to 3 h and 24 h totals in mm (×1000 from the `units` attribute, not hard-coded blindly),
clip packing negatives, pytest for the maths, one matplotlib map.
