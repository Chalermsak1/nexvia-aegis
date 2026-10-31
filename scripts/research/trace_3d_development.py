#!/usr/bin/env python3
"""Trace one explicitly selected exploratory simulation, never a holdout run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True, help="Development seed only")
    parser.add_argument("--bias", type=float, nargs=3, required=True)
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--range-bias-m", type=float, default=0.0)
    parser.add_argument("--anchor-bias-xyz", type=float, nargs=3, default=[0.0, 0.0, 0.0])
    parser.add_argument("--anchor-dropout-probability", type=float, default=0.0)
    parser.add_argument("--controller", choices=("AEGIS_3D_AWARE_CBF", "AEGIS_3D_STRICT_RANGE", "AEGIS_3D_ANCHOR_GUARD"), default="AEGIS_3D_AWARE_CBF")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.max_steps <= 0:
        parser.error("max steps must be positive")
    # Reserve output first: do not execute if evidence already exists.
    with args.output.open("x", encoding="utf-8") as out:
        trace = []
        result = run_3d_episode(AegisMuJoCo3DEnvironment(), args.controller,
                                args.seed, np.asarray(args.bias), args.max_steps,
                                range_bias_m=args.range_bias_m, trace=trace,
                                anchor_bias_xyz=np.asarray(args.anchor_bias_xyz),
                                anchor_dropout_probability=args.anchor_dropout_probability)
        paths = ["experiments/benchmark_physical_3d_cbf.py", "src/aegis/v9/controller_3d.py",
                 "src/aegis/env/mujoco_3d_cbf.py", "src/aegis/v9/anchor_arrival_candidate.py",
                 "scripts/research/trace_3d_development.py"]
        payload = {"classification": "EXPLORATORY_SIMULATION", "seed": args.seed,
                   "bias_xyz": args.bias, "range_bias_m": args.range_bias_m,
                   "anchor_bias_xyz": args.anchor_bias_xyz, "anchor_dropout_probability": args.anchor_dropout_probability,
                   "max_steps": args.max_steps, "episode": result,
                   "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
                   "steps": trace}
        json.dump(payload, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
