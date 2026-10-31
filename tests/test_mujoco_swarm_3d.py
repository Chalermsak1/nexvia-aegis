"""
tests/test_mujoco_swarm_3d.py — Unit Tests for 3D MuJoCo Multi-Agent Swarm with HOCBF.
"""

import math
import numpy as np
import pytest

from aegis.env.mujoco_swarm_3d import (
    AegisMuJoCoSwarm3DEnvironment,
    Swarm3DConfig,
    SwarmCBF3DFilter,
)
from aegis.env.mujoco_3d_cbf import Obstacle3D


def test_swarm_initialization_and_step():
    cfg = Swarm3DConfig(num_robots=4, timestep=0.02)
    env = AegisMuJoCoSwarm3DEnvironment(cfg)
    rng = np.random.default_rng(42)
    st = env.reset(rng)

    assert len(st["positions"]) == 4
    assert len(st["velocities"]) == 4
    assert st["step"] == 0

    # Step with zero control (hover/stabilize)
    zero_u = [np.zeros(3) for _ in range(4)]
    next_st = env.step(zero_u)

    assert next_st["step"] == 1
    assert not next_st["any_collision"]
    assert next_st["min_obstacle_distance"] > 0.0
    assert next_st["min_inter_agent_distance"] > 0.0


def test_inter_agent_collision_avoidance_cbf():
    """
    Test that two robots commanded to crash directly into each other are deflected
    by the reciprocal inter-agent CBF filter.
    """
    cfg = Swarm3DConfig(num_robots=2, timestep=0.02, robot_radius=0.20, inter_agent_margin=0.10)
    cbf_filter = SwarmCBF3DFilter(cfg)

    # Robot 0 at [0, 0, 1.0], Robot 1 at [0.6, 0, 1.0] (distance = 0.60m)
    # Collision threshold = 2 * 0.20 = 0.40m
    pos = [np.array([0.0, 0.0, 1.0]), np.array([0.60, 0.0, 1.0])]
    vel = [np.array([1.5, 0.0, 0.0]), np.array([-1.5, 0.0, 0.0])]  # High closing speed = 3.0 m/s
    des_u = [np.array([2.0, 0.0, 0.0]), np.array([-2.0, 0.0, 0.0])]

    safe_u, active = cbf_filter.compute_safe_swarm_controls(
        positions=pos,
        velocities=vel,
        desired_controls=des_u,
        obstacles=[],
    )

    assert any(active), "Inter-agent CBF should be active under head-on closing trajectory."
    # Safe control for robot 0 must decelerate (force in -x direction)
    assert safe_u[0][0] < des_u[0][0]
    # Safe control for robot 1 must decelerate (force in +x direction)
    assert safe_u[1][0] > des_u[1][0]


def test_swarm_obstacle_avoidance_invariance():
    """
    Simulates swarm approaching obstacles, ensuring zero collisions across 50 steps.
    """
    cfg = Swarm3DConfig(num_robots=3, timestep=0.02)
    env = AegisMuJoCoSwarm3DEnvironment(cfg)
    rng = np.random.default_rng(999)
    env.reset(rng)

    # Command all robots straight toward target (which lies past the obstacles)
    target = env.target_pos

    for _ in range(50):
        st = env.get_state()
        des_u = []
        for p, v in zip(st["positions"], st["velocities"]):
            u = 1.5 * (target - p) - 0.5 * v
            des_u.append(u)

        st_next = env.step(des_u)
        assert not st_next["any_collision"], (
            f"Collision detected: obs={st_next['collision_obstacle']}, "
            f"inter={st_next['collision_inter_agent']}"
        )


def test_wind_perturbation_propagation():
    """
    Verifies that the Ornstein-Uhlenbeck continuous wind process fluctuates stochastically
    around the defined mean velocity.
    """
    cfg = Swarm3DConfig(
        num_robots=2,
        timestep=0.02,
        wind_enabled=True,
        wind_mean=np.array([0.5, 0.0, 0.0]),
        wind_sigma=0.2,
    )
    env = AegisMuJoCoSwarm3DEnvironment(cfg)
    rng = np.random.default_rng(123)
    env.reset(rng)

    wind_samples = []
    zero_u = [np.zeros(3), np.zeros(3)]
    for _ in range(60):
        st = env.step(zero_u)
        wind_samples.append(st["wind_velocity"].copy())

    wind_arr = np.array(wind_samples)
    mean_w = np.mean(wind_arr, axis=0)
    # The empirical mean should be in the neighborhood of [0.5, 0.0, 0.0]
    assert abs(mean_w[0] - 0.5) < 0.35
    # Variance along X should be strictly positive
    assert np.var(wind_arr[:, 0]) > 0.0


def test_asymmetric_cbf_around_quarantined_peer():
    """
    Validates that when a peer drone is marked as quarantined/faulty,
    the healthy peer assumes 100% full unilateral evasion responsibility
    and commands stronger evasive deceleration than standard reciprocal sharing.
    """
    cfg = Swarm3DConfig(num_robots=2, robot_radius=0.20, inter_agent_margin=0.10)
    cbf = SwarmCBF3DFilter(cfg)

    # Robot 0 approaching Robot 1 (which is stationary/faulty at 0.80m)
    pos = [np.array([0.0, 0.0, 1.0]), np.array([0.80, 0.0, 1.0])]
    vel = [np.array([0.7, 0.0, 0.0]), np.array([0.0, 0.0, 0.0])]
    des_u = [np.array([1.5, 0.0, 0.0]), np.array([0.0, 0.0, 0.0])]

    # 1. Reciprocal sharing (assumes peer 1 will dodge equally)
    safe_u_recip, act_recip = cbf.compute_safe_swarm_controls(
        positions=pos, velocities=vel, desired_controls=des_u, obstacles=[], quarantined_mask=[False, False]
    )

    # 2. Asymmetric AEGIS (knows peer 1 is quarantined/unresponsive)
    safe_u_asym, act_asym = cbf.compute_safe_swarm_controls(
        positions=pos, velocities=vel, desired_controls=des_u, obstacles=[], quarantined_mask=[False, True]
    )

    # Robot 0 must exert stronger deceleration against the quarantined peer
    assert safe_u_asym[0][0] < safe_u_recip[0][0], "Asymmetric CBF must enforce greater braking against non-dodging peer"
    # Robot 1 (quarantined) must be commanded with active damping hover
    assert np.allclose(safe_u_asym[1], np.zeros(3)), "Stationary quarantined peer should remain hovering"

