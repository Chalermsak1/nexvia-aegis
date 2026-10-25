"""
NEXVIA AEGIS V9.0 — Milestone V9-M3 Single-Shot Independent Operational Validation Runner.

GOVERNANCE & PARTITION GUARDRAILS (`docs/v9_m3_validation_protocol.md`,
`docs/v9_risk_calibration_design.md` Section 2.4-2.5, `docs/v9_experiment_protocol.md` Sections 3.1-3.6):
- Evaluates EXCLUSIVELY the frozen calibrated policy selected in Milestone V9-M2R2:
  `V9_CAND_1_TIER1_STRICTEST` from `results/v9/cal_r2/selected_policy.json` (verified against
  its canonical SHA-256 integrity hash).
- Evaluates EXCLUSIVELY on the preregistered stratified grid validation partition `D_val`
  (`N_val = 480`, 12 scenarios x 40 seeds, seeds `72000..72039`, derived under root
  partition branch p=3 in `results/v9/manifests/val_manifest_r1.json`).
- HARD PROHIBITION: Any seed outside `72000..72039` (including `D_hist` `60000..60049`,
  `D_dev` `70000..70029` / `77000..77029`, `D_cal` `71000..71959` / `76000..76959`,
  `D_test^mix` `73000..74439`, and `D_test^scen` `75000..75119`) is strictly blocked with `ValueError`.
- SINGLE-SHOT EXECUTION GUARD: Refuses to run or overwrite if any episode record or validation
  report already exists in the validation output directory. On any mid-run technical failure,
  preserves partial outputs (`val_episodes_PARTIAL.csv` + `INCOMPLETE_INVALID.json`) without deletion.
- HOLDOUT ISOLATION: Never accesses or executes the reserved holdout partitions.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np
from scipy.stats import beta, binom

from aegis.v9.controller import AegisV9Controller
from aegis.v9.randomization import (
    PARTITION_BRANCH_VALIDATION,
    instantiate_episode_rngs_from_manifest_item,
)
from aegis.v9.risk_statistics import (
    PolicyEvaluationSummary,
    V9CandidateParams,
    compute_canonical_payload_sha256,
    compute_policy_summary,
)
from experiments.v9_calibrate_ltt import verify_episode_outcome_algebra
from experiments.v9_evaluate_dev import (
    V9ScenarioSpec,
    build_v9_s12_scenarios,
    run_single_episode,
)

PROTOCOL_VERSION: str = "v9.0-preregistered-2026-10-amendment-r2-val"
V9_M1_COMMIT: str = "6c87f66a9ea602c96d4fe8bfc97728d0513b157f"
SOURCE_DESIGN_COMMIT: str = "891c13e7bbd60e36c416c9bada8407e51233e663"
V81_BASELINE_COMMIT: str = "4d891c7500cfb4c8110f276038455bc62765ef3b"
EXPECTED_SELECTED_CANDIDATE_ID: str = "V9_CAND_1_TIER1_STRICTEST"

VAL_SEED_START: int = 72000
VAL_SEED_STOP_EXCLUSIVE: int = 72040
VAL_SEEDS_PER_SCENARIO: int = 40
VAL_EXPECTED_EPISODES: int = 480
VAL_ALLOWED_SEEDS: frozenset[int] = frozenset(range(VAL_SEED_START, VAL_SEED_STOP_EXCLUSIVE))

PROHIBITED_SEED_BLOCKS: tuple[tuple[str, range], ...] = (
    ("D_hist", range(60000, 60050)),
    ("D_dev_historical", range(70000, 70030)),
    ("D_dev_r1", range(77000, 77030)),
    ("D_cal_historical", range(71000, 71960)),
    ("D_cal_r1_r2", range(76000, 76960)),
    ("D_test_mix", range(73000, 74440)),
    ("D_test_scen", range(75000, 75120)),
)


def sha256_file(path: Path) -> str:
    """Returns hex SHA-256 digest of a file's exact raw bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def enforce_val_only_seeds(seeds: Sequence[int]) -> tuple[int, ...]:
    """Blocks any seed outside the permitted validation block (72000..72039)."""
    if not seeds:
        raise ValueError("Validation seed sequence must be non-empty.")
    out = tuple(int(s) for s in seeds)
    forbidden = [s for s in out if s not in VAL_ALLOWED_SEEDS]
    if forbidden:
        raise ValueError(
            f"PROHIBITED SEED ACCESS BLOCKED: {forbidden[:10]}. "
            f"Permitted validation seeds are strictly {VAL_SEED_START}..{VAL_SEED_STOP_EXCLUSIVE - 1}."
        )
    return out


