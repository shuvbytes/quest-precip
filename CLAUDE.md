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
- Env: conda env `quest-precip` (Python 3.11, conda-forge eccodes/cfgrib). System Python 3.9 is not used.

## Milestones
- [x] M0 repo, env, this file (Python 3.11.18, eccodes 2.50.0, cfgrib 0.9.15.1, xarray 2026.9.0, ecmwf-opendata 0.3.35)
- [ ] M1 download one HRES run; print units/stepType/base time/grid
- [ ] M2 de-accumulate to 3 h / 24 h mm; tests; one map
- [ ] M3 ENS tpg* probabilities; P(≥10 mm) map
- [ ] M4 3857 PNGs + manifest + point grid; alignment check
- [ ] M5 Leaflet front end locally
- [ ] M6 client-side point forecast panel
- [ ] M7 GitHub Actions + Pages deploy (public URL)
- [ ] M8 honesty/UX polish, README
- [ ] Buffer (15 Nov AM): fixes, optional FastAPI

## Status
M0 done (12 Nov). Run everything with `conda run -n quest-precip ...` or `conda activate quest-precip`.

## Next steps
M1: download the latest HRES 00z/12z `tp` run for the region; print GRIB units, stepType, base time
(UTC), steps, grid shape and bbox before writing any processing code.
