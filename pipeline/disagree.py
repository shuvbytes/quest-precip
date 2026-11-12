"""Where the single HRES run and the ENS ensemble disagree (24 h windows). Rule approved 12 Nov:

X = the ENS threshold the viewer has selected (1, 5, 10, 20, 25, 50 or 100 mm).
A "wetter": HRES >= X at the point AND ENS P(>=X) < 25 % at the point and all 8 neighbours.
B "drier":  ENS P(>=X) >= 75 % at the point AND HRES < X at the point and all 8 neighbours.
The neighbourhood condition stops a one-cell shift of the same rain from counting as disagreement.
At the region edge, only the neighbours that exist are used.
"""
from __future__ import annotations

from collections import deque

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

P_UNLIKELY = 25.0   # %: below this the ensemble says "unlikely"
P_LIKELY = 75.0     # %: at or above this the ensemble says "likely"
# Map only (user, 12 Nov): hatch a flag only if it belongs to >= 3 touching (8-connected) flagged
# cells. The point panel still reports every flagged cell, including isolated ones.
MAP_MIN_CLUSTER = 3
# Web map: marks are only readable from zoom 6 (12 Nov check); below that the UI shows ZOOM_NOTE.
MIN_ZOOM_FOR_MARKS = 6
ZOOM_NOTE = "Zoom in to see disagreement marks"


def clusters(mask: np.ndarray):
    """Sizes of 8-connected clusters of True cells, and a label array (0 = not flagged)."""
    lab = np.zeros(mask.shape, int)
    sizes = []
    for i, j in zip(*np.nonzero(mask)):
        if lab[i, j]:
            continue
        sizes.append(0)
        q = deque([(i, j)])
        lab[i, j] = len(sizes)
        while q:
            a, b = q.popleft()
            sizes[-1] += 1
            for da in (-1, 0, 1):
                for db in (-1, 0, 1):
                    y, x = a + da, b + db
                    if 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x] and not lab[y, x]:
                        lab[y, x] = len(sizes)
                        q.append((y, x))
    return np.array(sizes, int), lab


def keep_min_cluster(mask: np.ndarray, n: int = MAP_MIN_CLUSTER) -> np.ndarray:
    """Only the cells that belong to a cluster of at least n cells."""
    mask = np.asarray(mask, bool)
    if n <= 1 or not mask.any():
        return mask
    sizes, lab = clusters(mask)
    return np.concatenate([[False], sizes >= n])[lab]


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
