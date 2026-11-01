import numpy as np
import pytest
from aegis.bridge.aegis_safety_box import (
    AegisSafetyBox,
    SafetyBoxStatus,
    VehicleTelemetry,
    ObstacleEstimate,
)


def test_safety_box_nominal_passthrough():
    box = AegisSafetyBox()
    telem = VehicleTelemetry(
        timestamp_s=100.0,
        position=np.array([0.0, 0.0, 1.0]),
        velocity=np.array([0.5, 0.0, 0.0]),
        sigma_p=0.05,
        sigma_v=0.08,
    )
    cmd = np.array([1.0, 0.0, 0.0])
    out = box.process_command(cmd, telem, obstacles=[], current_time_s=100.0)

    assert out.status == SafetyBoxStatus.NOMINAL_PASSTHROUGH
    assert not out.intervened
    assert np.allclose(out.safe_accel, cmd)
    assert out.latency_us < 200.0  # Ultra-fast execution


def test_safety_box_barrier_intervention():
    box = AegisSafetyBox()
    telem = VehicleTelemetry(
        timestamp_s=100.0,
        position=np.array([0.0, 0.0, 1.0]),
        velocity=np.array([1.5, 0.0, 0.0]),
        sigma_p=0.05,
        sigma_v=0.08,
    )
    # Obstacle directly ahead at x = 1.0
    obs = [ObstacleEstimate(center=np.array([1.0, 0.0, 1.0]), radius=0.4)]
    # Upstream tries to accelerate forward toward obstacle
    cmd = np.array([3.0, 0.0, 0.0])

    out = box.process_command(cmd, telem, obstacles=obs, current_time_s=100.0)

    assert out.status == SafetyBoxStatus.BARRIER_INTERVENTION
    assert out.intervened
    # Must intervene and decelerate in x
    assert out.safe_accel[0] < 0.0


def test_safety_box_observability_abstain():
    box = AegisSafetyBox()
    telem = VehicleTelemetry(
        timestamp_s=100.0,
        position=np.array([0.0, 0.0, 1.0]),
        velocity=np.array([1.0, 0.0, 0.0]),
        sigma_p=0.35,  # Exceeds 0.25 threshold
        sigma_v=0.08,
    )
    cmd = np.array([1.0, 0.0, 0.0])
    out = box.process_command(cmd, telem, obstacles=[], current_time_s=100.0)

    assert out.status == SafetyBoxStatus.OBSERVABILITY_ABSTAIN
    assert out.intervened
    assert out.dwell_active
    # Deadbeat braking opposite to velocity
    assert out.safe_accel[0] < 0.0


def test_safety_box_watchdog_timeout():
    box = AegisSafetyBox(watchdog_timeout_ms=50.0)
    telem = VehicleTelemetry(
        timestamp_s=100.0,
        position=np.array([0.0, 0.0, 1.0]),
        velocity=np.array([1.0, 0.0, 0.0]),
        sigma_p=0.05,
        sigma_v=0.08,
    )
    cmd = np.array([1.0, 0.0, 0.0])

    # First message initializes heartbeat
    box.process_command(cmd, telem, obstacles=[], current_time_s=100.0)

    # Next message arrives 100ms later (> 50ms timeout)
    out = box.process_command(cmd, telem, obstacles=[], current_time_s=100.10)

    assert out.status == SafetyBoxStatus.WATCHDOG_TIMEOUT_FAILSAFE
    assert out.intervened
    assert out.dwell_active
