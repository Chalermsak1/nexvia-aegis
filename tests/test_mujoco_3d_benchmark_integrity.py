"""Regression checks for measured 3D development-benchmark outcomes."""

import json
import mujoco
import numpy as np
import pytest
from types import SimpleNamespace
from scipy.optimize import minimize

from aegis.env import mujoco_3d_cbf
from experiments import benchmark_physical_3d_cbf
from experiments.benchmark_physical_3d_cbf import run_3d_episode


def test_step_reports_post_step_obstacle_collision(monkeypatch):
    env = mujoco_3d_cbf.AegisMuJoCo3DEnvironment()
    env.reset(np.random.default_rng(12))
    assert not env.get_state()["safety_violation"]

    def move_into_obstacle(model, data):
        data.qpos[:3] = env.obstacles[0].center
        mujoco.mj_forward(model, data)

    monkeypatch.setattr(mujoco_3d_cbf.mujoco, "mj_step", move_into_obstacle)
    after = env.step(np.zeros(3))

    assert after["safety_violation"]
    assert after["min_obstacle_distance"] < 0
    assert after["contact_obstacle"]
    assert np.allclose(after["robot_pos"], env.obstacles[0].center)


def test_cbf_exposes_infeasible_actuator_limited_state():
    cbf = mujoco_3d_cbf.ControlBarrierFilter3D()
    action, active = cbf.compute_safe_control(
        pos=np.array([2.6, 0.0, 1.0]),
        vel=np.array([2.0, 0.0, 0.0]),
        desired_u=np.array([2.0, 0.0, 0.0]),
        obstacles=[],
    )
    assert active
    assert np.all(np.abs(action) <= cbf.force_limit)
    assert cbf.last_constraint_residual is not None
    assert cbf.last_constraint_residual > 0.0
    assert cbf.last_qp_feasible is False
    assert cbf.last_projection_method == "INFEASIBLE_WITHIN_ACTUATOR_BOX"

    cbf.compute_safe_control(
        pos=np.array([0.0, 0.0, 1.0]),
        vel=np.zeros(3),
        desired_u=np.zeros(3),
        obstacles=[], force_braking=True,
    )
    assert cbf.last_constraint_residual is not None
    assert cbf.last_constraint_residual <= 1e-8
    assert cbf.last_qp_feasible is True


def test_exact_3d_projection_respects_intersecting_planes_and_box():
    cbf = mujoco_3d_cbf.ControlBarrierFilter3D(force_limit=2.0)
    solution = cbf._exact_feasible_projection(
        np.array([1.0, 1.0, 0.0]),
        [(np.array([1.0, 1.0, 0.0]), 0.0),
         (np.array([1.0, 0.0, 0.0]), 0.5)],
    )
    assert solution is not None
    assert np.allclose(solution, [0.0, 0.0, 0.0])
    assert cbf._exact_feasible_projection(
        np.zeros(3), [(np.array([1.0, 0.0, 0.0]), -3.0)]
    ) is None


def test_exact_projection_matches_independent_scipy_solver_on_feasible_fixtures():
    rng = np.random.default_rng(20261029)
    cbf = mujoco_3d_cbf.ControlBarrierFilter3D(force_limit=2.0)
    for _ in range(12):
        normals = rng.normal(size=(5, 3))
        bounds = rng.uniform(0.2, 1.2, size=5)  # origin is feasible
        desired = rng.uniform(-2.0, 2.0, size=3)
        constraints = list(zip(normals, bounds))
        actual = cbf._exact_feasible_projection(desired, constraints)
        assert actual is not None

        reference = minimize(
            lambda u: float(np.sum((u - desired) ** 2)),
            x0=np.zeros(3), method="SLSQP",
            bounds=[(-2.0, 2.0)] * 3,
            constraints={"type": "ineq", "fun": lambda u: bounds - normals @ u},
            options={"ftol": 1e-12},
        )
        assert reference.success
        assert np.all(normals @ actual <= bounds + 1e-8)
        assert np.all(np.abs(actual) <= 2.0 + 1e-8)
        assert np.sum((actual - desired) ** 2) <= np.sum((reference.x - desired) ** 2) + 1e-7


def test_cbf_stopping_envelope_brakes_before_wall_becomes_unrecoverable():
    cbf = mujoco_3d_cbf.ControlBarrierFilter3D()
    action, active = cbf.compute_safe_control(
        pos=np.array([0.8, 0.0, 1.0]),
        vel=np.array([2.5, 0.0, 0.0]),
        desired_u=np.array([2.0, 0.0, 0.0]),
        obstacles=[],
    )
    assert active
    assert action[0] < -1.0
    assert cbf.last_constraint_residual is not None
    assert cbf.last_constraint_residual <= 1e-8


def test_benchmark_counts_collision_on_last_step_and_final_distance():
    class OneStepWorld:
        config = SimpleNamespace(success_radius=0.25)

        def reset(self, rng):
            return {
                "robot_pos": np.array([-2.0, -2.0, 0.5]),
                "robot_velocity": np.zeros(3),
                "target_pos": np.array([2.0, 2.0, 0.5]),
                "distance": 5.6568,
                "safety_violation": False,
            }

        def step(self, desired_control, force_braking=False):
            return {"distance": 1.2345, "safety_violation": True}

    result = run_3d_episode(
        OneStepWorld(), "CBF_ONLY", seed=12,
        sensor_bias=np.zeros(3), max_steps=1,
    )

    assert result["collision_occurred"] == 1
    assert result["final_distance"] == 1.2345
    assert result["timeout"] == 1


