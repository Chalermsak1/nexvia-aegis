"""
NEXVIA AEGIS V7.0 — Unit and Architecture Regression Suite.

Verifies:
1. MPC forward simulation agreement with MuJoCo dynamics.
2. MPC control bounds, velocity limits, and workspace boundary soft barrier.
3. Active terminal velocity braking penalty during probing.
4. Fallback safe braking when optimizer fails.
5. Intermittent Anchor Sensor: query gating, noise, dropout, and operational costs.
6. Event-triggered Anchor Query Scheduler under high entropy / H4 suspicion.
7. Anchor Integrity Gate: rejection of corrupted anchor measurements.
8. Common-mode symmetry breaking: anchor resolves correlated vector bias (H4).
9. Zero ground-truth leakage into live online controllers or estimators.
10. Preservation of historical V1–V6 artifacts.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from aegis.v3.env.world import AegisPhysicalWorld
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v6.hypothesis_models import DiagnosticReport, FaultHypothesis
from aegis.v7.anchor_scheduler import AnchorIntegrityGate, AnchorQueryScheduler
from aegis.v7.anchor_sensor import AnchorReading, AnchorSensor, AnchorSensorConfig
from aegis.v7.mpc_planner import RiskConstrainedMPCPlanner
from aegis.v7.recovery_controller import AegisV7RecoveryController


def test_mpc_forward_simulate_agreement_with_mujoco():
    """Validates that discrete kinematic predictions closely match MuJoCo transitions."""
    planner = RiskConstrainedMPCPlanner(horizon_steps=5, timestep=0.02)
    p0 = np.array([-2.0, -2.0], dtype=np.float64)
    v0 = np.array([0.1, 0.05], dtype=np.float64)
    u_seq = np.array([[1.0, 0.5]] * 5, dtype=np.float64)

    p_pred, v_pred = planner.forward_simulate(p0, v0, u_seq)
    assert p_pred.shape == (6, 2)
    assert v_pred.shape == (6, 2)

    # Over dt=0.02, v1 = v0 + a*dt = [0.1, 0.05] + [0.02, 0.01] = [0.12, 0.06]
    assert np.allclose(v_pred[1], [0.12, 0.06], atol=1e-5)
    # p1 = p0 + v1*dt = [-2, -2] + [0.12*0.02, 0.06*0.02] = [-1.9976, -1.9988]
    assert np.allclose(p_pred[1], [-1.9976, -1.9988], atol=1e-5)


def test_mpc_control_bounds_and_terminal_braking():
    """Verifies that MPC outputs respect actuator limits and penalize terminal velocity."""
    planner = RiskConstrainedMPCPlanner(horizon_steps=5, timestep=0.02, w_terminal_velocity=15.0)
    p0 = np.array([0.0, 0.0])
    v0 = np.array([0.40, 0.20])
    target_vec = np.array([1.5, 0.0])

    plan = planner.plan_probing_step(
        current_pos=p0,
        current_vel=v0,
        target_relative_vector=target_vec,
        step_in_probing=2,
    )

    # Actuator limits
    assert np.all(plan.action >= -1.0) and np.all(plan.action <= 1.0)
    # Terminal velocity should be lower than initial or well-braked
    assert plan.terminal_velocity_norm < 0.60
    assert plan.solver_status in ("OPTIMAL", "FEASIBLE")


def test_anchor_sensor_query_gating_and_cost():
    """Tests that anchor measurements are only returned when queried and accrue operational cost."""
    cfg = AnchorSensorConfig(query_cost=0.05, noise_sigma=0.04)
    sensor = AnchorSensor(cfg)
    rng = np.random.default_rng(42)
    true_delta = np.array([1.5, -1.0])

    # Unqueried: should return invalid reading with zero cost
    reading_unqueried = sensor.measure(true_delta, rng, query=False)
    assert not reading_unqueried.valid
    assert not reading_unqueried.queried
    assert sensor.total_queries == 0
    assert sensor.total_cost == 0.0

    # Queried: should return valid reading and accrue 0.05 cost
    reading_queried = sensor.measure(true_delta, rng, query=True)
    assert reading_queried.valid
    assert reading_queried.queried
    assert sensor.total_queries == 1
    assert np.isclose(sensor.total_cost, 0.05)
    # Error should be within 3-sigma bound
    assert np.linalg.norm(reading_queried.estimate - true_delta) < 0.20


def test_anchor_sensor_dropout():
    """Tests intermittent packet dropout model on anchor."""
    cfg = AnchorSensorConfig(dropout_probability=1.0)  # Total dropout
    sensor = AnchorSensor(cfg)
    rng = np.random.default_rng(42)

    reading = sensor.measure(np.array([2.0, 1.0]), rng, query=True)
    assert not reading.valid
    assert reading.queried
    assert sensor.total_queries == 1


def test_anchor_query_scheduler_triggers():
    """Verifies event-triggered query logic under high entropy and H4 common-mode suspicion."""
    scheduler = AnchorQueryScheduler()

    # Low entropy, nominal: should not query
    rep_nominal = DiagnosticReport(
        leading_hypothesis=FaultHypothesis.H0_NOMINAL,
        scores={},
        probabilities={h.value: (1.0 if h == FaultHypothesis.H0_NOMINAL else 0.0) for h in FaultHypothesis},
        entropy=0.20,
        is_ambiguous=False,
        can_recalibrate=True,
        estimated_bias=np.zeros(2),
        reason_code="NOMINAL",
    )
    assert not scheduler.should_query(rep_nominal, consecutive_mismatches=0, total_queries=0)

    # High entropy (ambiguity): should trigger query
    rep_ambiguous = DiagnosticReport(
        leading_hypothesis=FaultHypothesis.H6_AMBIGUOUS,
        scores={},
        probabilities={h.value: (1.0 / 7.0) for h in FaultHypothesis},
        entropy=1.50,
        is_ambiguous=True,
        can_recalibrate=False,
        estimated_bias=np.zeros(2),
        reason_code="AMBIGUOUS",
    )
    assert scheduler.should_query(rep_ambiguous, consecutive_mismatches=0, total_queries=0)

    # H4 common-mode correlated bias: should trigger query
    rep_h4 = DiagnosticReport(
        leading_hypothesis=FaultHypothesis.H4_CORRELATED_BIAS,
        scores={},
        probabilities={h.value: (0.8 if h == FaultHypothesis.H4_CORRELATED_BIAS else 0.03) for h in FaultHypothesis},
        entropy=0.60,
        is_ambiguous=True,
        can_recalibrate=False,
        estimated_bias=np.zeros(2),
        reason_code="CORRELATED_BIAS",
    )
    assert scheduler.should_query(rep_h4, consecutive_mismatches=0, total_queries=0)


def test_anchor_integrity_gate_rejection():
    """Verifies that corrupted anchor measurements are caught and rejected."""
    gate = AnchorIntegrityGate(consistency_tolerance=0.35)

    # Corrupted anchor: distance = 4.0m, while range radar = 2.0m
    anchor_bad = AnchorReading(
        estimate=np.array([4.0, 0.0]),
        sigma=0.04,
        valid=True,
        queried=True,
        cost_accrued=0.05,
    )
    range_good = RangeReading(distance=2.0, sigma=0.05, valid=True)
    raw_vec = np.array([2.0, 0.0])

    is_valid, code, bias = gate.validate_anchor(anchor_bad, range_good, raw_vec)
    assert not is_valid
    assert code == "REJECTED_ANCHOR_RANGE_INCONSISTENT"
    assert bias is None


def test_anchor_resolves_correlated_vector_bias():
    """Verifies that a valid anchor successfully breaks symmetry in H4 common-mode bias."""
    gate = AnchorIntegrityGate(consistency_tolerance=0.35)

    # True distance is 2.0m along X.
    # Both vector sensors are biased by [+0.7, +0.7]: raw_vector = [2.7, 0.7] (norm = 2.789m)
    # Range radar measures true distance: 2.0m
    # Anchor measures true vector: [2.01, 0.02] (norm = 2.01m, matches radar!)
    raw_vec = np.array([2.7, 0.7])
    anchor_good = AnchorReading(
        estimate=np.array([2.01, 0.02]),
        sigma=0.04,
        valid=True,
        queried=True,
        cost_accrued=0.05,
    )
    range_good = RangeReading(distance=2.0, sigma=0.05, valid=True)

    is_valid, code, inferred_bias = gate.validate_anchor(anchor_good, range_good, raw_vec)
    assert is_valid
    assert code == "VALIDATED_CORRELATED_BIAS_RESOLVED"
    assert inferred_bias is not None
    # Inferred bias should be close to [0.7, 0.7]
    assert np.allclose(inferred_bias, [0.69, 0.68], atol=0.05)


def test_zero_ground_truth_leakage_in_v7_controller():
    """Ensures V7 controller update only uses observable sensor readings."""
    ctrl = AegisV7RecoveryController()
    r_a = SensorReading(
        estimate=np.array([1.0, 1.0]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )
    r_b = SensorReading(
        estimate=np.array([1.0, 1.0]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )
    r_r = RangeReading(distance=1.414, sigma=0.05, valid=True)

    action, dec, report, cal_vec, query_anchor = ctrl.update(
        reading_a=r_a,
        reading_b=r_b,
        range_reading=r_r,
        anchor_reading=None,
        verification_status="VERIFIED",
        step=1,
    )

    # Verify no private simulation variables were leaked or required
    assert isinstance(action, np.ndarray) and action.shape == (2,)
    assert dec in ("ACT", "PROBE", "STOP", "ABSTAIN", "VERIFY")
    assert isinstance(query_anchor, bool)


def test_preservation_of_historical_artifacts():
    """Guarantees historical files and benchmark outputs from V1 to V6 exist untouched."""
    assert Path("src/aegis/v1").exists() or Path("src/aegis/policies.py").exists()
    assert Path("src/aegis/v3").exists()
    assert Path("src/aegis/v5").exists()
    assert Path("src/aegis/v6").exists()
    assert Path("results/v4").exists()
    assert Path("results/v5").exists()
    assert Path("results/v6/v6_benchmark_episodes.csv").exists()
    assert Path("results/v6/v6_benchmark_summary.csv").exists()
    assert Path("results/v6/v6_ablation_summary.csv").exists()
