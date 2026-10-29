"""
NEXVIA AEGIS — Benchmark: 3D Physical AI with Control Barrier Functions (CBF) & Ville Martingales.

Evaluates:
1. Baseline Unshielded Controller: Susceptible to both obstacle collision and sensor corruption false arrival.
2. CBF-Only Controller: Prevents collisions, but vulnerable to sensor bias/drift (false arrivals).
3. AEGIS-V9 + CBF Controller: Planar V9 decision core integrated with 3D motion.
4. AEGIS-V9 + CBF + range guard: Exploratory fail-closed STOP corroboration.
5. AEGIS-V9 + CBF + fixed range window: Exploratory four-sample STOP check.
6. AEGIS-V9 + CBF + 3D veto: Same range window plus two 3D vector
   plausibility checks. These are development heuristics, not risk certificates.

This is a development benchmark. Observations are not a safety guarantee or a
confirmatory evaluation, and the range guard is not a sequential confidence bound.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
import mujoco
import aegis.env.mujoco_3d_cbf as world_module
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment, PhysicalWorld3DConfig
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.controller import AegisV9Controller
from aegis.v9.controller_3d import Aegis3DAwareController


def corroborate_3d_stop(
    ranges: list[float],
    vectors_a: list[np.ndarray],
    vectors_b: list[np.ndarray],
    *,
    sigma: float,
    radius: float,
) -> bool:
    """Fixed-window range confirmation with two independent 3D vector vetoes.

    The vector lower-distance margins only reject gross contradictions. They
    do not make a sequential or distribution-free safety guarantee.
    """
    if len(ranges) != 4 or len(vectors_a) != 4 or len(vectors_b) != 4:
        return False
    if not math.isfinite(sigma) or sigma <= 0 or not math.isfinite(radius) or radius <= 0:
        return False
    if not all(np.isfinite(v).all() and np.shape(v) == (3,) for v in vectors_a + vectors_b):
        return False
    if not all(math.isfinite(value) for value in ranges):
        return False

    margin = 1.645 * sigma / math.sqrt(4)
    if float(np.mean(ranges)) + margin > radius:
        return False
    for vectors in (vectors_a, vectors_b):
        if float(np.linalg.norm(np.mean(vectors, axis=0))) - margin > radius:
            return False
    return True


def run_3d_episode(
    env: AegisMuJoCo3DEnvironment,
    controller_type: str,
    seed: int,
    sensor_bias: np.ndarray,  # 3D bias vector
    max_steps: int = 300,
    range_bias_m: float = 0.0,
    range_dropout_probability: float = 0.0,
    range_latency_steps: int = 0,
) -> dict:
    if controller_type not in {
        "UNSHIELDED", "CBF_ONLY", "AEGIS_V9_CBF",
        "AEGIS_V9_CBF_RANGE_GUARD", "AEGIS_V9_CBF_RANGE_WINDOW",
        "AEGIS_V9_CBF_RANGE_3D_VETO", "AEGIS_3D_AWARE_CBF",
    }:
        raise ValueError(f"Unknown 3D controller type: {controller_type}")
    if not 0.0 <= range_dropout_probability <= 1.0 or range_latency_steps < 0:
        raise ValueError("Range dropout probability must be in [0,1] and latency nonnegative")
    if not math.isfinite(range_bias_m) or np.shape(sensor_bias) != (3,) or not np.isfinite(sensor_bias).all():
        raise ValueError("Range bias and 3D vector-sensor bias must be finite")
    env_seq, sensor_seq, fault_seq = np.random.SeedSequence(seed).spawn(3)
    rng_env = np.random.default_rng(env_seq)
    rng_sensors = np.random.default_rng(sensor_seq)
    rng_faults = np.random.default_rng(fault_seq)
    state = env.reset(rng_env)

    v9_ctrl = AegisV9Controller() if controller_type.startswith("AEGIS_V9_CBF") else None
    if v9_ctrl:
        v9_ctrl.reset()
    ctrl_3d = Aegis3DAwareController(success_radius=env.config.success_radius) if controller_type == "AEGIS_3D_AWARE_CBF" else None
    if ctrl_3d:
        ctrl_3d.reset()

    collision_occurred = False
    cbf_constraint_violation_occurred = False
    cbf_unchecked_steps = 0
    cbf_exact_fallback_steps = 0
    cbf_infeasible_steps = 0
    false_arrival = False
    true_success = False
    abstained = False
    timeout = False

    steps_taken = 0
    next_query_anchor = False
    range_window: list[float] = []
    vector_window_a: list[np.ndarray] = []
    vector_window_b: list[np.ndarray] = []
    range_history: list[tuple[float, bool]] = []

    def observe_step(step_state: dict) -> None:
        nonlocal collision_occurred, cbf_constraint_violation_occurred
        nonlocal cbf_unchecked_steps, cbf_exact_fallback_steps, cbf_infeasible_steps
        collision_occurred |= bool(step_state["safety_violation"])
        if controller_type != "UNSHIELDED":
            residual = step_state.get("cbf_constraint_residual")
            if residual is None:
                cbf_unchecked_steps += 1
            elif residual > 1e-8:
                cbf_constraint_violation_occurred = True
            method = step_state.get("cbf_projection_method")
            cbf_exact_fallback_steps += int(method == "EXACT_ACTIVE_SET")
            cbf_infeasible_steps += int(method == "INFEASIBLE_WITHIN_ACTUATOR_BOX")

    for step in range(max_steps):
        steps_taken = step + 1
        pos = state["robot_pos"]
        vel = state["robot_velocity"]
        target = state["target_pos"]

        true_delta_3d = target - pos
        true_dist = float(np.linalg.norm(true_delta_3d))

        # Sensor readings in 3D (projected to 2D for V9 planar-aware core, with Z tracking)
        noise_a = rng_sensors.normal(0.0, 0.05, size=3)
        noise_b = rng_sensors.normal(0.0, 0.05, size=3)
        meas_a_3d = true_delta_3d + sensor_bias + noise_a
        meas_b_3d = true_delta_3d + sensor_bias + noise_b
        raw_range = true_dist + range_bias_m + float(rng_sensors.normal(0.0, 0.05))
        raw_valid = not (
            range_dropout_probability > 0.0
            and rng_faults.random() < range_dropout_probability
        )
        range_history.append((raw_range, raw_valid))
        if len(range_history) > range_latency_steps:
            range_meas, range_valid = range_history[-range_latency_steps - 1]
        else:
            range_meas, range_valid = 0.0, False
        range_fresh = range_valid and range_latency_steps == 0

        if controller_type in {"AEGIS_V9_CBF_RANGE_WINDOW", "AEGIS_V9_CBF_RANGE_3D_VETO"} and range_window:
            # Continue a fixed-size verification window after planar STOP. The
            # independent range sensor is sampled while the robot brakes; this
            # is a development heuristic, not a sequential risk certificate.
            state = env.step(np.zeros(3), force_braking=True)
            observe_step(state)
            if not range_fresh or not math.isfinite(range_meas):
                abstained = True
                break
            range_window.append(range_meas)
            vector_window_a.append(meas_a_3d.copy())
            vector_window_b.append(meas_b_3d.copy())
            if len(range_window) == 4:
                range_upper = float(np.mean(range_window)) + 1.645 * 0.05 / math.sqrt(4)
                accepted_by_range = math.isfinite(range_upper) and range_upper <= env.config.success_radius
                accepted_by_vectors = (
                    controller_type != "AEGIS_V9_CBF_RANGE_3D_VETO"
                    or corroborate_3d_stop(
                        range_window, vector_window_a, vector_window_b,
                        sigma=0.05, radius=env.config.success_radius,
                    )
                )
                if accepted_by_range and accepted_by_vectors:
                    if state["distance"] <= env.config.success_radius:
                        true_success = True
                    else:
                        false_arrival = True
                else:
                    abstained = True
                break
            continue

        if controller_type == "UNSHIELDED":
            # Direct tracking of biased sensor without CBF
            u_des = 1.2 * meas_a_3d - 0.5 * vel
            # In unshielded mode, we bypass CBF filter completely:
            f_total = np.clip(u_des, -env.config.control_force_limit, env.config.control_force_limit)
            f_total[2] += env.config.robot_mass * 9.81
            env.data.xfrc_applied[env.robot_body_id, :3] = f_total
            import mujoco
            mujoco.mj_step(env.model, env.data)
            env.step_count += 1
            state = env.get_state()
            observe_step(state)

            # Arrival condition based on flawed sensor A
            if np.linalg.norm(meas_a_3d) < 0.22:
                if true_dist <= env.config.success_radius:
                    true_success = True
                else:
                    false_arrival = True
                break

        elif controller_type == "CBF_ONLY":
            # Uses CBF to prevent obstacle collision, but trusts flawed sensor A
            u_des = 1.2 * meas_a_3d - 0.5 * vel
            state = env.step(u_des, force_braking=False)
            observe_step(state)

            if np.linalg.norm(meas_a_3d) < 0.22:
                if true_dist <= env.config.success_radius:
                    true_success = True
                else:
                    false_arrival = True
                break

        elif controller_type.startswith("AEGIS_V9_CBF"):
            # AEGIS-V9 Runtime Assurance + CBF
            rd_a = SensorReading(
                estimate=meas_a_3d[:2],
                sigma=0.05,
                valid=True,
                anomaly=False,
                dropped=False,
                bias=np.zeros(2),
                drift=np.zeros(2),
            )
            rd_b = SensorReading(
                estimate=meas_b_3d[:2],
                sigma=0.05,
                valid=True,
                anomaly=False,
                dropped=False,
                bias=np.zeros(2),
                drift=np.zeros(2),
            )
            rd_r = RangeReading(
                distance=range_meas if range_valid else 0.0,
                sigma=0.05,
                valid=range_valid,
                dropped=not range_valid,
            )

            anc_reading = None
            if next_query_anchor:
                # Provide high-integrity episodic anchor reading in 2D
                anc_noise = rng_sensors.normal(0.0, 0.04, size=2)
                anc_reading = AnchorReading(
                    estimate=true_delta_3d[:2] + anc_noise,
                    sigma=0.04,
                    valid=True,
                    queried=True,
                    cost_accrued=0.05,
                )

            action_2d, dec_type, _, next_query_anchor = v9_ctrl.update(
                rd_a, rd_b, rd_r, anchor_reading=anc_reading, step=step
            )

            if dec_type == "ABSTAIN":
                # Brake on abstention through the same CBF feasibility check.
                state = env.step(np.zeros(3), force_braking=True)
                observe_step(state)
                abstained = True
                break
            elif dec_type == "STOP":
                if controller_type in {"AEGIS_V9_CBF_RANGE_WINDOW", "AEGIS_V9_CBF_RANGE_3D_VETO"}:
                    state = env.step(np.zeros(3), force_braking=True)
                    observe_step(state)
                    if not range_fresh or not math.isfinite(range_meas):
                        abstained = True
                        break
                    range_window.append(range_meas)
                    vector_window_a.append(meas_a_3d.copy())
                    vector_window_b.append(meas_b_3d.copy())
                    continue
                if controller_type == "AEGIS_V9_CBF_RANGE_GUARD":
                    # Engineering guard only. A one-observation range margin is not a
                    # repeated-look statistical guarantee; final safety is measured
                    # against ground truth after the decision.
                    range_upper = range_meas + 1.645 * rd_r.sigma
                    if not range_fresh or not math.isfinite(range_upper) or range_upper > env.config.success_radius:
                        state = env.step(np.zeros(3), force_braking=True)
                        observe_step(state)
                        abstained = True
                        break
                if true_dist <= env.config.success_radius:
                    true_success = True
                else:
                    false_arrival = True
                break
            else:
                # Active probing or nominal navigation
                u_des_3d = np.array([action_2d[0], action_2d[1], 0.8 * meas_a_3d[2] - 0.4 * vel[2]])
                force_brake = (dec_type == "VERIFY")
                state = env.step(u_des_3d, force_braking=force_brake)
                observe_step(state)

        elif controller_type == "AEGIS_3D_AWARE_CBF":
            assert ctrl_3d is not None
            rd_a = SensorReading(
                estimate=meas_a_3d,
                sigma=0.05,
                valid=True,
                anomaly=False,
                dropped=False,
                bias=np.zeros(3),
                drift=np.zeros(3),
            )
            rd_b = SensorReading(
                estimate=meas_b_3d,
                sigma=0.05,
                valid=True,
                anomaly=False,
                dropped=False,
                bias=np.zeros(3),
                drift=np.zeros(3),
            )
            rd_r = RangeReading(
                distance=range_meas if range_valid else 0.0,
                sigma=0.05,
                valid=range_valid,
                dropped=not range_valid,
            )
            anc_reading = None
            if next_query_anchor:
                anc_noise = rng_sensors.normal(0.0, 0.04, size=3)
                anc_reading = AnchorReading(
                    estimate=true_delta_3d + anc_noise,
                    sigma=0.04,
                    valid=True,
                    queried=True,
                    cost_accrued=0.05,
                )

            action_3d, dec_type, _, next_query_anchor = ctrl_3d.update(
                rd_a, rd_b, rd_r, anchor_reading=anc_reading, step=step
            )

            if dec_type == "ABSTAIN":
                state = env.step(np.zeros(3), force_braking=True)
                observe_step(state)
                abstained = True
                break
            elif dec_type == "STOP":
                if true_dist <= env.config.success_radius:
                    true_success = True
                else:
                    false_arrival = True
                break
            else:
                u_des_3d = action_3d - 0.5 * vel
                force_brake = (dec_type == "VERIFY")
                state = env.step(u_des_3d, force_braking=force_brake)
                observe_step(state)

    else:
        timeout = True

    return {
        "controller": controller_type,
        "seed": seed,
        "steps": steps_taken,
        "final_distance": round(float(state["distance"]), 4),
        "true_success": int(true_success),
        "false_arrival": int(false_arrival),
        "collision_occurred": int(collision_occurred),
        "cbf_constraint_violation_occurred": int(cbf_constraint_violation_occurred),
        "cbf_unchecked_steps": cbf_unchecked_steps,
        "cbf_exact_fallback_steps": cbf_exact_fallback_steps,
        "cbf_infeasible_steps": cbf_infeasible_steps,
        "abstained": int(abstained),
        "timeout": int(timeout),
        "range_bias_m": range_bias_m,
        "range_dropout_probability": range_dropout_probability,
        "range_latency_steps": range_latency_steps,
    }


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Exploratory 3D MuJoCo development benchmark")
    parser.add_argument("--seed-start", type=int, default=88000)
    parser.add_argument("--n-seeds", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--range-bias-m", type=float, default=0.0)
    parser.add_argument("--range-dropout-probability", type=float, default=0.0)
    parser.add_argument("--range-latency-steps", type=int, default=0)
    parser.add_argument("--sensor-bias-xyz", type=float, nargs=3,
                        metavar=("X", "Y", "Z"),
                        help="Run one explicit 3D vector-sensor bias instead of the default suite")
    parser.add_argument("--include-3d-aware", action="store_true", help="Include AEGIS_3D_AWARE_CBF in evaluation suite")
    parser.add_argument("--output", type=Path, help="New JSON evidence file; existing files are never overwritten")
    args = parser.parse_args(argv)
    if args.n_seeds <= 0 or args.max_steps <= 0:
        parser.error("--n-seeds and --max-steps must be positive")
    if not 0.0 <= args.range_dropout_probability <= 1.0 or args.range_latency_steps < 0:
        parser.error("range dropout probability must be in [0,1] and latency nonnegative")
    if not math.isfinite(args.range_bias_m) or (
        args.sensor_bias_xyz is not None and not all(math.isfinite(v) for v in args.sensor_bias_xyz)
    ):
        parser.error("range and vector-sensor biases must be finite")

    env = AegisMuJoCo3DEnvironment()
    seeds = range(args.seed_start, args.seed_start + args.n_seeds)
    biases = [
        np.array([0.0, 0.0, 0.0]),       # Nominal
        np.array([0.5, -0.4, 0.2]),      # Sensor Bias
        np.array([0.8, 0.8, -0.3]),      # Heavy Correlated Bias
    ]
    if args.sensor_bias_xyz is not None:
        biases = [np.asarray(args.sensor_bias_xyz, dtype=np.float64)]

    print("=" * 80)
    print("NEXVIA AEGIS — CONTINUOUS 3D MUJOCO & CONTROL BARRIER FUNCTION BENCHMARK")
    print("=" * 80)

    controllers = [
        "UNSHIELDED", "CBF_ONLY", "AEGIS_V9_CBF",
        "AEGIS_V9_CBF_RANGE_GUARD", "AEGIS_V9_CBF_RANGE_WINDOW",
        "AEGIS_V9_CBF_RANGE_3D_VETO",
    ]
    if args.include_3d_aware:
        controllers.append("AEGIS_3D_AWARE_CBF")

    all_results = {}
    episode_records = []
    for c_type in controllers:
        n_total = 0
        n_ts = 0
        n_fa = 0
        n_col = 0
        n_abs = 0
        n_to = 0
        n_cbf_viol = 0
        n_cbf_unchecked = 0
        n_cbf_exact = 0
        n_cbf_infeasible = 0

        for b in biases:
            for s in seeds:
                res = run_3d_episode(
                    env, c_type, s, b, max_steps=args.max_steps,
                    range_bias_m=args.range_bias_m,
                    range_dropout_probability=args.range_dropout_probability,
                    range_latency_steps=args.range_latency_steps,
                )
                res["bias_xyz"] = b.tolist()
                episode_records.append(res)
                n_total += 1
                n_ts += res["true_success"]
                n_fa += res["false_arrival"]
                n_col += res["collision_occurred"]
                n_abs += res["abstained"]
                n_to += res["timeout"]
                n_cbf_viol += res["cbf_constraint_violation_occurred"]
                n_cbf_unchecked += res["cbf_unchecked_steps"]
                n_cbf_exact += res["cbf_exact_fallback_steps"]
                n_cbf_infeasible += res["cbf_infeasible_steps"]

        tsr = 100.0 * n_ts / n_total
        fa_rate = 100.0 * n_fa / n_total
        col_rate = 100.0 * n_col / n_total
        abs_rate = 100.0 * n_abs / n_total
        coverage = 100.0 * (n_ts + n_fa) / n_total
        all_results[c_type] = {"episodes": n_total, "true_success": n_ts,
                               "false_arrival": n_fa, "collision": n_col,
                               "abstained": n_abs, "timeout": n_to,
                               "accepted": n_ts + n_fa,
                               "cbf_constraint_violation_episodes": n_cbf_viol,
                               "cbf_unchecked_steps": n_cbf_unchecked,
                               "cbf_exact_fallback_steps": n_cbf_exact,
                               "cbf_infeasible_steps": n_cbf_infeasible}

        print(f"\nPolicy Architecture: {c_type}")
        print(f"  Episodes Evaluated: {n_total}")
        print(f"  True Success Rate:  {tsr:.1f}% ({n_ts}/{n_total})")
        print(f"  False Arrival Rate: {fa_rate:.1f}% ({n_fa}/{n_total})  <-- Safety Risk")
        print(f"  Obstacle Collision: {col_rate:.1f}% ({n_col}/{n_total})  <-- Simulated contact")
        print(f"  Safe Abstention:    {abs_rate:.1f}% ({n_abs}/{n_total})")
        print(f"  Accepted Decisions: {coverage:.1f}% ({n_ts+n_fa}/{n_total})")
        print(f"  Timeouts:           {n_to}/{n_total}")
        if c_type != "UNSHIELDED":
            print(f"  CBF Residual > 0:  {n_cbf_viol}/{n_total} episodes")
            print(f"  CBF Unchecked:     {n_cbf_unchecked} braking steps")
            print(f"  CBF Exact Fallback: {n_cbf_exact} steps")
            print(f"  CBF Infeasible:    {n_cbf_infeasible} steps")

    print("\n" + "=" * 80)
    labels_to_print = [
        "AEGIS_V9_CBF", "AEGIS_V9_CBF_RANGE_GUARD",
        "AEGIS_V9_CBF_RANGE_WINDOW", "AEGIS_V9_CBF_RANGE_3D_VETO",
    ]
    if "AEGIS_3D_AWARE_CBF" in all_results:
        labels_to_print.append("AEGIS_3D_AWARE_CBF")
    for label in labels_to_print:
        candidate = all_results[label]
        print(f"Observed {label}: {candidate['collision']}/{candidate['episodes']} "
              f"collision episodes; {candidate['false_arrival']}/{candidate['episodes']} "
              "false-arrival episodes.")
    print("These simulation observations do not establish a safety guarantee or real-robot validation.")
    print("=" * 80)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "v9-m5-3d-development-benchmark/1.7",
            "classification": "EXPLORATORY_SIMULATION",
            "random_streams": "SeedSequence(seed).spawn(3): environment, sensors, faults",
            "source_sha256": {
                "benchmark": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "world": hashlib.sha256(Path(world_module.__file__).read_bytes()).hexdigest(),
            },
            "runtime": {
                "python": sys.version.split()[0],
                "numpy": np.__version__,
                "mujoco": mujoco.__version__,
            },
            "seed_start": args.seed_start,
            "n_seeds_per_bias": args.n_seeds,
            "bias_vectors_xyz": [bias.tolist() for bias in biases],
            "max_steps": args.max_steps,
            "range_fault": {
                "bias_m": args.range_bias_m,
                "dropout_probability": args.range_dropout_probability,
                "latency_steps": args.range_latency_steps,
            },
            "summary": all_results,
            "episodes": episode_records,
        }
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
            handle.write("\n")
        print(f"Evidence written: {args.output}")


if __name__ == "__main__":
    main()
