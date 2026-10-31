#!/usr/bin/env python3
"""Compare exploratory bounded gaps under development-only sensor faults."""
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
         "src/aegis/v9/stabilized_arrival_candidate.py", "src/aegis/v9/anchor_recovery_candidate.py",
         "src/aegis/v9/sustained_stop_candidate.py", "src/aegis/v9/velocity_freshness_candidate.py",
         "src/aegis/v9/bounded_gap_candidate.py", "scripts/research/study_bounded_gap.py"]


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
    cases = [{"name": "nominal", "velocity_dropout_probability": 0., "velocity_latency_steps": 0, "velocity_replay_probability": 0., "velocity_scale": 1.},
             {"name": "dropout_10_percent", "velocity_dropout_probability": 0.1, "velocity_latency_steps": 0, "velocity_replay_probability": 0., "velocity_scale": 1.},
             {"name": "dropout_30_percent", "velocity_dropout_probability": 0.3, "velocity_latency_steps": 0, "velocity_replay_probability": 0., "velocity_scale": 1.},
             {"name": "dropout_10_underreport", "velocity_dropout_probability": 0.1, "velocity_latency_steps": 0, "velocity_replay_probability": 0., "velocity_scale": 0.25},
             {"name": "replay_20_percent", "velocity_dropout_probability": 0., "velocity_latency_steps": 0, "velocity_replay_probability": 0.2, "velocity_scale": 1.}]
    with a.output.open("x", encoding="utf-8") as out:
        initial_hashes = hashes()
        records = []
        for case in cases:
            for seed in range(a.seed_start, a.seed_start + a.n_seeds):
                for bias in ([0., 0., 0.], [0.8, 0.8, -0.3]):
                    for arm in ("AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP"):
                        identity = {"case": case["name"], "seed": seed, "bias_xyz": bias, "controller": arm}
                        trace = []
                        try:
                            row = run_3d_episode(AegisMuJoCo3DEnvironment(), arm, seed, np.asarray(bias), a.max_steps,
                                range_bias_m=-0.08, velocity_dropout_probability=case["velocity_dropout_probability"],
                                velocity_scale=case["velocity_scale"], velocity_latency_steps=case["velocity_latency_steps"],
                                velocity_replay_probability=case["velocity_replay_probability"],
                                post_stop_steps=a.post_stop_steps, trace=trace)
                            from collections import Counter
                            gate_reasons = dict(Counter(event["velocity_gate_reason"] for event in trace if event["velocity_gate_reason"] is not None))
                            gap_events = [event for event in trace if event["gap_bridged"]]
                            records.append({**identity, **row, "execution_status": "COMPLETED", "last_events": trace[-4:],
                                            "velocity_gate_reasons": gate_reasons, "gap_events": gap_events})
                        except Exception as exc:
                            records.append({**identity, "execution_status": "ERROR", "error_type": type(exc).__name__,
                                            "error": str(exc), "last_events": trace[-4:]})
        final_hashes = hashes()
        json.dump({"classification": "EXPLORATORY_SIMULATION", "seed_start": a.seed_start,
                   "n_seeds": a.n_seeds, "max_steps": a.max_steps, "post_stop_steps": a.post_stop_steps,
                   "cases": cases, "range_bias_m": -0.08, "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                   "mujoco": mujoco.__version__, "timestep_seconds": AegisMuJoCo3DEnvironment().config.timestep},
                   "source_sha256_before": initial_hashes, "source_sha256_after": final_hashes,
                   "sources_unchanged": initial_hashes == final_hashes, "episodes": records}, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
