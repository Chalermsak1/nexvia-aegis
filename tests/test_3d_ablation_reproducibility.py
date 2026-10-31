"""Synthetic tests for 3D ablation and matched sensor randomness."""

from types import SimpleNamespace
import numpy as np
import pytest

from experiments import benchmark_physical_3d_cbf as benchmark


class FixedWorld:
    config = SimpleNamespace(success_radius=0.25)

    def reset(self, rng):
        return self.state()

    def state(self):
        return {
            "robot_pos": np.zeros(3), "robot_velocity": np.zeros(3),
            "target_pos": np.array([1.0, 0.0, 0.0]), "distance": 1.0,
            "safety_violation": False,
        }

    def step(self, desired_control, force_braking=False):
        return self.state()


def test_no_active_probe_arm_abstains_before_anchor_query(monkeypatch):
    class ProbeController:
        def __init__(self, **kwargs):
            self.anchors = []

        def reset(self):
            pass

        def update(self, a, b, r, anchor_reading=None, step=0):
            self.anchors.append(anchor_reading)
            return np.zeros(3), "PROBE", np.zeros(3), True

    ctrl = ProbeController()
    monkeypatch.setattr(benchmark, "Aegis3DAwareController", lambda **kwargs: ctrl)
    result = benchmark.run_3d_episode(FixedWorld(), "AEGIS_3D_NO_ACTIVE_PROBE", 1234567, np.zeros(3), max_steps=3)
    assert result["abstained"] == 1
    assert result["steps"] == 1
    assert ctrl.anchors == [None]


@pytest.mark.parametrize("controller", ["UNSHIELDED", "CBF_ONLY"])
def test_baseline_stop_is_scored_without_an_extra_physics_step(monkeypatch, controller):
    class ZeroNoise:
        def normal(self, loc, scale, size=None):
            return np.zeros(size) if size is not None else 0.0

    class AtTargetWorld(FixedWorld):
        def state(self):
            state = super().state()
            state["target_pos"] = np.array([0.1, 0.0, 0.0])
            state["distance"] = 0.1
            return state

        def step(self, *args, **kwargs):
            raise AssertionError("A STOP decision must not advance physics")

    monkeypatch.setattr(benchmark.np.random, "default_rng", lambda *args: ZeroNoise())
    result = benchmark.run_3d_episode(AtTargetWorld(), controller, 1234567, np.zeros(3), max_steps=3)
    assert result["true_success"] == 1
    assert result["final_distance"] == 0.1


def test_anchor_query_does_not_shift_vector_sensor_random_stream(monkeypatch):
    class NavigationController:
        def __init__(self, request_anchor):
            self.request_anchor = request_anchor
            self.observations = []
            self.received_anchor = False

        def reset(self):
            pass

        def update(self, a, b, r, anchor_reading=None, step=0):
            self.observations.append(a.estimate.copy())
            self.received_anchor |= anchor_reading is not None
            return np.zeros(3), "NAVIGATE", np.zeros(3), self.request_anchor and step == 0

    observations = []
    for request_anchor in (False, True):
        ctrl = NavigationController(request_anchor)
        monkeypatch.setattr(benchmark, "Aegis3DAwareController", lambda **kwargs: ctrl)
        benchmark.run_3d_episode(FixedWorld(), "AEGIS_3D_AWARE_CBF", 1234567, np.zeros(3), max_steps=4)
        assert ctrl.received_anchor == request_anchor
        observations.append(ctrl.observations)
    assert np.allclose(observations[0], observations[1])


@pytest.mark.parametrize("latency,expected", [(0, True), (2, False)])
def test_3d_controller_receives_only_fresh_range_as_valid(monkeypatch, latency, expected):
    class RangeObserver:
        def __init__(self):
            self.observed = []

        def reset(self):
            pass

        def update(self, a, b, r, anchor_reading=None, step=0):
            self.observed.append((r.valid, r.dropped))
            return np.zeros(3), "NAVIGATE", np.zeros(3), False

    ctrl = RangeObserver()
    monkeypatch.setattr(benchmark, "Aegis3DAwareController", lambda **kwargs: ctrl)
    benchmark.run_3d_episode(FixedWorld(), "AEGIS_3D_AWARE_CBF", 1234567,
                             np.zeros(3), max_steps=5, range_latency_steps=latency)
    assert all(valid is expected and dropped is (not expected) for valid, dropped in ctrl.observed)
