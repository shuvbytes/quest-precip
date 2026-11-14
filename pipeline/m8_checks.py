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


RECORDER_JS = r"""
(() => {
  // After every real key press (keyup is not stopped by the page), record where the cross stands and where it is drawn.
  const R = window.__rainOutlook, map = R.map, cur = R.cross, mc = map.getContainer();
  const ch = document.getElementById('crosshair');
  window.__log = [];
  window.addEventListener('keyup', () => {
    const want = map.latLngToContainerPoint([38 - cur.row * 0.25, 65 + cur.col * 0.25]);
    const r = ch.getBoundingClientRect(), m = mc.getBoundingClientRect(), size = map.getSize();
    const x = r.left + r.width / 2 - m.left, y = r.top + r.height / 2 - m.top;
    window.__log.push([cur.row, cur.col, +Math.hypot(x - want.x, y - want.y).toFixed(2),
                       x >= 0 && y >= 0 && x <= size.x && y <= size.y && !ch.hidden ? 1 : 0, map.getCenter().lat, map.getCenter().lng]);
  }, true);
  return true;
})()
"""


def _walk(b):
    """Snake walk over every grid point with REAL key events; returns (visited, failures, enters, max_err)."""
    b.js(RECORDER_JS)
    b.js("document.querySelector('#map').focus()")
    for _ in range(14):                                       # Shift+arrows to the north-west corner (row 0, col 0)
        b.key("ArrowUp", shift=True); b.key("ArrowLeft", shift=True)
    b.js("window.__log = []")
    if b.js("[window.__rainOutlook.cross.row, window.__rainOutlook.cross.col]") != [0, 0]:
        return 0, ["did not reach 0,0"], 0, 0
    fails, enters, max_err, visited = [], 0, 0.0, 1
    expect = [(0, 0)]
    for row in range(133):
        right = row % 2 == 0
        for k in range(140):
            b.key("ArrowRight" if right else "ArrowLeft")
            expect.append((row, k + 1 if right else 139 - k))
        if row < 132:
            b.key("ArrowDown")
            expect.append((row + 1, 140 if right else 0))
        if row % 12 == 0:                                     # Enter selects exactly the cross's grid point
            r_, c_ = expect[-1]
            b.key("Enter")
            enters += 1
            t = b.js("document.getElementById('point-title').textContent")
            want = f"{38 - r_ * 0.25:.2f}°N, {65 + c_ * 0.25:.2f}°E"
            if want not in t:
                fails.append(f"Enter at {r_},{c_}: {t}")
    log = b.js("window.__log")
    # positions after each key press, consecutive repeats removed (Enter does not move the cross)
    path = [(0, 0)]
    for entry in log:
        rc = (entry[0], entry[1])
        if rc != path[-1]:
            path.append(rc)
        max_err = max(max_err, entry[2])
        if entry[2] > 0.5 or not entry[3]:
            fails.append(f"{rc}: err {entry[2]} px, visible {entry[3]}")
    if path != expect:
        k = next((i for i, (a_, b_) in enumerate(zip(path, expect)) if a_ != b_), min(len(path), len(expect)))
        fails.append(f"path differs from the expected one-step path at step {k}: got {path[k:k+3]}, want {expect[k:k+3]}")
    seen = set(path)
    one_step = all(abs(a_[0] - b_[0]) + abs(a_[1] - b_[1]) == 1 for a_, b_ in zip(path, path[1:]))
    if not one_step:
        fails.append("some key press moved the cross by more than one grid point")
    return len(seen), fails, enters, max_err


