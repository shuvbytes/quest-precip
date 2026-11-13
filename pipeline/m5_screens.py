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
import json
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
  // wait for a selected point's data too (max ~3 s, so a deliberately slowed load still shows its loading state)
  if (d.body.dataset.point === "loading" && (window.__w = (window.__w || 0) + 1) < 30) return setTimeout(copy, 100);
  if ({scroll}) f.contentWindow.scrollTo(0, {scroll});
  for (const k of ["status", "zoom", "hscroll", "frame", "point"]) document.body.dataset[k] = d.body.dataset[k] || "";
  const n = d.getElementById("zoom-note");
  document.body.dataset.zoomnote = n && !n.hidden ? "visible" : "hidden";
}}
f.addEventListener("load", copy);
</script></body></html>"""


# Slider stress test: 300 'input' events in one burst, counting history.replaceState calls (Safari throws after
# 100 per 10 s). Reports the count, the page status, any post-load error and the final URL hash.
STRESS = """<!doctype html><html><body data-status="loading"><iframe id="f" src="index.html#{hash}" style="width:1200px;height:800px;border:0"></iframe>
<script>
const f = document.getElementById("f");
function go() {{
  const w = f.contentWindow, d = f.contentDocument;
  if (!d || !d.body || d.body.dataset.status !== "ready") return setTimeout(go, 100);
  let calls = 0;
  const orig = w.history.replaceState.bind(w.history);
  w.history.replaceState = (...a) => {{ calls++; return orig(...a); }};
  const sl = d.getElementById("t");
  for (let i = 0; i < 300; i++) {{ sl.value = i % (+sl.max + 1); sl.dispatchEvent(new w.Event("input")); }}
  setTimeout(() => {{
    document.body.dataset.calls = calls;
    document.body.dataset.pagestatus = d.body.dataset.status;
    document.body.dataset.lasterror = d.body.dataset.lasterror || "none";
    document.body.dataset.hash = w.location.hash;
    document.body.dataset.label = d.getElementById("t-label").textContent;
    document.body.dataset.status = "done";
  }}, 1200);
}}
f.addEventListener("load", go);
</script></body></html>"""


# Keyboard test: focus the map, press ArrowRight x3 (must pan, not change the time window), Enter (select the point under
# the centre crosshair), wait for the panel, then Escape (close). Reports what happened at each stage.
KEYS = """<!doctype html><html><body data-status="loading"><iframe id="f" src="index.html#{hash}" style="width:1200px;height:800px;border:0"></iframe>
<script>
const f = document.getElementById("f");
const out = (k, v) => {{ document.body.dataset[k] = v; }};
function go() {{
  const w = f.contentWindow, d = f.contentDocument;
  if (!d || !d.body || d.body.dataset.status !== "ready") return setTimeout(go, 100);
  const mc = d.getElementById("map"), label0 = d.getElementById("t-label").textContent;
  const key = (k) => {{                // keyCode must be set explicitly (Leaflet reads it; init dicts ignore it)
    const ev = new w.KeyboardEvent("keydown", {{ key: k, bubbles: true }}), code = {{ArrowRight: 39, Enter: 13, Escape: 27}}[k];
    Object.defineProperty(ev, "keyCode", {{ get: () => code }});
    mc.dispatchEvent(ev);
  }};
  const cBefore = w.__rainOutlook.map.getCenter();
  d.dispatchEvent(new w.KeyboardEvent("keydown", {{ key: "Tab", bubbles: true }}));   // a real user tabs to the map
  mc.focus();
  out("crosshair", d.getElementById("crosshair").hidden ? "hidden" : "visible");
  const c0 = w.__map ? "" : "";
  for (let i = 0; i < 3; i++) key("ArrowRight");
  setTimeout(() => {{
    out("timeunchanged", String(d.getElementById("t-label").textContent === label0));
    out("panned", String(!w.__rainOutlook.map.getCenter().equals(cBefore)));
    key("Enter");
    const wait = (n) => {{
      const p = d.body.dataset.point || "";
      if ((p === "" || p === "loading") && n < 60) return setTimeout(() => wait(n + 1), 100);
      out("selected", p);
      out("panel", d.getElementById("point").hidden ? "hidden" : "visible");
      out("hash", w.location.hash);
      key("Escape");
      setTimeout(() => {{ out("afteresc", d.getElementById("point").hidden ? "hidden" : "visible"); out("status", "done"); }}, 600);
    }};
    wait(0);
  }}, 800);
}}
f.addEventListener("load", go);
</script></body></html>"""


# Crosshair test: it must appear only for keyboard use, never for mouse/touch.
CROSS = """<!doctype html><html><body data-status="loading"><iframe id="f" src="index.html#mode=3h&t=33" style="width:1200px;height:800px;border:0"></iframe>
<script>
const f = document.getElementById("f");
function go() {
  const w = f.contentWindow, d = f.contentDocument;
  if (!d || !d.body || d.body.dataset.status !== "ready") return setTimeout(go, 100);
  const mc = d.getElementById("map"), ch = () => (d.getElementById("crosshair").hidden ? "hidden" : "VISIBLE");
  const ptr = () => mc.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true }));
  const key = (k, target) => (target || d).dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true }));
  const r = [];
  ptr(); mc.focus(); r.push("1 mouse click focuses map: " + ch());
  mc.blur(); key("Tab"); mc.focus(); r.push("2 Tab onto map: " + ch());
  ptr(); r.push("3 mouse press after keyboard: " + ch());
  key("ArrowRight", mc); r.push("4 arrow key on mouse-focused map: " + ch());
  mc.blur(); r.push("5 map loses focus: " + ch());
  document.body.dataset.result = r.join(" | ");
  document.body.dataset.status = "done";
}
f.addEventListener("load", go);
</script></body></html>"""


# Crosshair accuracy: open a point first (the panel grows the page), then Tab to the map, pan with arrow keys, press
# Enter, and measure in CSS px how far the selected position is drawn from the crosshair centre.
AIM = """<!doctype html><html><body data-status="loading" style="margin:0"><iframe id="f" src="index.html#{hash}" style="width:{w}px;height:{h}px;border:0"></iframe>
<script>
const f = document.getElementById("f");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function go() {{
  const w = f.contentWindow, d = f.contentDocument;
  if (!d || !d.body || d.body.dataset.status !== "ready" || !w.__rainOutlook) return setTimeout(go, 100);
  const map = w.__rainOutlook.map, mc = d.getElementById("map");
  // 1. open a point by clicking (panel appears and grows the page), wait for its data
  map.fire("click", {{ latlng: w.L.latLng(15, 80), originalEvent: {{}} }});
  for (let i = 0; i < 80 && (d.body.dataset.point || "loading") === "loading"; i++) await sleep(100);
  await sleep(300);
  // 2. keyboard: Tab to the map, pan, Enter
  d.dispatchEvent(new w.KeyboardEvent("keydown", {{ key: "Tab", bubbles: true }}));
  mc.focus();
  // Leaflet reads e.keyCode, which browsers ignore in a KeyboardEvent init dict, so set it explicitly; dispatch on the
  // document (where Leaflet listens while the map has focus) and on the map (where the page's Enter handler is).
  const key = (k, code, target) => {{
    const ev = new w.KeyboardEvent("keydown", {{ key: k, bubbles: true }});
    Object.defineProperty(ev, "keyCode", {{ get: () => code }});
    Object.defineProperty(ev, "which", {{ get: () => code }});
    (target || mc).dispatchEvent(ev);
  }};
  const c0 = map.getCenter();
  // Move the map as two ArrowDown + two ArrowRight presses would (Leaflet pans 80 px per press). Leaflet's own arrow
  // handling does not run under headless Chrome's simulated clock (its pan animation never completes there), so pan
  // directly by the same pixels; arrow-key panning itself was confirmed by the user in a real browser.
  map.panBy([160, 160], {{ animate: false }});
  await sleep(300);

  const settle = async () => {{                      // wait until the map stops moving (pans animate)
    let prev = "";
    for (let i = 0; i < 40; i++) {{ const c = map.getCenter(), now = c.lat.toFixed(6) + c.lng.toFixed(6);
      if (now === prev) return; prev = now; await sleep(150); }}
  }};
  await settle();
  // how far the arrow keys moved the map (measured after the pans have finished)
  document.body.dataset.panned = map.latLngToContainerPoint(c0).distanceTo(map.getSize().divideBy(2)).toFixed(0);
  const offsetNow = () => {{
    const cr = d.getElementById("crosshair").getBoundingClientRect(), mr = mc.getBoundingClientRect();
    return [cr.left + cr.width / 2 - mr.left, cr.top + cr.height / 2 - mr.top];
  }};
  key("Enter", 13);
  const [ax, ay] = offsetNow();
  const atEnter = map.containerPointToLatLng([ax, ay]);
  await sleep(300);
  await settle();
  document.body.dataset.moved = map.latLngToContainerPoint(atEnter).distanceTo([ax, ay]).toFixed(1);
  // 3. measure
  const sub = [...d.querySelectorAll("#point-body .sub")].map((e) => e.textContent).find((t) => t.startsWith("You selected"));
  const m = sub && sub.match(/([\\d.]+)°N, ([\\d.]+)°E/);
  const cr = d.getElementById("crosshair").getBoundingClientRect(), mr = mc.getBoundingClientRect();
  const cx = cr.left + cr.width / 2 - mr.left, cy = cr.top + cr.height / 2 - mr.top;
  let res = "no selection";
  if (m) {{
    const p = map.latLngToContainerPoint([+m[1], +m[2]]);
    res = `arrow keys panned ${{document.body.dataset.panned}} px; map moved after Enter by ${{d.body.dataset.moved || document.body.dataset.moved}} px; selected ${{m[1]}}N ${{m[2]}}E; crosshair at (${{cx.toFixed(1)}}, ${{cy.toFixed(1)}}) px, selection drawn at ` +
          `(${{p.x.toFixed(1)}}, ${{p.y.toFixed(1)}}) px -> offset ${{(p.x - cx).toFixed(1)}}, ${{(p.y - cy).toFixed(1)}} px; ` +
          `map box ${{mr.height.toFixed(0)}} px tall, Leaflet thinks ${{map.getSize().y}} px`;
    document.body.dataset.dy = (p.y - cy).toFixed(1); document.body.dataset.dx = (p.x - cx).toFixed(1);
  }}
  document.body.dataset.result = res; document.body.dataset.status = "done";
}}
f.addEventListener("load", go);
</script></body></html>"""


# Edge reach: from the fitted view or zoom 7, hold Shift+arrows toward each edge/corner until nothing moves, Enter, and
# report the selected grid point and whether it is the grid point nearest the crosshair centre.
EDGES = """<!doctype html><html><body data-status="loading" style="margin:0"><iframe id="f" src="index.html#{hash}" style="width:{w}px;height:{h}px;border:0"></iframe>
<script>
const f = document.getElementById("f"); const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const DIRS = {{ S: ["ArrowDown"], N: ["ArrowUp"], W: ["ArrowLeft"], E: ["ArrowRight"],
  SW: ["ArrowDown", "ArrowLeft"], SE: ["ArrowDown", "ArrowRight"], NW: ["ArrowUp", "ArrowLeft"], NE: ["ArrowUp", "ArrowRight"] }};
