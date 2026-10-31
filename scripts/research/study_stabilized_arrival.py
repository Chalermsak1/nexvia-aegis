#!/usr/bin/env python3
"""Compare exploratory velocity-gated arrival under development faults."""
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

FILES = ["experiments/benchmark_physical_3d_cbf.py", "src/aegis/v9/controller_3d.py",
         "src/aegis/v9/anchor_arrival_candidate.py", "src/aegis/env/mujoco_3d_cbf.py",
         "src/aegis/v9/stabilized_arrival_candidate.py", "scripts/research/study_stabilized_arrival.py"]


def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed-start", type=int, required=True, help="Development seeds only")
    p.add_argument("--n-seeds", type=int, default=20)
    p.add_argument("--max-steps", type=int, default=300)
    p.add_argument("--post-stop-steps", type=int, default=50)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if min(a.n_seeds, a.max_steps, a.post_stop_steps) <= 0:
        p.error("all counts must be positive")
    cases = [{"name": "nominal", "range_bias_m": 0., "anchor_dropout_probability": 0., "velocity_bias_xyz": [0., 0., 0.], "velocity_dropout_probability": 0.},
             {"name": "biased_range", "range_bias_m": -0.08, "anchor_dropout_probability": 0., "velocity_bias_xyz": [0., 0., 0.], "velocity_dropout_probability": 0.},
             {"name": "biased_range_anchor_dropout", "range_bias_m": -0.08, "anchor_dropout_probability": 0.3, "velocity_bias_xyz": [0., 0., 0.], "velocity_dropout_probability": 0.},
             {"name": "biased_range_velocity_bias", "range_bias_m": -0.08, "anchor_dropout_probability": 0., "velocity_bias_xyz": [0.08, 0., 0.], "velocity_dropout_probability": 0.},
             {"name": "biased_range_velocity_dropout", "range_bias_m": -0.08, "anchor_dropout_probability": 0., "velocity_bias_xyz": [0., 0., 0.], "velocity_dropout_probability": 0.1}]
    with a.output.open("x", encoding="utf-8") as out:
        initial_hashes = hashes()
        records = []
        for case in cases:
            for seed in range(a.seed_start, a.seed_start + a.n_seeds):
                for bias in ([0., 0., 0.], [0.8, 0.8, -0.3]):
                    for arm in ("AEGIS_3D_STRICT_RANGE", "AEGIS_3D_ANCHOR_GUARD", "AEGIS_3D_STABILIZED"):
                        identity = {"case": case["name"], "seed": seed, "bias_xyz": bias, "controller": arm}
                        trace = []
                        try:
                            row = run_3d_episode(AegisMuJoCo3DEnvironment(), arm, seed, np.asarray(bias), a.max_steps,
                                range_bias_m=case["range_bias_m"], anchor_dropout_probability=case["anchor_dropout_probability"],
                                velocity_bias_xyz=np.asarray(case["velocity_bias_xyz"]), velocity_dropout_probability=case["velocity_dropout_probability"],
                                post_stop_steps=a.post_stop_steps, trace=trace)
                            records.append({**identity, **row, "execution_status": "COMPLETED", "last_events": trace[-4:]})
                        except Exception as exc:
                            records.append({**identity, "execution_status": "ERROR", "error_type": type(exc).__name__,
                                            "error": str(exc), "last_events": trace[-4:]})
        final_hashes = hashes()
        json.dump({"classification": "EXPLORATORY_SIMULATION", "seed_start": a.seed_start,
                   "n_seeds": a.n_seeds, "max_steps": a.max_steps, "post_stop_steps": a.post_stop_steps,
                   "cases": cases, "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                   "mujoco": mujoco.__version__, "timestep_seconds": AegisMuJoCo3DEnvironment().config.timestep},
                   "source_sha256_before": initial_hashes, "source_sha256_after": final_hashes,
                   "sources_unchanged": initial_hashes == final_hashes, "episodes": records}, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
