"""
NEXVIA AEGIS V9.0 — Development-Set-Only (`D_dev`) Candidate Evaluation & Ordering Verifier.

GOVERNANCE & PARTITION GUARDRAILS (`docs/v9_experiment_protocol.md` Sections 2.5.2 & 3.6):
- Evaluates EXCLUSIVELY on the preregistered development grid `D_dev`:
      [(scenario, seed) for scenario in S_12 for seed in range(70000, 70030)]
  (12 scenarios x 30 seeds = 360 matched episodes per policy).
- HARD PROHIBITION: Requests for any seed outside `70000..70029` (including `D_hist`
  `60000..60049`, `D_cal` `71000..71959`, `D_val` `72000..72039`, `D_test^mix`
  `73000..74439`, or `D_test^scen` `75000..75119`) raise `ValueError` immediately.
- HARD OUTPUT ISOLATION: Writes evaluation artifacts ONLY inside `results/v9/dev/`
  (and optionally writes `configs/v9_candidates_frozen.json` when `--write-frozen-config`
  is explicitly passed AND `D_dev` ordering admissibility verification passes).
- NOTE ON STATISTICAL SCOPE: Because `D_dev` is a fixed-quota stratified grid (30 episodes
  per scenario) used for pre-calibration ordering verification, `D_dev` metrics DO NOT
  certify the 5% selective-risk target; formal certification requires single-shot LTT on
  `D_cal` followed by locked holdout evaluation in a subsequent milestone.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any
import numpy as np

from aegis.next.agent_next import AegisNextController
from aegis.next.baselines import AegisV7MPCBaselineController
from aegis.v3.env.world import AegisPhysicalWorld
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig
from aegis.v7.anchor_sensor import AnchorSensor, AnchorSensorConfig
from aegis.v9.controller import AegisV9Controller
from aegis.v9.randomization import create_decoupled_rng_pair
from aegis.v9.risk_statistics import (
    PREREGISTERED_CANDIDATE_FAMILY,
    PolicyEvaluationSummary,
    V9CandidateParams,
    compute_policy_summary,
    verify_preregistered_dev_ordering,
    write_frozen_candidates_json,
)

DEV_SEED_START: int = 70000
DEV_SEED_STOP_EXCLUSIVE: int = 70030
DEV_ALLOWED_SEEDS: frozenset[int] = frozenset(range(DEV_SEED_START, DEV_SEED_STOP_EXCLUSIVE))

PROTOCOL_VERSION: str = "v9.0-preregistered-2026-10"
SOURCE_DESIGN_COMMIT: str = "891c13e7bbd60e36c416c9bada8407e51233e663"
V81_BASELINE_COMMIT: str = "4d891c7500cfb4c8110f276038455bc62765ef3b"


@dataclass(frozen=True)
class V9ScenarioSpec:
    """Frozen scenario definition in the 12-scenario suite S_12."""

    index: int
    name: str
    suite: str
    description: str
    sensor_a: SensorConfig
    sensor_b: SensorConfig
    range_sensor_noise: float = 0.05
    range_sensor_bias: float = 0.0
    range_dropout_prob: float = 0.0
    anchor_corrupted: bool = False


def build_v9_s12_scenarios() -> tuple[V9ScenarioSpec, ...]:
    """
    Constructs the exact 12-scenario suite S_12 = S_10 U S_ext defined in
    `docs/v9_experiment_protocol.md` Table 3.1.2 (preserving S_10 bit-identically
    with `experiments/benchmark_next.py:71-160`).
    """
    return (
        V9ScenarioSpec(
            index=1,
            name="NOMINAL",
            suite="S_10",
            description="Baseline operation under nominal Gaussian sensor noise",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=2,
            name="PRIMARY_BIAS",
            suite="S_10",
            description="Static spatial bias on primary sensor A (+0.8, -0.6)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.8, -0.6)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=3,
            name="INDEPENDENT_BIAS",
            suite="S_10",
            description="Independent non-identical biases on vector A (+0.6, +0.4) and B (-0.5, +0.5)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.6, 0.4)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.5, 0.5)),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=4,
            name="CORRELATED_BIAS",
            suite="S_10",
            description="Common-mode correlated bias (+0.7, +0.7) on both vector sensors",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=5,
            name="SENSOR_DRIFT",
            suite="S_10",
            description="Non-stationary dynamic drift on sensor A (0.003*t, 0.0015*t)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, drift_rate=(0.003, 0.0015)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=6,
            name="OUTLIER_BURSTS",
            suite="S_10",
            description="Heavy-tailed outlier bursts (p=0.12, 4.5x scale)",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, outlier_probability=0.12, outlier_scale=4.5
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=7,
            name="SENSOR_DROPOUT",
            suite="S_10",
            description="Intermittent packet loss (p=0.40) on sensor A",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, dropout_probability=0.40),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=8,
            name="FAULTY_REFERENCE_SENSOR",
            suite="S_10",
            description="Correlated vector bias (+0.7, +0.7) AND range corrupted (+1.0m bias)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            range_sensor_bias=1.0,
        ),
        V9ScenarioSpec(
            index=9,
            name="CORRUPTED_ANCHOR_STRESS",
            suite="S_10",
            description="Correlated vector bias (+0.7, +0.7) AND anchor corrupted (+1.2, -1.0m bias)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            anchor_corrupted=True,
        ),
        V9ScenarioSpec(
            index=10,
            name="COMPOUND_HOLDOUT_EXTREME",
            suite="S_10",
            description="Held-out compound stress: vector drift + common bias + range shift (-0.40m)",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.06, bias=(0.5, 0.5), drift_rate=(0.002, 0.002)
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.06, bias=(0.5, 0.5)),
            range_sensor_noise=0.06,
            range_sensor_bias=-0.40,
        ),
        V9ScenarioSpec(
            index=11,
            name="COMPOUND_DRIFT_DROPOUT",
            suite="S_ext",
            description="Asymmetric drift + 30% vec_a dropout + 10% range dropout",
            sensor_a=SensorConfig(
                name="vec_a",
                noise_sigma=0.05,
                bias=(0.0, 0.0),
                drift_rate=(0.0025, -0.0020),
                dropout_probability=0.30,
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.45, 0.35)),
            range_sensor_noise=0.05,
            range_sensor_bias=0.0,
            range_dropout_prob=0.10,
        ),
        V9ScenarioSpec(
            index=12,
            name="COMPOUND_ANTIPODAL_RANGE_SHIFT",
            suite="S_ext",
            description="Near-canceling antipodal biases + 35% vec_b dropout jumps + -0.30m range shift",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.55, 0.40)),
            sensor_b=SensorConfig(
                name="vec_b",
                noise_sigma=0.05,
                bias=(-0.45, -0.35),
                dropout_probability=0.35,
            ),
            range_sensor_noise=0.05,
            range_sensor_bias=-0.30,
        ),
    )


def enforce_dev_only_seeds(seeds: Sequence[int]) -> tuple[int, ...]:
    """Raises ValueError if any seed falls outside the permitted D_dev range 70000..70029."""
    if not seeds:
        raise ValueError("Seed sequence must be non-empty.")
    out = tuple(int(s) for s in seeds)
    forbidden = [s for s in out if s not in DEV_ALLOWED_SEEDS]
    if forbidden:
        raise ValueError(
            f"PROHIBITED SEED ACCESS BLOCKED: {forbidden}. "
            f"Milestone V9-M1 permits ONLY D_dev seeds {DEV_SEED_START}..{DEV_SEED_STOP_EXCLUSIVE - 1}."
        )
    if len(set(out)) != len(out):
        raise ValueError("Duplicate seeds within a scenario grid are not allowed.")
    return out


def enforce_dev_output_directory(out_dir: str | Path) -> Path:
    """Ensures D_dev evaluation writes strictly inside `results/v9/dev`."""
    resolved = Path(out_dir).resolve()
    parts = resolved.parts
    if len(parts) < 3 or parts[-3:] != ("results", "v9", "dev"):
        raise ValueError(
            f"Output path `{resolved}` must end with `results/v9/dev` to protect historical "
            f"results and prevent writing to calibration/holdout directories."
        )
    return resolved


def run_single_episode(
    scen: V9ScenarioSpec,
    ep_seed: int,
    policy_id: str,
    controller: Any,
    *,
    rng_env: np.random.Generator | None = None,
    rng_sensors: np.random.Generator | None = None,
) -> dict[str, Any]:
    """
    Executes one closed-loop episode with zero ground-truth leakage and fail-unsafe
    exception accounting (`crashed = 1 -> false_success = 1`).
    Guarantees mathematical decoupling between physical environment and sensor noise.
    """
    if rng_env is None or rng_sensors is None:
        rng_env, rng_sensors = create_decoupled_rng_pair(ep_seed)

    world = AegisPhysicalWorld()
    world.reset(rng_env)

    sensor_a = FaultInjectableSensor(scen.sensor_a)
    sensor_b = FaultInjectableSensor(scen.sensor_b)
    range_sensor = RangeSensor(
        noise_sigma=scen.range_sensor_noise,
        dropout_probability=scen.range_dropout_prob,
    )
    anchor_sensor = AnchorSensor(
        AnchorSensorConfig(
            query_cost=0.05,
            noise_sigma=0.04,
            is_corrupted=scen.anchor_corrupted,
            corrupted_bias=(1.2, -1.0),
        )
    )

    if hasattr(controller, "reset"):
        controller.reset()

    decisions: dict[str, int] = {}
    query_anchor = False
    min_dist_reached = float("inf")
    max_overshoot = 0.0
    dist_traveled = 0.0
    prev_pos = world.state()["robot_pos"].copy()

    crashed = False
    crash_error = ""
    step_wall_ns_total = 0
    step_calls = 0

    try:
        for _ in range(world.config.max_steps):
            st = world.state()
            true_delta = st["target_pos"] - st["robot_pos"]

            read_a = sensor_a.measure(true_delta, rng_sensors, step=st["step"])
            read_b = sensor_b.measure(true_delta, rng_sensors, step=st["step"])
            true_range_val = float(st["distance"]) + scen.range_sensor_bias
            read_r = range_sensor.measure(true_range_val, rng_sensors)
            read_anchor = anchor_sensor.measure(true_delta, rng_sensors, query=query_anchor)

            t0 = time.perf_counter_ns()
            action, dec_type, _cal_vec, query_anchor = controller.update(
                read_a,
                read_b,
                read_r,
                read_anchor,
                step=st["step"],
            )
            step_wall_ns_total += time.perf_counter_ns() - t0
            step_calls += 1

            decisions[dec_type] = decisions.get(dec_type, 0) + 1
            if dec_type in ("STOP", "ABSTAIN"):
                break

            w_st = world.step(action, rng_env)
            curr_pos = w_st["robot_pos"].copy()
            dist_traveled += float(np.linalg.norm(curr_pos - prev_pos))
            prev_pos = curr_pos

            cur_dist = float(w_st["distance"])
            if cur_dist < min_dist_reached:
                min_dist_reached = cur_dist
            elif min_dist_reached <= 0.50:
                overshoot = cur_dist - min_dist_reached
                max_overshoot = max(max_overshoot, overshoot)

            if w_st["truncated"]:
                break
    except Exception as exc:  # Fail-unsafe crash accounting per Protocol Section 3.1.3
        crashed = True
        crash_error = f"{type(exc).__name__}: {exc}"

    final_st = world.state()
    final_dist = float(final_st["distance"])
    steps_taken = int(final_st["step"])
    max_steps = int(world.config.max_steps)
    world.close()

    if crashed:
        accepted = 0
        true_success = 0
        false_success = 1
        abstain_explicit = 0
        timeout = 0
        abstain = 0
    else:
        stopped = decisions.get("STOP", 0) > 0
        abstained_exp = decisions.get("ABSTAIN", 0) > 0
        accepted = int(stopped)
        true_success = int(stopped and final_dist <= 0.45)
        false_success = int(stopped and final_dist > 0.45)
        abstain_explicit = int(abstained_exp)
        timeout = int((not stopped) and (not abstained_exp) and (steps_taken == max_steps))
        abstain = int(1 - accepted)

    mean_step_ms = (step_wall_ns_total / 1e6 / step_calls) if step_calls > 0 else 0.0
    terminal_reason = getattr(controller, "terminal_reason", "")

    return {
        "scenario": scen.name,
        "suite": scen.suite,
        "policy": policy_id,
        "seed": ep_seed,
        "accepted": accepted,
        "true_success": true_success,
        "false_success": false_success,
        "abstain_explicit": abstain_explicit,
        "timeout": timeout,
        "abstain": abstain,
        "crashed": int(crashed),
        "crash_error": crash_error,
        "final_distance": round(final_dist, 4),
        "steps": steps_taken,
        "mean_step_ms": round(mean_step_ms, 4),
        "distance_traveled": round(dist_traveled, 4),
        "anchor_queries": anchor_sensor.total_queries,
        "anchor_cost": round(anchor_sensor.total_cost, 4),
        "max_overshoot": round(max_overshoot, 4),
        "terminal_reason": terminal_reason,
    }


def _format_float_or_undef(val: float) -> str:
    if math.isnan(val):
        return "UNDEFINED"
    return f"{val:.6f}"


def evaluate_dev_grid(
    *,
    out_dir: str | Path = "results/v9/dev",
    seeds: Sequence[int] = tuple(range(DEV_SEED_START, DEV_SEED_STOP_EXCLUSIVE)),
    include_reference_baselines: bool = True,
    write_frozen_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Runs the complete D_dev stratified evaluation (12 scenarios x 30 seeds = 360 episodes/policy),
    verifies complete-run integrity and candidate ordering invariants, and writes artifacts
    exclusively under `results/v9/dev/`.
    """
    checked_seeds = enforce_dev_only_seeds(seeds)
    res_dir = enforce_dev_output_directory(out_dir)
    res_dir.mkdir(parents=True, exist_ok=True)

    scenarios = build_v9_s12_scenarios()
    manifest_pairs = [(scen, seed) for scen in scenarios for seed in checked_seeds]
    manifest_digest = hashlib.sha256(
        json.dumps([(sc.name, sd) for sc, sd in manifest_pairs], separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    candidates = PREREGISTERED_CANDIDATE_FAMILY
    policy_specs: list[tuple[str, Any]] = [
        (cand.candidate_id, lambda c=cand: AegisV9Controller(c)) for cand in candidates
    ]
    if include_reference_baselines:
        policy_specs.extend(
            [
                ("AEGIS_NEXT_MARTINGALE", lambda: AegisNextController()),
                ("AEGIS_V7_MPC_BASELINE", lambda: AegisV7MPCBaselineController()),
            ]
        )

    expected_total_records = len(manifest_pairs) * len(policy_specs)
    episode_records: list[dict[str, Any]] = []
    t_start = time.time()

    invalid_marker = res_dir / "INCOMPLETE_INVALID.json"
    if invalid_marker.exists():
        invalid_marker.unlink()

    try:
        for scen in scenarios:
            for ep_seed in checked_seeds:
                for pol_id, factory in policy_specs:
                    ctrl = factory()
                    rec = run_single_episode(scen, ep_seed, pol_id, ctrl)
                    episode_records.append(rec)
    except BaseException as exc:
        invalid_marker.write_text(
            json.dumps(
                {
                    "status": "INCOMPLETE_INVALID",
                    "recorded_episodes": len(episode_records),
                    "expected_episodes": expected_total_records,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise

    if len(episode_records) != expected_total_records:
        invalid_marker.write_text(
            json.dumps(
                {
                    "status": "INCOMPLETE_INVALID",
                    "recorded_episodes": len(episode_records),
                    "expected_episodes": expected_total_records,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise RuntimeError(
            f"Incomplete D_dev run: recorded {len(episode_records)} != expected {expected_total_records}."
        )

    elapsed_sec = time.time() - t_start

    # 1. Write raw episode-level CSV
    episodes_csv = res_dir / "dev_episodes.csv"
    ep_fields = list(episode_records[0].keys())
    with episodes_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ep_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(episode_records)

    # 2. Compute policy-level and per-scenario summaries
    policy_summaries: dict[str, PolicyEvaluationSummary] = {}
    scenario_summaries: list[dict[str, Any]] = []
    policy_step_ms: dict[str, float] = {}

    for pol_id, _ in policy_specs:
        pol_eps = [r for r in episode_records if r["policy"] == pol_id]
        if len(pol_eps) != len(manifest_pairs):
            raise RuntimeError(f"Policy {pol_id} missing episodes ({len(pol_eps)} != {len(manifest_pairs)}).")
        policy_summaries[pol_id] = compute_policy_summary(pol_id, pol_eps)
        policy_step_ms[pol_id] = float(
            sum(float(r["mean_step_ms"]) for r in pol_eps) / len(pol_eps)
        )

        for scen in scenarios:
            s_eps = [r for r in pol_eps if r["scenario"] == scen.name]
            s_sum = compute_policy_summary(pol_id, s_eps)
            scenario_summaries.append(
                {
                    "policy": pol_id,
                    "scenario": scen.name,
                    "suite": scen.suite,
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
                    "r_inc_ucb95": f"{s_sum.r_inc_ucb95:.6f}",
                    "r_sel_status": s_sum.r_sel_status,
                    "r_sel": _format_float_or_undef(s_sum.r_sel),
                    "r_sel_ucb95": _format_float_or_undef(s_sum.r_sel_ucb95),
                    "mean_steps": f"{s_sum.mean_steps:.2f}",
                    "mean_anchor_cost": f"{s_sum.mean_anchor_cost:.4f}",
                    "mean_max_overshoot": f"{s_sum.mean_max_overshoot:.4f}",
                }
            )

    policy_csv = res_dir / "dev_policy_summary.csv"
    pol_rows: list[dict[str, Any]] = []
    for pol_id, _ in policy_specs:
        s = policy_summaries[pol_id]
        pol_rows.append(
            {
                "policy": s.policy_id,
                "n_episodes": s.n_episodes,
                "m_accepted": s.m_accepted,
                "ts_count": s.ts_count,
                "fs_count": s.fs_count,
                "ab_explicit_count": s.ab_explicit_count,
                "timeout_count": s.timeout_count,
                "ab_total_count": s.ab_total_count,
                "crashed_count": s.crashed_count,
                "coverage": f"{s.coverage:.6f}",
                "tsr": f"{s.tsr:.6f}",
                "r_inc": f"{s.r_inc:.6f}",
                "r_inc_ucb95_descriptive": f"{s.r_inc_ucb95:.6f}",
                "r_sel_status": s.r_sel_status,
                "r_sel": _format_float_or_undef(s.r_sel),
                "r_sel_ucb95_descriptive": _format_float_or_undef(s.r_sel_ucb95),
                "mean_steps": f"{s.mean_steps:.2f}",
                "mean_step_ms": f"{policy_step_ms[pol_id]:.4f}",
                "mean_distance_traveled": f"{s.mean_distance_traveled:.4f}",
                "mean_anchor_queries": f"{s.mean_anchor_queries:.3f}",
                "mean_anchor_cost": f"{s.mean_anchor_cost:.4f}",
                "mean_max_overshoot": f"{s.mean_max_overshoot:.4f}",
            }
        )
    with policy_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(pol_rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(pol_rows)

    scen_csv = res_dir / "dev_scenario_summary.csv"
    with scen_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(scenario_summaries[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(scenario_summaries)

    # 3. Verify preregistered 6-candidate ordering and utility pre-checks on D_dev
    cands_with_dev: list[tuple[V9CandidateParams, PolicyEvaluationSummary, float]] = []
    for cand in candidates:
        nom_eps = [
            r
            for r in episode_records
            if r["policy"] == cand.candidate_id and r["scenario"] == "NOMINAL"
        ]
        nom_tsr = sum(int(r["true_success"]) for r in nom_eps) / len(nom_eps)
        cands_with_dev.append((cand, policy_summaries[cand.candidate_id], nom_tsr))

    ordering_report = verify_preregistered_dev_ordering(cands_with_dev)
    dev_manifest_meta = {
        "partition": "D_dev",
        "sampling_law": "stratified_deterministic_grid",
        "scenarios": [sc.name for sc in scenarios],
        "num_scenarios": len(scenarios),
        "seed_start": checked_seeds[0],
        "seed_end_inclusive": checked_seeds[-1],
        "seeds_per_scenario": len(checked_seeds),
        "episodes_per_policy": len(manifest_pairs),
        "manifest_sha256": manifest_digest,
    }

    eval_cmd = (
        "PYTHONPATH=src uv run python experiments/v9_evaluate_dev.py "
        "--write-frozen-config configs/v9_candidates_frozen.json"
    )
    created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    report_payload: dict[str, Any] = {
        "status": "COMPLETE_VALID",
        "protocol_version": PROTOCOL_VERSION,
        "source_design_commit": SOURCE_DESIGN_COMMIT,
        "v81_baseline_commit": V81_BASELINE_COMMIT,
        "created_utc": created_utc,
        "elapsed_seconds": round(elapsed_sec, 3),
        "statistical_scope_note": (
            "D_dev is a fixed-quota stratified development grid (12 x 30 = 360 episodes/policy) "
            "used solely for pre-calibration ordering verification. Pooled CIs/UCBs on D_dev are "
            "descriptive diagnostics only and DO NOT certify the 5% selective-risk target."
        ),
        "dev_manifest": dev_manifest_meta,
        "ordering_verification": ordering_report,
        "candidates": [asdict(c) for c in candidates],
        "policy_summaries": pol_rows,
    }

    frozen_info: dict[str, Any] | None = None
    if write_frozen_config_path is not None:
        if not ordering_report["tier1_precheck_passed"] or not ordering_report["all_candidates_admissible"]:
            raise RuntimeError(
                "Refusing to freeze configs/v9_candidates_frozen.json: D_dev ordering/admissibility "
                f"pre-check failed ({ordering_report})."
            )
        frozen_path, frozen_sha = write_frozen_candidates_json(
            write_frozen_config_path,
            protocol_version=PROTOCOL_VERSION,
            source_design_commit=SOURCE_DESIGN_COMMIT,
            v81_baseline_commit=V81_BASELINE_COMMIT,
            ordered_candidates=candidates,
            dev_manifest_metadata=dev_manifest_meta,
            dev_ordering_report=ordering_report,
            evaluation_command=eval_cmd,
            created_utc=created_utc,
        )
        frozen_info = {
            "path": str(frozen_path),
            "integrity_sha256": frozen_sha,
        }
        report_payload["frozen_candidates_config"] = frozen_info

    report_json = res_dir / "dev_ordering_report.json"
    report_json.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")
    return report_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate V9 candidate family ONLY on D_dev (seeds 70000..70029)."
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="results/v9/dev",
        help="Isolated D_dev output directory (must end with results/v9/dev).",
    )
    parser.add_argument(
        "--write-frozen-config",
        type=str,
        default=None,
        help="Optional path (e.g., configs/v9_candidates_frozen.json) to write after verification.",
    )
    args = parser.parse_args()

    report = evaluate_dev_grid(
        out_dir=args.out_dir,
        write_frozen_config_path=args.write_frozen_config,
    )

    print("=" * 92)
    print("NEXVIA AEGIS V9-M1 — D_dev (SEEDS 70000..70029, N=360/POLICY) EVALUATION SUMMARY")
    print("=" * 92)
    header = (
        f"{'Policy':<34} {'Acc(M)':>6} {'Cov':>7} {'TS':>5} {'TSR':>7} "
        f"{'FS(K)':>5} {'R_sel':>8} {'R_inc':>7} {'AB_exp':>6} {'TO':>4} {'Anc$':>7}"
    )
    print(header)
    print("-" * 92)
    for row in report["policy_summaries"]:
        r_sel_disp = (
            "UNDEF"
            if row["r_sel"] == "UNDEFINED"
            else f"{100.0 * float(row['r_sel']):6.2f}%"
        )
        print(
            f"{row['policy']:<34} {row['m_accepted']:>6} "
            f"{100.0 * float(row['coverage']):6.2f}% {row['ts_count']:>5} "
            f"{100.0 * float(row['tsr']):6.2f}% {row['fs_count']:>5} "
            f"{r_sel_disp:>8} {100.0 * float(row['r_inc']):6.2f}% "
            f"{row['ab_explicit_count']:>6} {row['timeout_count']:>4} "
            f"{float(row['mean_anchor_cost']):>7.4f}"
        )
    print("-" * 92)
    ov = report["ordering_verification"]
    print(
        f"Tier-1 Precheck Passed: {ov['tier1_precheck_passed']} "
        f"(Tier-1 Coverage={100.0 * ov['tier1_coverage']:.2f}% >= 42.0%) | "
        f"All 6 Candidates Admissible: {ov['all_candidates_admissible']}"
    )
    if "frozen_candidates_config" in report:
        fc = report["frozen_candidates_config"]
        print(f"Frozen Config Written: {fc['path']} (SHA-256: {fc['integrity_sha256']})")


if __name__ == "__main__":
    main()
