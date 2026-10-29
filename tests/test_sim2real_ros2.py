"""Unit Tests for Sim2Real ROS 2 and PX4 Autopilot Hardware Bridge.

Verifies:
  1. Attitude quaternion generation and tilt boundary constraints.
  2. Latency extrapolation and watchdog failsafe degradation state machine.
  3. 200 Hz inner-loop attitude setpoint generation under normal and corrupted states.
  4. Anytime Ville martingale sensor corruption detection and safe loiter trigger.
"""

import math
import numpy as np
import pytest

from aegis.sim2real.mavlink_protocol import (
    AttitudeTargetSetpoint,
    DroneOdometry,
    FailsafeAction,
    force_vector_to_attitude_and_thrust,
    quaternion_to_euler_angles,
)
from aegis.sim2real.safety_watchdog import (
    HardwareWatchdogConfig,
    RealtimeSafetyWatchdog,
    WatchdogHealthState,
)
from aegis.sim2real.aegis_ros2_node import (
    AegisNodeConfig,
    AegisROS2DroneNode,
)
from aegis.vision.depth_lidar_sensor import SensorObservation


def test_force_vector_to_attitude_tilt_clamping():
    """Verifies that extreme horizontal forces are strictly clamped to 35 deg tilt."""
    # Request extreme horizontal force (100 N horizontal, 15 N vertical)
    extreme_force = np.array([100.0, 0.0, 14.715], dtype=np.float64)
    quat, thrust = force_vector_to_attitude_and_thrust(
        desired_force_world=extreme_force,
        desired_yaw_rad=0.0,
        mass_kg=1.5,
        max_thrust_n=25.0,
        max_tilt_rad=math.radians(35.0),
    )

    # Check quaternion normalization
    assert math.isclose(float(np.linalg.norm(quat)), 1.0, rel_tol=1e-5)

    # Extract Euler angles
    roll, pitch, yaw = quaternion_to_euler_angles(quat)
    tilt_deg = math.degrees(math.acos(math.cos(roll) * math.cos(pitch)))

    # Tilt must not exceed 35 deg + tolerance
    assert tilt_deg <= 35.05
    # Thrust must be capped at 1.0
    assert 0.05 <= thrust <= 1.0


def test_watchdog_latency_extrapolation():
    """Verifies forward position projection under camera transmission latency."""
    watchdog = RealtimeSafetyWatchdog(HardwareWatchdogConfig(max_latency_extrapolation_s=0.05))

    pos = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    vel = np.array([2.0, 0.0, -1.0], dtype=np.float64)
    data_t = 100.0
    now_t = 100.025  # 25 ms delay

    ext_pos, ext_vel, dt_comp = watchdog.extrapolate_state_for_latency(
        position=pos,
        velocity=vel,
        now_s=now_t,
        data_timestamp_s=data_t,
    )

    assert math.isclose(dt_comp, 0.025, abs_tol=1e-4)
    # p_proj = [1.0 + 2*0.025, 2.0, 3.0 - 1*0.025] = [1.05, 2.0, 2.975]
    assert np.allclose(ext_pos, np.array([1.05, 2.0, 2.975]), atol=1e-4)
    assert np.allclose(ext_vel, vel)


def test_watchdog_failsafe_state_transitions():
    """Tests watchdog degradation under odometry loss, perception drop, and battery sag."""
    watchdog = RealtimeSafetyWatchdog(
        HardwareWatchdogConfig(
            odometry_timeout_s=0.040,
            perception_timeout_s=0.150,
            battery_critical_v=13.6,
        )
    )

    now = 10.0
    watchdog.record_odometry(now)
    watchdog.record_perception(now)

    # 1. Nominal state
    diag_nom = watchdog.evaluate_health(now_s=now + 0.010, battery_voltage_v=16.0)
    assert diag_nom.health_state in (WatchdogHealthState.HEALTHY_NOMINAL, WatchdogHealthState.LATENCY_COMPENSATED)
    assert diag_nom.recommended_action == FailsafeAction.NONE

    # 2. Odometry timeout (> 40ms) -> POSITION_HOLD_HOVER
    diag_odom_loss = watchdog.evaluate_health(now_s=now + 0.060, battery_voltage_v=16.0)
    assert diag_odom_loss.health_state == WatchdogHealthState.COMMUNICATION_TIMEOUT
    assert diag_odom_loss.recommended_action == FailsafeAction.POSITION_HOLD_HOVER

    # 3. Critical battery (< 13.6V) -> EMERGENCY_LAND
    diag_batt = watchdog.evaluate_health(now_s=now + 0.010, battery_voltage_v=13.2)
    assert diag_batt.health_state == WatchdogHealthState.BATTERY_CRITICAL
    assert diag_batt.recommended_action == FailsafeAction.EMERGENCY_LAND

    # 4. Ville Martingale corruption -> SAFE_ABSTENTION_LOITER
    diag_martingale = watchdog.evaluate_health(now_s=now + 0.010, battery_voltage_v=16.0, martingale_violation=True)
    assert diag_martingale.health_state == WatchdogHealthState.FAILSAFE_ACTIVE
    assert diag_martingale.recommended_action == FailsafeAction.SAFE_ABSTENTION_LOITER


def test_aegis_ros2_node_step_cycle_and_martingale_betting():
    """Verifies that the ROS 2 companion node executes control cycles and reacts to sensor bias."""
    node = AegisROS2DroneNode(
        AegisNodeConfig(
            control_rate_hz=200.0,
            target_pos=np.array([2.0, 0.0, 1.0]),
            ville_alpha=0.05,
        )
    )

    now = 1.0
    # Ingest nominal odometry
    node.ingest_odometry(
        position=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        quaternion_wxyz=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64),
        linear_velocity=np.array([0.5, 0.0, 0.0], dtype=np.float64),
        angular_velocity=np.zeros(3, dtype=np.float64),
        timestamp_s=now,
    )
    # Ingest battery
    node.ingest_battery(voltage_v=16.2, current_a=6.0, percentage=0.90, timestamp_s=now)

    # Ingest obstacle perception (centroid, radius)
    node.ingest_perception(
        clusters=[(np.array([1.2, 0.0, 1.0]), 0.25)],
        timestamp_s=now,
    )

    # Step control cycle
    setpoint, diag = node.step_control_cycle(now_s=now + 0.005)
    assert setpoint.thrust_normalized > 0.05
    assert math.isclose(float(np.linalg.norm(setpoint.orientation_wxyz)), 1.0, rel_tol=1e-5)
    assert diag.health_state in (WatchdogHealthState.HEALTHY_NOMINAL, WatchdogHealthState.LATENCY_COMPENSATED)

    # Simulate persistent sensor corruption (cross-modal residual = 0.6m)
    for _ in range(15):
        node.update_martingale_sensor_check(cross_modal_residual=0.60)

    # Martingale wealth must cross 1/alpha = 20.0
    assert node.martingale_wealth >= 20.0
    assert node.martingale_violation is True

    # Next step cycle must engage safe abstention loiter
    setpoint_corrupt, diag_corrupt = node.step_control_cycle(now_s=now + 0.010)
    assert diag_corrupt.recommended_action == FailsafeAction.SAFE_ABSTENTION_LOITER
