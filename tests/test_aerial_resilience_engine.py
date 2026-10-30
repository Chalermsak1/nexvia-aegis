"""
Unit and Integration Tests for NEXVIA-AEGIS Aerial Resilience Engine.

Verifies:
  1. Pillar 1: Homotopy Deadlock Resolver breaks collinear CBF stall.
  2. Pillar 2: Active Epistemic Prober triggers gaze rotation and air-braking on occlusion.
  3. Pillar 3: Anytime-Valid Ville Sensor Guard bounds Type-I error under H0 and rapidly evicts drift.
  4. Unified Closed-Loop Agent executes end-to-end without NaN or invariant violation.
"""

import math
import numpy as np
import pytest

from aegis.aerial_resilience_engine import (
    AegisAerialResilientAgent,
    ActiveEpistemicProber,
    AnytimeValidSensorGuard,
    HomotopyDeadlockResolver,
)
from aegis.env.quadrotor_6dof import Obstacle3D, QuadrotorConfig
from aegis.nmpc.nmpc_cbf_optimizer import NmpcCbfConfig


# =============================================================================
# Pillar 1 Tests: Homotopy Deadlock Resolver
# =============================================================================

def test_pillar1_deadlock_detection_and_unlocking():
    resolver = HomotopyDeadlockResolver(
        stall_velocity_thresh=0.15,
        stall_time_thresh=0.20,
        goal_arrival_radius=0.20,
        barrier_active_dist=0.50,
        evasion_force_gain=8.0,
    )

    drone_pos = np.array([0.0, 0.0, 1.0])
    target_pos = np.array([1.5, 0.0, 1.0])
    obs = Obstacle3D(center=np.array([0.35, 0.0, 1.0]), radius=0.20)

    # 1. Moving normally: No deadlock
    drone_vel_fast = np.array([0.8, 0.0, 0.0])
    force, stat = resolver.evaluate_and_unlock(drone_pos, drone_vel_fast, target_pos, [obs], dt=0.02)
    assert not stat.is_deadlocked
    assert np.allclose(force, 0.0)

    # 2. Stalled in front of obstacle (v_x ~ 0 for multiple steps)
    drone_vel_stalled = np.array([0.02, 0.0, 0.0])
    for _ in range(12):  # 12 * 0.02 = 0.24s > 0.20s
        force, stat = resolver.evaluate_and_unlock(drone_pos, drone_vel_stalled, target_pos, [obs], dt=0.02)

    assert stat.is_deadlocked
    assert stat.homotopy_active
    assert np.linalg.norm(force) > 5.0
    # Tangent force must be orthogonal to obstacle normal (X-axis here) -> force must be primarily in Y
    assert abs(force[0]) < 1e-4
    assert abs(force[1]) > 5.0

    # 3. Once drone clears obstacle or reaches target: Deadlock clears
    drone_pos_reached = np.array([1.45, 0.0, 1.0])
    force, stat = resolver.evaluate_and_unlock(drone_pos_reached, drone_vel_stalled, target_pos, [obs], dt=0.02)
    assert not stat.is_deadlocked
    assert np.allclose(force, 0.0)


# =============================================================================
# Pillar 2 Tests: Active Epistemic Prober
# =============================================================================

def test_pillar2_active_epistemic_prober():
    prober = ActiveEpistemicProber(
        entropy_safe_thresh=0.10,
        entropy_critical_thresh=0.35,
        air_braking_gain=3.0,
    )

    drone_pos = np.array([0.0, 0.0, 1.0])
    drone_vel = np.array([1.0, 0.0, 0.0])
    target_pos = np.array([2.0, 0.0, 1.0])
    obs_center = np.array([1.0, 0.5, 1.0])

    # Case A: Low uncertainty (clear visibility, small covariance)
    cov_low = np.diag([0.01, 0.01, 0.01])**2
    dec_low = prober.compute_probing_action(
        drone_pos=drone_pos,
        drone_vel=drone_vel,
        current_yaw_deg=0.0,
        target_pos=target_pos,
        obstacle_covariances=[cov_low],
        obstacle_centers=[obs_center],
        dt=0.02,
    )
    assert not dec_low.is_actively_probing
    assert np.allclose(dec_low.proactive_brake_force, 0.0)
    assert dec_low.desired_yaw_deg == 0.0

    # Case B: High uncertainty (occlusion frustum, large covariance)
    cov_high = np.diag([0.30, 0.30, 0.20])**2
    dec_high = prober.compute_probing_action(
        drone_pos=drone_pos,
        drone_vel=drone_vel,
        current_yaw_deg=0.0,
        target_pos=target_pos,
        obstacle_covariances=[cov_high],
        obstacle_centers=[obs_center],
        dt=0.02,
    )
    assert dec_high.is_actively_probing
    # Proactive braking: force opposing drone velocity
    assert dec_high.proactive_brake_force[0] < -1.5
    # Desired yaw must rotate towards obstacle center at [1.0, 0.5, 1.0] (positive yaw angle)
    assert dec_high.desired_yaw_deg > 0.0
    assert np.linalg.norm(dec_high.probing_displacement_bias) > 1.0


