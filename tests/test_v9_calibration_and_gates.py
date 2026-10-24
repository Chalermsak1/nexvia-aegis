"""
NEXVIA AEGIS V9.0 — Unit Tests for Per-Sensor Disjoint Calibration and Symmetric Anchor/Range Gate.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.anchor_range_gate import AnchorRangeStatus, SymmetricAnchorRangeGate
from aegis.v9.sensor_calibration import DisjointPerSensorCalibrator, SensorCalStatus


def _mk_vec(est: np.ndarray | list[float], sigma: float = 0.05, valid: bool = True) -> SensorReading:
    return SensorReading(
        estimate=np.asarray(est, dtype=np.float64),
        sigma=sigma,
        valid=valid,
        anomaly=False,
        dropped=not valid,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )


def _mk_rng(dist: float, sigma: float = 0.05, valid: bool = True) -> RangeReading:
    return RangeReading(distance=dist, sigma=sigma, valid=valid, anomaly=False, dropped=not valid)


def _mk_anc(est: np.ndarray | list[float], sigma: float = 0.04, valid: bool = True) -> AnchorReading:
    return AnchorReading(
        estimate=np.asarray(est, dtype=np.float64),
        sigma=sigma,
        valid=valid,
        queried=valid,
        cost_accrued=0.05 if valid else 0.0,
    )


def test_disjoint_windows_independent_estimators_and_disagreement_preservation():
    """
    Verifies:
    1. Fit indices strictly in {1..22}, gap {23,24} excluded, val indices strictly in {25..36}.
    2. Held-out validation observations NEVER enter `estimator_a` or `estimator_b`.
    3. Independent bias recovery on `vec_a` (+0.6, +0.4) and `vec_b` (-0.5, +0.5).
    4. Raw inter-sensor disagreement (~1.10m) and calibrated disagreement (~0.06m) tracked separately.
    5. Frozen bias immutability (no online refit or buffer mutation permitted).
    """
    rng = np.random.default_rng(701)
    cal = DisjointPerSensorCalibrator()

    true_b_a = np.array([0.60, 0.40])
    true_b_b = np.array([-0.50, 0.50])

    for p_step in range(1, 37):
        angle = 0.08 * p_step
        d_true = np.array([2.2 * math.cos(angle), 2.2 * math.sin(angle)])
        ra = _mk_vec(d_true + true_b_a + rng.normal(0.0, 0.03, size=2), sigma=0.05)
        rb = _mk_vec(d_true + true_b_b + rng.normal(0.0, 0.03, size=2), sigma=0.05)
        rr = _mk_rng(float(np.linalg.norm(d_true)) + float(rng.normal(0.0, 0.03)), sigma=0.05)
        anc = (d_true + rng.normal(0.0, 0.03, size=2)) if p_step in (4, 14) else None

        ok = cal.record_probing_step(
            p_step,
            ra,
            rb,
            rr,
            verified_anchor_estimate=anc,
            verified_anchor_sigma=0.04,
        )
        assert ok

    fit_a = set(cal.fit_step_indices("vec_a"))
    val_a = set(cal.val_step_indices("vec_a"))
    assert fit_a == set(range(1, 23))
    assert val_a == set(range(25, 37))
    assert fit_a.isdisjoint(val_a)
    assert 23 not in fit_a and 23 not in val_a
    assert 24 not in fit_a and 24 not in val_a
    # Underlying OnlineBiasEstimator instances received ONLY the 22 fit samples, never validation!
    assert cal.estimator_a.sample_count == 22
    assert cal.estimator_b.sample_count == 22

    st_a, st_b = cal.finalize_validation(tau_val=0.12, tau_diff=3.80)
    assert st_a.status == SensorCalStatus.CALIBRATED_VALID
    assert st_b.status == SensorCalStatus.CALIBRATED_VALID
    assert float(np.linalg.norm(st_a.bias - true_b_a)) < 0.08
    assert float(np.linalg.norm(st_b.bias - true_b_b)) < 0.08

    # Raw disagreement (~1.1045 m) vs bias-corrected disagreement (< 0.12 m) preserved separately
    assert cal.raw_disagreement_rms is not None and cal.raw_disagreement_rms > 0.95
    assert cal.calibrated_disagreement_rms is not None and cal.calibrated_disagreement_rms < 0.12

    # Frozen bias arrays are read-only and post-freeze recording is prohibited
    assert not st_a.bias.flags.writeable
    with pytest.raises(ValueError):
        st_a.bias[0] = 0.0
    with pytest.raises(RuntimeError):
        cal.record_probing_step(25, ra, rb, rr)


def test_single_sensor_dropout_isolation_without_fusion_bias_jumps():
    """
    Verifies that intermittent dropout on `vec_b` under antipodal biases neither contaminates
    `vec_a` nor causes fused-vector jumps when `vec_b` drops out during CALIBRATED fusion.
    """
    rng = np.random.default_rng(702)
    cal = DisjointPerSensorCalibrator()
    b_a = np.array([0.55, 0.40])
    b_b = np.array([-0.45, -0.35])

    for p_step in range(1, 37):
        d_true = np.array([1.8 + 0.03 * p_step, -1.2 + 0.02 * p_step])
        # Drop vec_b on 80% of validation steps so vec_b fails n_val >= 6 while vec_a stays clean
        b_valid = True if p_step <= 22 else (p_step in (25, 26, 27))
        ra = _mk_vec(d_true + b_a + rng.normal(0.0, 0.02, size=2))
        rb = _mk_vec(d_true + b_b + rng.normal(0.0, 0.02, size=2), valid=b_valid)
        rr = _mk_rng(float(np.linalg.norm(d_true)) + float(rng.normal(0.0, 0.02)))
        anc = d_true if p_step == 4 else None
        cal.record_probing_step(p_step, ra, rb, rr, verified_anchor_estimate=anc)

    st_a, st_b = cal.finalize_validation(tau_val=0.12, tau_diff=3.80)
    assert st_a.status == SensorCalStatus.CALIBRATED_VALID
    assert st_b.status == SensorCalStatus.DROPOUT_INSUFFICIENT
    assert math.isinf(st_b.variance_u2)

    # Check fusion stability when vec_b toggles valid/invalid: zero bias jump!
    d_now = np.array([1.20, -0.80])
    f_both = cal.fuse_calibrated(_mk_vec(d_now + b_a), _mk_vec(d_now + b_b, valid=True))
    f_drop = cal.fuse_calibrated(_mk_vec(d_now + b_a), _mk_vec([0.0, 0.0], valid=False))
    assert f_both.valid and f_drop.valid
    assert np.allclose(f_both.fused_vector, f_drop.fused_vector, atol=1e-12)
    assert float(np.linalg.norm(f_drop.fused_vector - d_now)) < 0.08


def test_insufficient_validation_samples_and_invalid_value_rejection():
    """Verifies n_val < 6 fails closed and NaN/Inf in valid readings is rejected immediately."""
    cal = DisjointPerSensorCalibrator()
    d_true = np.array([2.0, 0.5])
    for p_step in range(1, 30):  # Only 5 validation steps (25..29) < n_val_min=6!
        cal.record_probing_step(
            p_step,
            _mk_vec(d_true),
            _mk_vec(d_true),
            _mk_rng(float(np.linalg.norm(d_true))),
            verified_anchor_estimate=d_true if p_step == 3 else None,
        )
    st_a, st_b = cal.finalize_validation(tau_val=0.12, tau_diff=3.80)
    assert st_a.status == SensorCalStatus.DROPOUT_INSUFFICIENT
    assert st_b.status == SensorCalStatus.DROPOUT_INSUFFICIENT
    assert not cal.has_any_valid_calibrated_sensor()

    # NaN in valid reading fails closed before entering estimator buffer
    cal_nan = DisjointPerSensorCalibrator()
    ok = cal_nan.record_probing_step(
        1,
        _mk_vec([float("nan"), 1.0], valid=True),
        _mk_vec(d_true),
        _mk_rng(float(np.linalg.norm(d_true))),
    )
    assert not ok
    assert cal_nan.invalid_input_detected
    assert cal_nan.estimator_a.sample_count == 0


def test_anchor_range_gate_consistent_conflicting_and_insufficient_chord():
    """
    Verifies SymmetricAnchorRangeGate:
    - Consistent modalities -> CONSISTENT.
    - Single-epoch conflict -> ABSTAIN_DISAGREEMENT (neither range nor anchor assumed oracle).
    - Two-epoch conflict with chord < 0.40 m -> ABSTAIN_DISAGREEMENT.
    """
    gate = SymmetricAnchorRangeGate(tau_ar=4.20, min_chord_m=0.40, min_epoch_separation_steps=10)
    d1 = np.array([2.0, 0.0])

    # Consistent anchor and range
    res_ok = gate.evaluate(
        _mk_anc(d1),
        _mk_rng(2.01),
        _mk_vec(d1 + [0.7, 0.7]),
        _mk_vec(d1 + [0.7, 0.7]),
        step=3,
    )
    assert res_ok.status == AnchorRangeStatus.CONSISTENT
    assert not gate.has_unresolved_disagreement()

    # Conflicting modalities (+1.0m range fault) on single epoch -> fail closed!
    gate.reset()
    res_conf1 = gate.evaluate(
        _mk_anc(d1),
        _mk_rng(3.00),
        _mk_vec(d1 + [0.7, 0.7]),
        _mk_vec(d1 + [0.7, 0.7]),
        step=3,
    )
    assert res_conf1.status == AnchorRangeStatus.ABSTAIN_DISAGREEMENT
    assert gate.has_unresolved_disagreement()

    # Second epoch 12 steps later, but displacement is only 0.20 m (< 0.40 m) -> still ABSTAIN!
    d2_short = np.array([2.0, 0.20])
    res_short = gate.evaluate(
        _mk_anc(d2_short),
        _mk_rng(float(np.linalg.norm(d2_short)) + 1.00),
        _mk_vec(d2_short + [0.7, 0.7]),
        _mk_vec(d2_short + [0.7, 0.7]),
        step=15,
    )
    assert res_short.status == AnchorRangeStatus.ABSTAIN_DISAGREEMENT
    assert "INSUFFICIENT_CHORD" in res_short.reason


def test_anchor_range_gate_valid_corroboration_common_mode_and_corrupted_anchor():
    """
    Verifies:
    1. Ambiguous curvature separation (<= 3.5 * sigma_dr) fails closed (`ABSTAIN_DISAGREEMENT`),
       whereas strong 2-epoch chord separation (>= 0.40m, > 3.5 * sigma_dr) corroborates
       healthy anchor under static range bias (`CORROBORATED_ANCHOR_RANGE_BIASED`).
    2. Common-mode drift suspicion blocks corroboration (`ABSTAIN_DISAGREEMENT`).
    3. Static anchor corruption `(1.2, -1.0)` (which cancels in Delta z_anc!) is caught by the
       range-increment curvature check and NEVER corroborated as valid anchor!
    4. Invalid/NaN readings fail closed (`INVALID_INPUT`).
    """
    gate_ambig = SymmetricAnchorRangeGate(tau_ar=4.20, min_chord_m=0.40, min_epoch_separation_steps=10)
    # Ambiguous transverse chord where |pred_dr_rng - obs_dr| = 0.130m <= 3.5 * sigma_dr (~0.402m):
    # MUST fail closed per Protocol Section 3.4.3 / D3!
    d1_amb = np.array([0.90, 0.00])
    d2_amb = np.array([0.90, 0.65])
    b_vec = np.array([0.50, 0.50])
    gate_ambig.evaluate(_mk_anc(d1_amb), _mk_rng(0.45), _mk_vec(d1_amb + b_vec), _mk_vec(d1_amb + b_vec), step=5)
    r_ambig = gate_ambig.evaluate(
        _mk_anc(d2_amb),
        _mk_rng(float(np.linalg.norm(d2_amb)) - 0.45),
        _mk_vec(d2_amb + b_vec),
        _mk_vec(d2_amb + b_vec),
        step=20,
    )
    assert r_ambig.status == AnchorRangeStatus.ABSTAIN_DISAGREEMENT

    # 1. Unambiguous 0.80m chord crossing origin under static range spoofing b_r = +1.00 m:
    # True d1 = (0.35, 0.0) -> true r1 = 0.35, spoofed r1 = 1.35
    # True d2 = (-0.45, 0.0) -> chord L = 0.80 >= 0.40; true r2 = 0.45, spoofed r2 = 1.45
    # Observed Delta r = +0.10 (anchor predicts +0.10; spoofed range circle r1=1.35 predicts -0.80 -> 0.90m > 3.5*sigma_dr!)
    gate = SymmetricAnchorRangeGate(tau_ar=4.20, min_chord_m=0.40, min_epoch_separation_steps=10)
    d1 = np.array([0.35, 0.00])
    d2 = np.array([-0.45, 0.00])
    b_r = 1.00

    r1 = gate.evaluate(
        _mk_anc(d1),
        _mk_rng(float(np.linalg.norm(d1)) + b_r),
        _mk_vec(d1 + b_vec),
        _mk_vec(d1 + b_vec),
        step=5,
    )
    assert r1.status == AnchorRangeStatus.ABSTAIN_DISAGREEMENT

    # 2. If common-mode drift is suspected on both sensors, corroboration MUST fail closed!
    r2_drift = gate.evaluate(
        _mk_anc(d2),
        _mk_rng(float(np.linalg.norm(d2)) + b_r),
        _mk_vec(d2 + b_vec),
        _mk_vec(d2 + b_vec),
        step=20,
        drift_suspected={"vec_a": True, "vec_b": True},
    )
    assert r2_drift.status == AnchorRangeStatus.ABSTAIN_DISAGREEMENT
    assert gate.has_unresolved_disagreement()

    # Without drift, valid 2-epoch chord corroborates anchor and identifies static range bias!
    gate.reset()
    gate.evaluate(
        _mk_anc(d1),
        _mk_rng(float(np.linalg.norm(d1)) + b_r),
        _mk_vec(d1 + b_vec),
        _mk_vec(d1 + b_vec),
        step=5,
    )
    r2_valid = gate.evaluate(
        _mk_anc(d2),
        _mk_rng(float(np.linalg.norm(d2)) + b_r),
        _mk_vec(d2 + b_vec),
        _mk_vec(d2 + b_vec),
        step=20,
    )
    assert r2_valid.status == AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED
    assert not gate.has_unresolved_disagreement()

    # 3. Corrupted anchor with static bias (1.2, -1.0) (`CORRUPTED_ANCHOR_STRESS`):
    # Delta z_anc == d2 - d1 cancels (1.2, -1.0), yet curvature range-increment catches it!
    gate_corrupt = SymmetricAnchorRangeGate(tau_ar=4.20)
    b_anc = np.array([1.20, -1.00])
    gate_corrupt.evaluate(
        _mk_anc(d1 + b_anc),
        _mk_rng(float(np.linalg.norm(d1))),
        _mk_vec(d1 + b_vec),
        _mk_vec(d1 + b_vec),
        step=5,
        calibrated_biases={"vec_a": b_vec, "vec_b": b_vec},
        calibrated_valid_flags={"vec_a": True, "vec_b": True},
    )
    r2_corrupt = gate_corrupt.evaluate(
        _mk_anc(d2 + b_anc),
        _mk_rng(float(np.linalg.norm(d2))),
        _mk_vec(d2 + b_vec),
        _mk_vec(d2 + b_vec),
        step=20,
        calibrated_biases={"vec_a": b_vec, "vec_b": b_vec},
        calibrated_valid_flags={"vec_a": True, "vec_b": True},
    )
    assert r2_corrupt.status != AnchorRangeStatus.CORROBORATED_ANCHOR_RANGE_BIASED
    assert r2_corrupt.status == AnchorRangeStatus.CORROBORATED_RANGE_ANCHOR_CORRUPTED

    # 4. Malformed NaN reading fails closed
    gate_bad = SymmetricAnchorRangeGate()
    r_bad = gate_bad.evaluate(
        _mk_anc([float("nan"), 0.0], valid=True),
        _mk_rng(1.0),
        _mk_vec(d1),
        _mk_vec(d1),
        step=1,
    )
    assert r_bad.status == AnchorRangeStatus.INVALID_INPUT
    assert gate_bad.has_unresolved_disagreement()
