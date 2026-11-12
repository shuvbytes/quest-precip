"""DEV-ONLY (needs cartopy from environment-dev.yml): side-by-side validation figure.

Left: our 0-144 h HRES total from open data (0.25 deg), drawn with ECMWF OpenCharts colour bins.
Right: ECMWF's own OpenCharts `medium-rain-acc` chart for the same run and lead time.
Usage: python pipeline/validation_figure.py data/raw/hres_tp_YYYYMMDDHHz.grib2 OUT.png
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request

import cartopy.crs as ccrs
import matplotlib
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import xarray as xr
from matplotlib.colors import BoundaryNorm, ListedColormap

matplotlib.use("Agg")

from process import base_time_utc, difference, step_hours
from region import crop

# ECMWF OpenCharts medium-rain-acc legend (mm) and colours sampled from the chart legend.
ECMWF_BINS = [0.1, 1, 2, 5, 10, 15, 20, 30, 40, 50, 100, 300, 1000]
ECMWF_COLS = ["#efdbb7", "#b5f9aa", "#78ee6f", "#b2eff7", "#7ab8f5", "#3d95f0", "#2163dc",
              "#fde67a", "#ffa200", "#ff0000", "#a01a1a", "#ff00ff"]
API = ("https://charts.ecmwf.int/opencharts-api/v1/products/medium-rain-acc/"
       "?base_time={b}&valid_time={v}&projection=opencharts_southern_asia")


def fetch_chart(base, end_h):
    import datetime as dt
    url = API.format(b=base.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     v=(base + dt.timedelta(hours=end_h)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    meta = json.load(urllib.request.urlopen(url, timeout=60))
    png = urllib.request.urlopen(meta["data"]["link"]["href"], timeout=60).read()
    return mpimg.imread(io.BytesIO(png), format="png"), url


def main(path, out):
    ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    tp = crop(ds["tp"]).load()
    base = base_time_utc(ds)
    end_h = int(step_hours(tp)[-1])
    total = difference(tp, [0], [end_h]).mm.isel(window=0)
    chart, url = fetch_chart(base, end_h)

    fig = plt.figure(figsize=(15, 7.2))
    ax = fig.add_subplot(1, 2, 1, projection=ccrs.PlateCarree())
    cm = ListedColormap(ECMWF_COLS)
    cm.set_under("white")
    m = ax.pcolormesh(total.longitude, total.latitude, total.values, cmap=cm,
                      norm=BoundaryNorm(ECMWF_BINS, cm.N), shading="nearest")
    ax.coastlines("10m", lw=0.6)
    ax.gridlines(draw_labels=True, lw=0.3)
    ax.set_title(f"Ours: open-data HRES 0.25°, 0–{end_h} h total, ECMWF chart bins\n"
                 f"run {base:%Y-%m-%d %H} UTC; one grid point per cell, no smoothing", fontsize=10)
    cb = fig.colorbar(m, ax=ax, orientation="horizontal", shrink=0.8, pad=0.07, label="mm")
    cb.set_ticks(ECMWF_BINS[:-1])
    cb.set_ticklabels([f"{b:g}" for b in ECMWF_BINS[:-1]])

    ax2 = fig.add_subplot(1, 2, 2)
    # Map panel cropped to roughly our region (the chart uses its own projection, so edges are approximate).
    ax2.imshow(chart[250:1245, 330:1480])
    ax2.axis("off")
    ax2.set_title(f"ECMWF OpenCharts 'medium-rain-acc', same run, +{end_h} h\n"
                  "(legend: 0.1, 1, 2, 5, 10, 15, 20, 30, 40, 50, 100, 300, 1000 mm)", fontsize=10)
    fig.text(0.5, 0.01, "Right panel © ECMWF, CC BY 4.0 (charts.ecmwf.int). "
             "Left panel: our processing of ECMWF Open Data (CC BY 4.0).", ha="center", fontsize=8)
    fig.savefig(out, dpi=80, bbox_inches="tight")
    print(f"wrote {out}\nchart API: {url}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
