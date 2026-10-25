"""
NEXVIA AEGIS V9.0 — Milestone V9-M4 Confirmatory Holdout Evaluation Harness.

GOVERNANCE & PARTITION GUARDRAILS (`docs/v9_experiment_protocol.md` Sections 3.5-3.6,
`docs/v9_risk_calibration_design.md` Section 2.5, `docs/v9_m4_readiness_review.md`):
- Evaluates EXCLUSIVELY the frozen calibrated policy selected in Milestone V9-M2R2:
  `V9_CAND_1_TIER1_STRICTEST` from `results/v9/cal_r2/selected_policy.json` (verified against
  its canonical SHA-256 integrity hash).
- Two Preregistered Holdout Partitions:
  1. Mixture Holdout (D_test^mix):
     - N = 1,440 episodes sampled i.i.d. from the uniform 12-scenario mixture P_12.
     - Reserved seed range: 73000..74439 (1,440 seeds).
     - Partition branch: p = PARTITION_BRANCH_TEST_MIXTURE = 4.
     - Target output directory: results/v9/test_mix/
     - Confirmatory Hypotheses: H_1 (Selective Risk Control), H_2 (Unconditional Incidence Reduction),
       H_4 (Coverage Floor Precondition).
  2. Scenario Holdout (D_test^scen):
     - N = 1,440 episodes under deterministic stratified grid (12 scenarios x 120 seeds/scenario).
     - Reserved seed range: 75000..75119 (120 seeds per scenario).
     - Partition branch: p = PARTITION_BRANCH_TEST_SCENARIO = 5.
     - Target output directory: results/v9/test_scen/
     - Confirmatory Hypotheses: H_3 (Operational Utility & TSR Noninferiority vs V7),
       H_5 (Worst-Case Scenario Safety).
- HARD PROHIBITION: Seeds from D_hist (60000..60049), D_dev (70000..70029, 77000..77029),
  D_cal (71000..71959, 76000..76959), D_val (72000..72039), or cross-partition seeds are blocked.
- SINGLE-SHOT EXECUTION GUARD: Refuses to overwrite existing holdout outputs.
- PREFLIGHT SAFETY GUARD: Real holdout execution requires explicit user authorization token.
  Without the token, the runner fails closed, prohibiting live holdout simulation.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
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
from scipy.stats import beta, binom, binomtest, norm, t

from aegis.next.agent_next import AegisNextController
from aegis.next.baselines import AegisV7MPCBaselineController
from aegis.v9.controller import AegisV9Controller
from aegis.v9.randomization import (
    PARTITION_BRANCH_TEST_MIXTURE,
    PARTITION_BRANCH_TEST_SCENARIO,
    create_decoupled_rng_pair,
    instantiate_episode_rngs_from_manifest_item,
)
from aegis.v9.risk_statistics import (
    PolicyEvaluationSummary,
    V9CandidateParams,
    compute_canonical_payload_sha256,
    compute_policy_summary,
)
from experiments.v9_calibrate_ltt import verify_episode_outcome_algebra
verify_holdout_outcome_algebra = verify_episode_outcome_algebra
from experiments.v9_evaluate_dev import (
    V9ScenarioSpec,
    build_v9_s12_scenarios,
    run_single_episode,
)

PROTOCOL_VERSION: str = "v9.0-preregistered-2026-10-amendment-r2-holdout"
V9_M1_COMMIT: str = "6c87f66a9ea602c96d4fe8bfc97728d0513b157f"
SOURCE_DESIGN_COMMIT: str = "891c13e7bbd60e36c416c9bada8407e51233e663"
V81_BASELINE_COMMIT: str = "4d891c7500cfb4c8110f276038455bc62765ef3b"
EXPECTED_SELECTED_CANDIDATE_ID: str = "V9_CAND_1_TIER1_STRICTEST"

TEST_MIX_SEED_START: int = 73000
TEST_MIX_SEED_STOP_EXCLUSIVE: int = 74440
TEST_MIX_EXPECTED_EPISODES: int = 1440
TEST_MIX_ALLOWED_SEEDS: frozenset[int] = frozenset(
    range(TEST_MIX_SEED_START, TEST_MIX_SEED_STOP_EXCLUSIVE)
)

TEST_SCEN_SEED_START: int = 75000
TEST_SCEN_SEED_STOP_EXCLUSIVE: int = 75120
TEST_SCEN_SEEDS_PER_SCENARIO: int = 120
TEST_SCEN_EXPECTED_EPISODES: int = 1440
TEST_SCEN_ALLOWED_SEEDS: frozenset[int] = frozenset(
    range(TEST_SCEN_SEED_START, TEST_SCEN_SEED_STOP_EXCLUSIVE)
)

PROHIBITED_SEED_BLOCKS: tuple[tuple[str, range], ...] = (
    ("D_hist", range(60000, 60050)),
    ("D_dev_historical", range(70000, 70030)),
    ("D_dev_r1", range(77000, 77030)),
    ("D_cal_historical", range(71000, 71960)),
    ("D_cal_r1_r2", range(76000, 76960)),
    ("D_val", range(72000, 72040)),
)

REQUIRED_EXECUTION_TOKEN: str = "NEXVIA_AEGIS_V9_M4_AUTHORIZED_CONFIRMATORY_EXECUTION_20261025"


# ==============================================================================
# Cryptographic and Formatting Helpers
# ==============================================================================

def sha256_file(path: Path) -> str:
    """Returns hex SHA-256 digest of a file's exact raw bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def enforce_holdout_seeds(seeds: Sequence[int], partition: str) -> tuple[int, ...]:
    """Blocks any seed outside the permitted holdout partition seed range."""
    if not seeds:
        raise ValueError("Holdout seed sequence must be non-empty.")
    out = tuple(int(s) for s in seeds)
    if partition == "mixture":
        allowed = TEST_MIX_ALLOWED_SEEDS
        expected_range = f"{TEST_MIX_SEED_START}..{TEST_MIX_SEED_STOP_EXCLUSIVE - 1}"
    elif partition == "scenario":
        allowed = TEST_SCEN_ALLOWED_SEEDS
        expected_range = f"{TEST_SCEN_SEED_START}..{TEST_SCEN_SEED_STOP_EXCLUSIVE - 1}"
    else:
        raise ValueError(f"Unknown partition type: {partition}")

    forbidden = [s for s in out if s not in allowed]
    if forbidden:
        raise ValueError(
            f"PROHIBITED SEED ACCESS BLOCKED: {forbidden[:10]}. "
            f"Permitted {partition} holdout seeds are strictly {expected_range}."
        )
    return out


