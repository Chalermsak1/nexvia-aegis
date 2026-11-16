"""Opt-in development state synchronization; no policy or stopping acceptance."""
import mujoco
import numpy as np
import pytest
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment, PhysicalWorld3DConfig
from aegis.env.mujoco_3d_synchronized import SynchronizedAegisMuJoCo3DEnvironment


def prepared(cls, dt=.02):
    env = cls(PhysicalWorld3DConfig(timestep=dt))
    env.reset(np.random.default_rng(9201001))
    env.target_pos = np.array([2., 2., .5])
    return env


@pytest.mark.parametrize('dt', [.01, .02])
@pytest.mark.parametrize('speed', [0., .1, .5])
def test_synchronized_position_velocity_and_time_after_exactly_one_integration(dt, speed):
    env = prepared(SynchronizedAegisMuJoCo3DEnvironment, dt)
    env.data.qvel[:3] = [speed, 0., 0.]
    for i in range(3):
        state = env.step(np.zeros(3))
        np.testing.assert_allclose(state['robot_pos'], env.data.qpos[:3], atol=1e-12, rtol=0)
        np.testing.assert_array_equal(state['robot_velocity'], env.data.qvel[:3])
        assert state['distance'] == pytest.approx(np.linalg.norm(env.target_pos - env.data.qpos[:3]))
        assert state['control_interval_start_seconds'] == pytest.approx(i * dt)
        assert state['simulation_time_seconds'] == pytest.approx((i + 1) * dt)
        assert state['runtime_timestep_seconds'] == dt
        assert state['step'] == env.step_count == i + 1
        assert state['environment_id'] == env.ENVIRONMENT_ID
        assert state['state_phase'] == 'POST_INTEGRATION_FORWARD_REFRESH'
        assert state['control_diagnostics_phase'] == 'PRE_INTEGRATION_CBF'


def test_cbf_receives_refreshed_position_after_external_state_edit(monkeypatch):
    env = prepared(SynchronizedAegisMuJoCo3DEnvironment)
    env.data.qpos[:3] = [-1.8, -2., .6]
    env.data.qvel[:3] = [.1, 0., 0.]
    seen = []
    original = env.cbf.compute_safe_control
    def capture(**kwargs):
        seen.append((kwargs['pos'].copy(), kwargs['vel'].copy()))
        return original(**kwargs)
    monkeypatch.setattr(env.cbf, 'compute_safe_control', capture)
    state = env.step(np.zeros(3))
    assert len(seen) == 1
    np.testing.assert_array_equal(seen[0][0], [-1.8, -2., .6])
    np.testing.assert_array_equal(seen[0][1], [.1, 0., 0.])
    assert not np.array_equal(state['robot_pos'], seen[0][0])


def test_floor_contact_is_refreshed_at_integrated_position():
    env = prepared(SynchronizedAegisMuJoCo3DEnvironment)
    env.data.qpos[:3] = [-2., -2., .201]
    env.data.qvel[:3] = [0., 0., -1.]
    state = env.step(np.zeros(3))
    assert env.data.qpos[2] < env.config.robot_radius
    assert state['contact_floor'] is True and state['safety_violation'] is True
    np.testing.assert_allclose(state['robot_pos'], env.data.qpos[:3], atol=1e-12, rtol=0)


def test_acceleration_braking_matches_explicit_refreshed_reference_pipeline():
    fixed = prepared(SynchronizedAegisMuJoCo3DEnvironment)
    reference = prepared(AegisMuJoCo3DEnvironment)
    for i in range(10):
        command = np.array([.5, .2, .1]) if i < 5 else np.zeros(3)
        state = fixed.step(command, force_braking=i >= 5)
        mujoco.mj_forward(reference.model, reference.data)
        transition = reference.step(command, force_braking=i >= 5)
        mujoco.mj_forward(reference.model, reference.data)
        observation = reference.get_state()
        np.testing.assert_array_equal(fixed.data.qpos, reference.data.qpos)
        np.testing.assert_array_equal(fixed.data.qvel, reference.data.qvel)
        np.testing.assert_array_equal(state['robot_pos'], observation['robot_pos'])
        np.testing.assert_array_equal(state['safe_action'], transition['safe_action'])
        assert state['cbf_constraint_residual'] == transition['cbf_constraint_residual']
        assert state['simulation_time_seconds'] == pytest.approx((i + 1) * .02)


def test_read_queries_do_not_integrate_and_return_independent_arrays():
    env = prepared(SynchronizedAegisMuJoCo3DEnvironment)
    env.data.qvel[:3] = [.1, 0., 0.]
    state = env.step(np.zeros(3))
    qpos, qvel, time, count = env.data.qpos.copy(), env.data.qvel.copy(), env.data.time, env.step_count
    for _ in range(3):
        read = env.get_state()
        np.testing.assert_array_equal(read['robot_pos'], state['robot_pos'])
        read['robot_pos'][:] = 999
    np.testing.assert_array_equal(env.data.qpos, qpos)
    np.testing.assert_array_equal(env.data.qvel, qvel)
    assert env.data.time == time and env.step_count == count


def test_legacy_default_keeps_historical_timing():
    env = prepared(AegisMuJoCo3DEnvironment)
    env.data.qvel[:3] = [.1, 0., 0.]
    mujoco.mj_forward(env.model, env.data)
    state = env.step(np.zeros(3))
    assert env.data.qpos[0] - state['robot_pos'][0] == pytest.approx(.002)
    assert 'environment_id' not in state


def test_obstacle_contact_is_refreshed_after_crossing_into_sphere():
    env = prepared(SynchronizedAegisMuJoCo3DEnvironment)
    env.data.qpos[:3] = [-.70, 0., .5]
    env.data.qvel[:3] = [4., 0., 0.]
    state = env.step(np.zeros(3))
    assert np.linalg.norm(state['robot_pos'] - env.obstacles[0].center) < .65
    assert state['contact_obstacle'] is True
    assert state['min_obstacle_distance'] < 0 and state['safety_violation'] is True


def test_horizontal_boundary_crossing_is_measured_after_integration():
    env = prepared(SynchronizedAegisMuJoCo3DEnvironment)
    env.data.qpos[:3] = [2.79, -2., .6]
    env.data.qvel[:3] = [2., 0., 0.]
    state = env.step(np.zeros(3))
    assert state['robot_pos'][0] > 2.8
    assert state['boundary_clearance'] < 0
    assert state['safety_violation'] is True