async function go() {{
  const w = f.contentWindow, d = f.contentDocument;
  if (!d || !d.body || d.body.dataset.status !== "ready" || !w.__rainOutlook) return setTimeout(go, 100);
  const map = w.__rainOutlook.map, mc = d.getElementById("map"), out = [];
  const key = (k, shift) => mc.dispatchEvent(new w.KeyboardEvent("keydown", {{ key: k, shiftKey: !!shift, bubbles: true }}));
  const crossLL = () => {{ const cr = d.getElementById("crosshair").getBoundingClientRect(), mr = mc.getBoundingClientRect();
    return map.containerPointToLatLng([cr.left + cr.width / 2 - mr.left, cr.top + cr.height / 2 - mr.top]); }};
  const view = map.getCenter(), z0 = map.getZoom();
  for (const [name, keys] of Object.entries(DIRS)) {{
    map.setView(view, z0, {{ animate: false }});
    d.dispatchEvent(new w.KeyboardEvent("keydown", {{ key: "Tab", bubbles: true }}));
    d.body.dispatchEvent(new w.PointerEvent("pointerdown", {{ bubbles: true }}));   // reset the crosshair to the centre
    d.dispatchEvent(new w.KeyboardEvent("keydown", {{ key: "Tab", bubbles: true }}));
    mc.blur(); mc.focus();
    let prev = "", presses = 0;
    for (let i = 0; i < 400; i++) {{
      for (const k of keys) key(k, true);
      presses++;
      const c = crossLL(), now = c.lat.toFixed(5) + "," + c.lng.toFixed(5) + "," + map.getCenter().lat.toFixed(5);
      if (now === prev) break; prev = now;
    }}
    const c = crossLL();
    key("Enter");
    await sleep(150);
    const title = d.getElementById("point-title").textContent;
    const g = w.__rainOutlook.map && title.match(/([\d.]+)°N, ([\d.]+)°E/);
    const nearest = [(38 - Math.round((38 - c.lat) / 0.25) * 0.25).toFixed(2), (65 + Math.round((c.lng - 65) / 0.25) * 0.25).toFixed(2)];
    const ringPx = g ? map.latLngToContainerPoint([+g[1], +g[2]]).distanceTo(map.latLngToContainerPoint(c)) : NaN;
    const cellPx = map.latLngToContainerPoint([c.lat, c.lng]).distanceTo(map.latLngToContainerPoint([c.lat + 0.125, c.lng + 0.125]));
    out.push(`${{name}}|${{g ? g[1] + "," + g[2] : "none"}}|${{nearest.join(",")}}|${{presses}}|${{ringPx.toFixed(1)}}|${{cellPx.toFixed(1)}}|${{map.getZoom()}}`);
  }}
  document.body.dataset.result = out.join(";"); document.body.dataset.status = "done";
}}
f.addEventListener("load", go);
</script></body></html>"""


# Reach named places by keyboard only: big steps (Shift+arrow), then 80 px steps, then Alt+arrow grid steps, then Enter.
TARGETS = """<!doctype html><html><body data-status="loading" style="margin:0"><iframe id="f" src="index.html#{hash}" style="width:{w}px;height:{h}px;border:0"></iframe>
<script>
const f = document.getElementById("f"); const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PLACES = {places};
async function go() {{
  const w = f.contentWindow, d = f.contentDocument;
  if (!d || !d.body || d.body.dataset.status !== "ready" || !w.__rainOutlook) return setTimeout(go, 100);
  const map = w.__rainOutlook.map, mc = d.getElementById("map"), out = [];
  const key = (k, mods) => mc.dispatchEvent(new w.KeyboardEvent("keydown", Object.assign({{ key: k, bubbles: true }}, mods || {{}})));
  const crossPx = () => {{ const cr = d.getElementById("crosshair").getBoundingClientRect(), mr = mc.getBoundingClientRect();
    return w.L.point(cr.left + cr.width / 2 - mr.left, cr.top + cr.height / 2 - mr.top); }};
  const view = map.getCenter(), z0 = map.getZoom();
  for (const [name, lat, lon] of PLACES) {{
    map.setView(view, z0, {{ animate: false }});
    d.body.dispatchEvent(new w.PointerEvent("pointerdown", {{ bubbles: true }}));      // crosshair back to centre
    d.dispatchEvent(new w.KeyboardEvent("keydown", {{ key: "Tab", bubbles: true }})); mc.blur(); mc.focus();
    const tr = Math.round((38 - lat) / 0.25), tc = Math.round((lon - 65) / 0.25);
    const target = [38 - tr * 0.25, 65 + tc * 0.25];
    let presses = 0;
    for (let i = 0; i < 300; i++) {{
      const here = map.containerPointToLatLng(crossPx());
      const r = Math.round((38 - here.lat) / 0.25), c = Math.round((here.lng - 65) / 0.25);
      if (r === tr && c === tc) break;
      const tp = map.latLngToContainerPoint(target), cp = crossPx(), dx = tp.x - cp.x, dy = tp.y - cp.y;
      const ax = Math.abs(dx) >= Math.abs(dy), dist = Math.abs(ax ? dx : dy), sgn = Math.sign(ax ? dx : dy);
      const k = ax ? (sgn > 0 ? "ArrowRight" : "ArrowLeft") : (sgn > 0 ? "ArrowDown" : "ArrowUp");
      if (ax ? c === tc : r === tr) {{ key(ax ? (r < tr ? "ArrowDown" : "ArrowUp") : (c < tc ? "ArrowRight" : "ArrowLeft"), {{ altKey: true }}); }}
      else if (dist > 300) key(k, {{ shiftKey: true }});
      else if (dist > 100) key(k);
      else key(k, {{ altKey: true }});
      presses++;
    }}
    key("Enter");
    await sleep(150);
    const t = d.getElementById("point-title").textContent;
    out.push(`${{name}}|${{t}}|${{target[0].toFixed(2)}}N ${{target[1].toFixed(2)}}E|${{presses}}`);
  }}
  document.body.dataset.result = out.join(";"); document.body.dataset.status = "done";
}}
f.addEventListener("load", go);
</script></body></html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass                                    # headless Chrome closing early; not an error of the page

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/__targets.html":
            places = json.dumps([["Kanyakumari", 8.0883, 77.5385], ["Sri Lanka S tip (Dondra Head)", 5.9227, 80.5895],
                                 ["Southern Bay", 6.0, 88.0], ["Jaffna", 9.66, 80.01], ["Gilgit (far north)", 35.92, 74.31],
                                 ["Andaman (Port Blair)", 11.62, 92.72], ["Karachi (west)", 24.86, 67.0]])
            return self._send(TARGETS.format(hash=q.get("hash", ["mode=3h&t=33"])[0], w=int(q.get("w", ["1440"])[0]),
                                             h=int(q.get("h", ["900"])[0]), places=places).encode())
        if u.path == "/__edges.html":
            return self._send(EDGES.format(hash=q.get("hash", ["mode=3h&t=33"])[0], w=int(q.get("w", ["1440"])[0]),
                                           h=int(q.get("h", ["900"])[0])).encode())
        if u.path == "/__aim.html":
            return self._send(AIM.format(hash=q.get("hash", ["mode=3h&t=33"])[0], w=int(q.get("w", ["1440"])[0]),
                                         h=int(q.get("h", ["900"])[0])).encode())
        if u.path == "/__cross.html":
            return self._send(CROSS.encode())
        if u.path == "/__keys.html":
            return self._send(KEYS.format(hash=q.get("hash", ["mode=3h&t=33"])[0]).encode())
        if u.path == "/__stress.html":
            return self._send(STRESS.format(hash=q.get("hash", ["mode=3h&t=0"])[0]).encode())
        if u.path.endswith("points.bin") and os.environ.get("SLOW_POINTS"):
            # dev only: hold the point file back so the panel's loading state can be screenshotted
            import time
            time.sleep(float(os.environ["SLOW_POINTS"]))
        if u.path != "/__viewport.html":
            return super().do_GET()
        body = WRAPPER.format(w=int(q["w"][0]), h=int(q["h"][0]), scroll=int(q.get("scroll", ["0"])[0]),
                              src="index.html" + (("#" + q["hash"][0]) if q.get("hash") else "")).encode()
        self._send(body)

    def _send(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve():
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(SITE)))
    httpd.daemon_threads = True   # threaded: a slow points.bin (SLOW_POINTS) must not block the other files
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def chrome(args, url):
    base = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            "--run-all-compositor-stages-before-draw"]
    # Simulated time waits for every pending download; REAL_TIME=seconds instead shoots after that many real seconds
    # (used to capture the point panel's loading state while a slowed points.bin is still in flight).
    base += [f"--timeout={int(float(os.environ['REAL_TIME']) * 1000)}"] if os.environ.get("REAL_TIME") \
        else [f"--virtual-time-budget={os.environ.get('VTB', '9000')}"]
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
             for k in ("status", "zoom", "hscroll", "zoomnote", "frame", "point")}
    z = attrs["zoom"]
    print(f"{name:12s} {w}x{h:<5d} scroll={scroll:<4d} status={attrs['status']} "
          f"zoom={float(z):.2f} " if z not in ("?", "") else f"{name:12s} status={attrs['status']} ", end="")
    print(f"hscroll={attrs['hscroll']} zoom-note={attrs['zoomnote']} point={attrs['point']!r}  -> {png.name}")
    return attrs


