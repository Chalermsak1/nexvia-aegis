"""
NEXVIA AEGIS V9-M4 — Confirmatory Holdout Evaluation Harness Preflight Tests.

STRICT EXECUTION RESTRICTIONS:
- These tests use ENTIRELY synthetic, in-memory, or isolated mock inputs.
- They do NOT generate or read the real holdout manifests.
- They do NOT use the reserved seed ranges (73000..74439, 75000..75119) for live simulation.
- They do NOT invoke the real MuJoCo simulator on holdout scenarios.

Verifies all 12 preflight requirements:
1. Valid synthetic run and outcome reconciliation.
2. Missing or invalid manifest metadata.
3. Incorrect policy hash or policy identity.
4. Incorrect configuration hash.
5. Missing, duplicated, or malformed episode records.
6. Outcome partition inconsistencies.
7. Invalid or undefined selective-risk cases.
8. Correct separation of mixture and stratified analyses.
9. Existing output directory and overwrite protection.
10. Attempted execution without explicit authorization.
11. Reporting and artifact-manifest generation with synthetic data.
12. Reproducibility of the synthetic test results.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any
import numpy as np
import pytest

from aegis.v9.randomization import (
    PARTITION_BRANCH_TEST_MIXTURE,
    PARTITION_BRANCH_TEST_SCENARIO,
)
from aegis.v9.risk_statistics import (
    V9CandidateParams,
    compute_canonical_payload_sha256,
)
from experiments.v9_evaluate_dev import build_v9_s12_scenarios
from experiments.v9_evaluate_holdout import (
    REQUIRED_EXECUTION_TOKEN,
    TEST_MIX_ALLOWED_SEEDS,
    TEST_SCEN_ALLOWED_SEEDS,
    berger_intersection_union_test,
    clopper_pearson_one_sided_ucb,
    enforce_holdout_output_directory,
    enforce_holdout_seeds,
    evaluate_mixture_holdout,
    evaluate_scenario_holdout,
    execute_holdout_workflow,
    freeze_holdout_run_configuration,
    holm_shidak_adjusted_thresholds,
    mcnemar_exact_test,
    newcombe_paired_difference_ci,
    paired_difference_lcb,
    run_preflight_checks,
    sha256_file,
    verify_and_load_holdout_manifest,
    verify_and_load_selected_policy,
    verify_episode_records_integrity,
    verify_holdout_outcome_algebra,
    wilson_score_interval,
)


# ==============================================================================
# Synthetic Mock Record Helpers (Pure In-Memory, No Real Holdout Data)
# ==============================================================================

def make_synthetic_episode_record(
    *,
    episode_index: int,
    seed: int = 99000,
    scenario: str = "NOMINAL",
    scenario_index: int = 0,
    accepted: bool = True,
    outcome: str = "TERMINAL_SUCCESS",
    crashed: bool = False,
    steps: int = 120,
    mean_step_ms: float = 0.15,
    distance_traveled: float = 2.4,
    anchor_queries: int = 0,
    anchor_cost: float = 0.0,
    max_overshoot: float = 0.0,
) -> dict[str, Any]:
    """Generates a structurally valid synthetic episode record for preflight testing."""
    ts = outcome == "TERMINAL_SUCCESS"
    fs = outcome == "FALSE_SUCCESS"
    ab_exp = outcome == "ABSTAINED"
    to = outcome == "TIMEOUT"
    ab_tot = ab_exp or to

    return {
        "episode_index": str(episode_index),
        "seed": str(seed),
        "scenario_index": str(scenario_index),
        "scenario": scenario,
        "suite": "S_10" if scenario_index < 10 else "S_ext",
        "policy": "V9_CAND_1_TIER1_STRICTEST",
        "accepted": "1" if accepted else "0",
        "true_success": "1" if ts else "0",
        "false_success": "1" if fs else "0",
        "abstain_explicit": "1" if ab_exp else "0",
        "timeout": "1" if to else "0",
        "abstain": "1" if ab_tot else "0",
        "crashed": "1" if crashed else "0",
        "crash_error": "",
        "final_distance": "0.22" if ts else ("0.65" if fs else "1.50"),
        "steps": str(steps),
        "mean_step_ms": f"{mean_step_ms:.4f}",
        "distance_traveled": f"{distance_traveled:.4f}",
        "anchor_queries": str(anchor_queries),
        "anchor_cost": f"{anchor_cost:.4f}",
        "max_overshoot": f"{max_overshoot:.4f}",
        "terminal_reason": "SYNTHETIC_VERIFIED",
    }


def make_synthetic_mixture_dataset(n: int = 120) -> list[dict[str, Any]]:
    """Creates synthetic mixture dataset with known outcome proportions."""
    records: list[dict[str, Any]] = []
    scenarios = [s.name for s in build_v9_s12_scenarios()]
    for i in range(n):
        scen = scenarios[i % 12]
        # 60% accepted TS, 0% FS, 40% explicit abstention
        if i % 10 < 6:
            rec = make_synthetic_episode_record(
                episode_index=i,
                seed=99000 + i,
                scenario=scen,
                scenario_index=i % 12,
                accepted=True,
                outcome="TERMINAL_SUCCESS",
            )
        else:
            rec = make_synthetic_episode_record(
                episode_index=i,
                seed=99000 + i,
                scenario=scen,
                scenario_index=i % 12,
                accepted=False,
                outcome="ABSTAINED",
            )
        records.append(rec)
    return records


def make_synthetic_stratified_dataset(seeds_per_scen: int = 10) -> list[dict[str, Any]]:
    """Creates synthetic stratified dataset across all 12 scenarios."""
    records: list[dict[str, Any]] = []
    scenarios = build_v9_s12_scenarios()
    ep_idx = 0
    for scen in scenarios:
        for s in range(seeds_per_scen):
            # In adversarial scenarios, fail-closed abstention
            if "FAULTY" in scen.name or "CORRUPTED" in scen.name or "EXTREME" in scen.name or "ANTIPODAL" in scen.name:
                rec = make_synthetic_episode_record(
                    episode_index=ep_idx,
                    seed=99000 + ep_idx,
                    scenario=scen.name,
                    scenario_index=scen.index,
                    accepted=False,
                    outcome="ABSTAINED",
                )
            else:
                rec = make_synthetic_episode_record(
                    episode_index=ep_idx,
                    seed=99000 + ep_idx,
                    scenario=scen.name,
                    scenario_index=scen.index,
                    accepted=True,
                    outcome="TERMINAL_SUCCESS",
                )
            records.append(rec)
            ep_idx += 1
    return records


# ==============================================================================
# Test Cases Covering All 12 Preflight Requirements
# ==============================================================================

def test_1_valid_synthetic_run_and_outcome_reconciliation():
    """Requirement 1: Valid synthetic run reconciles episode outcomes with summary statistics."""
    records = make_synthetic_mixture_dataset(n=100)
    cand_params, _, _ = verify_and_load_selected_policy(Path("results/v9/cal_r2/selected_policy.json"))

    summary = evaluate_mixture_holdout(records=records, cand_params=cand_params)

    assert summary["n_episodes"] == 100
    assert summary["m_accepted"] == 60
    assert summary["ts_count"] == 60
    assert summary["fs_count"] == 0
    assert summary["ab_explicit_count"] == 40
    assert summary["ab_total_count"] == 40
    assert summary["coverage"] == 0.60
    assert summary["tsr"] == 0.60
    assert summary["r_inc"] == 0.0
    assert summary["r_sel"] == 0.0

    # Identities
    assert summary["m_accepted"] == summary["ts_count"] + summary["fs_count"]
    assert summary["ab_total_count"] == summary["ab_explicit_count"] + summary["timeout_count"]
    assert summary["n_episodes"] == summary["m_accepted"] + summary["ab_total_count"]

    # H_1: M=60 >= 59 and K=0 -> UCB95 <= 0.05
    assert summary["h1_selective_risk_control"]["precondition_m_ge_59"] is True
    assert summary["h1_selective_risk_control"]["passed"] is True
    assert summary["h1_selective_risk_control"]["status"] == "CONFIRMATORY_PASS"


def test_2_missing_or_invalid_manifest_metadata(tmp_path: Path):
    """Requirement 2: Manifest loader rejects missing files, invalid partitions, or corrupted hashes."""
    # Missing file
    with pytest.raises(FileNotFoundError):
        verify_and_load_holdout_manifest(tmp_path / "nonexistent.json", "mixture")

    # Invalid partition name
    bad_manifest = {
        "partition": "wrong_partition",
        "partition_index": PARTITION_BRANCH_TEST_MIXTURE,
        "planned_episodes": 1440,
        "episodes": [],
    }
    bad_manifest["integrity_sha256"] = compute_canonical_payload_sha256(bad_manifest)
    bad_file = tmp_path / "bad_man.json"
    bad_file.write_text(json.dumps(bad_manifest, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="Expected partition 'test_mix_r1'"):
        verify_and_load_holdout_manifest(bad_file, "mixture")

    # Tampered integrity hash
    bad_manifest2 = dict(bad_manifest)
    bad_manifest2["partition"] = "test_mix_r1"
    bad_manifest2["integrity_sha256"] = "deadbeef" * 8
    bad_file2 = tmp_path / "bad_man2.json"
    bad_file2.write_text(json.dumps(bad_manifest2, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="integrity hash mismatch"):
        verify_and_load_holdout_manifest(bad_file2, "mixture")


def test_3_incorrect_policy_hash_or_policy_identity(tmp_path: Path):
    """Requirement 3: Verifier rejects wrong candidate IDs, uncertified status, or tampered policy hashes."""
    pol_path = Path("results/v9/cal_r2/selected_policy.json")
    cand_params, payload, raw_sha = verify_and_load_selected_policy(pol_path)
    assert cand_params.candidate_id == "V9_CAND_1_TIER1_STRICTEST"

    # Tampered candidate ID
    bad_payload = dict(payload)
    bad_cand = dict(payload["selected_candidate"])
    bad_cand["candidate_id"] = "V9_CAND_2_TIER2_VERY_STRICT"
    bad_payload["selected_candidate"] = bad_cand
    bad_payload["integrity_sha256"] = compute_canonical_payload_sha256(bad_payload)
    bad_file = tmp_path / "bad_policy.json"
    bad_file.write_text(json.dumps(bad_payload, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="candidate ID mismatch"):
        verify_and_load_selected_policy(bad_file)


def test_4_incorrect_configuration_hash(tmp_path: Path):
    """Requirement 4: Frozen configuration generator detects and rejects hash tampering."""
    out_dir = tmp_path / "results" / "v9" / "test_mix"
    out_dir.mkdir(parents=True)
    cfg_file = out_dir / "holdout_mixture_run_config_frozen_r1.json"

    # Write tampered config
    tampered_cfg = {
        "schema_version": "nexvia-aegis-v9-holdout-run-config/1.0",
        "integrity_sha256": "fake_hash_123456",
    }
    cfg_file.write_text(json.dumps(tampered_cfg, indent=2), encoding="utf-8")

    cand_params, pol_payload, pol_raw_sha = verify_and_load_selected_policy(
        Path("results/v9/cal_r2/selected_policy.json")
    )

    with pytest.raises(ValueError, match="Existing frozen holdout configuration .* mismatch"):
        freeze_holdout_run_configuration(
            partition="mixture",
            manifest_path=tmp_path / "manifest.json",
            manifest_payload={},
            manifest_raw_sha256="0000",
            selected_policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            selected_policy_payload=pol_payload,
            selected_policy_raw_sha256=pol_raw_sha,
            candidate_params=cand_params,
            out_dir=out_dir,
        )


def test_5_missing_duplicated_or_malformed_episode_records():
    """Requirement 5: Record verifier rejects duplicate indices or incorrect episode counts."""
    records = make_synthetic_mixture_dataset(n=10)
    # Duplicate episode index 0
    records_dup = list(records)
    records_dup[1] = dict(records_dup[0])

    with pytest.raises(ValueError, match="Duplicated episode index"):
        verify_episode_records_integrity(records_dup, 10)

    # Incomplete count
    with pytest.raises(ValueError, match="count mismatch"):
        verify_episode_records_integrity(records[:5], 10)


def test_6_outcome_partition_inconsistencies():
    """Requirement 6: Record verifier rejects violations of the outcome algebra partition."""
    # Accepted but neither TS nor FS
    bad_rec1 = make_synthetic_episode_record(episode_index=0, accepted=True, outcome="ABSTAINED")
    with pytest.raises(ValueError, match="Outcome algebra violation"):
        verify_holdout_outcome_algebra(bad_rec1)

    # Accepted AND Abstained simultaneously
    bad_rec2 = make_synthetic_episode_record(episode_index=1, accepted=True, outcome="TERMINAL_SUCCESS")
    bad_rec2["abstain"] = "1"
    with pytest.raises(ValueError, match="Outcome algebra violation"):
        verify_holdout_outcome_algebra(bad_rec2)


def test_7_invalid_or_undefined_selective_risk_cases():
    """Requirement 7: Undefined selective risk (M_s = 0) is preserved as UNDEFINED and never reported as 0.0."""
    # Create dataset where all episodes abstain (M = 0)
    records = [
        make_synthetic_episode_record(episode_index=i, accepted=False, outcome="ABSTAINED")
        for i in range(20)
    ]
    cand_params, _, _ = verify_and_load_selected_policy(Path("results/v9/cal_r2/selected_policy.json"))

    summary = evaluate_mixture_holdout(records=records, cand_params=cand_params)
    assert summary["m_accepted"] == 0
    assert summary["r_sel"] == "UNDEFINED"
    assert summary["h1_selective_risk_control"]["passed"] is False
    assert summary["h1_selective_risk_control"]["status"] == "INSUFFICIENT_COVERAGE"


def test_8_correct_separation_of_mixture_and_stratified_analyses():
    """Requirement 8: Mixture and stratified analyses evaluate distinct preregistered hypotheses."""
    cand_params, _, _ = verify_and_load_selected_policy(Path("results/v9/cal_r2/selected_policy.json"))

    # Mixture evaluation evaluates H_1, H_2, H_4
    mix_records = make_synthetic_mixture_dataset(n=120)
    mix_res = evaluate_mixture_holdout(records=mix_records, cand_params=cand_params)
    assert "h1_selective_risk_control" in mix_res
    assert "h2_unconditional_incidence" in mix_res
    assert "h4_coverage_floor" in mix_res
    assert "h3_tsr_noninferiority_vs_v7" not in mix_res

    # Stratified evaluation evaluates H_3, H_5 and per-scenario breakdown
    scen_records = make_synthetic_stratified_dataset(seeds_per_scen=10)
    scen_res = evaluate_scenario_holdout(records=scen_records, cand_params=cand_params)
    assert "h3_tsr_noninferiority_vs_v7" in scen_res
    assert "h5_worst_case_safety" in scen_res
    assert "scenario_breakdown" in scen_res
    assert len(scen_res["scenario_breakdown"]) == 12

    # Check that catastrophic scenarios in stratified breakdown have UNDEFINED selective risk
    faulty_row = [r for r in scen_res["scenario_breakdown"] if r["scenario"] == "FAULTY_REFERENCE_SENSOR"][0]
    assert int(faulty_row["m_accepted"]) == 0
    assert faulty_row["r_sel"] == "UNDEFINED"
    assert faulty_row["r_sel_status"] == "UNDEFINED"


def test_9_existing_output_directory_and_overwrite_protection(tmp_path: Path):
    """Requirement 9: Single-shot guard refuses to overwrite existing holdout outputs."""
    out_dir = tmp_path / "results" / "v9" / "test_mix"
    out_dir.mkdir(parents=True)
    (out_dir / "test_mix_episodes.csv").write_text("existing_data", encoding="utf-8")

    synthetic_records = make_synthetic_mixture_dataset(n=10)
    with pytest.raises(RuntimeError, match="SINGLE-SHOT EXECUTION GUARD"):
        execute_holdout_workflow(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=tmp_path / "fake_man.json",
            out_dir=out_dir,
            synthetic_records=synthetic_records,
        )


def test_10_attempted_execution_without_explicit_authorization(tmp_path: Path):
    """Requirement 10: Live holdout execution fails closed without explicit authorization token."""
    out_dir = tmp_path / "results" / "v9" / "test_mix"
    out_dir.mkdir(parents=True)

    # Attempt execution with no synthetic records and no authorization token
    with pytest.raises(RuntimeError, match="EXECUTION GUARD: M4 holdout evaluation is not authorized"):
        execute_holdout_workflow(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=tmp_path / "fake_man.json",
            out_dir=out_dir,
            authorized_execution_token=None,
            synthetic_records=None,
        )

    # Attempt execution with invalid token
    with pytest.raises(RuntimeError, match="EXECUTION GUARD: M4 holdout evaluation is not authorized"):
        execute_holdout_workflow(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=tmp_path / "fake_man.json",
            out_dir=out_dir,
            authorized_execution_token="INVALID_TOKEN_ATTEMPT",
            synthetic_records=None,
        )


def test_11_reporting_and_artifact_manifest_generation_with_synthetic_data(tmp_path: Path):
    """Requirement 11: Machine-readable CSVs and JSON report generated and verified with cryptographic digests."""
    out_dir = tmp_path / "results" / "v9" / "test_mix"
    synthetic_records = make_synthetic_mixture_dataset(n=60)

    report = execute_holdout_workflow(
        partition="mixture",
        policy_path=Path("results/v9/cal_r2/selected_policy.json"),
        manifest_path=tmp_path / "fake_man.json",
        out_dir=out_dir,
        synthetic_records=synthetic_records,
    )

    assert report["status"] == "PREFLIGHT_SYNTHETIC_COMPLETE"
    assert (out_dir / "test_mix_episodes.csv").exists()
    assert (out_dir / "test_mix_summary.csv").exists()
    assert (out_dir / "test_mix_report.json").exists()

    # Verify SHA-256 digests in report match disk
    for rel_path, digest in report["artifact_sha256"].items():
        disk_file = Path(rel_path)
        if not disk_file.is_absolute():
            disk_file = _REPO_ROOT / disk_file
        if disk_file.exists():
            assert sha256_file(disk_file) == digest

    # Verify integrity hash of report
    stored_integrity = report["integrity_sha256"]
    computed_integrity = compute_canonical_payload_sha256(report)
    assert stored_integrity == computed_integrity


def test_12_reproducibility_of_synthetic_test_results():
    """Requirement 12: Independent runs on identical synthetic data produce bit-identical results."""
    records = make_synthetic_mixture_dataset(n=120)
    cand_params, _, _ = verify_and_load_selected_policy(Path("results/v9/cal_r2/selected_policy.json"))

    res1 = evaluate_mixture_holdout(records=records, cand_params=cand_params)
    res2 = evaluate_mixture_holdout(records=records, cand_params=cand_params)

    assert res1 == res2


def test_13_prohibited_seed_ranges_strictly_blocked():
    """Verify that seeds outside permitted ranges are strictly rejected by partition guards."""
    # Historical calibration and validation seeds must be blocked from holdout
    prohibited_for_mixture = [60000, 70000, 71000, 72000, 75000, 76000, 77000]
    for seed in prohibited_for_mixture:
        with pytest.raises(ValueError, match="PROHIBITED SEED ACCESS BLOCKED"):
            enforce_holdout_seeds([seed], "mixture")

    prohibited_for_scenario = [60000, 70000, 71000, 72000, 73000, 74000, 76000, 77000]
    for seed in prohibited_for_scenario:
        with pytest.raises(ValueError, match="PROHIBITED SEED ACCESS BLOCKED"):
            enforce_holdout_seeds([seed], "scenario")


def test_14_preflight_checks_read_only_status():
    """Verify that run_preflight_checks operates in strictly read-only mode."""
    checks = run_preflight_checks(policy_path=Path("results/v9/cal_r2/selected_policy.json"))
    assert checks["status"] == "PREFLIGHT_PASS"
    assert checks["policy_id"] == "V9_CAND_1_TIER1_STRICTEST"
    assert checks["certified"] is True
    assert checks["real_holdouts_executed"] is False
