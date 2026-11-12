"""DEV-ONLY: numbers behind the disagreement-layer review (12 Nov).

1. Minimum cluster size: how many flagged cells / clusters survive if isolated flags are dropped.
2. The straight vertical edge in the old crop: region edge or bug?
3. Wetter vs drier imbalance: property of the data or a lopsided rule?
Usage: python pipeline/m4_disagree_stats.py <hres_tp file> <ens_tpg file>
"""
from __future__ import annotations

import sys
from collections import deque

import numpy as np
import xarray as xr

from disagree import P_LIKELY, P_UNLIKELY, flags, neighbourhood_max
from ens import read_ens_probs
from process import window_totals
from region import LON_MIN, crop

BAY = (15.0, 86.5)


def clusters(mask):
    """Sizes of 8-connected clusters and a label array."""
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


def keep_min(mask, n):
    sizes, lab = clusters(mask)
    if n <= 1 or not len(sizes):
        return mask
    ok = np.concatenate([[False], sizes >= n])
    return ok[lab]


def main(hres_path, ens_path):
    tp = crop(xr.open_dataset(hres_path, engine="cfgrib", backend_kwargs={"indexpath": ""})["tp"]).load()
    w = window_totals(tp)
    pg = read_ens_probs(ens_path)                     # global, for the edge check
    p = crop(pg)
    p = p.isel(window=np.where(p.end_h.values <= 144)[0])
    lat, lon = p.latitude.values, p.longitude.values
    bi, bj = int(np.argmin(abs(lat - BAY[0]))), int(np.argmin(abs(lon - BAY[1])))

    print("== 1. Minimum cluster size (8-connected), all 77 threshold/windows ==")
    print(f"   {'X mm':>5s} | {'wetter cells (clusters) for min size 1 / 2 / 3':^48s} | {'drier cells, min 1 / 2 / 3':^28s}")
    tot = {n: [0, 0] for n in (1, 2, 3)}
    for t in p.threshold.values:
        row_w, row_d = [], []
        for n in (1, 2, 3):
            cw = cd = kw = kd = 0
            for k, s in enumerate(p.start_h.values):
                kh = int(np.where(w.start_h == s)[0][0])
                wet, dry = flags(w.mm.values[kh], p.sel(threshold=t).values[k], float(t))
                wet, dry = keep_min(wet, n), keep_min(dry, n)
                cw += wet.sum(); cd += dry.sum(); kw += len(clusters(wet)[0])
            row_w.append(f"{cw:4d} ({kw:3d})"); row_d.append(f"{cd:3d}")
            tot[n][0] += cw; tot[n][1] += cd
        print(f"   {t:5g} | {' / '.join(row_w):^48s} | {' / '.join(row_d):^28s}")
    for n in (1, 2, 3):
        print(f"   total, min size {n}: wetter {tot[n][0]}, drier {tot[n][1]}")
    k108 = int(np.where(p.start_h.values == 108)[0][0])
    wet, _ = flags(w.mm.values[int(np.where(w.start_h == 108)[0][0])], p.sel(threshold=100).values[k108], 100.0)
    sizes, lab = clusters(wet)
    print(f"   Bay point at >=100 mm, 108-132 h: in a cluster of {sizes[lab[bi, bj] - 1]} cells "
          f"(cluster sizes in that frame: {sorted(sizes.tolist(), reverse=True)})")

    print("\n== 2. Straight vertical edge ==")
    print(f"   Region west edge: grid points start at {lon[0]:.2f}E (LON_MIN = {LON_MIN}); image edge = {lon[0]-0.125:.3f}E")
    sel = (lat >= 5) & (lat <= 8)
    inside = p.sel(threshold=1).values[k108][sel, 0]
    glon = pg.longitude.values
    outside = pg.sel(threshold=1).isel(window=int(np.where(pg.start_h.values == 108)[0][0])).sel(
        latitude=lat[sel], longitude=glon[np.argmin(abs(glon - 64.75))]).values
    print(f"   ENS P(>=1) 108-132 h at 5-8N: at 65.00E (first column) {np.round(inside).astype(int).tolist()}")
    print(f"                                 at 64.75E (outside crop) {np.round(outside).astype(int).tolist()}")

    print("\n== 3. Wetter vs drier: data or rule? (all thresholds, all 11 windows) ==")
    for t in (1, 10, 50):
        hres_area = ens_area = pw = pd_ = nb_w = nb_d = 0
        n_lowp = n_hdry = 0
        for k, s in enumerate(p.start_h.values):
            H = w.mm.values[int(np.where(w.start_h == s)[0][0])]
            P = p.sel(threshold=t).values[k]
            hres_area += (H >= t).sum()
            ens_area += P.sum() / 100
            pw += ((H >= t) & (P < P_UNLIKELY)).sum()           # point-only rule
            pd_ += ((H < t) & (P >= P_LIKELY)).sum()
            low_p, h_dry = P < P_UNLIKELY, H < t
            n_lowp += low_p.sum(); n_hdry += h_dry.sum()
            nb_w += (low_p & (neighbourhood_max(P) < P_UNLIKELY)).sum()   # low P stays low around it
            nb_d += (h_dry & (neighbourhood_max(H) < t)).sum()            # dry HRES stays dry around it
        print(f"   X={t:>3g}: cells HRES>=X {hres_area:6d} vs ENS expected {ens_area:8.0f} (ratio {hres_area/ens_area:.2f}); "
              f"point-only rule wetter {pw:5d} / drier {pd_:4d}; neighbourhood keeps "
              f"{100*nb_w/n_lowp:.0f} % of low-P cells vs {100*nb_d/n_hdry:.0f} % of dry-HRES cells")


if __name__ == "__main__":
    main(*sys.argv[1:])
