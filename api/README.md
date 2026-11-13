# India Rain Outlook: point forecast API

`GET /point?lat=13.08&lon=80.27` returns the forecast at the nearest 0.25° grid point (5–38°N, 65–100°E):
ECMWF IFS HRES rain for every 3-hour step and 24-hour window (mm), and the ensemble's chance (%) of at least
1, 5, 10, 20, 25, 50 and 100 mm in each 24-hour window, with disagreement flags. Values and wording are the same as
on the map: https://shuvbytes.github.io/quest-precip/

- `GET /point?lat=&lon=[&x=10][&t=0]`: `x` = threshold (mm) and `t` = window start hour, for the `summary` block.
- `GET /health`: which forecast run is loaded (503 while loading).
- `/docs`: interactive documentation.

Data: read from the site above (`data/manifest.json`, `data/points.bin`) and refreshed when a new run is published.
Only https://shuvbytes.github.io may call it from a browser (CORS).

## Hosting: Render free web service, native Python runtime (no Docker)
Root Directory `api` · Build `pip install -r requirements.txt` · Start `uvicorn app:app --host 0.0.0.0 --port $PORT` ·
Health check path `/health` · env `PYTHON_VERSION=3.11.18` (same as the tested conda env) · Auto-Deploy on commit to `main`.
Free services sleep after 15 minutes without requests; the first request then takes about a minute, during which the
map page uses its own copy of the data (points.bin).

Source: ECMWF Open Data (www.ecmwf.int), licence CC BY 4.0. Modified: cropped, de-accumulated, converted to mm,
rounded to 0.1 mm / 1 %. ECMWF does not endorse this service.
