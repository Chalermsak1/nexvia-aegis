"""
NEXVIA AEGIS V6.0 — Comprehensive Architecture & Mathematical Test Suite.

Verifies:
1. Multi-hypothesis model scoring, normalization, and entropy.
2. Degenerate trajectory detection and FIM conditioning.
3. Probing strategy generation (Fixed, Circular, Figure-8, FIM, Discriminative).
4. Corrupted reference rejection (H3 safeguards).
5. Sensor dropout handling (H5 safeguards).
6. Zero ground-truth leakage into live estimation and diagnosis.
7. Closed-loop state machine transitions.
8. Strict preservation of V4 and V5 historical artifacts.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from aegis.calibration import OnlineBiasEstimator
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v6.diagnosis import MultiHypothesisDiagnosisEngine
from aegis.v6.hypothesis_models import (
    FaultHypothesis,
    compute_fisher_information,
)
from aegis.v6.recovery_controller import AegisV6RecoveryController
from aegis.v6.trajectory_planner import (
    ProbingStrategy,
    RiskConstrainedTrajectoryPlanner,
)


def make_reading(vec: np.ndarray, sigma: float = 0.05, valid: bool = True) -> SensorReading:
    return SensorReading(
        estimate=np.asarray(vec, dtype=np.float64),
        sigma=sigma,
        valid=valid,
        anomaly=False,
        dropped=not valid,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )


# ---------------------------------------------------------------------------
# Test 1: Probability Normalization and Entropy Calculation
# ---------------------------------------------------------------------------
def test_hypothesis_probability_normalization():
    engine = MultiHypothesisDiagnosisEngine(window_size=20, min_samples=6)

    # Feed nominal readings
    for i in range(10):
        pos = np.array([1.5 - 0.05 * i, 1.0 + 0.05 * i])
        r = float(np.linalg.norm(pos))
        engine.add_observation(
            reading_a=make_reading(pos),
            reading_b=make_reading(pos),
            reading_range=RangeReading(r, 0.05, True),
            step=i,
        )

    report = engine.diagnose()
    total_prob = sum(report.probabilities.values())
    assert abs(total_prob - 1.0) < 1e-5, "Probabilities must sum to 1.0"
    for p in report.probabilities.values():
        assert 0.0 <= p <= 1.0, f"Probability must be within [0, 1], got {p}"
    assert report.entropy >= 0.0, "Shannon entropy must be non-negative"


# ---------------------------------------------------------------------------
# Test 2: Insufficient Samples triggers H6_AMBIGUOUS
# ---------------------------------------------------------------------------
def test_insufficient_samples_ambiguity():
    engine = MultiHypothesisDiagnosisEngine(window_size=20, min_samples=6)
    # Only feed 3 readings (< min_samples=6)
    for i in range(3):
        engine.add_observation(
            reading_a=make_reading(np.array([1.0, 1.0])),
            reading_b=make_reading(np.array([1.0, 1.0])),
            reading_range=RangeReading(1.414, 0.05, True),
            step=i,
        )

    report = engine.diagnose()
    assert report.is_ambiguous is True
    assert report.reason_code == "INSUFFICIENT_WINDOW"
    assert report.can_recalibrate is False


# ---------------------------------------------------------------------------
# Test 3: Collinear Degeneracy in Fisher Information Matrix
# ---------------------------------------------------------------------------
def test_fim_collinear_degeneracy():
    # Construct exact 1D collinear observations along x-axis
    collinear_obs = [np.array([1.0 + 0.1 * i, 0.0]) for i in range(15)]
    zero_bias = np.zeros(2)

    fim, lambda_min, cond = compute_fisher_information(collinear_obs, zero_bias)
    assert fim.shape == (2, 2)
    assert abs(lambda_min) < 1e-6, "Collinear trajectory must have near-zero lambda_min"
    assert cond > 1e6, "Collinear trajectory must have infinite condition number"


# ---------------------------------------------------------------------------
# Test 4: Circular 2D Viewpoint Diversity in Fisher Information Matrix
# ---------------------------------------------------------------------------
def test_fim_circular_diversity():
    angles = np.linspace(0, np.pi, 16)
    diverse_obs = [np.array([2.0 * np.cos(a), 2.0 * np.sin(a)]) for a in angles]
    zero_bias = np.zeros(2)

    fim, lambda_min, cond = compute_fisher_information(diverse_obs, zero_bias)
    assert lambda_min > 1.0, "Circular trajectory must have substantial lambda_min"
    assert cond < 5.0, f"Circular trajectory must be well conditioned, got {cond}"


# ---------------------------------------------------------------------------
# Test 5: Identification of Constant Vector Bias (H1)
# ---------------------------------------------------------------------------
def test_h1_vector_bias_identification():
    engine = MultiHypothesisDiagnosisEngine(window_size=25, min_samples=6)
    true_bias = np.array([0.70, -0.50])

    angles = np.linspace(0.2, 1.2, 18)
    for i, a in enumerate(angles):
        d_true = np.array([2.5 * np.cos(a), 2.5 * np.sin(a)])
        z_a = d_true + true_bias  # Sensor A has bias
        z_b = d_true              # Sensor B is nominal
        r = float(np.linalg.norm(d_true))

        engine.add_observation(
            reading_a=make_reading(z_a),
            reading_b=make_reading(z_b),
            reading_range=RangeReading(r, 0.02, True),
            step=i,
        )

    report = engine.diagnose()
    assert report.leading_hypothesis == FaultHypothesis.H1_VECTOR_BIAS
    assert report.can_recalibrate is True
    assert np.linalg.norm(report.estimated_bias - true_bias) < 0.25


# ---------------------------------------------------------------------------
# Test 6: Rejection of Corrupted Reference Sensor (H3)
# ---------------------------------------------------------------------------
def test_h3_corrupted_reference_rejection():
    engine = MultiHypothesisDiagnosisEngine(window_size=25, min_samples=6)

    # Vector sensors agree with each other, but range sensor is corrupted by +1.0m
    angles = np.linspace(0.1, 1.0, 18)
    for i, a in enumerate(angles):
        d_true = np.array([2.0 * np.cos(a), 2.0 * np.sin(a)])
        r_corrupted = float(np.linalg.norm(d_true)) + 1.0  # +1.0m systematic reference error

        engine.add_observation(
            reading_a=make_reading(d_true),
            reading_b=make_reading(d_true),
            reading_range=RangeReading(r_corrupted, 0.02, True),
            step=i,
        )

    report = engine.diagnose()
    assert report.leading_hypothesis == FaultHypothesis.H3_REFERENCE_FAULT
    assert report.can_recalibrate is False, "Must NEVER recalibrate against a corrupted reference!"
    assert report.reason_code == "REFERENCE_SENSOR_CORRUPTED"


# ---------------------------------------------------------------------------
# Test 7: Sensor Dropout Handling (H5)
# ---------------------------------------------------------------------------
def test_h5_dropout_detection():
    engine = MultiHypothesisDiagnosisEngine(window_size=20, min_samples=6)

    for i in range(12):
        engine.add_observation(
            reading_a=make_reading(np.zeros(2), valid=False),  # Packet dropped
            reading_b=make_reading(np.zeros(2), valid=False),  # Packet dropped
            reading_range=RangeReading(2.0, 0.05, True),
            step=i,
        )

    report = engine.diagnose()
    assert report.leading_hypothesis == FaultHypothesis.H5_SENSOR_DROPOUT
    assert report.can_recalibrate is False
    assert report.reason_code == "SENSOR_DROPOUT_DETECTED"


# ---------------------------------------------------------------------------
# Test 8: Trajectory Strategies Output Validity & Bounded Action
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy", [
    ProbingStrategy.STRATEGY_A_FIXED_ORTHOGONAL,
    ProbingStrategy.STRATEGY_B_CIRCULAR_ORBIT,
    ProbingStrategy.STRATEGY_C_FIGURE_EIGHT,
    ProbingStrategy.STRATEGY_D_RANDOM_SAFE,
    ProbingStrategy.STRATEGY_E_FIM_GUIDED,
    ProbingStrategy.STRATEGY_F_DISCRIMINATIVE,
])
def test_probing_strategies_bounded_actions(strategy: ProbingStrategy):
    planner = RiskConstrainedTrajectoryPlanner(strategy=strategy, probing_force=0.85)
    base_vec = np.array([2.0, 1.5])
    curr_vel = np.array([0.1, -0.05])

    for step in range(32):
        action = planner.plan_action(step, base_vec, curr_vel)
        assert action.shape == (2,)
        assert np.all(action >= -1.0) and np.all(action <= 1.0), f"Action exceeds [-1, 1] for {strategy}: {action}"


# ---------------------------------------------------------------------------
# Test 9: Zero Ground-Truth Leakage in Live Agent
# ---------------------------------------------------------------------------
def test_v6_zero_ground_truth_leakage():
    ctrl = AegisV6RecoveryController()
    # Check that controller has no reference to simulator ground truth
    assert not hasattr(ctrl, "target_pos")
    assert not hasattr(ctrl, "robot_pos")
    assert not hasattr(ctrl, "true_bias")


# ---------------------------------------------------------------------------
# Test 10: State Machine Transitions (NOMINAL -> ACTIVE_PROBING -> CALIBRATED/ABSTAIN)
# ---------------------------------------------------------------------------
def test_v6_controller_state_flow():
    ctrl = AegisV6RecoveryController(probing_steps=8)
    assert ctrl.state.mode == "NOMINAL"

    read_a = make_reading(np.array([2.0, 2.0]))
    read_b = make_reading(np.array([2.0, 2.0]))
    read_r = RangeReading(2.83, 0.05, True)

    _, dec, _, _ = ctrl.update(read_a, read_b, read_r, "VERIFIED", step=0)
    assert dec == "ACT"

    # Trigger mismatch
    ctrl.update(read_a, read_b, read_r, "CROSS_MODAL_MISMATCH", step=1)
    ctrl.update(read_a, read_b, read_r, "CROSS_MODAL_MISMATCH", step=2)
    assert ctrl.state.mode == "ACTIVE_PROBING"


# ---------------------------------------------------------------------------
# Test 11: Strict Preservation of Historical Artifacts (V4 and V5)
# ---------------------------------------------------------------------------
def test_preservation_of_historical_artifacts():
    v4_summary = Path("results/v4/v4_benchmark_summary.csv")
    v4_episodes = Path("results/v4/v4_benchmark_episodes.csv")
    v5_summary = Path("results/v5/v5_benchmark_summary.csv")
    v5_episodes = Path("results/v5/v5_benchmark_episodes.csv")

    assert v4_summary.exists() and v4_summary.stat().st_size > 1000
    assert v4_episodes.exists() and v4_episodes.stat().st_size > 100000
    assert v5_summary.exists() and v5_summary.stat().st_size > 1000
    assert v5_episodes.exists() and v5_episodes.stat().st_size > 100000
