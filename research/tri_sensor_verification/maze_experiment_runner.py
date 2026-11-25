"""
3D Subterranean Maze Exploration Experiment Runner (My Sensor Research).

Runs a full controlled benchmark inside NEXVIA AEGIS's existing 3D subterranean
maze (FrontierExplorationEngine) comparing 3 localization arms across ALL 3
sensors (S1_VIO, S2_LIDAR, S3_UWB) and ALL GitHub-aligned fault modes:
  - NOMINAL
  - GRADUAL_DRIFT       (tested on S1, S2, S3 individually)
  - HEAVY_DRIFT         (tested on S1, S2, S3 individually)
  - SUDDEN_BIAS         (tested on S1, S2, S3 individually)
  - OUTLIER_BURSTS      (tested on S1, S2, S3 individually)
  - RETIMESTAMPED_FREEZE(tested on S1, S2, S3 individually — LIVE01 #1 gap)
  - SENSOR_BLACKOUT     (tested on S1, S2, S3 individually — V9-M16 blackout)
  - DUAL_SENSOR_FAILURE (stress test / counterexample: S1 heavy drift + S2 freeze)

Every run writes complete, granular, separated logs to:
  research/tri_sensor_verification/logs/<run_id>/
    ├── experiment_config.json
    ├── summary_table.csv
    ├── summary_report.json
    ├── audit_quarantine_events.jsonl
    ├── dashboard_payload.json
    ├── per_scenario/<scenario_id>_telemetry.csv
    └── figures/*.png
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import datetime
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from aegis.navigation import frontier_exploration as frontier_mod
from aegis.navigation.frontier_exploration import (
    ExplorationConfig,
    FrontierExplorationEngine,
    OccupancyVoxelGrid3D,
)
from research.tri_sensor_verification.sensor_suite import (
    DEFAULT_TRI_SENSORS,
    FaultInjectionSpec,
    FaultType,
    TriSensorSimulator,
)
from research.tri_sensor_verification.tri_sensor_verifier import (
    NaiveAverageFusion,
    TriSensorVerifier,
    TwoSensorMinSigmaBaseline,
    VerifierConfig,
)


# ---------------------------------------------------------------------------
# Maze Environment (mirrors experiments/benchmark_autonomous_exploration.py)
# ---------------------------------------------------------------------------
MAZE_CFG = ExplorationConfig(
    voxel_resolution=0.25,
    bounds_min=(-5.0, -5.0, 0.0),
    bounds_max=(5.0, 5.0, 2.5),
    sensor_max_range=3.5,
)

MAZE_PILLARS: List[Tuple[np.ndarray, float]] = [
    (np.array([0.0, 0.0, 1.0]), 0.60),
    (np.array([2.0, 2.0, 1.0]), 0.50),
    (np.array([-2.0, 2.0, 1.0]), 0.50),
    (np.array([2.0, -2.0, 1.0]), 0.50),
    (np.array([-2.0, -2.0, 1.0]), 0.50),
]

ROBOT_RADIUS_M = 0.22
START_POS = np.array([-3.5, -3.5, 1.0], dtype=np.float64)


def simulate_maze_lidar_hits(pos: np.ndarray, cfg: ExplorationConfig = MAZE_CFG) -> List[np.ndarray]:
    """Raycast 3D LiDAR hits from the robot's true position inside the subterranean maze."""
    hits: List[np.ndarray] = []
    azimuths = np.linspace(0.0, 2.0 * math.pi, 24, endpoint=False)
    elevations = np.radians([-20.0, 0.0, 20.0])

    for el in elevations:
        cos_el = math.cos(el)
        sin_el = math.sin(el)
        for az in azimuths:
            ray_dir = np.array([cos_el * math.cos(az), cos_el * math.sin(az), sin_el])
            hit_dist = cfg.sensor_max_range
            for obs_center, obs_r in MAZE_PILLARS:
                to_obs = obs_center - pos
                proj = float(np.dot(to_obs, ray_dir))
                if proj > 0.0:
                    perp_sq = float(np.sum(to_obs ** 2)) - proj ** 2
                    if perp_sq < obs_r ** 2:
                        d_hit = proj - math.sqrt(max(0.0, obs_r ** 2 - perp_sq))
                        if 0.0 < d_hit < hit_dist:
                            hit_dist = d_hit
            for axis in range(3):
                if ray_dir[axis] > 1e-4:
                    d_wall = (cfg.bounds_max[axis] - pos[axis]) / ray_dir[axis]
                    if 0.0 < d_wall < hit_dist:
                        hit_dist = d_wall
                elif ray_dir[axis] < -1e-4:
                    d_wall = (cfg.bounds_min[axis] - pos[axis]) / ray_dir[axis]
                    if 0.0 < d_wall < hit_dist:
                        hit_dist = d_wall
            hits.append(pos + hit_dist * ray_dir)
    return hits


