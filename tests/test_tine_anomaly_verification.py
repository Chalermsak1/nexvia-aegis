"""Verification and anomaly-detection suite for NEXVIA AEGIS (Tine / Pattaradanai Kantamee).

Tests no-oracle ground-truth isolation, timestamp/data anomalies, malformed IPC
resilience, cross-artifact integrity, seed reproducibility, and review-evidence
consistency. Assertions reflect expected safety/verification invariants and are
never weakened to force failing checks to pass.
"""

from __future__ import annotations

import csv
import hashlib
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

from aegis.development import live_recovery_contract as contract
from aegis.development.live_recovery_processes import write_beacon
from aegis.development.restart_process_experiment import Endpoint, obs
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from aegis.env.sensors.sensor_corruption_suite import OnlineCovarianceEstimator
from aegis.v3.env.world import AegisPhysicalWorld
from aegis.v3.sensors.cross_modal import RangeReading, RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig, SensorReading
from aegis.v7.anchor_sensor import AnchorSensor, AnchorSensorConfig
from aegis.v9.controller import AegisV9Controller
from aegis.v9.robust_tube_clbf import (
    DwellPhase,
    RobustTubeCLBFConfig,
    RobustTubeCLBFController,
    TubeUncertaintyState,
)
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from scripts.research import live_recovery_study as study

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = REPO_ROOT / "results" / "research_development" / "review" / "nexvia_recovery_2026-11-17"


class _GroundTruthTrapReading:
    """Proxy exposing only observable sensor fields; accessing truth raises AssertionError."""

    def __init__(self, estimate: np.ndarray, sigma: float = 0.05, valid: bool = True) -> None:
        self.estimate = np.asarray(estimate, dtype=np.float64)
        self.sigma = float(sigma)
        self.valid = bool(valid)

    @property
    def bias(self) -> np.ndarray:
        raise AssertionError("Oracle ground-truth .bias accessed")

    @property
    def drift(self) -> np.ndarray:
        raise AssertionError("Oracle ground-truth .drift accessed")

    @property
    def anomaly(self) -> bool:
        raise AssertionError("Oracle ground-truth .anomaly accessed")

    @property
    def dropped(self) -> bool:
        raise AssertionError("Oracle ground-truth .dropped accessed")


def _live01_fixture(tmp_path: Path, *, sample_override: dict | None = None, host_times=(1_000_000_000, 1_010_000_000)):
    root = tmp_path / "run"
    root.mkdir()
    public = study.public_for(
        dict(id="tine-probe", arm="SIMULATION_CONTRACT_CHECKS", steps=80, wall_period=0.03,
             assessment_mode="STATE_TUBE_WINDOW_V1", evidence_backend="ATOMIC_BUNDLE_V1"),
        sources={},
    )
    write_beacon(root, public, 0, "sensor-0")
    sample = dict(
        id="sensor-0:0",
        tick=0,
        remote_time=1000,
        remote_epoch="sensor-0",
        clock_offset_ms=1000,
        source_id="SYNTHETIC_MEASURED_CHANNEL",
        frame="WORLD_X_SI",
        position_center="0",
        velocity_center=".3",
        emitted_host_ns=1_000_000_000,
        reported_dynamics_id=public["model"]["dynamics_id"],
        support_valid=True,
        topology=dict(controller=11, watchdog=12, plant=13),
        **obs(0, 0.3),
    )
    if sample_override:
        sample.update(sample_override)
    times = iter(host_times)
    basis = contract.assess_frame(
        root,
        "watchdog-0/assessments/00000000",
        sample,
        public,
        "watchdog-0",
        primary_healthy=True,
        controller_generation=0,
        host_clock=lambda: next(times),
    )
    return root, public, sample, basis


# ---------------------------------------------------------------------------
# Duty 2: No-oracle isolation under common-mode faults
# ---------------------------------------------------------------------------

def test_v9_controller_common_mode_fault_never_reads_ground_truth():
    ctrl = AegisV9Controller()
    ctrl.reset()
    for step in range(20):
        biased = np.array([1.2 - 0.02 * step, 0.5])
        ra = _GroundTruthTrapReading(biased, sigma=0.05, valid=True)
        rb = _GroundTruthTrapReading(biased, sigma=0.05, valid=True)
        rr = RangeReading(distance=float(np.linalg.norm(biased)), sigma=0.05, valid=True)
        act, dec, _, _ = ctrl.update(ra, rb, rr, None, step=step)  # type: ignore[arg-type]
        assert np.all(np.isfinite(act))
        assert dec in ("ACT", "PROBE", "STOP", "ABSTAIN", "VERIFY")


# ---------------------------------------------------------------------------
# Duty 3: Spoofed timestamps, vacuous bounds, NaN/neg-cov, common-mode freeze
# ---------------------------------------------------------------------------

def test_live01_rejects_future_emitted_host_timestamp(tmp_path: Path):
    _, _, _, basis = _live01_fixture(
        tmp_path,
        sample_override=dict(emitted_host_ns=5_000_000_000),
        host_times=(1_000_000_000, 1_010_000_000),
    )
    assert basis["reason"] is not None
    assert basis["result"] is None or basis["result"]["development_action"] is None


