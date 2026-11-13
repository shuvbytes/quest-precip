import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Pipeline modules import each other by plain name (e.g. `from region import crop`); api/ holds the API's modules.
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "api"))
RAW = ROOT / "data" / "raw"


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """The site built from the newest downloaded run (shared by test_build and test_api): (data dir, manifest)."""
    import io
    import json
    from contextlib import redirect_stdout
    hres, ens = sorted(RAW.glob("hres_tp_*.grib2")), sorted(RAW.glob("ens_tpg_*.grib2"))
    if not (hres and ens):
        pytest.skip("real GRIB not downloaded")
    from build import main
    out = tmp_path_factory.mktemp("site") / "data"   # build.py copies web/ into out.parent
    with redirect_stdout(io.StringIO()):
        main(str(hres[-1]), str(ens[-1]), out)
    return out, json.loads((out / "manifest.json").read_text())