def check_physical_collision(pos: np.ndarray, cfg: ExplorationConfig = MAZE_CFG) -> Tuple[bool, float]:
    """Check true physical collision against maze pillars and boundary walls."""
    min_clear = 999.0
    for obs_center, obs_r in MAZE_PILLARS:
        dist_xy = float(np.linalg.norm(pos[:2] - obs_center[:2])) - obs_r
        min_clear = min(min_clear, dist_xy)
    wall_clear = min(
        pos[0] - cfg.bounds_min[0],
        cfg.bounds_max[0] - pos[0],
        pos[1] - cfg.bounds_min[1],
        cfg.bounds_max[1] - pos[1],
    )
    min_clear = min(min_clear, float(wall_clear))
    return (min_clear <= ROBOT_RADIUS_M), min_clear


def apply_safe_pillar_avoidance(pos: np.ndarray, move: np.ndarray) -> np.ndarray:
    """Gentle local reactive steering around known pillar geometry when pose is accurate."""
    candidate = pos + move
    for obs_center, obs_r in MAZE_PILLARS:
        vec = candidate[:2] - obs_center[:2]
        d = float(np.linalg.norm(vec))
        safe_r = obs_r + ROBOT_RADIUS_M + 0.12
        if 1e-6 < d < safe_r:
            push = (vec / d) * (safe_r - d)
            candidate[0] += push[0]
            candidate[1] += push[1]
    return candidate


# ---------------------------------------------------------------------------
# Scenario Builder: All 3 Sensors x All GitHub Fault Modes + Dual Counterexample
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ExperimentScenario:
    scenario_id: str
    fault_category: str
    target_sensor: str          # S1_VIO, S2_LIDAR, S3_UWB, NONE, or DUAL_S1_S2
    description: str
    faults: Tuple[FaultInjectionSpec, ...]
    fault_start_step: int = 12


