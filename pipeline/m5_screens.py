"""DEV-ONLY: screenshot the built site with headless Google Chrome (already installed; no new dependency).

Starts a local http server on site_build/, loads the page at given window sizes and URL hashes, saves PNGs to
outputs/checks/, and prints the page's data-status ("ready" or "error: ...") read from the rendered DOM.
Usage: python pipeline/m5_screens.py name=WxH[#hash] [name=WxH[#hash] ...]
  e.g. python pipeline/m5_screens.py desktop=1440x900 phone=390x844 bay=1440x900#mode=24h&x=100&t=9
"""
from __future__ import annotations

import functools
import http.server
import re
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = Path(__import__("os").environ.get("SITE_DIR", ROOT / "site_build"))
OUT = ROOT / "outputs" / "checks"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    handler = functools.partial(Quiet, directory=str(SITE))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def chrome(args, url):
    base = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            "--virtual-time-budget=8000", "--run-all-compositor-stages-before-draw"]
    return subprocess.run(base + args + [url], capture_output=True, text=True, timeout=120)


def shot(name, size, hsh, port):
    w, h = size.split("x")
    url = f"http://127.0.0.1:{port}/index.html" + (f"#{hsh}" if hsh else "")
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"m5_{name}.png"
    chrome([f"--window-size={w},{h}", f"--screenshot={png}"], url)
    dom = chrome([f"--window-size={w},{h}", "--dump-dom"], url).stdout
    status = re.search(r'data-status="([^"]*)"', dom)
    print(f"{name:12s} {size:>9s} {('#' + hsh) if hsh else '':40s} status={status.group(1) if status else '??'}  -> {png}")
    return dom


def main(specs):
    httpd, port = serve()
    try:
        for spec in specs:
            name, rest = spec.split("=", 1)
            size, _, hsh = rest.partition("#")
            shot(name, size, hsh, port)
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main(sys.argv[1:] or ["desktop=1440x900"])
