"""
Automated Pytest Suite for My Tri-Sensor Self-Verification Research.

Verifies:
  1. Nominal operation uses all 3 sensors with 0 false quarantines.
  2. Single-sensor Heavy Drift, Sudden Bias, Retimestamped Freeze, and Blackout
     are isolated & excluded for EVERY sensor (S1_VIO, S2_LIDAR, S3_UWB).
  3. Faulty sensor values NEVER leak into display_pos or control_pos once quarantined.
  4. Dual simultaneous sensor failure triggers FAIL-CLOSED abstention (display_pos is None).
"""

from __future__ import annotations

import json
import numpy as np
import pytest

from research.tri_sensor_verification.maze_experiment_runner import (
    ExperimentScenario,
    run_full_experiment,
    run_single_arm_episode,
)
from research.tri_sensor_verification.sensor_suite import (
    DEFAULT_TRI_SENSORS,
    FaultInjectionSpec,
    FaultType,
    SensorReading,
    TriSensorSimulator,
)
from research.tri_sensor_verification.tri_sensor_verifier import TriSensorVerifier, VerifierConfig


SENSOR_IDS = tuple(s.sensor_id for s in DEFAULT_TRI_SENSORS)


def _run_trajectory_test(faults, steps=35, seed=101):
    sim = TriSensorSimulator(DEFAULT_TRI_SENSORS, faults=faults, seed=seed)
    verifier = TriSensorVerifier(SENSOR_IDS, VerifierConfig())
    outputs = []
    pos = np.array([-3.0, -3.0, 1.0], dtype=np.float64)
    for k in range(steps):
        pos = pos + np.array([0.16, 0.10, 0.0])
        readings = sim.sample(k, pos)
        out = verifier.verify_and_fuse(readings)
        outputs.append((pos.copy(), readings, out))
    return outputs


def test_nominal_uses_all_three_sensors_without_false_quarantine():
    trace = _run_trajectory_test(faults=[], steps=35, seed=7)
    errors = []
    quarantines = 0
    for pos, _, out in trace:
        assert out.trusted is True
        assert out.display_pos is not None
        errors.append(float(np.linalg.norm(out.display_pos - pos)))
        if out.quarantined_sensors:
            quarantines += 1
    assert np.sqrt(np.mean(np.square(errors))) < 0.06
    assert quarantines == 0


@pytest.mark.parametrize("target_sid", SENSOR_IDS)
@pytest.mark.parametrize("fault_type", [
    FaultType.HEAVY_DRIFT,
    FaultType.SUDDEN_BIAS,
    FaultType.RETIMESTAMPED_FREEZE,
    FaultType.SENSOR_BLACKOUT,
])
def test_every_sensor_fault_is_isolated_and_excluded_from_display(target_sid, fault_type):
    spec = FaultInjectionSpec(
        sensor_id=target_sid,
        fault_type=fault_type,
        start_step=10,
        drift_rate_per_step=(0.09, -0.06, 0.01),
        drift_accel_per_step2=(0.005, 0.0, 0.0),
        bias_vector=(1.2, -0.9, 0.1),
    )
    trace = _run_trajectory_test(faults=[spec], steps=35, seed=42)

    # By step 16 (at most 6 steps after onset), target_sid must be quarantined and excluded
    late_trace = trace[16:]
    for pos, _, out in late_trace:
        assert out.trusted is True
        assert target_sid in out.quarantined_sensors
        assert target_sid not in out.used_sensors
        assert out.display_pos is not None
        # Display output must remain tightly locked to ground truth (< 0.18 m)
        assert float(np.linalg.norm(out.display_pos - pos)) < 0.18