def build_all_scenarios() -> List[ExperimentScenario]:
    scenarios: List[ExperimentScenario] = [
        ExperimentScenario(
            scenario_id="00_NOMINAL_ALL_HEALTHY",
            fault_category="NOMINAL",
            target_sensor="NONE",
            description="All 3 sensors healthy under nominal Gaussian noise.",
            faults=(),
            fault_start_step=-1,
        )
    ]

    sensor_ids = [s.sensor_id for s in DEFAULT_TRI_SENSORS]
    idx = 1

    # 1. Gradual Drift on S1, S2, S3
    for sid in sensor_ids:
        scenarios.append(ExperimentScenario(
            scenario_id=f"{idx:02d}_{sid}_GRADUAL_DRIFT",
            fault_category="GRADUAL_DRIFT",
            target_sensor=sid,
            description=f"{sid} drifts slowly (+0.030, -0.020, +0.005 m/step) from step 12.",
            faults=(FaultInjectionSpec(
                sensor_id=sid,
                fault_type=FaultType.GRADUAL_DRIFT,
                start_step=12,
                drift_rate_per_step=(0.030, -0.020, 0.005),
            ),),
            fault_start_step=12,
        ))
        idx += 1

    # 2. Heavy Drift on S1, S2, S3
    for sid in sensor_ids:
        scenarios.append(ExperimentScenario(
            scenario_id=f"{idx:02d}_{sid}_HEAVY_DRIFT",
            fault_category="HEAVY_DRIFT",
            target_sensor=sid,
            description=f"{sid} experiences severe accelerating drift from step 12.",
            faults=(FaultInjectionSpec(
                sensor_id=sid,
                fault_type=FaultType.HEAVY_DRIFT,
                start_step=12,
                drift_rate_per_step=(0.085, -0.060, 0.010),
                drift_accel_per_step2=(0.006, -0.004, 0.0),
            ),),
            fault_start_step=12,
        ))
        idx += 1

    # 3. Sudden Static Bias Jump on S1, S2, S3 (V7 PRIMARY_BIAS)
    for sid in sensor_ids:
        scenarios.append(ExperimentScenario(
            scenario_id=f"{idx:02d}_{sid}_SUDDEN_BIAS",
            fault_category="SUDDEN_BIAS",
            target_sensor=sid,
            description=f"{sid} jumps abruptly by (+1.10, -0.85, +0.15 m) at step 12.",
            faults=(FaultInjectionSpec(
                sensor_id=sid,
                fault_type=FaultType.SUDDEN_BIAS,
                start_step=12,
                bias_vector=(1.10, -0.85, 0.15),
            ),),
            fault_start_step=12,
        ))
        idx += 1

    # 4. Intermittent Outlier Bursts on S1, S2, S3 (V7 OUTLIER_BURSTS)
    for sid in sensor_ids:
        scenarios.append(ExperimentScenario(
            scenario_id=f"{idx:02d}_{sid}_OUTLIER_BURSTS",
            fault_category="OUTLIER_BURSTS",
            target_sensor=sid,
            description=f"{sid} emits 30% intermittent 2.4 m spikes from step 12.",
            faults=(FaultInjectionSpec(
                sensor_id=sid,
                fault_type=FaultType.OUTLIER_BURSTS,
                start_step=12,
                outlier_prob=0.30,
                outlier_magnitude=2.40,
            ),),
            fault_start_step=12,
        ))
        idx += 1

    # 5. Retimestamped Freeze on S1, S2, S3 (LIVE01 #1 Unresolved Gap!)
    for sid in sensor_ids:
        scenarios.append(ExperimentScenario(
            scenario_id=f"{idx:02d}_{sid}_RETIMESTAMPED_FREEZE",
            fault_category="RETIMESTAMPED_FREEZE",
            target_sensor=sid,
            description=f"{sid} freezes physical reading at step 12 while emitting fresh timestamps.",
            faults=(FaultInjectionSpec(
                sensor_id=sid,
                fault_type=FaultType.RETIMESTAMPED_FREEZE,
                start_step=12,
            ),),
            fault_start_step=12,
        ))
        idx += 1

    # 6. Sensor Blackout / NaN Dropout on S1, S2, S3 (V9-M16)
    for sid in sensor_ids:
        scenarios.append(ExperimentScenario(
            scenario_id=f"{idx:02d}_{sid}_SENSOR_BLACKOUT",
            fault_category="SENSOR_BLACKOUT",
            target_sensor=sid,
            description=f"{sid} suffers complete feed blackout (NaN) from step 12.",
            faults=(FaultInjectionSpec(
                sensor_id=sid,
                fault_type=FaultType.SENSOR_BLACKOUT,
                start_step=12,
            ),),
            fault_start_step=12,
        ))
        idx += 1

    # 7. Dual Sensor Failure Stress Test / Counterexample (Research Integrity!)
    scenarios.append(ExperimentScenario(
        scenario_id=f"{idx:02d}_DUAL_S1_DRIFT_S2_FREEZE",
        fault_category="DUAL_SENSOR_FAILURE",
        target_sensor="DUAL_S1_S2",
        description="Stress counterexample: S1 heavy drift + S2 retimestamped freeze simultaneously (expect Fail-Closed Abstain).",
        faults=(
            FaultInjectionSpec(
                sensor_id="S1_VIO",
                fault_type=FaultType.HEAVY_DRIFT,
                start_step=12,
                drift_rate_per_step=(0.10, -0.07, 0.0),
                drift_accel_per_step2=(0.005, 0.0, 0.0),
            ),
            FaultInjectionSpec(
                sensor_id="S2_LIDAR",
                fault_type=FaultType.RETIMESTAMPED_FREEZE,
                start_step=12,
            ),
        ),
        fault_start_step=12,
    ))

    return scenarios


