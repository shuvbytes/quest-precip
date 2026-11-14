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


LAYOUT_JS = r"""
(() => {
  const vw = innerWidth, vh = innerHeight, de = document.documentElement;
  const R = (sel) => { const e = typeof sel === 'string' ? document.querySelector(sel) : sel;
    if (!e || e.offsetParent === null && getComputedStyle(e).position !== 'fixed') return null;
    const r = e.getBoundingClientRect(); return r.width && r.height ? [r.left, r.top, r.right, r.bottom] : null; };
  // inside the viewport AND at least 30 px tall (a squeezed 2 px control is not usable)
  const inView = (r, minH = 0) => r && r[0] >= 0 && r[1] >= 0 && r[2] <= vw + 0.5 && r[3] <= vh + 0.5 && r[3] - r[1] >= minH;
  const overlap = (a, b) => a && b && a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
  const map = window.__rainOutlook.map, mapR = R('#map');
  const b = map.getBounds(), img = [[4.875, 64.875], [38.125, 100.125]];
  const fits = b.getSouth() <= img[0][0] + 0.3 && b.getNorth() >= img[1][0] - 0.3 && b.getWest() <= img[0][1] + 0.3 && b.getEast() >= img[1][1] - 0.3;
  const showing = R('#showing span'), zoomCtl = R('.leaflet-control-zoom');
  const edges = [...document.querySelectorAll('.edge-label span')].map(R).filter(Boolean);
  const noteOnMap = R('#zoom-note'), noteInline = R('#zoom-note-inline');
  const sum = R('#about > summary');
  return {
    vw, vh, pageScrollY: de.scrollHeight - vh, hscroll: de.scrollWidth > vw,
    header: Math.round(R('header').at(3) - R('header')[1]), footer: R('#foot') ? Math.round(R('#foot')[3] - R('#foot')[1]) : 0,
    mapH: Math.round(mapR[3] - mapR[1]), mapW: Math.round(mapR[2] - mapR[0]), zoom: map.getZoom(), regionFits: fits,
    sliderInView: inView(R('#t'), 10), modeInView: inView(R('.seg'), 30), searchInView: inView(R('#place-q'), 24),
    timeButtonsInView: inView(R('#next'), 30), thresholdInView: inView(R('#x'), 20),
    showingVsZoom: overlap(showing, zoomCtl), showingVsEdge: edges.some((e) => overlap(showing, e)),
    edgeLabels: edges.length, noteOnMapShown: !!noteOnMap, noteInlineShown: !!noteInline,
    aboutSummaryShown: !!sum, aboutSummaryInView: inView(sum),
  };
})()
"""


def layout():
    httpd, port = s.serve()
    ok = True
    sizes = [("landscape", 844, 390, True), ("landscape-small", 667, 375, True), ("landscape-large", 932, 430, True),
             ("portrait", 390, 844, True), ("desktop", 1440, 900, False)]
    try:
        for name, w, h, mobile in sizes:
            with Browser(w, h, mobile=mobile) as b:
                b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=chance&x=10&t=0")
                r = b.js(LAYOUT_JS)
                land = h <= 560 and w / h >= 4 / 3
                checks = {"no sideways scroll": not r["hscroll"]}
                if land:
                    checks.update({
                        "no page scroll": r["pageScrollY"] <= 1,
                        "map >= 75% of height": r["mapH"] >= 0.75 * h,
                        "region fits in the map": r["regionFits"],
                        "time slider visible without scrolling": r["sliderInView"],
                        "mode buttons visible (>= 30 px tall)": r["modeInView"],
                        "time buttons visible": r["timeButtonsInView"],
                        "search visible": r["searchInView"],
                        "zoom note not on the map (in the panel)": not r["noteOnMapShown"] and r["noteInlineShown"],
                        "'Showing' clear of zoom buttons and edge labels": not r["showingVsZoom"] and not r["showingVsEdge"],
                        "short footer line + 'About & sources' visible": r["aboutSummaryInView"],
                    })
                elif w <= 700 or h <= 560:
                    checks.update({"map as before (62% of height)": r["mapH"] >= 0.6 * h,
                                   "'About & sources' line shown": r["aboutSummaryShown"],
                                   "'Showing' clear of zoom buttons": not r["showingVsZoom"]})
                else:
                    checks.update({"full attribution (no summary line)": not r["aboutSummaryShown"],
                                   "zoom note on the map as before": r["noteOnMapShown"]})
                if land:   # threshold: in view, or reachable by scrolling the side panel only (page stays put)
                    reach = b.js("""(() => { const x = document.getElementById('x'); x.scrollIntoView({block: 'nearest'});
                      const r = x.getBoundingClientRect(), p = document.documentElement.scrollHeight - innerHeight;
                      const ok = r.top >= 0 && r.bottom <= innerHeight && window.scrollY === 0;
                      document.getElementById('panel').scrollTop = 0; return ok; })()""")
                    checks["threshold reachable by scrolling the panel only"] = reach
                # About & sources: open, read, close (small screens)
                if r["aboutSummaryShown"]:
                    b.js("document.querySelector('#about > summary').scrollIntoView(); document.querySelector('#about > summary').click()")
                    sheet = b.js("(() => { const e = document.querySelector('.about-body'); const r = e.getBoundingClientRect(); return [document.getElementById('about').open, Math.round(r.top), Math.round(r.height), e.textContent.includes('CC BY 4.0') && e.textContent.includes('DataMeet') && e.textContent.includes('Natural Earth')]; })()")
                    b.screenshot(s.OUT / f"m8d_{name}_about.png")
                    b.js("document.querySelector('.about-close').click()")
                    closed = not b.js("document.getElementById('about').open")
                    checks["About opens (full credits) and Close closes it"] = sheet[0] and sheet[3] and closed
                    b.js("window.scrollTo(0, 0)")
                b.screenshot(s.OUT / f"m8d_{name}.png")
                # tap a point: the panel shows it
                m = b.js("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left + r.width * 0.55, r.top + r.height * 0.6]; })()")
                for t_ in ("mousePressed", "mouseReleased"):
                    b.call("Input.dispatchMouseEvent", type=t_, x=m[0], y=m[1], button="left", clickCount=1)
                b.wait("/^-?\\d/.test(document.body.dataset.point || '') || document.body.dataset.point === 'outside'", 20)
                b.js("new Promise(r => setTimeout(r, 600))")
                if land:
                    pt = b.js("(() => { const r = document.getElementById('point-title').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()")
                    checks["after a tap the point panel is in view"] = pt
                    b.screenshot(s.OUT / f"m8d_{name}_point.png")
                good = all(checks.values())
                ok &= good
                print(f"{'PASS' if good else 'FAIL'}  {name} {w}x{h}: header {r['header']} px, map {r['mapW']}x{r['mapH']} px "
                      f"(zoom {r['zoom']}), footer {r['footer']} px, page scroll {r['pageScrollY']} px")
                for k, v in checks.items():
                    if not v:
                        print(f"        FAIL: {k}")
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


