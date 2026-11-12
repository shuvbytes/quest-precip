"""Where the single HRES run and the ENS ensemble disagree (24 h windows). Rule approved 12 Nov:

X = the ENS threshold the viewer has selected (1, 5, 10, 20, 25, 50 or 100 mm).
A "wetter": HRES >= X at the point AND ENS P(>=X) < 25 % at the point and all 8 neighbours.
B "drier":  ENS P(>=X) >= 75 % at the point AND HRES < X at the point and all 8 neighbours.
The neighbourhood condition stops a one-cell shift of the same rain from counting as disagreement.
At the region edge, only the neighbours that exist are used.
"""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

P_UNLIKELY = 25.0   # %: below this the ensemble says "unlikely"
P_LIKELY = 75.0     # %: at or above this the ensemble says "likely"


def neighbourhood_max(a: np.ndarray) -> np.ndarray:
    """Max over each point and its 8 neighbours (edge values repeated, so only real neighbours count)."""
    return sliding_window_view(np.pad(a, 1, mode="edge"), (3, 3)).max(axis=(-1, -2))


def flags(hres_mm: np.ndarray, prob_pct: np.ndarray, x_mm: float):
    """Boolean arrays (wetter, drier) for one window and threshold."""
    wetter = (hres_mm >= x_mm) & (neighbourhood_max(prob_pct) < P_UNLIKELY)
    drier = (prob_pct >= P_LIKELY) & (neighbourhood_max(hres_mm) < x_mm)
    return wetter, drier


LEGEND = {
    "wetter": "The single detailed run (HRES) is much wetter than the ensemble here",
    "drier": "The single detailed run (HRES) is much drier than the ensemble here",
}
# Point-panel text; the front end fills {hres}, {pct}, {x} from points.bin for the clicked cell.
POINT_TEXT = {
    "wetter": ("The models disagree here. The single detailed run gives {hres} mm in this window, but the "
               "ensemble gives only a {pct} % chance of at least {x} mm here and nearby. "
               "Heavy rain is possible, not likely."),
    "drier": ("The models disagree here. The ensemble gives a {pct} % chance of at least {x} mm, but the "
              "single detailed run has less than {x} mm here and nearby. "
              "Rain is likely even though this one run misses it."),
}
