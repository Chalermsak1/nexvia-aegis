"""Characterization tests: copied forward observation without live-state changes."""
import mujoco
import numpy as np
import pytest
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from scripts.research.diagnose_state_phase import compare_position_phase, measure_case


@pytest.mark.parametrize('dt', [.01, .02])
@pytest.mark.parametrize('speed', [0., .1, .5])
def test_integrated_position_and_reported_position_have_different_phases(dt, speed):
    case = measure_case(dt, speed)
    for i, row in enumerate(case['steps']):
        assert row['position_phase_offset_m'] == pytest.approx(dt * speed, abs=1e-12)
        assert row['copied_forward_position'] == pytest.approx(row['integrated_translation_qpos'])
        assert row['simulation_time_seconds'] == pytest.approx((i + 1) * dt)
        if speed:
            assert row['reported_distance'] != pytest.approx(row['copied_forward_distance'], abs=1e-10)
        else:
            assert row['reported_distance'] == pytest.approx(row['copied_forward_distance'])


def test_copy_observation_does_not_change_live_solver_or_integration_state():
    env = AegisMuJoCo3DEnvironment()
    env.reset(np.random.default_rng(9201001))
    env.data.qvel[:3] = [.1, 0., 0.]
    mujoco.mj_forward(env.model, env.data)
    reported = env.step(np.zeros(3))
    names = ['qpos', 'qvel', 'qacc', 'qacc_warmstart', 'xpos', 'xfrc_applied']
    before = {name: getattr(env.data, name).copy() for name in names}
    prior_time, prior_count = env.data.time, env.step_count
    row = compare_position_phase(env, reported)
    assert row['position_phase_offset_m'] == pytest.approx(.002)
    assert env.data.time == prior_time and env.step_count == prior_count
    for name, value in before.items():
        np.testing.assert_array_equal(getattr(env.data, name), value)
    assert reported['robot_pos'].tolist() == before['xpos'][env.robot_body_id].tolist()
