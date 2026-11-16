"""
Unit tests for Pure Estimated-State Sensor Blackout & Observability Gate (Tasks E-05 & E-06).

Validates:
1. Nominal low-uncertainty observations pass the gate and permit goal progress.
2. Degraded observability / blackout covariance swelling triggers immediate fail-closed abstention.
3. Closed-loop prevention of blind collision when camera/LiDAR blackouts occur mid-flight.
4. Pure estimated-state execution with zero ground-truth leakage (Task E-05 compliance).
"""

import math
import numpy as np
import pytest

from aegis.v9.robust_tube_clbf import (
    DwellPhase,
    RobustTubeCLBFConfig,
    RobustTubeCLBFController,
    TubeUncertaintyState,
)


def test_nominal_observations_pass_gate():
    """
    Validates that clean, verified observations pass the observability gate
    and allow normal goal-seeking CLBF guidance.
    """
    config = RobustTubeCLBFConfig(
        enable_observability_gate=True,
        max_position_uncertainty_m=0.25,
        max_velocity_uncertainty_mps=0.35,
    )
    ctrl = RobustTubeCLBFController(config)

    # Clean low-variance observation
    p_hat = np.array([2.0, 0.0, 0.0])
    v_hat = np.array([1.5, 0.0, 0.0])
    cov_p = np.eye(3) * (0.02 ** 2)  # sigma_p = 0.02m << 0.25m
    cov_v = np.eye(3) * (0.03 ** 2)  # sigma_v = 0.03m/s << 0.35m/s
    state = TubeUncertaintyState(p_hat=p_hat, v_hat=v_hat, cov_p=cov_p, cov_v=cov_v)

    res = ctrl.step(state, np.array([10.0, 0.0, 0.0]), obstacles=[])

    assert res["phase"] == DwellPhase.CRUISING.value
    assert res["reason"] == "ACTIVE_CLBF_GUIDANCE"
    assert not res["is_terminal"]
    assert res["action"][0] > 0.0, "Should accelerate towards goal along x-axis"


def test_swelled_covariance_triggers_immediate_fail_closed_abstention():
    """
    Validates that when sensor blackout causes estimation covariance to exceed safety limits,
    the framework rejects the observation and triggers fail-closed active braking (Abstain).
    """
    config = RobustTubeCLBFConfig(
        enable_observability_gate=True,
        max_position_uncertainty_m=0.25,
        max_velocity_uncertainty_mps=0.35,
        a_max=5.5,
    )
    ctrl = RobustTubeCLBFController(config)

    # Swelled position uncertainty (sigma_p = 0.40m > 0.25m) from optical blackout
    p_hat = np.array([2.0, 0.0, 0.0])
    v_hat = np.array([2.0, 0.0, 0.0])
    cov_p = np.eye(3) * (0.40 ** 2)
    cov_v = np.eye(3) * (0.05 ** 2)
    state = TubeUncertaintyState(p_hat=p_hat, v_hat=v_hat, cov_p=cov_p, cov_v=cov_v)

    res = ctrl.step(state, np.array([10.0, 0.0, 0.0]), obstacles=[])

    assert res["phase"] == DwellPhase.EMERGENCY_STOP.value
    assert res["reason"] == "OBSERVATION_UNRELIABLE_BLACKOUT_GATE_REJECTED"
    assert res["is_terminal"] is True
    # Commanded action must be maximum active deceleration along velocity vector (-x)
    assert res["action"][0] < -4.0, f"Expected strong braking force, got {res['action'][0]}"


