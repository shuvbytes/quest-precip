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
- [x] M3 ENS tpg* probabilities; P(≥10 mm) map; Bay P(≥50/100) check
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
- Display floor (decided 12 Nov, replaces an earlier per-run floor): per interval, floor_i = 2 × q_i, where
  q_i = max(quantum at start, quantum at end) (`process.interval_floor`). Fixed legends:
  3 h 0.5, 1, 2, 5, 10, 20, 50, 100 mm; 24 h 1, 2.5, 5, 10, 20, 50, 100, 200 mm. If floor_i > the first edge, that frame
  starts at the next edge and is flagged (`process.lowest_visible`); the manifest must carry floor_i + the flag.
  This run: 3 h floors 0.061–0.488 mm (thin margin under 0.5), 24 h floors 0.122–0.488 mm; no frame raised.
  12.3 % of 3 h cells are > 0 but < 0.5 mm: the UI must say "amounts below 0.5 mm (3 h) / 1 mm (24 h) not
  shown", because ECMWF's own charts start at 0.1 mm.
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

## Decided after M2 follow-up (12 Nov)
- Point panel text (M6), exactly: "Model value at the nearest grid point (0.25°, ~25 km spacing). Rain can vary
  a lot within that distance." Plus "nearby: X–Y mm" = min–max over the 3×3 neighbouring points (fewer at edges).
- Validation record: `docs/validation/` (md + one side-by-side image; the only image deliberately in git).
- cartopy is dev-only: `environment.yml` = pipeline/CI, `environment-dev.yml` = + cartopy (local env built from it).

## M3 findings (run 2026-11-12 00z, `pipeline/ens.py`, `pipeline/m3_check.py`)
- **Run selection changed.** Since IFS 50r1 (May 2026) 06z/18z HRES runs are also under `stream=oper` and
  reach 144 h, so `latest()` returned 06z (our guard caught it). ENS `ep` exists only for 00z/12z (checked
  per hour). `fetch.latest_main_run` now picks the newest 00z/12z run where BOTH HRES (step 144) and ENS
  (last window) are published.
- ENS file: 84 messages = 7 thresholds × 12 windows (0–24 … 132–156). Units `%`, stepType accum,
  probabilityType 3 = "above lower limit"; thresholds from keys = 1, 5, 10, 20, 25, 50, 100 (mm; ECMWF names say
  "at least X mm"). Packing quantum: 0.031 % (tpg1–20), 0.5 % (tpg25–100).
- **Bug caught:** the first reader flipped latitude (eccodes `distinctLatitudes` order). Fixed by sorting
  descending and asserting against `latitudeOfFirstGridPointInDegrees`. `tests/test_ens.py` checks orientation
  against HRES: median P(≥1 mm) where HRES 0–24 h ≥ 20 mm = 100 % (flipped: 0 %).
- Probabilities are **not** multiples of 1/51 (likely interpolated from the native grid); the file does not
  state the ensemble size. UI shows "%" only, never "k of 51 members".
- 0–24 h agreement: HRES 1–10 mm → median P(≥10) 5 %; 10–20 mm → 68 %; 20–50 mm → 94 %; ≥ 50 mm → 100 %.
- **Bay check** at 15.00N 86.50E (HRES 505 mm cell), point (3×3 range):
  96–120 h: HRES 92 mm (68–111), P≥50 50 % (42–57), P≥100 21 % (11–28);
  108–132 h: HRES 369 mm (128–369), P≥50 56 % (50–62), P≥100 22 % (19–24);
  120–144 h: HRES 382 mm (111–382), P≥50 47 % (40–48), P≥100 20 % (19–27);
  132–156 h: P≥50 31 %, P≥100 12 % (beyond HRES range).
  So HRES's 370–380 mm/24 h is an extreme scenario; the ensemble gives ~1-in-5 chance of ≥ 100 mm there.
  The ENS P(≥100) peak in the Bay is 42 % at 13.00N 84.75E in 84–108 h (earlier and further SW). This is the
  core story the 24 h mode should tell.

## M3 follow-up: ENS/HRES window alignment (`pipeline/m3_window_check.py`)
- Concern: central Bay (12–18N, 85–91E) looked like 20–50 mm in HRES but ENS P(≥10) < 10–25 %.
- GRIB keys: ENS tpg10 message has dataDate 20261112, dataTime 0000, stepRange 0-24, validity 20261113 0000,
  stream enfo / type ep. HRES step 24 has the same date, time and validity (stream oper, type fc). Same run, same window.
- Correlation of ENS P(≥10) 0–24 h with HRES 24 h totals: 0–24 h Pearson 0.897 / Spearman 0.807 (best);
  12–36 h 0.814 / 0.751; it falls steadily for later windows. The reverse check (HRES 0–24 vs each ENS window) also
  peaks at 0–24. **Window labels are correct.**
- The band is actually mostly dry-ish in HRES: 437 of 625 cells < 5 mm, 124 at 5–10, 60 at 10–20, only 4 at 20–50
  (all at 90.5–91E, ENS P(≥10) 29–50 %). The ENS median P(≥10) by HRES bin: 5–10 mm 11 %, 10–20 mm 38 %.
