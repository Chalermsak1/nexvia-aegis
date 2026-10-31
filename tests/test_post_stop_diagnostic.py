"""Verify separate post-STOP observation without altering arrival scoring."""
from types import SimpleNamespace
import numpy as np
import pytest
from experiments import benchmark_physical_3d_cbf as benchmark


class MovingWorld:
    config = SimpleNamespace(success_radius=0.25)

    def reset(self, rng):
        self.x = 0.2
        return self.state()

    def state(self):
        return {"robot_pos": np.array([self.x, 0., 0.]), "robot_velocity": np.array([1., 0., 0.]),
                "target_pos": np.zeros(3), "distance": self.x, "safety_violation": self.x > 0.3,
                "cbf_constraint_residual": 0.0}

    def step(self, control, force_braking=False):
        assert force_braking
        self.x += 0.06
        return self.state()


def test_post_stop_records_exiting_target_but_preserves_score(monkeypatch):
    class StopController:
        def __init__(self, **kwargs): pass
        def reset(self): pass
        def update(self, *args, **kwargs):
            return np.zeros(3), "STOP", np.zeros(3), False

    monkeypatch.setattr(benchmark, "Aegis3DAwareController", StopController)
    row = benchmark.run_3d_episode(MovingWorld(), "AEGIS_3D_STRICT_RANGE", 1234,
                                    np.zeros(3), post_stop_steps=3)
    assert row["true_success"] == 1 and row["final_distance"] == 0.2
    assert row["collision_occurred"] == 0  # post-STOP is reported separately
    assert row["post_stop"]["decision_speed"] == 1
    assert row["post_stop"]["steps"][0]["distance"] > 0.25
    assert row["post_stop"]["steps"][1]["collision"]


@pytest.mark.parametrize("count", [-1, 1.5, True])
def test_post_stop_invalid_horizon_rejected(count):
    with pytest.raises(ValueError):
        benchmark.run_3d_episode(MovingWorld(), "AEGIS_3D_STRICT_RANGE", 1234,
                                 np.zeros(3), post_stop_steps=count)


def test_post_stop_unsupported_arm_rejected():
    with pytest.raises(ValueError):
        benchmark.run_3d_episode(MovingWorld(), "CBF_ONLY", 1234, np.zeros(3), post_stop_steps=1)
