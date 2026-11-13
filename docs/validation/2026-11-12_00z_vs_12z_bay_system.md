# Run-to-run: the Bay of Bengal heavy-rain system, 2026-11-12 00z vs 12z

**Observation.** In the 00z run, the ensemble (ENS) put its highest chance of ≥ 100 mm in 24 h **earlier and further
southwest** than the single high-resolution run (HRES) put its heaviest rain. Twelve hours later, the 12z HRES
moved its heaviest rain **earlier and southwest as well**: the new HRES peak is closer to where the old ENS
pointed than to where the old HRES had it.

**Caveat.** This is one case. It is consistent with the ensemble giving useful early warning of a shift, but one case is not
evidence that ENS is more skilful in general. Peak locations are maxima of noisy 0.25° point fields: differences of
one or two grid steps (28–56 km) carry little meaning. The 12z ENS itself moved further still (below), so this is not a
case of "the forecast converged".

All times below are **valid times** (when the rain falls), not lead times. The two runs start 12 h apart, so the same
lead time means different days. Bay box: 5–20°N, 80–95°E.

## The key peaks

| What | Run | Valid window (IST) | Value | Location |
|---|---|---|---|---|
| HRES heaviest 24 h | 00z | Tue 17 Nov 05:30 → Wed 18 Nov 05:30 (+120–144 h) | 381.6 mm | 15.00°N 86.50°E |
| ENS best P(≥ 100 mm) | 00z | Sun 15 Nov 17:30 → Mon 16 Nov 17:30 (+84–108 h) | 42 % | 13.00°N 84.75°E |
| HRES heaviest 24 h | 12z | Sun 15 Nov 05:30 → Mon 16 Nov 05:30 (+60–84 h) | 475.1 mm | 11.50°N 85.00°E |
| ENS best P(≥ 100 mm) | 12z | Sat 14 Nov 17:30 → Sun 15 Nov 17:30 (+48–72 h) | 52 % | 9.50°N 85.25°E |

Distances:
- 00z ENS peak → 00z HRES peak: **292 km** (ENS earlier by ~1.5 days in valid time, and to the SW).
- 00z HRES peak → 12z HRES peak: **422 km**, and about 2 days earlier.
- 00z ENS peak → 12z HRES peak: **169 km**, with the 12z HRES peak within 12 h of the old ENS peak window
  (the 12z HRES also has 466 mm at the same point in exactly the old ENS window, 15 Nov 12Z–16 Nov 12Z).
- 00z ENS peak → 12z ENS peak: **393 km**, 1 day earlier, further south.

## Same valid windows, both runs (ENS threshold 100 mm)

| Valid window (UTC) | 00z HRES max | 00z ENS max P | 12z HRES max | 12z ENS max P |
|---|---|---|---|---|
| 14 Nov 00Z–15 Nov 00Z | 131 mm, 7.00N 83.25E | 21 %, 7.25N 84.50E | 296 mm, 8.25N 85.75E | 45 %, 9.00N 85.50E |
| 14 Nov 12Z–15 Nov 12Z | 324 mm, 9.00N 84.75E | 24 %, 9.25N 83.75E | 281 mm, 8.25N 85.75E | **52 %**, 9.50N 85.25E |
| 15 Nov 00Z–16 Nov 00Z | 318 mm, 9.00N 84.75E | 30 %, 11.25N 84.25E | **475 mm**, 11.50N 85.00E | 37 %, 11.25N 85.50E |
| 15 Nov 12Z–16 Nov 12Z | 217 mm, 12.75N 85.75E | **42 %**, 13.00N 84.75E | 466 mm, 11.50N 85.00E | 41 %, 12.75N 85.75E |
| 16 Nov 00Z–17 Nov 00Z | 311 mm, 13.75N 86.00E | 39 %, 13.75N 85.25E | 371 mm, 13.50N 85.75E | 27 %, 13.25N 86.50E |
| 16 Nov 12Z–17 Nov 12Z | 369 mm, 15.00N 86.50E | 33 %, 13.50N 85.75E | 280 mm, 13.50N 85.75E | 22 %, 14.25N 86.00E |
| 17 Nov 00Z–18 Nov 00Z | **382 mm**, 15.00N 86.50E | 27 %, 15.25N 86.25E | 231 mm, 15.00N 85.75E | 23 %, 17.00N 87.75E |

Read across a row: in the 12z run, both HRES and ENS put the heaviest rain and highest chances 1–2 days earlier
than the 00z HRES did, and further south. The 00z HRES's late, northern maximum (the 505 mm 0–144 h cell at 15.00N
86.50E) has weakened to 231 mm in the 12z run.

## What this means for the app
- It supports showing ENS probabilities **next to** HRES, not only HRES: the 00z ENS already pointed to the
  timing and position the next HRES moved towards.
- The disagreement layer flagged the 00z HRES Bay maximum as "wetter than the ensemble" at 100 mm (108–132 h).
  In the 12z run that maximum was not repeated, which is consistent with that flag.

Reproduce (dev environment, needs both runs in `data/raw/`):
`python pipeline/compare_runs.py data/raw/hres_tp_2026111200z.grib2 data/raw/ens_tpg_2026111200z.grib2 data/raw/hres_tp_2026111212z.grib2 data/raw/ens_tpg_2026111212z.grib2 100`
