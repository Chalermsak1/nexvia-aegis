from __future__ import annotations

import numpy as np
import pytest

from aegis.v3.agent import AegisAgentV3
from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig


def test_v3_sensors_and_verification():
    rng = np.random.default_rng(42)
    s1 = FaultInjectableSensor(SensorConfig(name="s1", noise_sigma=0.05))
    s2 = FaultInjectableSensor(SensorConfig(name="s2", noise_sigma=0.05))
    range_sensor = RangeSensor(noise_sigma=0.05)

    delta = np.array([2.0, 1.0])
    r1 = s1.measure(delta, rng)
    r2 = s2.measure(delta, rng)
    dist = float(np.linalg.norm(delta))
    rr = range_sensor.measure(dist, rng)

    controller = VerificationController()
    ver = controller.verify([r1, r2], rr)
    assert hasattr(ver, "status")
    assert hasattr(ver, "confidence")
    assert hasattr(ver, "estimate")
    assert ver.estimate.shape == (2,)


def test_v3_agent_episode():
    agent = AegisAgentV3()
    result = agent.run_episode(seed=42)
    assert isinstance(result, dict)
    assert "success" in result
    assert "steps" in result
    assert "decisions" in result
    assert result["steps"] > 0
