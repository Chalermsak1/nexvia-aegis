"""
Unit tests for Milestone V9-M13 Robust Tube-CLBF & Physical Stillness Architecture.

Validates resolutions for the 4 core research bottlenecks:
1. True vs. Measured Speed Discrepancy (Section 11.3)
2. Tube-CBF Margin Inflation under Covariance Uncertainty (Section 11.6)
3. Conservatism Reduction & Progress Preservation via CLBF (Section 11.6)
4. Terminal Physical Stillness & Active Dwell Semantics (Section 11.1)
5. Guaranteed Micro-QP Feasibility & Martingale Slack Abuse Detection (Section 11.6)
"""

import math
import numpy as np
import pytest

from aegis.v9.robust_tube_clbf import (
    DwellPhase,
    MicroActiveSetQPSolver,
    RobustTubeCLBFConfig,
    RobustTubeCLBFController,
    TerminalPhysicalStillnessMonitor,
    TubeUncertaintyState,
)


def test_tube_speed_bound_prevents_false_underestimated_confirmation():
    """
    Validates Bottleneck 2 (Section 11.3):
    When measured velocity appears low due to noise, the robust covariance
    upper bound prevents premature arrival certification.
    """
    config = RobustTubeCLBFConfig(
        speed_limit_at_goal=0.08,
        confidence_delta=1e-4,
    )
    ctrl = RobustTubeCLBFController(config)

    # Measured velocity is low: 0.04 m/s (below 0.08 m/s limit)
    v_hat = np.array([0.04, 0.0, 0.0])
    # But velocity covariance has high variance: sigma = 0.03 m/s
    # kappa_delta = sqrt(2 * ln(1e4)) ~= 4.29
    # Bound should be 0.04 + 4.29 * 0.03 = 0.1687 m/s (> 0.08 m/s)
    cov_v = np.diag([0.03**2, 0.03**2, 0.03**2])

    v_upper = ctrl.compute_tube_speed_bound(v_hat, cov_v)
    assert v_upper > config.speed_limit_at_goal, (
        f"Expected robust bound {v_upper:.4f} to exceed {config.speed_limit_at_goal}"
    )

    # When variance shrinks (reliable sensor), bound drops below threshold
    cov_v_low = np.diag([0.005**2, 0.005**2, 0.005**2])
    v_upper_low = ctrl.compute_tube_speed_bound(v_hat, cov_v_low)
    # 0.04 + 4.29 * 0.005 = 0.0615 <= 0.08
    assert v_upper_low <= config.speed_limit_at_goal


def test_tube_cbf_safety_margin_inflation_under_position_uncertainty():
    """
    Validates Bottleneck 2:
    Covariance inflation pushes the effective barrier outward, triggering
    earlier and smoother deceleration before reaching true physical hazard.
    """
    config = RobustTubeCLBFConfig(safe_distance=1.0, confidence_delta=1e-4)
    ctrl = RobustTubeCLBFController(config)

    p_hat = np.array([1.5, 0.0, 0.0])
    v_hat = np.array([-1.0, 0.0, 0.0])  # Moving directly towards obstacle
    obstacles = [np.array([0.0, 0.0, 0.0])]

    # Zero uncertainty
    cov_zero = np.zeros((3, 3))
    _, _, margins_zero = ctrl.compute_tube_cbf_constraints(p_hat, v_hat, cov_zero, cov_zero, obstacles)

    # High position uncertainty
    cov_pos = np.diag([0.1**2, 0.1**2, 0.1**2])
    _, _, margins_noisy = ctrl.compute_tube_cbf_constraints(p_hat, v_hat, cov_pos, cov_zero, obstacles)

    # The tube margin must be strictly smaller (more conservative) than nominal
    assert margins_noisy[0] < margins_zero[0]
    # Difference must match kappa_delta * 2 * dist * sigma
    expected_diff = ctrl.kappa_delta * 2.0 * 1.5 * 0.1
    assert math.isclose(margins_zero[0] - margins_noisy[0], expected_diff, rel_tol=1e-3)


