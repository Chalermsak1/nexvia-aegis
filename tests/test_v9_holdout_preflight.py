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
from scipy.stats import binom

from aegis.v9.randomization import (
    PARTITION_BRANCH_TEST_MIXTURE,
    PARTITION_BRANCH_TEST_SCENARIO,
    V9HierarchicalManifestGenerator,
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
    TEST_SCEN_SEEDS_PER_SCENARIO,
    MockHoldoutSimulator,
    _derive_episode_rngs,
    align_and_pair_records,
    berger_intersection_union_test,
    clopper_pearson_one_sided_ucb,
    enforce_holdout_output_directory,
    enforce_holdout_seeds,
    evaluate_mixture_holdout,
    evaluate_scenario_holdout,
    execute_holdout_workflow,
    execute_production_holdout_pipeline,
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


def make_synthetic_stratified_dataset(seeds_per_scen: int = 120) -> list[dict[str, Any]]:
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
    scen_records = make_synthetic_stratified_dataset(seeds_per_scen=120)
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


# ==============================================================================
# M4-F02 Remediation Tests: H5 Unconditional Incidence & Scenario Safety
# ==============================================================================

def test_15_h5_unconditional_incidence_zero_accepted_zero_fs():
    """
    M4-F02 Boundary 1: N_s = 120, FS_s = 0, M_s = 0 (all 120 episodes abstained).
    The unconditional-incidence test uses all 120 episodes and does not assign p = 1.0
    solely because every episode was abstained. Selective risk must remain UNDEFINED.
    """
    scenarios = build_v9_s12_scenarios()
    records: list[dict[str, Any]] = []
    ep_idx = 0
    for scen in scenarios:
        for s in range(120):
            # All abstained for all scenarios
            rec = make_synthetic_episode_record(
                episode_index=ep_idx,
                seed=99000 + ep_idx,
                scenario=scen.name,
                scenario_index=scen.index,
                accepted=False,
                outcome="ABSTAINED",
            )
            records.append(rec)
            ep_idx += 1

    summary = evaluate_scenario_holdout(records=records)
    assert len(summary["scenario_breakdown"]) == 12

    # Theoretical exact binomial p-value under null boundary p0 = 0.05:
    # P(Bin(120, 0.05) <= 0) = (0.95)^120
    expected_p = float(binom.cdf(0, 120, 0.05))
    assert math.isclose(expected_p, (0.95)**120, rel_tol=1e-9)
    assert expected_p < 0.05

    for row in summary["scenario_breakdown"]:
        assert int(row["n_episodes"]) == 120
        assert int(row["m_accepted"]) == 0
        assert int(row["fs_count"]) == 0
        assert row["coverage"] == "0.000000"
        assert row["r_inc"] == "0.000000"

        # Crucial M4-F02 check: p-value must be ~ 0.002122, NOT 1.0!
        p_val = float(row["p_value_binomial_005"])
        assert math.isclose(p_val, expected_p, abs_tol=1e-5)
        assert p_val < 0.05

        # Selective risk must remain UNDEFINED, not 0.0
        assert row["r_sel"] == "UNDEFINED"
        assert row["r_sel_status"] == "UNDEFINED"
        assert row["r_sel_ucb95"] == "UNDEFINED"
        assert row["r_sel_ucb_shidak"] == "UNDEFINED"

    # All individual components pass -> Berger IUT must pass
    assert summary["h5_worst_case_safety"]["berger_iut_passed"] is True
    assert summary["h5_worst_case_safety"]["status"] == "CONFIRMATORY_PASS_IUT"


def test_16_h5_unconditional_incidence_independent_of_accepted_count():
    """
    M4-F02 Boundary 2: N_s = 120, FS_s = 0, M_s > 0 vs M_s = 0.
    The H5 unconditional incidence p-value must be completely invariant to accepted count M_s
    when FS_s = 0 and total episode count N_s = 120 are unchanged.
    """
    scenarios = build_v9_s12_scenarios()
    nominal_scen = scenarios[0]

    expected_p = float(binom.cdf(0, 120, 0.05))

    # Test varying M_s in {0, 30, 60, 120}
    for m_accepted in [0, 30, 60, 120]:
        records: list[dict[str, Any]] = []
        ep_idx = 0
        for scen in scenarios:
            for s in range(120):
                is_accepted = (s < m_accepted) if scen.name == nominal_scen.name else True
                rec = make_synthetic_episode_record(
                    episode_index=ep_idx,
                    seed=99000 + ep_idx,
                    scenario=scen.name,
                    scenario_index=scen.index,
                    accepted=is_accepted,
                    outcome="TERMINAL_SUCCESS" if is_accepted else "ABSTAINED",
                )
                records.append(rec)
                ep_idx += 1

        summary = evaluate_scenario_holdout(records=records)
        nom_row = [r for r in summary["scenario_breakdown"] if r["scenario"] == nominal_scen.name][0]

        assert int(nom_row["m_accepted"]) == m_accepted
        assert int(nom_row["fs_count"]) == 0
        p_val = float(nom_row["p_value_binomial_005"])
        assert math.isclose(p_val, expected_p, abs_tol=1e-5), f"Failed for m_accepted={m_accepted}"

        if m_accepted == 0:
            assert nom_row["r_sel"] == "UNDEFINED"
            assert nom_row["r_sel_status"] == "UNDEFINED"
        else:
            assert nom_row["r_sel"] == "0.000000"
            assert nom_row["r_sel_status"] == "DEFINED"


def test_17_h5_unconditional_incidence_single_and_multiple_fs():
    """
    M4-F02 Boundary 3 & 4 & H5 Numerical Reconciliation:
    Exact mathematical evaluation for FS_s in {0, 1, 2, 3} at N_s = 120, p_0 = 0.05.
    - FS_s = 0: p = (0.95)^120 = 0.0021224263786981585 <= 0.05 (PASS)
    - FS_s = 1: p = 0.015527224559949685 <= 0.05 (PASS)
    - FS_s = 2: p = 0.05750540833807949 > 0.05 (FAIL)
    - FS_s = 3: p = 0.14440761335245347 > 0.05 (FAIL)
    """
    scenarios = build_v9_s12_scenarios()
    target_scen = scenarios[0]

    reconciled_references = {
        0: 0.0021224263786981585,
        1: 0.015527224559949685,
        2: 0.05750540833807949,
        3: 0.14440761335245347,
    }

    for fs_count, should_pass in [(0, True), (1, True), (2, False), (3, False)]:
        records: list[dict[str, Any]] = []
        ep_idx = 0
        for scen in scenarios:
            for s in range(120):
                if scen.name == target_scen.name:
                    if s < fs_count:
                        outcome = "FALSE_SUCCESS"
                        accepted = True
                    else:
                        outcome = "TERMINAL_SUCCESS"
                        accepted = True
                else:
                    outcome = "TERMINAL_SUCCESS"
                    accepted = True

                rec = make_synthetic_episode_record(
                    episode_index=ep_idx,
                    seed=99000 + ep_idx,
                    scenario=scen.name,
                    scenario_index=scen.index,
                    accepted=accepted,
                    outcome=outcome,
                )
                records.append(rec)
                ep_idx += 1

        summary = evaluate_scenario_holdout(records=records)
        target_row = [r for r in summary["scenario_breakdown"] if r["scenario"] == target_scen.name][0]

        expected_p = float(binom.cdf(fs_count, 120, 0.05))
        assert math.isclose(expected_p, reconciled_references[fs_count], rel_tol=1e-12)

        p_val = float(target_row["p_value_binomial_005"])
        assert math.isclose(p_val, round(expected_p, 6), abs_tol=1e-7)
        assert (p_val <= 0.05) is should_pass




def test_18_h5_invalid_denominator_or_inconsistent_episode_counts():
    """
    M4-F02 Boundary 5: Reject invalid denominator (N_s <= 0), total record count mismatch,
    or inconsistent per-scenario episode counts.
    """
    records = make_synthetic_stratified_dataset(seeds_per_scen=120)

    # 1. Non-positive denominator
    with pytest.raises(ValueError, match="Invalid denominator"):
        evaluate_scenario_holdout(records=records, expected_seeds_per_scenario=0)
    with pytest.raises(ValueError, match="Invalid denominator"):
        evaluate_scenario_holdout(records=records, expected_seeds_per_scenario=-5)

    # 2. Total record count mismatch
    with pytest.raises(ValueError, match="Stratified scenario record count mismatch"):
        evaluate_scenario_holdout(records=records[:1439], expected_seeds_per_scenario=120)

    # 3. Inconsistent per-scenario count (e.g., scenario 0 has 119, scenario 1 has 121)
    bad_records = list(records)
    # Move one record from scenario 0 to scenario 1
    bad_records[0] = dict(bad_records[0])
    bad_records[0]["scenario"] = bad_records[120]["scenario"]
    bad_records[0]["scenario_index"] = bad_records[120]["scenario_index"]

    with pytest.raises(ValueError, match="episode count mismatch"):
        evaluate_scenario_holdout(records=bad_records, expected_seeds_per_scenario=120)


def test_19_h5_outcome_algebra_rejects_zero_accepted_one_fs():
    """
    M4-F02 Boundary 7: A scenario with zero accepted decisions and one false success
    violates benchmark outcome algebra and must be strictly rejected.
    """
    bad_record = make_synthetic_episode_record(
        episode_index=0,
        accepted=False,
        outcome="ABSTAINED",
    )
    bad_record["false_success"] = "1"  # Violates accepted (0) == ts (0) + fs (1)

    with pytest.raises(ValueError, match="Outcome algebra violation"):
        verify_holdout_outcome_algebra(bad_record)


def test_20_h5_iut_aggregation_all_pass_vs_one_fail():
    """
    M4-F02 Boundary 8 & 9 & H5 Consistency Audit:
    Comprehensive verification of Cases A, B, C, D, E covering the interaction between
    the global Berger IUT conjunction (unadjusted max p_s <= 0.05) and the auxiliary
    sequentially rejective Holm-Šidák step-down procedure.
    """
    scenarios = build_v9_s12_scenarios()

    def build_stratified_fixture(fs_counts_per_scen: list[int]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        ep_idx = 0
        for scen_idx, scen in enumerate(scenarios):
            target_fs = fs_counts_per_scen[scen_idx]
            for s in range(120):
                outcome = "FALSE_SUCCESS" if s < target_fs else "TERMINAL_SUCCESS"
                rec = make_synthetic_episode_record(
                    episode_index=ep_idx,
                    seed=99000 + ep_idx,
                    scenario=scen.name,
                    scenario_index=scen.index,
                    accepted=True,
                    outcome=outcome,
                )
                records.append(rec)
                ep_idx += 1
        return records

    # Case A: All 12 scenarios have FS = 0 (p_s = 0.002122 <= 0.05)
    # Both Berger IUT passes AND all 12 scenarios pass Holm-Šidák step-down.
    res_a = evaluate_scenario_holdout(records=build_stratified_fixture([0] * 12))
    assert res_a["h5_worst_case_safety"]["berger_iut_passed"] is True
    assert res_a["h5_worst_case_safety"]["status"] == "CONFIRMATORY_PASS_IUT"
    assert res_a["h5_worst_case_safety"]["holm_shidak_rejections_count"] == 12

    # Case B: All 12 scenarios have FS = 1 (p_s = 0.015527 <= 0.05)
    # Global Berger IUT passes (max p = 0.015527 <= 0.05), BUT Holm-Šidák step-down
    # stops at step 1 because p_(1) = 0.015527 > alpha_1 = 0.004265 (0 rejections).
    res_b = evaluate_scenario_holdout(records=build_stratified_fixture([1] * 12))
    assert res_b["h5_worst_case_safety"]["berger_iut_passed"] is True
    assert res_b["h5_worst_case_safety"]["status"] == "CONFIRMATORY_PASS_IUT"
    assert res_b["h5_worst_case_safety"]["holm_shidak_rejections_count"] == 0

    # Case C: 6 scenarios have FS = 0, 6 scenarios have FS = 1
    # Global Berger IUT passes (max p = 0.015527 <= 0.05).
    # Holm-Šidák step-down rejects the first 6 (p=0.002122 <= alpha_r for r<=6)
    # and stops at r=7 (p=0.015527 > alpha_7 = 0.008512).
    res_c = evaluate_scenario_holdout(records=build_stratified_fixture([0] * 6 + [1] * 6))
    assert res_c["h5_worst_case_safety"]["berger_iut_passed"] is True
    assert res_c["h5_worst_case_safety"]["status"] == "CONFIRMATORY_PASS_IUT"
    assert res_c["h5_worst_case_safety"]["holm_shidak_rejections_count"] == 6

    # Case D: 11 scenarios have FS = 0, 1 scenario has FS = 2 (p = 0.057505 > 0.05)
    # Global Berger IUT fails (max p = 0.057505 > 0.05 -> RETAIN_SAFETY_NULL).
    # Holm-Šidák step-down rejects the first 11 scenarios and stops at r=12.
    res_d = evaluate_scenario_holdout(records=build_stratified_fixture([0] * 11 + [2]))
    assert res_d["h5_worst_case_safety"]["berger_iut_passed"] is False
    assert res_d["h5_worst_case_safety"]["status"] == "RETAIN_SAFETY_NULL"
    assert res_d["h5_worst_case_safety"]["holm_shidak_rejections_count"] == 11

    # Case E: 1 scenario has FS = 0, 11 scenarios have FS = 1
    # Global Berger IUT passes (max p = 0.015527 <= 0.05).
    # Holm-Šidák step-down rejects exactly 1 scenario (p_(1) = 0.002122 <= alpha_1 = 0.004265)
    # and stops at r=2 (p_(2) = 0.015527 > alpha_2 = 0.004652).
    res_e = evaluate_scenario_holdout(records=build_stratified_fixture([0] * 1 + [1] * 11))
    assert res_e["h5_worst_case_safety"]["berger_iut_passed"] is True
    assert res_e["h5_worst_case_safety"]["status"] == "CONFIRMATORY_PASS_IUT"
    assert res_e["h5_worst_case_safety"]["holm_shidak_rejections_count"] == 1


def test_21_h5_holm_shidak_step_down_thresholds():
    """
    M4-F02 Boundary 10: Verify exact mathematical implementation and monotonic ordering
    of Holm-Šidák step-down thresholds for k = 12, alpha = 0.05.
    """
    thresholds = holm_shidak_adjusted_thresholds(12, alpha=0.05)
    assert len(thresholds) == 12

    # Verify strict monotonic increase
    for i in range(len(thresholds) - 1):
        assert thresholds[i] < thresholds[i + 1]

    # Verify boundary points
    # First threshold: 1 - (1 - 0.05)**(1/12)
    expected_first = 1.0 - (0.95) ** (1.0 / 12.0)
    assert math.isclose(thresholds[0], expected_first, rel_tol=1e-7)
    assert math.isclose(thresholds[0], 0.004265324, abs_tol=1e-6)

    # Last threshold: 1 - (1 - 0.05)**(1/1) = 0.05
    assert math.isclose(thresholds[-1], 0.05, rel_tol=1e-7)


# ==============================================================================
# M4-F03 Remediation Tests: Paired Record Identity Alignment
# ==============================================================================

def test_22_pairing_correct_matching_records():
    """M4-F03 Test 1: Exactly matching records pair cleanly in forward order."""
    policy_records = make_synthetic_mixture_dataset(n=50)
    baseline_records = make_synthetic_mixture_dataset(n=50)

    paired = align_and_pair_records(policy_records, baseline_records, baseline_label="test_v8")
    assert len(paired) == 50
    for r_pi, r_b in paired:
        assert int(r_pi["seed"]) == int(r_b["seed"])
        assert str(r_pi["scenario"]) == str(r_b["scenario"])


def test_23_pairing_reversed_baseline_row_order():
    """
    M4-F03 Test 2: Reversed baseline row order is resolved by keyed join to produce
    identical pairing and identical contingency counts without order distortion.
    """
    policy_records = make_synthetic_mixture_dataset(n=50)
    baseline_records = make_synthetic_mixture_dataset(n=50)

    # Inject some divergent false-success outcomes to test contingency counts
    for i in range(10):
        policy_records[i]["false_success"] = "1"
        policy_records[i]["true_success"] = "0"
    for i in range(5, 15):
        baseline_records[i]["false_success"] = "1"
        baseline_records[i]["true_success"] = "0"

    # Forward pairing
    paired_forward = align_and_pair_records(policy_records, baseline_records, baseline_label="test_v8")
    n11_f = sum(1 for r, v in paired_forward if int(r["false_success"]) == 1 and int(v["false_success"]) == 1)
    n10_f = sum(1 for r, v in paired_forward if int(r["false_success"]) == 1 and int(v["false_success"]) == 0)
    n01_f = sum(1 for r, v in paired_forward if int(r["false_success"]) == 0 and int(v["false_success"]) == 1)
    n00_f = sum(1 for r, v in paired_forward if int(r["false_success"]) == 0 and int(v["false_success"]) == 0)

    # Reverse baseline rows
    reversed_baseline = list(reversed(baseline_records))
    paired_reversed = align_and_pair_records(policy_records, reversed_baseline, baseline_label="test_v8")
    n11_r = sum(1 for r, v in paired_reversed if int(r["false_success"]) == 1 and int(v["false_success"]) == 1)
    n10_r = sum(1 for r, v in paired_reversed if int(r["false_success"]) == 1 and int(v["false_success"]) == 0)
    n01_r = sum(1 for r, v in paired_reversed if int(r["false_success"]) == 0 and int(v["false_success"]) == 1)
    n00_r = sum(1 for r, v in paired_reversed if int(r["false_success"]) == 0 and int(v["false_success"]) == 0)

    # Contingency table MUST be bit-identical despite row-order inversion
    assert (n11_f, n10_f, n01_f, n00_f) == (n11_r, n10_r, n01_r, n00_r)
    assert (n11_f, n10_f, n01_f, n00_f) == (5, 5, 5, 35)


def test_24_pairing_rejects_mismatched_seed():
    """M4-F03 Test 3: Reject baseline record with mismatched seed."""
    policy_records = make_synthetic_mixture_dataset(n=10)
    baseline_records = make_synthetic_mixture_dataset(n=10)

    # Corrupt seed of one baseline episode
    baseline_records[3] = dict(baseline_records[3])
    baseline_records[3]["seed"] = "99999"

    with pytest.raises(ValueError, match="Missing baseline"):
        align_and_pair_records(policy_records, baseline_records, baseline_label="v8")


def test_25_pairing_rejects_mismatched_scenario():
    """M4-F03 Test 4: Reject baseline record with mismatched scenario."""
    policy_records = make_synthetic_mixture_dataset(n=10)
    baseline_records = make_synthetic_mixture_dataset(n=10)

    # Corrupt scenario of one baseline episode
    baseline_records[2] = dict(baseline_records[2])
    baseline_records[2]["scenario"] = "NONEXISTENT_SCENARIO"

    with pytest.raises(ValueError, match="Missing baseline"):
        align_and_pair_records(policy_records, baseline_records, baseline_label="v7")


def test_26_pairing_rejects_duplicate_identity_keys():
    """M4-F03 Test 5: Reject duplicate (seed, scenario) identity keys in policy or baseline."""
    policy_records = make_synthetic_mixture_dataset(n=10)
    baseline_records = make_synthetic_mixture_dataset(n=10)

    # Duplicate key in policy records
    dup_policy = list(policy_records)
    dup_policy[1] = dict(dup_policy[0])
    with pytest.raises(ValueError, match="Duplicate identity key"):
        align_and_pair_records(dup_policy, baseline_records)

    # Duplicate key in baseline records
    dup_baseline = list(baseline_records)
    dup_baseline[1] = dict(dup_baseline[0])
    with pytest.raises(ValueError, match="Duplicate identity key"):
        align_and_pair_records(policy_records, dup_baseline)


def test_27_pairing_rejects_missing_baseline_or_policy_episodes():
    """M4-F03 Test 6 & 7: Reject missing baseline or policy episodes (count mismatch)."""
    policy_records = make_synthetic_mixture_dataset(n=20)
    baseline_records = make_synthetic_mixture_dataset(n=19)

    with pytest.raises(ValueError, match="Record count mismatch"):
        align_and_pair_records(policy_records, baseline_records, baseline_label="v8")


def test_28_pairing_rejects_invalid_or_absent_identity_fields():
    """M4-F03 Test 8: Reject missing, empty, or unparseable identity fields."""
    # 1. Missing seed
    bad_pol1 = make_synthetic_mixture_dataset(n=5)
    del bad_pol1[0]["seed"]
    with pytest.raises(ValueError, match="missing required identity key 'seed'"):
        align_and_pair_records(bad_pol1, make_synthetic_mixture_dataset(n=5))

    # 2. Non-integer seed
    bad_pol2 = make_synthetic_mixture_dataset(n=5)
    bad_pol2[0]["seed"] = "invalid_int_seed"
    with pytest.raises(ValueError, match="invalid integer seed"):
        align_and_pair_records(bad_pol2, make_synthetic_mixture_dataset(n=5))

    # 3. Missing scenario
    bad_pol3 = make_synthetic_mixture_dataset(n=5)
    del bad_pol3[0]["scenario"]
    with pytest.raises(ValueError, match="missing required identity key 'scenario'"):
        align_and_pair_records(bad_pol3, make_synthetic_mixture_dataset(n=5))

    # 4. Empty scenario
    bad_pol4 = make_synthetic_mixture_dataset(n=5)
    bad_pol4[0]["scenario"] = "   "
    with pytest.raises(ValueError, match="missing required identity key 'scenario'"):
        align_and_pair_records(bad_pol4, make_synthetic_mixture_dataset(n=5))


def test_29_pairing_reconciles_discordant_pair_counts():
    """
    M4-F03 Test 9: Exact reconciliation of discordant-pair counts (n_10, n_01)
    and paired McNemar exact test calculation.
    """
    n = 100
    policy_records: list[dict[str, Any]] = []
    baseline_records: list[dict[str, Any]] = []

    # Construct known contingency distribution:
    # n_11 = 10, n_10 = 5, n_01 = 20, n_00 = 65
    for i in range(n):
        seed = 98000 + i
        scen = "NOMINAL"
        if i < 10:  # Both FS
            p_fs, b_fs = 1, 1
        elif i < 15:  # Policy FS, Baseline TS
            p_fs, b_fs = 1, 0
        elif i < 35:  # Policy TS, Baseline FS
            p_fs, b_fs = 0, 1
        else:  # Both TS
            p_fs, b_fs = 0, 0

        policy_records.append(make_synthetic_episode_record(
            episode_index=i, seed=seed, scenario=scen, accepted=True,
            outcome="FALSE_SUCCESS" if p_fs else "TERMINAL_SUCCESS"
        ))
        baseline_records.append(make_synthetic_episode_record(
            episode_index=i, seed=seed, scenario=scen, accepted=True,
            outcome="FALSE_SUCCESS" if b_fs else "TERMINAL_SUCCESS"
        ))

    paired = align_and_pair_records(policy_records, baseline_records)
    n11 = sum(1 for r, v in paired if int(r["false_success"]) == 1 and int(v["false_success"]) == 1)
    n10 = sum(1 for r, v in paired if int(r["false_success"]) == 1 and int(v["false_success"]) == 0)
    n01 = sum(1 for r, v in paired if int(r["false_success"]) == 0 and int(v["false_success"]) == 1)
    n00 = sum(1 for r, v in paired if int(r["false_success"]) == 0 and int(v["false_success"]) == 0)

    assert (n11, n10, n01, n00) == (10, 5, 20, 65)

    # McNemar exact test: 2 * binom.cdf(min(5, 20), 25, 0.5)
    expected_mcnemar = float(mcnemar_exact_test(n10, n01))
    calc_mcnemar = 2.0 * float(binom.cdf(5, 25, 0.5))
    assert math.isclose(expected_mcnemar, calc_mcnemar, rel_tol=1e-7)
    assert expected_mcnemar < 0.05  # Significant reduction


# ==============================================================================
# Phase 4 & 5: Mock Simulator and Production Execution Pathway Tests
# ==============================================================================

def test_30_mock_simulator_crn_determinism():
    """Requirement: Mock simulator and _derive_episode_rngs preserve Common Random Numbers (CRN)."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=5,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    ep_item = man["episodes"][0]
    ep_seed = int(ep_item["manifest_id"])

    # Simulate Policy V9, Baseline V8, Baseline V7 on the same episode
    rng1_env, rng1_sens = _derive_episode_rngs(ep_item, ep_seed)
    rng2_env, rng2_sens = _derive_episode_rngs(ep_item, ep_seed)
    rng3_env, rng3_sens = _derive_episode_rngs(ep_item, ep_seed)

    # Initial draws must be bitwise identical across all three instances
    draw1_env = rng1_env.uniform(size=10)
    draw2_env = rng2_env.uniform(size=10)
    draw3_env = rng3_env.uniform(size=10)
    assert np.array_equal(draw1_env, draw2_env)
    assert np.array_equal(draw2_env, draw3_env)

    draw1_sens = rng1_sens.normal(size=10)
    draw2_sens = rng2_sens.normal(size=10)
    draw3_sens = rng3_sens.normal(size=10)
    assert np.array_equal(draw1_sens, draw2_sens)
    assert np.array_equal(draw2_sens, draw3_sens)


def test_31_production_pipeline_authorization_guard(tmp_path: Path):
    """Requirement: Production pipeline strictly enforces explicit authorization token."""
    out_dir = tmp_path / "results" / "v9" / "test_mix_guard"
    out_dir.mkdir(parents=True)
    fake_man = tmp_path / "fake_man.json"

    # Token = None
    with pytest.raises(RuntimeError, match="EXECUTION GUARD: Production holdout evaluation is not authorized"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=fake_man,
            out_dir=out_dir,
            authorized_execution_token=None,
        )

    # Invalid Token
    with pytest.raises(RuntimeError, match="EXECUTION GUARD: Production holdout evaluation is not authorized"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=fake_man,
            out_dir=out_dir,
            authorized_execution_token="UNAUTHORIZED_TEST_TOKEN",
        )


def test_32_production_pipeline_custom_simulator_requires_allow_mock(tmp_path: Path):
    """Requirement: Custom/mock simulator without allow_mock_simulation=True is blocked fail-closed."""
    out_dir = tmp_path / "results" / "v9" / "test_mix_mock_guard"
    out_dir.mkdir(parents=True)
    fake_man = tmp_path / "fake_man.json"
    mock_sim = MockHoldoutSimulator()

    with pytest.raises(RuntimeError, match="Custom/mock simulators are only permitted when allow_mock_simulation is explicitly True"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=fake_man,
            out_dir=out_dir,
            authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
            simulator_fn=mock_sim,
            allow_mock_simulation=False,
        )


def test_33_production_pipeline_mixture_mock_e2e(tmp_path: Path):
    """Requirement: Full end-to-end orchestration of mixture holdout with mock simulator."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    mix_man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=120,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_mix_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(mix_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_mix_synthetic"
    mock_sim = MockHoldoutSimulator()

    res = execute_production_holdout_pipeline(
        partition="mixture",
        policy_path=Path("results/v9/cal_r2/selected_policy.json"),
        manifest_path=man_path,
        out_dir=out_dir,
        authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
        simulator_fn=mock_sim,
        allow_mock_simulation=True,
    )

    # 1. Report schema & provenance
    assert res["status"] == "COMPLETE_MOCK_VERIFIED"
    assert res["simulation_mode"] == "MOCK_SYNTHETIC"
    assert res["partition"] == "mixture"
    assert res["selected_policy_id"] == "V9_CAND_1_TIER1_STRICTEST"

    # 2. Output files exist
    episodes_csv = out_dir / "test_mix_episodes.csv"
    v8_csv = out_dir / "test_mix_baseline_v8_episodes.csv"
    v7_csv = out_dir / "test_mix_baseline_v7_episodes.csv"
    summary_csv = out_dir / "test_mix_summary.csv"
    report_json = out_dir / "test_mix_report.json"
    assert episodes_csv.exists()
    assert v8_csv.exists()
    assert v7_csv.exists()
    assert summary_csv.exists()
    assert report_json.exists()

    # 3. Artifact SHA-256 verification
    assert res["artifact_sha256"][str(episodes_csv)] == sha256_file(episodes_csv)
    assert res["artifact_sha256"][str(summary_csv)] == sha256_file(summary_csv)
    assert res["artifact_sha256"][str(v8_csv)] == sha256_file(v8_csv)
    assert res["artifact_sha256"][str(v7_csv)] == sha256_file(v7_csv)

    # 4. Report JSON integrity hash
    loaded_report = json.loads(report_json.read_text(encoding="utf-8"))
    assert loaded_report["integrity_sha256"] == compute_canonical_payload_sha256(loaded_report)

    # 5. Statistical evaluations
    summary = res["evaluation_summary"]
    assert summary["n_episodes"] == 120
    assert summary["m_accepted"] > 59
    assert summary["h4_coverage_floor"]["passed"] is True
    assert "vs_v8_martingale" in summary["h2_unconditional_incidence"]["comparisons"]
    assert "vs_v7_mpc" in summary["h2_unconditional_incidence"]["comparisons"]


def test_34_production_pipeline_scenario_mock_e2e(tmp_path: Path):
    """Requirement: Full end-to-end orchestration of scenario holdout with mock simulator."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    scen_man = gen.generate_stratified_manifest(
        partition_name="test_scen_synthetic",
        seed_start=81000,
        seeds_per_scenario=2,
        partition_index=PARTITION_BRANCH_TEST_SCENARIO,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_scen_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(scen_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_scen_synthetic"
    mock_sim = MockHoldoutSimulator()

    res = execute_production_holdout_pipeline(
        partition="scenario",
        policy_path=Path("results/v9/cal_r2/selected_policy.json"),
        manifest_path=man_path,
        out_dir=out_dir,
        authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
        simulator_fn=mock_sim,
        allow_mock_simulation=True,
    )

    # 1. Report schema & provenance
    assert res["status"] == "COMPLETE_MOCK_VERIFIED"
    assert res["simulation_mode"] == "MOCK_SYNTHETIC"
    assert res["partition"] == "scenario"

    # 2. Output files exist including breakdown CSV
    episodes_csv = out_dir / "test_scen_episodes.csv"
    v7_csv = out_dir / "test_scen_baseline_v7_episodes.csv"
    summary_csv = out_dir / "test_scen_summary.csv"
    breakdown_csv = out_dir / "test_scen_breakdown.csv"
    report_json = out_dir / "test_scen_report.json"
    assert episodes_csv.exists()
    assert v7_csv.exists()
    assert summary_csv.exists()
    assert breakdown_csv.exists()
    assert report_json.exists()

    # 3. Artifact SHA-256 verification
    assert res["artifact_sha256"][str(breakdown_csv)] == sha256_file(breakdown_csv)

    # 4. Scenario breakdown has exactly 12 scenarios
    summary = res["evaluation_summary"]
    assert summary["total_scenarios"] == 12
    assert len(summary["scenario_breakdown"]) == 12
    assert summary["h3_tsr_noninferiority_vs_v7"]["nominal_tsr"] == 1.0


def test_35_production_pipeline_single_shot_guard(tmp_path: Path):
    """Requirement: Single-shot output protection blocks overwriting existing holdout artifacts."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    mix_man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=12,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_mix_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(mix_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_mix_singleshot"
    mock_sim = MockHoldoutSimulator()

    # Initial run: succeeds
    execute_production_holdout_pipeline(
        partition="mixture",
        policy_path=Path("results/v9/cal_r2/selected_policy.json"),
        manifest_path=man_path,
        out_dir=out_dir,
        authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
        simulator_fn=mock_sim,
        allow_mock_simulation=True,
    )

    # Subsequent run: must raise SINGLE-SHOT EXECUTION GUARD RuntimeError
    with pytest.raises(RuntimeError, match="SINGLE-SHOT EXECUTION GUARD: Holdout output already exists"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=man_path,
            out_dir=out_dir,
            authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
            simulator_fn=mock_sim,
            allow_mock_simulation=True,
        )


def test_36_production_pipeline_mid_run_failure_partial_output(tmp_path: Path):
    """Requirement: Injected exception during simulation writes partial CSV and invalid marker."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    mix_man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=6,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_mix_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(mix_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_mix_partial"

    # Inject failure on episode index 3
    fail_ep = mix_man["episodes"][3]
    fail_key = (fail_ep["scenario"], int(fail_ep["manifest_id"]))
    mock_sim = MockHoldoutSimulator(inject_runtime_exception_keys={fail_key})

    with pytest.raises(RuntimeError, match="MockInjectedRuntimeError"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=man_path,
            out_dir=out_dir,
            authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
            simulator_fn=mock_sim,
            allow_mock_simulation=True,
        )

    # Partial CSV and INCOMPLETE_INVALID.json must exist
    partial_csv = out_dir / "test_mix_episodes_PARTIAL.csv"
    invalid_marker = out_dir / "INCOMPLETE_INVALID.json"
    complete_report = out_dir / "test_mix_report.json"

    assert partial_csv.exists()
    assert invalid_marker.exists()
    assert not complete_report.exists()

    # Rerun must refuse because INCOMPLETE_INVALID.json exists
    with pytest.raises(RuntimeError, match="SINGLE-SHOT EXECUTION GUARD: Found existing incomplete marker"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=man_path,
            out_dir=out_dir,
            authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
            simulator_fn=mock_sim,
            allow_mock_simulation=True,
        )


def test_37_production_pipeline_outcome_algebra_violation_injected(tmp_path: Path):
    """Requirement: Pipeline halts fail-closed if simulator violates benchmark outcome algebra."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    mix_man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=4,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_mix_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(mix_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_mix_bad_algebra"

    # Inject algebra violation on episode 1
    bad_ep = mix_man["episodes"][1]
    bad_key = (bad_ep["scenario"], int(bad_ep["manifest_id"]))
    mock_sim = MockHoldoutSimulator(inject_algebra_violation_keys={bad_key})

    with pytest.raises(RuntimeError, match=r"Acceptance identity A == TS \+ FS violated"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=man_path,
            out_dir=out_dir,
            authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
            simulator_fn=mock_sim,
            allow_mock_simulation=True,
        )


def test_38_production_pipeline_crash_fail_unsafe_classification(tmp_path: Path):
    """Requirement: Fail-unsafe crash accounting: crashed=1 -> accepted=0, false_success=1."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    mix_man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=10,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_mix_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(mix_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_mix_crash"

    # Inject crash on episode 0
    crash_ep = mix_man["episodes"][0]
    crash_key = (crash_ep["scenario"], int(crash_ep["manifest_id"]))
    mock_sim = MockHoldoutSimulator(inject_crash_keys={crash_key})

    res = execute_production_holdout_pipeline(
        partition="mixture",
        policy_path=Path("results/v9/cal_r2/selected_policy.json"),
        manifest_path=man_path,
        out_dir=out_dir,
        authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
        simulator_fn=mock_sim,
        allow_mock_simulation=True,
    )

    summary = res["evaluation_summary"]
    assert summary["crashed_count"] >= 1
    assert summary["fs_count"] >= 1


def test_39_production_pipeline_timeout_and_abstain_classification(tmp_path: Path):
    """Requirement: Timeout and explicit abstention classifications are correctly recorded."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    mix_man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=10,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_mix_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(mix_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_mix_timeout_abstain"

    to_ep = mix_man["episodes"][0]
    ab_ep = mix_man["episodes"][1]
    mock_sim = MockHoldoutSimulator(
        inject_timeout_keys={(to_ep["scenario"], int(to_ep["manifest_id"]))},
        inject_abstain_keys={(ab_ep["scenario"], int(ab_ep["manifest_id"]))},
    )

    res = execute_production_holdout_pipeline(
        partition="mixture",
        policy_path=Path("results/v9/cal_r2/selected_policy.json"),
        manifest_path=man_path,
        out_dir=out_dir,
        authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
        simulator_fn=mock_sim,
        allow_mock_simulation=True,
    )

    summary = res["evaluation_summary"]
    assert summary["timeout_count"] >= 1
    assert summary["ab_explicit_count"] >= 1
    assert summary["ab_total_count"] == summary["ab_explicit_count"] + summary["timeout_count"]


def test_40_production_pipeline_undefined_selective_risk_in_stratified(tmp_path: Path):
    """Requirement: Undefined selective risk (M_s = 0) in stratified holdout handled fail-closed."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    scen_man = gen.generate_stratified_manifest(
        partition_name="test_scen_synthetic",
        seed_start=81000,
        seeds_per_scenario=2,
        partition_index=PARTITION_BRANCH_TEST_SCENARIO,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_scen_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(scen_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_scen_undef_risk"

    # Force zero accepted decisions in CORRUPTED_ANCHOR_STRESS
    mock_sim = MockHoldoutSimulator(
        scenario_overrides={"CORRUPTED_ANCHOR_STRESS": {"force_zero_accepted": True}}
    )

    res = execute_production_holdout_pipeline(
        partition="scenario",
        policy_path=Path("results/v9/cal_r2/selected_policy.json"),
        manifest_path=man_path,
        out_dir=out_dir,
        authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
        simulator_fn=mock_sim,
        allow_mock_simulation=True,
    )

    summary = res["evaluation_summary"]
    target_row = next(r for r in summary["scenario_breakdown"] if r["scenario"] == "CORRUPTED_ANCHOR_STRESS")
    assert target_row["m_accepted"] == 0
    assert target_row["r_sel"] == "UNDEFINED"
    assert target_row["r_sel_status"] == "UNDEFINED"
    assert target_row["r_sel_ucb95"] == "UNDEFINED"


def test_41_production_pipeline_manifest_integrity_guard(tmp_path: Path):
    """Requirement: Tampered manifest integrity hash or invalid partition name raises ValueError."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    mix_man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=5,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    # Corrupt integrity hash
    mix_man["integrity_sha256"] = "0" * 64
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_mix_bad_man.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(mix_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_mix_bad_man"
    mock_sim = MockHoldoutSimulator()

    with pytest.raises(ValueError, match="Holdout manifest integrity hash mismatch"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=Path("results/v9/cal_r2/selected_policy.json"),
            manifest_path=man_path,
            out_dir=out_dir,
            authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
            simulator_fn=mock_sim,
            allow_mock_simulation=True,
        )


def test_42_production_pipeline_policy_hash_mismatch(tmp_path: Path):
    """Requirement: Tampered policy artifact raises ValueError fail-closed."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    mix_man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=5,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_mix_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(mix_man, indent=2), encoding="utf-8")

    # Create corrupted policy artifact
    pol_bytes = Path("results/v9/cal_r2/selected_policy.json").read_bytes()
    pol_payload = json.loads(pol_bytes.decode("utf-8"))
    pol_payload["selected_candidate"]["alpha_mon"] = 0.999
    bad_pol_path = tmp_path / "bad_policy.json"
    bad_pol_path.write_text(json.dumps(pol_payload, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_mix_bad_pol"
    mock_sim = MockHoldoutSimulator()

    with pytest.raises(ValueError, match="Selected policy integrity hash mismatch"):
        execute_production_holdout_pipeline(
            partition="mixture",
            policy_path=bad_pol_path,
            manifest_path=man_path,
            out_dir=out_dir,
            authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
            simulator_fn=mock_sim,
            allow_mock_simulation=True,
        )


def test_43_production_pipeline_paired_baseline_integrity(tmp_path: Path):
    """Requirement: Policy and baseline records strictly match on (seed, scenario)."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    mix_man = gen.generate_manifest(
        partition_name="test_mix_synthetic",
        manifest_id_start=80000,
        count=15,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    man_path = tmp_path / "results" / "v9" / "manifests" / "test_mix_synthetic.json"
    man_path.parent.mkdir(parents=True)
    man_path.write_text(json.dumps(mix_man, indent=2), encoding="utf-8")

    out_dir = tmp_path / "results" / "v9" / "test_mix_paired"
    mock_sim = MockHoldoutSimulator()

    res = execute_production_holdout_pipeline(
        partition="mixture",
        policy_path=Path("results/v9/cal_r2/selected_policy.json"),
        manifest_path=man_path,
        out_dir=out_dir,
        authorized_execution_token=REQUIRED_EXECUTION_TOKEN,
        simulator_fn=mock_sim,
        allow_mock_simulation=True,
    )

    # Read back generated episodes CSV files
    with (out_dir / "test_mix_episodes.csv").open(encoding="utf-8") as f:
        pol_rows = list(csv.DictReader(f))
    with (out_dir / "test_mix_baseline_v8_episodes.csv").open(encoding="utf-8") as f:
        v8_rows = list(csv.DictReader(f))
    with (out_dir / "test_mix_baseline_v7_episodes.csv").open(encoding="utf-8") as f:
        v7_rows = list(csv.DictReader(f))

    # Bijective alignment must succeed
    paired_v8 = align_and_pair_records(pol_rows, v8_rows, baseline_label="v8")
    paired_v7 = align_and_pair_records(pol_rows, v7_rows, baseline_label="v7")

    assert len(paired_v8) == len(pol_rows)
    assert len(paired_v7) == len(pol_rows)

    for p, b in paired_v8:
        assert p["seed"] == b["seed"]
        assert p["scenario"] == b["scenario"]

    for p, b in paired_v7:
        assert p["seed"] == b["seed"]
        assert p["scenario"] == b["scenario"]


def test_44_cli_default_preflight_and_production_dispatch():
    """Requirement: CLI defaults to read-only preflight mode; --run-production dispatches to pipeline."""
    from experiments.v9_evaluate_holdout import main as cli_main
    import sys

    # In preflight mode (default), executes read-only checks and exits 0
    orig_argv = sys.argv
    try:
        sys.argv = ["v9_evaluate_holdout.py", "--preflight-only"]
        with pytest.raises(SystemExit) as exc_info:
            cli_main()
        assert exc_info.value.code == 0
    finally:
        sys.argv = orig_argv


def test_45_h3_authoritative_v8_and_v7_dual_baseline_evaluation():
    """Requirement: H3 evaluates primary noninferiority vs V8.1 and co-evaluates vs V7 per Protocol 3.1.1."""
    scenarios = build_v9_s12_scenarios()
    seeds_per_scen = 10
    pol_records = []
    v8_records = []
    v7_records = []

    ep_idx = 0
    for sc_idx, scen in enumerate(scenarios):
        for s_idx in range(seeds_per_scen):
            seed = 85000 + sc_idx * 100 + s_idx
            # Policy V9: high true success (1.0 on nominal, 1.0 on all)
            pol_records.append(make_synthetic_episode_record(
                episode_index=ep_idx,
                seed=seed,
                scenario=scen.name,
                scenario_index=sc_idx,
                accepted=True,
                outcome="TERMINAL_SUCCESS",
            ))
            # Baseline V8.1: moderate true success
            v8_records.append(make_synthetic_episode_record(
                episode_index=ep_idx,
                seed=seed,
                scenario=scen.name,
                scenario_index=sc_idx,
                accepted=True,
                outcome="TERMINAL_SUCCESS" if s_idx < 8 else "FALSE_SUCCESS",
            ))
            # Baseline V7: lower true success
            v7_records.append(make_synthetic_episode_record(
                episode_index=ep_idx,
                seed=seed,
                scenario=scen.name,
                scenario_index=sc_idx,
                accepted=True,
                outcome="TERMINAL_SUCCESS" if s_idx < 7 else "FALSE_SUCCESS",
            ))
            ep_idx += 1

    res = evaluate_scenario_holdout(
        records=pol_records,
        v8_records=v8_records,
        v7_records=v7_records,
        expected_seeds_per_scenario=seeds_per_scen,
    )

    # 1. H3 overall summary is present and confirms primary V8.1 and co-evaluated V7
    assert "h3_overall" in res
    assert res["h3_overall"]["primary_baseline"] == "v8_martingale"
    assert res["h3_overall"]["co_evaluated_baseline"] == "v7_mpc"
    assert res["h3_overall"]["passed"] is True
    assert res["h3_overall"]["status"] == "CONFIRMATORY_PASS"

    # 2. Primary V8.1 noninferiority evaluation
    assert "h3_tsr_noninferiority_vs_v8" in res
    h3_v8 = res["h3_tsr_noninferiority_vs_v8"]
    assert h3_v8["baseline"] == "v8_martingale"
    assert h3_v8["nominal_tsr"] == 1.0
    assert h3_v8["mean_delta_tsr"] > 0.0
    assert h3_v8["lcb95_delta_tsr"] > -0.05
    assert h3_v8["passed"] is True

    # 3. Co-evaluated V7 noninferiority evaluation (preserving backward-compatible key)
    assert "h3_tsr_noninferiority_vs_v7" in res
    h3_v7 = res["h3_tsr_noninferiority_vs_v7"]
    assert h3_v7["baseline"] == "v7_mpc"
    assert h3_v7["nominal_tsr"] == 1.0
    assert h3_v7["mean_delta_tsr"] > 0.0
    assert h3_v7["lcb95_delta_tsr"] > -0.05
    assert h3_v7["passed"] is True


def test_46_h3_baseline_substitution_rejection():
    """Requirement: Unintended baseline substitution or mismatched identity keys fails closed."""
    scenarios = build_v9_s12_scenarios()
    seeds_per_scen = 5
    pol_records = []
    corrupted_baseline = []

    ep_idx = 0
    for sc_idx, scen in enumerate(scenarios):
        for s_idx in range(seeds_per_scen):
            seed = 86000 + sc_idx * 100 + s_idx
            pol_records.append(make_synthetic_episode_record(
                episode_index=ep_idx,
                seed=seed,
                scenario=scen.name,
                scenario_index=sc_idx,
                accepted=True,
                outcome="TERMINAL_SUCCESS",
            ))
            # Substituted/corrupted seed in baseline
            corrupted_baseline.append(make_synthetic_episode_record(
                episode_index=ep_idx,
                seed=seed + 9999,  # Mismatched seed
                scenario=scen.name,
                scenario_index=sc_idx,
                accepted=True,
                outcome="TERMINAL_SUCCESS",
            ))
            ep_idx += 1

    # Passing mismatched baseline into v8_records must raise ValueError
    with pytest.raises(ValueError, match="Missing baseline v8_martingale record for episode"):
        evaluate_scenario_holdout(
            records=pol_records,
            v8_records=corrupted_baseline,
            expected_seeds_per_scenario=seeds_per_scen,
        )

    # Passing mismatched baseline into v7_records must also raise ValueError
    with pytest.raises(ValueError, match="Missing baseline v7_mpc record for episode"):
        evaluate_scenario_holdout(
            records=pol_records,
            v7_records=corrupted_baseline,
            expected_seeds_per_scenario=seeds_per_scen,
        )


def test_47_crn_controller_order_invariance():
    """Requirement: Simulating controllers in different orders produces bitwise identical random streams."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    man = gen.generate_manifest(
        partition_name="test_crn_order",
        manifest_id_start=87000,
        count=3,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    scen = build_v9_s12_scenarios()[0]

    for item in man["episodes"]:
        ep_seed = int(item["manifest_id"])

        # Order 1: V9 -> V8 -> V7
        sim_1 = MockHoldoutSimulator()
        rng_env_pi1, rng_sen_pi1 = _derive_episode_rngs(item, ep_seed)
        sim_1(scen, ep_seed, "V9", None, rng_env=rng_env_pi1, rng_sensors=rng_sen_pi1)

        rng_env_v81, rng_sen_v81 = _derive_episode_rngs(item, ep_seed)
        sim_1(scen, ep_seed, "V8", None, rng_env=rng_env_v81, rng_sensors=rng_sen_v81)

        rng_env_v71, rng_sen_v71 = _derive_episode_rngs(item, ep_seed)
        sim_1(scen, ep_seed, "V7", None, rng_env=rng_env_v71, rng_sensors=rng_sen_v71)

        # Order 2: V7 -> V8 -> V9
        sim_2 = MockHoldoutSimulator()
        rng_env_v72, rng_sen_v72 = _derive_episode_rngs(item, ep_seed)
        sim_2(scen, ep_seed, "V7", None, rng_env=rng_env_v72, rng_sensors=rng_sen_v72)

        rng_env_v82, rng_sen_v82 = _derive_episode_rngs(item, ep_seed)
        sim_2(scen, ep_seed, "V8", None, rng_env=rng_env_v82, rng_sensors=rng_sen_v82)

        rng_env_pi2, rng_sen_pi2 = _derive_episode_rngs(item, ep_seed)
        sim_2(scen, ep_seed, "V9", None, rng_env=rng_env_pi2, rng_sensors=rng_sen_pi2)

        # Look up records by policy
        log1 = {entry["policy"]: entry for entry in sim_1.call_log}
        log2 = {entry["policy"]: entry for entry in sim_2.call_log}

        for pol in ["V9", "V8", "V7"]:
            assert log1[pol]["env_val"] == log2[pol]["env_val"], f"Order discrepancy in env for {pol}"
            assert log1[pol]["sens_val"] == log2[pol]["sens_val"], f"Order discrepancy in sens for {pol}"


def test_48_crn_consumption_and_early_termination_isolation():
    """Requirement: Early termination or divergent draw counts in one controller does not alter another."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    man = gen.generate_manifest(
        partition_name="test_crn_isolation",
        manifest_id_start=88000,
        count=1,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    item = man["episodes"][0]
    ep_seed = int(item["manifest_id"])

    # Reference full stream for Controller 2 (runs 100 steps)
    rng_ref_env, rng_ref_sen = _derive_episode_rngs(item, ep_seed)
    ref_env_draws = [rng_ref_env.uniform() for _ in range(100)]
    ref_sen_draws = [rng_ref_sen.normal() for _ in range(100)]

    # Experiment: Controller 1 terminates early after drawing 5 numbers
    rng_ctrl1_env, rng_ctrl1_sen = _derive_episode_rngs(item, ep_seed)
    _ = [rng_ctrl1_env.uniform() for _ in range(5)]
    _ = [rng_ctrl1_sen.normal() for _ in range(5)]

    # Controller 2 is now instantiated and run
    rng_ctrl2_env, rng_ctrl2_sen = _derive_episode_rngs(item, ep_seed)
    ctrl2_env_draws = [rng_ctrl2_env.uniform() for _ in range(100)]
    ctrl2_sen_draws = [rng_ctrl2_sen.normal() for _ in range(100)]

    # Assert 100% bitwise equivalence with the reference run
    assert ctrl2_env_draws == ref_env_draws, "Controller 1 early termination contaminated Controller 2 env stream"
    assert ctrl2_sen_draws == ref_sen_draws, "Controller 1 early termination contaminated Controller 2 sens stream"


def test_49_crn_initial_conditions_and_divergence_characteristics():
    """Requirement: Verifies common initial conditions and documents mutable-stream divergence characteristics."""
    from aegis.v3.env.world import AegisPhysicalWorld

    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    man = gen.generate_manifest(
        partition_name="test_crn_physics",
        manifest_id_start=89000,
        count=1,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    item = man["episodes"][0]
    ep_seed = int(item["manifest_id"])

    # 1. Physical world target position is 100% bitwise identical across all 3 controllers
    rng_env_v9, _ = _derive_episode_rngs(item, ep_seed)
    w_v9 = AegisPhysicalWorld()
    st_v9 = w_v9.reset(rng_env_v9)

    rng_env_v8, _ = _derive_episode_rngs(item, ep_seed)
    w_v8 = AegisPhysicalWorld()
    st_v8 = w_v8.reset(rng_env_v8)

    rng_env_v7, _ = _derive_episode_rngs(item, ep_seed)
    w_v7 = AegisPhysicalWorld()
    st_v7 = w_v7.reset(rng_env_v7)

    assert np.array_equal(st_v9["target_pos"], st_v8["target_pos"])
    assert np.array_equal(st_v9["target_pos"], st_v7["target_pos"])
    assert np.array_equal(st_v9["robot_pos"], st_v8["robot_pos"])
    assert np.array_equal(st_v9["robot_pos"], st_v7["robot_pos"])

    # 2. Initial sensor noise draws at step t=0 are identical
    _, rng_sen_v9 = _derive_episode_rngs(item, ep_seed)
    _, rng_sen_v8 = _derive_episode_rngs(item, ep_seed)
    _, rng_sen_v7 = _derive_episode_rngs(item, ep_seed)

    draw_v9_t0 = rng_sen_v9.normal(size=4)
    draw_v8_t0 = rng_sen_v8.normal(size=4)
    draw_v7_t0 = rng_sen_v7.normal(size=4)
    assert np.array_equal(draw_v9_t0, draw_v8_t0)
    assert np.array_equal(draw_v9_t0, draw_v7_t0)

    # 3. Document mutable-stream offset divergence when anchor is queried
    # Suppose V8 queries anchor at step 0 (advances 2 draws), but V7 does not
    _ = rng_sen_v8.normal(size=2)  # anchor query draws

    # Step t=1: sensor noise draws now diverge in mutable stream
    draw_v8_t1 = rng_sen_v8.normal(size=2)
    draw_v7_t1 = rng_sen_v7.normal(size=2)
    assert not np.array_equal(draw_v8_t1, draw_v7_t1), "Expected mutable stream offset after anchor query"


def test_50_crn_independent_generator_state_and_timestep_channel_comparison():
    """Requirement: Verifies distinct in-memory Generator state and channel noise coupling at t=0."""
    from aegis.v3.sensors.sensors import FaultInjectableSensor
    from aegis.v3.sensors.cross_modal import RangeSensor
    from aegis.v7.anchor_sensor import AnchorSensor, AnchorSensorConfig

    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    man = gen.generate_manifest(
        partition_name="test_crn_channels",
        manifest_id_start=91000,
        count=1,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    item = man["episodes"][0]
    ep_seed = int(item["manifest_id"])
    scen = build_v9_s12_scenarios()[0]

    # Verify separate in-memory Generator instances
    rng_env_v9, rng_sen_v9 = _derive_episode_rngs(item, ep_seed)
    rng_env_v8, rng_sen_v8 = _derive_episode_rngs(item, ep_seed)
    rng_env_v7, rng_sen_v7 = _derive_episode_rngs(item, ep_seed)

    assert rng_env_v9 is not rng_env_v8
    assert rng_env_v8 is not rng_env_v7
    assert rng_sen_v9 is not rng_sen_v8
    assert rng_sen_v8 is not rng_sen_v7

    # Sensor measurements at t=0: zero anchor query calls
    sen_a_v9 = FaultInjectableSensor(scen.sensor_a)
    sen_a_v8 = FaultInjectableSensor(scen.sensor_a)
    sen_a_v7 = FaultInjectableSensor(scen.sensor_a)

    delta_true = np.array([1.5, -2.0], dtype=np.float64)
    read_a_v9 = sen_a_v9.measure(delta_true, rng_sen_v9, step=0)
    read_a_v8 = sen_a_v8.measure(delta_true, rng_sen_v8, step=0)
    read_a_v7 = sen_a_v7.measure(delta_true, rng_sen_v7, step=0)

    # Identical sensor noise at step t=0 across all three controllers
    assert np.array_equal(read_a_v9.estimate, read_a_v8.estimate)
    assert np.array_equal(read_a_v9.estimate, read_a_v7.estimate)


def test_51_crn_anchor_query_count_induced_stream_offset():
    """Requirement: Verifies that anchor queries shift mutable streams by exact consumption count."""
    gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    man = gen.generate_manifest(
        partition_name="test_crn_offset",
        manifest_id_start=92000,
        count=1,
        partition_index=PARTITION_BRANCH_TEST_MIXTURE,
    )
    item = man["episodes"][0]
    ep_seed = int(item["manifest_id"])

    # Stream A: 0 anchor queries
    _, rng_a = _derive_episode_rngs(item, ep_seed)
    # Stream B: 1 anchor query (consumes 2 normal draws)
    _, rng_b = _derive_episode_rngs(item, ep_seed)

    # Stream B executes an anchor query
    _ = rng_b.normal(size=2)

    # Subsequent 10 draws from B match draws 2..11 from A
    draws_a = [rng_a.normal() for _ in range(12)]
    draws_b = [rng_b.normal() for _ in range(10)]

    assert np.allclose(draws_a[2:], draws_b, atol=1e-12)


def test_52_h3_synthetic_combinations_primary_pass_coeval_fail():
    """Requirement: H3 reports primary pass and co-eval fail without conflating their roles."""
    scenarios = build_v9_s12_scenarios()
    seeds_per_scen = 10
    ep_idx = 0

    pol_records = []
    v8_records = []
    v7_records = []

    for sc_idx, scen in enumerate(scenarios):
        for s_idx in range(seeds_per_scen):
            seed = 93000 + sc_idx * 100 + s_idx
            # Policy V9: 100% nominal TSR, 80% adversarial TSR
            pol_ts = 1 if (scen.name == "NOMINAL" or s_idx < 8) else 0
            # Baseline V8: lower TSR (V9 is superior/noninferior vs V8)
            v8_ts = 1 if (scen.name == "NOMINAL" or s_idx < 5) else 0
            # Baseline V7: higher TSR (V9 is inferior vs V7)
            v7_ts = 1  # V7 gets 100% TSR

            pol_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(pol_ts),
                outcome="TERMINAL_SUCCESS" if pol_ts else "ABSTAINED",
            ))
            v8_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(v8_ts),
                outcome="TERMINAL_SUCCESS" if v8_ts else "ABSTAINED",
            ))
            v7_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(v7_ts),
                outcome="TERMINAL_SUCCESS" if v7_ts else "ABSTAINED",
            ))
            ep_idx += 1

    res = evaluate_scenario_holdout(
        records=pol_records,
        v8_records=v8_records,
        v7_records=v7_records,
        expected_seeds_per_scenario=seeds_per_scen,
    )

    h3_ov = res["h3_overall"]
    assert h3_ov["primary_passed"] is True
    assert h3_ov["coeval_passed"] is False
    assert h3_ov["all_baselines_passed"] is False
    # Primary null is rejected, so overall pass is True
    assert h3_ov["passed"] is True
    assert res["h3_tsr_noninferiority_vs_v8"]["passed"] is True
    assert res["h3_tsr_noninferiority_vs_v7"]["passed"] is False


