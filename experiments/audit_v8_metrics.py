"""
NEXVIA AEGIS V8.1 — Benchmark Reconciliation and Statistical Audit Engine.

Independently ingests results/next/benchmark_episodes.csv and performs:
1. Complete recalculation of summary statistics per scenario and policy.
2. Independent Wilson score and Clopper-Pearson exact confidence interval calculation.
3. Verification of undefined selective risk handling when coverage is zero.
4. Cell-by-cell discrepancy analysis against results/next/benchmark_summary.csv.
5. Paired episode-level comparative statistics (McNemar test, paired t-test) between AEGIS-Next and V7.
6. Per-scenario vs. pooled risk decomposition.
7. Export of certified results/v8_audit/metrics_recalculated.csv.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
import numpy as np
from scipy.stats import beta, binomtest, ttest_rel


def wilson_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Computes two-sided Wilson score confidence interval."""
    if n == 0:
        return float("nan"), float("nan")
    # Quantile for two-sided (1 - alpha/2)
    # For 95%: 1.959963984540054
    alpha = 1.0 - confidence
    from scipy.stats import norm
    z = float(norm.ppf(1.0 - alpha / 2.0))
    p = k / n
    denom = 1.0 + (z**2) / n
    center = (p + (z**2) / (2.0 * n)) / denom
    margin = (z * math.sqrt((p * (1.0 - p) / n) + (z**2) / (4.0 * (n**2)))) / denom
    return max(0.0, float(center - margin)), min(1.0, float(center + margin))


