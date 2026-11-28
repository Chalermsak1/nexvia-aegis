"""Minimal 1D braking & fallback control test fixture.

Separates plant true state from controller observations to prevent hidden-state
leakage, reuses DelayedSlewBrake for actuator delay/ramp/cap/power-loss, and
verifies physical stopping outcomes including inter-sample clearance extrema.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Callable

from .bounded_braking import scalar
from .dynamic_braking import DelayedSlewBrake


@dataclass(frozen=True)
class SensorObservation:
    """Only interface exposed to controllers (no true plant/fault state)."""

    tick: int
    timestamp_s: float
    measured_position_m: float
    measured_velocity_m_s: float
    obstacle_position_m: float


@dataclass(frozen=True)
class ActuatorSpec:
    delay_ticks: int
    slew_n_s: float
    cap_n: float


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    dt_s: float = 0.02
    max_ticks: int = 250
    mass_kg: float = 10.0
    initial_position_m: float = 0.0
    initial_velocity_m_s: float = 5.0
    obstacle_position_m: float = 10.0
    primary_actuator: ActuatorSpec = ActuatorSpec(delay_ticks=0, slew_n_s=1000.0, cap_n=50.0)
    backup_actuator: ActuatorSpec | None = None
    power_loss_tick: int | None = None
    backup_available: bool = True
    disturbance_n: float = 0.0
    position_noise_m: float = 0.0
    velocity_noise_m_s: float = 0.0
    stop_velocity_eps_m_s: float = 1e-3


@dataclass(frozen=True)
class StepRecord:
    tick: int
    time_s: float
    true_position_m: float
    true_velocity_m_s: float
    distance_to_obstacle_m: float
    segment_min_clearance_m: float
    observed_position_m: float
    observed_velocity_m_s: float
    commanded_brake_force_n: float
    primary_force_n: float
    backup_force_n: float
    actual_brake_force_n: float
    primary_powered: bool
    backup_engaged: bool
    disturbance_n: float
    collided: bool
    physically_stopped: bool


@dataclass(frozen=True)
class EpisodeResult:
    scenario: str
    outcome: str
    physically_stopped: bool
    collided: bool
    brake_cmd_time_s: float | None
    brake_engage_time_s: float | None
    stop_time_s: float | None
    stopping_distance_m: float | None
    min_clearance_m: float
    final_position_m: float
    final_velocity_m_s: float
    max_actual_brake_force_n: float
    steps: tuple[StepRecord, ...]


class FallbackBrakeController:
    """Observation-only braking controller with conservative stopping trigger.

    Decides solely from SensorObservation; has zero access to plant internals,
    actual brake force, power state, or disturbance.
    """

    def __init__(self, *, max_brake_force_n: float, trigger_margin_m: float = 0.5,
                 assumed_decel_m_s2: float = 2.0):
        self.max_brake_force_n = scalar(max_brake_force_n, "max_brake_force_n", positive=True)
        self.trigger_margin_m = scalar(trigger_margin_m, "trigger_margin_m")
        self.assumed_decel_m_s2 = scalar(assumed_decel_m_s2, "assumed_decel_m_s2", positive=True)
        self.latched = False

    def compute_brake_command(self, obs: SensorObservation) -> float:
        if not isinstance(obs, SensorObservation):
            raise TypeError("controller only accepts SensorObservation")
        v = max(0.0, obs.measured_velocity_m_s)
        clearance = obs.obstacle_position_m - obs.measured_position_m
        est_stop_dist = (v * v) / (2.0 * self.assumed_decel_m_s2)
        if self.latched or clearance <= est_stop_dist + self.trigger_margin_m:
            self.latched = True
            return -self.max_brake_force_n if v > 0.0 else 0.0
        return 0.0


def _segment_max_position(p0: float, v0: float, acc: float, dt: float) -> float:
    candidates = [p0, p0 + v0 * dt + 0.5 * acc * dt * dt]
    if acc < 0.0:
        t_peak = -v0 / acc
        if 0.0 < t_peak < dt:
            candidates.append(p0 + v0 * t_peak + 0.5 * acc * t_peak * t_peak)
    return max(candidates)


def run_episode(
    config: ScenarioConfig,
    controller: FallbackBrakeController | Callable[[SensorObservation], float],
) -> EpisodeResult:
    dt = scalar(config.dt_s, "dt_s", positive=True)
    mass = scalar(config.mass_kg, "mass_kg", positive=True)
    if config.max_ticks <= 0:
        raise ValueError("max_ticks must be positive")

    primary = DelayedSlewBrake(
        delay_ticks=config.primary_actuator.delay_ticks,
        slew_n_s=config.primary_actuator.slew_n_s,
        cap_n=config.primary_actuator.cap_n,
        dt_seconds=dt,
    )
    backup = (
        DelayedSlewBrake(
            delay_ticks=config.backup_actuator.delay_ticks,
            slew_n_s=config.backup_actuator.slew_n_s,
            cap_n=config.backup_actuator.cap_n,
            dt_seconds=dt,
        )
        if config.backup_actuator is not None
        else None
    )

    compute = (
        controller.compute_brake_command
        if isinstance(controller, FallbackBrakeController)
        else controller
    )

    p = float(config.initial_position_m)
    v = float(config.initial_velocity_m_s)
    obs_p_limit = float(config.obstacle_position_m)
    min_clearance = obs_p_limit - p
    collided = min_clearance <= 0.0
    physically_stopped = abs(v) <= config.stop_velocity_eps_m_s and not collided

    brake_cmd_time: float | None = None
    brake_cmd_pos: float | None = None
    brake_engage_time: float | None = None
    stop_time: float | None = None
    max_brake_mag = 0.0
    records: list[StepRecord] = []

    for tick in range(config.max_ticks):
        t = tick * dt
        obs = SensorObservation(
            tick=tick,
            timestamp_s=t,
            measured_position_m=p + config.position_noise_m,
            measured_velocity_m_s=v + config.velocity_noise_m_s,
            obstacle_position_m=obs_p_limit,
        )
        cmd_force = float(compute(obs))
        if not math.isfinite(cmd_force):
            raise ValueError("controller returned non-finite force")
        if brake_cmd_time is None and cmd_force < 0.0:
            brake_cmd_time = t
            brake_cmd_pos = p

        primary_powered = config.power_loss_tick is None or tick < config.power_loss_tick
        primary_force = primary.step((cmd_force, 0.0, 0.0), tick=tick, powered=primary_powered)[0]

        backup_engaged = False
        backup_force = 0.0
        if backup is not None:
            # Backup actuator activates when primary power is lost and a brake request is active.
            backup_req = cmd_force if (not primary_powered and config.backup_available) else 0.0
            backup_powered = (not primary_powered) and config.backup_available
            backup_force = backup.step((backup_req, 0.0, 0.0), tick=tick, powered=backup_powered)[0]
            backup_engaged = abs(backup_force) > 1e-12

        total_brake = primary_force + backup_force
        if brake_engage_time is None and total_brake < -1e-9:
            brake_engage_time = t
        max_brake_mag = max(max_brake_mag, abs(total_brake))

        # Physical friction-like brake cannot reverse velocity past zero; once v == 0,
        # static braking holds unless disturbance exceeds available braking magnitude.
        if v <= config.stop_velocity_eps_m_s and config.disturbance_n <= abs(total_brake):
            acc = 0.0
            p_next = p
            v_next = 0.0
            seg_max_p = p
            step_stop_dt = 0.0
        else:
            acc = (total_brake + config.disturbance_n) / mass
            if v > 0.0 and acc < 0.0 and v + acc * dt <= 0.0:
                step_stop_dt = -v / acc
                p_next = p + v * step_stop_dt + 0.5 * acc * step_stop_dt * step_stop_dt
                v_next = 0.0
                seg_max_p = max(p, p_next)
            else:
                step_stop_dt = dt
                p_next = p + v * dt + 0.5 * acc * dt * dt
                v_next = v + acc * dt
                seg_max_p = _segment_max_position(p, v, acc, dt)

        seg_min_clearance = obs_p_limit - seg_max_p
        min_clearance = min(min_clearance, seg_min_clearance)
        if seg_min_clearance <= 0.0:
            collided = True

        p, v = p_next, v_next
        if not collided and abs(v) <= config.stop_velocity_eps_m_s and config.disturbance_n <= abs(total_brake):
            physically_stopped = True
            if stop_time is None:
                stop_time = t + step_stop_dt

        records.append(
            StepRecord(
                tick=tick,
                time_s=t,
                true_position_m=p,
                true_velocity_m_s=v,
                distance_to_obstacle_m=obs_p_limit - p,
                segment_min_clearance_m=seg_min_clearance,
                observed_position_m=obs.measured_position_m,
                observed_velocity_m_s=obs.measured_velocity_m_s,
                commanded_brake_force_n=cmd_force,
                primary_force_n=primary_force,
                backup_force_n=backup_force,
                actual_brake_force_n=total_brake,
                primary_powered=primary_powered,
                backup_engaged=backup_engaged,
                disturbance_n=config.disturbance_n,
                collided=collided,
                physically_stopped=physically_stopped,
            )
        )
        if collided or physically_stopped:
            break

    stopping_distance = (
        (p - brake_cmd_pos) if (physically_stopped and brake_cmd_pos is not None) else None
    )
    if collided:
        outcome = "COLLISION"
    elif physically_stopped:
        outcome = "SAFE_PHYSICAL_STOP"
    else:
        outcome = "HORIZON_EXCEEDED_NOT_STOPPED"

    return EpisodeResult(
        scenario=config.name,
        outcome=outcome,
        physically_stopped=physically_stopped,
        collided=collided,
        brake_cmd_time_s=brake_cmd_time,
        brake_engage_time_s=brake_engage_time,
        stop_time_s=stop_time,
        stopping_distance_m=stopping_distance,
        min_clearance_m=min_clearance,
        final_position_m=p,
        final_velocity_m_s=v,
        max_actual_brake_force_n=max_brake_mag,
        steps=tuple(records),
    )


def export_raw_evidence(result: EpisodeResult, output_dir: Path) -> tuple[Path, Path]:
    """Write per-step CSV and summary JSON raw evidence without overwriting."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{result.scenario}_trace.csv"
    json_path = output_dir / f"{result.scenario}_summary.json"
    if csv_path.exists() or json_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing evidence in {output_dir}")

    fieldnames = list(StepRecord.__dataclass_fields__.keys())
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for step in result.steps:
            writer.writerow(asdict(step))

    summary = asdict(result)
    summary.pop("steps")
    summary["step_count"] = len(result.steps)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return csv_path, json_path
