#!/usr/bin/env python3
"""Development-only matched recovery study with an append-only ledger.

Never use this runner for V9-M4 Holdout. It does not resume or rerun records.
"""
import argparse
import hashlib
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
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect

FILES = ["experiments/benchmark_physical_3d_cbf.py", "src/aegis/env/mujoco_3d_cbf.py",
         "src/aegis/v9/controller_3d.py", "src/aegis/v9/ville_monitor.py",
         "src/aegis/v9/anchor_recovery_candidate.py", "src/aegis/v9/stabilized_arrival_candidate.py",
         "src/aegis/v9/recovery_monitor_candidate.py", "src/aegis/v9/exploratory_sensor_validation.py",
         "scripts/research/development_ledger.py", "scripts/research/study_recovery_monitor_ledger.py"]


def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    seed_group = parser.add_mutually_exclusive_group(required=True)
    seed_group.add_argument("--seed-start", type=int, help="Explicit development seeds only")
    seed_group.add_argument("--development-seeds", type=int, nargs="+", help="Explicit unique development seed list")
    parser.add_argument("--n-seeds", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--post-stop-steps", type=int, default=50)
    parser.add_argument("--include-vector-loss", action="store_true", help="Inject both vector sensors dropping after a STOP proposal")
    parser.add_argument("--incremental-events", action="store_true", help="Persist each pre-physics decision event")
    parser.add_argument("--navigation-force-method", choices=("AXIS_CLIP", "DIRECTION_PRESERVING_PEAK"), default="AXIS_CLIP", help="Development-only guidance ablation; does not change recovery braking")
    parser.add_argument("--recovery-steps", type=int, default=100, help="Explicit exploratory recovery budget; STOP criteria unchanged")
    parser.add_argument("--case", action="append", choices=("nominal", "biased_range", "range_dropout", "vector_loss_after_proposal"), help="Explicit development diagnostic subset; repeat to select multiple cases")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.n_seeds, args.max_steps, args.post_stop_steps, args.recovery_steps) <= 0:
        parser.error("counts must be positive")
    seeds = args.development_seeds if args.development_seeds is not None else list(range(args.seed_start, args.seed_start + args.n_seeds))
    if len(set(seeds)) != len(seeds) or any(seed < 0 for seed in seeds):
        parser.error("development seeds must be unique and nonnegative")
    cases = [{"name": "nominal", "range_bias_m": 0., "range_dropout_probability": 0.},
             {"name": "biased_range", "range_bias_m": -0.08, "range_dropout_probability": 0.},
             {"name": "range_dropout", "range_bias_m": 0., "range_dropout_probability": 0.1}]
    if args.include_vector_loss:
        cases.append({"name": "vector_loss_after_proposal", "range_bias_m": 0., "range_dropout_probability": 0.,
                      "fail_vectors_after_stop_proposal": True})
    if args.case:
        if set(args.case) - {case["name"] for case in cases}:
            parser.error("vector-loss case requires --include-vector-loss")
        cases = [case for case in cases if case["name"] in args.case]
    initial_hashes = hashes()
    runtime = {"python": platform.python_version(), "numpy": np.__version__, "mujoco": mujoco.__version__}
    assignments = []
    for case in cases:
        for seed in seeds:
            for bias in ([0., 0., 0.], [0.8, 0.8, -0.3]):
                for arm in ("AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_RECOVERY_MONITOR"):
                    assignments.append({"id": f"{case['name']}:{seed}:{bias[0]}:{arm}", "case": case,
                        "seed": seed, "bias_xyz": bias, "controller": arm, "max_steps": args.max_steps,
                        "post_stop_steps": args.post_stop_steps, "source_sha256": initial_hashes, "runtime": runtime})
                    assignments[-1]["navigation_force_method"] = args.navigation_force_method
                    assignments[-1]["recovery_steps_limit"] = args.recovery_steps
    with DevelopmentLedger.create(args.output, study="V9-M5 exploratory recovery monitor", assignments=assignments, record_events=args.incremental_events) as ledger:
        for assignment in assignments:
            ledger.start(assignment["id"])
            trace = []
            try:
                result = run_3d_episode(AegisMuJoCo3DEnvironment(), assignment["controller"], assignment["seed"],
                    np.asarray(assignment["bias_xyz"]), assignment["max_steps"],
                    range_bias_m=assignment["case"]["range_bias_m"],
                    range_dropout_probability=assignment["case"]["range_dropout_probability"],
                    fail_vectors_after_stop_proposal=assignment["case"].get("fail_vectors_after_stop_proposal", False),
                    post_stop_steps=assignment["post_stop_steps"], trace=trace,
                    navigation_force_method=assignment["navigation_force_method"],
                    recovery_steps=assignment["recovery_steps_limit"],
                    on_trace=(lambda event: ledger.event(assignment["id"], details={"type": "PRE_PHYSICS_DECISION", "record": event})) if args.incremental_events else None)
                details = {"episode": result, "last_events": trace[-4:]}
                status = "COMPLETED"
            except (LedgerError, LedgerWriteError):
                raise
            except Exception as exc:
                details = {"error_type": type(exc).__name__, "error": str(exc), "last_events": trace[-4:]}
                status = "ERROR"
            after = hashes()
            details["source_sha256_after"] = after
            if after != initial_hashes:
                details["source_changed_during_run"] = True
                ledger.complete(assignment["id"], status="ERROR", details=details)
                raise SystemExit("sources changed; ledger preserved incomplete, no automatic rerun")
            ledger.complete(assignment["id"], status=status, details=details)
        ledger.finalize()
    result = inspect(args.output)
    print(f"ledger_state={result['state']} counts={result['counts']} path={args.output}")


if __name__ == "__main__":
    main()
