"""
NEXVIA AEGIS V9.0 — Milestone V9-M2 Single-Shot Fixed-Sequence LTT Calibration Runner.

GOVERNANCE & PARTITION GUARDRAILS (`docs/v9_risk_calibration_design.md` Section 2.4-2.5,
`docs/v9_experiment_protocol.md` Sections 3.1-3.6):
- Evaluates EXCLUSIVELY the 6 frozen candidate policies from `configs/v9_candidates_frozen.json`
  (verified against its canonical SHA-256 and raw file SHA-256) in their exact preregistered
  sequence j = 1..6.
- Uses EXCLUSIVELY the preregistered i.i.d. uniform 12-scenario mixture calibration partition
  `D_cal` (`N_cal = 960`, seeds `71000..71959`, scenario indices drawn once via
  `np.random.default_rng(20260901).integers(0, 12, size=960)`).
- HARD PROHIBITION: Any seed outside `71000..71959` (including `D_hist` `60000..60049`,
  `D_dev` `70000..70029`, `D_val` `72000..72039`, `D_test^mix` `73000..74439`, and
  `D_test^scen` `75000..75119`) is strictly blocked with `ValueError`.
- SINGLE-SHOT EXECUTION GUARD: Refuses to run or overwrite if any episode record or calibration
  report already exists in the calibration output directory. On any mid-run technical failure,
  preserves partial outputs (`cal_episodes_PARTIAL.csv` + `INCOMPLETE_INVALID.json`) without
  deletion.
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
from aegis.v9.risk_statistics import (
    PREREGISTERED_CANDIDATE_FAMILY,
    PolicyEvaluationSummary,
    V9CandidateParams,
    compute_canonical_payload_sha256,
    compute_policy_summary,
    fixed_sequence_ltt_select,
    holm_stepdown_ltt,
    load_frozen_candidates_json,
    minimum_zero_error_acceptances,
    selective_risk_pvalue,
)
from experiments.v9_evaluate_dev import (
    V9ScenarioSpec,
    build_v9_s12_scenarios,
    run_single_episode,
)

PROTOCOL_VERSION: str = "v9.0-preregistered-2026-10"
V9_M1_COMMIT: str = "6c87f66a9ea602c96d4fe8bfc97728d0513b157f"
SOURCE_DESIGN_COMMIT: str = "891c13e7bbd60e36c416c9bada8407e51233e663"
V81_BASELINE_COMMIT: str = "4d891c7500cfb4c8110f276038455bc62765ef3b"

EXPECTED_FROZEN_CANONICAL_SHA256: str = (
    "04d44b759ee4f5bbf9e2c8667d6f85e0df90fcea366313a39868c0b3a1b7a779"
)
EXPECTED_FROZEN_CANONICAL_SHA256_R1: str = (
    "732862c33d5a2e987bd2065e83b92bec5ad4ffb16a9c3b56a7b15ec6cb9b4d72"
)

CAL_MANIFEST_PRNG_SEED: int = 20260901
CAL_SEED_START: int = 71000
CAL_SEED_STOP_EXCLUSIVE: int = 71960
CAL_R1_SEED_START: int = 76000
CAL_R1_SEED_STOP_EXCLUSIVE: int = 76960
CAL_EXPECTED_EPISODES: int = 960
CAL_ALLOWED_SEEDS: frozenset[int] = (
    frozenset(range(CAL_SEED_START, CAL_SEED_STOP_EXCLUSIVE))
    | frozenset(range(CAL_R1_SEED_START, CAL_R1_SEED_STOP_EXCLUSIVE))
)

ALPHA_TARGET: float = 0.05
SIGNIFICANCE_DELTA: float = 0.05
C_MIN_EMPIRICAL: float = 0.35


def sha256_file(path: Path) -> str:
    """Returns hex SHA-256 digest of a file's exact raw bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def enforce_cal_only_seeds(seeds: Sequence[int]) -> tuple[int, ...]:
    """Blocks any seed outside permitted calibration partitions (71000..71959 or 76000..76959)."""
    if not seeds:
        raise ValueError("Calibration seed sequence must be non-empty.")
    out = tuple(int(s) for s in seeds)
    forbidden = [s for s in out if s not in CAL_ALLOWED_SEEDS]
    if forbidden:
        raise ValueError(
            f"PROHIBITED SEED ACCESS BLOCKED: {forbidden[:10]}. "
            f"Permitted calibration seeds are 71000..71959 (historical) or 76000..76959 (fresh r1)."
        )
    if len(set(out)) != len(out):
        raise ValueError("Duplicate episode seeds are prohibited in calibration.")
    if len(out) != CAL_EXPECTED_EPISODES:
        raise ValueError(
            f"Calibration partition requires exact N={CAL_EXPECTED_EPISODES} episodes, got len={len(out)}."
        )
    return out


def enforce_cal_output_directory(out_dir: str | Path) -> Path:
    """Ensures calibration outputs are written strictly under `results/v9/cal` or `results/v9/cal_r1`."""
    resolved = Path(out_dir).resolve()
    parts = resolved.parts
    if len(parts) < 3 or parts[-2] != "v9" or not parts[-1].startswith("cal"):
        raise ValueError(
            f"Calibration output path `{resolved}` must end with `results/v9/cal` or `results/v9/cal_r1` "
            "to isolate calibration artifacts from D_dev, historical results, and holdout splits."
        )
    return resolved


