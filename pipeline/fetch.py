"""Download ECMWF Open Data precipitation fields.

M1 scope: IFS HRES total precipitation (`tp`) for the latest 00z or 12z run,
steps 0-144 h every 3 h, on the global 0.25 deg grid. Cropping to India happens
later, after reading the file, so the raw download stays exactly as ECMWF publishes it.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from ecmwf.opendata import Client

HRES_STEPS = list(range(0, 145, 3))  # 0, 3, ..., 144 h (documented 3-hourly range)
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def latest_main_run(client: Client) -> dt.datetime:
    """Most recent 00z/12z HRES run whose last requested step is published.

    `stream=oper` only carries 00z and 12z runs (06z/18z live in `scda`),
    so asking `latest` for step 144 gives a run that is complete up to 144 h.
    """
    run = client.latest(stream="oper", type="fc", param="tp", step=HRES_STEPS[-1])
    if run.hour not in (0, 12):
        raise RuntimeError(f"Unexpected run hour {run.hour:02d}z for stream=oper")
    return run


def fetch_hres_tp(out_dir: Path = RAW_DIR, source: str = "ecmwf") -> Path:
    client = Client(source=source, model="ifs", resol="0p25")
    run = latest_main_run(client)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"hres_tp_{run:%Y%m%d%H}z.grib2"
    if target.exists():
        print(f"Already downloaded: {target}")
        return target
    print(f"Downloading HRES tp, run {run:%Y-%m-%d %H}z, steps 0-144 -> {target}")
    client.retrieve(
        date=run.date(),
        time=run.hour,
        stream="oper",
        type="fc",
        param="tp",
        step=HRES_STEPS,
        target=str(target),
    )
    return target


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="ecmwf", choices=["ecmwf", "aws", "azure", "google"])
    args = ap.parse_args()
    path = fetch_hres_tp(source=args.source)
    print(f"Saved {path} ({path.stat().st_size / 1e6:.1f} MB)")
