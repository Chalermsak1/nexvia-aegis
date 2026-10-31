"""Synthetic regressions for simulator-facing input and timing boundaries."""

import math
import numpy as np
import pytest

from aegis.sim2real.aegis_ros2_node import AegisROS2DroneNode
from aegis.sim2real import aegis_ros2_node
from aegis.sim2real.mavlink_protocol import FailsafeAction
from aegis.sim2real.safety_watchdog import RealtimeSafetyWatchdog
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.controller_3d import Aegis3DAwareController


def test_future_odometry_and_perception_are_not_treated_as_fresh():
    watchdog = RealtimeSafetyWatchdog()
    watchdog.record_odometry(100.0)
    watchdog.record_perception(100.0)
    diagnostic = watchdog.evaluate_health(now_s=10.0, battery_voltage_v=16.0)
    assert diagnostic.recommended_action == FailsafeAction.POSITION_HOLD_HOVER

    watchdog = RealtimeSafetyWatchdog()
    watchdog.record_odometry(10.0)
    watchdog.record_perception(100.0)
    diagnostic = watchdog.evaluate_health(now_s=10.01, battery_voltage_v=16.0)
    assert diagnostic.recommended_action == FailsafeAction.VELOCITY_AIR_BRAKE


def test_future_timestamps_can_recover_with_valid_fresh_packets():
    watchdog = RealtimeSafetyWatchdog()
    watchdog.record_odometry(100.0)
    watchdog.record_perception(10.0)
    assert watchdog.evaluate_health(10.01, battery_voltage_v=16.0).recommended_action != FailsafeAction.NONE
    assert watchdog.record_odometry(10.01)
    assert watchdog.evaluate_health(10.02, battery_voltage_v=16.0).recommended_action == FailsafeAction.NONE

    watchdog.record_perception(100.0)
    assert watchdog.evaluate_health(10.02, battery_voltage_v=16.0).recommended_action == FailsafeAction.VELOCITY_AIR_BRAKE
    assert watchdog.record_perception(10.02)
    assert watchdog.evaluate_health(10.03, battery_voltage_v=16.0).recommended_action == FailsafeAction.NONE


def test_replayed_odometry_does_not_overwrite_newer_state():
    node = AegisROS2DroneNode()
    quat = np.array([1.0, 0.0, 0.0, 0.0])
    zero = np.zeros(3)
    node.ingest_odometry(np.array([2.0, 0.0, 0.0]), quat, zero, zero, timestamp_s=20.0)
    node.ingest_odometry(np.array([99.0, 0.0, 0.0]), quat, zero, zero, timestamp_s=19.0)
    assert node.current_odom.timestamp_s == 20.0
    assert node.current_odom.position[0] == 2.0


def test_nonfinite_odometry_does_not_replace_valid_state():
    node = AegisROS2DroneNode()
    quat = np.array([1.0, 0.0, 0.0, 0.0])
    zero = np.zeros(3)
    node.ingest_odometry(np.array([2.0, 0.0, 0.0]), quat, zero, zero, timestamp_s=20.0)
    node.ingest_odometry(np.array([math.nan, 0.0, 0.0]), quat, zero, zero, timestamp_s=21.0)
    assert node.current_odom.timestamp_s == 20.0
    assert node.watchdog.last_odometry_time_s == 20.0


def test_missing_or_nonfinite_battery_never_reports_nominal():
    node = AegisROS2DroneNode()
    quat = np.array([1.0, 0.0, 0.0, 0.0])
    zero = np.zeros(3)
    node.ingest_odometry(zero, quat, zero, zero, timestamp_s=10.0)
    node.ingest_perception([], timestamp_s=10.0)
    node.ingest_battery(voltage_v=math.nan, current_a=1.0, percentage=.5, timestamp_s=10.0)
    _, diagnostic = node.step_control_cycle(10.01)
    assert diagnostic.recommended_action != FailsafeAction.NONE


def test_future_battery_fails_closed_then_recovers_with_fresh_telemetry():
    node = AegisROS2DroneNode()
    quat = np.array([1.0, 0.0, 0.0, 0.0])
    zero = np.zeros(3)
    node.ingest_odometry(zero, quat, zero, zero, timestamp_s=10.0)
    node.ingest_perception([], timestamp_s=10.0)
    node.ingest_battery(voltage_v=16.0, current_a=1.0, percentage=.5, timestamp_s=100.0)
    _, bad = node.step_control_cycle(10.01)
    assert bad.recommended_action != FailsafeAction.NONE
    node.ingest_battery(voltage_v=16.0, current_a=1.0, percentage=.5, timestamp_s=10.01)
    _, recovered = node.step_control_cycle(10.02)
    assert recovered.recommended_action == FailsafeAction.NONE


@pytest.mark.parametrize("vector", [np.array([1.0, 2.0]), np.array([math.nan, 0.0, 0.0])])
def test_malformed_valid_vector_abstains_without_exception(vector):
    controller = Aegis3DAwareController()
    action, decision, _, _ = controller.update(vector, vector, 1.0, step=1)
    assert decision == "ABSTAIN"
    assert np.all(np.isfinite(action))
    assert np.allclose(action, 0.0)


def test_unqueried_or_nonfinite_anchor_does_not_calibrate():
    controller = Aegis3DAwareController()
    vector = np.array([1.0, 0.0, 0.0])
    for index, anchor in enumerate([
        AnchorReading(np.zeros(3), .04, valid=True, queried=False, cost_accrued=0.0),
        AnchorReading(np.array([math.nan, 0.0, 0.0]), .04, valid=True, queried=True, cost_accrued=0.0),
    ]):
        controller.update(vector, vector, 1.0, anchor_reading=anchor, step=index)
    assert controller.cal_a.sample_count == 0
    assert controller.cal_b.sample_count == 0


def test_nonfinite_valid_range_clears_arrival_evidence():
    controller = Aegis3DAwareController()
    vector = np.array([0.1, 0.0, 0.0])
    controller.update(vector, vector, RangeReading(.1, .05, valid=True), step=0)
    _, decision, _, _ = controller.update(vector, vector, RangeReading(math.nan, .05, valid=True), step=1)
    assert decision != "STOP"
    assert controller.arrival_check_steps == 0
    assert controller.arrival_range_samples == []


def test_live_ros_interfaces_fail_explicitly_until_transport_exists():
    node = AegisROS2DroneNode()
    with pytest.raises(RuntimeError, match="ROS 2 transport"):
        node._init_ros2_interfaces()


def test_live_ros_constructor_rejects_before_node_initialization(monkeypatch):
    monkeypatch.setattr(aegis_ros2_node, "_HAS_RCLPY", True)
    with pytest.raises(RuntimeError, match="ROS 2 transport"):
        aegis_ros2_node.AegisROS2DroneNode()