def _pose_examples(x="10", t=0):
    """One grid point per pose for the current local build, chosen in Python with the card's rules."""
    import json
    sys.path.insert(0, str(s.ROOT / "api"))
    import pointcore as pc
    m = json.loads((s.SITE / "data" / "manifest.json").read_text())
    a = pc.decode(m, (s.SITE / "data" / "points.bin").read_bytes())
    g = m["grid"]
    k = pc.window_index(m["products"]["hres_24h"]["frames"], t)
    keys = pc.threshold_keys(m)
    found = {}
    for row in range(0, g["nlat"], 2):
        for col in range(0, g["nlon"], 2):
            idx = row * g["nlon"] + col
            if pc.cell_flag(m, x, k, idx):
                pose = "disagree"
            elif a["ens_prob"][keys.index("50"), k, row, col] >= 50:
                pose = "heavy"
            elif a["hres_24h"][k, row, col] >= 1 or a["ens_prob"][keys.index("1"), k, row, col] >= 50:
                pose = "light"
            else:
                pose = "dry"
            found.setdefault(pose, (g["lat_north"] - row * g["dlat"], g["lon_west"] + col * g["dlon"]))
    return found


def card():
    httpd, port = s.serve()
    ok = True
    base = f"http://127.0.0.1:{port}/index.html?api=off"
    try:
        for t in (0, 48, 96):
            ex = _pose_examples("10", t)
            print(f"t={t}: pose examples {ex}")
            for pose, (lat, lon) in ex.items():
                with Browser(1440, 900) as b:
                    b.open(f"{base}#mode=24h&fill=chance&x=10&t={t}&p={lat:.2f},{lon:.2f}")
                    b.wait("!document.getElementById('pcard').hidden", 20)
                    r = b.js("""(() => { const c = document.getElementById('pcard'), f = (n) => (document.querySelector(`[data-field="${n}"]`) || {}).textContent;
                      const map = window.__rainOutlook.map, app = window.__rainOutlook.app, pt = map.latLngToContainerPoint([app.point.lat, app.point.lon]);
                      const cr = c.getBoundingClientRect(), mr = document.getElementById('map').getBoundingClientRect();
                      const px = pt.x + mr.left, py = pt.y + mr.top;
                      return {pose: c.dataset.pose, near: f('card-near') === f('near'), main: f('card-main') === f('sum-24h'),
                        chip: (f('card-chip') || '').replace(/\u00a0/g, ' ').endsWith((f('sum-ens') || '').split(': ').pop()), badge: !!c.querySelector('.pc-badge'),
                        panelDisagree: !!document.querySelector('[data-field=disagree]'),
                        alt: c.querySelector('.pc-guide svg') ? c.querySelector('.pc-guide svg').getAttribute('aria-label') : 'guide hidden',   // the guide's alt text (not the decorative key icons)
                        onScreen: cr.left >= mr.left && cr.right <= mr.right + 1 && cr.top >= mr.top && cr.bottom <= mr.bottom + 1,
                        coversPoint: px >= cr.left && px <= cr.right && py >= cr.top && py <= cr.bottom,
                        main_text: f('card-main'), chip_text: f('card-chip')}; })()""")
                    good = (r["pose"] == pose and r["near"] and r["main"] and r["chip"] and r["badge"] == r["panelDisagree"]
                            and bool(r["alt"]) and r["onScreen"] and not r["coversPoint"])
                    print(f"  {'PASS' if good else 'FAIL'}  {pose:8s} at {lat:.2f},{lon:.2f}: card pose {r['pose']}; '{r['main_text']}' | "
                          f"'{r['chip_text']}' | badge {r['badge']} (panel sentence {r['panelDisagree']}); on screen {r['onScreen']}, "
                          f"covers point {r['coversPoint']}")
                    if pose == "disagree" and t == 0:
                        b.screenshot(s.OUT / "m8c_card_disagree.png")
                    if pose == "heavy" and t == 0:
                        b.screenshot(s.OUT / "m8c_card_heavy.png")
                    ok &= good
        # behaviour: Esc order, x, Full details, guide toggle (persisted), phone sheet
        with Browser(1440, 900) as b:
            b.open(f"{base}#mode=24h&fill=chance&x=10&t=0&p=13.00,80.25")
            b.wait("!document.getElementById('pcard').hidden", 20)
            b.key("Escape")
            e1 = b.js("[document.getElementById('pcard').hidden, document.getElementById('point').hidden]")
            b.key("Escape")
            e2 = b.js("[document.getElementById('pcard').hidden, document.getElementById('point').hidden]")
            res = [("Esc closes the card first, then the panel", e1 == [True, False] and e2 == [True, True])]
            b.open(f"{base}#mode=24h&fill=chance&x=10&t=0&p=13.00,80.25")
            b.wait("!document.getElementById('pcard').hidden", 20)
            b.js("document.querySelector('.pc-close').click()")
            res.append(("x closes the card, panel stays", b.js("[document.getElementById('pcard').hidden, document.getElementById('point').hidden]") == [True, False]))
            b.open(f"{base}#mode=24h&fill=chance&x=10&t=0&p=13.00,80.25")
            b.wait("!document.getElementById('pcard').hidden", 20)
            more = lambda: b.js("!document.querySelector('.pc-more').hidden")
            res.append(("desktop, details in view: no 'Full details' button", not more()))
            b.js("document.getElementById('panel').scrollTop = 1e6")
            b.js("new Promise(r => setTimeout(r, 100))")
            shown = more()
            b.js("document.querySelector('.pc-more').click()")
            b.js("new Promise(r => setTimeout(r, 600))")
            res.append(("desktop, side panel scrolled away: button shown; click closes the card and focuses the panel title",
                        shown and b.js("document.activeElement.id") == "point-title" and b.js("document.getElementById('pcard').hidden")))
            b.js("document.getElementById('guide').click()")
            b.open(f"{base}#mode=24h&fill=chance&x=10&t=0&p=13.00,80.25")
            b.wait("!document.getElementById('pcard').hidden", 20)
            res.append(("guide toggle hides the character (also after reload)", b.js("!document.querySelector('#pcard .pc-guide') && !document.getElementById('guide').checked && !!document.querySelector('#pcard .skies svg')")))
            b.js("document.getElementById('guide').click()")
            b.js("new Promise(r => setTimeout(r, 100))")
            res.append(("toggle on again shows it", b.js("!!document.querySelector('#pcard .pc-guide svg')")))
        with Browser(390, 844, mobile=True) as b:
            b.open(f"{base}#mode=24h&fill=chance&x=10&t=0&p=13.00,80.25")
            b.wait("!document.getElementById('pcard').hidden", 20)
            sheet = b.js("(() => { const r = document.getElementById('pcard').getBoundingClientRect(); return [document.getElementById('pcard').classList.contains('sheet'), Math.round(r.bottom), innerHeight, Math.round(r.width)]; })()")
            b.screenshot(s.OUT / "m8c_card_phone.png")
            res.append(("phone: bottom sheet, full width", sheet[0] and abs(sheet[1] - sheet[2]) <= 1 and sheet[3] == 390))
            res.append(("phone, details below the map: button shown", b.js("!document.querySelector('.pc-more').hidden")))
            b.js("document.querySelector('.pc-more').click()")
            b.js("new Promise(r => setTimeout(r, 900))")
            res.append(("phone: Full details scrolls the details into view", b.js("(() => { const r = document.getElementById('point-title').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()")))
        for name, good in res:
            print(f"{'PASS' if good else 'FAIL'}  {name}")
            ok &= good
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


