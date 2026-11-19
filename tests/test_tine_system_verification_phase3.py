"""Phase 3 full-system verification audit for NEXVIA AEGIS (Tine / Pattaradanai Kantamee).

Covers secondary modules (RL wrapper, Sim2Real watchdog, Multi-Agent BRMC, AV
Frenet shield), LIVE01 hard-killed plant forensics, cross-frame beacon rollback,
and full row-by-row recovery_phases.csv evidence reconciliation. Assertions encode
expected verification invariants and are never weakened to force passes.
"""

from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

from aegis.av.frenet_cbf_shield import FrenetSafetyShield
from aegis.av.vehicle_dynamics import FrenetState, VehicleState
from aegis.development import live_recovery_contract as contract
from aegis.development.live_recovery_processes import write_beacon
from aegis.development.restart_process_experiment import Endpoint, obs, read_records
from aegis.multiagent.brmc_engine import AgentMessage, ByzantineResilientMartingaleConsensus
from aegis.rl.safe_env_wrapper import Safe6DOFQuadrotorEnv
from aegis.sim2real.mavlink_protocol import FailsafeAction
from aegis.sim2real.safety_watchdog import RealtimeSafetyWatchdog, WatchdogHealthState
from scripts.research import live_recovery_study as study

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = REPO_ROOT / "results" / "research_development" / "review" / "nexvia_recovery_2026-11-17"


# ---------------------------------------------------------------------------
# Duty 2: Secondary-module No-Oracle Ground-Truth Audit (RL Safe Env Wrapper)
# ---------------------------------------------------------------------------

def test_rl_safe_env_shield_must_not_feed_simulator_truth_under_sensor_fault():
    env = Safe6DOFQuadrotorEnv(
        shield_enabled=True,
        enable_innovation_gate=True,
        sensor_fault_config={"start_step": 0, "fault_type": "spoof_arrival"},
    )
    env.reset(rng=np.random.default_rng(71002))
    captured: list[tuple[np.ndarray, np.ndarray]] = []
    orig = env.sim.cbf.filter_safe_force

    def spy(*, pos, vel, desired_force, obstacles, current_tilt, adaptive_gammas=None):
        captured.append((np.asarray(pos).copy(), np.asarray(vel).copy()))
        return orig(
            pos=pos, vel=vel, desired_force=desired_force, obstacles=obstacles,
            current_tilt=current_tilt, adaptive_gammas=adaptive_gammas,
        )

    env.sim.cbf.filter_safe_force = spy  # type: ignore[method-assign]
    st_true = env.sim.get_state()
    env.step(np.zeros(3))
    assert captured, "RL HOCBF shield was not invoked"
    shield_pos, shield_vel = captured[0]
    used_exact_truth = np.array_equal(shield_pos, st_true["pos"]) and np.array_equal(shield_vel, st_true["vel"])
    assert not used_exact_truth, (
        "Safe6DOFQuadrotorEnv passed exact simulator ground-truth pos/vel into HOCBF shield during active sensor spoof"
    )


# ---------------------------------------------------------------------------
# Duty 3 & 4: Secondary-module Safety Anomalies (Sim2Real, Multi-Agent, AV)
# ---------------------------------------------------------------------------

def test_sim2real_watchdog_must_detect_overdue_heartbeat():
    wd = RealtimeSafetyWatchdog()
    wd.record_heartbeat(0.1)
    assert wd.record_odometry(10.0)
    assert wd.record_perception(10.0)
    diag = wd.evaluate_health(now_s=10.0, battery_voltage_v=16.0)
    assert diag.health_state != WatchdogHealthState.HEALTHY_NOMINAL and diag.recommended_action != FailsafeAction.NONE, (
        f"Watchdog ignored 9.9s overdue heartbeat (timeout={wd.config.heartbeat_timeout_s}s): {diag}"
    )