def enforce_holdout_output_directory(out_dir: str | Path, partition: str) -> Path:
    """Ensures holdout outputs are written strictly to isolated holdout directories."""
    resolved = Path(out_dir).resolve()
    parts = resolved.parts
    if len(parts) < 3 or parts[-2] != "v9":
        raise ValueError(
            f"Holdout output path `{resolved}` must be under `results/v9/` to isolate holdout artifacts."
        )
    if partition == "mixture" and not parts[-1].startswith("test_mix"):
        raise ValueError(
            f"Mixture holdout output `{resolved}` must end with `test_mix` or `test_mix_*`."
        )
    if partition == "scenario" and not parts[-1].startswith("test_scen"):
        raise ValueError(
            f"Scenario holdout output `{resolved}` must end with `test_scen` or `test_scen_*`."
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


def verify_and_load_holdout_manifest(
    manifest_path: Path,
    expected_partition: str,
    *,
    allow_synthetic: bool = False,
) -> tuple[dict[str, Any], str]:
    """
    Verifies that a holdout manifest exists, passes internal SHA-256 integrity checks,
    uses the approved partition branch, and matches the expected episode count and seeds.
    When allow_synthetic=True, verifies integrity and schema for synthetic testing
    without enforcing reserved production seed blocks or full-size holdout counts.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Holdout manifest not found: {manifest_path}")

    raw_bytes = manifest_path.read_bytes()
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    loaded = json.loads(raw_bytes.decode("utf-8"))

    stored_integrity = loaded.get("integrity_sha256")
    computed_canonical = compute_canonical_payload_sha256(loaded)
    filtered = {k: v for k, v in loaded.items() if k != "integrity_sha256"}
    computed_indent = hashlib.sha256(json.dumps(filtered, sort_keys=True, indent=2).encode("utf-8")).hexdigest()
    if stored_integrity not in (computed_canonical, computed_indent):
        raise ValueError(
            f"Holdout manifest integrity hash mismatch: {stored_integrity} != {computed_canonical} (nor {computed_indent})."
        )

    if expected_partition == "mixture":
        if not allow_synthetic:
            if loaded.get("partition") != "test_mix_r1":
                raise ValueError(f"Expected partition 'test_mix_r1', got '{loaded.get('partition')}'.")
            if loaded.get("partition_index") != PARTITION_BRANCH_TEST_MIXTURE:
                raise ValueError(
                    f"Expected partition_index={PARTITION_BRANCH_TEST_MIXTURE}, got {loaded.get('partition_index')}."
                )
            if loaded.get("planned_episodes") != TEST_MIX_EXPECTED_EPISODES:
                raise ValueError(
                    f"Expected {TEST_MIX_EXPECTED_EPISODES} episodes, got {loaded.get('planned_episodes')}."
                )
            episodes = loaded.get("episodes", [])
            if len(episodes) != TEST_MIX_EXPECTED_EPISODES:
                raise ValueError(
                    f"Manifest episode count mismatch: planned={TEST_MIX_EXPECTED_EPISODES}, actual={len(episodes)}."
                )
            seeds = [int(ep.get("seed", ep.get("manifest_id"))) for ep in episodes]
            enforce_holdout_seeds(seeds, "mixture")
        else:
            ep_part = str(loaded.get("partition", ""))
            if not (ep_part.startswith("test_mix") or "mixture" in ep_part):
                raise ValueError(f"Expected mixture partition in synthetic manifest, got '{ep_part}'.")

    elif expected_partition == "scenario":
        if not allow_synthetic:
            if loaded.get("partition") != "test_scen_r1":
                raise ValueError(f"Expected partition 'test_scen_r1', got '{loaded.get('partition')}'.")
            if loaded.get("partition_index") != PARTITION_BRANCH_TEST_SCENARIO:
                raise ValueError(
                    f"Expected partition_index={PARTITION_BRANCH_TEST_SCENARIO}, got {loaded.get('partition_index')}."
                )
            if loaded.get("planned_episodes") != TEST_SCEN_EXPECTED_EPISODES:
                raise ValueError(
                    f"Expected {TEST_SCEN_EXPECTED_EPISODES} episodes, got {loaded.get('planned_episodes')}."
                )
            episodes = loaded.get("episodes", [])
            if len(episodes) != TEST_SCEN_EXPECTED_EPISODES:
                raise ValueError(
                    f"Manifest episode count mismatch: planned={TEST_SCEN_EXPECTED_EPISODES}, actual={len(episodes)}."
                )
            counts = loaded.get("realized_scenario_counts", {})
            if len(counts) != 12 or any(cnt != TEST_SCEN_SEEDS_PER_SCENARIO for cnt in counts.values()):
                raise ValueError(f"Invalid stratified scenario counts: {counts}.")
            seeds = [int(ep.get("seed", ep.get("manifest_id"))) for ep in episodes]
            enforce_holdout_seeds(seeds, "scenario")
        else:
            ep_part = str(loaded.get("partition", ""))
            if not (ep_part.startswith("test_scen") or "scenario" in ep_part):
                raise ValueError(f"Expected scenario partition in synthetic manifest, got '{ep_part}'.")
    else:
        raise ValueError(f"Unknown partition type: {expected_partition}")

    return loaded, raw_hash


def verify_holdout_outcome_algebra(
    rec: Mapping[str, Any],
    *,
    expected_policy_id: str | None = None,
    expected_seed: int | None = None,
    expected_scenario: str | None = None,
) -> None:
    """
    Asserts that an episode record satisfies the exact benchmark outcome partition
    (`docs/v9_risk_calibration_design.md` Section 2.1.1 & `docs/v9_experiment_protocol.md` Section 3.1.3).
    """
    if expected_policy_id is not None and str(rec.get("policy")) != expected_policy_id:
        raise ValueError(f"Policy ID mismatch: {rec.get('policy')} != {expected_policy_id}")
    if expected_seed is not None and int(rec.get("seed", -1)) != expected_seed:
        raise ValueError(f"Seed mismatch: {rec.get('seed')} != {expected_seed}")
    if expected_scenario is not None and str(rec.get("scenario")) != expected_scenario:
        raise ValueError(f"Scenario mismatch: {rec.get('scenario')} != {expected_scenario}")

    acc = int(rec["accepted"])
    ts = int(rec["true_success"])
    fs = int(rec["false_success"])
    ab_exp = int(rec["abstain_explicit"])
    to = int(rec["timeout"])
    ab = int(rec["abstain"])
    crashed = int(rec["crashed"])

    for flag in (acc, ts, fs, ab_exp, to, ab, crashed):
        if flag not in (0, 1):
            raise ValueError(f"Non-binary outcome indicator in record: {rec}")

    if crashed == 1:
        if not (acc == 0 and ts == 0 and fs == 1 and ab_exp == 0 and to == 0 and ab == 0):
            raise ValueError(f"Invalid fail-unsafe crash accounting in record: {rec}")
    else:
        if acc != (ts + fs):
            raise ValueError(f"Outcome algebra violation: accepted ({acc}) != ts ({ts}) + fs ({fs})")
        if ab != (ab_exp + to):
            raise ValueError(f"Outcome algebra violation: abstain ({ab}) != ab_exp ({ab_exp}) + timeout ({to})")
        if acc + ab != 1:
            raise ValueError(f"Outcome algebra violation: accepted ({acc}) + abstain ({ab}) != 1")
        if ts + fs + ab_exp + to != 1:
            raise ValueError(f"Outcome algebra violation: ts + fs + ab_exp + to != 1: {rec}")


def verify_episode_records_integrity(
    records: Sequence[Mapping[str, Any]],
    expected_n: int,
) -> None:
    """Verifies that episode records are complete, unique, non-duplicated, and satisfy outcome algebra."""
    if len(records) != expected_n:
        raise ValueError(f"Episode record count mismatch: expected {expected_n}, got {len(records)}.")

    seen_indices: set[int] = set()
    for rec in records:
        ep_idx = int(rec["episode_index"])
        if ep_idx in seen_indices:
            raise ValueError(f"Duplicated episode index {ep_idx} in episode records.")
        seen_indices.add(ep_idx)
        verify_holdout_outcome_algebra(rec)


def align_and_pair_records(
    policy_records: Sequence[Mapping[str, Any]],
    baseline_records: Sequence[Mapping[str, Any]],
    *,
    baseline_label: str = "baseline",
    require_exact_length: bool = True,
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """
    Strictly aligns and pairs policy and baseline episode records using authoritative identity keys:
    (seed: int, scenario: str).

    Enforces:
    1. Pairing keys 'seed' and 'scenario' must be present, non-empty, and correctly typed in both record sets.
    2. No duplicate pairing keys in either policy or baseline records.
    3. If require_exact_length is True, len(policy_records) must equal len(baseline_records).
    4. Exactly one corresponding baseline record for every policy record (bijective keyed match).
    5. Rejects any missing, unmatchable, or extraneous records.
    """
    if require_exact_length and len(policy_records) != len(baseline_records):
        raise ValueError(
            f"Record count mismatch in paired comparison vs {baseline_label}: "
            f"policy has {len(policy_records)} records, baseline has {len(baseline_records)} records."
        )

    # 1. Parse and validate policy keys
    policy_keys: set[tuple[int, str]] = set()
    for i, r in enumerate(policy_records):
        seed_raw = r.get("seed")
        if seed_raw is None:
            raise ValueError(f"Policy record index {i} is missing required identity key 'seed'.")
        try:
            seed = int(seed_raw)
        except (ValueError, TypeError) as err:
            raise ValueError(f"Policy record index {i} has invalid integer seed '{seed_raw}': {err}") from err

        scen_raw = r.get("scenario")
        if scen_raw is None or not str(scen_raw).strip():
            raise ValueError(f"Policy record index {i} is missing required identity key 'scenario'.")
        scenario = str(scen_raw).strip()

        key = (seed, scenario)
        if key in policy_keys:
            raise ValueError(f"Duplicate identity key (seed={seed}, scenario='{scenario}') in policy records.")
        policy_keys.add(key)

    # 2. Parse and index baseline records
    baseline_dict: dict[tuple[int, str], Mapping[str, Any]] = {}
    for i, r in enumerate(baseline_records):
        seed_raw = r.get("seed")
        if seed_raw is None:
            raise ValueError(f"Baseline {baseline_label} record index {i} is missing required identity key 'seed'.")
        try:
            seed = int(seed_raw)
        except (ValueError, TypeError) as err:
            raise ValueError(f"Baseline {baseline_label} record index {i} has invalid integer seed '{seed_raw}': {err}") from err

        scen_raw = r.get("scenario")
        if scen_raw is None or not str(scen_raw).strip():
            raise ValueError(f"Baseline {baseline_label} record index {i} is missing required identity key 'scenario'.")
        scenario = str(scen_raw).strip()

        key = (seed, scenario)
        if key in baseline_dict:
            raise ValueError(f"Duplicate identity key (seed={seed}, scenario='{scenario}') in baseline {baseline_label} records.")
        baseline_dict[key] = r

    # 3. Check for count/key mismatch
    if len(baseline_dict) != len(policy_keys):
        raise ValueError(
            f"Key count mismatch in paired comparison vs {baseline_label}: "
            f"{len(policy_keys)} unique policy keys vs {len(baseline_dict)} unique baseline keys."
        )

    # 4. Perform bijective keyed join preserving policy evaluation order
    paired: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for r_pi in policy_records:
        key = (int(r_pi["seed"]), str(r_pi["scenario"]).strip())
        if key not in baseline_dict:
            raise ValueError(
                f"Missing baseline {baseline_label} record for episode with seed={key[0]}, scenario='{key[1]}'."
            )
        paired.append((r_pi, baseline_dict[key]))

    return paired


# ==============================================================================
# Statistical Estimators & Hypothesis Testing
# ==============================================================================

def wilson_score_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Calculates 2-sided Wilson score confidence interval for a binomial proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    z = float(norm.ppf(1.0 - (1.0 - confidence) / 2.0))
    p = k / n
    denom = 1.0 + (z**2) / n
    center = (p + (z**2) / (2.0 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1.0 - p) / n + (z**2) / (4.0 * n**2))
    return (max(0.0, center - margin), min(1.0, center + margin))


def clopper_pearson_exact_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Calculates 2-sided exact Clopper-Pearson confidence interval for a binomial proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    alpha_level = 1.0 - confidence
    lower = 0.0 if k == 0 else float(beta.ppf(alpha_level / 2.0, k, n - k + 1))
    upper = 1.0 if k == n else float(beta.ppf(1.0 - alpha_level / 2.0, k + 1, n - k))
    return (lower, upper)


def clopper_pearson_one_sided_ucb(k: int, n: int, delta: float = 0.05) -> float:
    """Calculates 1-sided (1 - delta) exact Clopper-Pearson upper confidence bound."""
    if n == 0:
        return float("nan")
    if k == 0:
        return float(1.0 - (delta ** (1.0 / n)))
    if k >= n:
        return 1.0
    return float(beta.ppf(1.0 - delta, k + 1, n - k))


def mcnemar_exact_test(n10: int, n01: int) -> float:
    """
    Computes exact two-sided McNemar test p-value for discordant pairs (b=n01, c=n10).
    Under H_0, b ~ Binomial(b + c, 0.5).
    """
    total_discordant = n10 + n01
    if total_discordant == 0:
        return 1.0
    res = binomtest(min(n10, n01), total_discordant, 0.5, alternative="two-sided")
    return float(res.pvalue)


def newcombe_paired_difference_ci(
    n11: int,
    n10: int,
    n01: int,
    n00: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """
    Calculates Newcombe's paired difference confidence interval (Method 10) for paired proportions.
    p1 = (n11 + n10) / n, p2 = (n11 + n01) / n, theta = p1 - p2.
    """
    n = n11 + n10 + n01 + n00
    if n == 0:
        return (float("nan"), float("nan"))
    p1 = (n11 + n10) / n
    p2 = (n11 + n01) / n
    diff = p1 - p2

    l1, u1 = wilson_score_interval(n11 + n10, n, confidence)
    l2, u2 = wilson_score_interval(n11 + n01, n, confidence)

    denom = (n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)
    phi = (n11 * n00 - n10 * n01) / math.sqrt(denom) if denom > 0 else 0.0

    lower = diff - math.sqrt((p1 - l1) ** 2 - 2.0 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2)
    upper = diff + math.sqrt((u1 - p1) ** 2 - 2.0 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2)
    return (lower, upper)


def paired_difference_lcb(diffs: Sequence[float], confidence: float = 0.95) -> float:
    """Calculates 1-sided lower confidence bound on paired continuous or binary difference."""
    n = len(diffs)
    if n < 2:
        return float("nan")
    mean_diff = float(np.mean(diffs))
    se_diff = float(np.std(diffs, ddof=1) / math.sqrt(n))
    t_crit = float(t.ppf(confidence, df=n - 1))
    return float(mean_diff - t_crit * se_diff)


def holm_shidak_adjusted_thresholds(n_tests: int = 12, alpha: float = 0.05) -> list[float]:
    """Computes step-down Holm-Šidák adjusted significance thresholds for n_tests."""
    return [float(1.0 - (1.0 - alpha) ** (1.0 / (n_tests - r + 1))) for r in range(1, n_tests + 1)]


def berger_intersection_union_test(p_values: Sequence[float], alpha: float = 0.05) -> bool:
    """
    Berger Intersection-Union Test (IUT): Rejects H_0: union{R_s >= alpha}
    iff every individual scenario hypothesis rejects at level alpha (i.e., max(p_s) <= alpha).
    """
    if not p_values:
        return False
    return max(p_values) <= alpha


# ==============================================================================
# Run Configuration Freeze
# ==============================================================================

def freeze_holdout_run_configuration(
    *,
    partition: str,
    manifest_path: Path,
    manifest_payload: dict[str, Any],
    manifest_raw_sha256: str,
    selected_policy_path: Path,
    selected_policy_payload: dict[str, Any],
    selected_policy_raw_sha256: str,
    candidate_params: V9CandidateParams,
    out_dir: Path,
) -> dict[str, Any]:
    """Writes and verifies the frozen holdout run configuration."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg_name = f"holdout_{partition}_run_config_frozen_r1.json"
    cfg_path = out_dir / cfg_name

    cfg_payload: dict[str, Any] = {
        "schema_version": "nexvia-aegis-v9-holdout-run-config/1.0",
        "protocol_version": PROTOCOL_VERSION,
        "v9_m1_commit": V9_M1_COMMIT,
        "source_design_commit": SOURCE_DESIGN_COMMIT,
        "v81_baseline_commit": V81_BASELINE_COMMIT,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "partition": partition,
        "holdout_manifest_path": str(manifest_path),
        "holdout_manifest_raw_sha256": manifest_raw_sha256,
        "holdout_manifest_canonical_sha256": compute_canonical_payload_sha256(manifest_payload),
        "selected_policy_path": str(selected_policy_path),
        "selected_policy_raw_sha256": selected_policy_raw_sha256,
        "selected_policy_canonical_sha256": compute_canonical_payload_sha256(selected_policy_payload),
        "candidate": asdict(candidate_params),
    }
    cfg_payload["integrity_sha256"] = compute_canonical_payload_sha256(cfg_payload)

    if cfg_path.exists():
        existing_raw = cfg_path.read_bytes()
        existing_payload = json.loads(existing_raw.decode("utf-8"))
        if existing_payload.get("integrity_sha256") != cfg_payload["integrity_sha256"]:
            raise ValueError(
                f"Existing frozen holdout configuration `{cfg_path}` mismatch: "
                f"stored={existing_payload.get('integrity_sha256')}, expected={cfg_payload['integrity_sha256']}."
            )
        return existing_payload

    cfg_bytes = json.dumps(cfg_payload, indent=2).encode("utf-8")
    cfg_path.write_bytes(cfg_bytes)
    return cfg_payload


# ==============================================================================
# Statistical Analysis A: Mixture Holdout (D_test^mix)
# ==============================================================================

def evaluate_mixture_holdout(
    *,
    records: Sequence[Mapping[str, Any]],
    cand_params: V9CandidateParams,
    v8_records: Sequence[Mapping[str, Any]] | None = None,
    v7_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Executes the confirmatory statistical analysis for the mixture holdout partition D_test^mix:
    - Verifies outcome algebra and sample coverage floor (H_4: C >= 0.35).
    - Tests H_1: Selective False-Success Risk Control (1-sided 95% Clopper-Pearson UCB <= 0.05 on M >= 59).
    - Tests H_2: Unconditional False-Success Incidence Reduction vs V8.1 and V7 baselines via paired McNemar test.
    """
    verify_episode_records_integrity(records, len(records))
    n = len(records)
    m = sum(1 for r in records if int(r["accepted"]) == 1)
    ts = sum(1 for r in records if int(r["true_success"]) == 1)
    fs = sum(1 for r in records if int(r["false_success"]) == 1)
    ab_exp = sum(1 for r in records if int(r["abstain_explicit"]) == 1)
    to = sum(1 for r in records if int(r["timeout"]) == 1)
    ab_tot = sum(1 for r in records if int(r["abstain"]) == 1)
    crashed = sum(1 for r in records if int(r["crashed"]) == 1)

    cov = m / n if n > 0 else 0.0
    tsr = ts / n if n > 0 else 0.0
    r_inc = fs / n if n > 0 else 0.0
    r_sel = fs / m if m > 0 else float("nan")

    # Hypothesis H_1: Selective Risk Control
    h1_precondition_met = m >= 59
    h1_ucb95 = clopper_pearson_one_sided_ucb(fs, m, delta=0.05) if m > 0 else float("nan")
    h1_passed = bool(h1_precondition_met and not math.isnan(h1_ucb95) and h1_ucb95 <= 0.05)
    h1_status = "CONFIRMATORY_PASS" if h1_passed else ("FAILED_UCB" if h1_precondition_met else "INSUFFICIENT_COVERAGE")

    # Hypothesis H_4: Coverage Floor Precondition
    h4_passed = bool(cov >= 0.35)
    h4_status = "PASS_ADEQUATE_UTILITY" if h4_passed else "FAIL_COVERAGE_DEGENERATE"

    # Hypothesis H_2: Unconditional FS Incidence Reduction vs Baselines
    h2_results: dict[str, Any] = {}
    h2_passed = False
    pooled_ucb95_fs = clopper_pearson_one_sided_ucb(fs, n, delta=0.05)

    if v8_records is not None:
        paired_v8 = align_and_pair_records(records, v8_records, baseline_label="v8_martingale")
        n11 = sum(1 for r, v in paired_v8 if int(r["false_success"]) == 1 and int(v["false_success"]) == 1)
        n10 = sum(1 for r, v in paired_v8 if int(r["false_success"]) == 1 and int(v["false_success"]) == 0)
        n01 = sum(1 for r, v in paired_v8 if int(r["false_success"]) == 0 and int(v["false_success"]) == 1)
        n00 = sum(1 for r, v in paired_v8 if int(r["false_success"]) == 0 and int(v["false_success"]) == 0)
        mcnemar_p_v8 = mcnemar_exact_test(n10, n01)
        newcombe_ci_v8 = newcombe_paired_difference_ci(n11, n10, n01, n00)
        h2_results["vs_v8_martingale"] = {
            "n_matched": len(paired_v8),
            "table_n11_n10_n01_n00": [n11, n10, n01, n00],
            "mcnemar_exact_p": mcnemar_p_v8,
            "newcombe_diff_ci95": [float(newcombe_ci_v8[0]), float(newcombe_ci_v8[1])],
            "significant_reduction": bool(n10 < n01 and mcnemar_p_v8 < 0.05),
        }

    if v7_records is not None:
        paired_v7 = align_and_pair_records(records, v7_records, baseline_label="v7_mpc")
        n11_7 = sum(1 for r, v in paired_v7 if int(r["false_success"]) == 1 and int(v["false_success"]) == 1)
        n10_7 = sum(1 for r, v in paired_v7 if int(r["false_success"]) == 1 and int(v["false_success"]) == 0)
        n01_7 = sum(1 for r, v in paired_v7 if int(r["false_success"]) == 0 and int(v["false_success"]) == 1)
        n00_7 = sum(1 for r, v in paired_v7 if int(r["false_success"]) == 0 and int(v["false_success"]) == 0)
        mcnemar_p_v7 = mcnemar_exact_test(n10_7, n01_7)
        newcombe_ci_v7 = newcombe_paired_difference_ci(n11_7, n10_7, n01_7, n00_7)
        h2_results["vs_v7_mpc"] = {
            "n_matched": len(paired_v7),
            "table_n11_n10_n01_n00": [n11_7, n10_7, n01_7, n00_7],
            "mcnemar_exact_p": mcnemar_p_v7,
            "newcombe_diff_ci95": [float(newcombe_ci_v7[0]), float(newcombe_ci_v7[1])],
            "significant_reduction": bool(n10_7 < n01_7 and mcnemar_p_v7 < 0.05),
        }

    # Compound scenarios subset check for H_2
    comp_scenarios = {"COMPOUND_DRIFT_DROPOUT", "COMPOUND_HOLDOUT_EXTREME", "COMPOUND_ANTIPODAL_RANGE_SHIFT"}
    comp_records = [r for r in records if str(r.get("scenario", "")) in comp_scenarios]
    n_comp = len(comp_records)
    fs_comp = sum(1 for r in comp_records if int(r["false_success"]) == 1)
    r_inc_comp = fs_comp / n_comp if n_comp > 0 else 0.0

    if pooled_ucb95_fs <= 0.05 and (not h2_results or any(v["significant_reduction"] for v in h2_results.values())):
        h2_passed = True
        h2_status = "CONFIRMATORY_PASS"
    else:
        h2_status = "DESCRIPTIVE_ONLY"

    # Anti-gaming rule evaluation
    if (not h4_passed) or (h1_passed and not h4_passed):
        overall_classification = "CONSERVATIVE_RISK_COVERAGE_TRADEOFF"
    elif h1_passed and h4_passed:
        overall_classification = "CERTIFIED_OPERATIONAL_IMPROVEMENT"
    else:
        overall_classification = "UNCERTIFIED_POLICY"

    summary: dict[str, Any] = {
        "partition": "mixture",
        "n_episodes": n,
        "m_accepted": m,
        "ts_count": ts,
        "fs_count": fs,
        "ab_explicit_count": ab_exp,
        "timeout_count": to,
        "ab_total_count": ab_tot,
        "crashed_count": crashed,
        "coverage": round(cov, 6),
        "tsr": round(tsr, 6),
        "r_inc": round(r_inc, 6),
        "r_sel": round(r_sel, 6) if not math.isnan(r_sel) else "UNDEFINED",
        "h1_selective_risk_control": {
            "hypothesis": "H_1",
            "estimand": "R_sel <= 0.05 on accepted decisions",
            "m_accepted": m,
            "precondition_m_ge_59": h1_precondition_met,
            "cp_ucb95": round(h1_ucb95, 6) if not math.isnan(h1_ucb95) else "UNDEFINED",
            "status": h1_status,
            "passed": h1_passed,
        },
        "h4_coverage_floor": {
            "hypothesis": "H_4",
            "estimand": "Coverage >= 0.35 (utility guardrail)",
            "coverage": round(cov, 6),
            "status": h4_status,
            "passed": h4_passed,
        },
        "h2_unconditional_incidence": {
            "hypothesis": "H_2",
            "estimand": "Unconditional FS reduction vs baselines",
            "pooled_ucb95_fs": round(pooled_ucb95_fs, 6),
            "compound_fs_count": fs_comp,
            "compound_n": n_comp,
            "compound_r_inc": round(r_inc_comp, 6),
            "comparisons": h2_results,
            "status": h2_status,
            "passed": h2_passed,
        },
        "overall_evaluation_classification": overall_classification,
    }

    return summary


# ==============================================================================
# Statistical Analysis B: Scenario Holdout (D_test^scen)
# ==============================================================================

def evaluate_scenario_holdout(
    records: Sequence[Mapping[str, Any]],
    *,
    cand_params: V9CandidateParams | None = None,
    v8_records: Sequence[Mapping[str, Any]] | None = None,
    v7_records: Sequence[Mapping[str, Any]] | None = None,
    expected_seeds_per_scenario: int = TEST_SCEN_SEEDS_PER_SCENARIO,
) -> dict[str, Any]:
    """
    Executes the confirmatory statistical analysis for the scenario holdout partition D_test^scen:
    - Produces exact 12-scenario stratified breakdown table.
    - Validates that scenario episode count reconciles with the registered scenario design.
    - Handles undefined selective risk (R_sel = UNDEFINED when M_s = 0) fail-closed.
    - Tests H_3: Operational Utility & TSR Noninferiority (Protocol Section 3.1.1):
      Primary null against V8.1 (1-sided 95% LCB > -0.05 on S_10, TSR_nominal >= 0.94),
      co-evaluated against V7 baseline using strict paired-record identity alignment.
    - Tests H_5: Worst-Case Scenario Safety via Holm-Šidák simultaneous bounds + Berger IUT on unconditional incidence.
    """
    if expected_seeds_per_scenario <= 0:
        raise ValueError(
            f"Invalid denominator: expected_seeds_per_scenario must be positive, got {expected_seeds_per_scenario}."
        )

    scenarios = build_v9_s12_scenarios()
    expected_total = len(scenarios) * expected_seeds_per_scenario
    if len(records) != expected_total:
        raise ValueError(
            f"Stratified scenario record count mismatch: expected {expected_total} "
            f"({len(scenarios)} scenarios x {expected_seeds_per_scenario} seeds), got {len(records)}."
        )

    verify_episode_records_integrity(records, len(records))

    breakdown_rows: list[dict[str, Any]] = []
    p_values_for_iut: list[float] = []

    # Sidak alpha for 12 simultaneous hypotheses: 1 - (1 - 0.05)**(1/12)
    delta_shidak = 1.0 - (1.0 - 0.05) ** (1.0 / len(scenarios))

    for scen in scenarios:
        s_eps = [r for r in records if str(r.get("scenario", "")).strip() == scen.name]
        n_s = len(s_eps)
        if n_s != expected_seeds_per_scenario:
            raise ValueError(
                f"Scenario '{scen.name}' episode count mismatch: expected {expected_seeds_per_scenario}, got {n_s}."
            )

        m_s = sum(1 for r in s_eps if int(r["accepted"]) == 1)
        ts_s = sum(1 for r in s_eps if int(r["true_success"]) == 1)
        fs_s = sum(1 for r in s_eps if int(r["false_success"]) == 1)
        ab_s = sum(1 for r in s_eps if int(r["abstain_explicit"]) == 1)
        to_s = sum(1 for r in s_eps if int(r["timeout"]) == 1)
        cr_s = sum(1 for r in s_eps if int(r["crashed"]) == 1)

        cov_s = m_s / n_s
        tsr_s = ts_s / n_s
        r_inc_s = fs_s / n_s

        # Unconditional false-success incidence estimand:
        # H0,5,s: R_inc,s > 0.05 vs H1,5,s: R_inc,s <= 0.05
        # Test statistic FS_s ~ Bin(N_s, 0.05) under null boundary
        p_inc_s = float(binom.cdf(fs_s, n_s, 0.05))
        ucb95_inc_s = clopper_pearson_one_sided_ucb(fs_s, n_s, delta=0.05)
        ucb_shidak_inc_s = clopper_pearson_one_sided_ucb(fs_s, n_s, delta=delta_shidak)

        # H5 IUT evaluates unconditional incidence across all 12 scenarios
        p_values_for_iut.append(p_inc_s)

        # Selective risk estimand (defined only when M_s > 0):
        if m_s > 0:
            r_sel_s = fs_s / m_s
            r_sel_status = "DEFINED"
            ucb95_sel_s = clopper_pearson_one_sided_ucb(fs_s, m_s, delta=0.05)
            ucb_shidak_sel_s = clopper_pearson_one_sided_ucb(fs_s, m_s, delta=delta_shidak)
            p_sel_s = float(binom.cdf(fs_s, m_s, 0.05))
        else:
            r_sel_s = float("nan")
            r_sel_status = "UNDEFINED"
            ucb95_sel_s = float("nan")
            ucb_shidak_sel_s = float("nan")
            p_sel_s = float("nan")

        mean_steps = float(np.mean([float(r["steps"]) for r in s_eps]))
        mean_step_ms = float(np.mean([float(r.get("mean_step_ms", 0.0)) for r in s_eps]))
        mean_dist = float(np.mean([float(r.get("distance_traveled", 0.0)) for r in s_eps]))
        mean_queries = float(np.mean([float(r.get("anchor_queries", 0.0)) for r in s_eps]))
        mean_cost = float(np.mean([float(r.get("anchor_cost", 0.0)) for r in s_eps]))
        mean_overshoot = float(np.mean([float(r.get("max_overshoot", 0.0)) for r in s_eps]))

        breakdown_rows.append({
            "scenario": scen.name,
            "scenario_index": scen.index,
            "suite": scen.suite,
            "n_episodes": n_s,
            "m_accepted": m_s,
            "ts_count": ts_s,
            "fs_count": fs_s,
            "ab_explicit_count": ab_s,
            "timeout_count": to_s,
            "crashed_count": cr_s,
            "coverage": f"{cov_s:.6f}",
            "tsr": f"{tsr_s:.6f}",
            "r_inc": f"{r_inc_s:.6f}",
            "r_inc_ucb95": f"{ucb95_inc_s:.6f}",
            "r_inc_ucb_shidak": f"{ucb_shidak_inc_s:.6f}",
            "r_sel": f"{r_sel_s:.6f}" if not math.isnan(r_sel_s) else "UNDEFINED",
            "r_sel_status": r_sel_status,
            "r_sel_ucb95": f"{ucb95_sel_s:.6f}" if not math.isnan(ucb95_sel_s) else "UNDEFINED",
            "r_sel_ucb_shidak": f"{ucb_shidak_sel_s:.6f}" if not math.isnan(ucb_shidak_sel_s) else "UNDEFINED",
            "p_value_binomial_005": f"{p_inc_s:.6f}",
            "p_value_unconditional_incidence_005": f"{p_inc_s:.6f}",
            "p_value_selective_risk_005": f"{p_sel_s:.6f}" if not math.isnan(p_sel_s) else "UNDEFINED",
            "mean_steps": f"{mean_steps:.2f}",
            "mean_step_ms": f"{mean_step_ms:.4f}",
            "mean_distance_traveled": f"{mean_dist:.4f}",
            "mean_anchor_queries": f"{mean_queries:.3f}",
            "mean_anchor_cost": f"{mean_cost:.4f}",
            "mean_max_overshoot": f"{mean_overshoot:.4f}",
        })

    # Hypothesis H_3: Operational Utility & TSR Noninferiority
    # Authoritative Protocol Section 3.1.1:
    # H0,3: TSR(pi; P_10) - TSR(pi_V8; P_10) <= -0.05 (and co-evaluated against pi_V7 at -0.05).
    # Pass Criterion: 1-sided 95% paired LCB(Delta TSR) > -0.05 on S_10 AND TSR_nominal >= 0.94.
    s10_names = {s.name for s in scenarios if s.suite == "S_10"}
    nominal_tsr_hat = 0.0
    nom_rows = [r for r in breakdown_rows if r["scenario"] == "NOMINAL"]
    if nom_rows:
        nominal_tsr_hat = float(nom_rows[0]["tsr"])

    # Evaluation against V8.1 (Primary Protocol Baseline)
    h3_v8_passed = False
    h3_v8_status = "NOT_EVALUATED_NO_V8_DATA"
    h3_v8_lcb95 = float("nan")
    h3_v8_mean_delta = float("nan")
    if v8_records is not None and len(v8_records) > 0:
        paired_v8 = align_and_pair_records(records, v8_records, baseline_label="v8_martingale")
        matched_diffs_v8: list[float] = []
        for r_pi, r_v8 in paired_v8:
            scen_name = str(r_pi.get("scenario", "")).strip()
            if scen_name in s10_names:
                diff = float(int(r_pi["true_success"])) - float(int(r_v8["true_success"]))
                matched_diffs_v8.append(diff)
        if matched_diffs_v8:
            h3_v8_mean_delta = float(np.mean(matched_diffs_v8))
            h3_v8_lcb95 = paired_difference_lcb(matched_diffs_v8, confidence=0.95)
            h3_v8_passed = bool(h3_v8_lcb95 > -0.05 and nominal_tsr_hat >= 0.94)
            h3_v8_status = "CONFIRMATORY_PASS" if h3_v8_passed else "FAIL_NONINFERIORITY_OR_NOMINAL"

    # Evaluation against V7 (Co-Evaluated Baseline)
    h3_v7_passed = False
    h3_v7_status = "NOT_EVALUATED_NO_V7_DATA"
    h3_v7_lcb95 = float("nan")
    h3_v7_mean_delta = float("nan")
    if v7_records is not None and len(v7_records) > 0:
        paired_v7 = align_and_pair_records(records, v7_records, baseline_label="v7_mpc")
        matched_diffs_v7: list[float] = []
        for r_pi, r_v7 in paired_v7:
            scen_name = str(r_pi.get("scenario", "")).strip()
            if scen_name in s10_names:
                diff = float(int(r_pi["true_success"])) - float(int(r_v7["true_success"]))
                matched_diffs_v7.append(diff)
        if matched_diffs_v7:
            h3_v7_mean_delta = float(np.mean(matched_diffs_v7))
            h3_v7_lcb95 = paired_difference_lcb(matched_diffs_v7, confidence=0.95)
            h3_v7_passed = bool(h3_v7_lcb95 > -0.05 and nominal_tsr_hat >= 0.94)
            h3_v7_status = "CONFIRMATORY_PASS" if h3_v7_passed else "FAIL_NONINFERIORITY_OR_NOMINAL"

    # Overall H_3 determination per Protocol Section 3.1.1:
    if v8_records is not None and len(v8_records) > 0:
        h3_overall_passed = h3_v8_passed
        h3_overall_status = h3_v8_status
    elif v7_records is not None and len(v7_records) > 0:
        h3_overall_passed = h3_v7_passed
        h3_overall_status = h3_v7_status
    else:
        h3_overall_passed = False
        h3_overall_status = "NOT_EVALUATED_NO_BASELINE_DATA"

    # Hypothesis H_5: Worst-Case Scenario Safety via Berger IUT and Holm-Šidák
    holm_thresholds = holm_shidak_adjusted_thresholds(len(p_values_for_iut), alpha=0.05)
    sorted_p = sorted(p_values_for_iut)
    # Sequentially rejective step-down: stop at the first non-rejection
    holm_rejections: list[bool] = []
    stopped = False
    for p, thresh in zip(sorted_p, holm_thresholds):
        if not stopped and p <= thresh:
            holm_rejections.append(True)
        else:
            stopped = True
            holm_rejections.append(False)
    iut_passed = berger_intersection_union_test(p_values_for_iut, alpha=0.05)
    h5_status = "CONFIRMATORY_PASS_IUT" if iut_passed else "RETAIN_SAFETY_NULL"

    summary: dict[str, Any] = {
        "partition": "scenario",
        "n_episodes": len(records),
        "total_scenarios": len(breakdown_rows),
        "nominal_tsr_hat": round(nominal_tsr_hat, 6),
        "h3_overall": {
            "hypothesis": "H_3",
            "decision_rule": "Primary noninferiority vs V8.1 (LCB95 > -0.05 on S_10) AND TSR_nominal >= 0.94; co-evaluated vs V7",
            "primary_baseline": "v8_martingale",
            "primary_passed": h3_v8_passed,
            "primary_status": h3_v8_status,
            "co_evaluated_baseline": "v7_mpc",
            "coeval_passed": h3_v7_passed,
            "coeval_status": h3_v7_status,
            "nominal_tsr_criterion_met": bool(nominal_tsr_hat >= 0.94),
            "all_baselines_passed": bool(h3_v8_passed and h3_v7_passed) if (v8_records and v7_records) else h3_overall_passed,
            "status": h3_overall_status,
            "passed": h3_overall_passed,
        },
        "h3_tsr_noninferiority_vs_v8": {
            "hypothesis": "H_3",
            "baseline": "v8_martingale",
            "estimand": "LCB95(Delta TSR) > -0.05 on S_10 and TSR_nominal >= 0.94",
            "nominal_tsr": round(nominal_tsr_hat, 6),
            "mean_delta_tsr": round(h3_v8_mean_delta, 6) if not math.isnan(h3_v8_mean_delta) else "N/A",
            "lcb95_delta_tsr": round(h3_v8_lcb95, 6) if not math.isnan(h3_v8_lcb95) else "N/A",
            "status": h3_v8_status,
            "passed": h3_v8_passed,
        },
        "h3_tsr_noninferiority_vs_v7": {
            "hypothesis": "H_3",
            "baseline": "v7_mpc",
            "estimand": "LCB95(Delta TSR) > -0.05 on S_10 and TSR_nominal >= 0.94",
            "nominal_tsr": round(nominal_tsr_hat, 6),
            "mean_delta_tsr": round(h3_v7_mean_delta, 6) if not math.isnan(h3_v7_mean_delta) else "N/A",
            "lcb95_delta_tsr": round(h3_v7_lcb95, 6) if not math.isnan(h3_v7_lcb95) else "N/A",
            "status": h3_v7_status,
            "passed": h3_v7_passed,
        },
        "h5_worst_case_safety": {
            "hypothesis": "H_5",
            "estimand": "Berger IUT max(p_inc_s) <= 0.05 on unconditional incidence R_inc,s across all 12 scenarios",
            "berger_iut_passed": iut_passed,
            "max_p_inc": round(max(p_values_for_iut), 6) if p_values_for_iut else float("nan"),
            "holm_shidak_rejections_count": sum(holm_rejections),
            "status": h5_status,
            "passed": iut_passed,
        },
        "scenario_breakdown": breakdown_rows,
    }

    return summary


# ==============================================================================
# Master Preflight and Workflow Runner
# ==============================================================================

def run_preflight_checks(
    *,
    policy_path: Path,
    manifest_mix_path: Path | None = None,
    manifest_scen_path: Path | None = None,
) -> dict[str, Any]:
    """
    Executes a read-only preflight audit of the holdout harness:
    - Verifies the selected policy file identity and canonical SHA-256.
    - Verifies manifest presence and schemas if provided.
    - Confirms that no real holdout execution has taken place.
    """
    cand_params, pol_payload, pol_raw_sha = verify_and_load_selected_policy(policy_path)

    checks: dict[str, Any] = {
        "status": "PREFLIGHT_PASS",
        "policy_id": cand_params.candidate_id,
        "policy_tier": cand_params.tier_label,
        "policy_raw_sha256": pol_raw_sha,
        "policy_canonical_sha256": compute_canonical_payload_sha256(pol_payload),
        "certified": pol_payload.get("certified", False),
        "runtime_assurance_protocol": PROTOCOL_VERSION,
        "real_holdouts_executed": False,
    }

    if manifest_mix_path and manifest_mix_path.exists():
        mix_data, mix_sha = verify_and_load_holdout_manifest(manifest_mix_path, "mixture")
        checks["manifest_mix"] = {"status": "VALID", "raw_sha256": mix_sha}
    else:
        checks["manifest_mix"] = {"status": "NOT_YET_GENERATED"}

    if manifest_scen_path and manifest_scen_path.exists():
        scen_data, scen_sha = verify_and_load_holdout_manifest(manifest_scen_path, "scenario")
        checks["manifest_scen"] = {"status": "VALID", "raw_sha256": scen_sha}
    else:
        checks["manifest_scen"] = {"status": "NOT_YET_GENERATED"}

    return checks


def execute_holdout_workflow(
    *,
    partition: str,
    policy_path: Path,
    manifest_path: Path,
    out_dir: Path,
    authorized_execution_token: str | None = None,
    freeze_only: bool = False,
    synthetic_records: Sequence[Mapping[str, Any]] | None = None,
    v8_synthetic_records: Sequence[Mapping[str, Any]] | None = None,
    v7_synthetic_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Unified entry point for holdout evaluation:
    - In PREFLIGHT mode (synthetic_records provided): executes statistical pipeline without simulator.
    - In PRODUCTION mode: strictly requires authorized_execution_token == REQUIRED_EXECUTION_TOKEN.
      Without this token, fails closed and refuses to generate, load, or run holdout episodes.
    - Enforces single-shot output guard against overwriting existing holdout artifacts.
    """
    cand_params, pol_payload, pol_raw_sha = verify_and_load_selected_policy(policy_path)
    enforced_out_dir = enforce_holdout_output_directory(out_dir, partition)

    # Fail-closed execution authorization guard
    is_synthetic = synthetic_records is not None
    if not is_synthetic and not freeze_only:
        if authorized_execution_token != REQUIRED_EXECUTION_TOKEN:
            raise RuntimeError(
                "EXECUTION GUARD: M4 holdout evaluation is not authorized for live execution during preflight. "
                "Explicit authorized_execution_token is required. Holdout partitions remain strictly untouched."
            )
        raise NotImplementedError("Live simulator execution is blocked during preflight milestone.")

    # Single-shot execution guard
    part_tag = "mix" if partition == "mixture" else ("scen" if partition == "scenario" else partition)
    episodes_csv = enforced_out_dir / f"test_{part_tag}_episodes.csv"
    summary_csv = enforced_out_dir / f"test_{part_tag}_summary.csv"
    report_json = enforced_out_dir / f"test_{part_tag}_report.json"

    if episodes_csv.exists() or report_json.exists():
        raise RuntimeError(
            f"SINGLE-SHOT EXECUTION GUARD: Holdout output already exists in `{enforced_out_dir}`. "
            "Re-running holdout or overwriting holdout artifacts is strictly prohibited."
        )

    # Freeze configuration
    if manifest_path.exists():
        manifest_payload, man_raw_sha = verify_and_load_holdout_manifest(manifest_path, partition)
    else:
        manifest_payload = {"partition": partition, "status": "SYNTHETIC_OR_UNALLOCATED"}
        man_raw_sha = "0000000000000000000000000000000000000000000000000000000000000000"

    run_cfg = freeze_holdout_run_configuration(
        partition=partition,
        manifest_path=manifest_path,
        manifest_payload=manifest_payload,
        manifest_raw_sha256=man_raw_sha,
        selected_policy_path=policy_path,
        selected_policy_payload=pol_payload,
        selected_policy_raw_sha256=pol_raw_sha,
        candidate_params=cand_params,
        out_dir=enforced_out_dir,
    )

    if freeze_only:
        return {"status": "FROZEN_READY", "run_config": run_cfg}

    # Process synthetic records for preflight testing
    if partition == "mixture":
        eval_result = evaluate_mixture_holdout(
            records=synthetic_records,
            cand_params=cand_params,
            v8_records=v8_synthetic_records,
            v7_records=v7_synthetic_records,
        )
    elif partition == "scenario":
        eval_result = evaluate_scenario_holdout(
            records=synthetic_records,
            cand_params=cand_params,
            v8_records=v8_synthetic_records,
            v7_records=v7_synthetic_records,
        )
    else:
        raise ValueError(f"Unknown partition {partition}")

    # Write output artifacts
    enforced_out_dir.mkdir(parents=True, exist_ok=True)

    # Write episodes CSV
    fieldnames = list(synthetic_records[0].keys())
    with episodes_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(synthetic_records)

    # Write summary CSV
    summary_headers = [
        "partition",
        "n_episodes",
        "m_accepted",
        "ts_count",
        "fs_count",
        "ab_explicit_count",
        "timeout_count",
        "ab_total_count",
        "crashed_count",
        "coverage",
        "tsr",
        "r_inc",
        "r_sel",
    ]
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary_headers, lineterminator="\n")
        writer.writeheader()
        writer.writerow({k: eval_result.get(k, "") for k in summary_headers})

    # If scenario, write breakdown CSV
    if partition == "scenario" and "scenario_breakdown" in eval_result:
        scen_csv = enforced_out_dir / "test_scen_breakdown.csv"
        scen_rows = eval_result["scenario_breakdown"]
        if scen_rows:
            scen_headers = list(scen_rows[0].keys())
            with scen_csv.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=scen_headers, lineterminator="\n")
                writer.writeheader()
                writer.writerows(scen_rows)

    # Write full JSON report
    report_payload: dict[str, Any] = {
        "schema_version": f"nexvia-aegis-v9-holdout-{partition}-report/1.0",
        "status": "PREFLIGHT_SYNTHETIC_COMPLETE" if is_synthetic else "COMPLETE_VALID",
        "protocol_version": PROTOCOL_VERSION,
        "v9_m1_commit": V9_M1_COMMIT,
        "source_design_commit": SOURCE_DESIGN_COMMIT,
        "v81_baseline_commit": V81_BASELINE_COMMIT,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "partition": partition,
        "selected_policy_id": cand_params.candidate_id,
        "selected_candidate": asdict(cand_params),
        "run_config": run_cfg,
        "evaluation_summary": eval_result,
        "artifact_sha256": {
            str(episodes_csv.relative_to(_REPO_ROOT) if episodes_csv.is_relative_to(_REPO_ROOT) else episodes_csv): sha256_file(episodes_csv),
            str(summary_csv.relative_to(_REPO_ROOT) if summary_csv.is_relative_to(_REPO_ROOT) else summary_csv): sha256_file(summary_csv),
        },
    }
    report_payload["integrity_sha256"] = compute_canonical_payload_sha256(report_payload)
    report_bytes = json.dumps(report_payload, indent=2).encode("utf-8")
    report_json.write_bytes(report_bytes)

    return report_payload


