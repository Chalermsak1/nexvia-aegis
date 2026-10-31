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
7. Optional 3D-aware no-active-probing arm: abstains when the same 3D-aware
   controller requests probing or an anchor; ordinary range checks remain enabled.

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
from aegis.v9.anchor_arrival_candidate import AnchorArrivalCandidate
from aegis.v9.stabilized_arrival_candidate import StabilizedArrivalCandidate
from aegis.v9.anchor_recovery_candidate import AnchorRecoveryCandidate
from aegis.v9.sustained_stop_candidate import SustainedStopCandidate
from aegis.v9.velocity_freshness_candidate import FreshVelocityStopCandidate, TimedVelocity
from aegis.v9.bounded_gap_candidate import BoundedGapCandidate
from aegis.v9.dual_velocity_candidate import DualVelocityCandidate
from aegis.v9.recovery_monitor_candidate import RecoveryMonitorCandidate
from aegis.v9.estimated_state_candidate import EstimatedStateCandidate
from aegis.v9.exploratory_sensor_validation import valid_range


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
    trace: list[dict] | None = None,
    anchor_bias_xyz: np.ndarray | None = None,
    anchor_dropout_probability: float = 0.0,
    post_stop_steps: int = 0,
    velocity_bias_xyz: np.ndarray | None = None,
    velocity_dropout_probability: float = 0.0,
    velocity_scale: float = 1.0,
    velocity_latency_steps: int = 0,
    velocity_replay_probability: float = 0.0,
    secondary_velocity_scale: float = 1.0,
    secondary_velocity_dropout_probability: float = 0.0,
    fail_vectors_after_stop_proposal: bool = False,
    on_trace=None,
    navigation_force_method: str = "AXIS_CLIP",
    recovery_steps: int = 100,
) -> dict:
    if type(recovery_steps) is not int or recovery_steps <= 0:
        raise ValueError("recovery_steps must be a positive integer")
    if recovery_steps != 100 and controller_type not in {"AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_RECOVERY_MONITOR"}:
        raise ValueError("alternate recovery budget supports only exploratory recovery arms")
    if navigation_force_method not in {"AXIS_CLIP", "DIRECTION_PRESERVING_PEAK"}:
        raise ValueError("unknown navigation force method")
    if navigation_force_method != "AXIS_CLIP" and controller_type not in {"AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_RECOVERY_MONITOR"}:
        raise ValueError("alternate navigation force supports only exploratory recovery arms")
    if on_trace is not None and (trace is None or not callable(on_trace)):
        raise ValueError("on_trace requires a trace list and a callable")
    if controller_type not in {
        "UNSHIELDED", "CBF_ONLY", "AEGIS_V9_CBF",
        "AEGIS_V9_CBF_RANGE_GUARD", "AEGIS_V9_CBF_RANGE_WINDOW",
        "AEGIS_V9_CBF_RANGE_3D_VETO", "AEGIS_3D_AWARE_CBF", "AEGIS_3D_NO_ACTIVE_PROBE", "AEGIS_3D_STRICT_RANGE", "AEGIS_3D_ANCHOR_GUARD", "AEGIS_3D_STABILIZED", "AEGIS_3D_STABILIZED_RETRY", "AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_SUSTAINED_STOP", "AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP", "AEGIS_3D_DUAL_VELOCITY", "AEGIS_3D_RECOVERY_MONITOR", "AEGIS_3D_ESTIMATED_STATE",
    }:
        raise ValueError(f"Unknown 3D controller type: {controller_type}")
    if not 0.0 <= range_dropout_probability <= 1.0 or range_latency_steps < 0:
        raise ValueError("Range dropout probability must be in [0,1] and latency nonnegative")
    if not isinstance(post_stop_steps, int) or isinstance(post_stop_steps, bool) or post_stop_steps < 0:
        raise ValueError("post_stop_steps must be a nonnegative integer")
    if post_stop_steps and controller_type not in {"AEGIS_3D_AWARE_CBF", "AEGIS_3D_NO_ACTIVE_PROBE", "AEGIS_3D_STRICT_RANGE", "AEGIS_3D_ANCHOR_GUARD", "AEGIS_3D_STABILIZED", "AEGIS_3D_STABILIZED_RETRY", "AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_SUSTAINED_STOP", "AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP", "AEGIS_3D_DUAL_VELOCITY", "AEGIS_3D_RECOVERY_MONITOR", "AEGIS_3D_ESTIMATED_STATE"}:
        raise ValueError("post-stop diagnostics currently support only 3D-aware arms")
    if not math.isfinite(range_bias_m) or np.shape(sensor_bias) != (3,) or not np.isfinite(sensor_bias).all():
        raise ValueError("Range bias and 3D vector-sensor bias must be finite")
    anchor_bias_xyz = np.zeros(3) if anchor_bias_xyz is None else np.asarray(anchor_bias_xyz)
    if anchor_bias_xyz.shape != (3,) or not np.isfinite(anchor_bias_xyz).all() or not 0 <= anchor_dropout_probability <= 1:
        raise ValueError("Anchor bias must be finite and dropout probability in [0,1]")
    velocity_bias_xyz = np.zeros(3) if velocity_bias_xyz is None else np.asarray(velocity_bias_xyz)
    if velocity_bias_xyz.shape != (3,) or not np.isfinite(velocity_bias_xyz).all() or not 0 <= velocity_dropout_probability <= 1:
        raise ValueError("Velocity bias must be finite and dropout probability in [0,1]")
    if not math.isfinite(velocity_scale) or not 0 <= velocity_scale <= 1:
        raise ValueError("velocity_scale must be finite and in [0,1]")
    if type(velocity_latency_steps) is not int or velocity_latency_steps < 0 or not 0 <= velocity_replay_probability <= 1:
        raise ValueError("velocity latency must be a nonnegative integer and replay probability in [0,1]")
    if type(fail_vectors_after_stop_proposal) is not bool:
        raise ValueError("fail_vectors_after_stop_proposal must be boolean")
    if fail_vectors_after_stop_proposal and controller_type not in {"AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_RECOVERY_MONITOR"}:
        raise ValueError("targeted vector-loss injection supports only the paired recovery arms")
    if not math.isfinite(secondary_velocity_scale) or not 0 <= secondary_velocity_scale <= 1 or not 0 <= secondary_velocity_dropout_probability <= 1:
        raise ValueError("secondary velocity scale and dropout must be in [0,1]")
    env_seq, sensor_seq, fault_seq, anchor_seq, anchor_fault_seq, velocity_seq, velocity_fault_seq, replay_seq, secondary_seq, secondary_fault_seq = np.random.SeedSequence(seed).spawn(10)
    rng_env = np.random.default_rng(env_seq)
    rng_sensors = np.random.default_rng(sensor_seq)
    rng_faults = np.random.default_rng(fault_seq)
    rng_anchor = np.random.default_rng(anchor_seq)
    rng_anchor_faults = np.random.default_rng(anchor_fault_seq)
    rng_velocity = np.random.default_rng(velocity_seq)
    rng_velocity_faults = np.random.default_rng(velocity_fault_seq)
    rng_velocity_replay = np.random.default_rng(replay_seq)
    rng_secondary = np.random.default_rng(secondary_seq)
    rng_secondary_fault = np.random.default_rng(secondary_fault_seq)
    state = env.reset(rng_env)

    v9_ctrl = AegisV9Controller() if controller_type.startswith("AEGIS_V9_CBF") else None
    if v9_ctrl:
        v9_ctrl.reset()
    ctrl_3d = Aegis3DAwareController(success_radius=env.config.success_radius, arrival_margin_m=0.0 if controller_type == "AEGIS_3D_STRICT_RANGE" else 0.03) if controller_type in {"AEGIS_3D_AWARE_CBF", "AEGIS_3D_NO_ACTIVE_PROBE", "AEGIS_3D_STRICT_RANGE"} else None
    if controller_type == "AEGIS_3D_ANCHOR_GUARD":
        ctrl_3d = AnchorArrivalCandidate(success_radius=env.config.success_radius)
    if controller_type == "AEGIS_3D_STABILIZED":
        ctrl_3d = StabilizedArrivalCandidate(success_radius=env.config.success_radius)
    if controller_type == "AEGIS_3D_STABILIZED_RETRY":
        ctrl_3d = StabilizedArrivalCandidate(success_radius=env.config.success_radius, max_missing_velocity=2)
    if controller_type == "AEGIS_3D_ANCHOR_RECOVERY":
        ctrl_3d = AnchorRecoveryCandidate(success_radius=env.config.success_radius, recovery_steps=recovery_steps)
    if controller_type == "AEGIS_3D_SUSTAINED_STOP":
        ctrl_3d = SustainedStopCandidate(success_radius=env.config.success_radius)
    if controller_type == "AEGIS_3D_FRESH_VELOCITY":
        ctrl_3d = FreshVelocityStopCandidate(success_radius=env.config.success_radius)
    if controller_type == "AEGIS_3D_BOUNDED_GAP":
        ctrl_3d = BoundedGapCandidate(success_radius=env.config.success_radius)
    if controller_type == "AEGIS_3D_DUAL_VELOCITY":
        ctrl_3d = DualVelocityCandidate(success_radius=env.config.success_radius)
    if controller_type == "AEGIS_3D_RECOVERY_MONITOR":
        ctrl_3d = RecoveryMonitorCandidate(success_radius=env.config.success_radius, recovery_steps=recovery_steps)
    if controller_type == "AEGIS_3D_ESTIMATED_STATE":
        ctrl_3d = EstimatedStateCandidate(success_radius=env.config.success_radius)
    if ctrl_3d:
        ctrl_3d.reset()

    collision_occurred = bool(state.get("safety_violation", False))
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
    anchor_queries = 0
    anchor_valid_readings = 0
    injected_vector_loss_steps = 0
    post_stop = None
    velocity_history = []
    previous_velocity_delivery = None
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
            u_des = 1.2 * meas_a_3d - 0.5 * vel
            arrival_candidate = bool(np.linalg.norm(meas_a_3d) < 0.22)
            dec_type = "STOP" if arrival_candidate else "NAVIGATE"
            if trace is not None:
                trace.append({
                    "step": step, "position": pos.tolist(), "target": target.tolist(),
                    "true_distance": true_dist, "velocity": vel.tolist(),
                    "action": [0.0, 0.0, 0.0] if arrival_candidate else u_des.tolist(),
                    "decision": dec_type,
                    "effective_decision": dec_type,
                    "vector_fault_injected": False,
                })
                if on_trace is not None:
                    on_trace(dict(trace[-1]))
            if arrival_candidate:
                if true_dist <= env.config.success_radius:
                    true_success = True
                else:
                    false_arrival = True
                if post_stop_steps:
                    after = []
                    for _ in range(post_stop_steps):
                        observed = env.step(np.zeros(3), force_braking=True)
                        after.append({"distance": float(observed["distance"]),
                                      "speed": float(np.linalg.norm(observed["robot_velocity"])),
                                      "collision": bool(observed["safety_violation"]),
                                      "cbf_residual": observed.get("cbf_constraint_residual")})
                    post_stop = {"decision_distance": true_dist,
                                 "decision_speed": float(np.linalg.norm(vel)),
                                 "steps": after}
                break
            # Direct tracking of biased sensor without CBF
            f_total = np.clip(u_des, -env.config.control_force_limit, env.config.control_force_limit)
            f_total[2] += env.config.robot_mass * 9.81
            env.data.xfrc_applied[env.robot_body_id, :3] = f_total
            import mujoco
            mujoco.mj_step(env.model, env.data)
            env.step_count += 1
            state = env.get_state()
            observe_step(state)

        elif controller_type == "CBF_ONLY":
            u_des = 1.2 * meas_a_3d - 0.5 * vel
            arrival_candidate = bool(np.linalg.norm(meas_a_3d) < 0.22)
            dec_type = "STOP" if arrival_candidate else "NAVIGATE"
            if trace is not None:
                trace.append({
                    "step": step, "position": pos.tolist(), "target": target.tolist(),
                    "true_distance": true_dist, "velocity": vel.tolist(),
                    "action": [0.0, 0.0, 0.0] if arrival_candidate else u_des.tolist(),
                    "decision": dec_type,
                    "effective_decision": dec_type,
                    "vector_fault_injected": False,
                })
                if on_trace is not None:
                    on_trace(dict(trace[-1]))
            if arrival_candidate:
                if true_dist <= env.config.success_radius:
                    true_success = True
                else:
                    false_arrival = True
                if post_stop_steps:
                    after = []
                    for _ in range(post_stop_steps):
                        observed = env.step(np.zeros(3), force_braking=True)
                        after.append({"distance": float(observed["distance"]),
                                      "speed": float(np.linalg.norm(observed["robot_velocity"])),
                                      "collision": bool(observed["safety_violation"]),
                                      "cbf_residual": observed.get("cbf_constraint_residual")})
                    post_stop = {"decision_distance": true_dist,
                                 "decision_speed": float(np.linalg.norm(vel)),
                                 "steps": after}
                break
            # Uses CBF to prevent obstacle collision, but trusts flawed sensor A
            state = env.step(u_des, force_braking=False)
            observe_step(state)

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
                anc_noise = rng_anchor.normal(0.0, 0.04, size=2)
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

        elif controller_type in {"AEGIS_3D_AWARE_CBF", "AEGIS_3D_NO_ACTIVE_PROBE", "AEGIS_3D_STRICT_RANGE", "AEGIS_3D_ANCHOR_GUARD", "AEGIS_3D_STABILIZED", "AEGIS_3D_STABILIZED_RETRY", "AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_SUSTAINED_STOP", "AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP", "AEGIS_3D_DUAL_VELOCITY", "AEGIS_3D_RECOVERY_MONITOR", "AEGIS_3D_ESTIMATED_STATE"}:
            assert ctrl_3d is not None
            phase_before = getattr(ctrl_3d, "phase", None)
            vector_loss = fail_vectors_after_stop_proposal and getattr(ctrl_3d, "phase", "BASE") in {"BRAKING", "ANCHOR", "RECOVERY"}
            injected_vector_loss_steps += int(vector_loss)
            rd_a = SensorReading(
                estimate=meas_a_3d,
                sigma=0.05,
                valid=not vector_loss,
                anomaly=False,
                dropped=vector_loss,
                bias=np.zeros(3),
                drift=np.zeros(3),
            )
            rd_b = SensorReading(
                estimate=meas_b_3d,
                sigma=0.05,
                valid=not vector_loss,
                anomaly=False,
                dropped=vector_loss,
                bias=np.zeros(3),
                drift=np.zeros(3),
            )
            rd_r = RangeReading(
                # A delayed reading describes an earlier position and cannot
                # corroborate arrival without motion compensation.
                distance=range_meas if range_fresh else 0.0,
                sigma=0.05,
                valid=range_fresh,
                dropped=not range_fresh,
            )
            anc_reading = None
            if next_query_anchor:
                anchor_queries += 1
                anc_noise = rng_anchor.normal(0.0, 0.04, size=3)
                anchor_valid = not (anchor_dropout_probability > 0 and rng_anchor_faults.random() < anchor_dropout_probability)
                anchor_valid_readings += int(anchor_valid)
                anc_reading = AnchorReading(
                    estimate=true_delta_3d + anc_noise + anchor_bias_xyz,
                    sigma=0.04,
                    valid=anchor_valid,
                    queried=True,
                    cost_accrued=0.05,
                )

            anchor_requested = next_query_anchor
            velocity_observation = None
            timed_velocity = None
            secondary_observation = None
            if controller_type in {"AEGIS_3D_STABILIZED", "AEGIS_3D_STABILIZED_RETRY", "AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_SUSTAINED_STOP", "AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP", "AEGIS_3D_DUAL_VELOCITY", "AEGIS_3D_RECOVERY_MONITOR", "AEGIS_3D_ESTIMATED_STATE"}:
                sampled = velocity_scale * vel + velocity_bias_xyz + rng_velocity.normal(0.0, 0.02, size=3)
                if velocity_dropout_probability > 0 and rng_velocity_faults.random() < velocity_dropout_probability:
                    sampled = None
                velocity_history.append(None if sampled is None else TimedVelocity(sampled, step, step * env.config.timestep))
                timed_velocity = velocity_history[-velocity_latency_steps - 1] if len(velocity_history) > velocity_latency_steps else None
                if velocity_replay_probability > 0 and rng_velocity_replay.random() < velocity_replay_probability:
                    timed_velocity = previous_velocity_delivery
                previous_velocity_delivery = timed_velocity
                velocity_observation = timed_velocity.vector if timed_velocity is not None else None
                if controller_type in {"AEGIS_3D_DUAL_VELOCITY", "AEGIS_3D_ESTIMATED_STATE"}:
                    secondary_observation = secondary_velocity_scale * vel + rng_secondary.normal(0.0, 0.02, size=3)
                    if secondary_velocity_dropout_probability > 0 and rng_secondary_fault.random() < secondary_velocity_dropout_probability:
                        secondary_observation = None
                    secondary = TimedVelocity(secondary_observation, step, step * env.config.timestep) if secondary_observation is not None else None
                    action_3d, dec_type, nav_vector, next_query_anchor = ctrl_3d.update(
                        rd_a, rd_b, rd_r, anchor_reading=anc_reading, step=step, velocity_reading=timed_velocity,
                        secondary_velocity_reading=secondary, now_seconds=step * env.config.timestep)
                elif controller_type in {"AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP"}:
                    action_3d, dec_type, nav_vector, next_query_anchor = ctrl_3d.update(
                        rd_a, rd_b, rd_r, anchor_reading=anc_reading, step=step,
                        velocity_reading=timed_velocity, now_seconds=step * env.config.timestep)
                else:
                    action_3d, dec_type, nav_vector, next_query_anchor = ctrl_3d.update(
                        rd_a, rd_b, rd_r, anchor_reading=anc_reading, step=step, velocity_reading=velocity_observation)
            else:
                action_3d, dec_type, nav_vector, next_query_anchor = ctrl_3d.update(
                    rd_a, rd_b, rd_r, anchor_reading=anc_reading, step=step)
            original_action_3d = action_3d.copy()
            navigation_force_transformed = False
            # Only inherited BASE guidance has kp=1.2. Recovery uses a
            # different, bounded anchor command and must never be rescaled.
            if (navigation_force_method == "DIRECTION_PRESERVING_PEAK"
                    and phase_before == "BASE" and ctrl_3d.phase == "BASE"
                    and dec_type in {"NAVIGATE", "PROBE"}):
                desired = 1.2 * np.asarray(nav_vector, dtype=float)
                if desired.shape != (3,) or not np.isfinite(desired).all():
                    raise ValueError("invalid alternate navigation vector")
                limit = ctrl_3d.cbf_force_limit
                action_3d = desired * min(1.0, limit / max(float(np.max(np.abs(desired))), limit))
                navigation_force_transformed = True
            if trace is not None:
                # Ground truth is recorded only after update and is never passed
                # to the controller except through the simulated observations.
                trace.append({
                    "step": step, "position": pos.tolist(), "target": target.tolist(),
                    "true_distance": true_dist, "velocity": vel.tolist(),
                    "velocity_observation": velocity_observation.tolist() if velocity_observation is not None else None,
                    "secondary_velocity_observation": secondary_observation.tolist() if secondary_observation is not None else None,
                    "velocity_crosscheck_reason": ctrl_3d.crosscheck_reason if controller_type == "AEGIS_3D_DUAL_VELOCITY" else None,
                    "velocity_sequence": timed_velocity.sequence if timed_velocity is not None else None,
                    "velocity_acquired_seconds": timed_velocity.acquired_seconds if timed_velocity is not None else None,
                    "velocity_gate_reason": ctrl_3d.velocity_gate.reason if controller_type in {"AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP"} else None,
                    "gap_bridged": ctrl_3d.gap_bridged if controller_type == "AEGIS_3D_BOUNDED_GAP" else False,
                    "gap_speed_bound": ctrl_3d.last_gap_bound if controller_type == "AEGIS_3D_BOUNDED_GAP" else None,
                    "sensor_a": meas_a_3d.tolist(), "sensor_b": meas_b_3d.tolist(),
                    "vector_fault_injected": vector_loss,
                    "range": float(range_meas) if range_valid else None,
                    "range_valid": bool(range_valid),
                    "range_fresh": bool(range_fresh),
                    "range_raw_sample": float(raw_range),
                    "range_raw_transport_valid": bool(raw_valid),
                    "range_controller_distance": float(rd_r.distance),
                    "range_semantically_valid": valid_range(rd_r),
                    "range_validation_status": "VALID" if valid_range(rd_r) else (
                        "NEGATIVE_DISTANCE" if range_fresh and math.isfinite(range_meas) and range_meas < 0 else "INVALID_OR_UNAVAILABLE"),
                    "recovery_steps": getattr(ctrl_3d, "recovery_steps", None),
                    "stabilization_wait_steps": getattr(ctrl_3d, "wait_steps", None),
                    "missing_velocity_count": getattr(ctrl_3d, "missing_velocity_count", None),
                    "anchor_requested": bool(anchor_requested),
                    "anchor": anc_reading.estimate.tolist() if anc_reading is not None else None,
                    "anchor_valid": bool(anc_reading.valid) if anc_reading is not None else None,
                    "action": action_3d.tolist(), "decision": dec_type,
                    "original_action": original_action_3d.tolist(),
                    "navigation_force_method": navigation_force_method,
                    "navigation_force_transformed": navigation_force_transformed,
                    "phase_before": phase_before, "phase_after": getattr(ctrl_3d, "phase", None),
                    "nav_vector": nav_vector.tolist(), "mode": ctrl_3d.mode,
                    "terminal_reason": ctrl_3d.terminal_reason,
                    "low_speed_samples": getattr(ctrl_3d, "low_speed_samples", None),
                    "postproposal_monitor_reason": ctrl_3d.postproposal_monitor_reason if controller_type == "AEGIS_3D_RECOVERY_MONITOR" else None,
                    "next_query_anchor": bool(next_query_anchor),
                    "calibration_count_a": ctrl_3d.cal_a.sample_count,
                    "calibration_count_b": ctrl_3d.cal_b.sample_count,
                    "bias_est_a": ctrl_3d.cal_a.bias_est.tolist(),
                    "bias_est_b": ctrl_3d.cal_b.bias_est.tolist(),
                    "arrival_range_samples": list(ctrl_3d.arrival_range_samples),
                })
            if controller_type == "AEGIS_3D_NO_ACTIVE_PROBE" and (dec_type == "PROBE" or next_query_anchor):
                # The ablation keeps the same monitors and range confirmation,
                # but terminates instead of probing or obtaining an anchor.
                dec_type = "ABSTAIN"
                next_query_anchor = False

            if trace is not None:
                trace[-1]["effective_decision"] = dec_type
                if on_trace is not None:
                    on_trace(dict(trace[-1]))

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
                if post_stop_steps:
                    # Separate diagnostic horizon; keep original STOP score,
                    # counts, and state intact. Ground truth is used for
                    # observation only, never for controller decisions.
                    after = []
                    for _ in range(post_stop_steps):
                        observed = env.step(np.zeros(3), force_braking=True)
                        after.append({"distance": float(observed["distance"]),
                                      "speed": float(np.linalg.norm(observed["robot_velocity"])),
                                      "collision": bool(observed["safety_violation"]),
                                      "cbf_residual": observed.get("cbf_constraint_residual")})
                    post_stop = {"decision_distance": true_dist,
                                 "decision_speed": float(np.linalg.norm(vel)),
                                 "steps": after}
                break
            else:
                if controller_type == "AEGIS_3D_ESTIMATED_STATE":
                    u_des_3d = action_3d + ctrl_3d.compute_damping()
                else:
                    u_des_3d = action_3d - 0.5 * vel
                force_brake = (dec_type == "VERIFY")
                state = env.step(u_des_3d, force_braking=force_brake)
                observe_step(state)

    else:
        timeout = True

    result = {
        "controller": controller_type,
        "navigation_force_method": navigation_force_method,
        "recovery_steps_limit": recovery_steps,
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
        "anchor_queries": anchor_queries,
        "anchor_valid_readings": anchor_valid_readings,
    }
    if post_stop_steps:
        result["post_stop"] = post_stop
    if controller_type in {"AEGIS_3D_FRESH_VELOCITY", "AEGIS_3D_BOUNDED_GAP"}:
        result["velocity_gate_rejections"] = ctrl_3d.velocity_gate.rejections
    if controller_type == "AEGIS_3D_BOUNDED_GAP":
        result["bridged_velocity_steps"] = ctrl_3d.bridged_steps
    if controller_type == "AEGIS_3D_DUAL_VELOCITY":
        result["velocity_comparisons"] = ctrl_3d.comparisons
        result["velocity_disagreements"] = ctrl_3d.disagreements
    if controller_type == "AEGIS_3D_RECOVERY_MONITOR":
        result["postproposal_monitor_steps"] = ctrl_3d.postproposal_monitor_steps
        result["postproposal_monitor_reason"] = ctrl_3d.postproposal_monitor_reason
    if fail_vectors_after_stop_proposal:
        result["injected_vector_loss_steps"] = injected_vector_loss_steps
    return result


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
    parser.add_argument("--include-3d-no-probe", action="store_true", help="Include paired 3D-aware and no-active-probing ablation arms")
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
    if args.include_3d_aware or args.include_3d_no_probe:
        controllers.append("AEGIS_3D_AWARE_CBF")
    if args.include_3d_no_probe:
        controllers.append("AEGIS_3D_NO_ACTIVE_PROBE")

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
    if "AEGIS_3D_NO_ACTIVE_PROBE" in all_results:
        labels_to_print.append("AEGIS_3D_NO_ACTIVE_PROBE")
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
            "random_streams": "SeedSequence(seed).spawn(4): environment, sensors, faults, anchor",
            "source_sha256": {
                "benchmark": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "world": hashlib.sha256(Path(world_module.__file__).read_bytes()).hexdigest(),
                "controller_3d": hashlib.sha256(Path(sys.modules[Aegis3DAwareController.__module__].__file__).read_bytes()).hexdigest(),
                "exploratory_sensor_validation": hashlib.sha256(Path(sys.modules["aegis.v9.exploratory_sensor_validation"].__file__).read_bytes()).hexdigest(),
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
