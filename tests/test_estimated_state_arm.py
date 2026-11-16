"""
Tests for Estimated-State Mission Arm & Safe Fallback (E-05, E-06).
Verifies zero truth leakage, dual velocity sensor fusion, and active deceleration air brake.
"""

import numpy as np
import pytest

from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.estimated_state_candidate import EstimatedStateCandidate
from aegis.v9.velocity_freshness_candidate import TimedVelocity
from experiments.benchmark_physical_3d_cbf import run_3d_episode


def test_estimated_state_arm_e05_zero_truth_leakage():
    """E-05: Verifies that EstimatedStateCandidate computes damping from sensor estimates only."""
    ctrl = EstimatedStateCandidate(success_radius=0.25, speed_limit=0.08, damping_gain=0.5)

    # Initial state
    assert np.allclose(ctrl.v_est, [0.0, 0.0, 0.0])
    assert np.allclose(ctrl.compute_damping(), [0.0, 0.0, 0.0])

    # Provide sensor velocity reading
    v_sample = np.array([0.4, -0.2, 0.1])
    timed_v = TimedVelocity(vector=v_sample, sequence=1, acquired_seconds=0.02)
    v_est, status, fallback = ctrl.update_velocity_estimator(timed_v, now_seconds=0.02)

    assert status == "HEALTHY_SINGLE"
    assert fallback is False
    # Filter update has updated v_est without any ground truth
    assert np.linalg.norm(v_est) > 0.0
    damping = ctrl.compute_damping()
    assert np.allclose(damping, -0.5 * v_est)


def test_estimated_state_arm_e06_safe_fallback_on_dropout():
    """E-06: Verifies active deceleration air brake triggers upon persistent velocity dropout."""
    ctrl = EstimatedStateCandidate(
        success_radius=0.25,
        speed_limit=0.08,
        max_missing_velocity_steps=3,
    )

    # 1. Establish velocity
    v_sample = np.array([0.5, 0.0, 0.0])
    timed_v = TimedVelocity(vector=v_sample, sequence=1, acquired_seconds=0.02)
    ctrl.update_velocity_estimator(timed_v, now_seconds=0.02)

    # 2. Simulate dropout for 1 step (temporary)
    v_est, status, fallback = ctrl.update_velocity_estimator(None, now_seconds=0.04)
    assert status == "TEMPORARY_VELOCITY_DROPOUT"
    assert fallback is True

    # 3. Simulate dropout exceeding max_missing_velocity_steps
    for step_i in range(3):
        v_est, status, fallback = ctrl.update_velocity_estimator(None, now_seconds=0.06 + step_i * 0.02)

    assert status == "PERSISTENT_VELOCITY_LOSS"
    assert fallback is True

    # Calling update now triggers E-06 Safe Fallback: active air brake and ABSTAIN
    rd_a = SensorReading(estimate=np.array([1.0, 0.0, 0.0]), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))
    rd_b = SensorReading(estimate=np.array([1.0, 0.0, 0.0]), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))
    rd_r = RangeReading(distance=1.0, sigma=0.05, valid=True)

    action, decision, nav, query = ctrl.update(rd_a, rd_b, rd_r, step=5)
    assert decision == "ABSTAIN"
    assert ctrl.terminal_reason == "ESTIMATED_STATE_VELOCITY_DIVERGENCE"
    # Action opposes velocity (active air brake)
    assert action[0] < 0.0


def test_estimated_state_arm_e06_safe_fallback_on_sensor_disagreement():
    """E-06: Verifies sensor disagreement triggers degraded state and conservative damping."""
    ctrl = EstimatedStateCandidate(
        success_radius=0.25,
        disagreement_limit=0.1,
    )

    v1 = TimedVelocity(vector=np.array([0.1, 0.0, 0.0]), sequence=1, acquired_seconds=0.02)
    v2 = TimedVelocity(vector=np.array([0.8, 0.0, 0.0]), sequence=1, acquired_seconds=0.02)  # Disagreement 0.7 > 0.1

    v_est, status, fallback = ctrl.update_velocity_estimator(v1, v2, now_seconds=0.02)
    assert status == "VELOCITY_SENSOR_DISAGREEMENT"
    assert fallback is True
    # Conservative selection takes higher speed estimate
    assert v_est[0] > 0.2


def test_estimated_state_mission_arm_full_episode_simulation():
    """Integrates AEGIS_3D_ESTIMATED_STATE inside continuous 3D physical environment."""
    env = AegisMuJoCo3DEnvironment()
    res = run_3d_episode(
        env,
        "AEGIS_3D_ESTIMATED_STATE",
        seed=2256000,
        sensor_bias=np.array([0.0, 0.0, 0.0]),
        max_steps=200,
        post_stop_steps=20,
    )
    assert res["controller"] == "AEGIS_3D_ESTIMATED_STATE"
    assert res["collision_occurred"] == 0
    assert res["steps"] > 0
