#!/usr/bin/env python3
"""Development-only MuJoCo braking micro-study; not a task or safety test.

Position/velocity for one arm are measured estimates; obstacle geometry remains
simulator-known. An unavailable command terminates the episode as NO_COMMAND,
without inventing a physical fallback. Never use this for V9-M4 Holdout.
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
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from scripts.research.no_oracle_control import EstimatedState, EstimateOnlyControl
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect

FILES = ["scripts/research/study_estimated_braking_v3.py", "scripts/research/no_oracle_control.py",
         "scripts/research/development_ledger.py", "src/aegis/env/mujoco_3d_cbf.py",
         "src/aegis/v9/velocity_freshness_candidate.py"]


def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}


def apply_filtered_force(env, force):
    """Advance physics without an extra truth-state CBF pass; simulation only."""
    vector = np.asarray(force, dtype=float)
    if vector.shape != (3,) or not np.isfinite(vector).all() or np.any(np.abs(vector) > env.config.control_force_limit + 1e-8):
        raise ValueError("invalid filtered force")
    applied = vector.copy()
    applied[2] += env.config.robot_mass * 9.81
    env.data.xfrc_applied[env.robot_body_id, :3] = applied
    mujoco.mj_step(env.model, env.data)
    env.step_count += 1
    state = env.get_state()
    state["cbf_constraint_residual"] = env.cbf.last_constraint_residual
    state["cbf_projection_method"] = env.cbf.last_projection_method
    return state


def run(seed, arm, case, max_steps, on_event=None):
    if arm not in ("ORACLE_STATE_CBF_BRAKE", "ESTIMATED_STATE_CBF_BRAKE"):
        raise ValueError("unknown braking study arm")
    env = AegisMuJoCo3DEnvironment()
    world_seq, noise_seq = np.random.SeedSequence(seed).spawn(2)
    state = env.reset(np.random.default_rng(world_seq))
    env.data.qvel[:3] = [0.4, 0., 0.]
    mujoco.mj_forward(env.model, env.data)
    state = env.get_state()
    rng = np.random.default_rng(noise_seq)
    controller = EstimateOnlyControl(mass=env.config.robot_mass, force_limit=env.config.control_force_limit)
    events = []
    def emit(event):
        if on_event is not None:
            on_event(event)
        events.append(event)
    no_command = False
    for step in range(max_steps):
        # Truth generates measurement; only the estimates enter the candidate.
        estimate = EstimatedState(state["robot_pos"] + rng.normal(0., .02, 3),
            case["velocity_scale"] * state["robot_velocity"] + rng.normal(0., .02, 3), step, step * env.config.timestep)
        truth_velocity_for_scoring = state["robot_velocity"].copy()
        truth_position_for_scoring = state["robot_pos"].copy()
        command = None
        if arm == "ORACLE_STATE_CBF_BRAKE":
            state = env.step(np.zeros(3), force_braking=True)
            force = state["safe_action"]
        else:
            if case["missing_velocity"]:
                estimate = EstimatedState(estimate.position, None, step, step * env.config.timestep)
            result = controller.command(estimate, now_seconds=step * env.config.timestep, mode="BRAKE",
                                        projector=env.cbf, obstacles=env.obstacles)
            if result["status"] != "COMMAND_PROPOSED":
                emit({"step": step, "status": "NO_COMMAND", "reason": result["reason"],
                               "estimated_position": np.asarray(estimate.position).tolist(),
                               "estimated_velocity": None if estimate.velocity is None else np.asarray(estimate.velocity).tolist(),
                               "sequence": estimate.sequence, "acquired_seconds": estimate.acquired_seconds})
                no_command = True
                break
            command = result
            force = np.asarray(result["projected_force"])
            state = apply_filtered_force(env, force)
        emit({"step": step, "status": "STEP", "true_speed_before": float(np.linalg.norm(truth_velocity_for_scoring)),
                       "true_speed_after": float(np.linalg.norm(state["robot_velocity"])), "force": force.tolist(),
                       "true_position_before": truth_position_for_scoring.tolist(),
                       "true_velocity_before": truth_velocity_for_scoring.tolist(),
                       "true_velocity_after": state["robot_velocity"].tolist(),
                       "estimated_position": np.asarray(estimate.position).tolist() if command is not None else None,
                       "estimated_velocity": np.asarray(estimate.velocity).tolist() if command is not None else None,
                       "measurement_sequence": estimate.sequence if command is not None else None,
                       "measurement_acquired_seconds": estimate.acquired_seconds if command is not None else None,
                       "command": command,
                       "force_dot_true_velocity_before": float(np.dot(force, truth_velocity_for_scoring)),
                       "safety_violation": bool(state["safety_violation"]),
                       "cbf_constraint_residual": state.get("cbf_constraint_residual"),
                       "cbf_projection_method": state.get("cbf_projection_method"),
                       "cbf_qp_feasible": bool(env.cbf.last_qp_feasible) if env.cbf.last_qp_feasible is not None else None})
    return {"controller": arm, "seed": seed, "case": case["name"], "no_command": no_command,
            "steps_applied": sum(e["status"] == "STEP" for e in events), "events": events}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed-start", required=True, type=int, help="Development seeds only")
    p.add_argument("--n-seeds", type=int, default=3)
    p.add_argument("--max-steps", type=int, default=80)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if min(args.n_seeds, args.max_steps) <= 0:
        p.error("counts must be positive")
    cases = [{"name": "nominal", "velocity_scale": 1., "missing_velocity": False},
             {"name": "underreported", "velocity_scale": .25, "missing_velocity": False},
             {"name": "reversed", "velocity_scale": -1., "missing_velocity": False},
             {"name": "missing", "velocity_scale": 1., "missing_velocity": True}]
    initial_hashes = hashes()
    runtime = {"python": platform.python_version(), "numpy": np.__version__, "mujoco": mujoco.__version__}
    assignments = [{"id": f"{case['name']}:{seed}:{arm}", "case": case, "seed": seed, "arm": arm,
                    "max_steps": args.max_steps, "source_sha256": initial_hashes, "runtime": runtime}
                   for case in cases for seed in range(args.seed_start, args.seed_start + args.n_seeds)
                   for arm in ("ORACLE_STATE_CBF_BRAKE", "ESTIMATED_STATE_CBF_BRAKE")]
    with DevelopmentLedger.create(args.output, study="V9-M5 exploratory estimated braking v3", assignments=assignments, record_events=True) as ledger:
        for a in assignments:
            ledger.start(a["id"])
            try:
                result = run(a["seed"], a["arm"], a["case"], a["max_steps"],
                             on_event=lambda event: ledger.event(a["id"], details=event))
                details, status = {"episode": result}, "COMPLETED"
            except (LedgerError, LedgerWriteError):
                raise
            except Exception as exc:
                details, status = {"error_type": type(exc).__name__, "error": str(exc)}, "ERROR"
            details["source_sha256_after"] = hashes()
            if details["source_sha256_after"] != initial_hashes:
                ledger.complete(a["id"], status="ERROR", details=details)
                raise SystemExit("sources changed; ledger remains incomplete")
            ledger.complete(a["id"], status=status, details=details)
        ledger.finalize()
    result = inspect(args.output)
    print(f"ledger_state={result['state']} counts={result['counts']} path={args.output}")


if __name__ == "__main__":
    main()
