"""
NEXVIA AEGIS — Phase 2: Tests for Native 3D-Aware Controller (Aegis3DAwareController).

Verifies:
1. Native 3D state tracking and clean reset.
2. Nominal 3D arrival verification (multi-sample range corroboration).
3. Prevention of false arrivals from vertical/altitude error (resolving Planar V9 flaw).
4. Continuous 3D bias calibration via episodic anchor queries.
5. Successful calibrated arrival without naive raw-sensor vetoes (resolving 3D Reality Gap).
6. Fail-closed safe abstention under total vector dropout or persistent range dropout.
"""

import math
import numpy as np
import pytest

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.controller_3d import Aegis3DAwareController, Sensor3DCalibration


def _make_reading_3d(vec: np.ndarray, sigma: float = 0.05, valid: bool = True) -> SensorReading:
    return SensorReading(
        estimate=np.asarray(vec, dtype=np.float64),
        sigma=float(sigma),
        valid=valid,
        anomaly=False,
        dropped=not valid,
        bias=np.zeros(3),
        drift=np.zeros(3),
    )


def _make_range(dist: float, sigma: float = 0.05, valid: bool = True) -> RangeReading:
    return RangeReading(
        distance=float(dist),
        sigma=float(sigma),
        valid=valid,
        dropped=not valid,
    )


def test_3d_controller_initialization_and_reset():
    ctrl = Aegis3DAwareController(success_radius=0.25)
    assert ctrl.mode == "NOMINAL"
    assert ctrl.terminal_reason == "ACTIVE"
    assert ctrl.cal_a.is_calibrated is False
    assert ctrl.cal_b.is_calibrated is False

    # Simulate one step and reset
    rd = _make_reading_3d(np.array([1.0, 1.0, 1.0]))
    rg = _make_range(math.sqrt(3.0))
    ctrl.update(rd, rd, rg, step=1)
    assert ctrl.step_count == 1
    assert ctrl.ville_monitor is not None

    ctrl.reset()
    assert ctrl.step_count == 0
    assert ctrl.ville_monitor is None
    assert ctrl.mode == "NOMINAL"


def test_nominal_3d_arrival_corroboration():
    ctrl = Aegis3DAwareController(success_radius=0.25)
    pos_3d = np.array([0.10, 0.10, 0.05])
    dist_3d = float(np.linalg.norm(pos_3d))
    assert dist_3d <= 0.25

    # Should take 3 consecutive verified samples to trigger STOP
    rd_a = _make_reading_3d(pos_3d)
    rd_b = _make_reading_3d(pos_3d)
    rg = _make_range(dist_3d)

    act1, dec1, _, _ = ctrl.update(rd_a, rd_b, rg, step=1)
    assert dec1 == "VERIFY"

    act2, dec2, _, _ = ctrl.update(rd_a, rd_b, rg, step=2)
    assert dec2 == "VERIFY"

    act3, dec3, _, _ = ctrl.update(rd_a, rd_b, rg, step=3)
    assert dec3 == "STOP"
    assert ctrl.terminal_reason == "3D_CALIBRATED_VERIFIED_ARRIVAL"
    assert np.allclose(act3, np.zeros(3))


def test_rejection_of_vertical_misalignment():
    """
    Planar V9 flaw: planar projection (x, y) = [0.10, 0.10] looks close (0.14m < 0.20m),
    but vertical z = 0.50m puts true distance at 0.52m > 0.25m.
    Aegis3DAwareController must reject this and continue navigating or verifying.
    """
    ctrl = Aegis3DAwareController(success_radius=0.25)
    # Planar coordinates are close, but z is far
    pos_3d = np.array([0.10, 0.10, 0.50])
    rd_a = _make_reading_3d(pos_3d)
    rd_b = _make_reading_3d(pos_3d)
    rg = _make_range(float(np.linalg.norm(pos_3d)))

    for step in range(1, 10):
        _, dec, nav, _ = ctrl.update(rd_a, rd_b, rg, step=step)
        assert dec != "STOP", f"Controller falsely confirmed arrival at z=0.50m on step {step}"
        assert ctrl.mode != "STOP"