# ---------------------------------------------------------------------------
# Single Episode Execution
# ---------------------------------------------------------------------------
def run_single_arm_episode(
    scenario: ExperimentScenario,
    arm_name: str,
    num_steps: int = 45,
    base_seed: int = 202601,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Execute one deterministic 3D maze exploration episode for a given arm."""
    sensor_ids = tuple(s.sensor_id for s in DEFAULT_TRI_SENSORS)
    np.random.seed(base_seed)  # Seed frontier_exploration internal sub-sampling deterministically

    sim = TriSensorSimulator(
        sensors=DEFAULT_TRI_SENSORS,
        faults=list(scenario.faults),
        seed=base_seed + 17,
    )
    if arm_name == "NAIVE_AVG":
        fusion_engine: Any = NaiveAverageFusion(sensor_ids)
    elif arm_name == "TWO_SENSOR_MIN_SIGMA":
        fusion_engine = TwoSensorMinSigmaBaseline(sensor_ids)
    elif arm_name == "TRI_SENSOR_VERIFIER":
        fusion_engine = TriSensorVerifier(sensor_ids, VerifierConfig())
    else:
        raise ValueError(f"Unknown arm: {arm_name}")

    planner = FrontierExplorationEngine(MAZE_CFG)
    true_eval_grid = OccupancyVoxelGrid3D(MAZE_CFG)

    true_pos = START_POS.copy()
    yaw = 0.0
    vel = np.zeros(3, dtype=np.float64)

    display_errors: List[float] = []
    fault_window_errors: List[float] = []
    telemetry_rows: List[Dict[str, Any]] = []
    audit_records: List[Dict[str, Any]] = []

    first_detection_step: Optional[int] = None
    fault_active_ticks = 0
    fault_window_abstain_steps = 0
    correct_isolation_ticks = 0
    healthy_ticks = 0
    false_alarm_ticks = 0
    excluded_faulty_samples = 0
    abstain_steps = 0
    simulation_collision_ticks = 0
    min_clearance = 999.0

    for step in range(num_steps):
        # Snapshot true pose at observation time so telemetry aligns 1:1 with sensor readings
        obs_true_pos = true_pos.copy()

        # 1. Ground-truth LiDAR rays in body frame
        true_hits = simulate_maze_lidar_hits(obs_true_pos, MAZE_CFG)
        hits_rel = [h - obs_true_pos for h in true_hits]
        true_eval_grid.integrate_sensor_scan(obs_true_pos, true_hits)
        true_cov_pct = true_eval_grid.get_coverage_ratio() * 100.0

        # 2. Sample 3 sensors
        readings = sim.sample(step, obs_true_pos)
        gt_faulty_ids = [sid for sid, r in readings.items() if r.gt_fault_active]

        # 3. Run fusion / self-verification
        out = fusion_engine.verify_and_fuse(readings)

        # 4. Evaluate accuracy, isolation, false alarm & display exclusion
        disp_err = float("nan")
        if out.display_pos is not None and np.all(np.isfinite(out.display_pos)):
            disp_err = float(np.linalg.norm(out.display_pos - obs_true_pos))
            display_errors.append(disp_err)
            if gt_faulty_ids:
                fault_window_errors.append(disp_err)
        else:
            abstain_steps += 1
            if gt_faulty_ids:
                fault_window_abstain_steps += 1

        if gt_faulty_ids:
            fault_active_ticks += 1
            if len(gt_faulty_ids) == 1:
                fid = gt_faulty_ids[0]
                if fid in out.quarantined_sensors and fid not in out.used_sensors:
                    correct_isolation_ticks += 1
                    excluded_faulty_samples += 1
                    if first_detection_step is None:
                        first_detection_step = step
            else:
                # Dual failure: correct safe response is fail-closed abstention!
                if not out.trusted and out.action == "ABSTAIN_SAFE_STOP":
                    correct_isolation_ticks += 1
                    excluded_faulty_samples += len(gt_faulty_ids)
                    if first_detection_step is None:
                        first_detection_step = step
        else:
            healthy_ticks += 1
            if len(out.quarantined_sensors) > 0:
                # Do not penalize clean post-outlier probation right after an outlier burst
                if not all(v.startswith("RECOVERY_PROBATION") for v in out.quarantined_sensors.values()):
                    false_alarm_ticks += 1

        # Record separate audit events (never mixed into trusted display output)
        for ev in out.audit_events:
            audit_records.append({
                "scenario_id": scenario.scenario_id,
                "arm": arm_name,
                **ev,
                "excluded_raw_values": out.excluded_raw_values,
            })

        # 5. Act in the real maze using the arm's trusted control estimate
        if out.trusted and out.control_pos is not None:
            est_pos = out.control_pos
            believed_hits = [est_pos + rel for rel in hits_rel]
            decision = planner.step_exploration(
                drone_pos=est_pos,
                drone_yaw=yaw,
                drone_vel=vel,
                sensor_hits=believed_hits,
            )
            target = decision["target_pos"]
            delta = target - est_pos
            dist = float(np.linalg.norm(delta))
            if dist > 0.05:
                move = (delta / dist) * min(0.55, dist)
                # Robot tries to avoid pillars using its *believed* position;
                # if est_pos is drifted, reactive avoidance misses the real pillar!
                believed_next = apply_safe_pillar_avoidance(est_pos, move)
                actual_move = believed_next - est_pos
                next_true = true_pos + actual_move
                # Clamp physical walls (but detect wall hit before clamping)
                hit_wall = (
                    next_true[0] <= MAZE_CFG.bounds_min[0] + ROBOT_RADIUS_M
                    or next_true[0] >= MAZE_CFG.bounds_max[0] - ROBOT_RADIUS_M
                    or next_true[1] <= MAZE_CFG.bounds_min[1] + ROBOT_RADIUS_M
                    or next_true[1] >= MAZE_CFG.bounds_max[1] - ROBOT_RADIUS_M
                )
                next_true[0] = float(np.clip(next_true[0], MAZE_CFG.bounds_min[0] + 0.15, MAZE_CFG.bounds_max[0] - 0.15))
                next_true[1] = float(np.clip(next_true[1], MAZE_CFG.bounds_min[1] + 0.15, MAZE_CFG.bounds_max[1] - 0.15))
                next_true[2] = float(np.clip(next_true[2], 0.4, 2.1))
                true_pos = next_true
                yaw = decision["target_yaw"]
                vel = actual_move / 0.20

                collided, clr = check_physical_collision(true_pos, MAZE_CFG)
                min_clearance = min(min_clearance, clr)
                if collided or hit_wall:
                    simulation_collision_ticks += 1
        else:
            # Fail-closed safe stop: hold position!
            vel = np.zeros(3, dtype=np.float64)
            _, clr = check_physical_collision(true_pos, MAZE_CFG)
            min_clearance = min(min_clearance, clr)

        # 6. Append complete tick-by-tick telemetry row
        def fmt_pos(arr: Optional[np.ndarray]) -> Tuple[Any, Any, Any]:
            if arr is None:
                return "", "", ""
            return (
                round(float(arr[0]), 4) if math.isfinite(float(arr[0])) else "NaN",
                round(float(arr[1]), 4) if math.isfinite(float(arr[1])) else "NaN",
                round(float(arr[2]), 4) if math.isfinite(float(arr[2])) else "NaN",
            )

        s1x, s1y, s1z = fmt_pos(readings["S1_VIO"].position)
        s2x, s2y, s2z = fmt_pos(readings["S2_LIDAR"].position)
        s3x, s3y, s3z = fmt_pos(readings["S3_UWB"].position)
        dx, dy, dz = fmt_pos(out.display_pos)

        telemetry_rows.append({
            "scenario_id": scenario.scenario_id,
            "arm": arm_name,
            "step": step,
            "true_x": round(float(obs_true_pos[0]), 4),
            "true_y": round(float(obs_true_pos[1]), 4),
            "true_z": round(float(obs_true_pos[2]), 4),
            "s1_x": s1x, "s1_y": s1y, "s1_z": s1z,
            "s2_x": s2x, "s2_y": s2y, "s2_z": s2z,
            "s3_x": s3x, "s3_y": s3y, "s3_z": s3z,
            "display_x": dx, "display_y": dy, "display_z": dz,
            "trusted": out.trusted,
            "mode": out.mode,
            "action": out.action,
            "used_sensors": "|".join(out.used_sensors),
            "quarantined_sensors": "|".join(f"{k}:{v}" for k, v in out.quarantined_sensors.items()),
            "gt_faulty_sensors": "|".join(gt_faulty_ids),
            "display_error_m": round(disp_err, 4) if math.isfinite(disp_err) else "",
            "z_s1_s2": out.pairwise_z.get("S1_VIO_vs_S2_LIDAR", ""),
            "z_s2_s3": out.pairwise_z.get("S2_LIDAR_vs_S3_UWB", ""),
            "z_s1_s3": out.pairwise_z.get("S1_VIO_vs_S3_UWB", ""),
            "cusum_s1_s2": out.pairwise_cusum.get("S1_VIO_vs_S2_LIDAR", ""),
            "cusum_s2_s3": out.pairwise_cusum.get("S2_LIDAR_vs_S3_UWB", ""),
            "cusum_s1_s3": out.pairwise_cusum.get("S1_VIO_vs_S3_UWB", ""),
            "true_maze_coverage_pct": round(true_cov_pct, 2),
        })

    UNAVAILABLE = "Unavailable"
    estimate_count = len(display_errors)
    fault_window_estimate_count = len(fault_window_errors)

    position_rmse_m: Any = (
        round(float(np.sqrt(np.mean(np.square(display_errors)))), 4)
        if estimate_count > 0
        else UNAVAILABLE
    )
    max_display_error_m: Any = (
        round(float(np.max(display_errors)), 4)
        if estimate_count > 0
        else UNAVAILABLE
    )
    fault_window_rmse_m: Any = (
        round(float(np.sqrt(np.mean(np.square(fault_window_errors)))), 4)
        if fault_window_estimate_count > 0
        else UNAVAILABLE
    )
    det_latency = (
        (first_detection_step - scenario.fault_start_step)
        if (first_detection_step is not None and scenario.fault_start_step >= 0)
        else None
    )
    iso_acc = (correct_isolation_ticks / fault_active_ticks * 100.0) if fault_active_ticks > 0 else 100.0
    far_pct = (false_alarm_ticks / healthy_ticks * 100.0) if healthy_ticks > 0 else 0.0

    summary = {
        "scenario_id": scenario.scenario_id,
        "fault_category": scenario.fault_category,
        "target_sensor": scenario.target_sensor,
        "arm": arm_name,
        "steps": num_steps,
        "estimate_count": estimate_count,
        "abstain_steps": abstain_steps,
        "fault_window_estimate_count": fault_window_estimate_count,
        "fault_window_abstain_steps": fault_window_abstain_steps,
        "position_rmse_m": position_rmse_m,
        "fault_window_rmse_m": fault_window_rmse_m,
        "max_display_error_m": max_display_error_m,
        "detection_latency_steps": det_latency,
        "isolation_accuracy_pct": round(iso_acc, 1),
        "false_alarm_rate_pct": round(far_pct, 1),
        "excluded_faulty_samples": excluded_faulty_samples,
        "true_maze_coverage_pct": round(true_eval_grid.get_coverage_ratio() * 100.0, 2),
        "simulation_collision_ticks": simulation_collision_ticks,
        "min_clearance_m": round(min_clearance, 3),
    }
    return summary, telemetry_rows, audit_records


# ---------------------------------------------------------------------------
# Provenance Helpers (Planner Commit, Dependency Versions, Scenario Seeds)
# ---------------------------------------------------------------------------
def _collect_planner_and_env_provenance() -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    git_commit = "unknown"
    git_dirty: Optional[bool] = None
    try:
        commit_out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        if commit_out:
            git_commit = commit_out
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        git_dirty = bool(status_out)
    except Exception:
        pass

    planner_file = Path(inspect.getfile(frontier_mod)).resolve()
    try:
        planner_rel = str(planner_file.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        planner_rel = str(planner_file)
    planner_sha256 = hashlib.sha256(planner_file.read_bytes()).hexdigest()

    packages: Dict[str, str] = {}
    for pkg in ("numpy", "scipy", "matplotlib", "pytest"):
        try:
            packages[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            packages[pkg] = "not-installed"

    return {
        "planner_provenance": {
            "planner_module": frontier_mod.__name__,
            "planner_source_path": planner_rel,
            "planner_source_sha256": planner_sha256,
            "git_commit": git_commit,
            "git_dirty": git_dirty,
        },
        "dependencies": {
            "python": sys.version,
            "platform": platform.platform(),
            "packages": packages,
        },
    }


def _fmt_rmse(val: Any) -> str:
    if isinstance(val, (int, float)) and math.isfinite(val):
        return f"{val:.3f}m"
    return str(val)


# ---------------------------------------------------------------------------
# Full Suite Runner + Detailed Separated Logging (Strict No-Overwrite)
# ---------------------------------------------------------------------------
def run_full_experiment(
    run_name: Optional[str] = None,
    num_steps: int = 45,
    logs_base_dir: Optional[Path] = None,
    base_seed_start: int = 202600,
) -> Path:
    t0 = time.time()
    base_dir = Path(logs_base_dir) if logs_base_dir is not None else Path("research/tri_sensor_verification/logs")

    if run_name is None:
        stamp = "run_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        candidate = base_dir / stamp
        suffix = 2
        while candidate.exists():
            candidate = base_dir / f"{stamp}_{suffix}"
            suffix += 1
        run_name = candidate.name
        root_logs = candidate
    else:
        root_logs = base_dir / run_name
        if root_logs.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing run directory: {root_logs}. "
                "Pass a new run_name or omit run_name to create a fresh timestamped folder."
            )

    per_scen_dir = root_logs / "per_scenario"
    fig_dir = root_logs / "figures"
    root_logs.mkdir(parents=True, exist_ok=False)
    per_scen_dir.mkdir(parents=True, exist_ok=False)
    fig_dir.mkdir(parents=True, exist_ok=False)

    scenarios = build_all_scenarios()
    arms = ["NAIVE_AVG", "TWO_SENSOR_MIN_SIGMA", "TRI_SENSOR_VERIFIER"]
    scenario_seeds = [
        {
            "scenario_id": scen.scenario_id,
            "base_seed": base_seed_start + s_idx * 100,
            "planner_seed": base_seed_start + s_idx * 100,
            "sensor_sim_seed": base_seed_start + s_idx * 100 + 17,
        }
        for s_idx, scen in enumerate(scenarios)
    ]
    provenance = _collect_planner_and_env_provenance()

    # 1. Save experiment config with full provenance & per-scenario seeds
    config_payload = {
        "run_name": run_name,
        "created_at": datetime.datetime.now().isoformat(),
        "num_steps_per_episode": num_steps,
        "maze_config": asdict(MAZE_CFG),
        "sensors": [asdict(s) for s in DEFAULT_TRI_SENSORS],
        "verifier_config": asdict(VerifierConfig()),
        "arms": arms,
        "scenario_count": len(scenarios),
        "scenario_seeds": scenario_seeds,
        **provenance,
    }
    (root_logs / "experiment_config.json").write_text(
        json.dumps(config_payload, indent=2), encoding="utf-8"
    )

    all_summaries: List[Dict[str, Any]] = []
    all_audit_events: List[Dict[str, Any]] = []
    showcase_telemetry: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    showcase_ids = {
        "00_NOMINAL_ALL_HEALTHY",
        "01_S1_VIO_GRADUAL_DRIFT",
        "04_S1_VIO_HEAVY_DRIFT",
        "05_S2_LIDAR_HEAVY_DRIFT",
        "09_S3_UWB_SUDDEN_BIAS",
        "10_S1_VIO_OUTLIER_BURSTS",
        "14_S2_LIDAR_RETIMESTAMPED_FREEZE",
        "16_S1_VIO_SENSOR_BLACKOUT",
        "19_DUAL_S1_DRIFT_S2_FREEZE",
    }

    print("=" * 78)
    print(f"Running Tri-Sensor Maze Benchmark ({len(scenarios)} scenarios x {len(arms)} arms = {len(scenarios)*len(arms)} runs)")
    print(f"Logs directory: {root_logs}")
    print("=" * 78)

    for s_idx, scen in enumerate(scenarios):
        scen_seed = base_seed_start + s_idx * 100
        scen_rows: List[Dict[str, Any]] = []
        for arm in arms:
            summary, rows, audits = run_single_arm_episode(
                scenario=scen,
                arm_name=arm,
                num_steps=num_steps,
                base_seed=scen_seed,
            )
            all_summaries.append(summary)
            scen_rows.extend(rows)
            all_audit_events.extend(audits)

            if scen.scenario_id in showcase_ids:
                showcase_telemetry.setdefault(scen.scenario_id, {})[arm] = rows

        # Save detailed per-scenario CSV log separately
        csv_path = per_scen_dir / f"{scen.scenario_id}_telemetry.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(scen_rows[0].keys()))
            writer.writeheader()
            writer.writerows(scen_rows)

        # Print concise progress line comparing Naive vs Min-Sigma vs Tri-Verifier
        s_naive = all_summaries[-3]
        s_two = all_summaries[-2]
        s_tri = all_summaries[-1]
        print(
            f"[{s_idx+1:02d}/{len(scenarios):02d}] {scen.scenario_id:34s} | "
            f"RMSE: Naive={_fmt_rmse(s_naive['position_rmse_m'])}, "
            f"2-Sens={_fmt_rmse(s_two['position_rmse_m'])}, "
            f"Tri={_fmt_rmse(s_tri['position_rmse_m'])} "
            f"(est={s_tri['estimate_count']}/{s_tri['steps']}, abst={s_tri['abstain_steps']}) | "
            f"Iso={s_tri['isolation_accuracy_pct']:5.1f}% | "
            f"SimCollTicks={s_tri['simulation_collision_ticks']}"
        )

    # 2. Save Master Summary CSV
    summary_csv = root_logs / "summary_table.csv"
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_summaries[0].keys()))
        writer.writeheader()
        writer.writerows(all_summaries)

    # 3. Save Master Summary JSON
    (root_logs / "summary_report.json").write_text(
        json.dumps(
            {
                "run_name": run_name,
                "elapsed_seconds": round(time.time() - t0, 2),
                **provenance,
                "summaries": all_summaries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # 4. Save Separate Quarantine Audit Log (JSONL)
    with open(root_logs / "audit_quarantine_events.jsonl", "w", encoding="utf-8") as f:
        for ev in all_audit_events:
            f.write(json.dumps(ev) + "\n")

    # 5. Save compact dashboard payload for interactive multi-tab UI
    dashboard_payload = {
        "run_name": run_name,
        "elapsed_seconds": round(time.time() - t0, 2),
        "pillars": [[float(p[0][0]), float(p[0][1]), float(p[1])] for p in MAZE_PILLARS],
        "bounds": [MAZE_CFG.bounds_min[0], MAZE_CFG.bounds_max[0], MAZE_CFG.bounds_min[1], MAZE_CFG.bounds_max[1]],
        "summaries": all_summaries,
        "showcase": showcase_telemetry,
        "audit_sample": all_audit_events[:120],
        "total_audit_events": len(all_audit_events),
    }
    (root_logs / "dashboard_payload.json").write_text(
        json.dumps(dashboard_payload), encoding="utf-8"
    )

    # Save pointer to latest run inside base_dir
    (base_dir / "LATEST_RUN.txt").write_text(str(root_logs).replace("\\", "/"), encoding="utf-8")

    print("=" * 78)
    print(f"Completed in {time.time() - t0:.2f}s. All detailed logs saved to: {root_logs}")
    print("=" * 78)
    return root_logs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run standalone Tri-Sensor 3D Maze Verification Benchmark into a new non-overwriting run directory."
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional new folder name under logs/. Defaults to a fresh timestamped folder; refuses to overwrite existing folders.",
    )
    parser.add_argument(
        "--num-steps",
        type=int,
        default=45,
        help="Number of simulation steps per episode (default: 45).",
    )
    parser.add_argument(
        "--logs-dir",
        default=None,
        help="Optional base logs directory (default: research/tri_sensor_verification/logs).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_full_experiment(
        run_name=args.run_name,
        num_steps=args.num_steps,
        logs_base_dir=Path(args.logs_dir) if args.logs_dir else None,
    )