def test_brmc_must_not_propagate_nan_or_suppress_swarm_alarm():
    brmc = ByzantineResilientMartingaleConsensus(num_agents=5, max_byzantine_faults=1, alpha_swarm=0.05)
    msgs = [
        AgentMessage(agent_id=i, step=1, pos_estimate=np.array([1.0, 2.0]), sigma=0.05, martingale_wealth=25.0)
        for i in range(4)
    ] + [
        AgentMessage(agent_id=4, step=1, pos_estimate=np.array([math.nan, math.nan]), sigma=0.05, martingale_wealth=math.nan)
    ]
    res = brmc.aggregate_step(msgs, step=1)
    assert np.all(np.isfinite(res.consensus_position)), f"NaN propagated into consensus_position: {res.consensus_position}"
    assert math.isfinite(res.consensus_martingale_wealth), f"NaN propagated into wealth: {res.consensus_martingale_wealth}"
    assert res.swarm_alarm is True


def test_brmc_must_reject_duplicate_agent_id_sybil_flooding():
    brmc = ByzantineResilientMartingaleConsensus(num_agents=5, max_byzantine_faults=1, alpha_swarm=0.05)
    honest = [
        AgentMessage(agent_id=i, step=1, pos_estimate=np.array([0.0, 0.0]), sigma=0.05, martingale_wealth=1.0)
        for i in range(4)
    ]
    sybil = [
        AgentMessage(agent_id=4, step=1, pos_estimate=np.array([10.0, 0.0]), sigma=0.05, martingale_wealth=1.0)
        for _ in range(2)
    ]
    res = brmc.aggregate_step(honest + sybil, step=1)
    assert float(np.linalg.norm(res.consensus_position)) < 1.0, (
        f"Duplicate agent_id Sybil flood hijacked consensus_position to {res.consensus_position}"
    )


def test_av_frenet_shield_must_reject_nan_nominal_controls():
    shield = FrenetSafetyShield()
    state = VehicleState(x=0.0, y=0.0, yaw=0.0, v_x=15.0, v_y=0.0, yaw_rate=0.0)
    frenet = FrenetState(s=0.0, d=0.0, s_dot=15.0, d_dot=0.0, yaw_rel=0.0, road_curvature=0.0)
    cmd = shield.filter_control(state, frenet, nominal_accel=math.nan, nominal_steering=math.nan)
    assert math.isfinite(cmd.accel_cmd) and math.isfinite(cmd.steering_cmd), (
        f"AV Frenet shield emitted non-finite commands: accel={cmd.accel_cmd}, steer={cmd.steering_cmd}"
    )


# ---------------------------------------------------------------------------
# Duty 4: LIVE01 Hard-Killed Plant Forensics & Cross-Frame Beacon Rollback
# ---------------------------------------------------------------------------