def keys():
    httpd, port = s.serve()
    ok = True
    base = f"http://127.0.0.1:{port}/index.html?api=off"
    try:
        for (w, h, mobile) in ((1440, 900, False), (390, 844, True)):
            for z in (None, 7):
                with Browser(w, h, mobile=mobile) as b:
                    b.open(f"{base}#mode=24h&fill=rain&t=0" + (f"&z={z}&c=20,80" if z else ""))
                    zoom = b.js("window.__rainOutlook.map.getZoom()")
                    visited, fails, enters, max_err = _walk(b)
                    good = visited == 133 * 141 and not fails
                    print(f"{'PASS' if good else 'FAIL'}  real-key walk {w}x{h} zoom {zoom}: {visited} grid points, "
                          f"Enter at {enters}, failures {len(fails)}, max position error {max_err} px"
                          + (f"  {fails[:4]}" if fails else ""))
                    ok &= good

        def cross(b):
            return tuple(b.js("[window.__rainOutlook.cross.row, window.__rainOutlook.cross.col]"))

        def one_step_east(b, label, row, col):
            """After a selection at (row, col): one real ArrowRight -> exactly (row, col + 1), one grid point east."""
            b.js("document.querySelector('#map').focus()")
            c0 = b.js("[window.__rainOutlook.map.getCenter().lat, window.__rainOutlook.map.getCenter().lng]")
            b.key("ArrowRight")
            got = cross(b)
            readout = b.js("document.getElementById('cross-readout').textContent")
            want = (row, col + 1)
            good = got == want and readout.startswith(f"{38 - row * 0.25:.2f}°N {65 + (col + 1) * 0.25:.2f}°E")
            print(f"{'PASS' if good else 'FAIL'}  {label}: selected {row},{col} -> ArrowRight -> cross {got} "
                  f"(want {want}); readout '{readout}'")
            return good

        for (w, h, mobile) in ((1440, 900, False), (390, 844, True)):
            for z in (5, 7):
                with Browser(w, h, mobile=mobile) as b:
                    b.open(f"{base}#mode=24h&fill=rain&t=0&z={z}&c=15,82")
                    # keyboard first (moves the cursor somewhere), THEN a real mouse click elsewhere, then an arrow
                    b.js("document.querySelector('#map').focus()")
                    for _ in range(3):
                        b.key("ArrowLeft", shift=True)
                    m = b.js("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
                    x, y = m[0] + m[2] * 0.62, m[1] + m[3] * 0.38
                    for t_ in ("mousePressed", "mouseReleased"):
                        b.call("Input.dispatchMouseEvent", type=t_, x=x, y=y, button="left", clickCount=1)
                    b.wait("/^-?\\d/.test(document.body.dataset.point || '') || document.body.dataset.point === 'loading'")
                    pt = b.js("document.getElementById('point-title').textContent")
                    lat, lon = [float(v[:-2]) for v in pt.replace("Grid point ", "").split(", ")]
                    row, col = round((38 - lat) / 0.25), round((lon - 65) / 0.25)
                    ok &= one_step_east(b, f"{w}x{h} z{z} keyboard, then mouse click, then arrow", row, col)
        with Browser(1440, 900) as b:
            b.open(f"{base}#mode=24h&fill=rain&t=0&p=13.00,80.25")
            ok &= one_step_east(b, "p=13.00,80.25 link, then arrow", 100, 61)
        with Browser(1440, 900) as b:
            b.open(f"{base}#mode=24h&fill=rain&t=0")
            b.js("document.getElementById('place-q').focus()")
            b.type("madras")
            b.wait("!document.getElementById('place-list').hidden")
            b.key("Enter")
            b.wait("(document.getElementById('point-title').textContent || '').includes('13.00')")
            ok &= one_step_east(b, "search 'madras' (Chennai), then arrow", 100, 61)
        # +/- with real keys: same grid point, same screen spot
        with Browser(1440, 900) as b:
            b.open(f"{base}#mode=24h&fill=rain&t=0&z=6&c=13,80.25")
            b.js("document.querySelector('#map').focus()")
            b.key("ArrowRight")
            st = lambda: b.js("(() => { const R = window.__rainOutlook, r = document.getElementById('crosshair').getBoundingClientRect(); return [R.cross.row, R.cross.col, R.map.getZoom(), r.left + r.width/2, r.top + r.height/2]; })()")
            a, _ = st(), b.key("+")
            z1 = st()
            b.key("-"); z2 = st()
            good = z1[2] > a[2] > z2[2] - 0.01 and z1[:2] == a[:2] == z2[:2] and abs(z1[3] - a[3]) <= 1 and abs(z1[4] - a[4]) <= 1
            print(f"{'PASS' if good else 'FAIL'}  real +/-: zoom {a[2]} -> {z1[2]} -> {z2[2]}, cross stays at {a[:2]}, "
                  f"screen moved {abs(z1[3]-a[3]):.1f},{abs(z1[4]-a[4]):.1f} px")
            ok &= good
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if {"search": search, "keys": keys}[sys.argv[1]]() else 1)
