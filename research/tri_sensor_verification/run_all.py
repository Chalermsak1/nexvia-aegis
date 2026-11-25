"""
One-Click Experiment Runner for VS Code (Press ▶ Play on this file!).

Runs the entire pipeline in order:
  1. Unit tests (pytest -v)
  2. 20-scenario x 3-arm 3D maze exploration benchmark (saves all CSV/JSON/Audit logs)
  3. Generates 4 high-resolution (300 DPI) PNG plots
  4. Builds the interactive 5-Tab HTML dashboard and opens it in your browser!
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import webbrowser
import pytest

# Ensure workspace root and src/ are always on sys.path even when clicking Run in VS Code
ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from research.tri_sensor_verification.maze_experiment_runner import run_full_experiment
from research.tri_sensor_verification.plot_results import generate_all_plots
from research.tri_sensor_verification.build_dashboard import build_dashboard


def main() -> None:
    print("\n[1/4] Running pytest unit tests...")
    exit_code = pytest.main(["-v", str(ROOT / "research" / "tri_sensor_verification" / "tests" / "test_tri_sensor_verifier.py")])
    if exit_code != 0:
        raise SystemExit(exit_code)

    print("\n[2/4] Running 20-scenario x 3-arm 3D Maze Experiment...")
    run_dir = run_full_experiment(run_name="tri_sensor_maze_v1")

    print("\n[3/4] Generating 300-DPI PNG plots...")
    generate_all_plots(str(run_dir))

    print("\n[4/4] Building & opening Interactive 5-Tab Dashboard...")
    dash_path = build_dashboard(str(run_dir))
    resolved = dash_path.resolve()
    if hasattr(os, "startfile"):
        os.startfile(str(resolved))
    else:
        webbrowser.open(resolved.as_uri())
    print(f"\nALL DONE! Dashboard opened in browser: {resolved}")


if __name__ == "__main__":
    main()
