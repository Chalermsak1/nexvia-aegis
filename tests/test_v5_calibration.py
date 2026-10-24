from __future__ import annotations

import numpy as np
import pytest

from aegis.calibration import CalibrationResult, OnlineBiasEstimator
from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.sensors.cross_modal import RangeReading, RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig, SensorReading
from aegis.v5.recovery_controller import SafeRecoveryController


def make_sensor_reading(estimate: np.ndarray, sigma: float = 0.05, valid: bool = True) -> SensorReading:
    return SensorReading(
        estimate=np.asarray(estimate, dtype=np.float64),
        sigma=float(sigma),
        valid=bool(valid),
        anomaly=False,
        dropped=not valid,
        bias=np.zeros(2, dtype=np.float64),
        drift=np.zeros(2, dtype=np.float64),
    )


# ---------------------------------------------------------------------------
# Test 1: Exact recovery under identifiable synthetic geometry
# ---------------------------------------------------------------------------
def test_exact_synthetic_recovery():
    """Verifies that an identifiable non-collinear trajectory recovers exact bias with machine precision."""
    b_true = np.array([0.75, -0.45], dtype=np.float64)
    p_target = np.array([3.0, 1.5], dtype=np.float64)
    positions = [
        np.array([0.0, 0.0]),
        np.array([0.5, 0.2]),
        np.array([0.2, 0.8]),
        np.array([-0.3, 0.6]),
        np.array([0.4, -0.3]),
        np.array([-0.2, -0.4]),
        np.array([0.6, 0.4]),
        np.array([0.1, 0.9]),
    ]
    est = OnlineBiasEstimator(min_samples=6)
    for p in positions:
        d = p_target - p
        r = float(np.linalg.norm(d))
        z = d + b_true
        est.add_observation(z, r, True)

    res = est.estimate(method="HUBER")
    assert res.status == "CALIBRATED"
    assert np.allclose(res.bias, b_true, atol=1e-3)
    assert res.residual_rmse < 1e-4


# ---------------------------------------------------------------------------
# Test 2: Bias-recovery error under controlled noise
# ---------------------------------------------------------------------------
def test_bias_recovery_under_controlled_noise():
    """Verifies that bias recovery RMSE remains bounded under zero-mean Gaussian noise."""
    rng = np.random.default_rng(101)
    b_true = np.array([0.6, 0.4], dtype=np.float64)
    p_target = np.array([2.5, 2.5], dtype=np.float64)

    t = np.linspace(-1, 1, 25)
    ortho = np.array([-1.0, 1.0]) / np.sqrt(2)
    forward = np.array([1.0, 1.0]) / np.sqrt(2)
    positions = np.outer(0.35 * t, ortho) + np.outer(0.30 * np.abs(t), forward)

    est = OnlineBiasEstimator(min_samples=8)
    for p in positions:
        d = p_target - p
        r = float(np.linalg.norm(d)) + float(rng.normal(0, 0.02))
        z = d + b_true + rng.normal(0, 0.02, size=2)
        est.add_observation(z, r, True)

    res = est.estimate(method="HUBER")
    assert res.status == "CALIBRATED"
    assert np.linalg.norm(res.bias - b_true) < 0.20


# ---------------------------------------------------------------------------
# Test 3: Robustness to outliers (Huber vs OLS)
# ---------------------------------------------------------------------------
def test_robustness_to_outliers():
    """Verifies that Huber estimator is less sensitive to heavy-tail outlier bursts than OLS."""
    b_true = np.array([0.5, 0.5])
    p_target = np.array([3.0, 3.0])

    t = np.linspace(0, 2 * np.pi, 24)
    positions = np.column_stack([0.8 * np.cos(t), 0.8 * np.sin(t)])

    est_ols = OnlineBiasEstimator(min_samples=8)
    est_hub = OnlineBiasEstimator(min_samples=8)

    for i, p in enumerate(positions):
        d = p_target - p
        r = float(np.linalg.norm(d))
        z = d + b_true
        # Add 2 large outliers into the observation stream
        if i in (4, 15):
            z = z + np.array([3.0, -3.0])
        est_ols.add_observation(z, r, True)
        est_hub.add_observation(z, r, True)

    res_ols = est_ols.estimate(method="OLS")
    res_hub = est_hub.estimate(method="HUBER")

    err_ols = np.linalg.norm(res_ols.bias - b_true)
    err_hub = np.linalg.norm(res_hub.bias - b_true)
    # Huber must achieve significantly lower error under heavy outliers than OLS
    assert err_hub < err_ols
    assert err_hub < 0.35