def enforce_cal_manifest_path(manifest_path: str | Path) -> Path:
    """Ensures calibration manifest is located strictly inside `results/v9/manifests`."""
    resolved = Path(manifest_path).resolve()
    parts = resolved.parts
    if len(parts) < 4 or parts[-4:-1] != ("results", "v9", "manifests") or not parts[-1].endswith(".json"):
        raise ValueError(
            f"Calibration manifest path `{resolved}` must be inside `results/v9/manifests/`."
        )
    return resolved


def build_preregistered_cal_manifest_payload() -> dict[str, Any]:
    """
    Constructs the exact preregistered D_cal manifest (`docs/v9_experiment_protocol.md`
    Section 3.6.1 item 3):
        rng_manifest = np.random.default_rng(20260901)
        scen_idx = rng_manifest.integers(0, 12, size=960)
    paired 1-to-1 with unique episode seeds 71000..71959.
    """
    scenarios = build_v9_s12_scenarios()
    if len(scenarios) != 12:
        raise RuntimeError(f"Expected 12 scenarios in S_12, got {len(scenarios)}.")

    seeds = enforce_cal_only_seeds(range(CAL_SEED_START, CAL_SEED_STOP_EXCLUSIVE))
    rng_manifest = np.random.default_rng(CAL_MANIFEST_PRNG_SEED)
    scen_indices = rng_manifest.integers(0, len(scenarios), size=CAL_EXPECTED_EPISODES)

    episodes: list[dict[str, Any]] = []
    pairs_for_hash: list[tuple[str, int]] = []
    counts: Counter[str] = Counter()

    for idx, (ep_seed, sc_idx_raw) in enumerate(zip(seeds, scen_indices, strict=True)):
        sc_idx = int(sc_idx_raw)
        scen = scenarios[sc_idx]
        counts[scen.name] += 1
        episodes.append(
            {
                "episode_index": idx,
                "seed": int(ep_seed),
                "scenario_index": sc_idx,
                "scenario": scen.name,
                "suite": scen.suite,
            }
        )
        pairs_for_hash.append((scen.name, int(ep_seed)))

    episodes_sha256 = hashlib.sha256(
        json.dumps(pairs_for_hash, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

    payload: dict[str, Any] = {
        "schema_version": "nexvia-aegis-v9-cal-manifest/1.0",
        "protocol_version": PROTOCOL_VERSION,
        "partition": "D_cal",
        "sampling_law": "iid_uniform_mixture_P12",
        "manifest_prng": "numpy.random.default_rng(20260901) [PCG64]",
        "manifest_prng_seed": CAL_MANIFEST_PRNG_SEED,
        "num_scenarios": len(scenarios),
        "scenario_catalog": [sc.name for sc in scenarios],
        "target_mixture_weights_rational": {sc.name: "1/12" for sc in scenarios},
        "target_mixture_weights_float": {sc.name: 1.0 / 12.0 for sc in scenarios},
        "seed_start": CAL_SEED_START,
        "seed_end_inclusive": CAL_SEED_STOP_EXCLUSIVE - 1,
        "n_episodes": CAL_EXPECTED_EPISODES,
        "realized_scenario_counts": {sc.name: int(counts[sc.name]) for sc in scenarios},
        "episodes_sha256": episodes_sha256,
        "episodes": episodes,
    }
    payload["integrity_sha256"] = compute_canonical_payload_sha256(payload)
    return payload


def freeze_or_verify_cal_manifest(manifest_path: Path) -> tuple[dict[str, Any], str]:
    """
    Writes `cal_manifest.json` if absent, or verifies an existing `cal_manifest.json`
    bit-for-bit against the deterministic preregistered specification.
    """
    if "r1" in manifest_path.name or "r2" in manifest_path.name:
        if not manifest_path.exists():
            raise FileNotFoundError(f"Fresh calibration manifest not found: {manifest_path}")
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        is_r2 = ("r2" in manifest_path.name)
        expected_part = ("D_cal,r2", "calibration_r2") if is_r2 else ("D_cal,r1", "calibration_r1")
        if loaded.get("partition") not in expected_part:
            raise ValueError(f"Expected partition in {expected_part}, got {loaded.get('partition')}")
        if loaded.get("planned_episodes") != CAL_EXPECTED_EPISODES:
            raise ValueError(f"Expected {CAL_EXPECTED_EPISODES} episodes, got {loaded.get('planned_episodes')}")
        if (
            loaded.get("manifest_id_start") != CAL_R1_SEED_START
            or loaded.get("manifest_id_stop_exclusive") != CAL_R1_SEED_STOP_EXCLUSIVE
        ):
            raise ValueError("Manifest ID range mismatch for D_cal.")
        stored_integrity = loaded.get("integrity_sha256")
        canon_bytes = json.dumps(
            {k: v for k, v in loaded.items() if k != "integrity_sha256"},
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        computed_integrity = hashlib.sha256(canon_bytes).hexdigest()
        if stored_integrity != computed_integrity:
            raise ValueError(f"{manifest_path.name} integrity hash mismatch: {stored_integrity} != {computed_integrity}")
        return loaded, sha256_file(manifest_path)

    expected = build_preregistered_cal_manifest_payload()
    if manifest_path.exists():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual_canon = compute_canonical_payload_sha256(loaded)
        if loaded.get("integrity_sha256") != actual_canon:
            raise ValueError("Existing cal_manifest.json failed internal SHA-256 verification.")
        if loaded != expected:
            raise ValueError(
                "Existing cal_manifest.json does not match deterministic preregistered D_cal specification."
            )
        return loaded, sha256_file(manifest_path)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    return expected, sha256_file(manifest_path)


def verify_and_load_frozen_candidates(
    candidates_path: Path,
) -> tuple[tuple[V9CandidateParams, ...], dict[str, Any], str]:
    """
    Verifies raw file SHA-256, canonical payload SHA-256, schema, and exact 6-candidate
    preregistered order before any calibration episode is executed.
    """
    if not candidates_path.exists():
        raise FileNotFoundError(f"Frozen candidate config not found: {candidates_path}")

    raw_sha = sha256_file(candidates_path)
    candidates, meta = load_frozen_candidates_json(candidates_path)
    if "r1" in candidates_path.name:
        if meta["integrity_sha256"] != EXPECTED_FROZEN_CANONICAL_SHA256_R1:
            raise ValueError(
                f"Frozen candidate canonical SHA-256 mismatch: expected {EXPECTED_FROZEN_CANONICAL_SHA256_R1}, got {meta['integrity_sha256']}."
            )
    else:
        if raw_sha != EXPECTED_FROZEN_RAW_SHA256:
            raise ValueError(
                f"Frozen candidate raw file SHA-256 mismatch: expected {EXPECTED_FROZEN_RAW_SHA256}, got {raw_sha}."
            )
        if meta["integrity_sha256"] != EXPECTED_FROZEN_CANONICAL_SHA256:
            raise ValueError(
                "Frozen candidate canonical SHA-256 mismatch: "
                f"expected {EXPECTED_FROZEN_CANONICAL_SHA256}, got {meta['integrity_sha256']}."
            )
    if candidates != PREREGISTERED_CANDIDATE_FAMILY:
        raise ValueError(
            "Loaded candidates do not match PREREGISTERED_CANDIDATE_FAMILY in exact order."
        )
    return candidates, meta, raw_sha


def verify_episode_outcome_algebra(
    rec: dict[str, Any],
    *,
    expected_policy_id: str,
    expected_seed: int,
    expected_scenario: str,
) -> None:
    """
    Asserts that an episode record satisfies the exact benchmark outcome partition
    (`docs/v9_risk_calibration_design.md` Section 2.1.1 & `docs/v9_experiment_protocol.md` Section 3.1.3).
    """
    if rec["policy"] != expected_policy_id:
        raise RuntimeError(f"Policy ID mismatch: {rec['policy']} != {expected_policy_id}")
    if int(rec["seed"]) != expected_seed:
        raise RuntimeError(f"Seed mismatch: {rec['seed']} != {expected_seed}")
    if rec["scenario"] != expected_scenario:
        raise RuntimeError(f"Scenario mismatch: {rec['scenario']} != {expected_scenario}")

    acc = int(rec["accepted"])
    ts = int(rec["true_success"])
    fs = int(rec["false_success"])
    ab_exp = int(rec["abstain_explicit"])
    to = int(rec["timeout"])
    ab = int(rec["abstain"])
    crashed = int(rec["crashed"])

    for flag in (acc, ts, fs, ab_exp, to, ab, crashed):
        if flag not in (0, 1):
            raise RuntimeError(f"Non-binary outcome indicator in record: {rec}")

    if crashed == 1:
        if not (acc == 0 and ts == 0 and fs == 1 and ab_exp == 0 and to == 0 and ab == 0):
            raise RuntimeError(f"Invalid fail-unsafe crash accounting in record: {rec}")
    else:
        if acc != ts + fs:
            raise RuntimeError(f"Acceptance identity A == TS + FS violated: {rec}")
        if ab != ab_exp + to or ab != 1 - acc:
            raise RuntimeError(f"Abstention identity AB == AB_exp + TO == 1 - A violated: {rec}")
        if ts + fs + ab_exp + to != 1:
            raise RuntimeError(
                f"Outcome partition TS + FS + AB_exp + TO == 1 violated: {rec}"
            )


def _format_float_or_undef(val: float, digits: int = 6) -> str:
    if math.isnan(val):
        return "UNDEFINED"
    return f"{val:.{digits}f}"


def _coverage_one_sided_lcb(m_accepted: int, n_episodes: int, delta: float = 0.05) -> float:
    """Descriptive exact one-sided (1-delta) Clopper-Pearson lower bound on coverage C."""
    if m_accepted <= 0:
        return 0.0
    if m_accepted >= n_episodes:
        return 1.0
    return float(beta.ppf(delta, m_accepted, n_episodes - m_accepted + 1))


def freeze_run_configuration(
    *,
    manifest_path: Path,
    candidates_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """
    Phase 3: Verifies inputs, locks `cal_manifest.json` and writes
    `calibration_run_config_frozen.json` prior to executing any calibration episode.
    """
    candidates, cand_meta, cand_raw_sha = verify_and_load_frozen_candidates(candidates_path)
    manifest_payload, manifest_raw_sha = freeze_or_verify_cal_manifest(manifest_path)

    m_min_0 = minimum_zero_error_acceptances(ALPHA_TARGET, SIGNIFICANCE_DELTA)
    m_min_cov = int(math.ceil(C_MIN_EMPIRICAL * CAL_EXPECTED_EPISODES))
    m_min_eff = max(m_min_0, m_min_cov)

    out_dir.mkdir(parents=True, exist_ok=True)
    is_r2 = ("r2" in manifest_path.name)
    is_r1 = ("r1" in manifest_path.name and not is_r2)
    cfg_name = (
        "calibration_run_config_frozen_r2.json"
        if is_r2
        else ("calibration_run_config_frozen_r1.json" if is_r1 else "calibration_run_config_frozen.json")
    )
    run_cfg_path = out_dir / cfg_name

    if (is_r1 or is_r2) and run_cfg_path.exists():
        existing = json.loads(run_cfg_path.read_text(encoding="utf-8"))
        if existing.get("integrity_sha256") != compute_canonical_payload_sha256(existing):
            raise ValueError(f"Existing {cfg_name} failed integrity check.")
        return existing

    spec = cand_meta["ltt_calibration_spec"]
    if (
        spec["primary_method"] != "FIXED_SEQUENCE_LTT"
        or float(spec["alpha_target"]) != ALPHA_TARGET
        or float(spec["delta"]) != SIGNIFICANCE_DELTA
        or float(spec["c_min"]) != C_MIN_EMPIRICAL
        or int(spec["m_min_zero_error"]) != m_min_0
    ):
        raise ValueError(f"Unexpected ltt_calibration_spec in frozen config: {spec}")

    run_cfg: dict[str, Any] = {
        "schema_version": "nexvia-aegis-v9-cal-run-config/1.0",
        "protocol_version": PROTOCOL_VERSION,
        "v9_m1_commit": V9_M1_COMMIT,
        "source_design_commit": SOURCE_DESIGN_COMMIT,
        "v81_baseline_commit": V81_BASELINE_COMMIT,
        "frozen_candidates_path": "configs/v9_candidates_frozen.json",
        "frozen_candidates_canonical_sha256": cand_meta["integrity_sha256"],
        "frozen_candidates_raw_sha256": cand_raw_sha,
        "cal_manifest_path": "results/v9/manifests/cal_manifest.json",
        "cal_manifest_canonical_sha256": manifest_payload["integrity_sha256"],
        "cal_manifest_raw_sha256": manifest_raw_sha,
        "cal_manifest_episodes_sha256": manifest_payload["episodes_sha256"],
        "partition": "D_cal",
        "sampling_law": "iid_uniform_mixture_P12",
        "manifest_prng_seed": CAL_MANIFEST_PRNG_SEED,
        "seed_range": [CAL_SEED_START, CAL_SEED_STOP_EXCLUSIVE - 1],
        "n_episodes_per_candidate": CAL_EXPECTED_EPISODES,
        "num_candidates": len(candidates),
        "total_planned_episodes": CAL_EXPECTED_EPISODES * len(candidates),
        "scenario_mixture_weights": manifest_payload["target_mixture_weights_rational"],
        "realized_scenario_counts_in_d_cal": manifest_payload["realized_scenario_counts"],
        "statistical_procedure": {
            "primary_method": "FIXED_SEQUENCE_LTT",
            "sensitivity_comparator": "HOLM_STEPDOWN_LTT",
            "target_selective_risk_alpha": ALPHA_TARGET,
            "significance_level_delta": SIGNIFICANCE_DELTA,
            "composite_null_hypothesis": (
                "H_0^{sel}(lambda): {C(pi_lambda; P_12) = 0} U "
                "{C(pi_lambda; P_12) > 0 and R_sel(pi_lambda; P_12) >= 0.05}"
            ),
            "certified_alternative_hypothesis": (
                "H_1^{sel}(lambda): C(pi_lambda; P_12) > 0 and R_sel(pi_lambda; P_12) <= 0.05"
            ),
            "c_min_value": C_MIN_EMPIRICAL,
            "c_min_role": (
                "EMPIRICAL_CALIBRATION_ELIGIBILITY_GUARDRAIL "
                "(enforced via M_cal >= ceil(0.35 * 960) = 336 in p_sel; "
                "NOT claimed as a population coverage >= 0.35 statistical guarantee)"
            ),
            "m_min_zero_error": m_min_0,
            "m_min_effective": m_min_eff,
            "candidate_order": [c.candidate_id for c in candidates],
            "stopping_rule": (
                "Test j=1..6 strictly in sequence at full delta=0.05; stop immediately at the "
                "first j* where p_sel(lambda^{(j*)}) > 0.05 (with M < 336 yielding p_sel = 1.0); "
                "never skip a failed candidate to certify any j > j*."
            ),
            "selection_rule_within_certified_prefix": spec["selection_rule"],
            "uncertified_outcome_if_j1_fails": "V9_CALIBRATION_UNCERTIFIED (selected_candidate = None)",
        },
        "reserved_untouched_partitions": {
            "D_val": "72000..72039",
            "D_test_mix": "73000..74439",
            "D_test_scen": "75000..75119",
        },
    }
    run_cfg["integrity_sha256"] = compute_canonical_payload_sha256(run_cfg)

    if run_cfg_path.exists():
        existing = json.loads(run_cfg_path.read_text(encoding="utf-8"))
        if existing != run_cfg:
            raise ValueError("Existing calibration_run_config_frozen.json differs from locked spec.")
    else:
        run_cfg_path.write_text(json.dumps(run_cfg, indent=2) + "\n", encoding="utf-8")

    return run_cfg


def execute_single_shot_calibration(
    *,
    manifest_path: str | Path = "results/v9/manifests/cal_manifest.json",
    candidates_path: str | Path = "configs/v9_candidates_frozen.json",
    out_dir: str | Path = "results/v9/cal",
    freeze_only: bool = False,
) -> dict[str, Any]:
    """
    Freezes run configuration and (unless `freeze_only=True`) executes single-shot V9-M2
    calibration across the 6 frozen candidates on D_cal (`N = 960` matched episodes).
    """
    man_path = enforce_cal_manifest_path(manifest_path)
    cand_path = Path(candidates_path).resolve()
    res_dir = enforce_cal_output_directory(out_dir)

    guard_files = (
        "cal_episodes.csv",
        "cal_episodes_PARTIAL.csv",
        "cal_candidate_summary.csv",
        "calibration_report.json",
        "selected_policy.json",
        "INCOMPLETE_INVALID.json",
    )
    if not freeze_only and res_dir.exists():
        existing_hits = [name for name in guard_files if (res_dir / name).exists()]
        if existing_hits:
            raise RuntimeError(
                f"SINGLE-SHOT CALIBRATION GUARD TRIGGERED: `{res_dir}` already contains "
                f"prior run artifacts {existing_hits}. Refusing to re-run or overwrite D_cal."
            )

    run_cfg = freeze_run_configuration(
        manifest_path=man_path,
        candidates_path=cand_path,
        out_dir=res_dir,
    )
    if freeze_only:
        return {"status": "FROZEN_READY", "run_config": run_cfg}

    if "r1" in man_path.name or "r2" in man_path.name:
        raise RuntimeError(
            "EXECUTION GUARD: Single-shot calibration for V9-M2R1/R2 (D_cal 76000..76959) is deferred "
            "pending independent protocol review. Calibration episodes must NOT be generated or executed in Milestone V9-M2R1."
        )

    candidates, _, _ = verify_and_load_frozen_candidates(cand_path)
    manifest_payload, _ = freeze_or_verify_cal_manifest(man_path)

    scenarios_by_name: dict[str, V9ScenarioSpec] = {
        sc.name: sc for sc in build_v9_s12_scenarios()
    }
    manifest_episodes = manifest_payload["episodes"]
    enforce_cal_only_seeds([int(item["seed"]) for item in manifest_episodes])

    expected_total_records = len(manifest_episodes) * len(candidates)
    episode_records: list[dict[str, Any]] = []
    t_start = time.time()

    partial_csv = res_dir / "cal_episodes_PARTIAL.csv"
    invalid_marker = res_dir / "INCOMPLETE_INVALID.json"

    try:
        for ep_item in manifest_episodes:
            ep_idx = int(ep_item["episode_index"])
            ep_seed = int(ep_item["seed"])
            scen_name = str(ep_item["scenario"])
            scen = scenarios_by_name[scen_name]

            for cand in candidates:
                ctrl = AegisV9Controller(cand)
                rec = run_single_episode(scen, ep_seed, cand.candidate_id, ctrl)
                verify_episode_outcome_algebra(
                    rec,
                    expected_policy_id=cand.candidate_id,
                    expected_seed=ep_seed,
                    expected_scenario=scen_name,
                )
                ordered_rec = {
                    "episode_index": ep_idx,
                    "seed": int(rec["seed"]),
                    "scenario_index": int(ep_item["scenario_index"]),
                    "scenario": rec["scenario"],
                    "suite": rec["suite"],
                    "sequence_position": cand.tier_index,
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
                f"Incomplete D_cal execution: recorded {len(episode_records)} != expected {expected_total_records}."
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

    elapsed_sec = time.time() - t_start

    # 1. Write complete raw episode records CSV (LF line endings)
    episodes_csv = res_dir / "cal_episodes.csv"
    with episodes_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(episode_records[0].keys()), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(episode_records)

    # 2. Compute per-candidate summaries and run Fixed-Sequence LTT EXACTLY ONCE
    m_min_0 = minimum_zero_error_acceptances(ALPHA_TARGET, SIGNIFICANCE_DELTA)
    m_min_eff = max(m_min_0, int(math.ceil(C_MIN_EMPIRICAL * CAL_EXPECTED_EPISODES)))

    ordered_for_ltt: list[tuple[V9CandidateParams, PolicyEvaluationSummary]] = []
    step_ms_by_cand: dict[str, float] = {}
    fs_stop_by_cand: dict[str, int] = {}
    clean_acc_by_cand: dict[str, int] = {}

    for cand in candidates:
        c_eps = [r for r in episode_records if r["policy"] == cand.candidate_id]
        if len(c_eps) != CAL_EXPECTED_EPISODES:
            raise RuntimeError(
                f"Candidate {cand.candidate_id} episode count {len(c_eps)} != {CAL_EXPECTED_EPISODES}."
            )
        summ = compute_policy_summary(
            cand.candidate_id,
            c_eps,
            alpha_target=ALPHA_TARGET,
            delta=SIGNIFICANCE_DELTA,
            m_min=m_min_eff,
        )
        ordered_for_ltt.append((cand, summ))
        step_ms_by_cand[cand.candidate_id] = float(
            sum(float(r["mean_step_ms"]) for r in c_eps) / len(c_eps)
        )
        fs_stop_by_cand[cand.candidate_id] = sum(
            1 for r in c_eps if int(r["accepted"]) == 1 and int(r["false_success"]) == 1
        )
        clean_acc_by_cand[cand.candidate_id] = sum(int(r["accepted"]) for r in c_eps)

    ltt_res = fixed_sequence_ltt_select(
        ordered_for_ltt,
        alpha_target=ALPHA_TARGET,
        delta=SIGNIFICANCE_DELTA,
        c_min=C_MIN_EMPIRICAL,
    )
    holm_certified_ids = set(
        holm_stepdown_ltt(
            ordered_for_ltt,
            alpha_target=ALPHA_TARGET,
            delta=SIGNIFICANCE_DELTA,
            c_min=C_MIN_EMPIRICAL,
        )
    )

    if ltt_res.stopped_at_position is None:
        overall_stop_reason = (
            "ALL_6_CANDIDATES_CERTIFIED_NO_EARLY_STOP "
            "(every candidate j=1..6 satisfied M_cal >= 336 and p_sel <= 0.05)"
        )
    else:
        stop_idx = ltt_res.stopped_at_position
        stop_rec = ltt_res.records[stop_idx - 1]
        if stop_rec.m_accepted < m_min_eff:
            overall_stop_reason = (
                f"STOPPED_AT_POSITION_{stop_idx}_{stop_rec.candidate_id}_"
                f"INSUFFICIENT_EMPIRICAL_COVERAGE_M_{stop_rec.m_accepted}_LT_{m_min_eff}"
            )
        else:
            overall_stop_reason = (
                f"STOPPED_AT_POSITION_{stop_idx}_{stop_rec.candidate_id}_"
                f"SELECTIVE_RISK_PVALUE_{stop_rec.p_value:.8f}_GT_DELTA_{SIGNIFICANCE_DELTA}"
            )

    # 3. Build per-candidate summary table (all Phase 4 required columns)
    summary_rows: list[dict[str, Any]] = []
    for (cand, summ), rec_ltt in zip(ordered_for_ltt, ltt_res.records, strict=True):
        pos = cand.tier_index
        p_check = selective_risk_pvalue(
            summ.fs_count,
            summ.m_accepted,
            alpha_target=ALPHA_TARGET,
            m_min=m_min_eff,
        )
        if not math.isclose(p_check, rec_ltt.p_value, rel_tol=0.0, abs_tol=1e-15):
            raise RuntimeError("Internal p-value mismatch between summary and LTT record.")

        unmasked_binom = (
            float("nan")
            if summ.m_accepted == 0
            else float(binom.cdf(summ.fs_count, summ.m_accepted, ALPHA_TARGET))
        )
        cov_eligible = summ.m_accepted >= m_min_eff
        cov_lcb95 = _coverage_one_sided_lcb(
            summ.m_accepted, summ.n_episodes, delta=SIGNIFICANCE_DELTA
        )

        fst_evaluated = (
            ltt_res.stopped_at_position is None or pos <= ltt_res.stopped_at_position
        )
        step_test_passed = bool(cov_eligible and (rec_ltt.p_value <= SIGNIFICANCE_DELTA))
        is_certified = bool(rec_ltt.passed_step)
        is_selected = (
            ltt_res.selected_candidate is not None
            and cand.candidate_id == ltt_res.selected_candidate.candidate_id
        )

        if ltt_res.stopped_at_position is None:
            row_stop_note = (
                "PASSED_FINAL_CANDIDATE" if pos == len(candidates) else "PASSED_CONTINUE"
            )
        elif pos < ltt_res.stopped_at_position:
            row_stop_note = "PASSED_CONTINUE"
        elif pos == ltt_res.stopped_at_position:
            row_stop_note = (
                "STOPPED_HERE_COVERAGE_INELIGIBLE"
                if not cov_eligible
                else "STOPPED_HERE_P_SEL_GT_DELTA"
            )
        else:
            row_stop_note = "NOT_CERTIFIED_BLOCKED_BY_EARLIER_STOP"

        summary_rows.append(
            {
                "sequence_position": pos,
                "candidate_id": cand.candidate_id,
                "tier_label": cand.tier_label,
                "n_episodes": summ.n_episodes,
                "m_accepted": summ.m_accepted,
                "m_clean_stops": clean_acc_by_cand[cand.candidate_id],
                "fs_count": summ.fs_count,
                "fs_stop_count": fs_stop_by_cand[cand.candidate_id],
                "crashed_count": summ.crashed_count,
                "ts_count": summ.ts_count,
                "ab_explicit_count": summ.ab_explicit_count,
                "timeout_count": summ.timeout_count,
                "ab_total_count": summ.ab_total_count,
                "coverage": f"{summ.coverage:.6f}",
                "tsr": f"{summ.tsr:.6f}",
                "r_inc": f"{summ.r_inc:.6f}",
                "r_inc_ucb95_descriptive": f"{summ.r_inc_ucb95:.6f}",
                "r_sel_status": summ.r_sel_status,
                "r_sel": _format_float_or_undef(summ.r_sel, 6),
                "r_sel_ucb95_descriptive": _format_float_or_undef(summ.r_sel_ucb95, 6),
                "p_sel": f"{rec_ltt.p_value:.10e}",
                "binom_cdf_unmasked": (
                    "UNDEFINED" if math.isnan(unmasked_binom) else f"{unmasked_binom:.10e}"
                ),
                "c_min_empirical_target": f"{C_MIN_EMPIRICAL:.2f}",
                "m_min_effective": m_min_eff,
                "coverage_lcb95_descriptive": f"{cov_lcb95:.6f}",
                "calibration_eligible": cov_eligible,
                "fst_evaluated_before_or_at_stop": fst_evaluated,
                "single_step_test_passed": step_test_passed,
                "fst_certified": is_certified,
                "selected_by_ltt": is_selected,
                "fst_step_outcome": row_stop_note,
                "holm_sensitivity_certified": cand.candidate_id in holm_certified_ids,
                "mean_steps": f"{summ.mean_steps:.2f}",
                "mean_step_ms": f"{step_ms_by_cand[cand.candidate_id]:.4f}",
                "mean_distance_traveled": f"{summ.mean_distance_traveled:.4f}",
                "mean_anchor_queries": f"{summ.mean_anchor_queries:.3f}",
                "mean_anchor_cost": f"{summ.mean_anchor_cost:.4f}",
                "mean_max_overshoot": f"{summ.mean_max_overshoot:.4f}",
            }
        )

    summary_csv = res_dir / "cal_candidate_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(summary_rows[0].keys()), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    # 4. Write descriptive per-scenario diagnostic breakdown (explicitly non-certifying)
    scen_rows: list[dict[str, Any]] = []
    for cand in candidates:
        c_eps = [r for r in episode_records if r["policy"] == cand.candidate_id]
        for sc in build_v9_s12_scenarios():
            s_eps = [r for r in c_eps if r["scenario"] == sc.name]
            if not s_eps:
                scen_rows.append(
                    {
                        "policy": cand.candidate_id,
                        "scenario": sc.name,
                        "suite": sc.suite,
                        "n_episodes": 0,
                        "m_accepted": 0,
                        "ts_count": 0,
                        "fs_count": 0,
                        "ab_explicit_count": 0,
                        "timeout_count": 0,
                        "crashed_count": 0,
                        "coverage": "UNDEFINED",
                        "tsr": "UNDEFINED",
                        "r_inc": "UNDEFINED",
                        "r_sel_status": "UNDEFINED",
                        "r_sel": "UNDEFINED",
                        "r_sel_ucb95_descriptive": "UNDEFINED",
                    }
                )
                continue
            s_sum = compute_policy_summary(cand.candidate_id, s_eps)
            scen_rows.append(
                {
                    "policy": cand.candidate_id,
                    "scenario": sc.name,
                    "suite": sc.suite,
                    "n_episodes": s_sum.n_episodes,
                    "m_accepted": s_sum.m_accepted,
                    "ts_count": s_sum.ts_count,
                    "fs_count": s_sum.fs_count,
                    "ab_explicit_count": s_sum.ab_explicit_count,
                    "timeout_count": s_sum.timeout_count,
                    "crashed_count": s_sum.crashed_count,
                    "coverage": f"{s_sum.coverage:.6f}",
                    "tsr": f"{s_sum.tsr:.6f}",
                    "r_inc": f"{s_sum.r_inc:.6f}",
                    "r_sel_status": s_sum.r_sel_status,
                    "r_sel": _format_float_or_undef(s_sum.r_sel, 6),
                    "r_sel_ucb95_descriptive": _format_float_or_undef(s_sum.r_sel_ucb95, 6),
                }
            )

    scen_csv = res_dir / "cal_scenario_breakdown_diagnostic.csv"
    with scen_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(scen_rows[0].keys()), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(scen_rows)

    created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 5. Write locked selected_policy.json for downstream holdout evaluation
    selected_policy_payload: dict[str, Any] = {
        "schema_version": "nexvia-aegis-v9-selected-policy/1.0",
        "protocol_version": PROTOCOL_VERSION,
        "v9_m1_commit": V9_M1_COMMIT,
        "source_design_commit": SOURCE_DESIGN_COMMIT,
        "v81_baseline_commit": V81_BASELINE_COMMIT,
        "created_utc": created_utc,
        "calibration_status": ltt_res.status,
        "certified": ltt_res.certified,
        "alpha_target": ALPHA_TARGET,
        "delta": SIGNIFICANCE_DELTA,
        "c_min_empirical_guardrail": C_MIN_EMPIRICAL,
        "m_min_effective": m_min_eff,
        "stopped_at_position": ltt_res.stopped_at_position,
        "stopping_reason": overall_stop_reason,
        "certified_candidate_ids": list(ltt_res.certified_candidate_ids),
        "selected_candidate": (
            asdict(ltt_res.selected_candidate)
            if ltt_res.selected_candidate is not None
            else None
        ),
        "diagnostic_fallback_candidate_if_uncertified": asdict(
            ltt_res.diagnostic_fallback_candidate
        ),
        "scope_of_calibration_claim": (
            "Certifies C(pi_hat; P_12) > 0 and R_sel(pi_hat; P_12) <= 0.05 at familywise "
            "confidence 1 - delta = 0.95 over the i.i.d. calibration draw D_cal under the "
            "exact 12-scenario uniform simulation mixture P_12 ONLY, when certified == True. "
            "Does NOT certify per-scenario selective risk, arbitrary distribution shifts, "
            "population coverage >= 0.35, zero true risk, or physical hardware safety. "
            "Final confirmatory holdout verification on D_test^mix remains reserved."
            if ltt_res.certified
            else "NO SELECTIVE-RISK CERTIFICATION CLAIM SUPPORTED (V9_CALIBRATION_UNCERTIFIED)."
        ),
    }
    selected_policy_payload["integrity_sha256"] = compute_canonical_payload_sha256(
        selected_policy_payload
    )
    selected_policy_path = res_dir / "selected_policy.json"
    selected_policy_path.write_text(
        json.dumps(selected_policy_payload, indent=2) + "\n", encoding="utf-8"
    )

    # 6. Write complete calibration_report.json with artifact SHA-256 manifest
    artifact_hashes = {
        "configs/v9_candidates_frozen.json": sha256_file(cand_path),
        "results/v9/manifests/cal_manifest.json": sha256_file(man_path),
        "results/v9/cal/calibration_run_config_frozen.json": sha256_file(
            res_dir / "calibration_run_config_frozen.json"
        ),
        "results/v9/cal/cal_episodes.csv": sha256_file(episodes_csv),
        "results/v9/cal/cal_candidate_summary.csv": sha256_file(summary_csv),
        "results/v9/cal/cal_scenario_breakdown_diagnostic.csv": sha256_file(scen_csv),
        "results/v9/cal/selected_policy.json": sha256_file(selected_policy_path),
    }

    report_payload: dict[str, Any] = {
        "schema_version": "nexvia-aegis-v9-calibration-report/1.0",
        "status": "COMPLETE_VALID",
        "protocol_version": PROTOCOL_VERSION,
        "v9_m1_commit": V9_M1_COMMIT,
        "source_design_commit": SOURCE_DESIGN_COMMIT,
        "v81_baseline_commit": V81_BASELINE_COMMIT,
        "created_utc": created_utc,
        "elapsed_seconds": round(elapsed_sec, 3),
        "run_config": run_cfg,
        "ltt_result": {
            "certified": ltt_res.certified,
            "status": ltt_res.status,
            "alpha_target": ltt_res.alpha_target,
            "delta": ltt_res.delta,
            "c_min_empirical_guardrail": ltt_res.c_min,
            "m_min_effective": ltt_res.m_min_effective,
            "stopped_at_position": ltt_res.stopped_at_position,
            "stopping_reason": overall_stop_reason,
            "certified_candidate_ids": list(ltt_res.certified_candidate_ids),
            "selected_candidate_id": (
                ltt_res.selected_candidate.candidate_id
                if ltt_res.selected_candidate is not None
                else None
            ),
            "selected_candidate": (
                asdict(ltt_res.selected_candidate)
                if ltt_res.selected_candidate is not None
                else None
            ),
            "holm_stepdown_sensitivity_certified_ids": sorted(
                holm_certified_ids,
                key=lambda cid: [c.candidate_id for c in candidates].index(cid),
            ),
            "records": [asdict(r) for r in ltt_res.records],
        },
        "candidate_summaries": summary_rows,
        "reserved_partitions_untouched": {
            "D_val_72000_72039": True,
            "D_test_mix_73000_74439": True,
            "D_test_scen_75000_75119": True,
        },
        "artifact_sha256": artifact_hashes,
    }
    report_payload["integrity_sha256"] = compute_canonical_payload_sha256(report_payload)
    report_path = res_dir / "calibration_report.json"
    report_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")

    return report_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute NEXVIA AEGIS V9-M2 single-shot Fixed-Sequence LTT calibration on D_cal."
    )
    parser.add_argument(
        "--manifest",
        type=str,
        default="results/v9/manifests/cal_manifest.json",
        help="Path to calibration manifest (must end with results/v9/manifests/cal_manifest.json).",
    )
    parser.add_argument(
        "--candidates",
        type=str,
        default="configs/v9_candidates_frozen.json",
        help="Path to frozen V9-M1 candidate JSON.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="results/v9/cal",
        help="Isolated calibration output directory (must end with results/v9/cal).",
    )
    parser.add_argument(
        "--freeze-only",
        action="store_true",
        help="Freeze and verify cal_manifest.json and calibration_run_config_frozen.json without running episodes.",
    )
    args = parser.parse_args()

    result = execute_single_shot_calibration(
        manifest_path=args.manifest,
        candidates_path=args.candidates,
        out_dir=args.out,
        freeze_only=args.freeze_only,
    )

    if args.freeze_only:
        rc = result["run_config"]
        print("=" * 92)
        print("NEXVIA AEGIS V9-M2 — PHASE 3 CALIBRATION CONFIGURATION FROZEN (NO EPISODES RUN)")
        print("=" * 92)
        print(f"Manifest SHA-256 (canonical): {rc['cal_manifest_canonical_sha256']}")
        print(f"Manifest SHA-256 (raw file):  {rc['cal_manifest_raw_sha256']}")
        print(f"Episodes SHA-256:             {rc['cal_manifest_episodes_sha256']}")
        print(f"Run Config SHA-256:           {rc['integrity_sha256']}")
        print(f"Realized S_12 counts (N=960): {rc['realized_scenario_counts_in_d_cal']}")
        return

    print("=" * 108)
    print("NEXVIA AEGIS V9-M2 — SINGLE-SHOT D_cal (SEEDS 71000..71959, N=960/CANDIDATE) LTT CALIBRATION")
    print("=" * 108)
    hdr = (
        f"{'Pos':>3} {'Candidate':<32} {'Acc(M)':>6} {'Cov':>7} {'TS':>5} {'TSR':>7} "
        f"{'FS(K)':>5} {'R_sel':>8} {'p_sel':>12} {'Cert':>5} {'Sel':>4}"
    )
    print(hdr)
    print("-" * 108)
    for row in result["candidate_summaries"]:
        r_sel_disp = (
            "UNDEF"
            if row["r_sel"] == "UNDEFINED"
            else f"{100.0 * float(row['r_sel']):6.2f}%"
        )
        print(
            f"{row['sequence_position']:>3} {row['candidate_id']:<32} {row['m_accepted']:>6} "
            f"{100.0 * float(row['coverage']):6.2f}% {row['ts_count']:>5} "
            f"{100.0 * float(row['tsr']):6.2f}% {row['fs_count']:>5} "
            f"{r_sel_disp:>8} {float(row['p_sel']):>12.4e} "
            f"{str(row['fst_certified']):>5} {str(row['selected_by_ltt']):>4}"
        )
    print("-" * 108)
    ltt = result["ltt_result"]
    print(f"LTT Status:          {ltt['status']} (certified={ltt['certified']})")
    print(f"Stopped Position:    {ltt['stopped_at_position']} ({ltt['stopping_reason']})")
    print(f"Selected Candidate:  {ltt['selected_candidate_id']}")
    print(f"Holm-6 Diagnostic:   {ltt['holm_stepdown_sensitivity_certified_ids']}")
    print(f"Report SHA-256:      {result['integrity_sha256']}")


if __name__ == "__main__":
    main()
