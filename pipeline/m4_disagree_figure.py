"""DEV-ONLY (needs cartopy): check figures for the disagreement layer.

1. Geography: ENS probability frame + hatch frame placed in Web Mercator by their bounds
   (as L.imageOverlay does), coastlines, lat/lon labels, title with threshold and IST window,
   Bay point marked. Full region + zoom.
2. Readability: the same overlay at the pixel size a browser draws it at web zooms 5/6/7.
Usage: python pipeline/m4_disagree_figure.py [site_data_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cartopy.crs as ccrs
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw

matplotlib.use("Agg")

from render import merc_y

R = 6378137.0
BAY = (15.0, 86.5)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "checks"
CASES = [  # threshold, window start, zoom box (lon0, lon1, lat0, lat1), what to look for
    ("100", 108, (82, 92, 9, 19), "wetter hatching on the Bay streak"),
    ("1", 108, (85, 94, 5, 11), "drier dots south of the Bay"),
]


def frame(m, product, x, s):
    return next(f for f in m["products"][product]["frames_by_threshold"][x] if f["start_h"] == s)


def composite(d, m, x, s):
    """ENS frame (upsampled, nearest) + hatch frame, on white, at hatch resolution."""
    e = Image.open(d / frame(m, "ens_prob", x, s)["file"]).convert("RGBA")
    h = frame(m, "disagreement", x, s)
    if h["file"]:
        hatch = Image.open(d / h["file"]).convert("RGBA")
        e = e.resize(hatch.size, Image.NEAREST)
    out = Image.new("RGBA", e.size, "white")
    out.alpha_composite(e)
    if h["file"]:
        out.alpha_composite(hatch)
    return out


def main(d=ROOT / "site_build" / "data"):
    d = Path(d)
    m = json.loads((d / "manifest.json").read_text())
    (s_, w_), (n_, e_) = m["image"]["bounds"]
    extent = [np.radians(w_) * R, np.radians(e_) * R, merc_y(s_) * R, merc_y(n_) * R]
    merc = ccrs.Mercator.GOOGLE

    fig = plt.figure(figsize=(15, 13))
    for k, (x, s, box, look) in enumerate(CASES):
        img = np.asarray(composite(d, m, x, s))
        h = frame(m, "disagreement", x, s)
        for j, ext in enumerate([(65, 100, 5, 38), box]):
            ax = fig.add_subplot(2, 2, 2 * k + j + 1, projection=merc)
            ax.imshow(img, extent=extent, origin="upper", transform=merc, interpolation="nearest")
            ax.coastlines("10m", lw=0.7, color="#333333")
            ax.set_extent(ext, crs=ccrs.PlateCarree())
            gl = ax.gridlines(draw_labels=True, lw=0.3, alpha=0.6)
            gl.top_labels = gl.right_labels = False
            ax.plot(BAY[1], BAY[0], "o", ms=12, mfc="none", mec="red", mew=2, transform=ccrs.PlateCarree())
            if j == 1:
                lo0, lo1, la0, la1 = box
                ax.set_title(f"Zoom {la0}–{la1}°N {lo0}–{lo1}°E: {look}", fontsize=9)
            else:
                ax.set_title(f"ENS chance of ≥ {x} mm + disagreement hatch\n{h['label_ist']}\n"
                             f"{h['n_wetter']} wetter (diagonal) / {h['n_drier']} drier (dots) cells; "
                             f"red ring = Bay point 15°N 86.5°E", fontsize=9)
    fig.suptitle(f"Disagreement layer check, run {m['run']['utc']} ({m['run']['ist']})", fontsize=11)
    out1 = OUT / "m4_disagree_check.png"
    fig.savefig(out1, dpi=85, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out1}")

    # --- readability at web-map zooms (Leaflet pixel scale: 256 * 2^z px per 360 deg of longitude) ---
    tiles = []
    for x, s, box, look in CASES:
        comp = composite(d, m, x, s)
        lo0, lo1, la0, la1 = box
        for z in (5, 6, 7):
            width = 256 * 2 ** z * (e_ - w_) / 360
            scale = width / comp.width
            img = comp.resize((round(comp.width * scale), round(comp.height * scale)),
                              Image.LANCZOS if scale < 1 else Image.NEAREST)
            # crop the zoom box in the scaled image (Mercator rows)
            def px(lat, lon):
                r = (merc_y(n_) - merc_y(lat)) / (merc_y(n_) - merc_y(s_)) * img.height
                c = (lon - w_) / (e_ - w_) * img.width
                return c, r
            c0, r0 = px(la1, lo0)
            c1, r1 = px(la0, lo1)
            crop = img.crop((int(c0), int(r0), int(c1), int(r1)))
            canvas = Image.new("RGBA", (crop.width, crop.height + 18), "white")
            canvas.paste(crop, (0, 18))
            ImageDraw.Draw(canvas).text((3, 3), f">={x} mm, zoom {z} ({width / 141:.1f} px/cell)", fill="black")
            tiles.append(canvas)
    W = sum(t.width for t in tiles[:3]) + 20
    H = max(t.height for t in tiles[:3]) + max(t.height for t in tiles[3:]) + 10
    sheet = Image.new("RGBA", (W, H), "white")
    xo = 0
    for t in tiles[:3]:
        sheet.paste(t, (xo, 0)); xo += t.width + 10
    xo, yo = 0, max(t.height for t in tiles[:3]) + 10
    for t in tiles[3:]:
        sheet.paste(t, (xo, yo)); xo += t.width + 10
    out2 = OUT / "m4_disagree_zooms.png"
    sheet.save(out2)
    print(f"wrote {out2} (shown at true screen pixels; downsampling smooths, upsampling is pixelated)")


if __name__ == "__main__":
    main(*sys.argv[1:])