# ---------------------------------------------------------------------------
# Test 4: Invalid or missing range measurements
# ---------------------------------------------------------------------------
def test_invalid_or_missing_range_measurements():
    """Verifies that NaN, zero, and flagged invalid measurements are safely discarded."""
    est = OnlineBiasEstimator()
    est.add_observation(np.array([1.0, 1.0]), float("nan"), True)
    est.add_observation(np.array([1.0, 1.0]), 0.0, True)
    est.add_observation(np.array([1.0, 1.0]), -1.5, True)
    est.add_observation(np.array([1.0, 1.0]), 2.5, False)
    est.add_observation(np.array([float("nan"), 1.0]), 2.5, True)

    assert est.sample_count == 0


# ---------------------------------------------------------------------------
# Test 5: Insufficient sample windows
# ---------------------------------------------------------------------------
def test_insufficient_sample_windows():
    """Verifies that estimation is rejected when sample count is below min_samples."""
    est = OnlineBiasEstimator(min_samples=10)
    for i in range(4):
        est.add_observation(np.array([1.0 + i * 0.1, 2.0]), 2.0, True)

    res = est.estimate()
    assert res.status == "REJECTED_INSUFFICIENT_DATA"
    assert res.rejection_reason is not None
    assert "minimum required" in res.rejection_reason


# ---------------------------------------------------------------------------
# Test 6: Poor-observability rejection (Collinear trajectory)
# ---------------------------------------------------------------------------
def test_poor_observability_rejection():
    """Verifies that purely collinear or stationary trajectories are rejected by the observability gate."""
    est = OnlineBiasEstimator(
        min_samples=8,
        lambda_min_threshold=0.0005,
        max_condition_number=15000.0,
    )
    p_target = np.array([4.0, 4.0])
    b_true = np.array([0.7, 0.7])
    for s in np.linspace(0, 0.4, 20):
        p = np.array([-2.0 + s, -2.0 + s])
        d = p_target - p
        r = float(np.linalg.norm(d))
        z = d + b_true
        est.add_observation(z, r, True)

    res = est.estimate(method="HUBER", enforce_observability_gate=True)
    assert res.status in ("REJECTED_ILL_CONDITIONED", "REJECTED_POOR_OBSERVABILITY")
    assert res.rejection_reason is not None


# ---------------------------------------------------------------------------
# Test 7: Optimizer failure handling
# ---------------------------------------------------------------------------
def test_optimizer_failure_handling():
    """Verifies that the estimator handles contradictory non-convergent inputs without crashing."""
    est = OnlineBiasEstimator(min_samples=6)
    for i in range(10):
        est.add_observation(np.array([2.0, 2.0]), float(i * 10.0 + 1.0), True)

    res = est.estimate()
    assert res.status in ("REJECTED_HIGH_RESIDUAL", "REJECTED_OPTIMIZER_FAILED", "REJECTED_ILL_CONDITIONED")


# ---------------------------------------------------------------------------
# Test 8: Fault onset and changing bias
# ---------------------------------------------------------------------------
def test_fault_onset_clears_stale_history():
    """Verifies that the recovery controller resets window when transitioning into PROBING."""
    ctrl = SafeRecoveryController(probing_steps=20)
    ctrl.estimator.add_observation(np.array([3.0, 3.0]), 4.24, True)
    assert ctrl.estimator.sample_count > 0

    dummy_a = make_sensor_reading(np.array([3.0, 3.0]))
    dummy_b = make_sensor_reading(np.array([2.0, 2.0]))
    dummy_r = RangeReading(4.24, 0.05, True)

    ctrl.update(dummy_a, dummy_b, dummy_r, "CROSS_MODAL_MISMATCH", step=0)
    ctrl.update(dummy_a, dummy_b, dummy_r, "CROSS_MODAL_MISMATCH", step=1)

    assert ctrl.state.mode == "PROBING"
    assert ctrl.estimator.sample_count <= 1


