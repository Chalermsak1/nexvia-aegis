"""Regression tests confirming the 5 audit fixes from peer review.

Verifies:
1. H2 evaluation returns UNEVALUABLE_NO_CORE10_DATA when core-10 data is absent (no fallback substitution).
2. Safety watchdog flags uninitialized odometry as UNINITIALIZED / POSITION_HOLD_HOVER (not HEALTHY_NOMINAL).
3. Safety watchdog flags uninitialized perception as VISION_DEGRADED / VELOCITY_AIR_BRAKE.
4. AegisROS2DroneNode executes VELOCITY_AIR_BRAKE with active deceleration and publishes setpoints.
5. Aegis3DAwareController ignores invalid anchor readings (valid=False) during bias calibration.
6. Aegis3DAwareController wipes arrival corroboration evidence when range sensor drops out.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from aegis.sim2real.mavlink_protocol import AttitudeTargetSetpoint, FailsafeAction
from aegis.sim2real.safety_watchdog import (
    HardwareWatchdogConfig,
    RealtimeSafetyWatchdog,
    WatchdogHealthState,
)
from aegis.sim2real.aegis_ros2_node import AegisNodeConfig, AegisROS2DroneNode
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.controller_3d import Aegis3DAwareController
from aegis.v9.risk_statistics import V9CandidateParams
from experiments.v9_evaluate_holdout import evaluate_mixture_holdout


# ----------------------------------------------------------------------
# 1. Regression Test: H2 Core-10 Missing Data Evaluation
# ----------------------------------------------------------------------
def test_h2_returns_unevaluable_when_no_core10_records():
    """H2 must return UNEVALUABLE when no core-10 scenarios exist, without falling back to all records."""
    # Synthetic records with only scenario index > 10 and non-core names
    synthetic_records = [
        {
            "episode_index": 0,
            "scenario": "EXTENDED_TEST_SCENARIO_11",
            "scenario_index": 11,
            "accepted": 1,
            "true_success": 1,
            "false_success": 0,
            "abstain_explicit": 0,
            "timeout": 0,
            "abstain": 0,
            "crashed": 0,
            "risk_type": "none",
        },
        {
            "episode_index": 1,
            "scenario": "EXTENDED_TEST_SCENARIO_12",
            "scenario_index": 12,
            "accepted": 0,
            "true_success": 0,
            "false_success": 0,
            "abstain_explicit": 1,
            "timeout": 0,
            "abstain": 1,
            "crashed": 0,
            "risk_type": "none",
        },
    ]

    cand = V9CandidateParams(
        candidate_id="c_test",
        tier_index=1,
        tier_label="T1",
        alpha_mon=0.05,
        h_cusum=5.0,
        tau_diff=0.2,
        tau_ar=0.2,
        tau_val=0.2,
        tau_stop=0.1,
    )
    h_eval = evaluate_mixture_holdout(
        records=synthetic_records,
        cand_params=cand,
    )
    h2_core10 = h_eval["h2_core10_selective_risk"]
    assert h2_core10["status"] == "UNEVALUABLE_NO_CORE10_DATA"
    assert h2_core10["passed"] is False
    assert h2_core10["n_core10"] == 0
    assert h2_core10["m_accepted"] == 0
    assert h_eval["h2_unconditional_incidence"]["status"] == "UNEVALUABLE_NO_CORE10_DATA"
    assert h_eval["h2_unconditional_incidence"]["passed"] is False


# ----------------------------------------------------------------------
# 2. Regression Test: Watchdog Uninitialized Telemetry
# ----------------------------------------------------------------------
def test_watchdog_uninitialized_odometry_does_not_report_healthy():
    """A fresh watchdog with no odometry packets received must NEVER report HEALTHY_NOMINAL."""
    watchdog = RealtimeSafetyWatchdog(HardwareWatchdogConfig())
    diag = watchdog.evaluate_health(now_s=10.0, battery_voltage_v=16.0)

    assert diag.health_state == WatchdogHealthState.UNINITIALIZED
    assert diag.recommended_action == FailsafeAction.POSITION_HOLD_HOVER
    assert "uninitialized" in diag.failsafe_reason.lower()


def test_watchdog_uninitialized_perception_triggers_air_brake():
    """A watchdog receiving odometry but zero perception packets must engage VELOCITY_AIR_BRAKE."""
    watchdog = RealtimeSafetyWatchdog(HardwareWatchdogConfig())
    now = 10.0
    watchdog.record_odometry(now)

    diag = watchdog.evaluate_health(now_s=now + 0.005, battery_voltage_v=16.0)
    assert diag.health_state == WatchdogHealthState.VISION_DEGRADED
    assert diag.recommended_action == FailsafeAction.VELOCITY_AIR_BRAKE
    assert "perception uninitialized" in diag.failsafe_reason.lower()


# ----------------------------------------------------------------------
# 3. Regression Test: VELOCITY_AIR_BRAKE Execution & Publishing
# ----------------------------------------------------------------------
def test_aegis_ros2_node_executes_velocity_air_brake_and_publishes():
    """When perception drops, node must execute VELOCITY_AIR_BRAKE and publish attitude setpoints."""
    node = AegisROS2DroneNode(
        AegisNodeConfig(
            drone_mass_kg=1.25,
            max_thrust_n=25.0,
            max_tilt_deg=35.0,
        )
    )

    now = 5.0
    # Provide odometry moving horizontally at +1.5 m/s in X
    node.ingest_odometry(
        position=np.array([0.5, 0.0, 1.0], dtype=np.float64),
        quaternion_wxyz=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64),
        linear_velocity=np.array([1.5, 0.0, 0.0], dtype=np.float64),
        angular_velocity=np.zeros(3, dtype=np.float64),
        timestamp_s=now,
    )
    node.ingest_battery(voltage_v=16.2, current_a=5.0, percentage=0.9, timestamp_s=now)

    # Ingest perception at t=5.0
    node.ingest_perception(clusters=[], timestamp_s=now)

    # Step at t=5.010 -> nominal (perception age = 10ms < 150ms)
    setpoint_nom, diag_nom = node.step_control_cycle(now_s=now + 0.010)
    assert diag_nom.recommended_action == FailsafeAction.NONE

    # Keep odometry fresh at t=5.195, but perception is NOT updated (age = 200ms > 150ms)
    node.ingest_odometry(
        position=np.array([0.8, 0.0, 1.0], dtype=np.float64),
        quaternion_wxyz=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64),
        linear_velocity=np.array([1.5, 0.0, 0.0], dtype=np.float64),
        angular_velocity=np.zeros(3, dtype=np.float64),
        timestamp_s=now + 0.195,
    )
    # Step at t=5.200 -> perception delayed by 200ms (> 150ms timeout)
    setpoint_brake, diag_brake = node.step_control_cycle(now_s=now + 0.200)
    assert diag_brake.health_state == WatchdogHealthState.VISION_DEGRADED
    assert diag_brake.recommended_action == FailsafeAction.VELOCITY_AIR_BRAKE

    # Check that attitude setpoint was computed and published
    assert len(node.published_attitude_setpoints) >= 2
    latest_pub = node.published_attitude_setpoints[-1]
    assert latest_pub["thrust_normalized"] > 0.0
    assert len(node.published_diagnostics) >= 2
    assert node.published_diagnostics[-1]["recommended_action"] == "VELOCITY_AIR_BRAKE"


# ----------------------------------------------------------------------
# 4. Regression Test: 3D Controller Invalid Anchor Rejection
# ----------------------------------------------------------------------
def test_controller_3d_ignores_invalid_anchor_readings():
    """Anchor readings marked valid=False must NOT be used to calibrate sensor bias."""
    ctrl = Aegis3DAwareController(success_radius=0.25)

    pos = np.array([1.0, 0.5, 0.2])
    bias_corrupt = np.array([2.5, -1.8, 0.5])
    rd_a = SensorReading(
        estimate=pos + bias_corrupt,
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(3),
        drift=np.zeros(3),
    )
    rg = RangeReading(distance=float(np.linalg.norm(pos)), sigma=0.05, valid=True, dropped=False)

    # Supply an INVALID anchor reading
    invalid_anchor = AnchorReading(
        estimate=np.array([99.0, 99.0, 99.0]),
        sigma=0.05,
        valid=False,
        queried=True,
        cost_accrued=0.05,
    )

    ctrl.update(rd_a, rd_a, rg, anchor_reading=invalid_anchor, step=1)
    assert ctrl.cal_a.sample_count == 0
    assert ctrl.cal_a.is_calibrated is False
    assert np.allclose(ctrl.cal_a.bias_est, np.zeros(3))


# ----------------------------------------------------------------------
# 5. Regression Test: 3D Controller Arrival Evidence Cleared on Range Drop
# ----------------------------------------------------------------------
def test_controller_3d_clears_arrival_evidence_on_range_dropout():
    """Accumulated arrival corroboration samples must be cleared when range drops out."""
    ctrl = Aegis3DAwareController(success_radius=0.25)

    # Robot is physically inside target zone
    target_pos = np.array([0.05, 0.05, 0.02])
    dist = float(np.linalg.norm(target_pos))
    rd = SensorReading(
        estimate=target_pos,
        sigma=0.03,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(3),
        drift=np.zeros(3),
    )
    rg_valid = RangeReading(distance=dist, sigma=0.03, valid=True, dropped=False)
    rg_dropped = RangeReading(distance=0.0, sigma=0.03, valid=False, dropped=True)

    # Step 1: Valid range in target zone
    _, dec1, _, _ = ctrl.update(rd, rd, rg_valid, step=1)
    assert dec1 == "VERIFY"
    assert ctrl.arrival_check_steps == 1
    assert len(ctrl.arrival_range_samples) == 1

    # Step 2: Range drops out
    _, dec2, _, _ = ctrl.update(rd, rd, rg_dropped, step=2)
    assert dec2 == "VERIFY"
    # Evidence must have been cleared!
    assert ctrl.arrival_check_steps == 0
    assert len(ctrl.arrival_range_samples) == 0

    # Step 3: Valid range arrives again -> starts fresh at step 1 (not step 3!)
    _, dec3, _, _ = ctrl.update(rd, rd, rg_valid, step=3)
    assert dec3 == "VERIFY"
    assert ctrl.arrival_check_steps == 1
    assert len(ctrl.arrival_range_samples) == 1
    # Must NOT have prematurely transitioned to STOP!
    assert ctrl.mode != "STOP"
