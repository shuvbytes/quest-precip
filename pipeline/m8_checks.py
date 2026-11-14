"""DEV-ONLY checks for M8 (real-clock headless Chrome, pipeline/cdp.py). Serves site_build/ on a free local port.

    python pipeline/m8_checks.py search      # place search, keyboard only
"""
from __future__ import annotations

import sys

import m5_screens as s
from cdp import Browser

OUT = s.ROOT / "outputs" / "checks"


def search():
    httpd, port = s.serve()
    ok = True
    try:
        with Browser(1440, 900) as b:
            b.open(f"http://127.0.0.1:{port}/index.html#mode=24h&fill=rain&t=0")
            cases = [("chen", 0, "13.00,80.25", "Chennai"), ("madras", 0, "13.00,80.25", "Chennai"),
                     ("bomb", 0, "19.00,72.75", "Mumbai"), ("kolk", 0, None, "Kolkata"),
                     ("thiruvanan", 0, None, "Thiruvananthapuram"), ("xyzq", None, None, None)]
            for q, pick, want_point, want_name in cases:
                b.js("document.getElementById('place-q').value = ''; document.getElementById('place-q').focus()")
                b.type(q)
                b.wait("!document.getElementById('place-list').hidden")
                opts = b.js("[...document.querySelectorAll('#place-list li')].map(li => li.textContent)")
                if pick is None:
                    good = opts == ["No matching place in the forecast area"] and \
                        b.js("document.getElementById('place-status').textContent") == "No matching place"
                    print(f"{'PASS' if good else 'FAIL'}  '{q}': {opts}")
                    ok &= good
                    continue
                b.key("ArrowDown")
                active = b.js("document.getElementById('place-q').getAttribute('aria-activedescendant')")
                b.key("Enter")
                b.wait("/^-?\\d/.test(document.body.dataset.point || '')", 20)
                point = b.js("document.body.dataset.point")
                title = b.js("document.getElementById('point-title').textContent")
                val = b.js("document.getElementById('place-q').value")
                good = val == want_name and active == "place-opt-0" and (want_point is None or point == want_point)
                print(f"{'PASS' if good else 'FAIL'}  '{q}' -> options {opts[:3]} -> ↓ ({active}) Enter -> "
                      f"input '{val}', panel '{title}' (point {point})")
                ok &= good
            b.js("document.getElementById('place-q').value=''; document.getElementById('place-q').focus()")
            b.type("pu")
            b.wait("!document.getElementById('place-list').hidden")
            b.key("ArrowDown"); b.key("ArrowDown")
            b.screenshot(OUT / "m8_search.png")
            b.key("Escape")
            closed = b.js("document.getElementById('place-list').hidden && document.getElementById('place-q').getAttribute('aria-expanded') === 'false'")
            print(f"{'PASS' if closed else 'FAIL'}  Esc closes the list (screenshot of 'pu' + 2×↓ saved)")
            ok &= bool(closed)
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


WALK_JS = r"""
(() => {
  const R = window.__rainOutlook, map = R.map, cur = R.cross, mc = map.getContainer();
  const g = { n: 38.0, w: 65.0, d: 0.25, nlat: 133, nlon: 141 };
  const ch = document.getElementById('crosshair'), title = document.getElementById('point-title');
  const press = (key, shift) => mc.dispatchEvent(new KeyboardEvent('keydown', { key, shiftKey: !!shift, bubbles: true, cancelable: true }));
  for (let i = 0; i < 200; i++) { press('ArrowUp', true); press('ArrowLeft', true); }   // to row 0, col 0
  const fails = [], size = map.getSize();
  let visited = 0, selects = 0, selectFails = 0, maxErr = 0;
  const check = (row, col) => {
    visited++;
    if (cur.row !== row || cur.col !== col) { fails.push(`at ${row},${col}: cross ${cur.row},${cur.col}`); return; }
    const want = map.latLngToContainerPoint([g.n - row * g.d, g.w + col * g.d]);
    const r = ch.getBoundingClientRect(), m = mc.getBoundingClientRect();
    const x = r.left + r.width / 2 - m.left, y = r.top + r.height / 2 - m.top;
    const err = Math.hypot(x - want.x, y - want.y); maxErr = Math.max(maxErr, err);
    if (err > 0.5) fails.push(`at ${row},${col}: drawn ${x.toFixed(1)},${y.toFixed(1)} want ${want.x.toFixed(1)},${want.y.toFixed(1)}`);
    if (x < 0 || y < 0 || x > size.x || y > size.y) fails.push(`at ${row},${col}: off screen ${x.toFixed(0)},${y.toFixed(0)}`);
    if (visited % 500 === 1) {                            // Enter selects exactly this grid point
      press('Enter'); selects++;
      const lat = (g.n - row * g.d).toFixed(2), lon = (g.w + col * g.d).toFixed(2);
      if (!title.textContent.includes(`${lat}°N, ${lon}°E`)) { selectFails++; fails.push(`Enter at ${row},${col}: '${title.textContent}'`); }
    }
  };
  for (let row = 0; row < g.nlat; row++) {
    const right = row % 2 === 0;
    for (let k = 0; k < g.nlon; k++) {
      const col = right ? k : g.nlon - 1 - k;
      check(row, col);
      if (k < g.nlon - 1) press(right ? 'ArrowRight' : 'ArrowLeft');
    }
    if (row < g.nlat - 1) press('ArrowDown');
  }
  return { visited, fails: fails.length, firstFails: fails.slice(0, 5), selects, selectFails, maxErr: +maxErr.toFixed(3), zoom: map.getZoom() };
})()
"""


