# CLAUDE.md — project memory

**App name (user, 14 Nov): "Baरिश" (Barish), subtitle "a second opinion on rain".** Page title "Baरिश (Barish) — a second
opinion on rain"; screen readers get "Barish" (Devanagari part aria-hidden + sr-only Latin). Repo and URLs unchanged
(shuvbytes/quest-precip, quest-precip-api). Devanagari via system fonts only (Kohinoor/Devanagari Sangam MN on Apple,
Noto Sans Devanagari on Android, Nirmala UI/Mangal on Windows).

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
- [x] M4 3857 PNGs + manifest + point grid; alignment check (real transfer size: measure in M7 after deploy).
      Disagreement layer: approved and built (min cluster 3 on map).
- [x] M5 Leaflet front end locally (13 Nov)
- [x] M6 client-side point forecast panel (lazy-loaded) — 13 Nov
- [x] M7 GitHub Actions + Pages deploy via deploy-pages — live at https://shuvbytes.github.io/quest-precip/ (13 Nov)
- [x] M7b FastAPI /point — live on Render free tier at https://quest-precip-api.onrender.com (13 Nov night; HF dropped)
- [ ] M8 honesty/UX polish, "last updated", README
- [ ] IMD-day (08:30–08:30 IST) view: 14 Nov night, only if M8 is done
- [ ] Buffer (15 Nov): fixes only, no new features

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

## Status (14 Nov, ~13:30 IST): M0–M7b + M8 A/B done (pushed; goes live with the next scheduled Pages deploy); live run 2026-11-13 12z; site https://shuvbytes.github.io/quest-precip/, API https://quest-precip-api.onrender.com
**M0–M7b done; 77 tests passing; repo public; site deployed by GitHub Actions (M7), point API on Render (M7b section).**
**Laptop check of the live site (user, Safari, 13 Nov night): all OK**: header, Bay link (label, zoom note, hatching),
slider, point click with progress bar, shared link, console. Wording change confirmed live (manifest `heavy_from_mm` 50,
both sentences; app.js picks `wetter_heavy` only for X ≥ 50). Phone check (Android Chrome): portrait OK; landscape poor → M8 item D. Earlier (evening): M6 closed by the user after confirming
both keyboard fixes in Safari (the ring lands on the crosshair). Earlier (afternoon): M0–M5 done. The map page runs locally and was checked by the user in Safari (all five check
views correct; console errors traced to a Safari extension and gone). Backed up to GitHub:
**https://github.com/shuvbytes/quest-precip** (public since 13 Nov, branch `main`).
Local server for checks: `python3 -m http.server 8000 --bind 127.0.0.1 --directory site_build` → http://127.0.0.1:8000/.

Earlier review questions, all resolved:
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
| `fe777ff`, `04ea885` | End-of-day status; schedule change (IMD-day → 14 Nov night, 15 Nov buffer only) |
| `b8d1090` | M4 step 1: Mercator frame PNGs |
| `5c5952c` | M4 step 2: alignment check |
| `07326f4` | M4 step 3: manifest.json |
| `c26b1bf` | M4 step 4: points.bin + round-trip test |
| `04e1392`, `b571f0c` | Disagreement rule + map layer |
| `e764ff8` | Whole centred "drier" dots; check figure |
| `8c98bd6`, `ac7a884` | Disagreement review numbers; zoom-6 decision |
| `1b85ed0` | Map min cluster 3; point panel keeps all flags; zoom note (pushed to GitHub) |
| `a9202a9`, `7d67c79` | Robustness check on 12z run; validation note: Bay system 00z vs 12z in valid time |
| `682f4cd` … `fdadb00` | M5 steps 1–5: basemap layers, page skeleton, controls, header/legend/footer, phone layout |
| `9b98148` | URL-hash updates throttled (Safari replaceState limit); banner only for load failures |
| `3ab0485` | Leaflet vendored (no CDN) after a Safari "can't find variable: L" failure |
| `0a60714` | Forecast-area edge: outside veil, subtler line, following labels |
| `fff79a2` | Cream land #fdf8ee; "Script error." banner fix; cache-busted asset links |
| `3482679`, `b9a11e1` | Vendored leaflet.js.map; ignored-error warning shows file/line |
| `42a3b24` + this commit | M5 closed; status updated and pushed to GitHub (13 Nov) |
| `4bcbbd9` … `7edceb3` | M6 steps 1–6: exact 24 h array, selection + lazy points.bin, summary/table, SVG chart, keyboard/phone, exact-match check |
| `911cd0d`, `c202a2e`, `191cbe7` | Crosshair keyboard-only; Enter selects exactly under it; crosshair reaches every grid point |
| `58aecca` | M6 closed; M8 point-card idea recorded; pushed |
| `9564dbd` | Wetter sentence: "Rain of X mm or more…" below 50 mm, "Heavy rain…" from 50 mm |
| `04cf9d9` … `cf35771` | M7: .gitignore audit, `fetch.py --print-latest`, workflow, progress-bar fix, skip-step fix, M7 notes |
| `7444592` … `1afe683` | M7b: pointcore (shared logic), FastAPI app + tests, page asks API first with fallback + source line |
| `5e96c69`, `8a7db0a` | HF dropped (Docker SDK now paid); Render free web service, native Python, gzip |
| `35e488a` | API follows a new site build at once (60 s checks, deploy loop; first via public `/health?check=1`) |
| `5ffd6ca` | M7b live checks + cold start recorded |
| `a96b624` | Reload trigger protected: token-only `POST /refresh` replaces public `/health?check=1` |
| `487d7ee` | Floor test checks the rule (13 Nov 12z raised floors); chart note for mixed floors |
| `eaf432c` | CLAUDE.md: refresh token, first 12z deploy |
| `869460c` | Floor mutation check; new PNG-floor test closes a gap no test covered |
| `7602d8c` | Validation: 260 mm / 3 h Bay peak is in ECMWF's own charts |
| `0b0f17c` | Hourly :23 cron slots for 6 h after each run (GitHub delayed slots ~4 h) |
| `68f98b8` | CLAUDE.md: pre-M8 checks |
| `c78af4c` … `44f3ebf` | M8 A (state lines, places, labels, search, Near) + M8 B (grid-step keyboard) |
| this commit | CLAUDE.md: M8 A + B, README example |

How to run: `conda activate quest-precip` (built from `environment-dev.yml`).
Fetch: `python pipeline/fetch.py` (HRES 23.5 MB + ENS 28.9 MB into git-ignored `data/raw/`).
Checks (dev): `pipeline/inspect_grib.py`, `packing.py`, `m2_check.py`, `diagnose_vs_chart.py`,
`validation_figure.py`, `m3_check.py`, `m3_window_check.py` → `outputs/checks/` (git-ignored). Tests: `python -m pytest`.

## M4 results (12 Nov evening, run 2026-11-12 00z) — `pipeline/render.py`, `pipeline/build.py`
- Build: `python pipeline/build.py <hres> <ens> [out]` → `site_build/data/` (git-ignored): `frames/*.png`,
  `manifest.json`, `points.bin`.
- Frames: 48 HRES 3 h + 11 HRES 24 h + 77 ENS (7 thresholds × 11 windows to 144 h) = 136 indexed PNGs,
  508 kB in total (1.6–6 kB each), 564 × 583 px, bounds [[4.875, 64.875], [38.125, 100.125]] (cell edges).
  Rows are resampled to Web Mercator (nearest grid point, no smoothing); index 0 is transparent below each frame's
  floor. No floor raised this run (3 h 0.061–0.488, 24 h 0.122–0.488, ENS 0.062–1.0).
- Alignment (`m4_alignment.py`, dev): at Chennai, Kanyakumari, Dondra Head, Mumbai, Chittagong and Karachi the image
  shows the cell containing the point (0 km). A naive lat/lon image would be 28–111 km off. ECMWF lsm via the
  same renderer lines up with 10 m coastlines.