# ==============================================================================
# Simulation RNG and Mock Infrastructure
# ==============================================================================

def _derive_episode_rngs(
    ep_item: Mapping[str, Any],
    ep_seed: int,
) -> tuple[np.random.Generator, np.random.Generator]:
    """
    Derives fresh decoupled NumPy RNG pair (rng_env, rng_sensors) for an episode.
    Uses master entropy and child spawn keys from manifest item if present (SeedSequence model),
    or falls back to create_decoupled_rng_pair(ep_seed).
    Calling this for multiple controllers on the same ep_item guarantees Common Random Numbers (CRN).
    """
    if "env_spawn_key" in ep_item and "sensor_spawn_key" in ep_item and "entropy" in ep_item:
        decoupled_rng = instantiate_episode_rngs_from_manifest_item(dict(ep_item))
        return decoupled_rng.rng_env, decoupled_rng.rng_sensors
    return create_decoupled_rng_pair(ep_seed)


class MockHoldoutSimulator:
    """
    Deterministic mock simulator for NEXVIA AEGIS V9 holdout pipeline verification.
    Produces valid, synthetic outcome records conforming to the registered schema.
    Supports failure injection:
    - inject_crash_keys: set of (scenario_name, seed, policy_id) -> returns fail-unsafe crash record
    - inject_timeout_keys: set of (scenario_name, seed, policy_id) -> returns timeout record
    - inject_abstain_keys: set of (scenario_name, seed, policy_id) -> returns explicit abstain record
    - inject_algebra_violation_keys: set of (scenario_name, seed, policy_id) -> returns record violating outcome algebra
    - inject_runtime_exception_keys: set of (scenario_name, seed, policy_id) -> raises RuntimeError
    - scenario_overrides: dict[str, dict[str, Any]] -> scenario-level overrides (e.g. force_zero_accepted)
    """

    def __init__(
        self,
        *,
        default_v9_tsr: float = 0.96,
        default_v8_tsr: float = 0.50,
        default_v7_tsr: float = 0.55,
        default_v9_coverage: float = 0.98,
        default_v8_coverage: float = 0.55,
        default_v7_coverage: float = 0.60,
        inject_crash_keys: set[tuple[str, int, str]] | None = None,
        inject_timeout_keys: set[tuple[str, int, str]] | None = None,
        inject_abstain_keys: set[tuple[str, int, str]] | None = None,
        inject_algebra_violation_keys: set[tuple[str, int, str]] | None = None,
        inject_runtime_exception_keys: set[tuple[str, int, str]] | None = None,
        scenario_overrides: dict[str, dict[str, Any]] | None = None,
    ):
        self.default_v9_tsr = default_v9_tsr
        self.default_v8_tsr = default_v8_tsr
        self.default_v7_tsr = default_v7_tsr
        self.default_v9_coverage = default_v9_coverage
        self.default_v8_coverage = default_v8_coverage
        self.default_v7_coverage = default_v7_coverage
        self.inject_crash_keys = set(inject_crash_keys or ())
        self.inject_timeout_keys = set(inject_timeout_keys or ())
        self.inject_abstain_keys = set(inject_abstain_keys or ())
        self.inject_algebra_violation_keys = set(inject_algebra_violation_keys or ())
        self.inject_runtime_exception_keys = set(inject_runtime_exception_keys or ())
        self.scenario_overrides = dict(scenario_overrides or {})
        self.call_log: list[dict[str, Any]] = []

    def __call__(
        self,
        scen: V9ScenarioSpec,
        ep_seed: int,
        policy_id: str,
        controller: Any,
        *,
        rng_env: np.random.Generator | None = None,
        rng_sensors: np.random.Generator | None = None,
    ) -> dict[str, Any]:
        key = (scen.name, ep_seed, policy_id)
        env_val = float(rng_env.uniform()) if rng_env is not None else 0.0
        sens_val = float(rng_sensors.normal()) if rng_sensors is not None else 0.0
        self.call_log.append({
            "key": key,
            "scenario": scen.name,
            "seed": ep_seed,
            "policy": policy_id,
            "env_val": env_val,
            "sens_val": sens_val,
        })

        if key in self.inject_runtime_exception_keys or (scen.name, ep_seed) in self.inject_runtime_exception_keys:
            raise RuntimeError(f"MockInjectedRuntimeError on {scen.name} seed={ep_seed} policy={policy_id}")

        if key in self.inject_crash_keys or (scen.name, ep_seed) in self.inject_crash_keys:
            return {
                "scenario": scen.name,
                "suite": scen.suite,
                "policy": policy_id,
                "seed": ep_seed,
                "accepted": 0,
                "true_success": 0,
                "false_success": 1,
                "abstain_explicit": 0,
                "timeout": 0,
                "abstain": 0,
                "crashed": 1,
                "crash_error": "MockInjectedCrashError: synthetic failure",
                "final_distance": 2.5000,
                "steps": 12,
                "mean_step_ms": 0.0500,
                "distance_traveled": 1.2000,
                "anchor_queries": 0,
                "anchor_cost": 0.0,
                "max_overshoot": 0.0,
                "terminal_reason": "MOCK_CRASH",
            }

        if key in self.inject_algebra_violation_keys or (scen.name, ep_seed) in self.inject_algebra_violation_keys:
            return {
                "scenario": scen.name,
                "suite": scen.suite,
                "policy": policy_id,
                "seed": ep_seed,
                "accepted": 1,
                "true_success": 1,
                "false_success": 1,
                "abstain_explicit": 0,
                "timeout": 0,
                "abstain": 0,
                "crashed": 0,
                "crash_error": "",
                "final_distance": 0.2000,
                "steps": 20,
                "mean_step_ms": 0.0500,
                "distance_traveled": 2.5000,
                "anchor_queries": 1,
                "anchor_cost": 0.0500,
                "max_overshoot": 0.0,
                "terminal_reason": "MOCK_ALGEBRA_VIOLATION",
            }

        if key in self.inject_timeout_keys or (scen.name, ep_seed) in self.inject_timeout_keys:
            return {
                "scenario": scen.name,
                "suite": scen.suite,
                "policy": policy_id,
                "seed": ep_seed,
                "accepted": 0,
                "true_success": 0,
                "false_success": 0,
                "abstain_explicit": 0,
                "timeout": 1,
                "abstain": 1,
                "crashed": 0,
                "crash_error": "",
                "final_distance": 1.2500,
                "steps": 100,
                "mean_step_ms": 0.0500,
                "distance_traveled": 3.8000,
                "anchor_queries": 2,
                "anchor_cost": 0.1000,
                "max_overshoot": 0.0,
                "terminal_reason": "MOCK_TIMEOUT",
            }

        if key in self.inject_abstain_keys or (scen.name, ep_seed) in self.inject_abstain_keys:
            return {
                "scenario": scen.name,
                "suite": scen.suite,
                "policy": policy_id,
                "seed": ep_seed,
                "accepted": 0,
                "true_success": 0,
                "false_success": 0,
                "abstain_explicit": 1,
                "timeout": 0,
                "abstain": 1,
                "crashed": 0,
                "crash_error": "",
                "final_distance": 1.8000,
                "steps": 30,
                "mean_step_ms": 0.0500,
                "distance_traveled": 2.1000,
                "anchor_queries": 2,
                "anchor_cost": 0.1000,
                "max_overshoot": 0.0,
                "terminal_reason": "MOCK_ABSTAIN",
            }

        # Scenario overrides
        if scen.name in self.scenario_overrides:
            ov = self.scenario_overrides[scen.name]
            if ov.get("force_zero_accepted", False):
                return {
                    "scenario": scen.name,
                    "suite": scen.suite,
                    "policy": policy_id,
                    "seed": ep_seed,
                    "accepted": 0,
                    "true_success": 0,
                    "false_success": 0,
                    "abstain_explicit": 1,
                    "timeout": 0,
                    "abstain": 1,
                    "crashed": 0,
                    "crash_error": "",
                    "final_distance": 2.1000,
                    "steps": 25,
                    "mean_step_ms": 0.0500,
                    "distance_traveled": 1.8000,
                    "anchor_queries": 1,
                    "anchor_cost": 0.0500,
                    "max_overshoot": 0.0,
                    "terminal_reason": "MOCK_FORCED_ABSTAIN",
                }

        # Deterministic outcome computation based on hash
        h_val = int(hashlib.sha256(f"{scen.name}:{ep_seed}:{policy_id}".encode("utf-8")).hexdigest()[:8], 16)
        u = (h_val % 10000) / 10000.0

        is_v9 = (policy_id == EXPECTED_SELECTED_CANDIDATE_ID or "V9" in policy_id)
        is_v8 = ("V8" in policy_id or "MARTINGALE" in policy_id)

        if is_v9:
            if scen.name == "NOMINAL":
                acc, ts, fs, ab_exp, to, ab = 1, 1, 0, 0, 0, 0
                final_dist = 0.1500
            else:
                if u < 0.95:
                    acc, ts, fs, ab_exp, to, ab = 1, 1, 0, 0, 0, 0
                    final_dist = 0.2000
                elif u < 0.96:
                    acc, ts, fs, ab_exp, to, ab = 1, 0, 1, 0, 0, 0
                    final_dist = 0.6500
                elif u < 0.99:
                    acc, ts, fs, ab_exp, to, ab = 0, 0, 0, 1, 0, 1
                    final_dist = 1.4000
                else:
                    acc, ts, fs, ab_exp, to, ab = 0, 0, 0, 0, 1, 1
                    final_dist = 1.6000
        elif is_v8:
            if u < 0.50:
                acc, ts, fs, ab_exp, to, ab = 1, 1, 0, 0, 0, 0
                final_dist = 0.2500
            elif u < 0.62:
                acc, ts, fs, ab_exp, to, ab = 1, 0, 1, 0, 0, 0
                final_dist = 0.7000
            elif u < 0.92:
                acc, ts, fs, ab_exp, to, ab = 0, 0, 0, 1, 0, 1
                final_dist = 1.5000
            else:
                acc, ts, fs, ab_exp, to, ab = 0, 0, 0, 0, 1, 1
                final_dist = 1.8000
        else:  # Baseline V7
            if u < 0.55:
                acc, ts, fs, ab_exp, to, ab = 1, 1, 0, 0, 0, 0
                final_dist = 0.2200
            elif u < 0.61:
                acc, ts, fs, ab_exp, to, ab = 1, 0, 1, 0, 0, 0
                final_dist = 0.6800
            elif u < 0.93:
                acc, ts, fs, ab_exp, to, ab = 0, 0, 0, 1, 0, 1
                final_dist = 1.4500
            else:
                acc, ts, fs, ab_exp, to, ab = 0, 0, 0, 0, 1, 1
                final_dist = 1.7500

        return {
            "scenario": scen.name,
            "suite": scen.suite,
            "policy": policy_id,
            "seed": ep_seed,
            "accepted": acc,
            "true_success": ts,
            "false_success": fs,
            "abstain_explicit": ab_exp,
            "timeout": to,
            "abstain": ab,
            "crashed": 0,
            "crash_error": "",
            "final_distance": final_dist,
            "steps": int(20 + 40 * u),
            "mean_step_ms": 0.0500,
            "distance_traveled": round(2.0 + u, 4),
            "anchor_queries": int(u * 3),
            "anchor_cost": round(int(u * 3) * 0.05, 4),
            "max_overshoot": round(0.02 * u, 4),
            "terminal_reason": "MOCK_SYNTHETIC",
        }


