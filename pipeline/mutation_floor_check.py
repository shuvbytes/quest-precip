"""DEV-ONLY: prove the display-floor tests catch a wrongly applied floor (not just that they pass).

The floor rule (decided 12 Nov): a frame starts at the smallest legend edge at or above its noise floor
(2 x packing quantum) and is flagged 'raised' when that is not the first edge. Each mutant below breaks one step of
the chain floor -> lowest_visible -> manifest + PNG, in memory only (no file is changed), and runs the floor tests in a
fresh Python process. A mutant must make at least one test FAIL ("caught"); the unmutated code must PASS.

Usage: python pipeline/mutation_floor_check.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ["tests/test_process.py::test_real_run_floor_rule",
         "tests/test_build.py::test_floors_and_files",
         "tests/test_build.py::test_png_never_colours_below_lowest_drawn",
         "tests/test_render.py::test_render_png_hides_values_below_a_raised_floor"]

MUTANTS = {
    "none (correct code)": "",
    "coarse frame left at the first edge (0.5 mm)": """
import process, build
bad = lambda bins, floor_mm: (float(bins[0]), False)
process.lowest_visible = bad; build.lowest_visible = bad
""",
    "frame raised one edge too far": """
import process, build
def bad(bins, floor_mm):
    i = next(i for i, e in enumerate(bins) if e >= floor_mm)
    return float(bins[min(i + 1, len(bins) - 1)]), True
process.lowest_visible = bad; build.lowest_visible = bad
""",
    "manifest right, PNG drawn from the first edge": """
import build, render
real = render.render_png
def bad(field, grid, bins, colours, lowest_drawn, path):
    return real(field, grid, bins, colours, bins[0], path)
build.render_png = bad
""",
}

RUNNER = """
import sys
sys.path[:0] = [{pipeline!r}, {api!r}]
{mutant}
import pytest
sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "--tb=line", *{tests!r}]))
"""


def main():
    ok = True
    for name, code in MUTANTS.items():
        src = RUNNER.format(pipeline=str(ROOT / "pipeline"), api=str(ROOT / "api"), mutant=code, tests=TESTS)
        r = subprocess.run([sys.executable, "-c", src], cwd=ROOT, capture_output=True, text=True)
        failed = [ln.split("::")[-1].split(" ")[0] for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        if not code:
            good = r.returncode == 0
            print(f"{'PASS' if good else 'FAIL'}  {name}: {r.stdout.strip().splitlines()[-1]}")
        else:
            good = r.returncode != 0
            print(f"{'CAUGHT' if good else 'MISSED'}  {name}: failing tests = {failed or 'none'}")
        ok &= good
    print("ALL GOOD: every mutant is caught and the correct code passes" if ok else "PROBLEM: see above")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
