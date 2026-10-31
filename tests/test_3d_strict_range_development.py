"""Synthetic checks for the exploratory strict-range variant."""
import math
import numpy as np
import pytest

from aegis.v9.controller_3d import Aegis3DAwareController
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from experiments.benchmark_physical_3d_cbf import run_3d_episode


def decisions(margin, distance):
    ctrl = Aegis3DAwareController(arrival_margin_m=margin)
    vector = np.array([0.1, 0.0, 0.0])
    return [ctrl.update(vector, vector, distance, step=i)[1] for i in range(3)]


def test_strict_variant_rejects_borderline_bound_default_accepts():
    # Third-sample bound is about 0.263 m: inside 0.28, outside 0.25.
    assert decisions(0.03, 0.215)[-1] == "STOP"
    assert decisions(0.0, 0.215)[-1] == "VERIFY"


def test_strict_variant_can_accept_when_bound_is_inside_radius():
    assert decisions(0.0, 0.15)[-1] == "STOP"


@pytest.mark.parametrize("margin", [-0.01, math.nan, math.inf])
def test_invalid_margin_is_rejected(margin):
    with pytest.raises(ValueError):
        Aegis3DAwareController(arrival_margin_m=margin)


def test_tracing_does_not_change_episode_and_records_decision_state():
    env = AegisMuJoCo3DEnvironment()
    bias = np.array([0.8, 0.8, -0.3])
    without_trace = run_3d_episode(env, "AEGIS_3D_AWARE_CBF", 2234001, bias, 100)
    trace = []
    with_trace = run_3d_episode(env, "AEGIS_3D_AWARE_CBF", 2234001, bias, 100, trace=trace)
    assert with_trace == without_trace
    assert len(trace) == with_trace["steps"]
    assert trace[-1]["decision"] == "STOP"
    assert trace[-1]["true_distance"] > env.config.success_radius
    assert len(trace[-1]["arrival_range_samples"]) >= 3


def test_delayed_range_does_not_produce_arrival_stop():
    from types import SimpleNamespace

    class AtTarget:
        config = SimpleNamespace(success_radius=0.25)

        def reset(self, rng):
            return self.state()

        def state(self):
            return {"robot_pos": np.zeros(3), "robot_velocity": np.zeros(3),
                    "target_pos": np.array([0.1, 0.0, 0.0]), "distance": 0.1,
                    "safety_violation": False}

        def step(self, control, force_braking=False):
            result = self.state()
            result["cbf_constraint_residual"] = 0.0
            return result

    trace = []
    result = run_3d_episode(AtTarget(), "AEGIS_3D_STRICT_RANGE", 2236001,
                            np.zeros(3), 20, range_latency_steps=2, trace=trace)
    assert result["true_success"] == result["false_arrival"] == 0
    assert all(not step["range_fresh"] and step["decision"] != "STOP" for step in trace)