- manifest.json (53 kB): run UTC + IST, each frame's UTC window + exact IST label, units (+ GRIB source units),
  bins, colours, floor / lowest_drawn / floor_raised, grid + image bounds, point-value wording, points layout,
  source, ECMWF CC BY 4.0 attribution with a modification notice. Tests check IST = UTC + 05:30 for every label.
- points.bin: HRES 3 h uint16 (0.1 mm) 1,800,288 B + ENS uint8 (%) 1,443,981 B = 3,244,269 B raw; gzip -9
  520,561 B (gzip -6 533,957). Decode test: within 0.1 mm / 1 %. The browser's 24 h point value = sum of 8 decoded
  3 h values: within ±0.35 mm of the map's TP(t+24) − TP(t) (never ≥ 0.5 mm), so no separate 24 h array.
- **Resolved in M7:** GitHub Pages does gzip points.bin (619,848 B on the wire), so no .gz file is shipped.

## Disagreement layer (approved and built 12 Nov evening) — `pipeline/disagree.py`
- Rule (user-approved): X = selected ENS threshold. **Wetter:** HRES ≥ X at the point and ENS P(≥X) < 25 % at the
  point and all 8 neighbours. **Drier:** ENS P(≥X) ≥ 75 % at the point and HRES < X at the point and all 8
  neighbours. At edges only the neighbours that exist are used. 25/75 chosen over 33/66; neighbourhood kept.
- Map: 24 h mode only, over the ENS layer. **On by default, with a toggle.** Hatch PNGs: wetter = diagonal lines,
  drier = dots, black with a white edge. One PNG per threshold/window with flags (74 of 77 this run).
- Manifest `products.disagreement`: rule, legend text, point-panel text templates ({hres}, {pct}, {x}), and per
  frame: counts + flat cell indices (row*nlon+col) so the point panel can show the right sentence. The manifest
  is now 119 kB because of these lists.
- This run: 2,489 wetter / 50 drier cells over 77 frames. Drier appears only at 1 and 5 mm. The Bay cell
  (15.0N 86.5E) is flagged wetter at 100 mm, 108–132 h (test).
- Visual note: the drier dots are small at full-region zoom; check readability in M5 when Leaflet scales the image.

### Disagreement review (12 Nov, late) — `m4_disagree_figure.py`, `m4_disagree_stats.py` (dev)
- Drier marks looked like glitches: the dot pattern (6 px period) was larger than a cell (4 px). Fixed: hatch
  frames are drawn at 12 px/cell (same bounds) with one centred dot per drier cell (`e764ff8`). Readable at web
  zooms 6 (11.4 px/cell) and 7 (22.8); at zoom 5 (5.7 px/cell) the dots shrink to faint rings → M5: start the
  map at zoom 6, or handle zoom 5 separately.
- Straight vertical edge in the old crop = the region's west edge (grid starts at 65.00E, image edge 64.875E).
  The ENS field continues outside (P(≥1) at 64.75E is similar to 65.00E). Not a bug.
- Wetter ≫ drier (2,489 vs 50) is a property of the data, not the rule: HRES's wet area matches the ENS expected
  wet area (ratio 1.02 at 1 mm, 1.07 at 10 mm, 0.88 at 50 mm); even the point-only rule is lopsided (1,245 vs 121
  at 10 mm); and the neighbourhood removes similar shares on both sides (96 % vs 94 % kept at 10 mm). Cause:
  ENS reaches ≥ 75 % only in broad organised rain, where HRES is almost always wet too, while HRES's sharp local
  maxima often fall where the ensemble spreads its probability below 25 %.
- Minimum cluster size (8-connected): wetter cells 2,489 → 1,861 (min 2) → 1,551 (min 3); clusters
  967 → 339 → 184; drier 50 → 44 → 32. The Bay point sits in a 26-cell cluster (it survives).
  **Decided (user, 12 Nov): map hatches only clusters of ≥ 3 cells (`disagree.MAP_MIN_CLUSTER`); the point panel
  keeps every flagged cell**, so clicking an isolated flagged cell still shows the disagreement sentence. Built in
  `1b85ed0`: 62 hatch PNGs; manifest `n_*_on_map` vs `n_*` + full `cells_*` lists (manifest 123.6 kB).
- **Decided (user, 12 Nov): small screens.** Fit the region on load; if that needs a zoom below 6, show
  "Zoom in to see disagreement marks" while zoom < 6 (manifest `min_zoom_for_marks`, `zoom_note`).
- User review (12 Nov, late): wetter hatching sits only on the 10–25 % shade, never on the ≥ 25 % core, which is
  consistent with the rule. **Decided: the web map starts at zoom 6** (dots faint at zoom 5). Optional polish: some
  dots look slightly clipped at zoom 7 (likely non-integer scaling), so check in M5.
- Generated outputs in git: checked 12 Nov. No frame/hatch PNG, points.bin, manifest or GRIB has ever been
  committed (`git log --all`). The only image in history is the deliberate validation figure.
  `.gitignore` covers `site_build/`, `data/raw/`, `outputs/`.

## Robustness check on a second run (13 Nov, 05:54 UTC)
- `fetch.py` chose **2026-11-12 12z** (= Thu 12 Nov 17:30 IST). The 13 Nov 00z run was not yet published (not even
  HRES step 90 at 05:54 UTC), so this is correct. The whole pipeline ran unchanged: 48 + 11 + 77 frames, 66 hatch PNGs,
  manifest 122.0 kB, points.bin 3,244,269 B. **No raised floors** (3 h 0.061–0.488, 24 h 0.244–0.488, ENS 0.062–1.0).
  Disagreement: 2,348 wetter / 59 drier flagged; on map (≥ 3 clusters) 1,517 / 38. **36/36 tests pass**; the
  real-data tests use the newest file (12z), and the run-specific checks stay pinned to the 00z files kept in `data/raw/`.
- 24 h windows are 17:30 → 17:30 IST for a 12z run (labels correct). 24 h max 475.1 mm at 11.50N 85.00E, 60–84 h
  (neighbours 176–345 mm; 3 h sum = 24 h exactly; ENS P(≥100) 30 %). The Bay system comes earlier and further SW
  than in the 00z run. Plausible, not a bug.
- `site_build/data/` now holds the 12z build.