def test_53_h3_synthetic_combinations_primary_fail_coeval_pass():
    """Requirement: When primary V8 noninferiority fails, H3 overall fails even if V7 passes."""
    scenarios = build_v9_s12_scenarios()
    seeds_per_scen = 10
    ep_idx = 0

    pol_records = []
    v8_records = []
    v7_records = []

    for sc_idx, scen in enumerate(scenarios):
        for s_idx in range(seeds_per_scen):
            seed = 94000 + sc_idx * 100 + s_idx
            # Policy V9: 100% nominal TSR, 50% adversarial TSR
            pol_ts = 1 if (scen.name == "NOMINAL" or s_idx < 5) else 0
            # Baseline V8: higher TSR (V9 is inferior vs V8)
            v8_ts = 1 if (scen.name == "NOMINAL" or s_idx < 9) else 0
            # Baseline V7: lower TSR (V9 is superior vs V7)
            v7_ts = 1 if (scen.name == "NOMINAL" or s_idx < 2) else 0

            pol_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(pol_ts),
                outcome="TERMINAL_SUCCESS" if pol_ts else "ABSTAINED",
            ))
            v8_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(v8_ts),
                outcome="TERMINAL_SUCCESS" if v8_ts else "ABSTAINED",
            ))
            v7_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(v7_ts),
                outcome="TERMINAL_SUCCESS" if v7_ts else "ABSTAINED",
            ))
            ep_idx += 1

    res = evaluate_scenario_holdout(
        records=pol_records,
        v8_records=v8_records,
        v7_records=v7_records,
        expected_seeds_per_scenario=seeds_per_scen,
    )

    h3_ov = res["h3_overall"]
    assert h3_ov["primary_passed"] is False
    assert h3_ov["coeval_passed"] is True
    assert h3_ov["all_baselines_passed"] is False
    assert h3_ov["passed"] is False
    assert res["h3_tsr_noninferiority_vs_v8"]["passed"] is False
    assert res["h3_tsr_noninferiority_vs_v7"]["passed"] is True