# =============================================================================
# Pillar 3 Tests: Anytime-Valid Ville Sensor Guard
# =============================================================================

def test_pillar3_anytime_valid_sensor_guard_h0():
    # Under H0 (nominal unbiased observations), wealth must stay bounded below 1/alpha
    guard = AnytimeValidSensorGuard(alpha=0.05)  # threshold = 20.0
    rng = np.random.default_rng(seed=42)

    for _ in range(50):
        # Unbiased Gaussian noise matching nominal sigmas
        imu_acc = rng.normal(0.0, 0.15, size=3)
        cmd_acc = np.zeros(3)
        vis_vel = rng.normal(0.0, 0.10, size=3)
        prop_vel = np.zeros(3)
        tof_alt = 1.0 + rng.normal(0.0, 0.05)
        ekf_alt = 1.0

        tel = guard.update_and_audit(
            imu_accel_world=imu_acc,
            commanded_accel_world=cmd_acc,
            vis_velocity=vis_vel,
            propagated_velocity=prop_vel,
            tof_altitude=tof_alt,
            ekf_altitude=ekf_alt,
            tilt_rad=0.0,
        )
        assert not tel.is_alarm
        assert tel.mixture_wealth < guard.threshold
        assert len(tel.evicted_channels) == 0


def test_pillar3_anytime_valid_sensor_guard_drift_detection():
    # Under persistent IMU stealth bias injection, wealth must cross threshold
    guard = AnytimeValidSensorGuard(alpha=0.05)
    rng = np.random.default_rng(seed=123)

    alarm_triggered = False
    alarm_step = -1

    for step in range(35):
        # Inject persistent +1.2 m/s^2 bias on IMU X-axis
        imu_acc = np.array([1.2, 0.0, 0.0]) + rng.normal(0.0, 0.15, size=3)
        cmd_acc = np.zeros(3)
        vis_vel = rng.normal(0.0, 0.10, size=3)
        prop_vel = np.zeros(3)
        tof_alt = 1.0 + rng.normal(0.0, 0.05)
        ekf_alt = 1.0

        tel = guard.update_and_audit(
            imu_accel_world=imu_acc,
            commanded_accel_world=cmd_acc,
            vis_velocity=vis_vel,
            propagated_velocity=prop_vel,
            tof_altitude=tof_alt,
            ekf_altitude=ekf_alt,
            tilt_rad=0.0,
        )
        if tel.is_alarm:
            alarm_triggered = True
            alarm_step = step
            assert "imu_acc" in tel.evicted_channels
            break

    assert alarm_triggered
    # Detection must occur rapidly (< 25 steps = 500 ms at 50 Hz)
    assert alarm_step < 25


# =============================================================================
# Unified Agent Test
# =============================================================================

def test_unified_aerial_resilient_agent_step():
    agent = AegisAerialResilientAgent(
        quad_config=QuadrotorConfig(),
        nmpc_config=NmpcCbfConfig(horizon_steps=8, dt=0.05),
        alpha_risk=0.05,
    )

    drone_pos = np.array([-0.5, 0.0, 1.0])
    drone_vel = np.array([0.2, 0.0, 0.0])
    target_pos = np.array([0.8, 0.0, 1.0])
    obs = Obstacle3D(center=np.array([0.1, 0.0, 1.0]), radius=0.20)
    cov = np.diag([0.05, 0.05, 0.05])**2

    res = agent.step(
        drone_pos=drone_pos,
        drone_vel=drone_vel,
        current_yaw_deg=0.0,
        target_pos=target_pos,
        target_vel=None,
        obstacles=[obs],
        obstacles_vel=[np.zeros(3)],
        obstacle_covariances=[cov],
        imu_accel_world=np.array([0.0, 0.0, 0.0]),
        vis_velocity=drone_vel,
        tof_altitude=1.0,
        ekf_altitude=1.0,
        tilt_rad=0.0,
        dt=0.02,
    )

    assert not np.any(np.isnan(res.optimal_force_world))
    assert res.optimal_force_world[2] > 0.0  # Must generate upward thrust
    assert isinstance(res.desired_yaw_deg, float)
    assert not res.sensor_guard.is_alarm
    assert res.nmpc_result.solver_success
