"""DEV-ONLY: drive headless Chrome over the DevTools protocol with a REAL clock.

Chrome's --dump-dom/--screenshot modes run on a simulated clock: timeouts, streamed downloads and key handling then
behave differently from a real browser (seen in M7/M7b). This helper sends real key events (Input.dispatchKeyEvent),
evaluates JavaScript and takes screenshots in a normal-speed page.

    with Browser(width=1440, height=900) as b:
        b.open("http://127.0.0.1:8000/#...", until="document.body.dataset.status === 'ready'")
        b.key("ArrowDown"); b.type("chen"); b.js("document.title")
"""
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
KEYS = {  # key -> (code, windowsVirtualKeyCode)
    "ArrowUp": ("ArrowUp", 38), "ArrowDown": ("ArrowDown", 40), "ArrowLeft": ("ArrowLeft", 37),
    "ArrowRight": ("ArrowRight", 39), "Enter": ("Enter", 13), "Escape": ("Escape", 27), "Tab": ("Tab", 9),
    " ": ("Space", 32), "+": ("Equal", 187), "-": ("Minus", 189),
}


class Browser:
    def __init__(self, width=1440, height=900, port=9340, mobile=False):
        self.width, self.height, self.port, self.mobile, self.n = width, height, port, mobile, 0

    def __enter__(self):
        self.proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={self.port}",
                                      f"--user-data-dir={tempfile.mkdtemp()}", "--hide-scrollbars",
                                      f"--window-size={self.width},{self.height}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json").read())
                break
            except Exception:
                time.sleep(0.1)
        self.ws = websocket.create_connection(next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"])
        # exact CSS viewport (also below Chrome's minimum window width, e.g. phones)
        self.call("Emulation.setDeviceMetricsOverride", width=self.width, height=self.height,
                  deviceScaleFactor=1, mobile=self.mobile)
        return self

    def __exit__(self, *exc):
        self.proc.kill()

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
        return r["result"].get("value")

    def wait(self, expr, timeout=20.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.js(expr):
                return time.time() - t0
            time.sleep(0.05)
        raise TimeoutError(expr)

    def open(self, url, until="document.body && document.body.dataset.status === 'ready'", timeout=30.0):
        self.call("Page.navigate", url="about:blank")
        self.call("Page.navigate", url=url)
        return self.wait(until, timeout)

    def key(self, key, shift=False, alt=False):
        code, vk = KEYS[key] if key in KEYS else (f"Key{key.upper()}", ord(key.upper()))
        mods = (8 if shift else 0) | (1 if alt else 0)
        text = key if len(key) == 1 else ("\r" if key == "Enter" else "")
        self.call("Input.dispatchKeyEvent", type="keyDown", key=key, code=code, windowsVirtualKeyCode=vk,
                  modifiers=mods, text=text)
        self.call("Input.dispatchKeyEvent", type="keyUp", key=key, code=code, windowsVirtualKeyCode=vk, modifiers=mods)

    def type(self, text):
        self.call("Input.insertText", text=text)

    def screenshot(self, path):
        data = self.call("Page.captureScreenshot", format="png")["data"]
        open(path, "wb").write(base64.b64decode(data))
        return path