GLYPH_JS = r"""
(() => {
  // Draw the name's Devanagari part in the page font, and an unassigned code point (U+0378, always the missing-glyph
  // box); if the two pictures are the same, the text would show as boxes.
  const font = getComputedStyle(document.querySelector('.brand-name')).fontFamily;
  const pic = (t) => { const c = document.createElement('canvas'); c.width = 120; c.height = 40; const x = c.getContext('2d');
    x.font = `28px ${font}`; x.fillText(t, 4, 30); return Array.from(x.getImageData(0, 0, 120, 40).data).join(','); };
  const box = pic('͸͸͸'), name = pic('रिश'), ri = pic('रि');
  return { font, differsFromBoxes: name !== box && ri !== pic('͸͸'),
           width: Math.round(document.querySelector('.brand-name').getBoundingClientRect().width) };
})()
"""


def brand():
    httpd, port = s.serve()
    ok = True
    try:
        for name, w, h, mobile in (("desktop", 1440, 900, False), ("portrait", 390, 844, True), ("landscape", 844, 390, True)):
            with Browser(w, h, mobile=mobile) as b:
                b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=rain&t=0")
                g = b.js(GLYPH_JS)
                b.call("Accessibility.enable")             # the heading's name as assistive technology gets it
                nodes = b.call("Accessibility.getFullAXTree")["nodes"]
                heads = [n for n in nodes if n.get("role", {}).get("value") == "heading"]
                acc = heads[0].get("name", {}).get("value") if heads else None
                title = b.js("document.title")
                tag = b.js("(() => { const t = document.querySelector('.tagline'); return t && t.offsetParent ? t.textContent : '(hidden)'; })()")
                good = g["differsFromBoxes"] and acc == "Barish" and title == "Baरिश (Barish) — a second opinion on rain"
                print(f"{'PASS' if good else 'FAIL'}  {name} {w}x{h}: heading read as {acc!r}; Devanagari drawn as real glyphs: "
                      f"{g['differsFromBoxes']}; name width {g['width']} px; subtitle: {tag!r}")
                b.screenshot(s.OUT / f"rename_{name}.png")
                ok &= good
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


