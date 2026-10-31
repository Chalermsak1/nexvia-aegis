#!/usr/bin/env python3
"""Exploratory paired simulation of anchor confirmation under explicit faults."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed-start", type=int, required=True, help="Development seeds only")
    p.add_argument("--n-seeds", type=int, default=20)
    p.add_argument("--max-steps", type=int, default=300)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.n_seeds <= 0 or args.max_steps <= 0:
        p.error("n-seeds and max-steps must be positive")
    cases = [
        {"name": "nominal_range", "range_bias_m": 0., "anchor_bias_xyz": [0., 0., 0.], "anchor_dropout_probability": 0.},
        {"name": "negative_range_bias", "range_bias_m": -0.08, "anchor_bias_xyz": [0., 0., 0.], "anchor_dropout_probability": 0.},
        {"name": "range_bias_anchor_dropout", "range_bias_m": -0.08, "anchor_bias_xyz": [0., 0., 0.], "anchor_dropout_probability": 0.3},
        {"name": "range_bias_anchor_bias", "range_bias_m": -0.08, "anchor_bias_xyz": [0.08, 0., 0.], "anchor_dropout_probability": 0.},
    ]
    paths = ["experiments/benchmark_physical_3d_cbf.py", "src/aegis/v9/controller_3d.py", "src/aegis/v9/exploratory_sensor_validation.py",
             "src/aegis/v9/anchor_arrival_candidate.py", "src/aegis/env/mujoco_3d_cbf.py",
             "scripts/research/compare_anchor_guard.py"]
    with args.output.open("x", encoding="utf-8") as out:
        episodes = []
        for case in cases:
            for seed in range(args.seed_start, args.seed_start + args.n_seeds):
                for bias in ([0., 0., 0.], [0.8, 0.8, -0.3]):
                    for arm in ("AEGIS_3D_STRICT_RANGE", "AEGIS_3D_ANCHOR_GUARD"):
                        identity = {"case": case["name"], "seed": seed, "bias_xyz": bias, "controller": arm}
                        try:
                            row = run_3d_episode(AegisMuJoCo3DEnvironment(), arm, seed, np.asarray(bias), args.max_steps,
                                range_bias_m=case["range_bias_m"], anchor_bias_xyz=np.asarray(case["anchor_bias_xyz"]),
                                anchor_dropout_probability=case["anchor_dropout_probability"])
                            episodes.append({**identity, **row, "execution_status": "COMPLETED"})
                        except Exception as exc:
                            episodes.append({**identity, "execution_status": "ERROR", "error_type": type(exc).__name__, "error": str(exc)})
        json.dump({"classification": "EXPLORATORY_SIMULATION", "seed_start": args.seed_start,
                   "n_seeds": args.n_seeds, "max_steps": args.max_steps, "cases": cases,
                   "runtime": {"python": platform.python_version(), "numpy": np.__version__, "mujoco": mujoco.__version__},
                   "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
                   "episodes": episodes}, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
