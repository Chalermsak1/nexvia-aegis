from __future__ import annotations

import numpy as np
import pytest

from aegis.decision import AegisDecisionPolicy
from aegis.env.mujoco_v2 import AegisMuJoCoV2
from aegis.sensing import NoisyPositionSensor, SensorArbitrator


def test_sensor_and_arbitrator():
    rng = np.random.default_rng(42)
    s1 = NoisyPositionSensor(noise_sigma=0.05)
    s2 = NoisyPositionSensor(noise_sigma=0.08)

    true_delta = np.array([1.0, 2.0])
    r1 = s1.measure(true_delta, rng)
    r2 = s2.measure(true_delta, rng)

    assert r1.estimate.shape == (2,)
    assert r2.estimate.shape == (2,)

    arbitrator = SensorArbitrator(disagreement_threshold=0.35)
    res = arbitrator.compare(r1, r2)
    assert "estimate" in res
    assert "disagreement" in res
    assert "cross_mismatch" in res
    assert isinstance(res["cross_mismatch"], (bool, np.bool_))


def test_decision_policy():
    policy = AegisDecisionPolicy()

    # Low confidence -> ABSTAIN
    d = policy.decide(
        estimated_distance=1.0,
        confidence=0.2,
        sensor_disagreement=0.1,
        cross_mismatch=False,
    )
    assert d.action == "ABSTAIN"

    # Cross mismatch -> ABSTAIN
    d = policy.decide(
        estimated_distance=0.1,
        confidence=0.9,
        sensor_disagreement=0.5,
        cross_mismatch=True,
    )
    assert d.action == "ABSTAIN"

    # High confidence -> ACT
    d = policy.decide(
        estimated_distance=1.0,
        confidence=0.85,
        sensor_disagreement=0.1,
        cross_mismatch=False,
    )
    assert d.action == "ACT"


def test_mujoco_v2_env():
    env = AegisMuJoCoV2()
    obs, info = env.reset(seed=42)
    assert obs.shape == (7,)
    assert "sensing" in info
    assert "target_pos" in info
    assert "robot_pos" in info

    action = np.array([0.5, 0.5], dtype=np.float32)
    obs, reward, terminated, truncated, info = env.step(action)
    assert obs.shape == (7,)
    assert not terminated
    env.close()