def stress(hsh="mode=3h&t=0"):
    httpd, port = serve()
    try:
        url = f"http://127.0.0.1:{port}/__stress.html?" + urllib.parse.urlencode({"hash": hsh})
        dom = chrome(["--window-size=1300,900", "--dump-dom"], url).stdout
    finally:
        httpd.shutdown()
    get = lambda k: (re.search(rf'data-{k}="([^"]*)"', dom) or [None, "?"])[1]
    print(f"stress: 300 slider inputs -> history.replaceState calls={get('calls')}, page status={get('pagestatus')}, "
          f"post-load error={get('lasterror')}\n        final hash={get('hash')}\n        label={get('label')}")


def keys(hsh="mode=3h&t=33"):
    httpd, port = serve()
    try:
        url = f"http://127.0.0.1:{port}/__keys.html?" + urllib.parse.urlencode({"hash": hsh})
        dom = chrome(["--window-size=1300,900", "--dump-dom"], url).stdout
    finally:
        httpd.shutdown()
    get = lambda k: (re.search(rf'data-{k}="([^"]*)"', dom) or [None, "?"])[1]
    print(f"keys: crosshair on focus={get('crosshair')}, map panned by 3x ArrowRight={get('panned')}, "
          f"time window unchanged={get('timeunchanged')}, "
          f"Enter selected point={get('selected')}, panel={get('panel')}, after Esc panel={get('afteresc')}\n"
          f"      URL hash after selection={get('hash')}")


