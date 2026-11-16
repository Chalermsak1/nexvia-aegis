import time
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


def test_safety_box_backend_detection_and_graceful_fallback():
    box_cpp = AegisSafetyBox()
    assert box_cpp.backend_type == "CPP20_MICROKERNEL"

    box_fallback_missing = AegisSafetyBox(
        kernel_lib_path="/nonexistent/path/libaegis_kernel.dylib"
    )
    assert box_fallback_missing.backend_type == "PURE_PYTHON_FALLBACK"

    box_fallback_disabled = AegisSafetyBox(use_cpp_backend=False)
    assert box_fallback_disabled.backend_type == "PURE_PYTHON_FALLBACK"


def test_safety_box_cpp_vs_python_numerical_consistency():
    """Verify C++20 microkernel and pure-Python fallback agree within Delta < 1e-3."""
    box_cpp = AegisSafetyBox(use_cpp_backend=True)
    box_py = AegisSafetyBox(
        kernel_lib_path="/nonexistent/path/libaegis_kernel.dylib"
    )
    assert box_cpp.backend_type == "CPP20_MICROKERNEL"
    assert box_py.backend_type == "PURE_PYTHON_FALLBACK"

    scenarios = [
        # 1. Nominal open-space passthrough
        (
            np.array([1.2, -0.4, 0.3]),
            VehicleTelemetry(
                timestamp_s=10.0,
                position=np.array([0.0, 0.0, 1.5]),
                velocity=np.array([0.5, 0.1, 0.0]),
                sigma_p=0.04,
                sigma_v=0.06,
                beta_min=1.0,
            ),
            [],
        ),
        # 2. Static obstacle intervention
        (
            np.array([3.0, 0.0, 0.0]),
            VehicleTelemetry(
                timestamp_s=10.04,
                position=np.array([0.0, 0.0, 1.0]),
                velocity=np.array([1.5, 0.0, 0.0]),
                sigma_p=0.05,
                sigma_v=0.08,
                beta_min=1.0,
            ),
            [ObstacleEstimate(center=np.array([1.0, 0.0, 1.0]), radius=0.4)],
        ),
        # 3. Dynamic moving obstacle + mass derating
        (
            np.array([2.5, 0.5, -0.2]),
            VehicleTelemetry(
                timestamp_s=10.08,
                position=np.array([0.2, -0.1, 1.2]),
                velocity=np.array([1.1, 0.2, 0.0]),
                sigma_p=0.06,
                sigma_v=0.09,
                beta_min=0.75,
            ),
            [
                ObstacleEstimate(
                    center=np.array([1.3, 0.0, 1.2]),
                    radius=0.45,
                    velocity=np.array([-1.2, 0.1, 0.0]),
                ),
                ObstacleEstimate(
                    center=np.array([0.9, 0.8, 1.2]),
                    radius=0.35,
                    velocity=np.array([0.0, -0.8, 0.0]),
                ),
            ],
        ),
        # 4. Observability gate abstention (sigma_p > 0.25)
        (
            np.array([2.0, 0.0, 0.0]),
            VehicleTelemetry(
                timestamp_s=10.12,
                position=np.array([0.5, 0.0, 1.2]),
                velocity=np.array([1.2, -0.3, 0.1]),
                sigma_p=0.32,
                sigma_v=0.10,
                beta_min=1.0,
            ),
            [],
        ),
    ]

    for idx, (cmd, telem, obs_list) in enumerate(scenarios):
        t_now = 10.0 + idx * 0.02
        out_cpp = box_cpp.process_command(cmd, telem, obs_list, current_time_s=t_now)
        out_py = box_py.process_command(cmd, telem, obs_list, current_time_s=t_now)

        delta = float(np.max(np.abs(out_cpp.safe_accel - out_py.safe_accel)))
        assert delta < 1e-3, f"Scenario {idx} mismatch: delta={delta:.6e}"
        assert out_cpp.status == out_py.status
        assert out_cpp.intervened == out_py.intervened
        assert out_cpp.dwell_active == out_py.dwell_active


def test_safety_box_cpp_backend_benchmark_under_100us():
    """Benchmark C++20 microkernel backend execution latency (< 100 us)."""
    box = AegisSafetyBox(use_cpp_backend=True)
    assert box.backend_type == "CPP20_MICROKERNEL"

    telem = VehicleTelemetry(
        timestamp_s=0.0,
        position=np.array([0.0, 0.0, 1.0]),
        velocity=np.array([1.2, 0.1, 0.0]),
        sigma_p=0.05,
        sigma_v=0.08,
        beta_min=0.9,
    )
    obs = [
        ObstacleEstimate(
            center=np.array([1.2, 0.0, 1.0]),
            radius=0.4,
            velocity=np.array([-1.0, 0.0, 0.0]),
        ),
        ObstacleEstimate(
            center=np.array([1.8, 0.6, 1.0]),
            radius=0.35,
            velocity=np.array([-0.5, -0.2, 0.0]),
        ),
    ]
    cmd = np.array([2.5, 0.0, 0.0])

    # Warmup calls
    t_sim = 1.0
    for _ in range(25):
        t_sim += 0.02
        box.process_command(cmd, telem, obs, current_time_s=t_sim)

    # Timed benchmark over 500 control cycles
    n_iters = 500
    t0 = time.perf_counter()
    latencies = []
    for _ in range(n_iters):
        t_sim += 0.02
        out = box.process_command(cmd, telem, obs, current_time_s=t_sim)
        latencies.append(out.latency_us)
    avg_wall_us = ((time.perf_counter() - t0) / n_iters) * 1e6
    median_us = float(np.median(latencies))

    assert avg_wall_us < 100.0, f"Expected < 100 us C++ solve latency, got {avg_wall_us:.2f} us"
    assert median_us < 100.0, f"Expected < 100 us median latency, got {median_us:.2f} us"


def test_safety_box_nmpc_receding_horizon_and_corridor():
    """Validates receding-horizon lookahead NMPC filter with corridor awareness."""
    box = AegisSafetyBox(use_cpp_backend=True)

    telem = VehicleTelemetry(
        timestamp_s=100.0,
        position=np.array([0.0, 0.0, 1.0]),
        velocity=np.array([1.2, 0.0, 0.0]),
        sigma_p=0.05,
        sigma_v=0.08,
    )
    target_pos = np.array([1.6, 0.0, 1.0])
    obs = [ObstacleEstimate(center=np.array([0.5, 0.04, 1.0]), radius=0.18)]
    corridor_planes = [(np.array([0.0, 1.0, 0.0]), 0.50)]  # Y <= 0.5

    cmd = np.array([2.0, 0.0, 0.0])

    out = box.process_command_nmpc(
        untrusted_accel=cmd,
        telemetry=telem,
        target_pos=target_pos,
        obstacles=obs,
        corridor_planes=corridor_planes,
        current_time_s=100.0,
    )

    assert out.status == SafetyBoxStatus.BARRIER_INTERVENTION
    assert out.intervened
    assert out.min_margin >= 0.05, f"Expected safe barrier margin, got {out.min_margin}"
    # NMPC RTI-SQP latency should be well under 2.5 ms (typically ~700-1200 us)
    assert out.latency_us < 2500.0, f"Expected sub-2.5ms latency, got {out.latency_us:.1f} us"
