"""
Unit tests for Bounded Active Probing POMDP & Epistemic Uncertainty Reduction (Task R-07).

Validates:
1. Probing triggers reliably upon obstacle stagnation (saddle point detection).
2. Exploratory micro-actions are strictly shielded by the Robust Tube-CBF (zero collision).
3. Probing successfully breaks symmetry in narrow corridors to complete the goal.
4. Probing exhaustion in true dead ends/cul-de-sacs triggers grounded physical abstention.
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


def test_probing_triggers_upon_obstacle_stagnation():
    """
    Validates that when a vehicle is stagnant in front of an obstacle
    (v < 0.15 m/s, distance < 2.2m) for >= stall_detection_steps (15 steps),
    the controller transitions from CRUISING to ACTIVE_PROBING.
    """
    config = RobustTubeCLBFConfig(
        enable_active_probing=True,
        stall_detection_steps=15,
        stagnation_speed_thresh=0.15,
        stagnation_dist_thresh=2.2,
    )
    ctrl = RobustTubeCLBFController(config)

    obstacle = np.array([3.0, 0.0, 0.0])
    goal = np.array([10.0, 0.0, 0.0])
    p_hat = np.array([1.5, 0.0, 0.0])  # dist to obs = 1.5m < 2.2m
    v_hat = np.array([0.05, 0.0, 0.0]) # speed = 0.05m/s < 0.15m/s
    cov_p = np.eye(3) * (0.01 ** 2)
    cov_v = np.eye(3) * (0.01 ** 2)
    state = TubeUncertaintyState(p_hat=p_hat, v_hat=v_hat, cov_p=cov_p, cov_v=cov_v)

    # First 14 steps: still counting stagnation
    for _ in range(14):
        res = ctrl.step(state, goal, obstacles=[obstacle])
        assert res["phase"] == DwellPhase.CRUISING.value
        assert not res["is_probing"]

    # Step 15: stagnation threshold reached -> ACTIVE_PROBING triggered
    res_15 = ctrl.step(state, goal, obstacles=[obstacle])
    assert res_15["phase"] == DwellPhase.ACTIVE_PROBING.value
    assert res_15["is_probing"] is True
    assert "BOUNDED_ACTIVE_PROBING" in res_15["reason"]
    # Lateral probing acceleration must be non-zero
    assert abs(res_15["action"][1]) > 0.1, "Should generate lateral probing acceleration"


def test_probing_action_is_strictly_tube_shielded():
    """
    Validates that exploratory micro-actions generated during ACTIVE_PROBING
    remain strictly shielded by the Tube-CBF Micro-QP. The controller will NEVER
    command an acceleration violating obstacle safety margins.
    """
    config = RobustTubeCLBFConfig(
        safe_distance=1.0,
        enable_active_probing=True,
        probing_accel=4.0,
        stall_detection_steps=1,  # immediate trigger for testing
    )
    ctrl = RobustTubeCLBFController(config)

    obstacle = np.array([3.0, 0.0, 0.0])
    goal = np.array([10.0, 0.0, 0.0])
    # Position vehicle near barrier margin (dist = 1.3m, safe_dist = 1.0m)
    p_hat = np.array([1.7, 0.0, 0.0])
    v_hat = np.array([0.0, 0.0, 0.0])
    cov_p = np.eye(3) * (0.01 ** 2)
    cov_v = np.eye(3) * (0.01 ** 2)
    state = TubeUncertaintyState(p_hat=p_hat, v_hat=v_hat, cov_p=cov_p, cov_v=cov_v)

    res = ctrl.step(state, goal, obstacles=[obstacle])
    assert res["phase"] == DwellPhase.ACTIVE_PROBING.value

    # Verify action does not push forward into the obstacle (u_x must be <= 0.05)
    assert res["action"][0] <= 0.05, f"Action must not drive into obstacle: u_x = {res['action'][0]}"
    assert res["slack_drawn"] == 0.0, "Active probing should not draw slack"


def test_probing_resolves_corridor_impasse():
    """
    Simulates a head-on symmetric obstacle where a naive or passive controller
    freezes at the saddle point, while the AEGIS active probing controller
    shunts laterally, clears the obstacle, and completes the goal.
    """
    obstacle = np.array([4.0, 0.0, 0.0])
    goal = np.array([10.0, 0.0, 0.0])
    dt = 0.04

    def run_corridor_sim(enable_probing: bool) -> tuple[bool, float, float]:
        cfg = RobustTubeCLBFConfig(
            safe_distance=1.0,
            enable_active_probing=enable_probing,
            stall_detection_steps=10,
            max_probing_steps=35,
            probing_accel=2.5,
        )
        ctrl = RobustTubeCLBFController(cfg)
        p = np.array([0.0, 0.0, 0.0])
        v = np.array([0.0, 0.0, 0.0])
        min_dist_to_obs = float("inf")

        for step in range(350):
            cov_p = np.eye(3) * (0.01 ** 2)
            cov_v = np.eye(3) * (0.01 ** 2)
            state = TubeUncertaintyState(p_hat=p, v_hat=v, cov_p=cov_p, cov_v=cov_v)
            res = ctrl.step(state, goal, obstacles=[obstacle])

            u = res["action"]
            v = v + dt * u
            p = p + dt * v

            d_obs = float(np.linalg.norm(p - obstacle))
            min_dist_to_obs = min(min_dist_to_obs, d_obs)

            if res["phase"] == DwellPhase.CONFIRMED_STILL.value:
                dist_g = float(np.linalg.norm(p - goal))
                if dist_g <= cfg.arrival_radius:
                    return True, min_dist_to_obs, float(np.linalg.norm(p - goal))

        return False, min_dist_to_obs, float(np.linalg.norm(p - goal))

    # Passive arm (probing disabled)
    pass_succ, pass_min_d, pass_rem_g = run_corridor_sim(enable_probing=False)
    # Active probing arm (probing enabled)
    act_succ, act_min_d, act_rem_g = run_corridor_sim(enable_probing=True)

    assert not pass_succ, "Passive arm should stall at saddle point"
    assert pass_rem_g > 3.0, f"Passive arm remained far from goal: {pass_rem_g:.2f}m"
    assert pass_min_d >= 0.95, "Passive arm should maintain safety"

    assert act_succ, "Active probing arm must successfully resolve impasse and capture goal"
    assert act_min_d >= 0.95, f"Active probing arm must maintain safety invariant: {act_min_d:.2f}m >= 0.95m"
    assert act_rem_g <= 0.35, f"Active probing arm arrived at goal: {act_rem_g:.2f}m"


def test_probing_exhaustion_in_dead_end_safely_abstains():
    """
    Simulates a dead-end (cul-de-sac) enclosed by obstacles on three sides.
    Validates that after probing lateral directions and exhausting the probing budget,
    the controller cleanly transitions to grounded physical abstention (CONFIRMED_STILL)
    with kinetic energy <= 0.005 J.
    """
    obstacles = [
        np.array([4.0, 0.0, 0.0]),   # Front wall
        np.array([3.0, 1.2, 0.0]),   # Left wall
        np.array([3.0, -1.2, 0.0]),  # Right wall
    ]
    goal = np.array([10.0, 0.0, 0.0])  # Goal behind front wall
    dt = 0.04

    cfg = RobustTubeCLBFConfig(
        safe_distance=0.8,
        enable_active_probing=True,
        stall_detection_steps=5,
        max_probing_steps=12,
        probing_budget_total=24,     # Small budget to trigger abstention quickly
    )
    ctrl = RobustTubeCLBFController(cfg)
    p = np.array([2.5, 0.0, 0.0])
    v = np.array([0.0, 0.0, 0.0])
    abstain_confirmed = False
    final_e_kinetic = float("inf")

    for step in range(120):
        cov_p = np.eye(3) * (0.01 ** 2)
        cov_v = np.eye(3) * (0.01 ** 2)
        state = TubeUncertaintyState(p_hat=p, v_hat=v, cov_p=cov_p, cov_v=cov_v)
        res = ctrl.step(state, goal, obstacles=obstacles)

        u = res["action"]
        v = v + dt * u
        p = p + dt * v

        for obs in obstacles:
            assert np.linalg.norm(p - obs) >= 0.75, "Safety invariant must never be breached in dead end"

        if res["phase"] == DwellPhase.CONFIRMED_STILL.value:
            abstain_confirmed = True
            final_e_kinetic = 0.5 * cfg.vehicle_mass_kg * float(np.dot(v, v))
            break

    assert abstain_confirmed, "Should achieve grounded physical abstention in enclosed dead end"
    assert final_e_kinetic <= cfg.kinetic_energy_thresh, f"Kinetic energy must be <= 0.005J, got {final_e_kinetic}J"