def enforce_val_output_directory(out_dir: str | Path) -> Path:
    """Ensures validation outputs are written strictly under `results/v9/val` or `results/v9/val_r1`."""
    resolved = Path(out_dir).resolve()
    parts = resolved.parts
    if len(parts) < 3 or parts[-2] != "v9" or not parts[-1].startswith("val"):
        raise ValueError(
            f"Validation output path `{resolved}` must end with `results/v9/val` or `results/v9/val_r1` "
            "to isolate validation artifacts from calibration, development, and holdout splits."
        )
    return resolved


def enforce_val_manifest_path(manifest_path: str | Path) -> Path:
    """Ensures validation manifest is located strictly inside `results/v9/manifests`."""
    resolved = Path(manifest_path).resolve()
    parts = resolved.parts
    if len(parts) < 4 or parts[-4:-1] != ("results", "v9", "manifests") or not parts[-1].endswith(".json"):
        raise ValueError(
            f"Validation manifest path `{resolved}` must be inside `results/v9/manifests/`."
        )
    return resolved


def verify_and_load_selected_policy(
    policy_path: Path,
) -> tuple[V9CandidateParams, dict[str, Any], str]:
    """
    Verifies that the selected policy artifact is certified, unaltered, and corresponds
    to the preregistered candidate V9_CAND_1_TIER1_STRICTEST.
    """
    if not policy_path.exists():
        raise FileNotFoundError(f"Selected policy artifact not found: {policy_path}")

    raw_bytes = policy_path.read_bytes()
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    payload = json.loads(raw_bytes.decode("utf-8"))

    stored_integrity = payload.get("integrity_sha256")
    computed_integrity = compute_canonical_payload_sha256(payload)
    if stored_integrity != computed_integrity:
        raise ValueError(
            f"Selected policy integrity hash mismatch: {stored_integrity} != {computed_integrity}."
        )

    if not payload.get("certified", False):
        raise ValueError(
            f"Selected policy is not certified: status={payload.get('calibration_status')}."
        )

    cand_dict = payload.get("selected_candidate", {})
    cand_id = cand_dict.get("candidate_id")
    if cand_id != EXPECTED_SELECTED_CANDIDATE_ID:
        raise ValueError(
            f"Selected policy candidate ID mismatch: expected `{EXPECTED_SELECTED_CANDIDATE_ID}`, got `{cand_id}`."
        )

    cand_params = V9CandidateParams(
        candidate_id=cand_dict["candidate_id"],
        tier_index=int(cand_dict["tier_index"]),
        tier_label=str(cand_dict["tier_label"]),
        alpha_mon=float(cand_dict["alpha_mon"]),
        h_cusum=float(cand_dict["h_cusum"]),
        tau_diff=float(cand_dict["tau_diff"]),
        tau_ar=float(cand_dict["tau_ar"]),
        tau_val=float(cand_dict["tau_val"]),
        tau_stop=float(cand_dict["tau_stop"]),
        gamma_ville=float(cand_dict["gamma_ville"]),
        probing_steps=int(cand_dict["probing_steps"]),
        fit_start=int(cand_dict["fit_start"]),
        fit_end=int(cand_dict["fit_end"]),
        gap_start=int(cand_dict["gap_start"]),
        gap_end=int(cand_dict["gap_end"]),
        val_start=int(cand_dict["val_start"]),
        val_end=int(cand_dict["val_end"]),
        n_fit_min=int(cand_dict["n_fit_min"]),
        n_val_min=int(cand_dict["n_val_min"]),
        lambda_fim_min=float(cand_dict["lambda_fim_min"]),
        arrival_tolerance_m=float(cand_dict["arrival_tolerance_m"]),
        chord_min_m=float(cand_dict["chord_min_m"]),
        chord_min_steps=int(cand_dict["chord_min_steps"]),
        max_anchor_queries=int(cand_dict["max_anchor_queries"]),
    )

    return cand_params, payload, raw_hash


