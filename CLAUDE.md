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
- [x] M4 3857 PNGs + manifest + point grid; alignment check (real transfer size: measure in M7 after deploy).
      Disagreement layer: approved and built (min cluster 3 on map).
- [x] M5 Leaflet front end locally (13 Nov)
- [x] M6 client-side point forecast panel (lazy-loaded) — 13 Nov
- [ ] M7 GitHub Actions + Pages deploy via deploy-pages (public URL)
- [ ] M7b FastAPI /point on HF Spaces (Render fallback), 14 Nov afternoon
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

## Status (13 Nov, evening IST): M0–M6 done; M7 next
**M0–M6 done; 42 tests passing; pushed to GitHub (13 Nov evening).** M6 closed by the user after confirming
both keyboard fixes in Safari (the ring lands on the crosshair). Earlier (afternoon): M0–M5 done. The map page runs locally and was checked by the user in Safari (all five check
views correct; console errors traced to a Safari extension and gone). Backed up to GitHub:
**https://github.com/shuvbytes/quest-precip** (private, branch `main`). Pages not enabled yet (M7).
Before making the repo public, re-check tracked files (now also `web/`, incl. vendored Leaflet + source map).
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
| this commit | M6 closed; M8 point-card idea recorded; pushed |

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
- **Open for M7:** GitHub Pages may not gzip `application/octet-stream`. Measure the real transfer with curl after
  deploy. If it is not compressed, ship `points.bin.gz` and decompress in the browser (DecompressionStream).

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

## M8 idea (user, 13 Nov) — record only, build in M8 after deployment
Compact **point card** anchored next to the selected point on the map: grid point + window, the main number, a chance
chip, a disagreement badge, a 6-day sparkline, and a "Full details" button that opens the existing side panel.
Updates with the slider; Esc/× closes; bottom sheet on phones; keyboard-accessible. **Reuse the panel's data code**
(selection, points.bin decode, formatting, flag lookup) rather than duplicating it.

## Next steps
**M7 — GitHub Actions + Pages deploy** (14 Nov per schedule; 13 Nov evening if time): workflow that fetches the latest
00z/12z run, builds `site_build/`, runs the tests, and deploys with `actions/upload-pages-artifact` + `deploy-pages`;
public URL; measure the real transfer size of points.bin (gzip by Pages or not → ship .gz + DecompressionStream).

## Remaining schedule (agreed 12 Nov)
| Day (IST) | Work |
|---|---|
| 12 Nov evening (after break) | M4 — **done**, plus disagreement layer and GitHub backup |
| 13 Nov (from morning) | M5 Leaflet front end (locally) — **done**, M6 point panel (wording + "nearby: X–Y mm"), M7 Pages deploy via deploy-pages (public URL) |
| 14 Nov | M7b FastAPI /point (HF Spaces, Render fallback); automation (GitHub Actions cron 2×/day, 00z/12z run selection); M8 polish ("last updated", README). Target: app finished by the night of 14 Nov |
| 14 Nov night | IMD-day (08:30–08:30 IST) HRES view, only if M8 is done |
| 15 Nov | Buffer only: fixes, no new features. Hard stop at start + 72 h |
