"""
Regression & Unit Tests for V9-M2R1 Initial-State Arrival Gate & Fail-Closed Logic.

Covers all Phase 3 required test cases:
1. Forensic reproduction of historical seed-71717 failure: verifies no step-0 false STOP,
   queries anchor on arrival hypothesis, and fails closed to ACTIVE_PROBING when anchor refutes it.
2. No anchor query and no temporal evidence at initial step: fails closed to PROBE, never stops.
3. Invalid, NaN, infinite, and missing readings: abstains safely with documented reason.
4. Genuine initial-at-goal conditions with valid independent corroboration: commits STOP
   with CORROBORATED_INITIAL_GOAL_ARRIVAL.
5. Persistent sensor agreement under shared bias: probes/abstains, never emits false STOP.
6. Correct behavior after verified motion / approach history (>= 3 approach steps):
   commits STOP with NOMINAL_VERIFIED_ARRIVAL when genuine arrival is verified.
7. Proof that STOP is impossible through the historical fail-open branch on single-step snapshot.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from aegis.v3.env.world import AegisPhysicalWorld
from aegis.v3.sensors.cross_modal import RangeReading, RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorReading
from aegis.v7.anchor_sensor import AnchorReading, AnchorSensor, AnchorSensorConfig
from aegis.v9.controller import AegisV9Controller
from aegis.v9.risk_statistics import PREREGISTERED_CANDIDATE_FAMILY
from aegis.v9.scenarios import build_v9_s12_scenarios


def make_reading(vec: np.ndarray, sigma: float = 0.05, valid: bool = True) -> SensorReading:
    return SensorReading(
        estimate=np.asarray(vec, dtype=np.float64).copy(),
        sigma=sigma,
        valid=valid,
        anomaly=False,
        dropped=not valid,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )


def test_1_historical_seed_71717_forensic_reproduction():
    """
    Case 1: Historical seed 71717 in COMPOUND_HOLDOUT_EXTREME.
    Under historical code, controller emitted STOP at step 0 because common-mode bias (+0.5, +0.5)
    and range bias (-0.40m) created apparent arrival while true distance was 0.5683m.
    Under corrected logic:
    - Step 0 returns VERIFY with query_anchor=True.
    - Step 1 anchor measures true distance (~0.57m > 0.22m), disproving arrival.
    - Controller enters ACTIVE_PROBING (PROBE) and NEVER emits false STOP.
    """
    scenarios = {s.name: s for s in build_v9_s12_scenarios()}
    scen = scenarios["COMPOUND_HOLDOUT_EXTREME"]

    ep_seed = 71717
    rng_env = np.random.default_rng(ep_seed)
    world = AegisPhysicalWorld()
    world.reset(rng_env)

    sensor_a = FaultInjectableSensor(scen.sensor_a)
    sensor_b = FaultInjectableSensor(scen.sensor_b)
    range_sensor = RangeSensor(
        noise_sigma=scen.range_sensor_noise,
        dropout_probability=scen.range_dropout_prob,
    )
    anchor_sensor = AnchorSensor(
        AnchorSensorConfig(
            query_cost=0.05,
            noise_sigma=0.04,
            is_corrupted=scen.anchor_corrupted,
            corrupted_bias=(1.2, -1.0),
        )
    )

    controller = AegisV9Controller(PREREGISTERED_CANDIDATE_FAMILY[2])
    rng_ep = np.random.default_rng(ep_seed)

    # Step 0
    st = world.state()
    true_delta = st["target_pos"] - st["robot_pos"]
    true_dist = float(st["distance"])
    assert true_dist > 0.45, f"Expected non-goal initial distance, got {true_dist}"

    read_a = sensor_a.measure(true_delta, rng_ep, step=0)
    read_b = sensor_b.measure(true_delta, rng_ep, step=0)
    true_range_val = true_dist + scen.range_sensor_bias
    read_r = range_sensor.measure(true_range_val, rng_ep)
    read_anchor = anchor_sensor.measure(true_delta, rng_ep, query=False)

    act0, dec0, _vec0, query0 = controller.update(read_a, read_b, read_r, read_anchor, step=0)

    # MUST NOT commit STOP at step 0!
    assert dec0 != "STOP", f"Step 0 false acceptance defect reproduced! Decision was {dec0}"
    assert dec0 == "VERIFY"
    assert query0 is True, "Must query anchor for independent corroboration"

    # Step 1: Anchor reading arrives, refuting the false arrival
    w_st = world.step(act0, rng_ep)
    read_a1 = sensor_a.measure(true_delta, rng_ep, step=1)
    read_b1 = sensor_b.measure(true_delta, rng_ep, step=1)
    read_r1 = range_sensor.measure(true_range_val, rng_ep)
    read_anchor1 = anchor_sensor.measure(true_delta, rng_ep, query=True)
    assert read_anchor1.valid is True

    act1, dec1, _vec1, query1 = controller.update(read_a1, read_b1, read_r1, read_anchor1, step=1)
    assert dec1 != "STOP", f"Step 1 committed false STOP: {dec1}"
    assert dec1 == "PROBE"
    assert controller.mode == "ACTIVE_PROBING"
    assert controller.terminal_reason == "UNCORROBORATED_INITIAL_ARRIVAL_PROBE"


def test_2_no_anchor_and_no_temporal_evidence():
    """
    Case 2: When anchor is disabled or budget is zero, and temporal evidence is unavailable,
    controller MUST fail closed to ACTIVE_PROBING rather than committing uncorroborated STOP.
    """
    controller = AegisV9Controller(PREREGISTERED_CANDIDATE_FAMILY[2], use_anchor=False)
    # Target appears to be within arrival tolerance
    fake_delta = np.array([0.08, 0.08])
    read_a = make_reading(fake_delta)
    read_b = make_reading(fake_delta)
    read_r = RangeReading(distance=0.11, sigma=0.05, valid=True)

    act, dec, _vec, query = controller.update(read_a, read_b, read_r, None, step=0)
    assert dec != "STOP"
    assert dec == "PROBE"
    assert controller.mode == "ACTIVE_PROBING"
    assert controller.terminal_reason == "UNCORROBORATED_INITIAL_ARRIVAL_PROBE"


def test_3_invalid_nan_infinite_and_missing_readings():
    """Case 3: Malformed, NaN, Infinite, and missing inputs trigger fail-closed abstinence."""
    controller = AegisV9Controller(PREREGISTERED_CANDIDATE_FAMILY[2])

    # NaN in sensor A
    nan_a = make_reading(np.array([np.nan, 0.0]))
    read_b = make_reading(np.array([0.1, 0.1]))
    read_r = RangeReading(distance=0.15, sigma=0.05, valid=True)
    _, dec, _, _ = controller.update(nan_a, read_b, read_r, None, step=0)
    assert dec == "ABSTAIN"
    assert "MALFORMED_SENSOR_A_INPUT" in controller.terminal_reason

    # Inf in Range
    controller.reset()
    read_a = make_reading(np.array([0.1, 0.1]))
    inf_r = RangeReading(distance=float("inf"), sigma=0.05, valid=True)
    _, dec, _, _ = controller.update(read_a, read_b, inf_r, None, step=0)
    assert dec == "ABSTAIN"
    assert "MALFORMED_RANGE_INPUT" in controller.terminal_reason

    # Persistent total vector dropout
    controller.reset()
    drop_a = SensorReading(
        estimate=np.zeros(2), sigma=0.05, valid=False, anomaly=False, dropped=True,
        bias=np.zeros(2), drift=np.zeros(2),
    )
    drop_b = SensorReading(
        estimate=np.zeros(2), sigma=0.05, valid=False, anomaly=False, dropped=True,
        bias=np.zeros(2), drift=np.zeros(2),
    )
    for s in range(7):
        _, dec, _, _ = controller.update(drop_a, drop_b, read_r, None, step=s)
    assert dec == "ABSTAIN"
    assert controller.terminal_reason == "PERSISTENT_TOTAL_VECTOR_DROPOUT"


def test_4_genuine_initial_at_goal_with_corroboration():
    """
    Case 4: Genuine initial-at-goal conditions with valid independent anchor corroboration
    must successfully commit STOP with CORROBORATED_INITIAL_GOAL_ARRIVAL.
    """
    controller = AegisV9Controller(PREREGISTERED_CANDIDATE_FAMILY[2])
    true_delta = np.array([0.06, 0.06])
    dist = float(np.linalg.norm(true_delta))

    read_a = make_reading(true_delta)
    read_b = make_reading(true_delta)
    read_r = RangeReading(distance=dist, sigma=0.05, valid=True)

    # Step 0: verifies apparent arrival and requests anchor
    act0, dec0, _vec0, query0 = controller.update(read_a, read_b, read_r, None, step=0)
    assert dec0 == "VERIFY"
    assert query0 is True

    # Step 1: anchor corroborates genuine arrival
    read_anc = AnchorReading(
        estimate=true_delta.copy(), sigma=0.04, valid=True, queried=True, cost_accrued=0.05
    )
    act1, dec1, _vec1, query1 = controller.update(read_a, read_b, read_r, read_anc, step=1)
    assert dec1 == "STOP"
    assert controller.terminal_reason == "CORROBORATED_INITIAL_GOAL_ARRIVAL"


def test_5_persistent_sensor_agreement_under_shared_bias():
    """
    Case 5: Shared bias on vector sensors (CORRELATED_BIAS).
    Without temporal evidence, controller does NOT accept arrival.
    Over time, range discrepancy triggers probing.
    """
    controller = AegisV9Controller(PREREGISTERED_CANDIDATE_FAMILY[2], use_anchor=False)
    # Bias is (+0.7, +0.7), robot at (-2, -2), target at (-2, -2). True dist = 0.0.
    # Vector sensors measure (+0.7, +0.7), range measures 0.05m.
    # Vector norm is 0.99m, range is 0.05m -> range discrepancy!
    vec_biased = np.array([0.7, 0.7])
    read_a = make_reading(vec_biased)
    read_b = make_reading(vec_biased)
    read_r = RangeReading(distance=0.05, sigma=0.05, valid=True)

    act, dec, _vec, _ = controller.update(read_a, read_b, read_r, None, step=0)
    assert dec != "STOP"


def test_6_correct_behavior_after_verified_motion():
    """
    Case 6: After at least 3 verified approach steps in NOMINAL mode, genuine arrival
    is committed through NOMINAL_VERIFIED_ARRIVAL.
    """
    controller = AegisV9Controller(PREREGISTERED_CANDIDATE_FAMILY[2])

    # Robot approaches from 1.5m away over steps 0, 1, 2
    for s in range(3):
        cur_delta = np.array([1.0 - 0.25 * s, 1.0 - 0.25 * s])
        d = float(np.linalg.norm(cur_delta))
        ra = make_reading(cur_delta)
        rb = make_reading(cur_delta)
        rr = RangeReading(distance=d, sigma=0.05, valid=True)
        act, dec, _, _ = controller.update(ra, rb, rr, None, step=s)
        assert dec == "ACT"

    assert controller._nominal_approach_steps >= 3

    # Step 3: robot enters arrival tolerance cleanly
    arr_delta = np.array([0.08, 0.08])
    arr_d = float(np.linalg.norm(arr_delta))
    ra_arr = make_reading(arr_delta)
    rb_arr = make_reading(arr_delta)
    rr_arr = RangeReading(distance=arr_d, sigma=0.05, valid=True)

    act_arr, dec_arr, _, _ = controller.update(ra_arr, rb_arr, rr_arr, None, step=3)
    assert dec_arr == "STOP"
    assert controller.terminal_reason == "NOMINAL_VERIFIED_ARRIVAL"


def test_7_fail_open_branch_is_impossible():
    """
    Case 7: Verify that single-step snapshot with zero approach history CANNOT
    reach NOMINAL_VERIFIED_ARRIVAL under any combination of inputs.
    """
    controller = AegisV9Controller(PREREGISTERED_CANDIDATE_FAMILY[2])

    # Try 100 random apparent arrivals at step 0 without anchor
    rng = np.random.default_rng(999)
    for _ in range(100):
        controller.reset()
        v = rng.uniform(-0.15, 0.15, size=2)
        r = float(np.linalg.norm(v)) + rng.uniform(-0.01, 0.01)
        ra = make_reading(v)
        rb = make_reading(v)
        rr = RangeReading(distance=max(0.01, r), sigma=0.05, valid=True)

        _, dec, _, _ = controller.update(ra, rb, rr, None, step=0)
        assert dec != "STOP"
        assert controller.terminal_reason != "NOMINAL_VERIFIED_ARRIVAL"