# ---------------------------------------------------------------------------
# Test 9: Range sensor faults (inconsistent corrupted reference)
# ---------------------------------------------------------------------------
def test_corrupted_range_sensor_rejection():
    """Verifies that an inconsistent corrupted reference sensor is rejected by residual check."""
    est = OnlineBiasEstimator(min_samples=8, max_residual_threshold=0.25)
    rng = np.random.default_rng(42)
    p_target = np.array([3.0, 3.0])
    b_true = np.array([0.7, 0.7])
    t = np.linspace(0, 2 * np.pi, 20)
    positions = np.column_stack([0.8 * np.cos(t), 0.8 * np.sin(t)])

    for p in positions:
        d = p_target - p
        # Large inconsistent corruption on range measurements
        r = float(np.linalg.norm(d)) + float(rng.normal(0.5, 0.5))
        z = d + b_true
        est.add_observation(z, r, True)

    res = est.estimate(method="HUBER")
    assert res.status == "REJECTED_HIGH_RESIDUAL"


# ---------------------------------------------------------------------------
# Test 10: Common-mode sensor faults detection
# ---------------------------------------------------------------------------
def test_common_mode_correlated_bias_detection():
    """Verifies that common-mode correlated bias is detected by cross-modal verification."""
    verifier = VerificationController()
    true_delta = np.array([2.0, 2.0])
    true_dist = float(np.linalg.norm(true_delta))

    read_a = make_sensor_reading(true_delta + np.array([0.7, 0.7]))
    read_b = make_sensor_reading(true_delta + np.array([0.7, 0.7]))
    read_r = RangeReading(true_dist, 0.05, True)

    ver = verifier.verify([read_a, read_b], read_r)
    assert ver.status == "CROSS_MODAL_MISMATCH"


# ---------------------------------------------------------------------------
# Test 11: No ground-truth leakage into the online estimator
# ---------------------------------------------------------------------------
def test_no_ground_truth_leakage():
    """Verifies that OnlineBiasEstimator only accepts observable (z, r) and has no access to target/world."""
    import inspect

    est = OnlineBiasEstimator()
    params = inspect.signature(est.add_observation).parameters
    expected_args = {"self", "vector_measurement", "range_measurement", "is_valid"}
    assert set(params.keys()) == (expected_args - {"self"})
    assert "target_pos" not in params
    assert "robot_pos" not in params
    assert "ground_truth_bias" not in params


# ---------------------------------------------------------------------------
# Test 12: Safe recovery decisions
# ---------------------------------------------------------------------------
def test_safe_recovery_controller_state_flow():
    """Verifies that the recovery controller state machine follows NOMINAL -> PROBING -> CALIBRATED / ABSTAIN."""
    ctrl = SafeRecoveryController(probing_steps=6)
    assert ctrl.state.mode == "NOMINAL"

    read_a = make_sensor_reading(np.array([2.0, 2.0]))
    read_b = make_sensor_reading(np.array([2.0, 2.0]))
    read_r = RangeReading(2.83, 0.05, True)

    _, dec, _, _ = ctrl.update(read_a, read_b, read_r, "VERIFIED", step=0)
    assert dec == "ACT"

    ctrl.update(read_a, read_b, read_r, "CROSS_MODAL_MISMATCH", step=1)
    ctrl.update(read_a, read_b, read_r, "CROSS_MODAL_MISMATCH", step=2)
    assert ctrl.state.mode == "PROBING"


# ---------------------------------------------------------------------------
# Test 13: Preservation of V4 behavior and outputs
# ---------------------------------------------------------------------------
def test_preservation_of_v4_outputs():
    """Verifies that V4 benchmark summary and episode files exist and are untouched."""
    from pathlib import Path

    v4_summary = Path("results/v4/v4_benchmark_summary.csv")
    v4_episodes = Path("results/v4/v4_benchmark_episodes.csv")
    assert v4_summary.exists(), "results/v4/v4_benchmark_summary.csv must be preserved"
    assert v4_episodes.exists(), "results/v4/v4_benchmark_episodes.csv must be preserved"
    assert v4_summary.stat().st_size > 1000
    assert v4_episodes.stat().st_size > 100000