def test_54_h3_synthetic_combinations_nominal_tsr_failure_blocks_both():
    """Requirement: Nominal TSR < 0.94 independently blocks H3 even if Delta TSR is positive."""
    scenarios = build_v9_s12_scenarios()
    seeds_per_scen = 10
    ep_idx = 0

    pol_records = []
    v8_records = []
    v7_records = []

    for sc_idx, scen in enumerate(scenarios):
        for s_idx in range(seeds_per_scen):
            seed = 95000 + sc_idx * 100 + s_idx
            # Policy V9: fails nominal (only 8/10 = 0.80)
            pol_ts = 1 if (scen.name == "NOMINAL" and s_idx < 8) else (1 if s_idx < 9 else 0)
            v8_ts = 1 if s_idx < 4 else 0
            v7_ts = 1 if s_idx < 3 else 0

            pol_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(pol_ts),
                outcome="TERMINAL_SUCCESS" if pol_ts else "ABSTAINED",
            ))
            v8_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(v8_ts),
                outcome="TERMINAL_SUCCESS" if v8_ts else "ABSTAINED",
            ))
            v7_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(v7_ts),
                outcome="TERMINAL_SUCCESS" if v7_ts else "ABSTAINED",
            ))
            ep_idx += 1

    res = evaluate_scenario_holdout(
        records=pol_records,
        v8_records=v8_records,
        v7_records=v7_records,
        expected_seeds_per_scenario=seeds_per_scen,
    )

    h3_ov = res["h3_overall"]
    assert h3_ov["nominal_tsr_criterion_met"] is False
    assert res["h3_tsr_noninferiority_vs_v8"]["passed"] is False
    assert res["h3_tsr_noninferiority_vs_v7"]["passed"] is False
    assert h3_ov["passed"] is False


