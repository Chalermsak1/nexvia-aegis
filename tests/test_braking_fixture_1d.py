"""Tests for the 1D braking & fallback control test fixture."""
from __future__ import annotations

import json
import pytest

from aegis.development.braking_fixture_1d import (
    ActuatorSpec,
    FallbackBrakeController,
    ScenarioConfig,
    SensorObservation,
    export_raw_evidence,
    run_episode,
)


def test_nominal_safe_physical_stop():
    cfg = ScenarioConfig(
        name="nominal",
        initial_velocity_m_s=5.0,
        obstacle_position_m=10.0,
        primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=5000.0, cap_n=50.0),
    )
    ctrl = FallbackBrakeController(max_brake_force_n=50.0, trigger_margin_m=1.0, assumed_decel_m_s2=3.0)
    res = run_episode(cfg, ctrl)

    assert res.outcome == "SAFE_PHYSICAL_STOP"
    assert res.physically_stopped is True
    assert res.collided is False
    assert res.min_clearance_m > 0.0
    assert res.brake_cmd_time_s is not None
    assert res.brake_engage_time_s == res.brake_cmd_time_s
    assert res.stopping_distance_m is not None and res.stopping_distance_m > 0.0


def test_delayed_braking_increases_stopping_distance_and_can_collide():
    ctrl_fast = FallbackBrakeController(max_brake_force_n=50.0, trigger_margin_m=1.0, assumed_decel_m_s2=4.0)
    res_zero = run_episode(
        ScenarioConfig(
            name="delay_0",
            initial_velocity_m_s=6.0,
            obstacle_position_m=10.0,
            primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=5000.0, cap_n=50.0),
        ),
        ctrl_fast,
    )

    ctrl_delayed = FallbackBrakeController(max_brake_force_n=50.0, trigger_margin_m=1.0, assumed_decel_m_s2=4.0)
    res_small_delay = run_episode(
        ScenarioConfig(
            name="delay_5",
            initial_velocity_m_s=6.0,
            obstacle_position_m=10.0,
            primary_actuator=ActuatorSpec(delay_ticks=5, slew_n_s=5000.0, cap_n=50.0),
        ),
        ctrl_delayed,
    )
    assert res_small_delay.brake_engage_time_s > res_small_delay.brake_cmd_time_s
    assert res_small_delay.stopping_distance_m > res_zero.stopping_distance_m

    ctrl_extreme = FallbackBrakeController(max_brake_force_n=50.0, trigger_margin_m=0.5, assumed_decel_m_s2=4.5)
    res_collide = run_episode(
        ScenarioConfig(
            name="delay_extreme",
            initial_velocity_m_s=6.0,
            obstacle_position_m=6.0,
            primary_actuator=ActuatorSpec(delay_ticks=30, slew_n_s=5000.0, cap_n=50.0),
        ),
        ctrl_extreme,
    )
    assert res_collide.outcome == "COLLISION"
    assert res_collide.collided is True
    assert res_collide.physically_stopped is False


def test_ramped_braking_gradual_force_buildup():
    ctrl_step = FallbackBrakeController(max_brake_force_n=50.0, trigger_margin_m=2.0, assumed_decel_m_s2=2.5)
    res_step = run_episode(
        ScenarioConfig(
            name="instant_slew",
            initial_velocity_m_s=5.0,
            obstacle_position_m=12.0,
            primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=5000.0, cap_n=50.0),
        ),
        ctrl_step,
    )

    ctrl_ramp = FallbackBrakeController(max_brake_force_n=50.0, trigger_margin_m=2.0, assumed_decel_m_s2=2.5)
    res_ramp = run_episode(
        ScenarioConfig(
            name="slow_ramp",
            initial_velocity_m_s=5.0,
            obstacle_position_m=12.0,
            primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=40.0, cap_n=50.0),
        ),
        ctrl_ramp,
    )
    assert res_ramp.outcome == "SAFE_PHYSICAL_STOP"
    assert res_ramp.stopping_distance_m > res_step.stopping_distance_m
    # Verify actual brake force increases gradually rather than jumping to 50N immediately.
    brake_forces = [abs(s.actual_brake_force_n) for s in res_ramp.steps if s.commanded_brake_force_n < 0.0]
    assert brake_forces[0] < 50.0
    assert brake_forces[1] > brake_forces[0]