def play():
    """Feature 1: real clicks/keys; window label after each step = the manifest's next frame; pauses; reduced motion."""
    import json
    import time
    m = json.loads((s.SITE / "data" / "manifest.json").read_text())
    frames = m["products"]["hres_24h"]["frames"]
    httpd, port = s.serve()
    ok = True
    label = "document.getElementById('t-label').textContent"
    playing = "document.body.dataset.playing"
    def click_el(b, sel):
        x, y = b.js(f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; }})()")
        for t_ in ("mousePressed", "mouseReleased"):
            b.call("Input.dispatchMouseEvent", type=t_, x=x, y=y, button="left", clickCount=1)
    try:
        res = []
        with Browser(1440, 900) as b:
            b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=rain&t=96")
            l0 = b.js(label)
            time.sleep(3)
            res.append(("no autoplay: nothing moves in 3 s", b.js(label) == l0 and b.js(playing) == "0"))
            click_el(b, "#play")
            t0 = time.time()
            seen = []
            for k in range(3):
                time.sleep(max(0, t0 + 1.05 * (k + 1) + 0.15 - time.time()))
                seen.append(b.js(label))
            want = [frames[9]["label_ist"], frames[10]["label_ist"], frames[0]["label_ist"]]   # 96 h -> 108, 120, loop to 0
            res.append((f"steps ~1/s through the manifest frames and loops (got {seen})", seen == want))
            res.append(("button shows pause, aria-pressed true", b.js("[document.getElementById('play').textContent, document.getElementById('play').getAttribute('aria-pressed')]") == ["❚❚", "true"]))
            x, y = b.js("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left + 300, r.top + 300]; })()")
            b.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
            b.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
            l1 = b.js(label); time.sleep(2.2)
            res.append(("a click on the map pauses it", b.js(playing) == "0" and b.js(label) == l1))
            b.js("document.getElementById('play').focus()")
            b.key(" ")
            time.sleep(1.3)
            on = b.js(playing) == "1"
            b.key(" ")
            l2 = b.js(label); time.sleep(1.5)
            res.append(("keyboard: Space on the button plays, Space again pauses", on and b.js(playing) == "0" and b.js(label) == l2))
            click_el(b, "#play"); time.sleep(0.3)
            b.js("document.getElementById('x').focus()")
            b.key("ArrowDown")
            l3 = b.js(label); time.sleep(1.5)
            res.append(("any other key pauses it", b.js(playing) == "0" and b.js(label) == l3))
            click_el(b, "#play"); time.sleep(0.3)
            click_el(b, "#next")
            l4 = b.js(label); time.sleep(1.5)
            res.append(("pressing › pauses it (and still steps once)", b.js(playing) == "0" and b.js(label) == l4))
        with Browser(1440, 900) as b:
            b.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
            b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=rain&t=0")
            l0 = b.js(label)
            time.sleep(3)
            still = b.js(label) == l0
            click_el(b, "#play"); t0 = time.time()
            time.sleep(max(0, t0 + 1.4 - time.time())); a = b.js(label)
            time.sleep(max(0, t0 + 2.4 - time.time())); c = b.js(label)
            res.append(("reduced motion: no autoplay; steps every 2 s, not 1 s", still and a == frames[0]["label_ist"] and c == frames[1]["label_ist"]))
        for name, w, h in (("portrait", 390, 844), ("landscape", 844, 390)):
            with Browser(w, h, mobile=True) as b:
                b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=rain&t=0")
                b.js("document.getElementById('play').scrollIntoView({block: 'center'})")
                r = b.js("(() => { const r = document.getElementById('play').getBoundingClientRect(); return [r.width, r.height, r.right <= innerWidth, document.documentElement.scrollWidth > innerWidth]; })()")
                click_el(b, "#play"); time.sleep(2.3)
                moved = b.js(label) == frames[2]["label_ist"]
                b.screenshot(s.OUT / f"play_{name}.png")
                res.append((f"{name}: button {r[0]:.0f}x{r[1]:.0f} px on screen, no sideways scroll, plays", r[2] and not r[3] and moved and r[1] >= 34))
        for name, good in res:
            print(f"{'PASS' if good else 'FAIL'}  {name}")
            ok &= good
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


