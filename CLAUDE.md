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
- Pipeline: GitHub Actions cron twice a day → PNGs (reprojected to Web Mercator / EPSG:3857 so they line
  up in Leaflet) + manifest.json + point grid → `gh-pages` branch.
- Basemap: no political borders + India official boundary GeoJSON overlay (source cited).
- Times: UTC everywhere internally; IST only at display. Units: read from GRIB attrs, convert m → mm explicitly.
- Tooling: `gh` CLI installed and logged in (user confirmed) → used for repo creation / Pages in M7.
- Env: conda env `quest-precip` (Python 3.11, conda-forge eccodes/cfgrib). System Python 3.9 is not used.

## Milestones
- [x] M0 repo, env, this file (Python 3.11.18, eccodes 2.50.0, cfgrib 0.9.15.1, xarray 2026.9.0, ecmwf-opendata 0.3.35)
- [x] M1 download one HRES run; print units/stepType/base time/grid
- [ ] M2 de-accumulate to 3 h / 24 h mm; tests; one map
- [ ] M3 ENS tpg* probabilities; P(≥10 mm) map
- [ ] M4 3857 PNGs + manifest + point grid; alignment check
- [ ] M5 Leaflet front end locally
- [ ] M6 client-side point forecast panel
- [ ] M7 GitHub Actions + Pages deploy (public URL)
- [ ] M8 honesty/UX polish, README
- [ ] Buffer (15 Nov AM): fixes, optional FastAPI

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