def test_3d_bias_calibration_via_anchor():
    """
    When sensor A has a 3D bias, anchor observations calibrate the bias vector.
    """
    ctrl = Aegis3DAwareController(success_radius=0.25)
    true_delta = np.array([1.5, -1.0, 0.8])
    bias_a = np.array([0.6, -0.4, 0.5])

    # First feed disagreeing readings to trigger active probing
    rd_a = _make_reading_3d(true_delta + bias_a)
    rd_b = _make_reading_3d(true_delta)
    rg = _make_range(float(np.linalg.norm(true_delta)))

    _, dec, _, query_anchor = ctrl.update(rd_a, rd_b, rg, step=1)
    # Discrepancy triggers probing
    assert ctrl.mode in ("NOMINAL", "ACTIVE_PROBING")

    # Feed 15 anchor steps to calibrate
    anc = AnchorReading(
        estimate=true_delta,
        sigma=0.02,
        valid=True,
        queried=True,
        cost_accrued=0.05,
    )
    for s in range(2, 17):
        ctrl.update(rd_a, rd_b, rg, anchor_reading=anc, step=s)

    assert ctrl.cal_a.is_calibrated is True
    # Calibrated bias estimate should be close to true bias
    assert np.allclose(ctrl.cal_a.bias_est, bias_a, atol=0.15)


def test_calibrated_3d_arrival_without_naive_veto():
    """
    Resolves the 3D Reality Gap:
    Sensor A has a bias of +0.8m.
    Naive 3D veto checked raw ||meas_a|| > radius and vetoed forever.
    Aegis3DAwareController calibrates out the bias and achieves verified STOP!
    """
    ctrl = Aegis3DAwareController(success_radius=0.25)
    # Robot is physically at target [0.08, 0.08, 0.04] (dist = 0.12m < 0.25m)
    true_pos = np.array([0.08, 0.08, 0.04])
    true_dist = float(np.linalg.norm(true_pos))
    bias_a = np.array([0.80, 0.0, 0.0])

    # Directly set calibration as if previously learned
    ctrl.cal_a.bias_est = bias_a.copy()
    ctrl.cal_a.is_calibrated = True
    ctrl.cal_a.sample_count = 20
    ctrl.mode = "CALIBRATED_APPROACH"

    rd_a = _make_reading_3d(true_pos + bias_a)
    # Raw norm is > 0.88m! Naive heuristic would reject
    assert np.linalg.norm(rd_a.estimate) > 0.80

    rd_b = _make_reading_3d(true_pos)
    rg = _make_range(true_dist)

    # 3 consecutive steps should verify arrival using CALIBRATED vector
    for step in range(1, 4):
        _, dec, nav, _ = ctrl.update(rd_a, rd_b, rg, step=step)

    assert dec == "STOP"
    assert ctrl.terminal_reason == "3D_CALIBRATED_VERIFIED_ARRIVAL"


def test_fail_closed_total_vector_dropout():
    ctrl = Aegis3DAwareController(success_radius=0.25)
    rd_none = _make_reading_3d(np.zeros(3), valid=False)
    rg = _make_range(1.0, valid=True)

    act, dec, _, _ = ctrl.update(rd_none, rd_none, rg, step=1)
    assert dec == "ABSTAIN"
    assert ctrl.terminal_reason == "TOTAL_3D_VECTOR_DROPOUT"
    assert np.allclose(act, np.zeros(3))


def test_fail_closed_persistent_range_dropout_under_stress():
    ctrl = Aegis3DAwareController(success_radius=0.25)
    ctrl.mode = "ACTIVE_PROBING"

    pos = np.array([1.0, 0.5, 0.2])
    rd = _make_reading_3d(pos)
    rg_dropped = _make_range(0.0, valid=False)

    for step in range(1, 12):
        act, dec, _, _ = ctrl.update(rd, rd, rg_dropped, step=step)
        if dec == "ABSTAIN":
            break

    assert dec == "ABSTAIN"
    assert ctrl.terminal_reason == "PERSISTENT_RANGE_DROPOUT_UNDER_STRESS"
    assert np.allclose(act, np.zeros(3))
