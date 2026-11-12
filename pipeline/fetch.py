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
ENS_PROB_PARAMS = ["tpg1", "tpg5", "tpg10", "tpg20", "tpg25", "tpg50", "tpg100"]
# 24 h windows starting every 12 h. 0-24 ... 120-144 match HRES steps 0-144; 132-156 is fetched
# as well so a late Bay system can be checked even if ENS timing differs from HRES.
ENS_WINDOWS = [f"{s}-{s + 24}" for s in range(0, 133, 12)]
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def latest_main_run(client: Client) -> dt.datetime:
    """Newest 00z/12z run for which BOTH HRES tp (to 144 h) and ENS tpg* (last window) are published.

    Checked 12 Nov 2026: since IFS 50r1 (May 2026) the 06z/18z HRES runs are also under
    stream=oper and reach 144 h, so `latest()` without `time` can return 06z/18z. ENS
    probabilities (type=ep) exist only for 00z/12z, so we pin `time` and take, per hour,
    the older of the two "latest" dates (both products are then on the server).
    """
    best = None
    for hour in (0, 12):
        try:
            hres = client.latest(time=hour, stream="oper", type="fc", param="tp", step=HRES_STEPS[-1])
            ens = client.latest(time=hour, stream="enfo", type="ep", param=ENS_PROB_PARAMS[-1],
                                step=ENS_WINDOWS[-1])
        except ValueError:
            continue
        run = min(hres, ens)
        best = run if best is None else max(best, run)
    if best is None or best.hour not in (0, 12):
        raise RuntimeError("No 00z/12z run with both HRES tp and ENS tpg* found in the last 2 days")
    return best


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




def fetch_ens_probs(run: dt.datetime, out_dir: Path = RAW_DIR, source: str = "ecmwf") -> Path:
    """ENS probabilities of 24 h precipitation thresholds (stream enfo, type ep) for `run`."""
    if run.hour not in (0, 12):
        raise ValueError("ENS probability products exist only for 00z and 12z runs")
    client = Client(source=source, model="ifs", resol="0p25")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"ens_tpg_{run:%Y%m%d%H}z.grib2"
    if target.exists():
        print(f"Already downloaded: {target}")
        return target
    print(f"Downloading ENS {','.join(ENS_PROB_PARAMS)}, run {run:%Y-%m-%d %H}z, windows "
          f"{ENS_WINDOWS[0]} .. {ENS_WINDOWS[-1]} -> {target}")
    client.retrieve(
        date=run.date(),
        time=run.hour,
        stream="enfo",
        type="ep",
        param=ENS_PROB_PARAMS,
        step=ENS_WINDOWS,
        target=str(target),
    )
    return target


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="ecmwf", choices=["ecmwf", "aws", "azure", "google"])
    args = ap.parse_args()
    path = fetch_hres_tp(source=args.source)
    print(f"Saved {path} ({path.stat().st_size / 1e6:.1f} MB)")
    # Same run as HRES, so the two layers always describe the same forecast.
    run = dt.datetime.strptime(path.stem.split("_")[-1], "%Y%m%d%Hz")
    epath = fetch_ens_probs(run, source=args.source)
    print(f"Saved {epath} ({epath.stat().st_size / 1e6:.1f} MB)")