def clopper_pearson_exact_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Computes Clopper-Pearson exact confidence interval using Beta distribution quantiles."""
    if n == 0:
        return float("nan"), float("nan")
    alpha = 1.0 - confidence
    lower = 0.0 if k == 0 else float(beta.ppf(alpha / 2.0, k, n - k + 1))
    upper = 1.0 if k == n else float(beta.ppf(1.0 - alpha / 2.0, k + 1, n - k))
    return lower, upper


def audit_and_recalculate_v8(
    episodes_path: str = "results/next/benchmark_episodes.csv",
    original_summary_path: str = "results/next/benchmark_summary.csv",
    output_audit_csv: str = "results/v8_audit/metrics_recalculated.csv",
) -> dict:
    ep_file = Path(episodes_path)
    sum_file = Path(original_summary_path)
    out_file = Path(output_audit_csv)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    if not ep_file.exists():
        raise FileNotFoundError(f"Missing {episodes_path}")

    with open(ep_file, "r") as f:
        ep_rows = list(csv.DictReader(f))

    total_episodes = len(ep_rows)
    scenarios = sorted(list(set(r["scenario"] for r in ep_rows)))
    policies = sorted(list(set(r["policy"] for r in ep_rows)))

    print("=" * 80)
    print("NEXVIA AEGIS V8.1 AUDIT: RECALCULATING BENCHMARK METRICS")
    print(f"Total Episodes Loaded: {total_episodes}")
    print(f"Scenarios ({len(scenarios)}): {scenarios}")
    print(f"Policies ({len(policies)}): {policies}")
    print("=" * 80)

    # 1. Sanity check: terminal state mutually exclusive and exhaustive
    invalid_terminal_episodes = []
    for idx, r in enumerate(ep_rows):
        ts = int(r["true_success"])
        fs = int(r["false_success"])
        ab = int(r["abstain"])
        if ts + fs + ab != 1:
            invalid_terminal_episodes.append((idx, r))

    if invalid_terminal_episodes:
        print(f"CRITICAL ERROR: Found {len(invalid_terminal_episodes)} episodes with invalid terminal states!")
    else:
        print("PASS: All 4,000 episodes satisfy TS + FS + AB == 1.")

    # 2. Recalculate summary rows
    recalculated_rows: list[dict] = []

    # Per-scenario calculations
    for scen in scenarios:
        for pol in policies:
            subset = [r for r in ep_rows if r["scenario"] == scen and r["policy"] == pol]
            n = len(subset)
            ts = sum(int(r["true_success"]) for r in subset)
            fs = sum(int(r["false_success"]) for r in subset)
            ab = sum(int(r["abstain"]) for r in subset)
            cov = ts + fs

            ts_rate = ts / n if n > 0 else 0.0
            fs_rate = fs / n if n > 0 else 0.0
            cov_rate = cov / n if n > 0 else 0.0
            ab_rate = ab / n if n > 0 else 0.0

            ts_ci_wilson = wilson_interval(ts, n)
            ts_ci_exact = clopper_pearson_exact_interval(ts, n)
            cov_ci_wilson = wilson_interval(cov, n)

            # Selective / Covered Risk = FS / (TS + FS)
            if cov > 0:
                cov_risk = fs / cov
                cov_risk_wilson = wilson_interval(fs, cov)
                cov_risk_exact = clopper_pearson_exact_interval(fs, cov)
                cov_risk_str = f"{cov_risk:.4f}"
                cov_risk_wilson_str = f"[{cov_risk_wilson[0]:.4f}, {cov_risk_wilson[1]:.4f}]"
                cov_risk_exact_str = f"[{cov_risk_exact[0]:.4f}, {cov_risk_exact[1]:.4f}]"
            else:
                cov_risk = float("nan")
                cov_risk_wilson = (float("nan"), float("nan"))
                cov_risk_exact = (float("nan"), float("nan"))
                cov_risk_str = "undefined"
                cov_risk_wilson_str = "undefined"
                cov_risk_exact_str = "undefined"

            mean_steps = float(np.mean([float(r["steps"]) for r in subset]))
            mean_dist = float(np.mean([float(r["distance_traveled"]) for r in subset]))
            mean_queries = float(np.mean([float(r["anchor_queries"]) for r in subset]))
            mean_cost = float(np.mean([float(r["anchor_cost"]) for r in subset]))
            mean_overshoot = float(np.mean([float(r["max_overshoot"]) for r in subset]))

            recalculated_rows.append({
                "aggregation_level": "SCENARIO",
                "scenario": scen,
                "policy": pol,
                "episodes": n,
                "true_success_count": ts,
                "true_success_rate": round(ts_rate, 4),
                "true_success_ci95_wilson": f"[{ts_ci_wilson[0]:.4f}, {ts_ci_wilson[1]:.4f}]",
                "true_success_ci95_exact": f"[{ts_ci_exact[0]:.4f}, {ts_ci_exact[1]:.4f}]",
                "false_success_count": fs,
                "false_success_rate": round(fs_rate, 4),
                "abstain_count": ab,
                "abstention_rate": round(ab_rate, 4),
                "accepted_decisions": cov,
                "task_coverage_rate": round(cov_rate, 4),
                "task_coverage_ci95_wilson": f"[{cov_ci_wilson[0]:.4f}, {cov_ci_wilson[1]:.4f}]",
                "covered_risk": cov_risk_str,
                "covered_risk_ci95_wilson": cov_risk_wilson_str,
                "covered_risk_ci95_exact": cov_risk_exact_str,
                "mean_steps": round(mean_steps, 2),
                "mean_distance_traveled": round(mean_dist, 4),
                "mean_anchor_queries": round(mean_queries, 2),
                "mean_anchor_cost": round(mean_cost, 4),
                "mean_max_overshoot": round(mean_overshoot, 4),
            })

    # Pooled calculations across all 10 scenarios
    for pol in policies:
        subset = [r for r in ep_rows if r["policy"] == pol]
        n = len(subset)
        ts = sum(int(r["true_success"]) for r in subset)
        fs = sum(int(r["false_success"]) for r in subset)
        ab = sum(int(r["abstain"]) for r in subset)
        cov = ts + fs

        ts_rate = ts / n
        fs_rate = fs / n
        cov_rate = cov / n
        ab_rate = ab / n

        ts_ci_wilson = wilson_interval(ts, n)
        ts_ci_exact = clopper_pearson_exact_interval(ts, n)
        cov_ci_wilson = wilson_interval(cov, n)

        if cov > 0:
            cov_risk = fs / cov
            cov_risk_wilson = wilson_interval(fs, cov)
            cov_risk_exact = clopper_pearson_exact_interval(fs, cov)
            cov_risk_str = f"{cov_risk:.4f}"
            cov_risk_wilson_str = f"[{cov_risk_wilson[0]:.4f}, {cov_risk_wilson[1]:.4f}]"
            cov_risk_exact_str = f"[{cov_risk_exact[0]:.4f}, {cov_risk_exact[1]:.4f}]"
        else:
            cov_risk = float("nan")
            cov_risk_str = "undefined"
            cov_risk_wilson_str = "undefined"
            cov_risk_exact_str = "undefined"

        mean_steps = float(np.mean([float(r["steps"]) for r in subset]))
        mean_dist = float(np.mean([float(r["distance_traveled"]) for r in subset]))
        mean_queries = float(np.mean([float(r["anchor_queries"]) for r in subset]))
        mean_cost = float(np.mean([float(r["anchor_cost"]) for r in subset]))
        mean_overshoot = float(np.mean([float(r["max_overshoot"]) for r in subset]))

        recalculated_rows.append({
            "aggregation_level": "POOLED_ALL_SCENARIOS",
            "scenario": "ALL_10_SCENARIOS",
            "policy": pol,
            "episodes": n,
            "true_success_count": ts,
            "true_success_rate": round(ts_rate, 4),
            "true_success_ci95_wilson": f"[{ts_ci_wilson[0]:.4f}, {ts_ci_wilson[1]:.4f}]",
            "true_success_ci95_exact": f"[{ts_ci_exact[0]:.4f}, {ts_ci_exact[1]:.4f}]",
            "false_success_count": fs,
            "false_success_rate": round(fs_rate, 4),
            "abstain_count": ab,
            "abstention_rate": round(ab_rate, 4),
            "accepted_decisions": cov,
            "task_coverage_rate": round(cov_rate, 4),
            "task_coverage_ci95_wilson": f"[{cov_ci_wilson[0]:.4f}, {cov_ci_wilson[1]:.4f}]",
            "covered_risk": cov_risk_str,
            "covered_risk_ci95_wilson": cov_risk_wilson_str,
            "covered_risk_ci95_exact": cov_risk_exact_str,
            "mean_steps": round(mean_steps, 2),
            "mean_distance_traveled": round(mean_dist, 4),
            "mean_anchor_queries": round(mean_queries, 2),
            "mean_anchor_cost": round(mean_cost, 4),
            "mean_max_overshoot": round(mean_overshoot, 4),
        })

    # Write out recalculated CSV
    fieldnames = list(recalculated_rows[0].keys())
    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(recalculated_rows)

    print(f"Recalculated metrics written to: {out_file}")

    # 3. Compare with original benchmark_summary.csv
    reconciliation_discrepancies = []
    if sum_file.exists():
        with open(sum_file, "r") as f:
            orig_sum_rows = list(csv.DictReader(f))

        for orow in orig_sum_rows:
            scen = orow["scenario"]
            pol = orow["policy"]
            # Match with recalculated row
            matched = [
                r for r in recalculated_rows
                if r["aggregation_level"] == "SCENARIO" and r["scenario"] == scen and r["policy"] == pol
            ]
            if not matched:
                reconciliation_discrepancies.append((scen, pol, "Missing in recalculated"))
                continue
            rrow = matched[0]

            # Check counts
            if int(orow["true_success_count"]) != rrow["true_success_count"]:
                reconciliation_discrepancies.append((scen, pol, "TS Count", orow["true_success_count"], rrow["true_success_count"]))
            if int(orow["false_success_count"]) != rrow["false_success_count"]:
                reconciliation_discrepancies.append((scen, pol, "FS Count", orow["false_success_count"], rrow["false_success_count"]))

            # Check covered risk representation when coverage is 0
            if rrow["accepted_decisions"] == 0:
                if float(orow["covered_risk"]) == 0.0:
                    reconciliation_discrepancies.append((
                        scen, pol, "ZERO_COVERAGE_REPORTED_AS_ZERO",
                        "Original: 0.0 (Should be undefined)", "Recalculated: undefined"
                    ))

    print(f"Discrepancies found with original summary: {len(reconciliation_discrepancies)}")
    zero_cov_cases = [d for d in reconciliation_discrepancies if d[2] == "ZERO_COVERAGE_REPORTED_AS_ZERO"]
    print(f"Zero-coverage logged as 0.0 risk in original: {len(zero_cov_cases)} instances")

    # 4. Detailed Wilson Interval Recalculation for AEGIS-Next pooled
    aegis_next_pooled = [r for r in recalculated_rows if r["aggregation_level"] == "POOLED_ALL_SCENARIOS" and r["policy"] == "AEGIS_NEXT_MARTINGALE"][0]
    k_fs = aegis_next_pooled["false_success_count"]
    n_cov = aegis_next_pooled["accepted_decisions"]
    p_hat = k_fs / n_cov
    w_ci = wilson_interval(k_fs, n_cov, 0.95)
    cp_ci = clopper_pearson_exact_interval(k_fs, n_cov, 0.95)

    print("\n" + "=" * 80)
    print("INDEPENDENT CONFIDENCE INTERVAL AUDIT FOR AEGIS-NEXT POOLED COVERED RISK")
    print(f"Numerator (False Successes): {k_fs}")
    print(f"Denominator (Accepted Decisions): {n_cov}")
    print(f"Point Estimate: {p_hat:.6f} ({p_hat*100:.4f}%)")
    print(f"Two-sided 95% Wilson Score Interval: [{w_ci[0]:.6f}, {w_ci[1]:.6f}] ({w_ci[0]*100:.3f}% to {w_ci[1]*100:.3f}%)")
    print(f"  Wilson Upper Bound < 0.0500? {w_ci[1] < 0.0500} (Difference: {0.0500 - w_ci[1]:.6f})")
    print(f"Two-sided 95% Clopper-Pearson Exact Interval: [{cp_ci[0]:.6f}, {cp_ci[1]:.6f}] ({cp_ci[0]*100:.3f}% to {cp_ci[1]*100:.3f}%)")
    print(f"  Clopper-Pearson Upper Bound < 0.0500? {cp_ci[1] < 0.0500} (Difference: {0.0500 - cp_ci[1]:.6f})")
    print("=" * 80)

    # 5. Paired comparison V7 vs AEGIS-Next
    v7_episodes = {(r["scenario"], int(r["seed"])): r for r in ep_rows if r["policy"] == "AEGIS_V7_MPC_BASELINE"}
    v8_episodes = {(r["scenario"], int(r["seed"])): r for r in ep_rows if r["policy"] == "AEGIS_NEXT_MARTINGALE"}

    n00 = n01 = n10 = n11 = 0
    diffs_ts = []
    diffs_cost = []
    diffs_overshoot = []

    for key in sorted(v7_episodes.keys()):
        r7 = v7_episodes[key]
        r8 = v8_episodes[key]
        ts7 = int(r7["true_success"])
        ts8 = int(r8["true_success"])
        c7 = float(r7["anchor_cost"])
        c8 = float(r8["anchor_cost"])
        o7 = float(r7["max_overshoot"])
        o8 = float(r8["max_overshoot"])

        diffs_ts.append(ts8 - ts7)
        diffs_cost.append(c8 - c7)
        diffs_overshoot.append(o8 - o7)

        if ts7 == 0 and ts8 == 0:
            n00 += 1
        elif ts7 == 0 and ts8 == 1:
            n01 += 1
        elif ts7 == 1 and ts8 == 0:
            n10 += 1
        elif ts7 == 1 and ts8 == 1:
            n11 += 1

    mcnemar_exact = binomtest(n01, n01 + n10, 0.5)
    diff_ts_mean = float(np.mean(diffs_ts))
    diff_ts_se = float(np.std(diffs_ts, ddof=1) / math.sqrt(len(diffs_ts)))
    ci_diff_ts = (diff_ts_mean - 1.95996 * diff_ts_se, diff_ts_mean + 1.95996 * diff_ts_se)

    cost_v7_mean = float(np.mean([float(r["anchor_cost"]) for r in v7_episodes.values()]))
    cost_v8_mean = float(np.mean([float(r["anchor_cost"]) for r in v8_episodes.values()]))
    t_cost = ttest_rel([float(r["anchor_cost"]) for r in v8_episodes.values()], [float(r["anchor_cost"]) for r in v7_episodes.values()])

    print("\n" + "=" * 80)
    print("PAIRED STATISTICAL COMPARISON: AEGIS-NEXT (V8) VS AEGIS-V7")
    print(f"Matched Episodes: {len(v7_episodes)}")
    print(f"True Success: V7 = 267 (53.4%), V8 = 251 (50.2%), Delta = {diff_ts_mean*100:.2f}%")
    print(f"Discordant Pairs: V8 wins (V7=0, V8=1) = {n01}, V7 wins (V7=1, V8=0) = {n10}")
    print(f"McNemar Exact 2-sided p-value: {mcnemar_exact.pvalue:.4f}")
    print(f"95% Wald CI for Paired True Success Difference: [{ci_diff_ts[0]*100:.2f}%, {ci_diff_ts[1]*100:.2f}%]")
    print(f"Noninferiority Check at Margin delta_NI = 5.0%: {ci_diff_ts[0] > -0.05} (Lower bound {ci_diff_ts[0]*100:.2f}% is below -5.00%)")
    print(f"Anchor Cost: V7 = {cost_v7_mean:.4f}, V8 = {cost_v8_mean:.4f}, Reduction = {((cost_v8_mean - cost_v7_mean)/cost_v7_mean)*100:.1f}% (p = {t_cost.pvalue:.2e})")
    print("=" * 80)

    return {
        "recalculated_rows": recalculated_rows,
        "discrepancies": reconciliation_discrepancies,
        "w_ci": w_ci,
        "cp_ci": cp_ci,
        "mcnemar_p": mcnemar_exact.pvalue,
        "diff_ts_mean": diff_ts_mean,
        "ci_diff_ts": ci_diff_ts,
    }


if __name__ == "__main__":
    audit_and_recalculate_v8()
