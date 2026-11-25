"""
Automated Pytest Suite for My Tri-Sensor Self-Verification Research.

Verifies:
  1. Nominal operation uses all 3 sensors with 0 false quarantines.
  2. Single-sensor Heavy Drift, Sudden Bias, Retimestamped Freeze, and Blackout
     are isolated & excluded for EVERY sensor (S1_VIO, S2_LIDAR, S3_UWB).
  3. Faulty sensor values NEVER leak into display_pos or control_pos once quarantined.
  4. Dual simultaneous sensor failure triggers FAIL-CLOSED abstention (display_pos is None).
"""

from __future__ import annotations

import numpy as np
import pytest

from research.tri_sensor_verification.sensor_suite import (
    DEFAULT_TRI_SENSORS,
    FaultInjectionSpec,
    FaultType,
    TriSensorSimulator,
)
from research.tri_sensor_verification.tri_sensor_verifier import TriSensorVerifier, VerifierConfig


SENSOR_IDS = tuple(s.sensor_id for s in DEFAULT_TRI_SENSORS)


def _run_trajectory_test(faults, steps=35, seed=101):
    sim = TriSensorSimulator(DEFAULT_TRI_SENSORS, faults=faults, seed=seed)
    verifier = TriSensorVerifier(SENSOR_IDS, VerifierConfig())
    outputs = []
    pos = np.array([-3.0, -3.0, 1.0], dtype=np.float64)
    for k in range(steps):
        pos = pos + np.array([0.16, 0.10, 0.0])
        readings = sim.sample(k, pos)
        out = verifier.verify_and_fuse(readings)
        outputs.append((pos.copy(), readings, out))
    return outputs


def test_nominal_uses_all_three_sensors_without_false_quarantine():
    trace = _run_trajectory_test(faults=[], steps=35, seed=7)
    errors = []
    quarantines = 0
    for pos, _, out in trace:
        assert out.trusted is True
        assert out.display_pos is not None
        errors.append(float(np.linalg.norm(out.display_pos - pos)))
        if out.quarantined_sensors:
            quarantines += 1
    assert np.sqrt(np.mean(np.square(errors))) < 0.06
    assert quarantines == 0


@pytest.mark.parametrize("target_sid", SENSOR_IDS)
@pytest.mark.parametrize("fault_type", [
    FaultType.HEAVY_DRIFT,
    FaultType.SUDDEN_BIAS,
    FaultType.RETIMESTAMPED_FREEZE,
    FaultType.SENSOR_BLACKOUT,
])
def test_every_sensor_fault_is_isolated_and_excluded_from_display(target_sid, fault_type):
    spec = FaultInjectionSpec(
        sensor_id=target_sid,
        fault_type=fault_type,
        start_step=10,
        drift_rate_per_step=(0.09, -0.06, 0.01),
        drift_accel_per_step2=(0.005, 0.0, 0.0),
        bias_vector=(1.2, -0.9, 0.1),
    )
    trace = _run_trajectory_test(faults=[spec], steps=35, seed=42)

    # By step 16 (at most 6 steps after onset), target_sid must be quarantined and excluded
    late_trace = trace[16:]
    for pos, _, out in late_trace:
        assert out.trusted is True
        assert target_sid in out.quarantined_sensors
        assert target_sid not in out.used_sensors
        assert out.display_pos is not None
        # Display output must remain tightly locked to ground truth (< 0.18 m)
        assert float(np.linalg.norm(out.display_pos - pos)) < 0.18


def test_dual_sensor_failure_triggers_fail_closed_abstention():
    faults = [
        FaultInjectionSpec(
            sensor_id="S1_VIO",
            fault_type=FaultType.HEAVY_DRIFT,
            start_step=10,
            drift_rate_per_step=(0.12, -0.08, 0.0),
        ),
        FaultInjectionSpec(
            sensor_id="S2_LIDAR",
            fault_type=FaultType.RETIMESTAMPED_FREEZE,
            start_step=10,
        ),
    ]
    trace = _run_trajectory_test(faults=faults, steps=30, seed=99)
    abstain_count = sum(1 for _, _, out in trace[14:] if (not out.trusted and out.display_pos is None and out.action == "ABSTAIN_SAFE_STOP"))
    assert abstain_count == len(trace[14:])


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-v", __file__]))