## M5 — map page (13 Nov) — `web/`, `pipeline/make_geo.py`, `pipeline/m5_screens.py`
How to run: `python pipeline/build.py data/raw/hres_tp_<run>.grib2 data/raw/ens_tpg_<run>.grib2` (copies `web/` into
`site_build/` next to `data/`), then `cd site_build && python -m http.server 8000` and open http://localhost:8000/.
Must be served over http (browsers block fetch() from file://). Screenshots (dev): `python pipeline/m5_screens.py
"name=WxH#hash[@scrollY]"`; it emulates true phone widths with an iframe wrapper served only by the dev server.
Web decisions:
- Plain HTML/CSS/JS, no framework/build step. **Leaflet 1.9.4 is vendored in `web/vendor/leaflet-1.9.4/`** (same files as
  cdnjs 1.9.4 + BSD-2 LICENSE; SRI hashes kept and checked by `tests/test_build.py`). Changed 13 Nov from cdnjs: in
  Safari a new tab failed with "can't find variable: L" because Leaflet did not load from the CDN, while every
  same-origin file was fine (reproduced by blocking cdnjs). The site now has no external dependency at all.
- URL hash writes are debounced (400 ms, only if changed, try/catch): Safari throws "SecurityError" after 100
  replaceState calls / 10 s, and Chrome silently drops them (the URL had shown the wrong window). The error banner is
  only for load failures; later errors are logged. Check: `python pipeline/m5_screens.py stress`.
- **No tile server.** Own basemap: Natural Earth 10 m land (fill #fafafa = palette.LAND) + coastline lines, white sea
  (palette.OCEAN), so the contrast test covers the basemap; no third-party borders. India boundary line on top from
  DataMeet `india-composite.geojson` (pinned commit `b3fbbde595`, SHA-256 checked). **Licence verified:** folder README
  says "CC-0" for this file (explicit statement beats the repo-wide "CC BY 4.0 unless explicitly stated"; MIT LICENSE
  covers software). Attribution given anyway; quotes in `web/geo/SOURCES.md`.
- Panes: land → data image → hatch → coast + India lines. Dashed rectangle = area with forecast data.
- `image-rendering: pixelated`: cells stay sharp squares (no invented detail).
- All labels, bins, colours, units, rule text, attribution come from manifest.json. IST shown from the manifest; header
  times computed as UTC + 05:30 with UTC formatting (never the viewer's time zone).
- View state in the URL hash (`#mode=24h&fill=chance&x=100&t=60&hatch=1[&z=7&c=lat,lon]`): shareable, used for checks.
  A hash view is applied without animation (bug found: zoom read mid-animation showed bold marks at zoom 7).
User decisions at M5 approval (13 Nov):
- **Initial view = fit the region on every screen** (≈ zoom 4.75 desktop 1440×900, 3.75–4 phones; minZoom 3). This
  supersedes the 12 Nov "start at zoom 6". The amber note "Zoom in to see disagreement marks" is shown on load (24 h
  mode, hatch on, zoom < 6), and **bold hatch** frames (`disagree-bold_*`, 4 px/cell, thick stripes/big dots) are
  used below zoom 6; fine ones (12 px/cell) from zoom 6.
- **Staleness badge** "Older than usual: newer runs may exist" when the run is **> 30 h** old (checked: none at 29 h,
  badge at 31 h).
- **24 h mode fill toggle** is a prominent segmented control ("Rain total / one detailed run (HRES)" vs "Chance of ≥ X mm /
  ensemble (ENS)"), and the map shows "Showing: …" naming the fill. The threshold X drives the chance layer and the marks.
Changes after the user's review (13 Nov):
- **Land colour #fdf8ee (cream), sea white, coastline #6b717b 1.1 px** (user-approved). Land-sea dE 2.4 (was 1.5); palest
  rain 9.1/10.1 and palest chance 8.1/9.4 vs land/sea, so `tests/test_palette.py` passes. A light blue-grey sea was rejected:
  the palest rain is pale blue, 5.0 on #e8eef3 (fails). A stronger tint would need a darker palest rain (palette decision).
- **Forecast-area edge** (user-approved): grey veil outside the area (palette.OUTSIDE, 12 %), lighter dashed edge, and a label
  "Forecast area edge · no data beyond" that follows each side edge on screen.
- **"Could not load the forecast: Script error."** (seen in Safari): "Script error." is a browser's opaque report of an
  error inside a script from another origin (an extension, or a stale cached page that still used cdnjs). Reproduced with a
  cross-origin script throwing during load. Fix: the banner appears only for errors from this site's own scripts before
  ready, or when main() fails; others are logged ("[other origin]" in data-lasterror); any banner is removed on ready.
  Verified: cross-origin error → no banner, map ready; missing manifest → banner "data/manifest.json: HTTP 404".
- **Confirmed by the user in Safari (13 Nov), after emptying caches:** cream land, white sea, no banner; the Bay URL
  `#mode=24h&fill=chance&x=100&t=60` opens with "Sun 15 Nov 05:30 IST → Mon 16 Nov 05:30 IST". Private-window check
  (does the "Ignored an error…" warning disappear, i.e. was it an extension?) **not yet reported**, so the original
  source of "Script error." (extension vs stale cache) is unconfirmed. The fix covers both.
- **User visual check (13 Nov), local server `python3 -m http.server 8000 --bind 127.0.0.1 --directory site_build`:**
  all five check views (default; Bay ≥100 mm t=60; rain t=0 with fill toggle; 3 h t=33 with fast slider; zoom 7 drier dots
  x=1 t=108) look correct and consistent with the expected labels. The browser's JavaScript console was **not** checked by
  the user; headless Chrome shows status ready and no errors for the same five views. (`--directory` keeps the server
  working when a rebuild deletes and recreates site_build/; a server started inside the old folder had stopped working.)
- **Safari console, link 1 (user, 13 Nov):** (a) Warning "Ignored an error from a script that is not part of this page:
  Script error. (app.js, line 30)": line 30 is our console.warn, i.e. the fix working. (b) "SyntaxError: Unexpected token
  '{'. Expected ')' to end a compound expression": NOT our code. app.js and leaflet.js both parse cleanly in JavaScriptCore
  (macOS `jsc`, Safari's engine; jsc does flag deliberately broken files with this message shape), and a parse error in
  either would kill the map. So it comes from a script injected into the page, almost certainly a Safari extension; the
  same error reached our handler as the opaque "Script error.". Confirm with a Private window / extensions off.
  (c) 404 leaflet.js.map: the console requests the source map named at the end of leaflet.js. Fixed by vendoring
  `leaflet.js.map` (cdnjs 1.9.4, 225 kB); test added.
- **Resolved (user, 13 Nov):** after the diagnostic warning (`b9a11e1`) and the Private-window / extensions-off check,
  the user reports the Safari console errors are gone. Which step cleared them was not stated; most likely a Safari
  extension. M5 closed with no known console errors from the app.
- **Cache busting**: `build.copy_web` rewrites index.html links to `app.js?v=<sha256[:10]>` (also style.css, vendored
  Leaflet), so changed files always get new URLs; tested in `test_built_index_links_are_cache_busted`.
Checks done: status ready, no console errors, slider labels equal the manifest (4 views), no horizontal scroll at 360/390/
1440 px, legends from manifest, footer attribution. Known cosmetic item: at zoom 7–8 the fine dots look slightly uneven
(non-integer scaling of 12 px/cell).

## M6 — point panel (13 Nov) — `web/app.js` (point section), `pipeline/m6_check.py`
User decisions at plan approval: **exact 24 h array** in points.bin (`hres_24h`, so panel = map = sentence);
**keyboard = crosshair + Enter** on the focused map; **small values shown as "< 0.5 mm" / "< 1 mm" / "< 2 %", no bar**.
- points.bin now: hres_3h u16 0.1 mm [48], hres_24h u16 0.1 mm [11], ens_prob u8 % [7×11]; 3,656,835 B raw,
  600,646 B gzip -9. `read_points` returns a dict by name. Test: hres_24h equals the map's values to 0.1 mm exactly.
- Click/tap → nearest grid point (ring marker); outside the area → "No forecast here" with the area's limits.
  points.bin is fetched on the first selection with a progress bar and Retry; DataView little-endian reads.
- Panel: grid point + clicked location, agreed wording (manifest), selected-window summary + "nearby: X–Y mm" (3×3)
  + ENS chance; disagreement sentence for the current X/window incl. isolated cells (note "not marked on the map");
  3-hourly **plain SVG** bar chart (IST midnights, selected window band, y axis ≥ 5 mm so trace rain looks small,
  hover/tap readout, values table); 24 h table (HRES total + ENS chance per threshold, palette shading, ▨/• flags,
  current window outlined and scrolled into view as whole columns).
- URL `p=lat,lon` (shared links reopen the point); Esc / × close. Keyboard: crosshair on map focus, Enter/Space
  selects, arrows pan (global ←/→ time stepping disabled while the map has focus). Phone: panel directly below the
  map, scrolled into view after a tap; no horizontal scroll at 390 px.
- **Correctness (`python pipeline/m6_check.py <hres>`): 697/697 fields match exactly** (Chennai 13.0827N 80.2707E →
  13.00N 80.25E, Bay 15.00N 86.50E, dry 22.00N 78.00E, a hatched Bay cell 9.50N 85.00E, an isolated flag 38.00N 78.75E):
  48 three-hourly values, 11 daily totals, 77 ENS cells, summary lines and both disagreement sentences. Raw GRIB vs
  stored: ≤ 0.05 mm (3 h).
- Dev tooling: `m5_screens.py` modes `keys` (keyboard path), `stress` (URL writes), env `SLOW_POINTS`/`REAL_TIME`
  (capture the loading state).
- **Crosshair fixes (13 Nov, user reports):** (1) shown only for keyboard use (last input = key, not pointer).
  (2) Enter selected ~24–49 px BELOW the crosshair on desktop: Leaflet measured the map box before the header/footer
  text arrived; the box then shrank by 66–99 px but Leaflet kept the old size, so its centre (used by Enter) was below the
  crosshair (drawn at the true centre). Fix: ResizeObserver → `map.invalidateSize`; Enter converts the crosshair's own
  screen position to a location (`containerPointToLatLng`), after `map.stop()` so no pan animation continues; desktop page
  capped at the window height (side panel scrolls; map no longer runs below the window). Check:
  `python pipeline/m5_screens.py aim` (opens a point, pans 226 px, Enter, 4 window sizes × zooms 5–7): old code 33–49 px
  off (FAIL), fixed ≤ 0.7 px (PASS). Note: headless Chrome does not run Leaflet's own arrow-key pan animations, so the
  check moves the map by the same pixels directly; arrow-key panning itself was confirmed by the user in a real browser.
  `window.__rainOutlook = {map}` is exposed only for these dev checks.
- **Keyboard reach (13 Nov, user report):** the crosshair stayed at the map centre, so where the map hit its pan limit
  keyboard users could not reach anything within half a screen of the edges (e.g. stuck at ~11.5N). Now the page handles
  the arrows itself (Leaflet's arrow handling bypassed): each press pans as far as allowed, and the remainder moves the
  crosshair; moving back first re-centres the crosshair. Panning also stops where the forecast edge would pass the
  crosshair (on a phone at zoom 7 the 5-deg pan margin had let the data leave the screen; crosshair ended at 101.25E).
  The crosshair is clamped to the forecast area. Keys: arrow = 80 px, Shift+arrow = 240 px, **Alt/Option+arrow = next
  grid point** (80 px can skip 0.25-deg cells), Enter selects, +/- zoom, Esc closes. Checks:
  `m5_screens.py edges` — all 4 edges + 4 corners at the fitted zoom and zoom 7, 1440x900 and 390x844: 32/32 reached,
  each selection = the grid point nearest the crosshair, ring within half a cell. `m5_screens.py targets` — Kanyakumari,
  Sri Lanka S tip, southern Bay, Jaffna, Gilgit, Port Blair, Karachi reached by keyboard only: 28/28 exact grid points.
- Table key line under the 24 h table was cut off at the left (a <caption> inside the sideways-scrolling box): now a
  visually hidden caption for screen readers + a visible line below the box.
- **Wetter sentence wording (decided by the user, 13 Nov):** for X < 50 mm it ends "Rain of X mm or more is possible here, but
  not likely."; "Heavy rain is possible, not likely." is used only when X >= 50 mm (`disagree.HEAVY_FROM_MM`,
  `point_text_key`; manifest `point_text.wetter_heavy` + `heavy_from_mm`). The old ending misled at low thresholds
  (1.5 mm at X = 1 mm). Drier sentence unchanged. Test `test_wetter_sentence_says_heavy_only_from_50_mm`; m6_check
  697/697 (isolated flag at X = 1 shows the new ending, Bay cell at X = 100 the heavy one).
- **Keyboard edges confirmed by the user in Safari (13 Nov):** the crosshair reaches the bottom dashed edge (~5°N,
  Sri Lanka) and the ring lands on the crosshair.

## M8 backlog (user, 13 Nov night) — recorded, not built; order: A + B first (14 Nov), card/README after M7b
**A. Place names (first priority: the user could not find Chennai on the map)**
1. City labels: state capitals, major metros, neighbouring capitals; more appear as you zoom in; white halo so they stay
   readable over rain colours. Local city list in the repo (source + licence cited), no tile server.
2. Neighbouring country names as labels (no extra political borders drawn).
3. Indian state boundaries as thin grey lines; source and licence verified and cited (like DataMeet in `web/geo/SOURCES.md`);
   must stay consistent with the official India boundary already drawn.
4. Place search box using the same local city list (no external API), fully keyboard-usable (combobox: type, arrows, Enter
   selects the city's nearest grid point and opens the panel).
5. Point panel: "Near <city> (N km)" (nearest city from the same list, great-circle distance).

**B. Keyboard navigation (each arrow press jumps too far when zoomed out)** — replaces the current 80 px / Shift 240 px /
Alt = one grid point scheme (`191cbe7`)
1. Arrow = crosshair moves one grid point (0.25°); Shift+arrow = 10 grid points. Map pans to keep the crosshair visible.
2. Live readout next to the crosshair: lat/lon + nearest city (also covers the "no orientation over sea" note).
3. +/− zoom keeps the crosshair on the same location.
4. Tests: every grid point reachable (edges + corners, fitted zoom and zoom 7, desktop + phone, as `m5_screens.py edges` /
   `targets`), Enter selects the grid point under the crosshair.

**D. Short screens / landscape phones** (user's Android Chrome test, 13 Nov night: portrait OK; landscape poor: map
under half the height while the attribution footer took almost as much; "Showing", zoom note, zoom buttons and edge labels
crowd the small map, and the left edge label overlaps "Showing"; point panel clipped mid-line; mode/slider controls not
visible; header scrolled away; region does not fit). Build after A and B:
1. Layout for short heights (e.g. `max-height: 500px` / landscape): map uses the full height, the panel beside it scrolls
   on its own, and the controls are reachable without scrolling the page.
2. Footer collapses on small screens into a short attribution line + "About & sources" link/drawer (ECMWF CC BY 4.0
   attribution must stay visible).
3. Smaller, non-overlapping overlays on short screens; the zoom note must not cover the map.
4. Test at 390×844 portrait and 844×390 landscape with screenshots (`m5_screens.py`), plus no page scroll sideways,
   region fits, panel and controls reachable.

**C. Polish**
1. Hatch stripes look jagged/staircased at max zoom (raster PNG stretched, `pixelated`): consider vector hatching, e.g. an
   SVG pattern built in the browser from the manifest's flagged-cell lists (map clusters ≥ 3 only), crisp at any zoom.
2. Point card next to the selected point (user, 13 Nov): grid point + window, main number, chance chip, disagreement
   badge, 6-day sparkline, "Full details" button opening the existing side panel; updates with the slider; Esc/× closes;
   bottom sheet on phones; keyboard-accessible. **Reuse the panel's data code** (selection, points.bin decode,
   formatting, flag lookup) rather than duplicating it.
3. README.

## M7 — GitHub Actions + Pages (13 Nov) — `.github/workflows/deploy.yml`
- **Live URL: https://shuvbytes.github.io/quest-precip/** (repo made public 13 Nov after an audit: 48 tracked files, no
  data/GRIB/points.bin/manifest/site_build/.claude now or in history, no token-like strings; the commit email stays public,
  user's choice). `.gitignore` now ignores all of `.claude/`. Pages source = "GitHub Actions" (no gh-pages branch).
- **Schedule (UTC), changed 14 Nov:** hourly at :23 for 6 h after each run: 08:23–13:23 and 20:23–01:23 (was 08:23/20:23 +
  backups 10:23/22:23). Why the first slot: measured Last-Modified on
  data.ecmwf.int (13 Nov 00z, 12 Nov 12z): HRES to 144 h 07:34 / 19:34, ENS ep 08:01 / 20:01 UTC; ~20 min margin; minute
  :23 avoids top-of-hour congestion where GitHub delays/drops scheduled runs. Scheduled runs compare
  `fetch.py --print-latest` with the live manifest `run.utc` and skip if equal (no redeploy of the same forecast).
  **First scheduled runs (13→14 Nov night), both ~4 h late:** 43537387045 (20:23 slot) started 00:55 UTC, 43546799504
  (22:23 slot) started 02:31 UTC; both: build success, "Live site already shows run 2026-11-13T12:00Z; nothing to deploy",
  deploy skipped (12z had been deployed by hand at 20:36 UTC). None dropped. Because a ~4 h delay on two slots could hold
  a forecast back for half a day, the slots became hourly for 6 h (`0b0f17c`); extra slots skip in ~20 s.
  Live on 14 Nov 06:15 UTC: site and API both run 2026-11-13 12z, build 20:37Z. 14 Nov 00z scheduled deploy: not yet at 06:22 UTC (first slot 08:23 UTC); to be confirmed.
- Job `build`: checkout → micromamba with the light `environment.yml` (cached) → newer-run check → fetch (HRES 21.8 MB,
  ENS 28.8 MB) → `pytest` (41 passed, 1 skipped: the test pinned to 12 Nov 00z files) → build → upload-pages-artifact.
  Job `deploy`: deploy-pages. Manual: `gh workflow run deploy.yml` (inputs `skip_if_unchanged`, `force_fail` for tests).
- **Verified on GitHub:** deploy (runs 43442536316, 43443561328); forced failure → build failed, deploy skipped, live
  `generated_utc` unchanged (43443936651); skip path → build success, deploy skipped (43444392922). Bug found: an explicit
  `exit 0` in the `bash -el` login shell runs ~/.bash_logout, which returns 1 on the runner → the step failed; fixed.
- **Transfer sizes (curl, live):** Pages gzips everything incl. `application/octet-stream`: points.bin 3,656,835 B →
  **619,848 B** on the wire; manifest.json 16,070 B; app.js 16,445 B; leaflet.js 43,194 B; land.geojson 32,673 B. So no
  pre-compressed .gz/DecompressionStream needed.
- **Bug found by the gzip:** the progress bar used Content-Length (compressed size) as the total while the stream yields
  decoded bytes → bar hit 100 % after 17 % of the data. Now total = manifest `points.bytes`, label shows % only. Seen on
  the live site in headless Chrome mid-download: "… 53 %".
- Live panel check (headless, Python decoding of the live points.bin): Chennai, Bay (t=60 and t=96, X = 100) 417/417
  fields exact; the dry central-India capture always snapshotted mid-download (test timing, not an app error).

## M7b — point API on Render (13–14 Nov) — `api/`
- **Live: https://quest-precip-api.onrender.com** (`/point?lat=&lon=[&x=][&t=]`, `/health`, `/docs`, `/` → `/docs`; `POST /refresh` token-only, not in /docs).
  Render free web service, native Python runtime (no Docker), region Singapore, created by the user in the form:
  root `api`, build `pip install -r requirements.txt`, start `uvicorn app:app --host 0.0.0.0 --port $PORT`, health check
  `/health`, env `PYTHON_VERSION=3.11.18` (= tested env; Render's default is 3.14), Auto-Deploy on commit, build filter `api/**`.
  No secrets anywhere (Render's GitHub app has access to this repo only).
- **Why not Hugging Face:** HF now lists the Docker SDK as paid (user, 13 Nov). The HF workflow + Dockerfile were removed before
  any push (`5e96c69`), so no failing job ever ran.
- **Render free tier (checked 13 Nov):** 512 MB RAM, 0.1 CPU; sleeps after 15 min without requests, ~1 min to wake;
  750 instance hours/month/workspace; Hobby plan 500 build minutes and **5 GB outbound/month** → responses gzipped
  (/point 33.8 kB → 3.3 kB, ~1.5 M answers per 5 GB); ephemeral disk (fine: data is reloaded from Pages at start).
- **Design:** `api/pointcore.py` (numpy only) = the panel's rules (nearest grid point, floor texts, 3×3 nearby, flags with the
  on-map cluster check, threshold wording); `pipeline/m6_check.py` uses it, so page == pointcore == API. `api/app.py` loads
  manifest.json + points.bin from the live Pages site, checks every 60 s (conditional GET, normally 304) and swaps when
  `generated_utc` changes; a failed refresh keeps the old data. 422 with a plain message for bad input (incl. NaN, unknown
  x/t), 404 "No forecast here: … outside the forecast area, 5–38°N, 65–100°E." CORS only `https://shuvbytes.github.io`
  (`DEV_ORIGIN_REGEX` env for local checks only).
- **Page:** asks the API first (3 s timeout, `manifest.api`), accepts only the same build + grid point, else uses
  points.bin; the panel shows "Values from: forecast API (Render) · answered in N ms" or "in-browser lookup (points.bin) ·
  <reason>". Pings `/health` on load to start waking a sleeping service. `?api=off` forces the local path.
- **Sync bug found live and fixed (`35e488a`):** after a Pages redeploy the site had build 19:45Z, the API 14:32Z (the deploy
  nudge came < 5 min after the API's last check) → the page correctly fell back. Now the API checks every 60 s, and the
  deploy job asks it to check at once, repeating until the API reports the deployed build.
- **Reload trigger protected (user request, `a96b624`):** the first version used a public `GET /health?check=1` (anyone could
  make the API re-read the fixed site URL, ≤ every 15 s: low risk, but unauthenticated work on demand). Now `/health` is
  read-only and the trigger is **`POST /refresh` with `Authorization: Bearer <token>`**: compared in constant time with Render
  env `REFRESH_TOKEN` (≥ 32 chars, else disabled → 503), wrong/missing → 401 + `WWW-Authenticate: Bearer`, ≤ every 15 s,
  hidden from /docs, GET → 405. Caller: deploy.yml step with GitHub secret `API_REFRESH_TOKEN` (masked `***`); without the
  secret the step is skipped and the 60 s self-check applies. **Token created by the user in their own terminal**
  (`openssl rand -hex 32 | tee >(pbcopy) | gh secret set API_REFRESH_TOKEN …`, then pasted into Render's Environment,
  clipboard cleared): never shown in this session. 7 tests. Checked live 13 Nov: no/wrong token → 401; deploy run
  43503111192: "try 1: API has build 2026-11-13T20:37Z, site has 2026-11-13T20:37Z"; run log has no token-like string
  (the only 64-hex strings are cache keys and the artifact digest in the build job).
- **First 12z deploy (13 Nov 20:37 UTC) and a blocked deploy before it:** run 43501967135 failed (live site unchanged, as
  designed) on `test_real_run_floors_below_legend`: in the 13 Nov 12z run ECMWF packs the accumulation from +105 h with
  E = −11 (quantum 0.488 mm; totals beyond ~1 m in the Bay system, 3 h max 260 mm at 14.5N 84.75E), so 13 of 48 3 h frames
  have floor 0.977 mm > 0.5 mm. The 12 Nov rule handles it (frame starts at 1 mm, `floor_raised`, legend note, panel
  "< 1 mm"); the test wrongly asserted it never happens → replaced by `test_real_run_floor_rule` (the rule, for every
  downloaded run). Also fixed: the chart's "No 3-hour window reaches X mm" named only the first frame's floor; with mixed
  floors it names both. Live after the fix: 695/695 via the API on the 12z build.
- **Checks (13 Nov, live):** curl: 3 places, 404/422 messages, gzip, CORS (site origin gets the header; other origins none;
  foreign preflight 400), `/docs` loads. API vs live points.bin: **561/561** values + texts (Chennai, Bay, dry). Live page in
  real-clock headless Chrome (DevTools protocol; simulated-clock headless proved unreliable for timeouts and downloads):
  **695/695 via the API, 695/695 with `?api=off`** (5 views). Local real-clock fallback tests: API down → "could not be
  reached"; 6 s slow → "did not answer within 3 s" (switches at 3 s); other build → "different forecast build (…)"; all with
  the same values. 67 tests (incl. 15 API tests) run in CI.
- **Cold start (measured 13 Nov 20:09 UTC, after 17 min without requests; one sample):** `curl /health` → HTTP 200 after
  **32.5 s** (first byte; the app's own log shows data loaded 23 s into the wake). Meanwhile the live page (Bay, X = 100,
  t = 60) showed "Asking the forecast API…" and at 3 s fell back: "in-browser lookup (points.bin) · API did not answer
  within 3 s", value 28.3 mm. Reloaded once awake: "forecast API (Render) · answered in 216 ms", same 28.3 mm.
  **Warm /point latency** (10 requests from India, gzip): min 0.16 s, median 0.18 s, max 0.33 s. So a sleeping API costs
  the visitor nothing but the 3 s wait on the first click (then points.bin, ~0.6 MB); the page's load-time `/health`
  ping usually wakes it before later clicks. Render's docs say ~1 min to wake; we saw ~32 s.

## Pre-M8 checks (14 Nov, user questions)
- **Scheduled runs:** see the M7 section (both fired ~4 h late, both skipped correctly; cron slots now hourly).
- **Floor test is corrected, not loosened** (`pipeline/mutation_floor_check.py`, in memory, fresh process per mutant):
  correct code PASS; "coarse frame left at 0.5 mm" CAUGHT (test_real_run_floor_rule + test_floors_and_files); "raised one
  edge too far" CAUGHT (test_real_run_floor_rule); "manifest right, PNG drawn from the first edge" was caught by **no**
  existing test (nothing looked at the picture) → new `test_png_never_colours_below_lowest_drawn` (every frame's PNG codes
  vs its lowest_drawn; 13 raised frames in 13 Nov 12z) catches it, plus a synthetic `render_png` test so the check is never
  vacuous on runs without raised floors.
- **260 mm / 3 h Bay peak** (13 Nov 12z, 14.50N 84.75E, 120–123 h): neighbours 15.6–99.6 mm; one intense step in a cyclonic
  system; ECMWF OpenCharts for the same run show > 64 mm/h at +123 h at ~14.7N 84.4E (eyeballed, ~40 km) and the same three
  300–1000 mm patches at +144 h as our ≥ 300 mm cells; ENS P(≥ 100 mm) 4 %. Real but extreme single-run scenario.
  Record: `docs/validation/2026-11-13_12z_bay_peak.md`.

## M8 A + B — place names and grid-step keyboard (14 Nov) — `pipeline/make_geo.py`, `web/app.js`, `pipeline/m8_checks.py`
- **State lines** `web/geo/states.geojson`: DataMeet `States/Admin2` at the pinned commit `b3fbbde595` (SHA-256 per file;
  36 features = 28 states + 8 UTs incl. Ladakh, DNH&DD merged). **CC BY 4.0** (no folder licence → the repo default, quoted
  in SOURCES.md); credited in the footer. Only edges shared by two states/UTs (~500 m tolerance) are kept, so no second
  national border appears (0.02° of 276° lies outside the official outline + 1 km). Rejected: SoI StateBoundary (pre-2019, no licence).
  Drawn #7d838c 0.9 px under the India outline (0.7 px #9aa0a8 was invisible at the fitted zoom).
- **Places** `web/geo/places.json` (24 kB, 8 kB gzip): 350 Natural Earth places + 10 countries + 5 seas (user: sea names yes).
  All 36 state/UT capitals checked against their polygons (Chandigarh: in Chandigarh UT, documented). State/country of each
  place from OUR layers (DataMeet states / official outline), never NE's ADM1 (NE puts Gandhinagar in DNH). Listed NE
  corrections: Shimla, Dehradun, Visakhapatnam spellings (old names = aliases); Yangon not a capital; Hyderabad (Pakistan)
  is a city. Country labels checked inside their NE country and away from India's official boundary.
- **Labels:** pane "places" (non-clickable); NE MIN_ZOOM − 0.5 decides when a city is a candidate (capitals always), greedy
  overlap removal by priority, whole labels only, cities only inside the forecast area, white halo. Capitals ◉ (a plain ring
  read as "O"). Fitted desktop: 31 capitals + 15 cities + 5 countries + 4 seas; Chennai labelled on desktop and phone.
- **Search:** WAI-ARIA combobox at the top of the side panel (above the point panel; below it the list fell off-screen).
  Names, word starts, aliases (Madras, Bombay…), accent/case-insensitive; in-area places only. `m8_checks.py search`: chen,
  madras → Chennai 13.00N 80.25E; bomb → Mumbai; kolk; thiruvanan; no-match message; Esc → all PASS (real key events).
- **Near** (user: ≤ 25 km "Near Chennai (11 km)", else "457 km SE of Visakhapatnam"): nearest listed city from the grid point,
  8-point direction from the place; `pointcore.near` = JS `nearText`; panel line `data-field="near"`; API `near` object
  (reads `geo/places.json` from the site; None until Pages has it). m6_check 700/700 incl. near; tests for all 8 directions.
- **Keyboard (B):** crosshair = grid point (row, col). Arrow ±1, Shift ±10, map pans only to keep it in view; +/−
  `setZoomAround` the cross; Enter selects exactly that point; readout "11.00°N 80.75°E · 144 km SE of Puducherry" beside
  the cross + aria-live (300 ms). Handler in capture phase with stopImmediatePropagation (Leaflet's own arrow/zoom handling
  could otherwise also act in a real browser) + `keyboardPanDelta: 0`. `m8_checks.py keys`: snake walk over **all 18,753
  grid points** at fitted zoom and zoom 7, desktop + phone: 0 failures (expected grid point each step, on screen, Enter exact
  at every 500th); real key events: +1 col without a Leaflet pan, Shift +10, +/− keep the cross ±1 px, Enter, readout: PASS.
  (Position error 0 px is a self-consistency number; the independent checks are grid point, on-screen, Enter.)
- Dev tooling: `pipeline/cdp.py` (real-clock DevTools driver; `websocket-client` added to environment-dev.yml only);
  `m5_screens.py` aim/edges/targets removed (old screen-offset model).

## M8 A + B — user confirmation and fixes (14 Nov)
- **Safari (user, 14 Nov, localhost, run 14 Nov 00z): city search works; keyboard jumps fixed; mouse/keyboard crosshair fixed.**
- Bug found by the user: after keyboard use, a click elsewhere left the keyboard cursor at the old point, so the next arrow
  "jumped" far (the walk test only used a fresh page + keyboard). Fix `853495a`: one `app.cursor` shared by click/tap,
  `p=` link, search and Enter. `m8_checks.py keys` now uses REAL DevTools key/mouse events: full walk 4 × 18,753 points,
  every press exactly one grid point; keyboard → real click → ArrowRight = exactly one point east (desktop + phone, z5/z7);
  same after p= link and search "madras". Safari note: Tab skips the map unless Option+Tab (or Safari setting).

## M8 D — short screens / landscape phones (14 Nov) — `web/style.css`, `pipeline/m8_checks.py layout`
- Short screens = `(max-height: 560px) and (min-aspect-ratio: 4/3)` (any width; 667×375 too). One-line header with short
  texts (run, issued, updated), map fills the rest, side panel min(300 px, 45vw) scrolls on its own: search, mode, **time**,
  colour/threshold/marks, then point panel, legend. Overlays smaller; edge labels hidden (veil + dashed edge stay); zoom note
  moved into the panel. Tapping a point scrolls the panel to it. Region refitted on map-box resize until the user moves it.
- Small screens (`max-width: 700px` or short): footer = one attribution line + "About & sources" bottom sheet (full credits,
  Close button); large screens unchanged.
- Results (real-clock Chrome, `python pipeline/m8_checks.py layout`): 844×390 header 26 / map 544×342 (was 197 tall) / footer
  22 px, no page scroll; 667×375 map 367×327; 932×430 map 632×382; portrait 390×844 map 390×523 as before; desktop unchanged.
  Checks: no page scroll, region fits, mode/search/time ≥ 30 px tall and in view, threshold reachable by panel scroll only,
  no overlay overlaps, credits sheet opens/closes. Bugs the check caught: mode buttons squeezed to 2 px (flex column),
  sheet text not wrapping, 667×375 getting the portrait layout. Not yet confirmed on a real phone.

## M8 C — point card + weather guide (14 Nov) — `web/app.js` renderCard/guideSVG, `pipeline/m8_checks.py card`
- M8 A+B+D **deployed by hand 14 Nov 13:02 UTC** (run 43597633946, user: scheduling already proven) with the 14 Nov 00z run;
  API took the build on try 1; live check: labels (Chennai), search, "Near Chennai (11 km)", values from the Render API,
  footer credits, 844×390 map 342 px with no page scroll. User confirmed landscape in Safari Responsive Design Mode.
- Card next to the selected point (phones: bottom sheet): nearest place, IST window, main number (3 h or 24 h as the mode),
  chance chip for X in the 24 h window (palette colour), disagreement badge, "Full details" (closes the card, scrolls to and
  focuses the panel title). **"Full details" only when needed (user, 14 Nov):** shown only if the panel's point heading is not
  on screen (phones: below the map or under the bottom sheet; short screens; side panel scrolled away); hidden on a desktop
  with the details in view, where it would only repeat them. Same data code as the panel. Esc closes the card first, then the panel; × closes the card only.
- **Weather guide** (original, simple SVG shapes; alt text per pose; toggle "Show the weather guide…" in the side panel,
  remembered in localStorage with try/catch). **Pose rules** (24 h window under the slider, first match wins):
  disagree = point flagged wetter/drier at the current X (same flag as the panel sentence); heavy = ENS P(≥ 50 mm) ≥ 50 %;
  light ("Some rain") = HRES 24 h ≥ 1 mm or ENS P(≥ 1 mm) ≥ 50 %; dry ("Mostly dry") otherwise. Note: "Some rain" can show
  next to "< 1 mm" when the ensemble, not the single run, gives ≥ 1 mm ≥ 50 %.
- Check `m8_checks.py card`: poses picked in Python for windows 0/48/96 h, 11/11 match; card texts = panel texts; badge iff
  panel sentence; card on screen, not covering the point; Esc order, ×, Full details, toggle persists, phone sheet: PASS.
  Sparkline skipped (time).

## Rename + interactive features plan (user decisions, 14 Nov)
- Order: 0 rename → 1 play → 2 "100 skies" (each checked locally, then deployed) → STOP features, write README (outline
  first) → 3 swipe compare → 5 story mode → 4 plan my day. (14 Nov: user asked for 3 before deploying 1+2.) A feature that is not solid is reverted to the last good commit.
- 1 Play: never autoplay; prefers-reduced-motion → 2 s steps instead of 1 s; any interaction pauses.
- 5 Story rules (approved with tweaks): heaviest 24 h; largest disagreement cluster at thresholds ≥ 10 mm (lower only if
  none); dry-vs-wet contrast where the wet point is in a group of ≥ 3 cells with ≥ 20 mm and a < 1 mm cell within 2 grid
  points; major city (≥ 1 M, in India) with the highest ENS P(≥ 10 mm); most confident heavy rain if P(≥ 50 mm) ≥ 30 %;
  spots ≥ 300 km apart; captions never call either model wrong.
- Rename done (`m8_checks.py brand`): heading read as "Barish" (accessibility tree), "रिश" drawn as real glyphs, not boxes,
  in headless Chrome on desktop/portrait/landscape; subtitle hidden only in the one-line short-screen header.

## Feature 1 — play (14 Nov) — `web/app.js` wire(), `m8_checks.py play`
- ▶/❚❚ button at the end of the time row (aria-pressed, label Play/Pause time animation). Steps the slider to the next
  frame every 1 s (2 s with prefers-reduced-motion), loops last → first, never autoplays. Pauses on any pointer press,
  wheel, touch or key press (except Space/Enter on the button) and when the tab is hidden.
- Check (real clicks/keys): no autoplay in 3 s; labels after 1/2/3 s = manifest frames 9, 10, then 0 (loop); map click,
  other key, › all pause; Space plays/pauses; reduced motion: no autoplay, 2 s steps; phone portrait 44 px / landscape
  34 px button, no sideways scroll. Also fixed: the guide toggle jumped to the top of the panel on short screens.

## Feature 2 — "100 skies" (14 Nov) — `web/app.js` skiesFigure, `m8_checks.py skies`
- In the point card under the chance chip, compact (user: the first 124 px grid took too much room → ~60 px grid in one row
  with its caption): 10×10 umbrellas (original SVG symbols), open (blue) = at least X mm, closed
  (ochre #b07a1e; the first grey #b3b8c0 had 2:1 contrast and vanished at 60 px; ochre 3.7:1 on white, OKLab dE 29 from
  the blue, 30/25 under deutan/protan simulation; dark grey was rejected at dE 11–14) = less; open count = the chip's whole % (stored chances are whole percents, so no extra rounding); "< 2 %" → 0 open,
  "fewer than 2 in 100". Caption "37 in 100 get ≥ 10 mm in this 24-hour window"; alt text gives both counts; never "members".
- Check: exact values 0, 1 (both "< 2 %"), 2, 37, 50, 99, 100 % found in the run and opened: open count = chip = panel,
  caption and alt right, icons ≤ 12.5 units on 100 distinct grid spots (first version drew every umbrella full-size on top
  of each other: <use> without width/height; the count-only check had passed), card fits phone portrait/landscape (compact
  card on short screens).

- **Redesign (user, 14 Nov): 6 px umbrella icons were unreadable** (open/closed indistinguishable at card size). Now a 10×10
  block of solid 6 px squares (69 px): blue #1f5fa8 = at least X mm, pale sand #e6cb94 = less (4.1:1 between them, dE 42,
  block still visible on white); above it a key with two readable 14 px umbrellas ("☂ ≥ 10 mm · closed = less").
  Earlier tries: grey closed umbrellas (2:1 on white, invisible), ochre umbrellas (visible but still unreadable shapes).
  Checks updated (squares counted by data-c; geometry: 100 distinct cells ≥ 5 px; key text); card check's guide-alt test now
  targets the guide SVG (the first SVG in the card is now a decorative key icon).

## Feature 3 — swipe compare (14 Nov; user moved it before deploying 1+2) — `web/app.js` updateSwipe, `m8_checks.py swipe`
- Toggle "Compare side by side…" in the 24 h controls (off by default; URL `cmp=1&sw=50`). Left = HRES 24 h total (pane fill),
  right = ENS chance for X (pane fill2), same window; each image clipped at the divider with clip-path (recomputed on
  move/zoom/resize/load); hatch pane above both, unclipped. Divider: full-height line + round handle (role slider):
  pointer drag (mouse/touch/pen, pointer capture), ←/→ 5 %, Shift 20 %, Home/End; never selects a point or steps time.
  Labels each side (short on maps < 640 px; stacked when colliding). Legend shows both scales with their own floor notes;
  colour buttons dimmed while comparing; "Showing: Comparing: …".
- Check (real events): pixel at a test point (15.75N 86.50E, 3×3-uniform bins, far from labels) = HRES colour #5daaf5 with
  the divider right of it, ENS colour #e657b1 left of it (also after a real mouse drag to 25 %); keyboard values
  [20, 40, 5, 95], time unchanged; hatch img unclipped across the divider; map click selects a point; toggle off restores
  the single image; phone portrait/landscape: real touch drag to 75 %, labels inside the map without overlap.
- Bugs found on the way: left legend showed the chance scale (legend chose the product from the fill state); labels
  overlapped on a 390 px phone.

## Deploy 14 Nov 14:41 UTC (run 43606088987): features 1 (play), 2 (100 skies), 3 (swipe compare) live
- Live check: play advances the window; card 100 skies 24 open = chip 24 % (values from the Render API); cmp=1&sw=40 opens
  the divider with the right image. API on the new build on try 2. Scheduled runs: still none since 02:31 UTC (both slots of
  14 Nov 00z not fired by 14:42 UTC); manual deploys cover it.
- **User (14 Nov): features 4 (plan my day) and 5 (story mode) deferred to later; next = README (outline first).**

## Scheduled runs on 14 Nov (00z slots 08:23–13:23 UTC)
- Only ONE of the six hourly slots fired: run 43608754960 at 15:10 UTC (≥ 1 h 47 min after the last slot); build success,
  "Live site already shows run 2026-11-14T00:00Z; nothing to deploy", deploy skipped, correct since 00z had been deployed
  by hand at 13:01 UTC. Overnight 13→14 Nov: 2 of 2 slots fired ~4 h late. So GitHub cron here is late and lossy; the
  hourly slots plus the skip check still made it work, and nothing is ever deployed twice.

## README written (14 Nov, `5414812`)
- ~2 screens (77 lines), user: reduce repetition, include a phone screenshot, and a brief "built with Claude Code in one
  session" note with the start time (first commit Thu 12 Nov 2026 16:22 IST). Images: `docs/readme/bay_disagreement.png`
  (desktop, 13 Nov 12z) + `docs/readme/phone_card.png` (live site 14 Nov 00z, 390×844 @2x, card at 15.75N 84.00E: 262.2 mm
  vs 22 % chance of ≥ 50 mm, hatched, guide "models disagree"). Note: the README's numbers are tied to those runs.

## Feature 5 — story mode "What's interesting today" (14 Nov) — `pipeline/highlights.py`, `web/app.js` storyGo/renderStory
- Spots chosen at build time from the STORED values (points.bin) into `manifest.highlights` (rules in highlights.py docstring,
  approved with tweaks: disagreement at X ≥ 10 mm; contrast wet point in a ≥ 3-cell group of ≥ 20 mm with a < 1 mm cell within
  2 grid points; ≥ 300 km apart). Run 14 Nov 00z: heaviest 13.50N 86.00E (713.4 mm, +72 h), disagreement 21.50N 89.25E (117-cell
  wetter group at ≥ 50 mm), contrast 15.25N 82.75E (75.0 mm, < 1 mm 77 km SW), city Chennai (33 % ≥ 10 mm), confident 5.25N 87.25E
  (100 % ≥ 50 mm). `tests/test_highlights.py` checks every rule independently.
- Page: "What's interesting today ▸" in the side panel; story bar over the map (Back / Next or Finish / Exit, Esc); each step
  sets 24 h mode, window, threshold, layer, flies there (no animation with reduced motion) and selects the point; the card is
  hidden during the story; captions built from the selected point's values with the panel's formatting, never calling a
  model wrong.
- Check `m8_checks.py story` (real clicks/keys): all 5 steps + Back: state, point, in view, caption mm/% == panel texts;
  keyboard Enter through to Finish; Esc restores the card; phone portrait/landscape bar inside the map. (A first version
  required the map to be centred on the point; a spot 0.25° from the region edge cannot be centred, so "in view" is checked.)
- Test harness note: `m8_checks.py card` timed out twice on page load (once on 14 Nov afternoon, once now) and passed on
  rerun both times: headless Chrome hiccup, not a page error.

## Feature 4 — Plan my day (14 Nov) — `web/app.js` planDay/renderPlan, twin `api/pointcore.py` plan_day, `m8_checks.py plan`
- Collapsible section in the side panel: own place field (the search component generalised: ids + onChoose), IST day picker
  (days touched by the run; default the 2nd, the 1st is partial). Uses the shared current point (map tap, p= link, search).
- Shows every HRES 3 h window overlapping the day with exact IST times (neighbouring-day parts marked "(Sat)"; day end
  "24:00"), each value with the frame's floor rule; driest stretch = longest run of windows below their floor (earliest if
  tied), or "No dry 3-hour window on this day." / "Dry in every 3-hour window shown (each below the lowest amount shown)."
  (first wording "Dry all day" overstated on days the run covers only partly → changed); ENS chance of ≥ X for the 24 h
  window overlapping the day most + "covers N of this day's 24 hours; its windows do not follow calendar days"; partial days:
  "The forecast covers only N hours of this day (…)".
- Check: every string == Python twin for Chennai/Mumbai/Port Blair × first/second/last day, a threshold change, a map tap,
  phone portrait/landscape (16/16); `test_plan_day_twin` in CI.

## README notes (for M8 C)
- **Next step (not built): vector hatching.** The disagreement hatch is a raster PNG stretched with `pixelated`, so stripes
  look staircased at the highest zooms. Drawing it as an SVG pattern from the manifest's flagged-cell lists (clusters ≥ 3)
  would keep it crisp at any zoom (user, 13–14 Nov: skipped for time).
- **Disagreement example (confirmed live 14 Nov 06:35 UTC, run 2026-11-13 12z):** 14.50°N 84.75°E, X = 100 mm, window
  Wed 18 Nov 05:30 → Thu 19 Nov 05:30 IST: HRES **441.4 mm** vs ENS **4 %** chance of ≥ 100 mm → flagged *wetter*, 12-cell
  group → hatched on the map; panel sentence "…only a 4 % chance of at least 100 mm here and nearby. Heavy rain is possible,
  not likely."; values from the Render API. At X = 50 mm the same window is *not* flagged (P≥50 = 28 % ≥ 25 %). Screenshot
  `outputs/checks/live_13nov12z_bay_hatch.png` (git-ignored; ask before committing an image to docs). Validation of the
  underlying 260 mm/3 h peak: `docs/validation/2026-11-13_12z_bay_peak.md`. Note: the live site moves on with each run.

## Next steps (order for 14 Nov, user-agreed 13 Nov night)
0. Confirm the 14 Nov 00z scheduled deploy (watcher running; see M7 section).
1. ~~M8 A + B~~ done 14 Nov (live with the next scheduled deploy; then live checks + user Safari/phone check).
   ~~M8 D~~ deployed 14 Nov. ~~M8 C point card~~ built 14 Nov (local; user check, then deploy). Next: README.
2. ~~M7b~~ done 13 Nov night (Render).
3. **M8 C**: point card, then README (vector hatch if time).
4. IMD-day view only if all of the above is done; 15 Nov buffer only.

## Remaining schedule (agreed 12 Nov)
| Day (IST) | Work |
|---|---|
| 12 Nov evening (after break) | M4 — **done**, plus disagreement layer and GitHub backup |
| 13 Nov (from morning) | M5 Leaflet front end — **done**, M6 point panel — **done**, M7 Pages deploy — **done** (live URL) |
| 14 Nov | (reordered 13 Nov night; M7b already done 13 Nov night) M8 A+B place names + keyboard → M8 D → point card + README. Automation already done in M7. Target: app finished by the night of 14 Nov |
| 14 Nov night | IMD-day (08:30–08:30 IST) HRES view, only if M8 is done |
| 15 Nov | Buffer only: fixes, no new features. Hard stop at start + 72 h |
