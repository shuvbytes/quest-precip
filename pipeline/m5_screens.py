"""DEV-ONLY: screenshot the built site with headless Google Chrome (already installed; no new dependency).

Desktop Chrome will not make a window narrower than ~500 px, so pages are loaded inside an <iframe> of the
exact viewport size (a true 390 px "phone"), on a wrapper page this script serves at /__viewport.html. The wrapper
is never written to the site. It copies the page's check attributes (data-status, data-zoom, data-hscroll,
data-frame, zoom-note visibility) onto itself so --dump-dom can read them.
Usage: python pipeline/m5_screens.py name=WxH[#hash][@scrollY] ...
  e.g. python pipeline/m5_screens.py desktop=1440x900 "phone=390x844#mode=24h&x=100&t=60" "phone_low=390x844@700"
"""
from __future__ import annotations

import functools
import http.server
import os
import re
import socketserver
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SITE = Path(os.environ.get("SITE_DIR", ROOT / "site_build"))
OUT = ROOT / "outputs" / "checks"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

WRAPPER = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;background:#fff}}iframe{{border:0;display:block;width:{w}px;height:{h}px}}</style>
</head><body data-status="loading"><iframe id="f" src="{src}"></iframe>
<script>
const f = document.getElementById("f");
function copy() {{
  const d = f.contentDocument;
  if (!d || !d.body || d.body.dataset.status === "loading") return setTimeout(copy, 100);
  if ({scroll}) f.contentWindow.scrollTo(0, {scroll});
  for (const k of ["status", "zoom", "hscroll", "frame"]) document.body.dataset[k] = d.body.dataset[k] || "";
  const n = d.getElementById("zoom-note");
  document.body.dataset.zoomnote = n && !n.hidden ? "visible" : "hidden";
}}
f.addEventListener("load", copy);
</script></body></html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path != "/__viewport.html":
            return super().do_GET()
        q = urllib.parse.parse_qs(u.query)
        body = WRAPPER.format(w=int(q["w"][0]), h=int(q["h"][0]), scroll=int(q.get("scroll", ["0"])[0]),
                              src="index.html" + (("#" + q["hash"][0]) if q.get("hash") else "")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve():
    httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(SITE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def chrome(args, url):
    base = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            "--virtual-time-budget=9000", "--run-all-compositor-stages-before-draw"]
    return subprocess.run(base + args + [url], capture_output=True, text=True, timeout=120)


def shot(name, w, h, hsh="", scroll=0, port=None):
    q = urllib.parse.urlencode({"w": w, "h": h, "hash": hsh, "scroll": scroll})
    url = f"http://127.0.0.1:{port}/__viewport.html?{q}"
    win = f"--window-size={max(w, 520)},{h}"
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"m5_{name}.png"
    chrome([win, f"--screenshot={png}"], url)
    Image.open(png).crop((0, 0, w, h)).save(png)            # keep exactly the emulated viewport
    dom = chrome([win, "--dump-dom"], url).stdout
    attrs = {k: (re.search(rf'data-{k}="([^"]*)"', dom) or [None, "?"])[1]
             for k in ("status", "zoom", "hscroll", "zoomnote", "frame")}
    z = attrs["zoom"]
    print(f"{name:12s} {w}x{h:<5d} scroll={scroll:<4d} status={attrs['status']} "
          f"zoom={float(z):.2f} " if z not in ("?", "") else f"{name:12s} status={attrs['status']} ", end="")
    print(f"hscroll={attrs['hscroll']} zoom-note={attrs['zoomnote']}  -> {png.name}")
    return attrs


def main(specs):
    httpd, port = serve()
    try:
        for spec in specs:
            name, rest = spec.split("=", 1)
            rest, _, scroll = rest.partition("@")
            size, _, hsh = rest.partition("#")
            w, h = map(int, size.split("x"))
            shot(name, w, h, hsh, int(scroll or 0), port)
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main(sys.argv[1:] or ["desktop=1440x900"])