def test_live01_rejects_intra_epoch_clock_offset_forgery(tmp_path: Path):
    _, public, sample0, _ = _live01_fixture(tmp_path)
    forged = dict(sample0, id="sensor-0:1", tick=1, clock_offset_ms=5000, remote_time=5020)
    res = contract.select_samples([sample0, forged], seen=-1, known={}, public=public)
    assert res["critical"] is not None


def test_live01_withholds_vacuous_position_interval_under_fresh_metadata(tmp_path: Path):
    _, _, _, basis = _live01_fixture(
        tmp_path,
        sample_override=dict(position=["-0.49", "0.31"], position_center="0", velocity=["-0.01", "0.01"], velocity_center="0"),
    )
    assert basis["reason"] is not None
    assert basis["result"] is None or basis["result"]["development_action"] is None


def test_robust_tube_clbf_fails_closed_on_nan_state_and_negative_covariance():
    ctrl = RobustTubeCLBFController(RobustTubeCLBFConfig(enable_observability_gate=True))
    bad_nan = TubeUncertaintyState(
        p_hat=np.array([math.nan, 0.0, 0.0]),
        v_hat=np.array([1.0, 0.0, 0.0]),
        cov_p=np.eye(3) * 0.01,
        cov_v=np.eye(3) * 0.01,
    )
    res_nan = ctrl.step(bad_nan, np.array([10.0, 0.0, 0.0]), obstacles=[])
    assert res_nan["phase"] == DwellPhase.EMERGENCY_STOP.value
    assert np.all(np.isfinite(res_nan["action"]))

    ctrl.reset()
    bad_neg = TubeUncertaintyState(
        p_hat=np.array([1.0, 0.0, 0.0]),
        v_hat=np.array([1.0, 0.0, 0.0]),
        cov_p=-np.eye(3),
        cov_v=np.eye(3) * 0.01,
    )
    res_neg = ctrl.step(bad_neg, np.array([10.0, 0.0, 0.0]), obstacles=[])
    assert res_neg["phase"] == DwellPhase.EMERGENCY_STOP.value


def test_v9_controller_detects_silent_all_channel_freeze():
    ctrl = AegisV9Controller()
    ctrl.reset()
    frozen_vec = np.array([1.5, 0.0])
    decisions = []
    for step in range(60):
        ra = SensorReading(estimate=frozen_vec.copy(), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(2), drift=np.zeros(2))
        rb = SensorReading(estimate=frozen_vec.copy(), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(2), drift=np.zeros(2))
        rr = RangeReading(distance=1.5, sigma=0.05, valid=True)
        _, dec, _, _ = ctrl.update(ra, rb, rr, None, step=step)
        decisions.append(dec)
    assert any(d in ("ABSTAIN", "PROBE", "VERIFY") for d in decisions)


def test_online_covariance_estimator_without_oracle_detects_frozen_sensor():
    """Without ground-truth p_true/v_true, an innovation-only estimator fed a frozen reading must flag anomaly."""
    est = OnlineCovarianceEstimator(window_size=10, nominal_sigma_p=0.05, nominal_sigma_v=0.08, blackout_sigma_thresh=0.25)
    p_frozen = np.array([1.5, 0.0, 0.0])
    v_frozen = np.array([0.0, 0.0, 0.0])
    dt = 0.04
    p_pred = p_frozen.copy()
    v_pred = v_frozen.copy()
    triggered = False
    for _ in range(30):
        _, _, is_bo = est.update(p_pred, p_frozen, v_pred, v_frozen)
        triggered |= is_bo
        p_pred = p_frozen + v_frozen * dt
        v_pred = v_frozen.copy()
    assert triggered is True