def skies():
    """Feature 2: open umbrellas == the chip's whole % == the panel's ENS value; edge cases; phone sheet fits."""
    import json
    sys.path.insert(0, str(s.ROOT / "api"))
    import pointcore as pc
    m = json.loads((s.SITE / "data" / "manifest.json").read_text())
    a = pc.decode(m, (s.SITE / "data" / "points.bin").read_bytes())
    g = m["grid"]
    x, t = "10", 0
    kx = pc.threshold_keys(m).index(x)
    k = pc.window_index(m["products"]["hres_24h"]["frames"], t)
    floor = m["products"]["ens_prob"]["frames_by_threshold"][x][k]["lowest_drawn"]
    want = {0: None, 1: None, 2: None, 37: None, 50: None, 99: None, 100: None}
    vals = a["ens_prob"][kx, k]
    for target in want:
        rr, cc = (vals == target).nonzero()
        if len(rr):
            i = len(rr) // 2
            want[target] = (g["lat_north"] - rr[i] * g["dlat"], g["lon_west"] + cc[i] * g["dlon"])
    httpd, port = s.serve()
    ok = True
    try:
        for target, ll in want.items():
            if ll is None:
                print(f"skip  {target} %: no grid point with exactly this value in this window")
                continue
            with Browser(1440, 900) as b:
                b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=chance&x={x}&t={t}&p={ll[0]:.2f},{ll[1]:.2f}")
                b.wait("!document.getElementById('pcard').hidden", 20)
                r = b.js("""(() => { const f = document.querySelector('#pcard .skies'), svg = f.querySelector('.skies-grid');
                  const rs = [...svg.querySelectorAll('rect')], bb = svg.getBoundingClientRect(), cell = rs[0].getBoundingClientRect();
                  return {open: rs.filter(q => q.dataset.c === '1').length, total: rs.length, dataOpen: f.dataset.open,
                          cap: f.querySelector('.skies-cap').textContent, key: f.querySelector('.skies-key').textContent.replace(/\u00a0/g, ' '),
                          geo: {cellPx: +cell.width.toFixed(1), gridPx: Math.round(bb.width), spots: new Set(rs.map(q => q.getAttribute('x') + ',' + q.getAttribute('y'))).size},
                          alt: svg.getAttribute('aria-label'), chip: document.querySelector('[data-field=card-chip]').textContent.replace(/\u00a0/g, ' '),
                          panel: document.querySelector('[data-field=sum-ens]').textContent}; })()""")
                shown = r["panel"].split(": ")[-1]                      # e.g. "67 %" or "< 2 %"
                exp_open = 0 if target < floor else target
                exp_say = f"fewer than {pc.js_num(floor)} in 100" if target < floor else f"{target} in 100"
                geo_ok = r["geo"]["spots"] == 100 and r["geo"]["cellPx"] >= 5 and r["key"].startswith(f"≥ {x} mm")   # 10x10, cells >= 5 px
                good = (geo_ok and r["open"] == exp_open and r["total"] == 100 and r["chip"].endswith(shown)
                        and shown == (f"< {pc.js_num(floor)} %" if target < floor else f"{target} %")
                        and r["cap"].startswith(exp_say) and (str(exp_open) in r["alt"] or target < floor) and "member" not in (r["cap"] + r["alt"]).lower())
                print(f"{'PASS' if good else 'FAIL'}  {target:3d} % at {ll[0]:.2f},{ll[1]:.2f}: panel '{shown}', chip '{r['chip'].split(': ')[-1]}', "
                      f"{r['open']} of {r['total']} blue, cells {r['geo']['cellPx']} px in a {r['geo']['gridPx']} px grid; caption '{r['cap']}'")
                if target == 37:
                    print(f"      alt: {r['alt']}")
                    b.screenshot(s.OUT / "skies_desktop.png")
                ok &= good
        mid = want.get(37) or want.get(50)
        for name, w, h in (("portrait", 390, 844), ("landscape", 844, 390)):
            with Browser(w, h, mobile=True) as b:
                b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=chance&x={x}&t={t}&p={mid[0]:.2f},{mid[1]:.2f}")
                b.wait("!document.getElementById('pcard').hidden", 20)
                r = b.js("(() => { const c = document.getElementById('pcard').getBoundingClientRect(); return [Math.round(c.top), Math.round(c.bottom), innerHeight, document.documentElement.scrollWidth > innerWidth]; })()")
                b.screenshot(s.OUT / f"skies_{name}.png")
                good = r[0] >= 0 and r[1] <= r[2] + 1 and not r[3]
                print(f"{'PASS' if good else 'FAIL'}  {name}: card spans y {r[0]}–{r[1]} of {r[2]} px, no sideways scroll")
                ok &= good
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