def test_power_loss_with_backup_vs_unavailable_backup():
    base_kwargs = dict(
        initial_velocity_m_s=5.0,
        obstacle_position_m=10.0,
        primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=2000.0, cap_n=50.0),
        backup_actuator=ActuatorSpec(delay_ticks=2, slew_n_s=1000.0, cap_n=35.0),
        power_loss_tick=5,
    )

    res_with_backup = run_episode(
        ScenarioConfig(name="power_loss_backup_ok", backup_available=True, **base_kwargs),
        FallbackBrakeController(max_brake_force_n=50.0, trigger_margin_m=2.0, assumed_decel_m_s2=2.0),
    )
    assert res_with_backup.outcome == "SAFE_PHYSICAL_STOP"
    assert any(s.backup_engaged for s in res_with_backup.steps)

    res_no_backup = run_episode(
        ScenarioConfig(name="power_loss_no_backup", backup_available=False, **base_kwargs),
        FallbackBrakeController(max_brake_force_n=50.0, trigger_margin_m=2.0, assumed_decel_m_s2=2.0),
    )
    assert res_no_backup.outcome == "COLLISION"
    assert res_no_backup.physically_stopped is False


def test_disturbance_and_actuator_saturation_can_prevent_stop():
    # Forward disturbance (30N) exceeds capped actuator force (25N) -> must collide, never claim safe stop.
    cfg = ScenarioConfig(
        name="insufficient_brake_under_disturbance",
        initial_velocity_m_s=4.0,
        obstacle_position_m=10.0,
        primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=2000.0, cap_n=25.0),
        disturbance_n=30.0,
    )
    ctrl = FallbackBrakeController(max_brake_force_n=80.0, trigger_margin_m=5.0, assumed_decel_m_s2=2.0)
    res = run_episode(cfg, ctrl)

    assert res.max_actual_brake_force_n <= 25.0 + 1e-9
    assert res.outcome == "COLLISION"
    assert res.physically_stopped is False


def test_controller_receives_only_observation_no_hidden_state():
    seen_types = []

    def inspecting_controller(obs):
        seen_types.append(type(obs))
        assert not hasattr(obs, "true_position_m")
        assert not hasattr(obs, "actual_brake_force_n")
        assert not hasattr(obs, "primary_powered")
        assert not hasattr(obs, "disturbance_n")
        return -50.0

    res = run_episode(ScenarioConfig(name="contract_check", max_ticks=5), inspecting_controller)
    assert seen_types and all(t is SensorObservation for t in seen_types)
    assert res.outcome == "HORIZON_EXCEEDED_NOT_STOPPED"
    assert res.physically_stopped is False


def test_export_raw_evidence_writes_csv_and_json_without_overwrite(tmp_path):
    res = run_episode(
        ScenarioConfig(name="evidence_export"),
        FallbackBrakeController(max_brake_force_n=50.0, trigger_margin_m=2.0, assumed_decel_m_s2=2.5),
    )
    csv_path, json_path = export_raw_evidence(res, tmp_path)
    assert csv_path.exists() and json_path.exists()
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    assert summary["outcome"] == "SAFE_PHYSICAL_STOP"
    assert summary["step_count"] == len(res.steps)
    with pytest.raises(FileExistsError):
        export_raw_evidence(res, tmp_path)


def test_campaign_runner_generates_both_safe_and_failing_raw_evidence(tmp_path):
    from scripts.research.run_braking_study_1d import run_campaign

    rows = run_campaign(tmp_path)
    assert len(rows) == 14
    outcomes = {r["outcome"] for r in rows}
    assert "SAFE_PHYSICAL_STOP" in outcomes
    assert "COLLISION" in outcomes
    assert (tmp_path / "campaign_summary.csv").exists()
    assert (tmp_path / "campaign_summary.json").exists()
    with pytest.raises(FileExistsError):
        run_campaign(tmp_path)

