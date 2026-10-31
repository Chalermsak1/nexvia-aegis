"""Synthetic tests for the non-integrated estimated-state control proposal."""
import math
import numpy as np
import pytest

from scripts.research.no_oracle_control import EstimatedState, EstimateOnlyControl, demonstration
from aegis.env.mujoco_3d_cbf import ControlBarrierFilter3D


class Recorder:
    def __init__(self, returned=None):
        self.calls = []
        self.returned = returned

    def compute_safe_control(self, **kwargs):
        self.calls.append(kwargs)
        return (kwargs["desired_u"] if self.returned is None else self.returned), False


def estimate(velocity, sequence=0, timestamp=0., position=(0., 0., 1.)):
    return EstimatedState(position, velocity, sequence, timestamp)


def test_braking_uses_estimated_velocity_everywhere_and_disables_oracle_override():
    recorder = Recorder()
    ctrl = EstimateOnlyControl()
    result = ctrl.command(estimate([.25, 0, 0]), now_seconds=0., mode="BRAKE", projector=recorder)
    assert result["status"] == "COMMAND_PROPOSED"
    assert np.allclose(result["projected_force"], [-.5, 0, 0])
    assert np.allclose(recorder.calls[0]["vel"], [.25, 0, 0])
    assert np.allclose(recorder.calls[0]["pos"], [0, 0, 1])
    assert recorder.calls[0]["force_braking"] is False
    assert result["projection_safety"] == "UNVERIFIED"


def test_navigation_damping_uses_estimate():
    r = Recorder()
    result = EstimateOnlyControl().command(estimate([.4, -.2, 0]), now_seconds=0,
                                           mode="NAVIGATE", action=[1, 0, 0], projector=r)
    assert np.allclose(result["desired_force"], [.8, .1, 0])


@pytest.mark.parametrize("bad", [None, [0, 0], [math.nan, 0, 0], ['bad', 0, 0]])
def test_missing_or_invalid_velocity_does_not_invoke_projector(bad):
    r = Recorder()
    result = EstimateOnlyControl().command(estimate(bad), now_seconds=0, mode="BRAKE", projector=r)
    assert result["status"] == "NO_COMMAND" and not r.calls


def test_stale_replay_and_rollback_do_not_issue_force():
    ctrl, r = EstimateOnlyControl(), Recorder()
    assert ctrl.command(estimate([1, 0, 0]), now_seconds=0, mode="BRAKE", projector=r)["status"] == "COMMAND_PROPOSED"
    assert ctrl.command(estimate([1, 0, 0]), now_seconds=.02, mode="BRAKE", projector=r)["status"] == "NO_COMMAND"
    assert ctrl.command(estimate([1, 0, 0], 1, .03), now_seconds=.03, mode="BRAKE", projector=r)["status"] == "COMMAND_PROPOSED"
    assert ctrl.command(estimate([1, 0, 0], 2, .01), now_seconds=.01, mode="BRAKE", projector=r)["reason"] == "NON_MONOTONIC_CLOCK"
    assert len(r.calls) == 2


def test_projector_error_and_invalid_output_are_no_command():
    class Failed:
        def compute_safe_control(self, **kwargs): raise RuntimeError("private detail")
    assert EstimateOnlyControl().command(estimate([1, 0, 0]), now_seconds=0, mode="BRAKE", projector=Failed())["reason"] == "PROJECTOR_ERROR"
    assert EstimateOnlyControl().command(estimate([1, 0, 0]), now_seconds=0, mode="BRAKE", projector=Recorder([float('nan'), 0, 0]))["reason"] == "INVALID_PROJECTED_FORCE"
    assert EstimateOnlyControl().command(estimate([1, 0, 0]), now_seconds=0, mode="BRAKE", projector=Recorder([3, 0, 0]))["reason"] == "INVALID_PROJECTED_FORCE"


def test_reversed_measurement_can_accelerate_robot_in_synthetic_model():
    rows = {r["fixture"]: r for r in demonstration()}
    assert rows["accurate"]["instantaneous_force_dot_true_velocity"] < 0
    assert rows["underreported"]["instantaneous_force_dot_true_velocity"] < 0
    assert rows["reversed"]["instantaneous_force_dot_true_velocity"] > 0
    assert rows["missing"]["result"]["status"] == "NO_COMMAND"


def test_real_3d_cbf_component_accepts_estimated_state_without_oracle_override():
    cbf = ControlBarrierFilter3D()
    result = EstimateOnlyControl().command(estimate([.2, 0, 0]), now_seconds=0, mode="BRAKE", projector=cbf)
    assert result["status"] == "COMMAND_PROPOSED"
    assert np.isfinite(result["projected_force"]).all()