def test_dual_sensor_failure_triggers_fail_closed_abstention():
    faults = [
        FaultInjectionSpec(
            sensor_id="S1_VIO",
            fault_type=FaultType.HEAVY_DRIFT,
            start_step=10,
            drift_rate_per_step=(0.12, -0.08, 0.0),
        ),
        FaultInjectionSpec(
            sensor_id="S2_LIDAR",
            fault_type=FaultType.RETIMESTAMPED_FREEZE,
            start_step=10,
        ),
    ]
    trace = _run_trajectory_test(faults=faults, steps=30, seed=99)
    abstain_count = sum(1 for _, _, out in trace[14:] if (not out.trusted and out.display_pos is None and out.action == "ABSTAIN_SAFE_STOP"))
    assert abstain_count == len(trace[14:])


# ---------------------------------------------------------------------------
# Recovery Probation Enforcement Across ALL Fusion Branches
# ---------------------------------------------------------------------------
def _make_readings(step: int, p1, p2, p3) -> dict[str, SensorReading]:
    sigmas = {s.sensor_id: s.nominal_sigma for s in DEFAULT_TRI_SENSORS}
    return {
        "S1_VIO": SensorReading("S1_VIO", step, step * 0.2, np.asarray(p1, dtype=np.float64), sigmas["S1_VIO"]),
        "S2_LIDAR": SensorReading("S2_LIDAR", step, step * 0.2, np.asarray(p2, dtype=np.float64), sigmas["S2_LIDAR"]),
        "S3_UWB": SensorReading("S3_UWB", step, step * 0.2, np.asarray(p3, dtype=np.float64), sigmas["S3_UWB"]),
    }


def _iv_fuse_pair(r_a: SensorReading, r_b: SensorReading) -> np.ndarray:
    wa = 1.0 / (r_a.nominal_sigma ** 2)
    wb = 1.0 / (r_b.nominal_sigma ** 2)
    return (wa * r_a.position + wb * r_b.position) / (wa + wb)


def test_quarantined_sensor_excluded_during_probation_in_all3_agree_branch():
    cfg = VerifierConfig(recovery_confirm_steps=3, recovery_z_threshold=2.0)
    v = TriSensorVerifier(SENSOR_IDS, cfg)

    # Step 0: S1 blackouts -> quarantined
    out0 = v.verify_and_fuse(_make_readings(0, [np.nan, np.nan, np.nan], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]))
    assert out0.trusted is True
    assert "S1_VIO" in out0.quarantined_sensors
    assert "S1_VIO" not in out0.used_sensors

    # Steps 1-2 (probation 1/3 and 2/3): S1 returns slightly offset within recovery_z_threshold.
    # Display & Control MUST equal exact fusion of S2 & S3 only (zero contribution from S1).
    for k in (1, 2):
        base = np.array([0.2 * k, 0.0, 1.0])
        readings = _make_readings(k, base + np.array([0.08, 0.0, 0.0]), base, base)
        expected_s2_s3 = _iv_fuse_pair(readings["S2_LIDAR"], readings["S3_UWB"])
        out = v.verify_and_fuse(readings)
        assert out.trusted is True
        assert out.used_sensors == ["S2_LIDAR", "S3_UWB"]
        assert "S1_VIO" in out.quarantined_sensors
        assert out.quarantined_sensors["S1_VIO"].startswith("RECOVERY_PROBATION")
        assert np.allclose(out.display_pos, expected_s2_s3, atol=1e-9)
        assert np.allclose(out.control_pos, expected_s2_s3, atol=1e-9)

    # Step 3 (probation 3/3 complete): S1 is re-admitted
    base3 = np.array([0.6, 0.0, 1.0])
    out3 = v.verify_and_fuse(_make_readings(3, base3, base3, base3))
    assert out3.trusted is True
    assert out3.used_sensors == ["S1_VIO", "S2_LIDAR", "S3_UWB"]
    assert "S1_VIO" not in out3.quarantined_sensors
    assert any(ev["event"] == "SENSOR_RECOVERED" and ev["sensor_id"] == "S1_VIO" for ev in out3.audit_events)


