"""DEV-ONLY: exact-match check of the point panel against Python (M6 step 6).

For each place: Python picks the nearest grid point (same rule as the page), decodes points.bin with
build.read_points, and formats every value with the panel's rules ("< 0.5 mm" below a frame's lowest drawn step,
one decimal, whole %, flag symbols). Then the page is opened headless at #...&p=lat,lon and every element with a
data-field is read back. Each field is compared as text: MATCH / DIFF. The raw GRIB values (before 0.1 mm / 1 %
storage) are printed alongside, to show the quantisation.
Usage: python pipeline/m6_check.py <hres_tp file> [mode=24h&fill=chance&x=100&t=60]
Env M6_QUERY='?api=off' forces the in-browser lookup (otherwise the page asks the point API first).
"""
from __future__ import annotations

import html
import os
import json
import re
import sys
from pathlib import Path

import numpy as np
import xarray as xr

import m5_screens as s

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import pointcore as pc  # noqa: E402  (shared with the API)
from build import read_points
from process import deaccumulate, window_totals
from region import crop

ROOT = Path(__file__).resolve().parent.parent
PLACES = [("Chennai", 13.0827, 80.2707, None), ("Bay of Bengal", 15.00, 86.50, None),
          ("Central India (dry)", 22.00, 78.00, None),
          # flagged cells, to check the disagreement sentence too (12z run of 12 Nov): a hatched Bay cell and an
          # isolated flag that the map does not hatch; each with its own view (threshold, window)
          ("Flagged Bay cell", 9.50, 85.00, "mode=24h&fill=chance&x=100&t=60"),
          ("Isolated flag (not on map)", 38.00, 78.75, "mode=24h&fill=chance&x=1&t=0")]


def expected(m, pts, row, col, state):
    """The panel's texts from Python (api/pointcore.py, the same code the API uses)."""
    exp = pc.panel_fields(m, pts, row, col, state["x"], state["t"])
    k = pc.window_index(m["products"]["hres_24h"]["frames"], state["t"])
    kx = pc.threshold_keys(m).index(state["x"])
    fl = pc.cell_flag(m, state["x"], k, row * m["grid"]["nlon"] + col)
    return exp, k, kx, (fl["kind"], fl["on_map"]) if fl else None


def page_fields(port, hsh, tries=3):
    for i in range(tries):
        dom = s.chrome(["--window-size=1440,1000", "--dump-dom"], f"http://127.0.0.1:{port}/index.html{os.environ.get('M6_QUERY', '')}#{hsh}").stdout
        point = (re.search(r'data-point="([^"]*)"', dom) or [None, ""])[1]
        if point and point != "loading":
            fields = {k: html.unescape(re.sub(r"<[^>]+>", "", v)).strip()
                      for k, v in re.findall(r'data-field="([^"]+)"[^>]*>(.*?)</(?:td|p)>', dom, re.S)}
            return point, fields
    return point, {}


def main(hres_path, default_view="mode=24h&fill=chance&x=100&t=60"):
    m = json.loads((s.SITE / "data" / "manifest.json").read_text())
    pts = read_points(s.SITE / "data" / "points.bin", m["points"])
    g = m["grid"]
    tp = crop(xr.open_dataset(hres_path, engine="cfgrib", backend_kwargs={"indexpath": ""})["tp"]).load()
    raw3, raw24 = deaccumulate(tp).mm.values, window_totals(tp).mm.values
    print(f"run {m['run']['utc']} ({m['run']['ist']})\n")
    httpd, port = s.serve()
    total_ok = total = 0
    try:
        for name, lat, lon, view in PLACES:
            view = view or default_view
            state = dict(re.findall(r"(\w+)=([^&]+)", view))
            state["t"] = int(state["t"])
            row = int(round((g["lat_north"] - lat) / g["dlat"]))
            col = int(round((lon - g["lon_west"]) / g["dlon"]))
            glat, glon = g["lat_north"] - row * g["dlat"], g["lon_west"] + col * g["dlon"]
            exp, k, kx, fl = expected(m, pts, row, col, state)
            point, got = page_fields(port, f"{view}&p={lat},{lon}")
            ok = [f for f in exp if got.get(f) == exp[f]]
            bad = [f for f in exp if got.get(f) != exp[f]]
            extra = sorted(set(got) - set(exp))
            total_ok += len(ok); total += len(exp)
            w = m["products"]["hres_24h"]["frames"][k]
            print(f"== {name}: clicked {lat}, {lon} -> grid point {glat:.2f}N {glon:.2f}E (page: {point})")
            print(f"   values from: {got.get('source', '(no source line)')}")
            print(f"   view #{view}; window {w['label_ist']}" + (f"; flag: {fl[0]}, on map: {fl[1]}" if fl else ""))
            for f in ("sum-24h", "near-24h", "sum-ens", "disagree"):
                if f in exp or f in got:
                    print(f"   {f:9s} python: {exp.get(f, '(none)')!r}\n   {'':9s} page:   {got.get(f, '(none)')!r}"
                          f"   {'MATCH' if exp.get(f) == got.get(f) else 'DIFF'}")
            print(f"   raw GRIB 24 h at the point: {raw24[k, row, col]:.4f} mm -> stored {pts['hres_24h'][k, row, col]:.1f};"
                  f" 3 h values: max |raw - stored| = {np.abs(raw3[:, row, col] - pts['hres_3h'][:, row, col]).max():.3f} mm")
            print(f"   3 h bars/table (48) + 24 h totals (11) + ENS cells (77) + summary: "
                  f"{len(ok)}/{len(exp)} fields MATCH" + (f"; DIFF: {bad[:6]}" if bad else "") +
                  (f"; page-only fields: {extra}" if extra else "") + "\n")
    finally:
        httpd.shutdown()
    print(f"TOTAL: {total_ok}/{total} fields match exactly")
    return total_ok == total


if __name__ == "__main__":
    sys.exit(0 if main(*sys.argv[1:]) else 1)