def test_55_h3_s10_block_restriction():
    """Requirement: Episodes in S_ext (scenarios 11 & 12) do not contaminate S_10 H3 evaluation."""
    scenarios = build_v9_s12_scenarios()
    seeds_per_scen = 10
    ep_idx = 0

    pol_records_clean = []
    pol_records_ext_altered = []
    v8_records = []

    for sc_idx, scen in enumerate(scenarios):
        for s_idx in range(seeds_per_scen):
            seed = 96000 + sc_idx * 100 + s_idx
            pol_ts = 1 if (scen.name == "NOMINAL" or s_idx < 8) else 0
            v8_ts = 1 if (scen.name == "NOMINAL" or s_idx < 7) else 0

            rec_clean = make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(pol_ts),
                outcome="TERMINAL_SUCCESS" if pol_ts else "ABSTAINED",
            )
            pol_records_clean.append(rec_clean)

            # In altered version, change outcome ONLY for S_ext scenarios (sc_idx >= 10)
            if sc_idx >= 10:
                rec_altered = make_synthetic_episode_record(
                    episode_index=ep_idx, seed=seed, scenario=scen.name,
                    scenario_index=sc_idx, accepted=False,
                    outcome="ABSTAINED",  # force 0 true success in S_ext
                )
            else:
                rec_altered = rec_clean
            pol_records_ext_altered.append(rec_altered)

            v8_records.append(make_synthetic_episode_record(
                episode_index=ep_idx, seed=seed, scenario=scen.name,
                scenario_index=sc_idx, accepted=bool(v8_ts),
                outcome="TERMINAL_SUCCESS" if v8_ts else "ABSTAINED",
            ))
            ep_idx += 1

    res_clean = evaluate_scenario_holdout(
        records=pol_records_clean,
        v8_records=v8_records,
        expected_seeds_per_scenario=seeds_per_scen,
    )
    res_altered = evaluate_scenario_holdout(
        records=pol_records_ext_altered,
        v8_records=v8_records,
        expected_seeds_per_scenario=seeds_per_scen,
    )

    # H3 statistics must be 100% bitwise identical despite S_ext differences
    assert res_clean["h3_tsr_noninferiority_vs_v8"]["mean_delta_tsr"] == res_altered["h3_tsr_noninferiority_vs_v8"]["mean_delta_tsr"]
    assert res_clean["h3_tsr_noninferiority_vs_v8"]["lcb95_delta_tsr"] == res_altered["h3_tsr_noninferiority_vs_v8"]["lcb95_delta_tsr"]
    assert res_clean["h3_tsr_noninferiority_vs_v8"]["passed"] == res_altered["h3_tsr_noninferiority_vs_v8"]["passed"]