- Root cause of the misreading: the check-map palette. **Correction (measured later):** the old YlGnBu steps
  were NOT too similar (adjacent OKLab dE 9–15). The real problem was lightness placement: the 5–10 mm bin was
  already a mid-blue (L 0.76), so light rain read as heavy.
- **Palette (`pipeline/palette.py`, used by M4):** one hue per layer, lightness monotone (dataviz skill).
  Rain (blue) lightness per bin 0.91 → 0.30, so bins below 10 mm stay pale. Adjacent dE 5.7 and 6.8 for the two
  palest pairs (an accepted trade-off; exact values are on click), 8.5–12.5 for the rest. Probability (magenta)
  uses even steps, adjacent dE 12–16. Backgrounds: land #fafafa, sea #ffffff. The first attempt was invisible on
  the old backgrounds (dE 2–3) and #f4f4f4 land also failed (6.8–7.3). `tests/test_palette.py` enforces:
  monotone L, adjacent dE thresholds, palest step ≥ 8 vs both backgrounds. The web basemap in M5 must meet the same.
- Like-for-like check (`m3_check.py`): HRES 10 mm contour drawn on the ENS P(≥10) panel; NE India figure compares
  HRES ≥ 1 mm with ENS P(≥1). NE 20–30N 85–100E, 0–24 h: HRES ≥ 1 mm cells → median P(≥1) 88 %; HRES < 1 mm →
  5.5 % (10–90 pct 0–39 %); match (HRES ≥ 1 vs P ≥ 50 %) 90.8 %. At 10 mm: 97.6 % match. The apparent NE mismatch
  came from comparing a ≥ 1 mm colouring with a ≥ 10 mm probability. The ENS also spreads low probabilities
  (10–50 %) over a wider area than HRES rain (e.g. Bangladesh), as expected from ensemble spread.
- Prob legend fixed: bins end at 100 (not 100.01); values ≥ last edge take the top colour.

## Status (end of 12 Nov session; user on a break, M4 NOT started)
**M0–M3 done; 18 tests passing.** All open questions from the M2/M3 reviews are resolved:
- ECMWF chart comparison: no bugs; 0.25° values are point samples (`docs/validation/`).
- ENS window alignment verified (same run/window in GRIB keys; best correlation at 0–24 h).
- NE India mismatch resolved: it came from comparing ≥ 1 mm colouring with P(≥ 10 mm). Like-for-like agreement
  is 90.8 % (1 mm) and 97.6 % (10 mm).
- **Palette decided (user, 12 Nov): keep as is.** Pale light rain matters more than equal steps, so the two
  palest rain pairs (dE 5.7 / 6.8) are accepted. Do not change without asking.

Commits so far:
| Commit | What |
|---|---|
| `285fa45` | M0 skeleton, env, CLAUDE.md |
| `2b4327b` | M1 fetch + GRIB metadata inspection |
| `017f713` | Post-M1 decisions (FastAPI M7b, artifact Pages, sizes, IST windows) |
| `0ed7133` | M2 de-accumulation, packing evidence, tests |
| `f1bbebf` | M2 follow-up: differences vs ECMWF chart |
| `550e37e` | cartopy dev-only env split |
| `311ad66` | Per-interval display floor + fixed 3 h / 24 h legends |
| `c065350` | Validation record (`docs/validation/`) |
| `ca4803e` | M3 ENS probabilities (+ run-selection fix, latitude-flip fix) |
| `509f9e1` | M3 window-alignment check, probability legend fix |
| `603b812` | Measured palette; NE like-for-like checks |

How to run: `conda activate quest-precip` (built from `environment-dev.yml`).
Fetch: `python pipeline/fetch.py` (HRES 23.5 MB + ENS 28.9 MB into git-ignored `data/raw/`).
Checks (dev): `pipeline/inspect_grib.py`, `packing.py`, `m2_check.py`, `diagnose_vs_chart.py`,
`validation_figure.py`, `m3_check.py`, `m3_window_check.py` → `outputs/checks/` (git-ignored). Tests: `python -m pytest`.

## Next steps
**M4 (next, when the user resumes; wait for the go-ahead):** render EPSG:3857 PNGs (3 h + 24 h HRES, ENS
probabilities) using `palette.py` and the fixed legends, with per-frame floor flags; manifest.json (run time UTC,
IST labels, windows, units, bins, floor_i, source, licence); point grid (uint16 0.1 mm + uint8 %); coastline
alignment check; report the real compressed transfer size.

## Remaining schedule (agreed 12 Nov)
| Day (IST) | Work |
|---|---|
| 12 Nov evening (after break) | M4 |
| 13 Nov | M5 Leaflet front end (locally), M6 point panel (wording + "nearby: X–Y mm"), M7 Pages deploy via deploy-pages (public URL) |
| 14 Nov | M7b FastAPI /point (HF Spaces, Render fallback); automation (GitHub Actions cron 2×/day, 00z/12z run selection); M8 polish ("last updated", README). Target: app finished by the night of 14 Nov |
| 15 Nov | Buffer: fixes, IMD-day (08:30–08:30 IST) stretch goal. Hard stop at start + 72 h |
