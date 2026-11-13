"""India Rain Outlook: point forecast API (FastAPI).

Data: the API loads manifest.json + points.bin from the live site (GitHub Pages), the same files the browser uses, and
checks every few minutes whether a newer build is published (ETag / generated_utc). So it is always in sync with the
map and needs no data pipeline of its own. All point logic is in pointcore.py, shared with the panel check.

Run locally:  uvicorn app:app --port 7860   (on Render: --host 0.0.0.0 --port $PORT)            (env DATA_DIR=<site_build/data> to use local files)
"""
from __future__ import annotations

import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

import pointcore as pc

SITE_URL = os.environ.get("SITE_URL", "https://shuvbytes.github.io/quest-precip").rstrip("/")
DATA_DIR = os.environ.get("DATA_DIR")              # tests / local runs: a folder with manifest.json + points.bin
CHECK_EVERY_S = float(os.environ.get("CHECK_EVERY_S", "300"))
ALLOWED_ORIGINS = ["https://shuvbytes.github.io"]  # the site; browsers elsewhere get no CORS header


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    """The loaded forecast (manifest + decoded arrays), swapped atomically when a newer build appears."""

    def __init__(self):
        self.data = None            # (manifest, arrays)
        self.etag = None
        self.loaded_at = None
        self.last_check = 0.0
        self.last_check_utc = None
        self.last_error = None
        self._lock = threading.Lock()

    # where the files come from
    def _manifest(self):
        if DATA_DIR:
            import json
            return json.loads((Path(DATA_DIR) / "manifest.json").read_text()), None
        h = {"If-None-Match": self.etag} if self.etag and self.data else {}
        r = httpx.get(f"{SITE_URL}/data/manifest.json", headers=h, timeout=20)
        if r.status_code == 304:
            return None, self.etag
        r.raise_for_status()
        return r.json(), r.headers.get("etag")

    def _points(self, m):
        if DATA_DIR:
            return (Path(DATA_DIR) / m["points"]["file"]).read_bytes()
        r = httpx.get(f"{SITE_URL}/data/{m['points']['file']}", timeout=60)   # httpx undoes the gzip transfer
        r.raise_for_status()
        return r.content

    def refresh(self):
        """Load the newest build if it differs from the one in memory. Errors keep the old data."""
        if not self._lock.acquire(blocking=False):
            return                                          # a refresh is already running
        try:
            self.last_check, self.last_check_utc = time.time(), _now()
            m, etag = self._manifest()
            if m is None or (self.data and m["generated_utc"] == self.data[0]["generated_utc"]):
                self.etag = etag or self.etag
                self.last_error = None
                return
            arrays = pc.decode(m, self._points(m))          # checks the byte count against the manifest
            self.data, self.etag, self.loaded_at, self.last_error = (m, arrays), etag, _now(), None
        except Exception as e:                               # noqa: BLE001 (report, keep serving the old data)
            self.last_error = f"{type(e).__name__}: {e}"
        finally:
            self._lock.release()

    def maybe_refresh(self, background: BackgroundTasks):
        if time.time() - self.last_check > CHECK_EVERY_S:
            self.last_check = time.time()                   # no second check while this one runs
            background.add_task(self.refresh)


store = Store()


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=store.refresh, daemon=True).start()   # start serving at once; /health says "loading"
    yield


app = FastAPI(
    title="India Rain Outlook: point forecast API",
    version="1.0",
    lifespan=lifespan,
    description=(
        "Rain forecast at the nearest 0.25° grid point for India and nearby seas (5–38°N, 65–100°E): ECMWF IFS HRES "
        "3-hourly and 24-hour totals (mm) and the ensemble's chance (%) of at least 1–100 mm in 24 hours, with the "
        "same values and wording as the map at https://shuvbytes.github.io/quest-precip/. Data is read from that site "
        "and refreshed when a new forecast run is published.\n\n"
        "Source: ECMWF Open Data, CC BY 4.0. Modified: cropped, de-accumulated, converted to mm, rounded to 0.1 mm / 1 %. "
        "ECMWF does not endorse this service."),
)
# DEV_ORIGIN_REGEX: local checks only (e.g. http://127\.0\.0\.1:\d+); unset on the Space, so only the site is allowed.
# gzip: a /point answer is 36.7 kB raw, 3.2 kB gzipped; Render's free plan includes 5 GB outbound per month
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_origin_regex=os.environ.get("DEV_ORIGIN_REGEX"),
                   allow_methods=["GET"], allow_headers=[])


@app.exception_handler(RequestValidationError)
async def invalid(request: Request, exc: RequestValidationError):
    msgs = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": "invalid_request", "message": "; ".join(msgs)})


def _error(status, code, message, **extra):
    return JSONResponse(status_code=status, content={"error": code, "message": message, **extra})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health", summary="Is the forecast loaded, and which run?")
def health(background: BackgroundTasks):
    store.maybe_refresh(background)
    base = {"source": DATA_DIR and "local files" or SITE_URL, "last_check_utc": store.last_check_utc,
            "last_error": store.last_error}
    if not store.data:
        return JSONResponse(status_code=503, content={"status": "loading", **base})
    m = store.data[0]
    return {"status": "ok", "run_utc": m["run"]["utc"], "run_ist": m["run"]["ist"],
            "generated_utc": m["generated_utc"], "loaded_at_utc": store.loaded_at, **base}


@app.get("/point", summary="Forecast at the nearest grid point")
def point(
    background: BackgroundTasks,
    lat: float = Query(..., ge=-90, le=90, allow_inf_nan=False, description="Latitude in degrees north (−90…90), e.g. 13.08"),
    lon: float = Query(..., ge=-180, le=180, allow_inf_nan=False, description="Longitude in degrees east (−180…180), e.g. 80.27"),
    x: str = Query("10", description="Threshold in mm for the summary's chance line: 1, 5, 10, 20, 25, 50 or 100"),
    t: int = Query(0, description="Start hour of the 24-hour window for the summary: 0, 12, 24, … 120"),
):
    """Values at the grid point nearest to (lat, lon): every 3-hour and 24-hour HRES amount, every ENS chance
    (with disagreement flags and their sentences) and a summary for one threshold and window, worded exactly as on
    the map's point panel. Outside the forecast area: 404 with the area's limits."""
    store.maybe_refresh(background)
    if not store.data:
        return _error(503, "loading", "The forecast is still loading; try again in a few seconds.")
    m, arrays = store.data
    keys = pc.threshold_keys(m)
    try:
        xk = pc.js_num(float(x))
    except ValueError:
        xk = None
    if xk not in keys:
        return _error(422, "invalid_request", f"x must be one of {', '.join(keys)} (mm)")
    starts = [f["start_h"] for f in m["products"]["hres_24h"]["frames"]]
    if t not in starts:
        return _error(422, "invalid_request", f"t must be one of {', '.join(map(str, starts))} (hours after the run)")
    r = pc.point_report(m, arrays, lat, lon, xk, t)
    if r is None:
        reg = m["region"]
        return _error(404, "outside_forecast_area",
                      f"No forecast here: ({lat:.2f}, {lon:.2f}) is outside the forecast area, "
                      f"{pc.js_num(reg['lat_min'])}–{pc.js_num(reg['lat_max'])}°N, "
                      f"{pc.js_num(reg['lon_min'])}–{pc.js_num(reg['lon_max'])}°E.",
                      forecast_area=reg, requested={"lat": lat, "lon": lon})
    r["source"] = {"data": DATA_DIR and "local files" or f"{SITE_URL}/data/", "attribution": m["attribution"]}
    return JSONResponse(r, headers={"Cache-Control": "public, max-age=60"})