def test_quarantined_sensor_excluded_in_two_valid_branch_fails_closed():
    cfg = VerifierConfig(recovery_confirm_steps=3, recovery_z_threshold=2.0)
    v = TriSensorVerifier(SENSOR_IDS, cfg)

    # Step 0: S1 blackouts -> quarantined
    v.verify_and_fuse(_make_readings(0, [np.nan, np.nan, np.nan], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]))

    # Steps 1-2: S1 returns valid on the SAME ticks that S3 drops out (len(valid_ids) == 2 branch!).
    # Because S1 is still in recovery probation, it MUST NOT be fused with S2 -> Fail-Closed!
    for k in (1, 2):
        base = np.array([0.2 * k, 0.0, 1.0])
        out = v.verify_and_fuse(_make_readings(k, base, base, [np.nan, np.nan, np.nan]))
        assert out.trusted is False
        assert out.action == "ABSTAIN_SAFE_STOP"
        assert out.display_pos is None
        assert out.control_pos is None
        assert "S1_VIO" not in out.used_sensors
        assert out.quarantined_sensors["S1_VIO"].startswith("RECOVERY_PROBATION")

    # Step 3: S1 completes 3/3 probation against healthy S2 -> now safe to fuse [S1, S2]
    base3 = np.array([0.6, 0.0, 1.0])
    out3 = v.verify_and_fuse(_make_readings(3, base3, base3, [np.nan, np.nan, np.nan]))
    assert out3.trusted is True
    assert out3.used_sensors == ["S1_VIO", "S2_LIDAR"]
    assert out3.display_pos is not None and out3.control_pos is not None


def test_quarantined_sensor_excluded_in_single_fault_isolation_branch_fails_closed():
    cfg = VerifierConfig(recovery_confirm_steps=3, recovery_z_threshold=2.0)
    v = TriSensorVerifier(SENSOR_IDS, cfg)

    # Step 0: S1 blackouts -> quarantined
    v.verify_and_fuse(_make_readings(0, [np.nan, np.nan, np.nan], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]))

    # Steps 1-2: S1 returns clean while S3 suffers sudden bias (+2.0m) -> 3 valid, 2 bad pairs,
    # isolation branch selects candidate_sensors=[S1, S2]. S1 MUST stay in probation -> Fail-Closed!
    for k in (1, 2):
        base = np.array([0.2 * k, 0.0, 1.0])
        out = v.verify_and_fuse(_make_readings(k, base, base, base + np.array([2.0, 0.0, 0.0])))
        assert out.trusted is False
        assert out.action == "ABSTAIN_SAFE_STOP"
        assert out.display_pos is None
        assert out.control_pos is None
        assert "S1_VIO" not in out.used_sensors
        assert out.quarantined_sensors["S1_VIO"].startswith("RECOVERY_PROBATION")

    # Step 3: Probation complete -> S1 + S2 trusted, S3 stays isolated
    base3 = np.array([0.6, 0.0, 1.0])
    out3 = v.verify_and_fuse(_make_readings(3, base3, base3, base3 + np.array([2.0, 0.0, 0.0])))
    assert out3.trusted is True
    assert out3.used_sensors == ["S1_VIO", "S2_LIDAR"]
    assert "S3_UWB" in out3.quarantined_sensors