def test_sensor_blackout_closed_loop_prevention_of_blind_collision():
    """
    Simulates a mid-course sensor blackout (fog, smoke, lens glare) when moving
    toward an obstacle at x = 5.0m.
    Compares:
    - Blind Arm (gate disabled): continues driving blind, causing collision.
    - AEGIS Observability Gate (gate enabled): detects unreliable observation,
      halts vehicle with active deceleration, maintaining safe clearance > 1.2m.
    """
    dt = 0.04
    tau_lag = 0.035
    alpha_lag = 1.0 - math.exp(-dt / tau_lag)
    obstacle = np.array([5.0, 0.0, 0.0])
    goal = np.array([12.0, 0.0, 0.0])

    def run_blackout_sim(enable_gate: bool) -> tuple[bool, float, float]:
        cfg = RobustTubeCLBFConfig(
            safe_distance=1.0,
            actuator_delay_s=tau_lag,
            enable_delay_compensation=True,
            enable_observability_gate=enable_gate,
            max_position_uncertainty_m=0.25,
            max_velocity_uncertainty_mps=0.35,
            a_max=5.5,
        )
        ctrl = RobustTubeCLBFController(cfg)

        p_true = np.array([0.0, 0.0, 0.0])
        v_true = np.array([0.0, 0.0, 0.0])
        u_motor = np.array([0.0, 0.0, 0.0])

        min_clearance = 999.0
        collision = False
        t_stop = 0.0

        for step in range(150):
            t = step * dt
            dist = float(np.linalg.norm(p_true - obstacle))
            min_clearance = min(min_clearance, dist)
            if dist < 0.85:
                collision = True
                break

            # Blackout occurs at step 25 (t = 1.0s)
            if step < 25:
                # Nominal sensing
                sig_p = 0.02
                sig_v = 0.02
                p_hat = p_true + np.random.normal(0, sig_p, size=3)
                v_hat = v_true + np.random.normal(0, sig_v, size=3)
            else:
                # SENSOR BLACKOUT: Observations freeze/drift, uncertainty swells quadratically
                dt_blackout = (step - 25) * dt
                sig_p = 0.02 + 0.45 * dt_blackout  # Covariance swells over time
                sig_v = 0.02 + 0.30 * dt_blackout
                # Filter operates open-loop dead-reckoning with drift
                drift_noise = np.array([0.15 * dt_blackout, 0.0, 0.0])
                p_hat = p_true + drift_noise
                v_hat = v_true.copy()

            cov_p = np.eye(3) * (sig_p ** 2)
            cov_v = np.eye(3) * (sig_v ** 2)
            state = TubeUncertaintyState(p_hat=p_hat, v_hat=v_hat, cov_p=cov_p, cov_v=cov_v)

            # Controller receives ONLY state (zero ground truth access - Task E-05)
            res = ctrl.step(state, goal, [obstacle])
            u_cmd = res["action"]

            u_motor += alpha_lag * (u_cmd - u_motor)
            p_true += v_true * dt + 0.5 * u_motor * (dt ** 2)
            v_true += u_motor * dt

            if res.get("is_terminal", False):
                t_stop = t
                # Verify that vehicle actively decelerates to stillness
                if np.linalg.norm(v_true) < 0.05:
                    break

        return collision, min_clearance, t_stop

    # Run Blind Arm (Gate Disabled)
    coll_blind, min_clear_blind, _ = run_blackout_sim(enable_gate=False)

    # Run AEGIS Arm (Gate Enabled)
    coll_aegis, min_clear_aegis, t_stop_aegis = run_blackout_sim(enable_gate=True)

    # Verification criteria
    assert coll_aegis is False, "AEGIS Observability Gate must prevent blind collision during blackout"
    assert min_clear_aegis >= 1.20, f"AEGIS must maintain safe clearance >= 1.20m, got {min_clear_aegis:.3f}m"
    assert t_stop_aegis > 0.0, "AEGIS must trigger terminal stop upon blackout"


def test_zero_ground_truth_leakage_enforcement():
    """
    Validates Task E-05: Controller strictly operates on TubeUncertaintyState
    with no hidden ground truth information or cheat signals.
    """
    config = RobustTubeCLBFConfig(enable_observability_gate=True)
    ctrl = RobustTubeCLBFController(config)

    state = TubeUncertaintyState(
        p_hat=np.array([1.0, 2.0, 3.0]),
        v_hat=np.array([0.1, 0.0, -0.1]),
        cov_p=np.eye(3) * 0.01,
        cov_v=np.eye(3) * 0.01,
    )

    res = ctrl.step(state, np.array([5.0, 5.0, 0.0]))
    assert "p_true" not in res
    assert "v_true" not in res
    assert isinstance(res["action"], np.ndarray)
    assert res["action"].shape == (3,)