def test_exploratory_range_guard_abstains_on_uncorroborated_stop(monkeypatch):
    class ImmediateStopController:
        def reset(self):
            pass

        def update(self, *args, **kwargs):
            return np.zeros(2), "STOP", None, False

    class FixedWorld:
        config = SimpleNamespace(success_radius=0.25)

        def reset(self, rng):
            return {
                "robot_pos": np.zeros(3),
                "robot_velocity": np.zeros(3),
                "target_pos": np.array([0.4, 0.0, 0.0]),
                "distance": 0.4,
                "safety_violation": False,
            }

        def step(self, desired_control, force_braking=False):
            assert force_braking
            return {"distance": 0.4, "safety_violation": False}

    monkeypatch.setattr(benchmark_physical_3d_cbf, "AegisV9Controller", ImmediateStopController)
    world = FixedWorld()
    original = run_3d_episode(world, "AEGIS_V9_CBF", 12, np.zeros(3), max_steps=1)
    guarded = run_3d_episode(world, "AEGIS_V9_CBF_RANGE_GUARD", 12, np.zeros(3), max_steps=1)

    assert original["false_arrival"] == 1
    assert guarded["false_arrival"] == 0
    assert guarded["abstained"] == 1
    assert guarded["true_success"] == 0


@pytest.mark.parametrize("fault", [
    {"range_dropout_probability": 1.0},
    {"range_latency_steps": 2},
])
def test_range_guard_and_window_reject_missing_or_stale_measurement(monkeypatch, fault):
    class ImmediateStopController:
        def reset(self):
            pass

        def update(self, *args, **kwargs):
            return np.zeros(2), "STOP", None, False

    class FixedWorld:
        config = SimpleNamespace(success_radius=0.25)

        def reset(self, rng):
            return {
                "robot_pos": np.zeros(3),
                "robot_velocity": np.zeros(3),
                "target_pos": np.array([0.4, 0.0, 0.0]),
                "distance": 0.4,
                "safety_violation": False,
            }

        def step(self, desired_control, force_braking=False):
            assert force_braking
            return {"distance": 0.4, "safety_violation": False}

    monkeypatch.setattr(benchmark_physical_3d_cbf, "AegisV9Controller", ImmediateStopController)
    for arm in (
        "AEGIS_V9_CBF_RANGE_GUARD", "AEGIS_V9_CBF_RANGE_WINDOW",
        "AEGIS_V9_CBF_RANGE_3D_VETO",
    ):
        result = run_3d_episode(FixedWorld(), arm, 12, np.zeros(3), max_steps=5, **fault)
        assert result["false_arrival"] == 0
        assert result["abstained"] == 1


def test_3d_veto_rejects_range_underread_when_vectors_disagree():
    close = [np.array([0.10, 0.0, 0.0])] * 4
    far = [np.array([0.40, 0.0, 0.0])] * 4
    check = benchmark_physical_3d_cbf.corroborate_3d_stop

    assert check([0.10] * 4, close, close, sigma=0.05, radius=0.25)
    assert not check([0.10] * 4, far, far, sigma=0.05, radius=0.25)
    assert not check([0.40] * 4, close, close, sigma=0.05, radius=0.25)
    assert not check([float("nan")] * 4, close, close, sigma=0.05, radius=0.25)
    assert not check([0.10] * 3, close, close, sigma=0.05, radius=0.25)


def test_benchmark_evidence_is_complete_and_not_overwritten(tmp_path):
    output = tmp_path / "development.json"
    args = ["--seed-start", "99001", "--n-seeds", "1", "--max-steps", "3", "--output", str(output)]
    benchmark_physical_3d_cbf.main(args)
    evidence = json.loads(output.read_text())

    assert evidence["classification"] == "EXPLORATORY_SIMULATION"
    assert len(evidence["episodes"]) == 3 * 6
    assert all("bias_xyz" in row for row in evidence["episodes"])
    for label, summary in evidence["summary"].items():
        rows = [row for row in evidence["episodes"] if row["controller"] == label]
        assert summary["accepted"] == sum(row["true_success"] + row["false_arrival"] for row in rows)
        assert summary["timeout"] == sum(row["timeout"] for row in rows)
        assert summary["cbf_constraint_violation_episodes"] == sum(
            row["cbf_constraint_violation_occurred"] for row in rows
        )
        assert summary["cbf_unchecked_steps"] == sum(row["cbf_unchecked_steps"] for row in rows)
        assert summary["cbf_exact_fallback_steps"] == sum(row["cbf_exact_fallback_steps"] for row in rows)
        assert summary["cbf_infeasible_steps"] == sum(row["cbf_infeasible_steps"] for row in rows)
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        benchmark_physical_3d_cbf.main(args)
    assert output.read_bytes() == original


def test_explicit_vertical_bias_records_one_scenario(tmp_path):
    output = tmp_path / "vertical.json"
    benchmark_physical_3d_cbf.main([
        "--seed-start", "99001", "--n-seeds", "1", "--max-steps", "2",
        "--sensor-bias-xyz", "0", "0", "0.6", "--output", str(output),
    ])
    evidence = json.loads(output.read_text())
    assert evidence["bias_vectors_xyz"] == [[0.0, 0.0, 0.6]]
    assert len(evidence["episodes"]) == 6
    assert all(row["bias_xyz"] == [0.0, 0.0, 0.6] for row in evidence["episodes"])
