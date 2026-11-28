"""Reproducible 1D braking & fallback control sweep runner.

Executes nominal, delayed, ramped, power-loss, disturbance/actuator-limit, and
combined-fault scenarios using braking_fixture_1d and writes immutable raw
evidence (per-step CSV traces, per-scenario JSON summaries, and campaign summary).
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path

from aegis.development.braking_fixture_1d import (
    ActuatorSpec,
    EpisodeResult,
    FallbackBrakeController,
    ScenarioConfig,
    export_raw_evidence,
    run_episode,
)


def build_scenarios() -> list[tuple[ScenarioConfig, dict]]:
    """Return ordered list of (ScenarioConfig, controller_kwargs)."""
    default_ctrl = dict(max_brake_force_n=50.0, trigger_margin_m=1.5, assumed_decel_m_s2=2.5)
    return [
        # 1. Nominal baseline
        (
            ScenarioConfig(
                name="01_nominal_ideal",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=5000.0, cap_n=50.0),
            ),
            default_ctrl,
        ),
        # 2. Delayed braking sweep (0.10s, 0.30s, 0.60s at dt=0.02s)
        (
            ScenarioConfig(
                name="02_delay_100ms",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=5, slew_n_s=5000.0, cap_n=50.0),
            ),
            default_ctrl,
        ),
        (
            ScenarioConfig(
                name="03_delay_300ms",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=15, slew_n_s=5000.0, cap_n=50.0),
            ),
            default_ctrl,
        ),
        (
            ScenarioConfig(
                name="04_delay_600ms_fail",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=30, slew_n_s=5000.0, cap_n=50.0),
            ),
            default_ctrl,
        ),
        # 3. Ramped braking sweep (slew rate 100 N/s, 40 N/s, 15 N/s)
        (
            ScenarioConfig(
                name="05_ramp_100n_s",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=100.0, cap_n=50.0),
            ),
            default_ctrl,
        ),
        (
            ScenarioConfig(
                name="06_ramp_40n_s",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=40.0, cap_n=50.0),
            ),
            default_ctrl,
        ),
        (
            ScenarioConfig(
                name="07_ramp_15n_s_fail",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=15.0, cap_n=50.0),
            ),
            default_ctrl,
        ),
        # 4. Power loss & insufficient braking
        (
            ScenarioConfig(
                name="08_power_loss_backup_ok",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=2000.0, cap_n=50.0),
                backup_actuator=ActuatorSpec(delay_ticks=3, slew_n_s=500.0, cap_n=35.0),
                power_loss_tick=30,
                backup_available=True,
            ),
            default_ctrl,
        ),
        (
            ScenarioConfig(
                name="09_power_loss_backup_weak_fail",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=2000.0, cap_n=50.0),
                backup_actuator=ActuatorSpec(delay_ticks=10, slew_n_s=100.0, cap_n=12.0),
                power_loss_tick=30,
                backup_available=True,
            ),
            default_ctrl,
        ),
        (
            ScenarioConfig(
                name="10_power_loss_no_backup_fail",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=2000.0, cap_n=50.0),
                backup_actuator=ActuatorSpec(delay_ticks=3, slew_n_s=500.0, cap_n=35.0),
                power_loss_tick=30,
                backup_available=False,
            ),
            default_ctrl,
        ),
        # 5. Disturbance & actuator limits
        (
            ScenarioConfig(
                name="11_disturbance_15n_cap_50n",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=2000.0, cap_n=50.0),
                disturbance_n=15.0,
            ),
            default_ctrl,
        ),
        (
            ScenarioConfig(
                name="12_disturbance_30n_cap_25n_fail",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=0, slew_n_s=2000.0, cap_n=25.0),
                disturbance_n=30.0,
            ),
            default_ctrl,
        ),
        # 6. Combined faults (delay + ramp + disturbance + power loss)
        (
            ScenarioConfig(
                name="13_combined_moderate_ok",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=3, slew_n_s=150.0, cap_n=45.0),
                backup_actuator=ActuatorSpec(delay_ticks=3, slew_n_s=120.0, cap_n=35.0),
                power_loss_tick=40,
                backup_available=True,
                disturbance_n=8.0,
            ),
            default_ctrl,
        ),
        (
            ScenarioConfig(
                name="14_combined_severe_fail",
                initial_velocity_m_s=5.0,
                obstacle_position_m=10.0,
                primary_actuator=ActuatorSpec(delay_ticks=8, slew_n_s=60.0, cap_n=40.0),
                backup_actuator=ActuatorSpec(delay_ticks=8, slew_n_s=50.0, cap_n=25.0),
                power_loss_tick=40,
                backup_available=True,
                disturbance_n=15.0,
            ),
            default_ctrl,
        ),
    ]


def run_campaign(output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = output_dir / "campaign_summary.csv"
    summary_json = output_dir / "campaign_summary.json"
    if summary_csv.exists() or summary_json.exists():
        raise FileExistsError(f"Refusing to overwrite existing campaign summary in {output_dir}")

    rows: list[dict] = []
    for cfg, ctrl_kwargs in build_scenarios():
        ctrl = FallbackBrakeController(**ctrl_kwargs)
        res: EpisodeResult = run_episode(cfg, ctrl)
        export_raw_evidence(res, output_dir)
        rows.append(
            {
                "scenario": res.scenario,
                "outcome": res.outcome,
                "physically_stopped": res.physically_stopped,
                "collided": res.collided,
                "delay_ticks": cfg.primary_actuator.delay_ticks,
                "slew_n_s": cfg.primary_actuator.slew_n_s,
                "cap_n": cfg.primary_actuator.cap_n,
                "power_loss_tick": cfg.power_loss_tick,
                "backup_available": cfg.backup_available if cfg.backup_actuator else False,
                "disturbance_n": cfg.disturbance_n,
                "brake_cmd_time_s": res.brake_cmd_time_s,
                "brake_engage_time_s": res.brake_engage_time_s,
                "stop_time_s": res.stop_time_s,
                "stopping_distance_m": res.stopping_distance_m,
                "max_actual_brake_force_n": res.max_actual_brake_force_n,
                "min_clearance_m": res.min_clearance_m,
                "final_velocity_m_s": res.final_velocity_m_s,
                "step_count": len(res.steps),
            }
        )

    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary_json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 1D braking fault sweep and export raw evidence.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/research_development/braking_fixture_1d/run_01"),
        help="Previously unused directory for raw evidence output.",
    )
    args = parser.parse_args()
    rows = run_campaign(args.output_dir)
    passed = sum(1 for r in rows if r["outcome"] == "SAFE_PHYSICAL_STOP")
    failed = len(rows) - passed
    print(f"Completed {len(rows)} scenarios -> {passed} SAFE_PHYSICAL_STOP, {failed} FAILED/COLLISION")
    print(f"Raw evidence written to: {args.output_dir}")


if __name__ == "__main__":
    main()
