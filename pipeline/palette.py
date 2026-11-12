"""Sequential colour scales for the maps, built so adjacent bins are measurably distinct.

Rule (dataviz skill): magnitude = one hue, light -> dark, lightness monotone. Steps are evenly
spaced in OKLCH lightness, and we check the OKLab distance between neighbouring steps instead
of judging by eye. Rain amounts use blue, probabilities magenta, so the two layers never share colours.
"""
from __future__ import annotations

import numpy as np


# ---- OKLab / OKLCH <-> sRGB (Björn Ottosson's reference matrices) ----

def _lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def _srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4))


def oklab_to_linrgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return np.array([
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    ])


def srgb_to_oklab(rgb):
    r, g, b = _srgb_to_lin(np.asarray(rgb, float))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    return np.array([
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    ])


def oklch_to_hex(L, C, h_deg):
    """OKLCH -> hex, reducing chroma until the colour fits in sRGB."""
    h = np.radians(h_deg)
    while C > 0:
        rgb = oklab_to_linrgb(L, C * np.cos(h), C * np.sin(h))
        if (rgb >= -1e-4).all() and (rgb <= 1 + 1e-4).all():
            break
        C -= 0.002
    srgb = _lin_to_srgb(oklab_to_linrgb(L, max(C, 0) * np.cos(h), max(C, 0) * np.sin(h)))
    return "#" + "".join(f"{int(round(v * 255)):02x}" for v in srgb)


def hex_to_oklab(hx):
    return srgb_to_oklab([int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)])


def ramp(n, hue, L_light=0.92, L_dark=0.30, C_max=0.16):
    """n steps, lightness evenly spaced; chroma peaks mid-ramp (pale and dark ends carry less)."""
    Ls = np.linspace(L_light, L_dark, n)
    t = np.linspace(0, 1, n)
    Cs = C_max * (0.45 + 0.55 * np.sin(np.pi * np.clip(t * 0.85 + 0.15, 0, 1)))
    return [oklch_to_hex(L, C, hue) for L, C in zip(Ls, Cs)]


def adjacent_delta_e(hexes):
    """OKLab distance x100 between neighbouring steps."""
    labs = [hex_to_oklab(h) for h in hexes]
    return [float(np.linalg.norm(labs[i + 1] - labs[i]) * 100) for i in range(len(labs) - 1)]


# Rain: 8 colours = 7 legend bins + over-range. Lightness is set per bin, not evenly spaced:
# the low bins stay pale so light rain does not read as heavy (decided 12 Nov after the M3 map).
# Measured cost: adjacent dE 5.7 / 6.8 at the two palest pairs (below the 8 target); the rest 8.5-12.5.
# Exact values are available on click, which serves as the secondary readout.
# A first try (palest L 0.96) was invisible on the old backgrounds (dE 2-3), so the palest step is
# L 0.91 and the backgrounds below are near-white neutrals; tests/test_palette.py enforces both.
RAIN_L = [0.91, 0.86, 0.80, 0.72, 0.63, 0.53, 0.42, 0.30]
RAIN_C = [0.06, 0.085, 0.11, 0.135, 0.15, 0.15, 0.13, 0.10]
RAIN = [oklch_to_hex(L, C, 250) for L, C in zip(RAIN_L, RAIN_C)]   # blue
PROB = ramp(6, hue=345, C_max=0.20)  # magenta, even steps, 6 bins: 2-10-25-50-75-90-100
LAND = "#fafafa"                 # map background, land (neutral; #f4f4f4 failed: palest dE 6.8-7.3)
OCEAN = "#ffffff"                # map background, sea