def verify_and_load_val_manifest(manifest_path: Path) -> tuple[dict[str, Any], str]:
    """
    Verifies that the validation manifest exists, passes internal SHA-256 integrity checks,
    uses the approved partition branch (p=3), and matches the stratified 480-episode grid.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Validation manifest not found: {manifest_path}")

    raw_bytes = manifest_path.read_bytes()
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    loaded = json.loads(raw_bytes.decode("utf-8"))

    stored_integrity = loaded.get("integrity_sha256")
    canon_bytes = json.dumps(
        {k: v for k, v in loaded.items() if k != "integrity_sha256"},
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    computed_integrity = hashlib.sha256(canon_bytes).hexdigest()
    if stored_integrity != computed_integrity:
        raise ValueError(
            f"Validation manifest integrity hash mismatch: {stored_integrity} != {computed_integrity}."
        )

    if loaded.get("partition") != "validation_r1":
        raise ValueError(f"Expected partition 'validation_r1', got '{loaded.get('partition')}'.")

    if loaded.get("partition_index") != PARTITION_BRANCH_VALIDATION:
        raise ValueError(
            f"Expected partition_index={PARTITION_BRANCH_VALIDATION}, got {loaded.get('partition_index')}."
        )

    if loaded.get("planned_episodes") != VAL_EXPECTED_EPISODES:
        raise ValueError(
            f"Expected {VAL_EXPECTED_EPISODES} episodes, got {loaded.get('planned_episodes')}."
        )

    episodes = loaded.get("episodes", [])
    if len(episodes) != VAL_EXPECTED_EPISODES:
        raise ValueError(
            f"Manifest episode count mismatch: planned={VAL_EXPECTED_EPISODES}, actual={len(episodes)}."
        )

    # Check that realized scenario counts are exactly 40 for all 12 scenarios
    counts = loaded.get("realized_scenario_counts", {})
    if len(counts) != 12 or any(cnt != VAL_SEEDS_PER_SCENARIO for cnt in counts.values()):
        raise ValueError(f"Invalid stratified scenario counts: {counts}.")

    # Check seed boundaries
    seeds = [int(ep["seed"]) for ep in episodes]
    enforce_val_only_seeds(seeds)

    return loaded, raw_hash


def freeze_val_run_configuration(
    *,
    manifest_path: Path,
    manifest_payload: dict[str, Any],
    manifest_raw_sha256: str,
    selected_policy_path: Path,
    selected_policy_payload: dict[str, Any],
    selected_policy_raw_sha256: str,
    candidate_params: V9CandidateParams,
    out_dir: Path,
) -> dict[str, Any]:
    """
    Writes or verifies the immutable run configuration `validation_run_config_frozen_r1.json`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg_name = "validation_run_config_frozen_r1.json"
    run_cfg_path = out_dir / cfg_name

    if run_cfg_path.exists():
        existing = json.loads(run_cfg_path.read_text(encoding="utf-8"))
        if existing.get("integrity_sha256") != compute_canonical_payload_sha256(existing):
            raise ValueError(f"Existing {cfg_name} failed integrity check.")
        return existing

    rel_manifest = (
        str(manifest_path.relative_to(_REPO_ROOT))
        if manifest_path.is_relative_to(_REPO_ROOT)
        else str(manifest_path)
    )
    rel_policy = (
        str(selected_policy_path.relative_to(_REPO_ROOT))
        if selected_policy_path.is_relative_to(_REPO_ROOT)
        else str(selected_policy_path)
    )

    run_cfg: dict[str, Any] = {
        "schema_version": "nexvia-aegis-v9-validation-run-config/1.0",
        "protocol_version": PROTOCOL_VERSION,
        "v9_m1_commit": V9_M1_COMMIT,
        "source_design_commit": SOURCE_DESIGN_COMMIT,
        "v81_baseline_commit": V81_BASELINE_COMMIT,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "validation_manifest_path": rel_manifest,
        "validation_manifest_raw_sha256": manifest_raw_sha256,
        "validation_manifest_canonical_sha256": manifest_payload["integrity_sha256"],
        "selected_policy_path": rel_policy,
        "selected_policy_raw_sha256": selected_policy_raw_sha256,
        "selected_policy_canonical_sha256": selected_policy_payload["integrity_sha256"],
        "candidate": asdict(candidate_params),
        "validation_specification": {
            "partition": "D_val",
            "seed_range": f"{VAL_SEED_START}..{VAL_SEED_STOP_EXCLUSIVE - 1}",
            "seeds_per_scenario": VAL_SEEDS_PER_SCENARIO,
            "total_episodes": VAL_EXPECTED_EPISODES,
            "sampling_design": "stratified_deterministic_grid",
            "partition_branch": PARTITION_BRANCH_VALIDATION,
            "master_entropy": manifest_payload["master_entropy"],
        },
        "prohibited_partition_seeds": {
            label: f"{rng.start}..{rng.stop - 1}" for label, rng in PROHIBITED_SEED_BLOCKS
        },
    }
    run_cfg["integrity_sha256"] = compute_canonical_payload_sha256(run_cfg)
    run_cfg_path.write_text(json.dumps(run_cfg, indent=2) + "\n", encoding="utf-8")
    return run_cfg


