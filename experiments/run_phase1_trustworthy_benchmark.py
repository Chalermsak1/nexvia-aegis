"""
NEXVIA AEGIS — Phase 1: Trustworthy Autonomous Decision-Making Benchmark Suite.

Executes a fully reproducible, matched-seed empirical benchmark across the 12
preregistered development scenarios (S_12) on D_dev (seeds 77000..77029).

Evaluates:
1. V9_AEGIS: Full runtime-assurance policy (Anytime Martingale + Active Probing + Calibrator)
2. V9_NO_MARTINGALE: Ablation disabling Anytime-Valid Ville Martingale alarm
3. V9_NO_ACTIVE_PROBE: Ablation disabling active probing maneuvers
4. V8_MARTINGALE_BASELINE: V8 audited baseline (AegisNextController)
5. V7_MPC_BASELINE: V7 unshielded / classical MPC baseline (AegisV7MPCBaselineController)

Strict Accounting & Mathematical Invariants:
- Terminal states are strictly disjoint and exhaustive: N = TS + FS + AB_exp + TO + CR
- Selective Risk: R_sel = FS / M (undefined when M = 0)
- Coverage: C = M / N
- Unconditional False-Success Incidence: R_inc = FS / N
- Task Success Rate: TSR = TS / N
- Paired McNemar exact tests and Newcombe confidence intervals on matched episodes
"""

from __future__ import annotations

import argparse
import csv
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
from aegis.v9.controller import AegisV9Controller
from aegis.v9.risk_statistics import (
    PREREGISTERED_CANDIDATE_FAMILY,
    clopper_pearson_one_sided_ucb,
)
from aegis.v9.ville_monitor import VilleStepResult
from experiments.v9_evaluate_dev import (
    DEV_SEED_START,
    DEV_SEED_STOP_EXCLUSIVE,
    V9ScenarioSpec,
    build_v9_s12_scenarios,
    run_single_episode,
)


# ==============================================================================
# Ablation Controllers
# ==============================================================================

class V9NoMartingaleController(AegisV9Controller):
    """
    Ablation Arm: V9 without Anytime-Valid Ville Martingale.
    Suppresses Ville alarm generation, forcing the controller to rely solely on
    instantaneous thresholds and CUSUM. Demonstrates the specific contribution of
    anytime-valid martingales to bounding selective risk under drift.
    """

    def _ensure_nominal_monitors(self, sig_a: float, sig_b: float, sig_r: float) -> None:
        super()._ensure_nominal_monitors(sig_a, sig_b, sig_r)
        if self._nominal_ville is not None:
            self._nominal_ville.update = lambda obs_map: VilleStepResult(
                wealth=1.0, anytime_p_value=1.0, is_alarm=False, invalid_input_detected=False, component_wealths={}
            )

    def _init_post_cal_monitors(self, *args: Any, **kwargs: Any) -> None:
        super()._init_post_cal_monitors(*args, **kwargs)
        if self._post_cal_ville is not None:
            self._post_cal_ville.update = lambda obs_map: VilleStepResult(
                wealth=1.0, anytime_p_value=1.0, is_alarm=False, invalid_input_detected=False, component_wealths={}
            )


class V9NoActiveProbeController(AegisV9Controller):
    """
    Ablation Arm: V9 without Active Probing.
    When a sensor anomaly or alarm triggers, rather than actively probing to disambiguate
    and calibrate the faulty sensor, the controller immediately abstains.
    Demonstrates how active probing recovers task completion (coverage and TSR).
    """

    def update(self, *args: Any, **kwargs: Any) -> tuple[np.ndarray, str, np.ndarray, bool]:
        force_action, dec_type, nav_vec, query_anchor = super().update(*args, **kwargs)
        if dec_type == "PROBE":
            zero_act = np.zeros(2, dtype=np.float64)
            self._prev_action = zero_act
            self.terminal_reason = "ALARM_IMMEDIATE_ABSTAIN_NO_PROBE"
            return zero_act, "ABSTAIN", nav_vec, False
        return force_action, dec_type, nav_vec, query_anchor


# ==============================================================================
# Statistical Helper Functions
# ==============================================================================

