"""Focused development checks for the MuJoCo braking micro-study."""
import numpy as np
import pytest
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from scripts.research.study_estimated_braking import apply_filtered_force, run


def test_plant_step_does_not_recompute_a_truth_state_projection(monkeypatch):
    env = AegisMuJoCo3DEnvironment()
    env.reset(np.random.default_rng(145))
    monkeypatch.setattr(env.cbf, "compute_safe_control", lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected oracle projection")))
    state = apply_filtered_force(env, [0., 0., 0.])
    assert env.step_count == 1 and np.isfinite(state["robot_pos"]).all()


@pytest.mark.parametrize("force", [[3, 0, 0], [0, 0], [float('nan'), 0, 0]])
def test_plant_step_rejects_bad_projected_force(force):
    env = AegisMuJoCo3DEnvironment()
    env.reset(np.random.default_rng(145))
    with pytest.raises(ValueError): apply_filtered_force(env, force)
    assert env.step_count == 0


def test_reversed_velocity_and_missing_observation_remain_visible():
    reversed_case = {"name": "reversed", "velocity_scale": -1., "missing_velocity": False}
    result = run(2248000, "ESTIMATED_STATE_CBF_BRAKE", reversed_case, 3)
    assert result["events"][0]["force_dot_true_velocity_before"] > 0
    missing = run(2248000, "ESTIMATED_STATE_CBF_BRAKE", {"name": "missing", "velocity_scale": 1., "missing_velocity": True}, 3)
    assert missing["no_command"] and missing["steps_applied"] == 0
