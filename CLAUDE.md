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
- [x] M2 de-accumulate to 3 h / 24 h mm; tests; one map. Also: prove the negative diffs come from GRIB packing
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

## M2 findings (run 2026-11-12 00z)
- Packing (`pipeline/packing.py`): every message is `grid_ccsds`, 12 bits, D = 0, R = 0, with E going from
  −15 to −12 as totals grow, so quantum q = 2^E m = 0.0305 → 0.2441 mm. Every decoded value lies exactly on
  its grid (checked). Every negative change is within −(q1+q2)/2.
  Negatives occur in only 4 intervals: 3–6, 48–51 and 69–72 h are where E changes (re-rounding onto a coarser
  grid: fully explained). **39–42 h has the same E on both sides**; rounding on one fixed grid is monotone,
  so there the values ECMWF packed already decreased by < 1 quantum (0.061 mm). The cause is probably an
  earlier processing step, but it is not provable from this file. Either way the error is bounded by q.
- Lowest map bin = smallest of (0.5, 1, 2) mm that is ≥ 2 × the run's largest quantum → 0.5 mm this run
  (computed per run, `process.lowest_bin`). 12.3 % of 3 h cells are > 0 but < 0.5 mm: the UI must say
  "amounts below 0.5 mm not shown", because ECMWF's own charts start at 0.1 mm.
- Clipping: 4,284 of 900,144 3 h values (0.48 %) clipped; most negative −0.122 mm.
- 24 h totals = TP(t+24) − TP(t) on ENS windows; tests prove they equal the unclipped sum of 3 h amounts
  exactly, and the clipped sum exceeds them by at most the clipped noise.
- Max 0–144 h total 505.4 mm at 15.00°N 86.50°E (central Bay of Bengal, open sea), mostly 123–132 h
  (~290 mm in 9 h): a late-run Bay low/cyclone signal. **Matches ECMWF's own chart** (OpenCharts
  `medium-rain-acc`, projection `opencharts_southern_asia`, base 2026-11-12 00 UTC, +144 h): same N–S
  300–1000 mm streak at ~85–87°E, 9–15°N, the same small separate speck to the south, and the same 100–300 mm area
  in the southern Bay. OpenCharts API: `https://charts.ecmwf.int/opencharts-api/v1/products/medium-rain-acc/?base_time=...&valid_time=...&projection=opencharts_southern_asia`.

## M2 follow-up: differences vs ECMWF chart (`pipeline/diagnose_vs_chart.py`, uses 0.1° step-144 file)
- Central India "beige" on the chart is the chart's **land background** RGB (255,226,171), not the 0.1–1 mm
  shade (239,219,183). Our 0–144 h totals there are exactly 0 at 22N 78E and 18N 76E in both 0.25° and 0.1°
  open data. The 16–24N, 74–82E box has 1054 of 1080 cells = 0. No disagreement.
  Note: at step 144 both open-data fields have quantum 0.244 mm, so true totals < 0.122 mm are stored as 0.
- South Tamil Nadu coast: 0.25° totals 3.4–13.9 mm; 0.1° cells inside the same 0.25° boxes range 1.9–52.5 mm.
  Rain varies on scales below 25 km, and our cells jump across the 5 and 10 mm bin edges, so the map looks
  patchy where the chart's smoothed contours look like a band. Not a bug.
- Himalaya: 7 of 1325 cells (26–32N, 80–93E) ≥ 50 mm; the highest is 165 mm at 28.50N 84.75E, where the 8 neighbours' median is 4 mm.
  The 0.1° field has 197 mm at the same point and a 91 mm mean over the box. These are real orographic peaks
  in the model; the chart's contouring does not resolve single-cell peaks. Not a bug (the 0–144 total is
  TP(144) alone, no differencing).
- **Key fact: a 0.25° open-data value is a point sample, not a box average.** At the 4,757 points shared with
  the 0.1° grid, |0.25 − 0.1| has median 0.000 mm (99th pct 0.73). |0.25 − mean of 0.1 cells in its box|
  has median 0.244 mm, 99th pct 10.7 mm, max 97 mm. So UI text must NOT say "average over a 25 km box".

## Status
M0, M1, M2 done (12 Nov). Run everything with `conda run -n quest-precip ...` or `conda activate quest-precip`.
Fetch: `python pipeline/fetch.py` (23.5 MB global GRIB in git-ignored `data/raw/`).
Inspect: `python pipeline/inspect_grib.py <file>`; packing proof: `python pipeline/packing.py <file>`;
M2 check + maps: `python pipeline/m2_check.py <file>` → `outputs/checks/` (git-ignored). Tests: `python -m pytest`.

## Next steps
M3: fetch ENS `type=ep` `tpg*` for the same run; print the params, windows, units (expect %) as read from the
GRIB; P(≥10 mm / 24 h) map for 0–24 h shown beside the HRES 24 h total for the same window.
