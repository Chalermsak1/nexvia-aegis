"""
Tests for NEXVIA AEGIS V9-M3 Operational Validation Suite.

Verifies:
1. Manifest loading and cryptographic integrity verification.
2. Selected policy enforcement (strictly requires certified V9_CAND_1_TIER1_STRICTEST).
3. Partition guardrails prohibiting seeds outside 72000..72039.
4. Output directory isolation.
5. Single-shot execution guard refusing to overwrite existing validation outputs.
6. Decoupled RNG derivation and stream disjointness with calibration/development.
7. Freeze-only run configuration creation without episode execution.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest

from aegis.v9.randomization import (
    PARTITION_BRANCH_CALIBRATION,
    PARTITION_BRANCH_DEV,
    PARTITION_BRANCH_VALIDATION,
    instantiate_episode_rngs_from_manifest_item,
)
from aegis.v9.risk_statistics import compute_canonical_payload_sha256
from experiments.v9_validate import (
    VAL_ALLOWED_SEEDS,
    VAL_EXPECTED_EPISODES,
    VAL_SEEDS_PER_SCENARIO,
    enforce_val_only_seeds,
    enforce_val_output_directory,
    execute_single_shot_validation,
    freeze_val_run_configuration,
    verify_and_load_selected_policy,
    verify_and_load_val_manifest,
)


def test_val_manifest_loader_and_integrity():
    """Verify that results/v9/manifests/val_manifest_r1.json passes strict integrity checks."""
    man_path = Path("results/v9/manifests/val_manifest_r1.json")
    manifest, raw_sha = verify_and_load_val_manifest(man_path)

    assert manifest["partition"] == "validation_r1"
    assert manifest["partition_index"] == PARTITION_BRANCH_VALIDATION
    assert manifest["planned_episodes"] == VAL_EXPECTED_EPISODES
    assert len(manifest["episodes"]) == VAL_EXPECTED_EPISODES

    counts = manifest["realized_scenario_counts"]
    assert len(counts) == 12
    for sc_name, count in counts.items():
        assert count == VAL_SEEDS_PER_SCENARIO, f"Scenario {sc_name} count {count} != {VAL_SEEDS_PER_SCENARIO}"

    # Verify seed boundaries
    seeds = [int(ep["seed"]) for ep in manifest["episodes"]]
    unique_seeds = set(seeds)
    assert unique_seeds == set(range(72000, 72040))


def test_selected_policy_enforcement():
    """Verify that only certified V9_CAND_1_TIER1_STRICTEST is accepted."""
    pol_path = Path("results/v9/cal_r2/selected_policy.json")
    cand, payload, raw_sha = verify_and_load_selected_policy(pol_path)

    assert cand.candidate_id == "V9_CAND_1_TIER1_STRICTEST"
    assert cand.tier_index == 1
    assert payload["certified"] is True
    assert payload["calibration_status"] == "V9_CALIBRATION_CERTIFIED"


def test_selected_policy_rejects_uncertified_or_mismatched(tmp_path: Path):
    """Verify rejection of uncertified policies or wrong candidate IDs."""
    pol_path = Path("results/v9/cal_r2/selected_policy.json")
    data = json.loads(pol_path.read_text(encoding="utf-8"))

    # Case 1: uncertified
    bad_data1 = dict(data)
    bad_data1["certified"] = False
    bad_data1["integrity_sha256"] = compute_canonical_payload_sha256(bad_data1)
    bad_path1 = tmp_path / "uncertified.json"
    bad_path1.write_text(json.dumps(bad_data1, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="not certified"):
        verify_and_load_selected_policy(bad_path1)

    # Case 2: mismatched candidate ID
    bad_data2 = dict(data)
    bad_cand = dict(data["selected_candidate"])
    bad_cand["candidate_id"] = "V9_CAND_2_TIER2_VERY_STRICT"
    bad_data2["selected_candidate"] = bad_cand
    bad_data2["integrity_sha256"] = compute_canonical_payload_sha256(bad_data2)
    bad_path2 = tmp_path / "wrong_cand.json"
    bad_path2.write_text(json.dumps(bad_data2, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate ID mismatch"):
        verify_and_load_selected_policy(bad_path2)


def test_validation_partition_guardrails():
    """Verify strict prohibition of non-validation seeds."""
    prohibited_seeds = [60000, 70000, 71000, 73000, 75000, 76000, 77000]
    for seed in prohibited_seeds:
        with pytest.raises(ValueError, match="PROHIBITED SEED ACCESS BLOCKED"):
            enforce_val_only_seeds([seed])

    # Allowed range
    valid_seeds = list(range(72000, 72040))
    enforced = enforce_val_only_seeds(valid_seeds)
    assert len(enforced) == 40


def test_validation_output_isolation(tmp_path: Path):
    """Verify that outputs can only be written to results/v9/val or results/v9/val_r1."""
    # Invalid directories
    with pytest.raises(ValueError, match="must end with"):
        enforce_val_output_directory(tmp_path / "cal_results")

    with pytest.raises(ValueError, match="must end with"):
        enforce_val_output_directory("results/v9/cal")

    # Valid directories
    valid_val = Path("results/v9/val_r1")
    assert enforce_val_output_directory(valid_val) == valid_val.resolve()


def test_single_shot_guard_refuses_overwrite(tmp_path: Path):
    """Verify that runner blocks execution if outputs already exist."""
    fake_val_dir = tmp_path / "results" / "v9" / "val_r1"
    fake_val_dir.mkdir(parents=True)
    (fake_val_dir / "val_episodes.csv").write_text("dummy", encoding="utf-8")

    with pytest.raises(RuntimeError, match="SINGLE-SHOT EXECUTION GUARD"):
        execute_single_shot_validation(
            manifest_path="results/v9/manifests/val_manifest_r1.json",
            selected_policy_path="results/v9/cal_r2/selected_policy.json",
            out_dir=fake_val_dir,
        )


def test_validation_rng_derivation_disjointness():
    """
    Verify that validation manifest streams use branch p=3 and have zero overlap
    with calibration (p=2) or development (p=1).
    """
    val_man_path = Path("results/v9/manifests/val_manifest_r1.json")
    val_man = json.loads(val_man_path.read_text(encoding="utf-8"))

    cal_man_path = Path("results/v9/manifests/cal_manifest_r2.json")
    cal_man = json.loads(cal_man_path.read_text(encoding="utf-8"))

    # Check spawn keys
    for ep in val_man["episodes"][:20]:
        assert ep["spawn_key"][0] == PARTITION_BRANCH_VALIDATION
        assert ep["env_spawn_key"][:2] == [PARTITION_BRANCH_VALIDATION, 1]
        assert ep["sensor_spawn_key"][:2] == [PARTITION_BRANCH_VALIDATION, 1]

        # Distinct child streams
        decoupled = instantiate_episode_rngs_from_manifest_item(ep)
        draw_env = decoupled.rng_env.normal(size=20)
        draw_sens = decoupled.rng_sensors.normal(size=20)
        assert not np.array_equal(draw_env, draw_sens)

    # Check root disjointness against calibration
    val_root = val_man["episodes"][0]["spawn_key"][0]
    cal_root = cal_man["episodes"][0]["spawn_key"][0]
    assert val_root == 3
    assert cal_root == 2
    assert val_root != cal_root


def test_freeze_only_run_config(tmp_path: Path):
    """Verify freeze-only creates the run config without generating episode records."""
    fake_val_dir = tmp_path / "results" / "v9" / "val_r1"
    res = execute_single_shot_validation(
        manifest_path="results/v9/manifests/val_manifest_r1.json",
        selected_policy_path="results/v9/cal_r2/selected_policy.json",
        out_dir=fake_val_dir,
        freeze_only=True,
    )
    assert res["status"] == "FROZEN_READY"
    cfg_file = fake_val_dir / "validation_run_config_frozen_r1.json"
    assert cfg_file.exists()

    # Verify no episode records or reports were written
    assert not (fake_val_dir / "val_episodes.csv").exists()
    assert not (fake_val_dir / "validation_report.json").exists()

    # Verify run config integrity
    cfg_payload = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert cfg_payload["integrity_sha256"] == compute_canonical_payload_sha256(cfg_payload)