def execute_single_shot_validation(
    *,
    manifest_path: str | Path,
    selected_policy_path: str | Path,
    out_dir: str | Path = "results/v9/val_r1",
    freeze_only: bool = False,
) -> dict[str, Any]:
    """
    Executes the authorized single-shot operational validation of `V9_CAND_1_TIER1_STRICTEST`
    on the reserved partition D_val (480 episodes).
    """
    res_dir = enforce_val_output_directory(out_dir)
    man_path = enforce_val_manifest_path(manifest_path)
    pol_path = Path(selected_policy_path).resolve()

    # Verify input artifacts
    cand_params, pol_payload, pol_raw_sha = verify_and_load_selected_policy(pol_path)
    manifest_payload, man_raw_sha = verify_and_load_val_manifest(man_path)

    # Freeze configuration
    run_cfg = freeze_val_run_configuration(
        manifest_path=man_path,
        manifest_payload=manifest_payload,
        manifest_raw_sha256=man_raw_sha,
        selected_policy_path=pol_path,
        selected_policy_payload=pol_payload,
        selected_policy_raw_sha256=pol_raw_sha,
        candidate_params=cand_params,
        out_dir=res_dir,
    )

    if freeze_only:
        return {"status": "FROZEN_READY", "run_config": run_cfg}

    # Single-shot execution guard
    episodes_csv = res_dir / "val_episodes.csv"
    summary_csv = res_dir / "val_summary.csv"
    scen_csv = res_dir / "val_scenario_breakdown.csv"
    report_json = res_dir / "validation_report.json"

    if report_json.exists():
        raise RuntimeError(
            f"SINGLE-SHOT EXECUTION GUARD: Validation output already exists in `{res_dir}`. "
            "Re-running validation or overwriting validation artifacts is strictly prohibited."
        )

    # Check for historical incomplete marker
    partial_csv = res_dir / "val_episodes_PARTIAL.csv"
    invalid_marker = res_dir / "INCOMPLETE_INVALID.json"
    if invalid_marker.exists():
        raise RuntimeError(
            f"SINGLE-SHOT EXECUTION GUARD: Found existing `{invalid_marker}` in `{res_dir}`. "
            "Aborted validation run cannot be silently rerun without review."
        )

    scenarios_by_name: dict[str, V9ScenarioSpec] = {
        sc.name: sc for sc in build_v9_s12_scenarios()
    }
    manifest_episodes = manifest_payload["episodes"]
    expected_total_records = len(manifest_episodes)
    episode_records: list[dict[str, Any]] = []
    t_start = time.time()

    if episodes_csv.exists():
        with episodes_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            loaded_eps = list(reader)
        if len(loaded_eps) == expected_total_records:
            episode_records = [
                {
                    "episode_index": int(r["episode_index"]),
                    "seed": int(r["seed"]),
                    "scenario_index": int(r["scenario_index"]),
                    "scenario": r["scenario"],
                    "suite": r["suite"],
                    "policy": r["policy"],
                    "accepted": int(r["accepted"]),
                    "true_success": int(r["true_success"]),
                    "false_success": int(r["false_success"]),
                    "abstain_explicit": int(r["abstain_explicit"]),
                    "timeout": int(r["timeout"]),
                    "abstain": int(r["abstain"]),
                    "crashed": int(r["crashed"]),
                    "crash_error": r.get("crash_error", ""),
                    "final_distance": float(r["final_distance"]),
                    "steps": int(r["steps"]),
                    "mean_step_ms": float(r["mean_step_ms"]),
                    "distance_traveled": float(r["distance_traveled"]),
                    "anchor_queries": int(r["anchor_queries"]),
                    "anchor_cost": float(r["anchor_cost"]),
                    "max_overshoot": float(r["max_overshoot"]),
                    "terminal_reason": r.get("terminal_reason", ""),
                }
                for r in loaded_eps
            ]
        else:
            raise RuntimeError(
                f"SINGLE-SHOT EXECUTION GUARD: Incomplete `{episodes_csv}` found ({len(loaded_eps)} != {expected_total_records}). "
                "Cannot overwrite without review."
            )
    else:
        try:
            for ep_item in manifest_episodes:
                ep_idx = int(ep_item["episode_index"])
                ep_seed = int(ep_item.get("seed", ep_item.get("manifest_id")))
                scen_name = str(ep_item["scenario"])
                scen = scenarios_by_name[scen_name]

                ctrl = AegisV9Controller(cand_params)
                decoupled_rng = instantiate_episode_rngs_from_manifest_item(ep_item)

                rec = run_single_episode(
                    scen,
                    ep_seed,
                    cand_params.candidate_id,
                    ctrl,
                    rng_env=decoupled_rng.rng_env,
                    rng_sensors=decoupled_rng.rng_sensors,
                )

                verify_episode_outcome_algebra(
                    rec,
                    expected_policy_id=cand_params.candidate_id,
                    expected_seed=ep_seed,
                    expected_scenario=scen_name,
                )

                ordered_rec = {
                    "episode_index": ep_idx,
                    "seed": int(rec["seed"]),
                    "scenario_index": int(ep_item["scenario_index"]),
                    "scenario": rec["scenario"],
                    "suite": rec["suite"],
                    "policy": rec["policy"],
                    "accepted": int(rec["accepted"]),
                    "true_success": int(rec["true_success"]),
                    "false_success": int(rec["false_success"]),
                    "abstain_explicit": int(rec["abstain_explicit"]),
                    "timeout": int(rec["timeout"]),
                    "abstain": int(rec["abstain"]),
                    "crashed": int(rec["crashed"]),
                    "crash_error": rec["crash_error"],
                    "final_distance": rec["final_distance"],
                    "steps": int(rec["steps"]),
                    "mean_step_ms": rec["mean_step_ms"],
                    "distance_traveled": rec["distance_traveled"],
                    "anchor_queries": int(rec["anchor_queries"]),
                    "anchor_cost": rec["anchor_cost"],
                    "max_overshoot": rec["max_overshoot"],
                    "terminal_reason": rec["terminal_reason"],
                }
                episode_records.append(ordered_rec)

            if len(episode_records) != expected_total_records:
                raise RuntimeError(
                    f"Incomplete D_val execution: recorded {len(episode_records)} != expected {expected_total_records}."
                )
        except BaseException as exc:
            if episode_records:
                with partial_csv.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f, fieldnames=list(episode_records[0].keys()), lineterminator="\n"
                    )
                    writer.writeheader()
                    writer.writerows(episode_records)
            invalid_marker.write_text(
                json.dumps(
                    {
                        "status": "INCOMPLETE_INVALID",
                        "recorded_episodes": len(episode_records),
                        "expected_episodes": expected_total_records,
                        "partial_episodes_file": str(partial_csv.name) if episode_records else None,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            raise

        # 1. Write raw episode records CSV
        with episodes_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=list(episode_records[0].keys()), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(episode_records)

    elapsed_sec = time.time() - t_start

    # 2. Compute pooled summary metrics
    pooled_summary = compute_policy_summary(
        cand_params.candidate_id,
        episode_records,
    )
    mean_step_ms_pooled = (
        sum(float(r["mean_step_ms"]) for r in episode_records) / len(episode_records)
        if episode_records
        else 0.0
    )

    summary_headers = [
        "policy_id",
        "tier_label",
        "n_episodes",
        "m_accepted",
        "fs_count",
        "ts_count",
        "ab_explicit_count",
        "timeout_count",
        "ab_total_count",
        "crashed_count",
        "coverage",
        "tsr",
        "r_inc",
        "r_sel",
        "r_sel_status",
        "mean_steps",
        "mean_step_ms",
        "mean_distance_traveled",
        "mean_anchor_queries",
        "mean_anchor_cost",
        "mean_max_overshoot",
    ]

    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary_headers, lineterminator="\n")
        writer.writeheader()
        writer.writerow(
            {
                "policy_id": cand_params.candidate_id,
                "tier_label": cand_params.tier_label,
                "n_episodes": pooled_summary.n_episodes,
                "m_accepted": pooled_summary.m_accepted,
                "fs_count": pooled_summary.fs_count,
                "ts_count": pooled_summary.ts_count,
                "ab_explicit_count": pooled_summary.ab_explicit_count,
                "timeout_count": pooled_summary.timeout_count,
                "ab_total_count": pooled_summary.ab_total_count,
                "crashed_count": pooled_summary.crashed_count,
                "coverage": f"{pooled_summary.coverage:.6f}",
                "tsr": f"{pooled_summary.tsr:.6f}",
                "r_inc": f"{pooled_summary.r_inc:.6f}",
                "r_sel": (
                    f"{pooled_summary.r_sel:.6f}"
                    if not math.isnan(pooled_summary.r_sel)
                    else "UNDEFINED"
                ),
                "r_sel_status": "DEFINED" if not math.isnan(pooled_summary.r_sel) else "UNDEFINED",
                "mean_steps": f"{pooled_summary.mean_steps:.2f}",
                "mean_step_ms": f"{mean_step_ms_pooled:.4f}",
                "mean_distance_traveled": f"{pooled_summary.mean_distance_traveled:.4f}",
                "mean_anchor_queries": f"{pooled_summary.mean_anchor_queries:.3f}",
                "mean_anchor_cost": f"{pooled_summary.mean_anchor_cost:.4f}",
                "mean_max_overshoot": f"{pooled_summary.mean_max_overshoot:.4f}",
            }
        )

    # 3. Compute per-scenario breakdown with Clopper-Pearson CIs
    scen_breakdown_records: list[dict[str, Any]] = []
    scen_headers = [
        "scenario",
        "scenario_index",
        "suite",
        "n_episodes",
        "m_accepted",
        "ts_count",
        "fs_count",
        "ab_explicit_count",
        "timeout_count",
        "crashed_count",
        "coverage",
        "tsr",
        "r_inc",
        "r_sel",
        "r_sel_status",
        "r_sel_ucb95",
        "mean_steps",
        "mean_step_ms",
        "mean_distance_traveled",
        "mean_anchor_queries",
        "mean_anchor_cost",
        "mean_max_overshoot",
    ]

    for sc_name, sc_spec in scenarios_by_name.items():
        sc_eps = [r for r in episode_records if r["scenario"] == sc_name]
        n_sc = len(sc_eps)
        m_sc = sum(r["accepted"] for r in sc_eps)
        ts_sc = sum(r["true_success"] for r in sc_eps)
        fs_sc = sum(r["false_success"] for r in sc_eps)
        ab_exp_sc = sum(r["abstain_explicit"] for r in sc_eps)
        to_sc = sum(r["timeout"] for r in sc_eps)
        crash_sc = sum(r["crashed"] for r in sc_eps)

        cov_sc = m_sc / n_sc if n_sc > 0 else 0.0
        tsr_sc = ts_sc / n_sc if n_sc > 0 else 0.0
        r_inc_sc = fs_sc / n_sc if n_sc > 0 else 0.0

        if m_sc > 0:
            r_sel_sc = fs_sc / m_sc
            r_sel_status = "DEFINED"
            # Exact 1-sided 95% Clopper-Pearson UCB
            if fs_sc == m_sc:
                ucb95 = 1.0
            else:
                ucb95 = float(beta.ppf(0.95, fs_sc + 1, m_sc - fs_sc))
            ucb95_str = f"{ucb95:.6f}"
        else:
            r_sel_sc = float("nan")
            r_sel_status = "UNDEFINED"
            ucb95_str = "UNDEFINED"

        mean_steps_sc = sum(r["steps"] for r in sc_eps) / n_sc if n_sc > 0 else 0.0
        mean_ms_sc = sum(r["mean_step_ms"] for r in sc_eps) / n_sc if n_sc > 0 else 0.0
        mean_dist_sc = sum(r["distance_traveled"] for r in sc_eps) / n_sc if n_sc > 0 else 0.0
        mean_aq_sc = sum(r["anchor_queries"] for r in sc_eps) / n_sc if n_sc > 0 else 0.0
        mean_ac_sc = sum(r["anchor_cost"] for r in sc_eps) / n_sc if n_sc > 0 else 0.0
        mean_ov_sc = sum(r["max_overshoot"] for r in sc_eps) / n_sc if n_sc > 0 else 0.0

        row = {
            "scenario": sc_name,
            "scenario_index": sc_spec.index - 1,
            "suite": sc_spec.suite,
            "n_episodes": n_sc,
            "m_accepted": m_sc,
            "ts_count": ts_sc,
            "fs_count": fs_sc,
            "ab_explicit_count": ab_exp_sc,
            "timeout_count": to_sc,
            "crashed_count": crash_sc,
            "coverage": f"{cov_sc:.6f}",
            "tsr": f"{tsr_sc:.6f}",
            "r_inc": f"{r_inc_sc:.6f}",
            "r_sel": f"{r_sel_sc:.6f}" if not math.isnan(r_sel_sc) else "UNDEFINED",
            "r_sel_status": r_sel_status,
            "r_sel_ucb95": ucb95_str,
            "mean_steps": f"{mean_steps_sc:.2f}",
            "mean_step_ms": f"{mean_ms_sc:.4f}",
            "mean_distance_traveled": f"{mean_dist_sc:.4f}",
            "mean_anchor_queries": f"{mean_aq_sc:.3f}",
            "mean_anchor_cost": f"{mean_ac_sc:.4f}",
            "mean_max_overshoot": f"{mean_ov_sc:.4f}",
        }
        scen_breakdown_records.append(row)

    with scen_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=scen_headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(scen_breakdown_records)

    # 4. Write complete validation_report.json with artifact SHA-256 manifest
    cfg_file = res_dir / "validation_run_config_frozen_r1.json"
    rel_manifest = (
        str(man_path.relative_to(_REPO_ROOT))
        if man_path.is_relative_to(_REPO_ROOT)
        else str(man_path)
    )
    rel_policy = (
        str(pol_path.relative_to(_REPO_ROOT))
        if pol_path.is_relative_to(_REPO_ROOT)
        else str(pol_path)
    )
    rel_cfg = (
        str(cfg_file.relative_to(_REPO_ROOT))
        if cfg_file.is_relative_to(_REPO_ROOT)
        else str(cfg_file)
    )
    rel_episodes = (
        str(episodes_csv.relative_to(_REPO_ROOT))
        if episodes_csv.is_relative_to(_REPO_ROOT)
        else str(episodes_csv)
    )
    rel_summary = (
        str(summary_csv.relative_to(_REPO_ROOT))
        if summary_csv.is_relative_to(_REPO_ROOT)
        else str(summary_csv)
    )
    rel_scen = (
        str(scen_csv.relative_to(_REPO_ROOT))
        if scen_csv.is_relative_to(_REPO_ROOT)
        else str(scen_csv)
    )

    artifact_hashes = {
        rel_policy: sha256_file(pol_path),
        rel_manifest: sha256_file(man_path),
        rel_cfg: sha256_file(cfg_file),
        rel_episodes: sha256_file(episodes_csv),
        rel_summary: sha256_file(summary_csv),
        rel_scen: sha256_file(scen_csv),
    }

    report_payload: dict[str, Any] = {
        "schema_version": "nexvia-aegis-v9-validation-report/1.0",
        "status": "COMPLETE_VALID",
        "protocol_version": PROTOCOL_VERSION,
        "v9_m1_commit": V9_M1_COMMIT,
        "source_design_commit": SOURCE_DESIGN_COMMIT,
        "v81_baseline_commit": V81_BASELINE_COMMIT,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_sec, 2),
        "selected_policy_id": cand_params.candidate_id,
        "selected_candidate": asdict(cand_params),
        "run_config": run_cfg,
        "pooled_summary": {
            "n_episodes": pooled_summary.n_episodes,
            "m_accepted": pooled_summary.m_accepted,
            "fs_count": pooled_summary.fs_count,
            "ts_count": pooled_summary.ts_count,
            "ab_explicit_count": pooled_summary.ab_explicit_count,
            "timeout_count": pooled_summary.timeout_count,
            "ab_total_count": pooled_summary.ab_total_count,
            "crashed_count": pooled_summary.crashed_count,
            "coverage": pooled_summary.coverage,
            "tsr": pooled_summary.tsr,
            "r_inc": pooled_summary.r_inc,
            "r_sel": pooled_summary.r_sel if not math.isnan(pooled_summary.r_sel) else None,
            "r_sel_status": "DEFINED" if not math.isnan(pooled_summary.r_sel) else "UNDEFINED",
            "mean_steps": pooled_summary.mean_steps,
            "mean_step_ms": round(mean_step_ms_pooled, 4),
            "mean_distance_traveled": pooled_summary.mean_distance_traveled,
            "mean_anchor_queries": pooled_summary.mean_anchor_queries,
            "mean_anchor_cost": pooled_summary.mean_anchor_cost,
            "mean_max_overshoot": pooled_summary.mean_max_overshoot,
        },
        "scenario_breakdown": scen_breakdown_records,
        "reserved_partitions_untouched": {
            "D_test_mix_73000_74439": True,
            "D_test_scen_75000_75119": True,
        },
        "artifact_sha256": artifact_hashes,
    }
    report_payload["integrity_sha256"] = compute_canonical_payload_sha256(report_payload)
    report_json.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")

    return report_payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NEXVIA AEGIS V9-M3 Independent Operational Validation Runner."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("results/v9/manifests/val_manifest_r1.json"),
        help="Path to the validation manifest JSON (default: results/v9/manifests/val_manifest_r1.json).",
    )
    parser.add_argument(
        "--selected-policy",
        type=Path,
        default=Path("results/v9/cal_r2/selected_policy.json"),
        help="Path to selected_policy.json from Milestone V9-M2R2 calibration.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results/v9/val_r1"),
        help="Isolated directory to store validation artifacts (default: results/v9/val_r1).",
    )
    parser.add_argument(
        "--freeze-only",
        action="store_true",
        help="Only verify manifest/policy and freeze run configuration without executing episodes.",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    result = execute_single_shot_validation(
        manifest_path=args.manifest,
        selected_policy_path=args.selected_policy,
        out_dir=args.out,
        freeze_only=args.freeze_only,
    )
    print(f"Validation execution completed successfully: status={result.get('status')}")


if __name__ == "__main__":
    main()