def crosshair():
    httpd, port = serve()
    try:
        dom = chrome(["--window-size=1300,900", "--dump-dom"], f"http://127.0.0.1:{port}/__cross.html").stdout
    finally:
        httpd.shutdown()
    res = (re.search(r'data-result="([^"]*)"', dom) or [None, "?"])[1]
    print("crosshair:\n  " + "\n  ".join(res.split(" | ")))


def targets():
    """Reach named places near the edges by keyboard only (Shift/plain/Alt arrows), Enter, check the grid point."""
    os.environ.setdefault("VTB", "60000")
    httpd, port = serve()
    ok_all = True
    try:
        for w, h in [(1440, 900), (390, 844)]:
            for label, hsh in [("fitted", "mode=3h&t=33"), ("zoom 7", "mode=3h&t=33&z=7&c=20,80")]:
                url = f"http://127.0.0.1:{port}/__targets.html?" + urllib.parse.urlencode({"hash": hsh, "w": w, "h": h})
                dom = chrome([f"--window-size={max(w, 520) + 20},{h + 20}", "--dump-dom"], url).stdout
                res = (re.search(r'data-result="([^"]*)"', dom) or [None, ""])[1]
                print(f"{w}x{h} {label}:")
                for row in filter(None, res.split(";")):
                    name, title, target, presses = row.split("|")
                    ok = title == f"Grid point {target.replace('N', '°N,').replace('E', '°E')}"
                    ok_all &= ok
                    print(f"  {'OK ' if ok else 'BAD'} {name:30s} target {target:16s} panel: {title:30s} ({presses} key presses)")
                if not res:
                    ok_all = False
                    print("  (no result)")
    finally:
        httpd.shutdown()
    print("ALL TARGETS REACHED BY KEYBOARD" if ok_all else "FAIL")
    return ok_all