# ---------------------------------------------------------------------------
# Duty 4: Malformed IPC resilience & cross-artifact evidence mismatch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "role,sock_name,bad_msg",
    [
        ("controller", "c0.sock", {"kind": "STATUS"}),
        ("watchdog", "w.sock", {"kind": "HEARTBEAT"}),
    ],
)
def test_live01_malformed_ipc_datagram_does_not_crash_actor(tmp_path: Path, role: str, sock_name: str, bad_msg: dict):
    run_dir = tmp_path / "case"
    run_dir.mkdir()
    public = study.public_for(
        dict(id=f"ipc-{role}", arm="SIMULATION_CONTRACT_CHECKS", steps=40, wall_period=0.03,
             assessment_mode="STATE_TUBE_WINDOW_V1", evidence_backend="ATOMIC_BUNDLE_V1"),
        sources={},
    )
    public_path = run_dir / "public.json"
    contract.save(public_path, public)
    with tempfile.TemporaryDirectory(prefix="nxtine-", dir="/private/tmp") as ipc_str:
        ipc = Path(ipc_str)
        plant_ep = Endpoint(ipc / "p.sock")
        mon_ep = Endpoint(ipc / "m.sock")
        env = dict(os.environ, PYTHONPATH="src:.", PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.Popen(
            [sys.executable, "-m", "aegis.development.live_recovery_processes",
             role, str(public_path), str(ipc), str(run_dir), "--generation", "0"],
            cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            deadline = time.monotonic() + 5.0
            ready = False
            while time.monotonic() < deadline and not ready:
                if any(m.get("kind") == "READY" and m.get("role") == role for m in mon_ep.drain()):
                    ready = True
                    break
                assert proc.poll() is None, f"{role} exited early: {proc.stdout.read()}"
                time.sleep(0.01)
            assert ready
            plant_ep.send(ipc / sock_name, bad_msg)
            time.sleep(0.05)
            plant_ep.send(ipc / sock_name, {"kind": "STOP", "administrative": True})
            rc = proc.wait(timeout=3)
            out = proc.stdout.read() if proc.stdout else ""
            assert rc == 0, f"{role} crashed on malformed {bad_msg['kind']} (rc={rc}): {out}"
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)
            plant_ep.close()
            mon_ep.close()


def test_live01_cross_artifact_mismatch_rejected_by_audit_frame(tmp_path: Path):
    root, public, _, _ = _live01_fixture(tmp_path)
    art_path = root / "watchdog-0/assessments/00000000/artifacts.json"
    rows = json.loads(art_path.read_bytes())
    rows[0]["observations"] = ["999", "999"]
    art_path.unlink()
    contract.save(art_path, rows)
    with pytest.raises(ValueError, match="witness"):
        study.audit_frame(root, "watchdog-0/assessments/00000000/result.json", public)


# ---------------------------------------------------------------------------
# Duty 5: Seed reproducibility (non-Holdout)
# ---------------------------------------------------------------------------

def test_v9_controller_seed_reproducibility_bit_identical():
    def run_once(seed: int) -> tuple[list[str], str, float]:
        rng_env = np.random.default_rng(seed)
        world = AegisPhysicalWorld()
        world.reset(rng_env)
        sa = FaultInjectableSensor(SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.4, -0.3)))
        sb = FaultInjectableSensor(SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.3, 0.4)))
        sr = RangeSensor(noise_sigma=0.05)
        anc = AnchorSensor(AnchorSensorConfig())
        ctrl = AegisV9Controller()
        ctrl.reset()
        rng_ep = np.random.default_rng(seed)
        query = False
        decisions: list[str] = []
        hasher = hashlib.sha256()
        for _ in range(world.config.max_steps):
            st = world.state()
            td = st["target_pos"] - st["robot_pos"]
            act, dec, _, query = ctrl.update(
                sa.measure(td, rng_ep, step=st["step"]),
                sb.measure(td, rng_ep, step=st["step"]),
                sr.measure(float(st["distance"]), rng_ep),
                anc.measure(td, rng_ep, query=query),
                step=st["step"],
            )
            decisions.append(dec)
            hasher.update(act.tobytes())
            if dec in ("STOP", "ABSTAIN"):
                break
            if world.step(act, rng_ep)["truncated"]:
                break
        dist = float(world.state()["distance"])
        world.close()
        return decisions, hasher.hexdigest(), dist

    assert run_once(71001) == run_once(71001)


def test_3d_mujoco_seed_reproducibility_non_holdout():
    r1 = run_3d_episode(AegisMuJoCo3DEnvironment(), "AEGIS_3D_AWARE_CBF", 2256000, np.zeros(3), max_steps=10)
    r2 = run_3d_episode(AegisMuJoCo3DEnvironment(), "AEGIS_3D_AWARE_CBF", 2256000, np.zeros(3), max_steps=10)
    assert r1 == r2


# ---------------------------------------------------------------------------
# Duty 6: Review evidence consistency (read-only)
# ---------------------------------------------------------------------------

def test_review_six_outcomes_csv_matches_main_campaign_audit_json():
    prov = json.loads((REVIEW_DIR / "provenance.json").read_bytes())
    main_audit = json.loads((REVIEW_DIR / "main_campaign_audit.json").read_bytes())
    assert prov["gate_b"] == main_audit["gate_b"] == "GATE_B_NOT_AUTHORIZED"
    assert prov["release_status"] == "BLOCKED"

    by_id = {r["assignment"]["id"]: r for r in main_audit["results"]}
    with (REVIEW_DIR / "six_outcomes.csv").open(newline="", encoding="utf-8") as f:
        rows = [row for row in csv.DictReader(f) if row["batch"] == "main"]

    assert len(rows) == len(by_id)
    for row in rows:
        rec = by_id[row["id"]]
        assert int(row["steps"]) == rec["execution"]["plant_steps"]
        assert int(row["violating_segments"]) == len(rec["trajectory_containment"]["violation_ticks"])
        assert int(row["unresolved_effect_ids"]) == len(rec["uncertain_effects"]["unresolved_ids"])
        assert int(row["new_consumptions"]) == rec["nominal_control_availability"]["new_consumptions"]
        assert int(row["consumptions_with_false_measurement_premise"]) == len(
            rec["nominal_control_availability"]["consumptions_with_false_measurement_premise"]
        )