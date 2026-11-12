import sys
from pathlib import Path

# Pipeline modules import each other by plain name (e.g. `from region import crop`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
