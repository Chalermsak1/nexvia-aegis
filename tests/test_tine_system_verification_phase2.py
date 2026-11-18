"""Phase 2 system-wide verification audit for NEXVIA AEGIS (Tine / Pattaradanai Kantamee).

Extends verification to 3D no-oracle ground-truth leakage checks, 3D controller
fail-closed latching and dropout/freeze anomalies, LIVE01 interrupted-step
forensics, and full provenance/multi-batch review reconciliation. Assertions
encode expected verification invariants and are never weakened to force passes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from aegis.development.restart_process_experiment import Records, read_records
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v9.controller_3d import Aegis3DAwareController
from scripts.research import live_recovery_study as study

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = REPO_ROOT / "results" / "research_development" / "review" / "nexvia_recovery_2026-11-17"


class _Trap3DSensorReading(SensorReading):
    """SensorReading subclass that fails if ground-truth fault flags are read online."""

    def __init__(self, estimate: np.ndarray, sigma: float = 0.05, valid: bool = True) -> None:
        self._obs_estimate = np.asarray(estimate, dtype=np.float64)
        self._obs_sigma = float(sigma)
        self._obs_valid = bool(valid)

    @property
    def estimate(self) -> np.ndarray:
        return self._obs_estimate

    @property
    def sigma(self) -> float:
        return self._obs_sigma

    @property
    def valid(self) -> bool:
        return self._obs_valid

    @property
    def bias(self) -> np.ndarray:
        raise AssertionError("Oracle ground-truth .bias accessed in 3D controller")

    @property
    def drift(self) -> np.ndarray:
        raise AssertionError("Oracle ground-truth .drift accessed in 3D controller")

    @property
    def anomaly(self) -> bool:
        raise AssertionError("Oracle ground-truth .anomaly accessed in 3D controller")

    @property
    def dropped(self) -> bool:
        raise AssertionError("Oracle ground-truth .dropped accessed in 3D controller")


# ---------------------------------------------------------------------------
# Duty 2: System-wide No-Oracle Ground-Truth Leakage Audits (3D)
# ---------------------------------------------------------------------------

def test_3d_aware_controller_must_not_read_ground_truth_fault_flags():
    ctrl = Aegis3DAwareController()
    ctrl.reset()
    vec = np.array([1.2, 0.3, 0.4])
    ra = _Trap3DSensorReading(vec, sigma=0.05, valid=True)
    rb = _Trap3DSensorReading(vec, sigma=0.05, valid=True)
    rr = RangeReading(distance=float(np.linalg.norm(vec)), sigma=0.05, valid=True)
    act, dec, _, _ = ctrl.update(ra, rb, rr, None, step=0)
    assert np.all(np.isfinite(act))
    assert dec in ("NAVIGATE", "PROBE", "STOP", "ABSTAIN", "VERIFY")


def test_mujoco_3d_env_step_must_not_pass_simulator_truth_directly_to_cbf():
    """Verifies whether AegisMuJoCo3DEnvironment.step passes exact qpos/qvel into CBF."""
    env = AegisMuJoCo3DEnvironment()
    env.reset(np.random.default_rng(2256000))
    recorded: list[tuple[np.ndarray, np.ndarray]] = []
    orig = env.cbf.compute_safe_control

    def spy(*, pos, vel, desired_u, obstacles, force_braking=False):
        recorded.append((np.asarray(pos).copy(), np.asarray(vel).copy()))
        return orig(pos=pos, vel=vel, desired_u=desired_u, obstacles=obstacles, force_braking=force_braking)

    env.cbf.compute_safe_control = spy  # type: ignore[method-assign]
    true_pos = env.data.xpos[env.robot_body_id].copy()
    true_vel = env.data.qvel[:3].copy()
    env.step(np.array([0.5, 0.0, 0.0]))
    assert recorded, "CBF was not invoked"
    cbf_pos, cbf_vel = recorded[0]
    passed_exact_simulator_truth = np.array_equal(cbf_pos, true_pos) and np.array_equal(cbf_vel, true_vel)
    assert not passed_exact_simulator_truth, (
        "AegisMuJoCo3DEnvironment.step fed exact MuJoCo simulator ground-truth xpos/qvel into CBF"
    )


# ---------------------------------------------------------------------------
# Duty 3: 3D Controller Fail-Closed Latching, Dropout & Freeze Probes
# ---------------------------------------------------------------------------

def test_3d_aware_controller_must_latch_terminal_abstain():
    ctrl = Aegis3DAwareController()
    ctrl.reset()
    bad = SensorReading(estimate=np.array([math.nan, 0.0, 0.0]), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))
    good = SensorReading(estimate=np.array([1.0, 0.0, 0.5]), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))
    rr = RangeReading(distance=math.hypot(1.0, 0.5), sigma=0.05, valid=True)

    _, dec0, _, _ = ctrl.update(bad, good, rr, None, step=0)
    assert dec0 == "ABSTAIN"
    _, dec1, _, _ = ctrl.update(good, good, rr, None, step=1)
    assert dec1 == "ABSTAIN", f"3D controller resumed {dec1} after ABSTAIN instead of latching fail-closed"


def test_3d_aware_controller_must_abstain_on_persistent_range_dropout_in_nominal():
    ctrl = Aegis3DAwareController()
    ctrl.reset()
    vec = np.array([1.5, 0.0, 0.5])
    good = SensorReading(estimate=vec, sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))
    dropped_rr = RangeReading(distance=0.0, sigma=0.05, valid=False, dropped=True)
    decisions = [ctrl.update(good, good, dropped_rr, None, step=s)[1] for s in range(15)]
    assert any(d in ("ABSTAIN", "PROBE") for d in decisions), (
        f"Persistent range dropout in NOMINAL never triggered ABSTAIN/PROBE: {set(decisions)}"
    )


def test_3d_aware_controller_detects_silent_all_channel_freeze():
    ctrl = Aegis3DAwareController()
    ctrl.reset()
    vec = np.array([1.5, 0.0, 0.5])
    rr = RangeReading(distance=float(np.linalg.norm(vec)), sigma=0.05, valid=True)
    decisions = []
    for s in range(60):
        ra = SensorReading(estimate=vec.copy(), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))
        rb = SensorReading(estimate=vec.copy(), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))
        decisions.append(ctrl.update(ra, rb, rr, None, step=s)[1])
    assert any(d in ("ABSTAIN", "PROBE", "VERIFY") for d in decisions)


# ---------------------------------------------------------------------------
# Duty 4: LIVE01 Interrupted Step & Incomplete Journal Forensics
# ---------------------------------------------------------------------------

def test_live01_analyze_case_rejects_unfinished_step_intent_without_step_result(tmp_path: Path):
    cfg = deepcopy(next(a for a in study.plan() if a["id"] == "SIMULATION_CONTRACT_CHECKS_nominal"))
    cfg["steps"] = 20
    original = tmp_path / "nominal"
    study.run_case(cfg, original)

    interrupted = tmp_path / "interrupted"
    shutil.copytree(original, interrupted)
    plant_dir = interrupted / "plant"
    files = sorted(plant_dir.glob("[0-9]" * 8 + ".json"))
    last_intent_idx = max(
        i for i, p in enumerate(files) if json.loads(p.read_bytes())["payload"]["kind"] == "STEP_INTENT"
    )
    for p in files[last_intent_idx + 1 :]:
        p.unlink()

    with pytest.raises(ValueError, match="unfinished physical step"):
        study.analyze_case(interrupted)


def test_live01_read_records_preserves_truncated_pending_file_without_promoting(tmp_path: Path):
    rec = Records(tmp_path / "actor", dict(role="controller", public_sha256="0" * 64, source_sha256={}))
    rec.append("COMMAND_INTENT", command={"command_id": "c0:1"})
    pending = tmp_path / "actor" / "pending_00000002.json"
    partial_bytes = b'{"seq":2,"payload":{"kind":"TRUNC'
    pending.write_bytes(partial_bytes)

    parsed = read_records(tmp_path / "actor")
    assert len(parsed["records"]) == 2
    assert len(parsed["pending"]) == 1
    assert parsed["pending"][0]["name"] == "pending_00000002.json"
    assert parsed["pending"][0]["bytes"] == len(partial_bytes)
    assert parsed["pending"][0]["committed_alias"] is False
    assert pending.read_bytes() == partial_bytes


# ---------------------------------------------------------------------------
# Duty 5 & 6: Full Provenance, 76-File Hash Parity & All-Batch Reconciliation
# ---------------------------------------------------------------------------

def test_review_provenance_sha256_and_sizes_match_all_summary_files():
    prov = json.loads((REVIEW_DIR / "provenance.json").read_bytes())
    assert prov["gate_b"] == "GATE_B_NOT_AUTHORIZED"
    assert prov["release_status"] == "BLOCKED"
    for name, meta in prov["summary_files"].items():
        path = REVIEW_DIR / name
        assert path.exists(), f"Missing provenance file: {name}"
        raw = path.read_bytes()
        assert len(raw) == meta["size_bytes"], f"Size mismatch for {name}"
        assert hashlib.sha256(raw).hexdigest() == meta["sha256"], f"SHA-256 mismatch for {name}"


def test_live01_76_source_hashes_match_main_campaign_audit_byte_for_byte():
    main_audit = json.loads((REVIEW_DIR / "main_campaign_audit.json").read_bytes())
    recorded = main_audit["results"][0]["source_sha256"]
    current = study.hashes()
    assert len(recorded) == 76
    assert current == recorded


def test_all_review_audit_batches_reconcile_with_six_outcomes_csv():
    with (REVIEW_DIR / "six_outcomes.csv").open(newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    # 1. Extended outage batch (6 qualified results)
    ext = json.loads((REVIEW_DIR / "extended_outage_audit.json").read_bytes())
    assert ext["gate_b"] == "GATE_B_NOT_AUTHORIZED" and not ext["incomplete"]
    ext_rows = [r for r in all_rows if r["batch"] == "boundary-long-outage"]
    ext_by_id = {r["assignment"]["id"]: r for r in ext["results"]}
    assert len(ext_rows) == len(ext_by_id) == 6
    for row in ext_rows:
        rec = ext_by_id[row["id"]]
        assert int(row["steps"]) == rec["execution"]["plant_steps"]
        assert int(row["violating_segments"]) == len(rec["trajectory_containment"]["violation_ticks"])
        assert int(row["unresolved_effect_ids"]) == len(rec["uncertain_effects"]["unresolved_ids"])

    # 2. Source-mismatch supplement (1 qualified result)
    sup = json.loads((REVIEW_DIR / "source_mismatch_supplement.json").read_bytes())
    assert sup["gate_b"] == "GATE_B_NOT_AUTHORIZED" and not sup["incomplete"]
    sup_rows = [r for r in all_rows if r["batch"] == "supplement"]
    assert len(sup_rows) == len(sup["results"]) == 1
    assert sup_rows[0]["id"] == sup["results"][0]["assignment"]["id"]
    assert int(sup_rows[0]["violating_segments"]) == len(sup["results"][0]["trajectory_containment"]["violation_ticks"])

    # 3. Higher-speed unqualified batch (6 incomplete assignments, 0 qualified)
    hs = json.loads((REVIEW_DIR / "higher_speed_audit.json").read_bytes())
    assert hs["gate_b"] == "GATE_B_NOT_AUTHORIZED" and len(hs["results"]) == 0
    hs_rows = [r for r in all_rows if r["batch"] == "boundary-higher-speed-unqualified"]
    assert len(hs_rows) == len(hs["incomplete"]) == 6
    assert {r["id"] for r in hs_rows} == {x["assignment"]["id"] for x in hs["incomplete"]}
    assert all(r["injection_qualified"] == "False" for r in hs_rows)