"""
Unit tests for Nonlinear Model Predictive Control with Control Barrier Functions (NMPC-CBF).
"""

import math
import numpy as np
import pytest

from aegis.env.quadrotor_6dof import Obstacle3D
from aegis.nmpc.nmpc_cbf_optimizer import NmpcCbfConfig, NmpcCbfController


def test_nmpc_initialization_and_precomputation():
    """Verify matrix dimensions, Hessian symmetry, and positive definiteness."""
    cfg = NmpcCbfConfig(horizon_steps=10, dt=0.05, drone_mass=1.25)
    controller = NmpcCbfController(cfg)

    assert controller.M_p.shape == (30, 30)
    assert controller.M_v.shape == (30, 30)
    assert controller.H.shape == (30, 30)

    # Check symmetry of Hessian H
    np.testing.assert_allclose(controller.H, controller.H.T, atol=1e-10)

    # Check positive definiteness (all eigenvalues > 0)
    eigvals = np.linalg.eigvalsh(controller.H)
    assert np.all(eigvals > 0), "Hessian must be strictly positive definite"


def test_nmpc_hover_equilibrium():
    """Verify that at setpoint with zero velocity, the controller commands exact hover thrust."""
    cfg = NmpcCbfConfig(horizon_steps=10, dt=0.05, drone_mass=1.25, gravity=9.81)
    controller = NmpcCbfController(cfg)

    current_pos = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    current_vel = np.zeros(3, dtype=np.float64)
    target_pos = np.array([0.0, 0.0, 1.0], dtype=np.float64)

    res = controller.compute_optimal_control(
        current_pos=current_pos,
        current_vel=current_vel,
        target_pos=target_pos,
    )

    expected_hover_z = 1.25 * 9.81  # ~12.2625 N
    assert res.solver_success is True
    assert abs(res.optimal_force_world[0]) < 0.1
    assert abs(res.optimal_force_world[1]) < 0.1
    assert abs(res.optimal_force_world[2] - expected_hover_z) < 0.35


def test_nmpc_obstacle_circumnavigation():
    """Verify that NMPC-CBF detects obstacle ahead and generates anticipatory lateral avoidance curve."""
    cfg = NmpcCbfConfig(
        horizon_steps=20,
        dt=0.05,
        drone_mass=1.25,
        robot_collision_radius=0.12,
        safety_margin=0.08,
    )
    controller = NmpcCbfController(cfg)

    # Moving forward along X towards target on the other side of obstacle
    current_pos = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    current_vel = np.array([1.2, 0.0, 0.0], dtype=np.float64)
    target_pos = np.array([1.6, 0.0, 1.0], dtype=np.float64)

    obs = Obstacle3D(center=np.array([0.5, 0.04, 1.0]), radius=0.18)

    res = controller.compute_optimal_control(
        current_pos=current_pos,
        current_vel=current_vel,
        target_pos=target_pos,
        obstacles=[obs],
    )

    assert res.solver_success is True
    # 1. Trajectory must deviate laterally around the obstacle
    pred_positions = res.planned_trajectory.positions
    lateral_deviations = np.abs(pred_positions[:, 1])
    max_lateral_dev = np.max(lateral_deviations)
    assert max_lateral_dev > 0.10, f"Expected lateral detour, got {max_lateral_dev}"

    # 2. Predicted trajectory must strictly respect collision buffer
    r_collision = obs.radius + cfg.robot_collision_radius
    dists_to_obs = np.linalg.norm(pred_positions - obs.center, axis=1)
    min_dist = np.min(dists_to_obs)
    assert min_dist >= r_collision - 1e-4, f"Trajectory penetrated obstacle: min_dist={min_dist}, r_coll={r_collision}"


def test_nmpc_obstacle_safe_braking():
    """Verify that when target is blocked, NMPC-CBF smoothly decelerates and preserves safe margin."""
    cfg = NmpcCbfConfig(
        horizon_steps=15,
        dt=0.05,
        drone_mass=1.25,
        robot_collision_radius=0.12,
        safety_margin=0.08,
    )
    controller = NmpcCbfController(cfg)

    current_pos = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    current_vel = np.array([1.2, 0.0, 0.0], dtype=np.float64)
    target_pos = np.array([1.0, 0.0, 1.0], dtype=np.float64)
    obs = Obstacle3D(center=np.array([0.45, 0.0, 1.0]), radius=0.18)

    res = controller.compute_optimal_control(
        current_pos=current_pos,
        current_vel=current_vel,
        target_pos=target_pos,
        obstacles=[obs],
    )

    assert res.solver_success is True
    assert res.min_barrier_margin >= 0.079, f"Barrier margin violated: {res.min_barrier_margin}"


def test_nmpc_tilt_bounding():
    """Verify that commanded force respects maximum tilt angle cone (35 degrees)."""
    cfg = NmpcCbfConfig(
        horizon_steps=10,
        dt=0.05,
        drone_mass=1.25,
        max_tilt_rad=math.radians(35.0),
    )
    controller = NmpcCbfController(cfg)

    # Aggressive step demand 5 meters away in X
    current_pos = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    current_vel = np.zeros(3, dtype=np.float64)
    target_pos = np.array([5.0, 0.0, 1.0], dtype=np.float64)

    res = controller.compute_optimal_control(
        current_pos=current_pos,
        current_vel=current_vel,
        target_pos=target_pos,
    )

    f_cmd = res.optimal_force_world
    tilt_rad = math.atan2(math.sqrt(f_cmd[0]**2 + f_cmd[1]**2), max(1e-4, f_cmd[2]))
    assert tilt_rad <= math.radians(35.5), f"Tilt exceeded 35 deg: {math.degrees(tilt_rad):.2f} deg"
