#!/usr/bin/env python3
"""Paired development-only comparison; results are descriptive, not confirmatory."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed-start", type=int, required=True, help="Development seeds only")
    p.add_argument("--n-seeds", type=int, required=True)
    p.add_argument("--max-steps", type=int, default=100)
    p.add_argument("--range-bias-m", type=float, default=0.0)
    p.add_argument("--range-dropout-probability", type=float, default=0.0)
    p.add_argument("--range-latency-steps", type=int, default=0)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.n_seeds <= 0 or args.max_steps <= 0:
        p.error("n-seeds and max-steps must be positive")
    if not math.isfinite(args.range_bias_m) or not 0 <= args.range_dropout_probability <= 1 or args.range_latency_steps < 0:
        p.error("range bias must be finite, dropout in [0,1], and latency nonnegative")
    with args.output.open("x", encoding="utf-8") as out:
        env = AegisMuJoCo3DEnvironment()
        episodes = []
        for seed in range(args.seed_start, args.seed_start + args.n_seeds):
            for bias in ([0.0, 0.0, 0.0], [0.8, 0.8, -0.3]):
                for controller in ("AEGIS_3D_AWARE_CBF", "AEGIS_3D_STRICT_RANGE"):
                    row = run_3d_episode(env, controller, seed, np.asarray(bias), args.max_steps,
                                         range_bias_m=args.range_bias_m,
                                         range_dropout_probability=args.range_dropout_probability,
                                         range_latency_steps=args.range_latency_steps)
                    row["bias_xyz"] = bias
                    episodes.append(row)
        paths = ["experiments/benchmark_physical_3d_cbf.py", "src/aegis/v9/controller_3d.py", "src/aegis/v9/exploratory_sensor_validation.py",
                 "src/aegis/env/mujoco_3d_cbf.py", "scripts/research/compare_strict_range.py"]
        json.dump({"classification": "EXPLORATORY_SIMULATION", "seed_start": args.seed_start,
                   "n_seeds": args.n_seeds, "max_steps": args.max_steps,
                   "range_fault": {"bias_m": args.range_bias_m, "dropout_probability": args.range_dropout_probability,
                                   "latency_steps": args.range_latency_steps},
                   "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
                   "episodes": episodes}, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
