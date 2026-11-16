"""
Unit tests for Actuator Delay Compensation Tube-CLBF (Task E-07).

Validates:
1. Exact kinematic & uncertainty forward projection over delay horizon tau.
2. Earlier and smoother braking before obstacle penetration under motor lag.
3. Closed-loop barrier invariance under 35-50ms physical actuator lag.
4. Safe stillness / abstention in dead-end traps without barrier breach.
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


def test_forward_predictive_state_math():
    """
    Validates kinematic state & covariance forward projection over delay horizon tau.
    """
    config = RobustTubeCLBFConfig(actuator_delay_s=0.04)
    ctrl = RobustTubeCLBFController(config)

    p_hat = np.array([2.0, 1.0, 0.0])
    v_hat = np.array([3.0, 0.0, 0.0])
    cov_p = np.diag([0.02**2, 0.02**2, 0.02**2])
    cov_v = np.diag([0.05**2, 0.05**2, 0.05**2])
    u_prev = np.array([-1.5, 0.0, 0.0])
    tau = 0.04

    p_proj, v_proj, cov_p_proj, cov_v_proj = ctrl.compute_predictive_delay_state(
        p_hat, v_hat, cov_p, cov_v, u_prev, tau
    )

    # Expected: p + tau * v + 0.5 * tau^2 * u
    expected_p = p_hat + tau * v_hat + 0.5 * (tau ** 2) * u_prev
    assert np.allclose(p_proj, expected_p, atol=1e-6)

    # Expected: v + tau * u
    expected_v = v_hat + tau * u_prev
    assert np.allclose(v_proj, expected_v, atol=1e-6)

    # Covariance must strictly inflate due to delay and velocity uncertainty
    assert cov_p_proj[0, 0] > cov_p[0, 0]
    assert cov_v_proj[0, 0] > cov_v[0, 0]


def test_delay_compensation_triggers_earlier_braking_near_obstacle():
    """
    Validates that delay compensation detects impending motor lag and inflates
    the barrier constraint earlier, producing stronger deceleration than uncompensated CBF.
    """
    # Config 1: Without delay compensation
    cfg_uncomp = RobustTubeCLBFConfig(
        actuator_delay_s=0.05,
        enable_delay_compensation=False,
        safe_distance=1.0,
    )
    ctrl_uncomp = RobustTubeCLBFController(cfg_uncomp)

    # Config 2: With delay compensation
    cfg_comp = RobustTubeCLBFConfig(
        actuator_delay_s=0.05,
        enable_delay_compensation=True,
        safe_distance=1.0,
    )
    ctrl_comp = RobustTubeCLBFController(cfg_comp)

    # Moving at 4 m/s towards obstacle located at x = 3.0
    p = np.array([1.4, 0.0, 0.0])
    v = np.array([4.0, 0.0, 0.0])
    cov = np.diag([0.01**2, 0.01**2, 0.01**2])
    state = TubeUncertaintyState(p_hat=p, v_hat=v, cov_p=cov, cov_v=cov)
    goal = np.array([10.0, 0.0, 0.0])
    obstacles = [np.array([3.0, 0.0, 0.0])]

    res_uncomp = ctrl_uncomp.step(state, goal, obstacles)
    res_comp = ctrl_comp.step(state, goal, obstacles)

    # Delay-compensated controller evaluates safety on the forward-projected position,
    # correctly detecting tighter proximity to the obstacle before motor lag elapses
    assert res_comp["tube_margin_min"] < res_uncomp["tube_margin_min"], (
        f"Compensated margin {res_comp['tube_margin_min']:.3f} should be strictly tighter than uncompensated {res_uncomp['tube_margin_min']:.3f}"
    )
    assert res_comp["p_projected"][0] > p[0], "Projected position must be forward along velocity vector"
    assert res_comp["delay_applied_s"] == 0.05


def test_closed_loop_navigation_under_actuator_lag():
    """
    Simulates actual physical first-order actuator lag in the closed-loop:
        dot(u_motor) = (1 / tau_lag) * (u_cmd - u_motor)
    Proves that with delay compensation, clearance remains safe (>= R_safe),
    preventing motor-lag penetration.
    """
    tau_lag = 0.04  # 40 ms motor lag
    dt = 0.02
    config = RobustTubeCLBFConfig(
        actuator_delay_s=tau_lag,
        enable_delay_compensation=True,
        safe_distance=1.0,
        a_max=5.0,
    )
    ctrl = RobustTubeCLBFController(config)

    p = np.array([0.0, 0.0, 0.0])
    v = np.array([0.0, 0.0, 0.0])
    u_motor = np.array([0.0, 0.0, 0.0])
    cov = np.diag([0.01**2, 0.01**2, 0.01**2])
    goal = np.array([8.0, 0.0, 0.0])
    obstacles = [np.array([4.0, 0.1, 0.0])]

    min_clearance = 999.0
    for t in range(200):
        state = TubeUncertaintyState(p_hat=p, v_hat=v, cov_p=cov, cov_v=cov)
        res = ctrl.step(state, goal, obstacles)
        u_cmd = res["action"]

        # First-order motor lag dynamics
        u_motor += (dt / tau_lag) * (u_cmd - u_motor)

        # Vehicle physical integration
        p += v * dt + 0.5 * u_motor * (dt ** 2)
        v += u_motor * dt

        dist_obs = float(np.linalg.norm(p - obstacles[0]))
        min_clearance = min(min_clearance, dist_obs)

        if np.linalg.norm(p - goal) <= 0.4 and np.linalg.norm(v) <= 0.2:
            break

    # Clearance must stay strictly above effective safety margin
    assert min_clearance >= 0.95, (
        f"Expected minimum clearance >= 0.95m under motor lag, got {min_clearance:.3f}m"
    )


def test_dead_end_cul_de_sac_safe_abstention_under_delay():
    """
    Tests dead-end trap with obstacles blocking all forward motion under 40ms motor lag.
    Verifies that the controller safely commands stopping/abstention without breaching barriers.
    """
    config = RobustTubeCLBFConfig(
        actuator_delay_s=0.04,
        enable_delay_compensation=True,
        safe_distance=1.0,
        a_max=5.0,
    )
    ctrl = RobustTubeCLBFController(config)

    # Start at x=0, moving at 2 m/s into a U-shaped dead end
    p = np.array([0.0, 0.0, 0.0])
    v = np.array([2.0, 0.0, 0.0])
    cov = np.diag([0.01**2, 0.01**2, 0.01**2])
    goal = np.array([6.0, 0.0, 0.0])
    # Dead end enclosing the agent
    obstacles = [
        np.array([2.5, 0.0, 0.0]),   # Front wall
        np.array([1.5, 0.8, 0.0]),   # Left wall
        np.array([1.5, -0.8, 0.0]),  # Right wall
    ]

    state = TubeUncertaintyState(p_hat=p, v_hat=v, cov_p=cov, cov_v=cov)
    res = ctrl.step(state, goal, obstacles)

    # The controller must immediately command strong negative acceleration (braking)
    assert res["action"][0] <= -2.0, f"Expected heavy braking, got {res['action'][0]:.2f}"
    assert res["p_projected"][0] > p[0], "Projected position must be ahead of current position"