def _swipe_point(x="10", t=0):
    """A sea grid point far from labels whose HRES 24 h and ENS chance both fall in one visible colour bin over its 3x3
    neighbourhood (so a pixel at its centre has an unambiguous expected colour on each side)."""
    import json
    import numpy as np
    sys.path.insert(0, str(s.ROOT / "api"))
    import pointcore as pc
    from render import classify
    m = json.loads((s.SITE / "data" / "manifest.json").read_text())
    a = pc.decode(m, (s.SITE / "data" / "points.bin").read_bytes())
    P, g = m["products"], m["grid"]
    k = pc.window_index(P["hres_24h"]["frames"], t)
    fr, fe = P["hres_24h"]["frames"][k], P["ens_prob"]["frames_by_threshold"][x][k]
    kx = pc.threshold_keys(m).index(x)
    cr = classify(a["hres_24h"][k], P["hres_24h"]["bins"], fr["lowest_drawn"], len(P["hres_24h"]["colours"]))
    ce = classify(a["ens_prob"][kx, k], P["ens_prob"]["bins"], fe["lowest_drawn"], len(P["ens_prob"]["colours"]))
    places = pc.places_from_json(json.loads((s.SITE / "geo" / "places.json").read_text()))
    best = None
    for r in range(3, g["nlat"] - 3):
        for c in range(3, g["nlon"] - 3):
            br, be = cr[r - 1:r + 2, c - 1:c + 2], ce[r - 1:r + 2, c - 1:c + 2]
            if br.min() == br.max() > 0 and be.min() == be.max() > 0:
                lat, lon = g["lat_north"] - r * g["dlat"], g["lon_west"] + c * g["dlon"]
                if min(pc.distance_km(lat, lon, q["lat"], q["lon"]) for q in places) > 150:
                    best = (lat, lon, P["hres_24h"]["colours"][cr[r, c] - 1], P["ens_prob"]["colours"][ce[r, c] - 1],
                            float(a["hres_24h"][k, r, c]), float(a["ens_prob"][kx, k, r, c]))
                    break
        if best:
            break
    return best


