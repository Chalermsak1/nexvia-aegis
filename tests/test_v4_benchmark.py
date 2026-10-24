from __future__ import annotations

import numpy as np
import pytest

from aegis.v3.env.world import WorldConfig
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from experiments.research_benchmark_v4 import (
    AegisFullPolicy,
    AegisNoAbstainPolicy,
    AegisNoCrossModalPolicy,
    AlwaysActPolicy,
    FusionOnlyPolicy,
    get_scenarios,
    run_episode,
)


def test_v4_scenarios_count():
    scenarios = get_scenarios()
    assert len(scenarios) == 8
    names = [s.name for s in scenarios]
    assert "NOMINAL" in names
    assert "CORRELATED_BIAS" in names
    assert "COMPOUND_HOLDOUT" in names


def test_v4_policy_interfaces():
    reading_a = SensorReading(
        estimate=np.array([1.0, 1.0]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )
    reading_b = SensorReading(
        estimate=np.array([1.0, 1.0]),
        sigma=0.05,
        valid=True,
        anomaly=False,
        dropped=False,
        bias=np.zeros(2),
        drift=np.zeros(2),
    )
    range_reading = RangeReading(
        distance=np.sqrt(2.0),
        sigma=0.05,
        valid=True,
    )

    policies = [
        AlwaysActPolicy(),
        FusionOnlyPolicy(),
        AegisNoCrossModalPolicy(),
        AegisNoAbstainPolicy(),
        AegisFullPolicy(),
    ]

    for p in policies:
        action, dec_type = p.decide(reading_a, reading_b, range_reading, step=0)
        assert isinstance(action, np.ndarray)
        assert action.shape == (2,)
        assert isinstance(dec_type, str)


def test_v4_matched_seed_determinism():
    world_config = WorldConfig(max_steps=50, success_radius=0.25)
    scenario = get_scenarios()[0]
    policy = AlwaysActPolicy()

    r1 = run_episode(world_config, scenario, policy, seed=12345, episode_idx=0)
    r2 = run_episode(world_config, scenario, policy, seed=12345, episode_idx=0)

    assert r1.final_true_distance == pytest.approx(r2.final_true_distance)
    assert r1.steps == r2.steps
    assert r1.true_success == r2.true_success


def test_v4_correlated_bias_behavior():
    world_config = WorldConfig(max_steps=200, success_radius=0.25)
    scenarios = {s.name: s for s in get_scenarios()}
    corr_sc = scenarios["CORRELATED_BIAS"]

    # Under correlated bias, Aegis Full should abstain and avoid false success
    aegis_full = AegisFullPolicy()
    r_full = run_episode(
        world_config, corr_sc, aegis_full, seed=999, episode_idx=0
    )
    assert r_full.abstained is True
    assert r_full.false_success is False

    # Under correlated bias, Always Act declares stop at phantom target
    always_act = AlwaysActPolicy()
    r_act = run_episode(
        world_config, corr_sc, always_act, seed=999, episode_idx=0
    )
    assert r_act.declared_success is True
    assert r_act.false_success is True