def edges():
    """Every edge and corner of the forecast area must be reachable by keyboard, and Enter must select the grid point
    nearest the crosshair. Fitted view and zoom 7, desktop and phone width."""
    os.environ.setdefault("VTB", "60000")
    expect = {"S": ("5.00", None), "N": ("38.00", None), "W": (None, "65.00"), "E": (None, "100.00"),
              "SW": ("5.00", "65.00"), "SE": ("5.00", "100.00"), "NW": ("38.00", "65.00"), "NE": ("38.00", "100.00")}
    httpd, port = serve()
    ok_all = True
    try:
        for w, h in [(1440, 900), (390, 844)]:
            for label, hsh in [("fitted", "mode=3h&t=33"), ("zoom 7", "mode=3h&t=33&z=7&c=20,80")]:
                url = f"http://127.0.0.1:{port}/__edges.html?" + urllib.parse.urlencode({"hash": hsh, "w": w, "h": h})
                dom = chrome([f"--window-size={max(w, 520) + 20},{h + 20}", "--dump-dom"], url).stdout
                res = (re.search(r'data-result="([^"]*)"', dom) or [None, ""])[1]
                print(f"{w}x{h} {label}:")
                for row in filter(None, res.split(";")):
                    name, sel, near, presses, ring, cell, z = row.split("|")
                    lat, lon = (sel.split(",") + [None])[:2]
                    el, eo = expect[name]
                    reach = (el is None or lat == el) and (eo is None or lon == eo)
                    nearest = sel == near
                    ok = reach and nearest and float(ring) <= float(cell) + 0.5
                    ok_all &= ok
                    print(f"  {name:2s} {'OK ' if ok else 'BAD'} selected {sel:13s} (expected edge {el or '-'}N/{eo or '-'}E: "
                          f"{'reached' if reach else 'NOT reached'}); nearest grid point to crosshair {near} "
                          f"{'=' if nearest else '!='}; ring {ring} px from crosshair (half cell {cell} px); "
                          f"{presses} Shift+arrow presses; zoom {float(z):.2f}")
                if not res:
                    ok_all = False
                    print("  (no result)")
    finally:
        httpd.shutdown()
    print("ALL EDGES AND CORNERS REACHABLE, NEAREST GRID POINT SELECTED" if ok_all else "FAIL")
    return ok_all