def test_quarantined_sensor_excluded_in_borderline_single_pair_branch():
    cfg = VerifierConfig(recovery_confirm_steps=3, spike_z_threshold=3.2, recovery_z_threshold=2.0)
    v = TriSensorVerifier(SENSOR_IDS, cfg)

    # Step 0: S1 blackouts -> quarantined
    v.verify_and_fuse(_make_readings(0, [np.nan, np.nan, np.nan], [0.0, 0.0, 1.0], [0.0, 0.0, 1.0]))

    # Step 1: Craft a borderline 1-bad-pair configuration where (S2, S3) is slightly above spike_z_threshold
    # (z_23 > 3.2), while S1 sits midway (z_12 < 3.2 and z_13 < 3.2), so best_pair contains quarantined S1.
    # Because S1 is still in probation, verifier MUST exclude S1 and fail closed!
    p2 = np.array([0.20, 0.0, 1.0])
    p3 = np.array([0.55, 0.0, 1.0])  # ||p3-p2||=0.35 -> z_23 = 0.35 / sqrt(3*(0.035^2+0.045^2)) ~ 3.54 > 3.2
    p1 = np.array([0.36, 0.0, 1.0])  # z_12 ~ 2.01 <= 3.2, z_13 ~ 2.03 <= 3.2 -> exactly 1 bad pair!
    out = v.verify_and_fuse(_make_readings(1, p1, p2, p3))
    assert out.trusted is False
    assert out.display_pos is None
    assert out.control_pos is None
    assert "S1_VIO" not in out.used_sensors


# ---------------------------------------------------------------------------
# Experiment Reliability, Provenance & No-Overwrite Guarantees
# ---------------------------------------------------------------------------
def test_all_abstain_episode_reports_unavailable_rmse_and_counts():
    scen = ExperimentScenario(
        scenario_id="99_TEST_ALL_ABSTAIN",
        fault_category="DUAL_BLACKOUT",
        target_sensor="DUAL_S1_S2",
        description="Permanent dual blackout from step 0 -> 0 estimates available.",
        faults=(
            FaultInjectionSpec(sensor_id="S1_VIO", fault_type=FaultType.SENSOR_BLACKOUT, start_step=0),
            FaultInjectionSpec(sensor_id="S2_LIDAR", fault_type=FaultType.SENSOR_BLACKOUT, start_step=0),
        ),
        fault_start_step=0,
    )
    summary, _, _ = run_single_arm_episode(scen, "TRI_SENSOR_VERIFIER", num_steps=8, base_seed=12345)
    assert summary["estimate_count"] == 0
    assert summary["abstain_steps"] == 8
    assert summary["estimate_count"] + summary["abstain_steps"] == summary["steps"]
    assert summary["position_rmse_m"] == "Unavailable"
    assert summary["fault_window_rmse_m"] == "Unavailable"
    assert summary["max_display_error_m"] == "Unavailable"
    assert summary["simulation_collision_ticks"] == 0


def test_run_full_experiment_refuses_overwrite_and_records_provenance(tmp_path):
    run_dir = run_full_experiment(run_name="test_run_01", num_steps=3, logs_base_dir=tmp_path)
    cfg_path = run_dir / "experiment_config.json"
    summary_path = run_dir / "summary_report.json"

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "planner_provenance" in cfg
    assert cfg["planner_provenance"]["planner_module"] == "aegis.navigation.frontier_exploration"
    assert len(cfg["planner_provenance"]["planner_source_sha256"]) == 64
    assert "git_commit" in cfg["planner_provenance"]
    assert "dependencies" in cfg and "numpy" in cfg["dependencies"]["packages"]
    assert "scenario_seeds" in cfg and len(cfg["scenario_seeds"]) == 20

    report = json.loads(summary_path.read_text(encoding="utf-8"))
    for row in report["summaries"]:
        assert row["estimate_count"] + row["abstain_steps"] == row["steps"]
        assert "simulation_collision_ticks" in row

    # Refusing overwrite preserves existing evidence untouched
    before_bytes = cfg_path.read_bytes()
    with pytest.raises(FileExistsError):
        run_full_experiment(run_name="test_run_01", num_steps=3, logs_base_dir=tmp_path)
    assert cfg_path.read_bytes() == before_bytes

    # Default run_name=None creates a brand-new unique folder without touching test_run_01
    run_dir_auto = run_full_experiment(run_name=None, num_steps=2, logs_base_dir=tmp_path)
    assert run_dir_auto != run_dir
    assert run_dir_auto.exists() and run_dir.exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-v", __file__]))

