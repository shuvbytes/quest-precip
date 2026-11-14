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


if __name__ == "__main__":
    sys.exit(0 if {"search": search}[sys.argv[1]]() else 1)