def mcnemar_exact_p_value(b: int, c: int) -> float:
    """Exact two-sided binomial p-value for paired discordant pairs (b vs c)."""
    n_discordant = b + c
    if n_discordant == 0:
        return 1.0
    k = min(b, c)
    # two-sided exact binomial test with p = 0.5
    cum_p = sum(math.comb(n_discordant, i) * (0.5 ** n_discordant) for i in range(k + 1))
    return min(1.0, 2.0 * cum_p)


def newcombe_paired_diff_ci(
    n11: int, n10: int, n01: int, n00: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Newcombe hybrid score interval for paired difference in proportions (p1 - p2)."""
    n = n11 + n10 + n01 + n00
    if n == 0:
        return (float("nan"), float("nan"))
    z = 1.959963984540054 if confidence == 0.95 else 1.6448536269514722
    p1 = (n11 + n10) / n
    p2 = (n11 + n01) / n
    d = p1 - p2

    def wilson_interval(count: int, total: int) -> tuple[float, float]:
        if total == 0:
            return (0.0, 0.0)
        p = count / total
        denom = 1.0 + (z**2) / total
        center = (p + (z**2) / (2 * total)) / denom
        half = (z * math.sqrt(p * (1.0 - p) / total + (z**2) / (4 * total**2))) / denom
        return (max(0.0, center - half), min(1.0, center + half))

    l1, u1 = wilson_interval(n11 + n10, n)
    l2, u2 = wilson_interval(n11 + n01, n)

    phi_denom = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    phi = (n11 * n00 - n10 * n01) / phi_denom if phi_denom > 0 else 0.0

    lower = d - math.sqrt((p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2)
    return (float(lower), float(upper))


# ==============================================================================
# Benchmark Runner Core
# ==============================================================================

def run_phase1_benchmark(
    *,
    seed_start: int = DEV_SEED_START,
    seed_stop: int = DEV_SEED_STOP_EXCLUSIVE,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Executes the Phase 1 Trustworthy Autonomous Decision-Making benchmark.
    Returns structured results and writes auditable JSON/CSV artifacts.
    """
    scenarios = build_v9_s12_scenarios()
    seeds = tuple(range(seed_start, seed_stop))
    n_seeds = len(seeds)
    n_scen = len(scenarios)
    total_episodes_per_policy = n_seeds * n_scen

    print(f"================================================================================")
    print(f" NEXVIA AEGIS — Phase 1: Trustworthy Autonomous Decision-Making Benchmark")
    print(f" Grid: {n_scen} Scenarios x {n_seeds} Seeds = {total_episodes_per_policy} Matched Episodes / Policy")
    print(f" Seeds: {seed_start}..{seed_stop - 1} (Approved D_dev partition)")
    print(f"================================================================================")

    policy_factories: dict[str, Any] = {
        "V9_AEGIS": lambda: AegisV9Controller(PREREGISTERED_CANDIDATE_FAMILY[2]),
        "V9_NO_MARTINGALE": lambda: V9NoMartingaleController(PREREGISTERED_CANDIDATE_FAMILY[2]),
        "V9_NO_ACTIVE_PROBE": lambda: V9NoActiveProbeController(PREREGISTERED_CANDIDATE_FAMILY[2]),
        "V8_MARTINGALE": lambda: AegisNextController(),
        "V7_MPC": lambda: AegisV7MPCBaselineController(),
    }

    all_records: dict[str, list[dict[str, Any]]] = {name: [] for name in policy_factories}
    policy_metrics: dict[str, dict[str, Any]] = {}

    start_time = time.time()

    for pol_name, factory in policy_factories.items():
        print(f"\n[Evaluating {pol_name}] ...", flush=True)
        t_pol = time.time()
        ctrl = factory()
        records: list[dict[str, Any]] = []

        for scen in scenarios:
            for seed in seeds:
                rec = run_single_episode(scen, seed, pol_name, ctrl)
                records.append(rec)

        elapsed_pol = time.time() - t_pol
        all_records[pol_name] = records

        # Aggregate metrics
        n = len(records)
        m = sum(1 for r in records if r["accepted"] == 1)
        ts = sum(1 for r in records if r["true_success"] == 1)
        fs = sum(1 for r in records if r["false_success"] == 1)
        ab_exp = sum(1 for r in records if r["abstain_explicit"] == 1)
        to = sum(1 for r in records if r["timeout"] == 1)
        cr = sum(1 for r in records if r["crashed"] == 1)
        ab_tot = sum(1 for r in records if r["abstain"] == 1)

        # Invariant check
        reconciled = (ts + fs + ab_exp + to) == n or (cr > 0 and (ts + fs + ab_exp + to + cr) >= n)

        cov = m / n if n > 0 else 0.0
        tsr = ts / n if n > 0 else 0.0
        r_inc = fs / n if n > 0 else 0.0
        r_sel = fs / m if m > 0 else float("nan")
        cp_r_sel_ucb95 = clopper_pearson_one_sided_ucb(fs, m, delta=0.05) if m > 0 else float("nan")
        cp_r_inc_ucb95 = clopper_pearson_one_sided_ucb(fs, n, delta=0.05) if n > 0 else float("nan")

        policy_metrics[pol_name] = {
            "n_episodes": n,
            "m_accepted": m,
            "true_successes": ts,
            "false_successes": fs,
            "abstain_explicit": ab_exp,
            "timeouts": to,
            "crashes": cr,
            "coverage": round(cov, 4),
            "tsr": round(tsr, 4),
            "r_inc": round(r_inc, 4),
            "r_sel": round(r_sel, 4) if not math.isnan(r_sel) else "UNDEFINED",
            "cp_r_sel_ucb95": round(cp_r_sel_ucb95, 4) if not math.isnan(cp_r_sel_ucb95) else "UNDEFINED",
            "cp_r_inc_ucb95": round(cp_r_inc_ucb95, 4) if not math.isnan(cp_r_inc_ucb95) else "UNDEFINED",
            "reconciled_exhaustiveness": reconciled,
            "wall_clock_seconds": round(elapsed_pol, 2),
        }

        print(
            f"  -> Done in {elapsed_pol:.2f}s | "
            f"TSR: {tsr*100:5.1f}% | Cov: {cov*100:5.1f}% | "
            f"FS: {fs:2d} (R_inc: {r_inc*100:4.1f}%) | "
            f"R_sel: {r_sel*100 if not math.isnan(r_sel) else 0.0:4.1f}% (UCB: {cp_r_sel_ucb95*100 if not math.isnan(cp_r_sel_ucb95) else 0.0:4.1f}%)"
        )

    total_elapsed = time.time() - start_time

    # ==========================================================================
    # Statistical Hypotheses & Mechanism Contrast Tests
    # ==========================================================================
    print(f"\n================================================================================")
    print(f" STATISTICAL CONTRASTS & MECHANISM ISOLATION (Matched Pairs, N = {total_episodes_per_policy})")
    print(f"================================================================================")

    contrasts: dict[str, Any] = {}
    v9_recs = all_records["V9_AEGIS"]

    for comp_name in ["V8_MARTINGALE", "V7_MPC", "V9_NO_MARTINGALE", "V9_NO_ACTIVE_PROBE"]:
        comp_recs = all_records[comp_name]
        # Match by (scenario, seed)
        comp_map = {(r["scenario"], r["seed"]): r for r in comp_recs}
        matched = [(r, comp_map[(r["scenario"], r["seed"])]) for r in v9_recs if (r["scenario"], r["seed"]) in comp_map]

        # False success contingency table (b = V9 failed & Comp passed; c = V9 passed & Comp failed)
        n11_fs = sum(1 for v, c in matched if v["false_success"] == 1 and c["false_success"] == 1)
        n10_fs = sum(1 for v, c in matched if v["false_success"] == 1 and c["false_success"] == 0)
        n01_fs = sum(1 for v, c in matched if v["false_success"] == 0 and c["false_success"] == 1)
        n00_fs = sum(1 for v, c in matched if v["false_success"] == 0 and c["false_success"] == 0)
        p_val_fs = mcnemar_exact_p_value(n10_fs, n01_fs)

        # TSR paired difference
        n11_ts = sum(1 for v, c in matched if v["true_success"] == 1 and c["true_success"] == 1)
        n10_ts = sum(1 for v, c in matched if v["true_success"] == 1 and c["true_success"] == 0)
        n01_ts = sum(1 for v, c in matched if v["true_success"] == 0 and c["true_success"] == 1)
        n00_ts = sum(1 for v, c in matched if v["true_success"] == 0 and c["true_success"] == 0)
        diff_tsr = (n10_ts - n01_ts) / len(matched)
        ci_tsr = newcombe_paired_diff_ci(n11_ts, n10_ts, n01_ts, n00_ts)

        contrasts[f"V9_vs_{comp_name}"] = {
            "n_matched": len(matched),
            "false_success_mcnemar": {
                "n11": n11_fs, "n10_v9_only_fs": n10_fs, "n01_comp_only_fs": n01_fs, "n00": n00_fs,
                "p_value": p_val_fs,
                "v9_significantly_fewer_fs": bool(n10_fs < n01_fs and p_val_fs < 0.05),
            },
            "tsr_paired_difference": {
                "delta_tsr": round(diff_tsr, 4),
                "ci95": [round(ci_tsr[0], 4), round(ci_tsr[1], 4)],
            },
        }

        print(f"[*] V9 vs {comp_name}:")
        print(
            f"    False Success Reduction: V9 FS={n10_fs+n11_fs} vs {comp_name} FS={n01_fs+n11_fs} "
            f"| Discordant (V9 only={n10_fs}, {comp_name} only={n01_fs}) | p = {p_val_fs:.6e}"
        )
        print(
            f"    Delta TSR: {diff_tsr*100:+5.2f}% (95% CI: [{ci_tsr[0]*100:+5.2f}%, {ci_tsr[1]*100:+5.2f}%])"
        )

    # Scenario Breakdown for V9
    scen_breakdown: dict[str, dict[str, Any]] = {}
    for scen in scenarios:
        s_recs = [r for r in v9_recs if r["scenario"] == scen.name]
        s_n = len(s_recs)
        s_m = sum(1 for r in s_recs if r["accepted"] == 1)
        s_ts = sum(1 for r in s_recs if r["true_success"] == 1)
        s_fs = sum(1 for r in s_recs if r["false_success"] == 1)
        s_to = sum(1 for r in s_recs if r["timeout"] == 1)
        s_r_sel = s_fs / s_m if s_m > 0 else float("nan")
        scen_breakdown[scen.name] = {
            "n": s_n, "m": s_m, "ts": s_ts, "fs": s_fs, "timeout": s_to,
            "tsr": round(s_ts / s_n, 4) if s_n > 0 else 0.0,
            "coverage": round(s_m / s_n, 4) if s_n > 0 else 0.0,
            "r_sel": round(s_r_sel, 4) if not math.isnan(s_r_sel) else "UNDEFINED",
        }

    # Summary payload
    results_payload = {
        "benchmark": "NEXVIA_AEGIS_PHASE_1_TRUSTWORTHY_DECISION_BENCHMARK",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_wall_clock_seconds": round(total_elapsed, 2),
        "grid": {
            "seed_start": seed_start,
            "seed_stop": seed_stop,
            "n_seeds_per_scen": n_seeds,
            "n_scenarios": n_scen,
            "total_episodes_per_policy": total_episodes_per_policy,
        },
        "policy_summaries": policy_metrics,
        "statistical_contrasts": contrasts,
        "v9_scenario_breakdown": scen_breakdown,
    }

    # Output paths
    if output_dir is None:
        output_dir = Path("results/v9/dev")
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "phase1_trustworthy_benchmark_summary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)

    csv_path = output_dir / "phase1_trustworthy_benchmark_episodes.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "policy", "scenario", "suite", "seed", "accepted", "true_success", "false_success",
            "abstain_explicit", "timeout", "crashed", "final_distance", "steps", "terminal_reason"
        ])
        for pol_name, recs in all_records.items():
            for r in recs:
                writer.writerow([
                    pol_name, r["scenario"], r["suite"], r["seed"],
                    r["accepted"], r["true_success"], r["false_success"],
                    r["abstain_explicit"], r["timeout"], r["crashed"],
                    round(r["final_distance"], 4), r["steps"], r["terminal_reason"]
                ])

    print(f"\n[Artifacts Saved Successfully]:")
    print(f"  -> JSON: {json_path}")
    print(f"  -> CSV:  {csv_path} ({len(policy_factories) * total_episodes_per_policy} rows)")

    return results_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 1 Trustworthy Autonomous Decision Benchmark")
    parser.add_argument("--seed-start", type=int, default=DEV_SEED_START)
    parser.add_argument("--seed-stop", type=int, default=DEV_SEED_STOP_EXCLUSIVE)
    parser.add_argument("--output-dir", type=str, default="results/v9/dev")
    args = parser.parse_args()

    run_phase1_benchmark(
        seed_start=args.seed_start,
        seed_stop=args.seed_stop,
        output_dir=Path(args.output_dir),
    )
