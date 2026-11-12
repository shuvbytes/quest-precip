"""GRIB packing precision: how coarsely each field was stored.

GRIB2 grid packing (simple and CCSDS) stores each value Y as integers X with
    Y = R + X * 2**E * 10**(-D)
(R = referenceValue, E = binaryScaleFactor, D = decimalScaleFactor). So every decoded
value lies on a grid of spacing q = 2**E * 10**(-D): the quantum. Rounding to that grid
moves each value by at most q/2. The difference of two fields therefore has error at most
(q1 + q2) / 2, and a true change of 0 can decode as anything down to -(q1 + q2) / 2.

Run as a script to check this claim against a file:
    python pipeline/packing.py data/raw/hres_tp_YYYYMMDDHHz.grib2
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import eccodes
import numpy as np


@dataclass
class FieldPacking:
    step: int
    packing_type: str
    bits: int
    E: int
    D: int
    R: float
    quantum: float  # in the field's own units


def read_packing(path: str) -> list[FieldPacking]:
    out = []
    with open(path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                E = eccodes.codes_get(gid, "binaryScaleFactor")
                D = eccodes.codes_get(gid, "decimalScaleFactor")
                bits = eccodes.codes_get(gid, "bitsPerValue")
                out.append(FieldPacking(
                    step=int(eccodes.codes_get(gid, "endStep")),
                    packing_type=eccodes.codes_get(gid, "packingType"),
                    bits=bits, E=E, D=D,
                    R=eccodes.codes_get(gid, "referenceValue"),
                    # A constant field (bits = 0) is stored exactly.
                    quantum=0.0 if bits == 0 else 2.0**E * 10.0**(-D),
                ))
            finally:
                eccodes.codes_release(gid)
    return out


def _check(path: str) -> None:
    import xarray as xr
    from region import crop

    packs = read_packing(path)
    da = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})["tp"]
    units = da.attrs["units"]
    vals = da.values.astype(np.float64)  # global field, all steps
    steps = (da.step.values / np.timedelta64(1, "h")).astype(int)
    assert [p.step for p in packs] == steps.tolist(), "message order differs from xarray steps"

    print(f"units: {units!r}\n")
    print("1) Every decoded value is R + integer * q (exactly on the packing grid)")
    worst = 0.0
    for p, v in zip(packs, vals):
        if p.quantum == 0:
            continue
        k = (v - p.R) / p.quantum
        worst = max(worst, float(np.abs(k - np.round(k)).max()))
    print(f"   max |k - round(k)| over all fields and points: {worst:.2e}  (0 means exact)\n")

    print("2) Negative step-to-step changes vs the bound -(q1 + q2) / 2")
    print(f"   {'interval':>10s} {'q1 (mm)':>8s} {'q2 (mm)':>8s} {'bound (mm)':>10s}"
          f" {'min diff (mm)':>13s} {'n neg (global)':>14s} {'n neg (region)':>14s}")
    reg = crop(da).values.astype(np.float64)
    all_ok = True
    for i in range(1, len(packs)):
        q1, q2 = packs[i - 1].quantum, packs[i].quantum
        d = vals[i] - vals[i - 1]
        bound = -(q1 + q2) / 2
        n_neg = int((d < 0).sum())
        n_neg_reg = int(((reg[i] - reg[i - 1]) < 0).sum())
        ok = d.min() >= bound - 1e-12
        all_ok &= ok
        if n_neg or i in (1, len(packs) - 1):
            print(f"   {packs[i-1].step:3d}-{packs[i].step:3d} h {q1*1e3:8.4f} {q2*1e3:8.4f}"
                  f" {bound*1e3:10.4f} {d.min()*1e3:13.4f} {n_neg:14d} {n_neg_reg:14d}"
                  f"{'' if ok else '  <-- EXCEEDS BOUND'}")
    print(f"\n   all negative changes within packing bound: {all_ok}")
    qmax = max(p.quantum for p in packs)
    print(f"   largest quantum in this run: {qmax*1e3:.4f} mm  -> worst error of any"
          f" interval total: {qmax*1e3:.4f} mm")


if __name__ == "__main__":
    _check(sys.argv[1])