def swipe():
    import time
    from PIL import Image
    httpd, port = s.serve()
    ok = True
    res = []
    pick = _swipe_point()
    lat, lon, col_r, col_e, v_r, v_e = pick
    print(f"test point {lat:.2f}N {lon:.2f}E: HRES {v_r:.1f} mm -> {col_r}; ENS {v_e:.0f} % -> {col_e}")
    hexrgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    def pixel(b, path):
        b.screenshot(path)
        x, y = b.js(f"(() => {{ const p = window.__rainOutlook.map.latLngToContainerPoint([{lat}, {lon}]), r = document.getElementById('map').getBoundingClientRect(); return [r.left + p.x, r.top + p.y]; }})()")
        return Image.open(path).convert("RGB").getpixel((round(x), round(y)))
    close = lambda p, h: max(abs(p[i] - hexrgb(h)[i]) for i in range(3)) <= 6
    base = f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=chance&x=10&t=0&hatch=0&z=7&c={lat},{lon}&cmp=1"
    try:
        with Browser(1440, 900) as b:
            for sw, side, want in ((70, "left", col_r), (30, "right", col_e)):
                b.open(f"{base}&sw={sw}")
                time.sleep(0.5)
                px = pixel(b, s.OUT / f"swipe_pixel_{side}.png")
                res.append((f"divider {sw} %: point is on the {side} -> pixel {px} = {'HRES' if side == 'left' else 'ENS'} colour {want}", close(px, want)))
            # drag with a real mouse: from the handle to 25 % of the map width
            b.open(f"{base}&sw=50")
            hx, hy = b.js("(() => { const r = document.getElementById('swipe-handle').getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; })()")
            mr = b.js("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left, r.width]; })()")
            b.call("Input.dispatchMouseEvent", type="mousePressed", x=hx, y=hy, button="left", clickCount=1)
            for f in (0.45, 0.35, 0.25):
                b.call("Input.dispatchMouseEvent", type="mouseMoved", x=mr[0] + f * mr[1], y=hy, button="left")
            b.call("Input.dispatchMouseEvent", type="mouseReleased", x=mr[0] + 0.25 * mr[1], y=hy, button="left", clickCount=1)
            time.sleep(0.6)
            st = b.js("[+document.getElementById('swipe-handle').getAttribute('aria-valuenow'), document.body.dataset.point || '', location.hash.includes('sw=25')]")
            res.append((f"mouse drag to 25 %: divider {st[0]} %, no point selected, URL has sw=25", st[0] == 25 and st[1] == "" and st[2]))
            px = pixel(b, s.OUT / "swipe_after_drag.png")
            res.append((f"after the drag to 25 % the centred point is on the right side -> ENS colour {px}", close(px, col_e)))
            t0 = b.js("document.getElementById('t-label').textContent")
            b.js("document.getElementById('swipe-handle').focus()")
            vals = []
            for k_, sh in (("ArrowLeft", False), ("ArrowRight", True), ("Home", False), ("End", False)):
                b.key(k_, shift=sh)
                vals.append(int(b.js("document.getElementById('swipe-handle').getAttribute('aria-valuenow')")))
            res.append((f"keyboard: ← -5, Shift+→ +20, Home, End -> {vals}; time window unchanged",
                        vals == [20, 40, 5, 95] and b.js("document.getElementById('t-label').textContent") == t0))
            # map click still selects a point; hatching unclipped on both sides
            b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=chance&x=100&t=96&hatch=1&cmp=1&sw=50")
            hatch = b.js("(() => { const i = [...document.querySelectorAll('.leaflet-hatch-pane img')].find(e => e.src.includes('disagree')); if (!i) return null; const r = i.getBoundingClientRect(), x = +document.getElementById('map').dataset.swipe + document.getElementById('map').getBoundingClientRect().left; return [i.style.clipPath || '', r.left < x && r.right > x]; })()")
            res.append((f"hatching drawn across the divider, not clipped: {hatch}", bool(hatch) and hatch[0] == "" and hatch[1]))
            mx, my = b.js("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left + r.width * 0.7, r.top + r.height * 0.7]; })()")
            for t_ in ("mousePressed", "mouseReleased"):
                b.call("Input.dispatchMouseEvent", type=t_, x=mx, y=my, button="left", clickCount=1)
            b.wait("/^-?\\d/.test(document.body.dataset.point || '') || document.body.dataset.point === 'outside' || document.body.dataset.point === 'loading'", 10)
            res.append(("a map click still selects a point in compare mode", bool(b.js("document.body.dataset.point"))))
            b.screenshot(s.OUT / "swipe_desktop.png")
            # turning compare off restores the normal map
            b.js("document.getElementById('cmp').click()")
            time.sleep(0.3)
            off = b.js("[document.getElementById('swipe').hidden, document.querySelectorAll('.leaflet-fill2-pane img').length, (document.querySelector('.leaflet-fill-pane img') || {style: {}}).style.clipPath || '']")
            res.append((f"toggle off: divider hidden, right image removed, no clipping: {off}", off[0] and off[1] == 0 and off[2] == ""))
        for name, w, h in (("portrait", 390, 844), ("landscape", 844, 390)):
            with Browser(w, h, mobile=True) as b:
                b.call("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=1)
                b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=chance&x=10&t=0&cmp=1&sw=50")
                hx, hy = b.js("(() => { const r = document.getElementById('swipe-handle').getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; })()")
                mr = b.js("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left, r.width]; })()")
                b.call("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": hx, "y": hy}])
                for f in (0.6, 0.7, 0.75):
                    b.call("Input.dispatchTouchEvent", type="touchMove", touchPoints=[{"x": mr[0] + f * mr[1], "y": hy}])
                b.call("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
                time.sleep(0.4)
                v = int(b.js("document.getElementById('swipe-handle').getAttribute('aria-valuenow')"))
                lab = b.js("(() => { const a = document.getElementById('swipe-left').getBoundingClientRect(), c = document.getElementById('swipe-right').getBoundingClientRect(), m = document.getElementById('map').getBoundingClientRect(); return [a.left >= m.left - 1 && c.right <= m.right + 1, a.right <= c.left + 1 || a.top >= c.bottom - 1, document.documentElement.scrollWidth > innerWidth]; })()")
                b.screenshot(s.OUT / f"swipe_{name}.png")
                res.append((f"{name}: touch drag -> divider {v} %, both labels inside the map and not overlapping, no sideways scroll",
                            v == 75 and lab[0] and lab[1] and not lab[2]))
        for name, good in res:
            print(f"{'PASS' if good else 'FAIL'}  {name}")
            ok &= good
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


def story():
    """Feature 5: each step's state, flight, selected point and caption numbers == panel; keyboard; Esc; phones."""
    import json
    import time
    m = json.loads((s.SITE / "data" / "manifest.json").read_text())
    hs = m["highlights"]
    httpd, port = s.serve()
    ok = True
    res = []
    def click(b, sel):
        x, y = b.js(f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; }})()")
        for t_ in ("mousePressed", "mouseReleased"):
            b.call("Input.dispatchMouseEvent", type=t_, x=x, y=y, button="left", clickCount=1)
    def check_step(b, i, label):
        h = hs[i]
        b.wait(f"document.body.dataset.story === '{i}' && !/^…$/.test(document.getElementById('story-cap').textContent) && !!document.querySelector('[data-field=story-mm], [data-field=story-pct]')", 30)
        time.sleep(1.4)                                         # let the flight end
        r = b.js("""(() => { const f = (n) => (document.querySelector(`[data-field="${n}"]`) || {}).textContent || null;
          const map = window.__rainOutlook.map, c = map.getCenter(), sz = map.getSize();
          const pp = map.latLngToContainerPoint([+document.body.dataset.point.split(',')[0], +document.body.dataset.point.split(',')[1]]);
          const inView = pp.x > 30 && pp.y > 30 && pp.x < sz.x - 30 && pp.y < sz.y - 30;   // near the region edge the map cannot centre it
          return {point: document.body.dataset.point, x: document.getElementById('x').value, t: document.getElementById('t-label').textContent,
            mode: document.querySelector('[data-mode][aria-pressed=true]').dataset.mode, fill: document.querySelector('[data-fill][aria-pressed=true]').dataset.fill,
            mm: f('story-mm'), pct: f('story-pct'), panelMm: f('sum-24h'), panelPct: f('sum-ens'), cap: document.getElementById('story-cap').textContent,
            step: document.getElementById('story-step').textContent, lat: c.lat, lon: c.lng, inView, card: document.getElementById('pcard').hidden}; })()""")
        want_t = m["products"]["hres_24h"]["frames"][h["window"]]["label_ist"]
        good = (r["point"] == f"{h['lat']:.2f},{h['lon']:.2f}" and r["x"] == h["x"] and r["t"] == want_t and r["mode"] == "24h"
                and r["fill"] == h["fill"] and r["inView"] and r["card"]
                and (r["mm"] is None or r["panelMm"].endswith(": " + r["mm"])) and (r["pct"] is None or r["panelPct"].endswith(": " + r["pct"]))
                and not any(w in r["cap"].lower() for w in ("wrong", "error", "incorrect", "mistake")))
        res.append((f"{label} step {i + 1} ({h['rule']}): point {r['point']}, x {r['x']}, {r['fill']}, point in view; caption numbers "
                    f"{r['mm']} / {r['pct']} = panel; '{r['cap'][:110]}…'", good))
    try:
        with Browser(1440, 900) as b:
            b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=3h&t=33")
            click(b, "#story-open")
            check_step(b, 0, "desktop")
            b.screenshot(s.OUT / "story_step1.png")
            for i in range(1, len(hs)):
                click(b, "#story-next")
                check_step(b, i, "desktop")
                b.screenshot(s.OUT / f"story_step{i + 1}.png")
            click(b, "#story-back")
            check_step(b, len(hs) - 2, "Back:")
            b.key("Escape")
            st = b.js("[document.getElementById('story').hidden, document.body.dataset.story, !document.getElementById('pcard').hidden]")
            res.append(("Esc leaves the story; the point card comes back", st[0] and st[1] == "" and st[2]))
            # keyboard only: Tab-focus the button, Enter, Enter... until Finish
            b.js("document.getElementById('story-open').focus()")
            b.key("Enter")
            check_step(b, 0, "keyboard")
            for i in range(1, len(hs)):
                b.key("Enter")                                     # focus sits on Next after opening
                check_step(b, i, "keyboard")
            b.key("Enter")                                         # Finish
            res.append(("keyboard: Enter on Next steps through, Finish closes", b.js("document.getElementById('story').hidden")))
        for name, w, h_ in (("portrait", 390, 844), ("landscape", 844, 390)):
            with Browser(w, h_, mobile=True) as b:
                b.open(f"http://127.0.0.1:{port}/index.html?api=off#mode=24h&fill=rain&t=0")
                b.js("document.getElementById('story-open').scrollIntoView({block: 'center'})")
                click(b, "#story-open")
                check_step(b, 0, name)
                b.js("document.getElementById('map').scrollIntoView({block: 'start'})")
                time.sleep(0.3)
                inside = b.js("(() => { const a = document.getElementById('story').getBoundingClientRect(), m = document.getElementById('map').getBoundingClientRect(); return [a.left >= m.left - 1, a.right <= m.right + 1, a.bottom <= m.bottom + 1, a.top >= m.top, document.documentElement.scrollWidth > innerWidth, Math.round(a.height)]; })()")
                b.screenshot(s.OUT / f"story_{name}.png")
                res.append((f"{name}: story bar inside the map ({inside[5]} px tall), no sideways scroll", all(inside[:4]) and not inside[4]))
        for name, good in res:
            print(f"{'PASS' if good else 'FAIL'}  {name}")
            ok &= good
    finally:
        httpd.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if {"search": search, "keys": keys, "layout": layout, "card": card, "brand": brand, "play": play, "skies": skies, "swipe": swipe, "story": story}[sys.argv[1]]() else 1)