def aim():
    """Crosshair accuracy across window sizes and zooms; prints the offset in CSS px (must be <= 1)."""
    os.environ.setdefault("VTB", "60000")          # waits for data and pans step by step (simulated clock)
    httpd, port = serve()
    worst = 0.0
    try:
        for w, h in [(1440, 900), (1280, 700), (1024, 768), (390, 844)]:
            for z in (5, 6, 7):
                hsh = f"mode=3h&t=33&z={z}&c=20,80"
                url = f"http://127.0.0.1:{port}/__aim.html?" + urllib.parse.urlencode({"hash": hsh, "w": w, "h": h})
                dom = chrome([f"--window-size={max(w, 520) + 20},{h + 20}", "--dump-dom"], url).stdout
                res = (re.search(r'data-result="([^"]*)"', dom) or [None, "?"])[1]
                dx = float((re.search(r'data-dx="([^"]*)"', dom) or [None, "nan"])[1])
                dy = float((re.search(r'data-dy="([^"]*)"', dom) or [None, "nan"])[1])
                off = (dx * dx + dy * dy) ** 0.5
                worst = max(worst, off) if off == off else float("inf")
                print(f"  {w}x{h} zoom {z}: {'OK ' if off <= 1 else 'BAD'} {res}")
    finally:
        httpd.shutdown()
    print(f"worst offset: {worst:.1f} px  ->  {'PASS' if worst <= 1 else 'FAIL'}")
    return worst <= 1


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
    if sys.argv[1:2] == ["stress"]:
        stress(*sys.argv[2:3])
    elif sys.argv[1:2] == ["targets"]:
        sys.exit(0 if targets() else 1)
    elif sys.argv[1:2] == ["edges"]:
        sys.exit(0 if edges() else 1)
    elif sys.argv[1:2] == ["aim"]:
        sys.exit(0 if aim() else 1)
    elif sys.argv[1:2] == ["crosshair"]:
        crosshair()
    elif sys.argv[1:2] == ["keys"]:
        keys(*sys.argv[2:3])
    else:
        main(sys.argv[1:] or ["desktop=1440x900"])