def test_live01_hard_killed_plant_has_no_finished_marker_and_preserves_prefix(tmp_path: Path):
    run_dir = tmp_path / "killed_plant"
    run_dir.mkdir()
    public = study.public_for(
        dict(id="kill-plant", arm="SIMULATION_CONTRACT_CHECKS", steps=40, wall_period=0.03,
             assessment_mode="STATE_TUBE_WINDOW_V1", evidence_backend="ATOMIC_BUNDLE_V1"),
        sources={},
    )
    fault = dict(scenario="nominal", fault_tick=18, initial_velocity=".3")
    contract.save(run_dir / "public.json", public)
    contract.save(run_dir / "fault.json", fault)
    with tempfile.TemporaryDirectory(prefix="nxkill-", dir="/private/tmp") as ipc_str:
        ipc = Path(ipc_str)
        mon = Endpoint(ipc / "m.sock")
        ctrl_ep = Endpoint(ipc / "c0.sock")
        wd_ep = Endpoint(ipc / "w.sock")
        env = dict(os.environ, PYTHONPATH="src:.", PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.Popen(
            [sys.executable, "-m", "aegis.development.live_recovery_processes",
             "plant", str(run_dir / "public.json"), str(ipc), str(run_dir), "--fault", str(run_dir / "fault.json")],
            cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if any(m.get("kind") == "READY" for m in mon.drain()):
                    break
                time.sleep(0.01)
            ctrl_ep.send(ipc / "p.sock", dict(kind="REGISTER_CONTROLLER", generation=0, pid=1001, path=str(ipc / "c0.sock")))
            wd_ep.send(ipc / "p.sock", dict(kind="REGISTER_WATCHDOG", generation=0, pid=1002, path=str(ipc / "w.sock")))
            mon.send(ipc / "p.sock", dict(kind="START"))
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if any(m.get("kind") == "STEP_RESULT" and m.get("tick", -1) >= 2 for m in mon.drain()):
                    break
                time.sleep(0.01)
            proc.kill()
            proc.wait(timeout=2)
        finally:
            mon.close(); ctrl_ep.close(); wd_ep.close()

    parsed = read_records(run_dir / "plant")
    kinds = [r["kind"] for r in parsed["records"]]
    assert "STEP_RESULT" in kinds
    assert "FINISHED" not in kinds


def test_live01_cross_frame_beacon_rollback_must_be_detected(tmp_path: Path):
    root = tmp_path / "rollback"
    root.mkdir()
    public = study.public_for(
        dict(id="rollback", arm="SIMULATION_CONTRACT_CHECKS", steps=80, wall_period=0.03,
             assessment_mode="STATE_TUBE_WINDOW_V1", evidence_backend="ATOMIC_BUNDLE_V1"),
        sources={},
    )

    def make_sample(tick_val: int):
        return dict(
            id=f"sensor-0:{tick_val}", tick=tick_val, remote_time=20 * tick_val + 1000,
            remote_epoch="sensor-0", clock_offset_ms=1000, source_id="SYNTHETIC_MEASURED_CHANNEL",
            frame="WORLD_X_SI", position_center="0", velocity_center=".3",
            emitted_host_ns=1_000_000_000, reported_dynamics_id=public["model"]["dynamics_id"],
            support_valid=True, topology=dict(controller=11, watchdog=12, plant=13), **obs(0, 0.3),
        )

    write_beacon(root, public, 5, "sensor-0")
    t0 = iter([1_000_000_000, 1_010_000_000])
    b0 = contract.assess_frame(root, "watchdog-0/assessments/00000005", make_sample(5), public, "watchdog-0",
                               primary_healthy=True, controller_generation=0, host_clock=lambda: next(t0))
    assert b0["reason"] is None

    # Roll beacon backwards to tick=2 within the same run/epoch
    write_beacon(root, public, 2, "sensor-0")
    t1 = iter([1_020_000_000, 1_030_000_000])
    b1 = contract.assess_frame(root, "watchdog-0/assessments/00000002", make_sample(2), public, "watchdog-0",
                               primary_healthy=True, controller_generation=0, host_clock=lambda: next(t1))
    assert b1["reason"] is not None, "assess_frame accepted a cross-frame beacon rollback from tick=5 to tick=2"


# ---------------------------------------------------------------------------
# Duty 6: Full Row-by-Row recovery_phases.csv Reconciliation (All Batches)
# ---------------------------------------------------------------------------

def test_review_recovery_phases_csv_matches_all_audit_jsons_row_for_row():
    sources = {
        "main": json.loads((REVIEW_DIR / "main_campaign_audit.json").read_bytes()),
        "boundary-long-outage": json.loads((REVIEW_DIR / "extended_outage_audit.json").read_bytes()),
        "supplement": json.loads((REVIEW_DIR / "source_mismatch_supplement.json").read_bytes()),
    }
    lookup = {
        (batch, r["assignment"]["id"]): r["recovery_latency"]
        for batch, data in sources.items()
        for r in data["results"]
    }
    with (REVIEW_DIR / "recovery_phases.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    checked = 0
    for row in rows:
        key = (row["batch"], row["id"])
        if key not in lookup:
            continue
        phase_obj = lookup[key][row["phase"]]
        assert row["status"] == phase_obj["status"]
        exp_ns = "" if phase_obj["host_ns"] is None else str(phase_obj["host_ns"])
        exp_ticks = "" if phase_obj["virtual_ticks"] is None else str(phase_obj["virtual_ticks"])
        assert row["host_nanoseconds_since_fault"] == exp_ns
        assert row["virtual_ticks_since_fault"] == exp_ticks
        checked += 1

    # 27 main + 6 extended_outage + 1 supplement = 34 qualified runs * 7 phases = 238 verified phase rows
    assert checked == 238