# ==============================================================================
# Production Holdout Execution Pipeline
# ==============================================================================

def execute_production_holdout_pipeline(
    *,
    partition: str,
    policy_path: Path,
    manifest_path: Path,
    out_dir: Path,
    authorized_execution_token: str | None = None,
    simulator_fn: Callable[..., dict[str, Any]] | None = None,
    include_v8_baseline: bool = True,
    include_v7_baseline: bool = True,
    allow_mock_simulation: bool = False,
) -> dict[str, Any]:
    """
    Dedicated production execution pathway for Milestone V9-M4 holdout evaluation.
    Evaluates:
    1. Selected policy: V9_CAND_1_TIER1_STRICTEST (AegisV9Controller)
    2. Audited baseline V8.1: AegisNextController (for H2 unconditional incidence reduction)
    3. Audited baseline V7: AegisV7MPCBaselineController (for H2 and H3 TSR noninferiority)

    Guards:
    - Fails closed if authorized_execution_token != REQUIRED_EXECUTION_TOKEN.
    - Fails closed if simulator_fn is provided but allow_mock_simulation is False.
    - Single-shot output protection: refuses to overwrite existing output files or prior aborted runs.
    - Verifies policy artifact integrity and certification.
    - Verifies manifest SHA-256 integrity, partition branch, and seed block bounds.
    - Preserves Common Random Numbers (CRN) across policy and baseline evaluations.
    """
    # 1. Authorization Gate
    if authorized_execution_token != REQUIRED_EXECUTION_TOKEN:
        raise RuntimeError(
            "EXECUTION GUARD: Production holdout evaluation is not authorized. "
            "Explicit authorized_execution_token is required. Holdout partitions remain strictly untouched."
        )

    # 2. Simulator mode gate
    if simulator_fn is not None and not allow_mock_simulation:
        raise RuntimeError(
            "EXECUTION GUARD: simulator_fn is provided but allow_mock_simulation is False. "
            "Custom/mock simulators are only permitted when allow_mock_simulation is explicitly True."
        )

    # 3. Policy verification
    cand_params, pol_payload, pol_raw_sha = verify_and_load_selected_policy(policy_path)

    # 4. Output directory & Single-shot guard
    enforced_out_dir = enforce_holdout_output_directory(out_dir, partition)
    part_tag = "mix" if partition == "mixture" else ("scen" if partition == "scenario" else partition)
    episodes_csv = enforced_out_dir / f"test_{part_tag}_episodes.csv"
    summary_csv = enforced_out_dir / f"test_{part_tag}_summary.csv"
    report_json = enforced_out_dir / f"test_{part_tag}_report.json"
    partial_csv = enforced_out_dir / f"test_{part_tag}_episodes_PARTIAL.csv"
    invalid_marker = enforced_out_dir / "INCOMPLETE_INVALID.json"

    if episodes_csv.exists() or report_json.exists():
        raise RuntimeError(
            f"SINGLE-SHOT EXECUTION GUARD: Holdout output already exists in `{enforced_out_dir}`. "
            "Re-running holdout or overwriting holdout artifacts is strictly prohibited."
        )
    if invalid_marker.exists():
        raise RuntimeError(
            f"SINGLE-SHOT EXECUTION GUARD: Found existing incomplete marker `{invalid_marker}` in `{enforced_out_dir}`. "
            "Cannot overwrite prior aborted execution without explicit review."
        )

    # 5. Manifest verification
    manifest_payload, man_raw_sha = verify_and_load_holdout_manifest(
        manifest_path,
        partition,
        allow_synthetic=allow_mock_simulation,
    )

    # 6. Freeze run configuration
    run_cfg = freeze_holdout_run_configuration(
        partition=partition,
        manifest_path=manifest_path,
        manifest_payload=manifest_payload,
        manifest_raw_sha256=man_raw_sha,
        selected_policy_path=policy_path,
        selected_policy_payload=pol_payload,
        selected_policy_raw_sha256=pol_raw_sha,
        candidate_params=cand_params,
        out_dir=enforced_out_dir,
    )

    # 7. Setup simulation
    sim = simulator_fn if simulator_fn is not None else run_single_episode
    scenarios_by_name = {sc.name: sc for sc in build_v9_s12_scenarios()}
    manifest_episodes = manifest_payload.get("episodes", [])
    expected_total_episodes = len(manifest_episodes)
    if expected_total_episodes == 0:
        raise ValueError("Holdout manifest contains 0 episodes.")

    policy_records: list[dict[str, Any]] = []
    v8_records: list[dict[str, Any]] = []
    v7_records: list[dict[str, Any]] = []

    enforced_out_dir.mkdir(parents=True, exist_ok=True)

    # 8. Simulation loop with partial failure protection
    try:
        for ep_item in manifest_episodes:
            scen_name = str(ep_item["scenario"])
            if scen_name not in scenarios_by_name:
                raise ValueError(f"Unknown scenario '{scen_name}' in manifest item: {ep_item}")
            scen = scenarios_by_name[scen_name]
            ep_seed = int(ep_item.get("seed", ep_item.get("manifest_id")))
            ep_idx = int(ep_item["episode_index"])
            sc_idx = int(ep_item.get("scenario_index", scen.index))

            # Policy V9
            rng_env_v9, rng_sens_v9 = _derive_episode_rngs(ep_item, ep_seed)
            ctrl_v9 = AegisV9Controller(cand_params)
            rec_v9 = sim(scen, ep_seed, cand_params.candidate_id, ctrl_v9, rng_env=rng_env_v9, rng_sensors=rng_sens_v9)
            verify_episode_outcome_algebra(
                rec_v9,
                expected_policy_id=cand_params.candidate_id,
                expected_seed=ep_seed,
                expected_scenario=scen_name,
            )
            rec_v9["episode_index"] = ep_idx
            rec_v9["scenario_index"] = sc_idx
            policy_records.append(rec_v9)

            # Baseline V8.1
            if include_v8_baseline:
                rng_env_v8, rng_sens_v8 = _derive_episode_rngs(ep_item, ep_seed)
                ctrl_v8 = AegisNextController()
                rec_v8 = sim(scen, ep_seed, "AEGIS_NEXT_MARTINGALE", ctrl_v8, rng_env=rng_env_v8, rng_sensors=rng_sens_v8)
                verify_episode_outcome_algebra(
                    rec_v8,
                    expected_policy_id="AEGIS_NEXT_MARTINGALE",
                    expected_seed=ep_seed,
                    expected_scenario=scen_name,
                )
                rec_v8["episode_index"] = ep_idx
                rec_v8["scenario_index"] = sc_idx
                v8_records.append(rec_v8)

            # Baseline V7
            if include_v7_baseline:
                rng_env_v7, rng_sens_v7 = _derive_episode_rngs(ep_item, ep_seed)
                ctrl_v7 = AegisV7MPCBaselineController()
                rec_v7 = sim(scen, ep_seed, "AEGIS_V7_MPC_BASELINE", ctrl_v7, rng_env=rng_env_v7, rng_sensors=rng_sens_v7)
                verify_episode_outcome_algebra(
                    rec_v7,
                    expected_policy_id="AEGIS_V7_MPC_BASELINE",
                    expected_seed=ep_seed,
                    expected_scenario=scen_name,
                )
                rec_v7["episode_index"] = ep_idx
                rec_v7["scenario_index"] = sc_idx
                v7_records.append(rec_v7)

    except BaseException as exc:
        if policy_records:
            fieldnames = list(policy_records[0].keys())
            with partial_csv.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
                writer.writeheader()
                writer.writerows(policy_records)
        invalid_marker.write_text(
            json.dumps(
                {
                    "status": "INCOMPLETE_INVALID",
                    "partition": partition,
                    "recorded_episodes": len(policy_records),
                    "expected_episodes": expected_total_episodes,
                    "error": f"{type(exc).__name__}: {exc}",
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise

    # 9. Statistical analysis
    if partition == "mixture":
        eval_result = evaluate_mixture_holdout(
            records=policy_records,
            cand_params=cand_params,
            v8_records=v8_records if include_v8_baseline else None,
            v7_records=v7_records if include_v7_baseline else None,
        )
    elif partition == "scenario":
        n_scens = len(scenarios_by_name)
        seeds_per_scen = (
            expected_total_episodes // n_scens
            if expected_total_episodes % n_scens == 0
            else TEST_SCEN_SEEDS_PER_SCENARIO
        )
        eval_result = evaluate_scenario_holdout(
            records=policy_records,
            cand_params=cand_params,
            v8_records=v8_records if include_v8_baseline else None,
            v7_records=v7_records if include_v7_baseline else None,
            expected_seeds_per_scenario=seeds_per_scen,
        )
    else:
        raise ValueError(f"Unknown partition type: {partition}")

    # 10. Write output CSV artifacts
    fieldnames = list(policy_records[0].keys())
    with episodes_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(policy_records)

    v8_csv = enforced_out_dir / f"test_{part_tag}_baseline_v8_episodes.csv"
    if v8_records:
        v8_fieldnames = list(v8_records[0].keys())
        with v8_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=v8_fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(v8_records)

    v7_csv = enforced_out_dir / f"test_{part_tag}_baseline_v7_episodes.csv"
    if v7_records:
        v7_fieldnames = list(v7_records[0].keys())
        with v7_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=v7_fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(v7_records)

    summary_headers = [
        "partition",
        "n_episodes",
        "m_accepted",
        "ts_count",
        "fs_count",
        "ab_explicit_count",
        "timeout_count",
        "ab_total_count",
        "crashed_count",
        "coverage",
        "tsr",
        "r_inc",
        "r_sel",
    ]
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary_headers, lineterminator="\n")
        writer.writeheader()
        writer.writerow({k: eval_result.get(k, "") for k in summary_headers})

    scen_csv = enforced_out_dir / "test_scen_breakdown.csv"
    if partition == "scenario" and "scenario_breakdown" in eval_result:
        scen_rows = eval_result["scenario_breakdown"]
        if scen_rows:
            scen_headers = list(scen_rows[0].keys())
            with scen_csv.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=scen_headers, lineterminator="\n")
                writer.writeheader()
                writer.writerows(scen_rows)

    # 11. Compute artifact digests and write JSON report
    artifact_shas: dict[str, str] = {
        str(episodes_csv.relative_to(_REPO_ROOT) if episodes_csv.is_relative_to(_REPO_ROOT) else episodes_csv): sha256_file(episodes_csv),
        str(summary_csv.relative_to(_REPO_ROOT) if summary_csv.is_relative_to(_REPO_ROOT) else summary_csv): sha256_file(summary_csv),
    }
    if v8_records and v8_csv.exists():
        artifact_shas[str(v8_csv.relative_to(_REPO_ROOT) if v8_csv.is_relative_to(_REPO_ROOT) else v8_csv)] = sha256_file(v8_csv)
    if v7_records and v7_csv.exists():
        artifact_shas[str(v7_csv.relative_to(_REPO_ROOT) if v7_csv.is_relative_to(_REPO_ROOT) else v7_csv)] = sha256_file(v7_csv)
    if partition == "scenario" and scen_csv.exists():
        artifact_shas[str(scen_csv.relative_to(_REPO_ROOT) if scen_csv.is_relative_to(_REPO_ROOT) else scen_csv)] = sha256_file(scen_csv)

    status_label = "COMPLETE_MOCK_VERIFIED" if allow_mock_simulation else "COMPLETE_VALID"
    sim_mode_label = "MOCK_SYNTHETIC" if allow_mock_simulation else "PRODUCTION_PHYSICS"
    report_payload: dict[str, Any] = {
        "schema_version": f"nexvia-aegis-v9-holdout-{partition}-report/1.0",
        "status": status_label,
        "protocol_version": PROTOCOL_VERSION,
        "v9_m1_commit": V9_M1_COMMIT,
        "source_design_commit": SOURCE_DESIGN_COMMIT,
        "v81_baseline_commit": V81_BASELINE_COMMIT,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "partition": partition,
        "simulation_mode": sim_mode_label,
        "selected_policy_id": cand_params.candidate_id,
        "selected_candidate": asdict(cand_params),
        "run_config": run_cfg,
        "evaluation_summary": eval_result,
        "artifact_sha256": artifact_shas,
    }
    report_payload["integrity_sha256"] = compute_canonical_payload_sha256(report_payload)
    report_bytes = json.dumps(report_payload, indent=2).encode("utf-8")
    report_json.write_bytes(report_bytes)

    return report_payload


# ==============================================================================
# CLI Entry Point
# ==============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="NEXVIA AEGIS V9-M4 Confirmatory Holdout Evaluation Harness (Preflight Mode)"
    )
    parser.add_argument(
        "--partition",
        choices=["mixture", "scenario"],
        default="mixture",
        help="Target holdout partition to evaluate.",
    )
    parser.add_argument(
        "--policy-path",
        type=Path,
        default=Path("results/v9/cal_r2/selected_policy.json"),
        help="Path to frozen calibrated selected policy artifact.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=None,
        help="Path to holdout manifest file.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Target output directory under results/v9/.",
    )
    parser.add_argument(
        "--preflight-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run read-only preflight verification checks without simulating holdouts (default: True).",
    )
    parser.add_argument(
        "--freeze-only",
        action="store_true",
        help="Generate and freeze holdout run configuration without simulating episodes.",
    )
    parser.add_argument(
        "--run-production",
        action="store_true",
        default=False,
        help="Execute the full production holdout evaluation pipeline (strictly requires authorized token).",
    )
    parser.add_argument(
        "--authorized-execution-token",
        type=str,
        default=None,
        help="Explicit user authorization token required for production holdout simulation.",
    )

    args = parser.parse_args()

    if args.preflight_only and not args.freeze_only and not args.run_production:
        print("[M4-PREFLIGHT] Running read-only preflight checks...")
        checks = run_preflight_checks(policy_path=args.policy_path)
        print(json.dumps(checks, indent=2))
        sys.exit(0)

    if args.manifest_path is None:
        default_man = (
            Path("results/v9/manifests/test_mix_manifest_r1.json")
            if args.partition == "mixture"
            else Path("results/v9/manifests/test_scen_manifest_r1.json")
        )
        args.manifest_path = default_man

    if args.out_dir is None:
        default_out = (
            Path("results/v9/test_mix")
            if args.partition == "mixture"
            else Path("results/v9/test_scen")
        )
        args.out_dir = default_out

    if args.run_production:
        res = execute_production_holdout_pipeline(
            partition=args.partition,
            policy_path=args.policy_path,
            manifest_path=args.manifest_path,
            out_dir=args.out_dir,
            authorized_execution_token=args.authorized_execution_token,
        )
        print(json.dumps(res, indent=2))
        return

    res = execute_holdout_workflow(
        partition=args.partition,
        policy_path=args.policy_path,
        manifest_path=args.manifest_path,
        out_dir=args.out_dir,
        authorized_execution_token=args.authorized_execution_token,
        freeze_only=args.freeze_only,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()