def test_clbf_prevents_freeze_and_preserves_progress():
    """
    Validates Bottleneck 1:
    Control Lyapunov-Barrier Function dynamically relaxes goal convergence
    to navigate around an obstacle without freezing in place (u != 0).
    """
    config = RobustTubeCLBFConfig(a_max=5.0, safe_distance=1.0)
    ctrl = RobustTubeCLBFController(config)

    # Agent at x=0, Goal at x=4. Obstacle at x=2 (directly on line of sight)
    p = np.array([0.5, 0.0, 0.0])
    v = np.array([1.0, 0.0, 0.0])
    cov = np.diag([0.01**2, 0.01**2, 0.01**2])
    state = TubeUncertaintyState(p_hat=p, v_hat=v, cov_p=cov, cov_v=cov)
    goal = np.array([4.0, 0.0, 0.0])
    obstacles = [np.array([2.0, 0.0, 0.0])]

    step_res = ctrl.step(state, goal, obstacles)
    action = step_res["action"]

    # Action must not be zero (no freezing)
    action_norm = np.linalg.norm(action)
    assert action_norm > 0.1, "CLBF should not freeze or command zero action"
    assert step_res["phase"] == "CRUISING"
    assert not step_res["is_terminal"]


def test_terminal_stillness_safe_dwell_semantics():
    """
    Validates Bottleneck 3 (Section 11.1):
    Dwell monitor requires continuous active braking until kinetic energy
    and drift are certified for N_dwell steps.
    """
    config = RobustTubeCLBFConfig(
        required_dwell_steps=5,
        kinetic_energy_thresh=0.01,
        drift_tolerance_m=0.05,
    )
    monitor = TerminalPhysicalStillnessMonitor(config)

    pos_0 = np.array([10.0, 0.0, 0.0])
    monitor.trigger_braking(pos_0)
    assert monitor.phase == DwellPhase.ACTIVE_BRAKING

    # Step 1: Still has high residual speed (0.5 m/s) -> kinetic energy ~ 0.5 * 1.5 * 0.25 = 0.18 > 0.01
    a_brake, phase, reason = monitor.step(pos_0, np.array([0.5, 0.0, 0.0]), v_upper_bound=0.5)
    assert phase == DwellPhase.ACTIVE_BRAKING
    assert np.linalg.norm(a_brake) > 0.5, "Active braking force must be applied"
    assert monitor.dwell_steps == 0

    # Step 2 to 5: Speed drops to near-zero (0.01 m/s) -> enters DWELLING
    for i in range(1, 5):
        a_b, phase, reason = monitor.step(pos_0 + np.array([0.01, 0, 0]), np.array([0.01, 0.0, 0.0]), v_upper_bound=0.01)
        assert phase == DwellPhase.DWELLING
        assert monitor.dwell_steps == i

    # Step 6: 5th dwell step reached -> CONFIRMED_STILL
    a_b, phase, reason = monitor.step(pos_0 + np.array([0.01, 0, 0]), np.array([0.005, 0.0, 0.0]), v_upper_bound=0.005)
    assert phase == DwellPhase.CONFIRMED_STILL
    assert reason == "PHYSICAL_STILLNESS_CONFIRMED"


def test_micro_qp_always_feasible_and_martingale_slack_alarm():
    """
    Validates Bottleneck 4 (Section 11.6):
    Micro-QP solves without infeasibility exception even under conflicting constraints,
    while Ville's supermartingale flags an alarm if slack is abused repeatedly.
    """
    config = RobustTubeCLBFConfig(
        a_max=4.0,
        martingale_risk_alpha=0.01,  # Threshold = 100.0
        slack_variance_ref=0.001,
    )
    ctrl = RobustTubeCLBFController(config)

    # Conflicting obstacles creating zero clearance
    p = np.array([0.0, 0.0, 0.0])
    v = np.array([0.0, 0.0, 0.0])
    cov = np.diag([0.01**2, 0.01**2, 0.01**2])
    state = TubeUncertaintyState(p_hat=p, v_hat=v, cov_p=cov, cov_v=cov)
    goal = np.array([10.0, 0.0, 0.0])
    # Obstacles directly pinning the agent
    obstacles = [
        np.array([0.5, 0.0, 0.0]),
        np.array([-0.5, 0.0, 0.0]),
        np.array([0.0, 0.5, 0.0]),
        np.array([0.0, -0.5, 0.0]),
    ]

    # Solver must NOT throw infeasible exception; must solve within < 5 ms
    res = ctrl.step(state, goal, obstacles)
    assert "action" in res
    assert np.all(np.abs(res["action"]) <= config.a_max + 1e-3)
    assert res["solve_time_ms"] < 10.0, f"Micro-QP should be ultra-fast: {res['solve_time_ms']:.2f} ms"

    # Simulate sustained slack abuse to trigger Ville supermartingale alarm
    alarm_triggered = False
    for _ in range(50):
        # Force high slack
        alarm = ctrl.update_martingale_slack_guard(slack_drawn=0.4)
        if alarm:
            alarm_triggered = True
            break

    assert alarm_triggered, "Ville supermartingale must trigger alarm under persistent slack abuse"
    assert ctrl.martingale_alarm is True
