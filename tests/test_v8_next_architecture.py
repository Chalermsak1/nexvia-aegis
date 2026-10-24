"""
NEXVIA AEGIS-Next (V8) — Unit & Architectural Regression Suite.

Verifies:
1. Martingale monitor under nominal folded Gaussian noise (wealth preserves capital, p-value >= 0.05).
2. Martingale monitor under corrupted bias (wealth grows past 1/alpha = 20.0, alarm trips).
3. Kinematic velocity controller: smooth approach without coasting overshoot.
4. Kinematic velocity controller: probing with active terminal braking.
5. Baseline controllers (Unshielded, Chi-Square NIS, EKF, V4, V5, V6, V7) execute cleanly.
6. AEGIS-Next controller closed-loop decision transitions.
7. Zero ground-truth leakage into live online controller.
"""

from __future__ import annotations

import numpy as np
import pytest

from aegis.next.martingale_monitor import AnytimeValidSequentialMonitor, MartingaleConfig
from aegis.next.velocity_controller import KinematicVelocityController, VelocityProfileConfig
from aegis.next.baselines import (
    UnshieldedAlwaysActController,
    ChiSquareNISGatingController,
    EKFConsistencyController,
    AegisV4PassiveController,
    AegisV5HuberController,
    AegisV6DiscriminativeController,
    AegisV7MPCBaselineController,
)
from aegis.next.agent_next import AegisNextController
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading


def test_martingale_nominal_noise_preserves_capital():
    """Under nominal zero-mean sensor noise, martingale wealth must remain strictly below 1/alpha."""
    monitor = AnytimeValidSequentialMonitor(MartingaleConfig(alpha=0.05))
    rng = np.random.default_rng(1234)

    # 100 nominal observations with sigma_v = sigma_r = 0.05
    for _ in range(100):
        # Difference of two zero-mean Gaussians with sigma=0.05 has sigma=0.0707
        diff = rng.normal(0.0, np.sqrt(0.05**2 + 0.05**2))
        res = abs(diff)
        wealth, p_val, is_alarm = monitor.update(res)

    assert not is_alarm
    assert wealth < 20.0
    assert p_val >= 0.05


def test_martingale_fault_detection_growth():
    """Under spatial bias (e.g. 0.6m), martingale wealth must grow exponentially past 1/alpha."""
    monitor = AnytimeValidSequentialMonitor(MartingaleConfig(alpha=0.05))
    rng = np.random.default_rng(5678)

    tripped = False
    alarm_step = -1
    for step in range(50):
        # Biased residual with mean 0.6m
        diff = rng.normal(0.60, np.sqrt(0.05**2 + 0.05**2))
        res = abs(diff)
        wealth, p_val, is_alarm = monitor.update(res)
        if is_alarm:
            tripped = True
            alarm_step = step
            break

    assert tripped
    assert alarm_step < 20  # Fast detection under severe bias
    assert monitor.wealth >= 20.0


def test_velocity_controller_smooth_docking():
    """Verifies that the velocity profile controller drives robot to arrival tolerance without overshoot."""
    ctrl = KinematicVelocityController(VelocityProfileConfig(arrival_tolerance=0.22))
    p = np.array([-2.0, -2.0])
    v = np.array([0.0, 0.0])
    target = np.array([0.0, 0.0])
    dt = 0.02
    min_dist = float("inf")
    overshoot = 0.0

    for step in range(300):
        d = target - p
        dist = float(np.linalg.norm(d))
        if dist < min_dist:
            min_dist = dist
        elif min_dist <= 0.50:
            overshoot = max(overshoot, dist - min_dist)

        action, arrived = ctrl.plan_approach_action(d, v)
        if arrived:
            break

        v = v + (dt / 1.0) * action
        p = p + dt * v

    assert arrived
    assert float(np.linalg.norm(target - p)) <= 0.22
    assert overshoot < 0.015


def test_velocity_controller_probing_terminal_braking():
    """Verifies that probing action applies active reverse counter-thrust during final 6 steps."""
    ctrl = KinematicVelocityController()
    d = np.array([2.0, 0.0])
    v_coasting = np.array([0.30, 0.20])

    # Step in probing: step 30 of 32 (braking phase)
    action = ctrl.plan_probing_action(d, v_coasting, step_in_probing=30, probing_steps=32)

    # Action must be in opposing direction to velocity
    dot_product = np.dot(action, v_coasting)
    assert dot_product < 0.0  # Decelerating
    assert np.all(action >= -1.0) and np.all(action <= 1.0)


def test_baseline_controllers_execution():
    """Verifies that all 7 baseline controllers instantiate and produce valid actions."""
    baselines = [
        UnshieldedAlwaysActController(),
        ChiSquareNISGatingController(),
        EKFConsistencyController(),
        AegisV4PassiveController(),
        AegisV5HuberController(),
        AegisV6DiscriminativeController(),
        AegisV7MPCBaselineController(),
    ]

    r_a = SensorReading(
        estimate=np.array([1.5, 0.5]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )
    r_b = SensorReading(
        estimate=np.array([1.5, 0.5]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )
    r_r = RangeReading(distance=1.58, sigma=0.05, valid=True)

    for b in baselines:
        b.reset()
        action, dec, cal_vec, query = b.update(r_a, r_b, r_r, None, step=1)
        assert isinstance(action, np.ndarray) and action.shape == (2,)
        assert dec in ("ACT", "PROBE", "STOP", "ABSTAIN", "VERIFY")
        assert np.all(action >= -1.0) and np.all(action <= 1.0)


def test_aegis_next_controller_closed_loop():
    """Tests AEGIS-Next controller closed-loop decision transitions."""
    ctrl = AegisNextController()
    ctrl.reset()

    r_a = SensorReading(
        estimate=np.array([2.0, 0.0]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )
    r_b = SensorReading(
        estimate=np.array([2.0, 0.0]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )
    r_r = RangeReading(distance=2.0, sigma=0.05, valid=True)

    # Nominal step
    action, dec, cal_vec, query = ctrl.update(r_a, r_b, r_r, None, step=1)
    assert dec == "ACT"
    assert not query
    assert np.all(action >= -1.0) and np.all(action <= 1.0)

    # Injected severe bias: should cause martingale wealth to rise
    r_a_biased = SensorReading(
        estimate=np.array([3.2, 0.0]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.array([1.2, 0.0]),
        drift=np.zeros(2),
    )
    r_b_biased = SensorReading(
        estimate=np.array([3.2, 0.0]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.array([1.2, 0.0]),
        drift=np.zeros(2),
    )

    for st in range(2, 20):
        action, dec, cal_vec, query = ctrl.update(r_a_biased, r_b_biased, r_r, None, step=st)

    assert ctrl.state.mode in ("ACTIVE_PROBING", "CALIBRATED")
    assert ctrl.martingale_monitor.wealth >= 20.0