def keys():
    httpd, port = s.serve()
    ok = True
    try:
        for (w, h, mobile) in ((1440, 900, False), (390, 844, True)):
            for z in (None, 7):
                with Browser(w, h, mobile=mobile) as b:
                    hsh = "mode=24h&fill=rain&t=0" + (f"&z={z}&c=20,80" if z else "")
                    b.open(f"http://127.0.0.1:{port}/index.html?api=off#{hsh}")
                    b.js("document.querySelector('#map').focus()")
                    r = b.js(WALK_JS)
                    good = r["visited"] == 133 * 141 and r["fails"] == 0 and r["selectFails"] == 0
                    print(f"{'PASS' if good else 'FAIL'}  walk {w}x{h} zoom {r['zoom']}: visited {r['visited']} grid points, "
                          f"Enter at {r['selects']} of them, failures {r['fails']} (max position error {r['maxErr']} px)"
                          + (f"  {r['firstFails']}" if r["fails"] else ""))
                    ok &= good
        # real key events (DevTools): arrows, Shift, +/- around the cross, Enter; Leaflet must not pan as well
        with Browser(1440, 900) as b:
            b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=rain&t=0&z=7&c=13,80.25")
            b.key("Tab")
            b.js("document.querySelector('#map').focus()")
            st = lambda: b.js("(() => { const R = window.__rainOutlook, c = R.map.getCenter(); const r = document.getElementById('crosshair').getBoundingClientRect(); return {row: R.cross.row, col: R.cross.col, z: R.map.getZoom(), cx: +c.lat.toFixed(4), cy: +c.lng.toFixed(4), x: +(r.left + r.width/2).toFixed(1), y: +(r.top + r.height/2).toFixed(1), shown: !document.getElementById('crosshair').hidden, readout: document.getElementById('cross-readout').textContent}; })()")
            b.key("ArrowRight")                              # first press shows the cross at the start point + 1
            a0 = st()
            b.key("ArrowRight"); a1 = st()
            b.key("ArrowDown", shift=True); a2 = st()
            res = [("arrow = +1 column, map not panned by Leaflet", a1["col"] == a0["col"] + 1 and a1["row"] == a0["row"]
                    and (a1["cx"], a1["cy"]) == (a0["cx"], a0["cy"])),
                   ("Shift+arrow = +10 rows", a2["row"] == a1["row"] + 10 and a2["col"] == a1["col"])]
            b.key("+"); z1 = st()
            res.append(("+ zooms in around the cross (same grid point, same screen spot ±1 px)",
                        z1["z"] > a2["z"] and (z1["row"], z1["col"]) == (a2["row"], a2["col"])
                        and abs(z1["x"] - a2["x"]) <= 1 and abs(z1["y"] - a2["y"]) <= 1))
            b.key("-"); z2 = st()
            res.append(("- zooms out around the cross", z2["z"] < z1["z"] and (z2["row"], z2["col"]) == (a2["row"], a2["col"])
                        and abs(z2["x"] - a2["x"]) <= 1 and abs(z2["y"] - a2["y"]) <= 1))
            b.key("Enter")
            b.wait("/^-?\\d/.test(document.body.dataset.point || '')", 20)
            lat, lon = 38.0 - z2["row"] * 0.25, 65.0 + z2["col"] * 0.25
            res.append((f"Enter selects the cross's grid point {lat:.2f},{lon:.2f}", b.js("document.body.dataset.point") == f"{lat:.2f},{lon:.2f}"))
            res.append(("readout shows position + nearest place", z2["readout"].startswith(f"{lat:.2f}°N {lon:.2f}°E · ")))
            b.screenshot(OUT / "m8_keys.png")
            for name, good in res:
                print(f"{'PASS' if good else 'FAIL'}  real keys: {name}")
                ok &= good
            print(f"      readout: {z2['readout']!r}")
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if {"search": search, "keys": keys}[sys.argv[1]]() else 1)
