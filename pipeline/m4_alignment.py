"""DEV-ONLY (needs cartopy): alignment check of rendered frames in Leaflet's projection (EPSG:3857).

1. Numbers: at known coastal points, which source grid cell does the rendered image show at that
   location (using the same pixel <-> lat/lon mapping Leaflet uses), and how far is it from the
   cell that actually contains the point? Compared with a naive lat/lon image (no reprojection).
2. Picture: ECMWF's land-sea mask rendered through render.py, plus one rain frame, placed in
   Web Mercator by their bounds exactly like L.imageOverlay, with coastlines drawn on top.
Usage: python pipeline/m4_alignment.py <hres_tp file> <rain frame png> <lsm grib or "fetch">
"""
from __future__ import annotations

import sys
from pathlib import Path

import cartopy.crs as ccrs
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from PIL import Image

matplotlib.use("Agg")

from region import crop
from render import Grid, merc_y, render_png

R_EARTH = 6378137.0  # Web Mercator sphere (m)
POINTS = {
    "Chennai": (13.0827, 80.2707),
    "Kanyakumari": (8.0883, 77.5385),
    "Dondra Head (Sri Lanka S tip)": (5.9227, 80.5895),
    "Mumbai": (18.9220, 72.8347),
    "Chittagong": (22.3569, 91.7832),
    "Karachi": (24.8607, 67.0011),
}
OUT = Path(__file__).resolve().parent.parent / "outputs" / "checks"


def km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl, dp = np.radians(lon2 - lon1), p2 - p1
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def fetch_lsm(base_date, hour, target):
    from ecmwf.opendata import Client
    Client(source="ecmwf", model="ifs", resol="0p25").retrieve(
        date=base_date, time=hour, stream="oper", type="fc", param="lsm", step=0, target=str(target))
    return target


def main(hres_path, frame_png, lsm_path):
    ds = xr.open_dataset(hres_path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    tp = crop(ds["tp"])
    lat, lon = tp.latitude.values, tp.longitude.values
    g = Grid.from_coords(lat, lon)
    rows, cols = g.resample_index()
    (s, w), (n, e) = g.bounds

    print("== 1. Cell shown at each point vs the cell containing it ==")
    print(f"   image {g.width}x{g.height} px, bounds S {s} N {n} W {w} E {e}")
    print(f"   {'point':30s} {'cell containing it':>19s} {'cell shown (ours)':>19s} {'error':>7s}"
          f" {'cell shown (naive)':>19s} {'error':>7s}")
    for name, (la, lo) in POINTS.items():
        ti, tj = g.source_index(la, lo)
        r, c = g.latlon_to_pixel(la, lo)               # where Leaflet draws this location
        oi, oj = rows[r], cols[c]                      # which source cell our image has there
        # naive image: rows evenly spaced in LATITUDE, but Leaflet still stretches them in Mercator
        frac = (merc_y(n) - merc_y(la)) / (merc_y(n) - merc_y(s))
        ni = min(int(frac * g.nlat), g.nlat - 1)
        err_ours = km(lat[ti], lon[tj], lat[oi], lon[oj])
        err_naive = km(lat[ti], lon[tj], lat[ni], lon[tj])
        print(f"   {name:30s} {lat[ti]:7.2f}N {lon[tj]:7.2f}E   {lat[oi]:7.2f}N {lon[oj]:7.2f}E"
              f" {err_ours:6.1f}km   {lat[ni]:7.2f}N {lon[tj]:7.2f}E {err_naive:6.1f}km")
    # whole image: max distance between where each pixel is drawn and the centre of its source cell
    plat, _ = g.pixel_to_latlon(np.arange(g.height), 0)
    _, plon = g.pixel_to_latlon(0, np.arange(g.width))
    dlat_km = np.abs(plat - lat[rows]).max() * 111.2
    dlon_km = (np.abs(plon - lon[cols]) * 111.2 * np.cos(np.radians(5))).max()
    print(f"   all pixels: drawn position vs centre of the cell they show, max {dlat_km:.1f} km N-S, "
          f"{dlon_km:.1f} km E-W (half a 0.25° cell is 13.9 km N-S; i.e. within the cell)")

    # --- picture ---
    lsm_path = Path(lsm_path)
    if str(lsm_path) == "fetch":
        lsm_path = Path(hres_path).with_name(f"lsm_{Path(hres_path).stem.split('_')[-1]}.grib2")
        if not lsm_path.exists():
            fetch_lsm(str(tp.time.values)[:10], int(str(tp.time.values)[11:13]), lsm_path)
    lsm = crop(xr.open_dataset(lsm_path, engine="cfgrib", backend_kwargs={"indexpath": ""})["lsm"]).values
    print(f"\n   land-sea mask: units {xr.open_dataset(lsm_path, engine='cfgrib', backend_kwargs={'indexpath': ''})['lsm'].attrs.get('units')!r}, "
          f"range {lsm.min():.2f}-{lsm.max():.2f}")
    lsm_png = OUT / "m4_lsm_rendered.png"
    render_png(lsm, g, [0.5, 1.01], ["#c9a66b"], 0.5, lsm_png)   # land (lsm >= 0.5) drawn

    merc = ccrs.Mercator.GOOGLE
    extent = [np.radians(w) * R_EARTH, np.radians(e) * R_EARTH, merc_y(s) * R_EARTH, merc_y(n) * R_EARTH]
    views = {"Whole region": (65, 100, 5, 38), "Chennai": (78.8, 81.8, 11.6, 14.6),
             "Kanyakumari": (76.0, 79.0, 6.6, 9.6), "Sri Lanka S tip": (79.1, 82.1, 5.0, 7.4)}
    fig = plt.figure(figsize=(16, 9))
    for k, (title, (x0, x1, y0, y1)) in enumerate(views.items()):
        ax = fig.add_subplot(2, 4, k + 1, projection=merc)
        ax.imshow(np.asarray(Image.open(lsm_png).convert("RGBA")), extent=extent, origin="upper",
                  transform=merc, interpolation="nearest")
        ax.coastlines("10m", lw=0.8, color="black")
        ax.set_extent([x0, x1, y0, y1], crs=ccrs.PlateCarree())
        for name, (la, lo) in POINTS.items():
            if x0 <= lo <= x1 and y0 <= la <= y1:
                ax.plot(lo, la, "r+", ms=10, mew=2, transform=ccrs.PlateCarree())
        ax.gridlines(draw_labels=k == 0, lw=0.3)
        ax.set_title(f"{title}: ECMWF land-sea mask (tan)\nvia render.py; black = coastline", fontsize=8)
        ax2 = fig.add_subplot(2, 4, k + 5, projection=merc)
        ax2.imshow(np.asarray(Image.open(frame_png).convert("RGBA")), extent=extent, origin="upper",
                   transform=merc, interpolation="nearest")
        ax2.coastlines("10m", lw=0.8, color="black")
        ax2.set_extent([x0, x1, y0, y1], crs=ccrs.PlateCarree())
        ax2.set_title(f"{title}: rain frame {Path(frame_png).name}", fontsize=8)
    fig.suptitle("Frames placed in Web Mercator (EPSG:3857) by their bounds, as L.imageOverlay does", fontsize=10)
    out = OUT / "m4_alignment.png"
    fig.savefig(out, dpi=90, bbox_inches="tight")
    print(f"   wrote {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
