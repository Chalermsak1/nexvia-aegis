"""
NEXVIA AEGIS-Next (V8) — Publication Figure Generator (300 DPI).

Generates:
1. fig1_next_success_and_coverage.png: True Success and Task Coverage across 8 policies.
2. fig2_next_covered_risk_safety.png: Empirical Covered Risk vs 5.0% certified threshold.
3. fig3_next_anchor_efficiency_pareto.png: Operational anchor query cost vs task success.
4. fig4_next_overshoot_comparison.png: Dynamic feasibility and target overshoot comparison.
"""

from __future__ import annotations

import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

# Set publication style
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 14,
    "figure.dpi": 300,
})

RESULTS_DIR = Path("results/next")
FIGURES_DIR = RESULTS_DIR / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def load_data():
    summary_path = RESULTS_DIR / "benchmark_summary.csv"
    episodes_path = RESULTS_DIR / "benchmark_episodes.csv"

    with open(summary_path) as f:
        summaries = list(csv.DictReader(f))

    with open(episodes_path) as f:
        episodes = list(csv.DictReader(f))

    return summaries, episodes


def plot_fig1_success_and_coverage(summaries):
    """Figure 1: Aggregate True Success and Coverage across 8 policies."""
    policies = [
        "UNSHIELDED_ALWAYS_ACT",
        "CHISQUARE_NIS_GATING",
        "EKF_CONSISTENCY_MONITOR",
        "AEGIS_V4_PASSIVE_VERIFY",
        "AEGIS_V5_HUBER_CALIBRATE",
        "AEGIS_V6_DISCRIMINATIVE",
        "AEGIS_V7_MPC_BASELINE",
        "AEGIS_NEXT_MARTINGALE",
    ]

    labels = [
        "Unshielded",
        "Chi-Square NIS",
        "EKF Monitor",
        "AEGIS V4",
        "AEGIS V5",
        "AEGIS V6",
        "AEGIS V7 MPC",
        "AEGIS-Next (V8)",
    ]

    ts_rates = []
    cov_rates = []

    for pol in policies:
        sub = [r for r in summaries if r["policy"] == pol]
        total_ep = sum(int(r["episodes"]) for r in sub)
        total_ts = sum(int(r["true_success_count"]) for r in sub)
        total_fs = sum(int(r["false_success_count"]) for r in sub)
        ts_rates.append((total_ts / total_ep) * 100.0)
        cov_rates.append(((total_ts + total_fs) / total_ep) * 100.0)

    x = np.arange(len(labels))
    width = 0.38

    fig, ax = plt.subplots(figsize=(11, 5.5))
    rects1 = ax.bar(x - width/2, ts_rates, width, label="True Success Rate (%)", color="#1f77b4", edgecolor="black", linewidth=0.8)
    rects2 = ax.bar(x + width/2, cov_rates, width, label="Task Coverage Rate (%)", color="#aec7e8", edgecolor="black", linewidth=0.8)

    ax.set_ylabel("Percentage (%)")
    ax.set_title("Figure 1: Aggregate True Success and Task Coverage across 4,000 Evaluations")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylim(0, 105)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper left")

    # Add values on top of bars
    for rect in rects1:
        h = rect.get_height()
        ax.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8.5, weight="bold")

    plt.tight_layout()
    out_file = FIGURES_DIR / "fig1_next_success_and_coverage.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"Generated {out_file}")


def plot_fig2_covered_risk_safety(summaries):
    """Figure 2: Covered Risk (False Success on Covered Decisions) vs 5.0% Target."""
    policies = [
        "UNSHIELDED_ALWAYS_ACT",
        "CHISQUARE_NIS_GATING",
        "EKF_CONSISTENCY_MONITOR",
        "AEGIS_V4_PASSIVE_VERIFY",
        "AEGIS_V5_HUBER_CALIBRATE",
        "AEGIS_V6_DISCRIMINATIVE",
        "AEGIS_V7_MPC_BASELINE",
        "AEGIS_NEXT_MARTINGALE",
    ]

    labels = [
        "Unshielded",
        "Chi-Square NIS",
        "EKF Monitor",
        "AEGIS V4",
        "AEGIS V5",
        "AEGIS V6",
        "AEGIS V7 MPC",
        "AEGIS-Next (V8)",
    ]

    risks = []
    for pol in policies:
        sub = [r for r in summaries if r["policy"] == pol]
        total_ts = sum(int(r["true_success_count"]) for r in sub)
        total_fs = sum(int(r["false_success_count"]) for r in sub)
        covered = total_ts + total_fs
        if covered > 0:
            risks.append((total_fs / covered) * 100.0)
        else:
            risks.append(0.0)

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["#d62728" if r > 5.0 else "#2ca02c" for r in risks]
    bars = ax.bar(labels, risks, color=colors, edgecolor="black", linewidth=0.8, width=0.55)

    ax.axhline(5.0, color="red", linestyle="--", linewidth=1.8, label="Pre-registered Risk Bound (5.0%)")
    ax.set_ylabel("Covered Risk $R_{cov}$ (%)")
    ax.set_title("Figure 2: Empirical Covered Risk across Competing Architectures")
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylim(0, max(max(risks) * 1.15, 12.0))
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper right")

    for bar, val in zip(bars, risks):
        ax.annotate(f"{val:.2f}%", xy=(bar.get_x() + bar.get_width() / 2, val),
                    xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=9, weight="bold")

    plt.tight_layout()
    out_file = FIGURES_DIR / "fig2_next_covered_risk_safety.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"Generated {out_file}")


def plot_fig3_anchor_efficiency_pareto(summaries):
    """Figure 3: Anchor Query Cost vs True Success Rate (Pareto Frontier)."""
    policies = [
        ("UNSHIELDED_ALWAYS_ACT", "Unshielded", "o", "#7f7f7f"),
        ("CHISQUARE_NIS_GATING", "Chi-Square NIS", "s", "#8c564b"),
        ("EKF_CONSISTENCY_MONITOR", "EKF Monitor", "^", "#e377c2"),
        ("AEGIS_V4_PASSIVE_VERIFY", "AEGIS V4", "v", "#bcbd22"),
        ("AEGIS_V5_HUBER_CALIBRATE", "AEGIS V5", "d", "#17becf"),
        ("AEGIS_V6_DISCRIMINATIVE", "AEGIS V6", "<", "#ff7f0e"),
        ("AEGIS_V7_MPC_BASELINE", "AEGIS V7 MPC", "p", "#1f77b4"),
        ("AEGIS_NEXT_MARTINGALE", "AEGIS-Next (V8)", "*", "#2ca02c"),
    ]

    fig, ax = plt.subplots(figsize=(9, 5.5))

    for pol_key, name, marker, color in policies:
        sub = [r for r in summaries if r["policy"] == pol_key]
        total_ep = sum(int(r["episodes"]) for r in sub)
        total_ts = sum(int(r["true_success_count"]) for r in sub)
        ts_pct = (total_ts / total_ep) * 100.0
        mean_cost = float(np.mean([float(r["mean_anchor_cost"]) for r in sub]))

        size = 200 if "NEXT" in pol_key else 110
        ax.scatter(mean_cost, ts_pct, s=size, color=color, marker=marker, edgecolors="black", linewidth=1.2, label=name, zorder=5)

    ax.set_xlabel("Mean Anchor Query Cost ($C_{anchor}$)")
    ax.set_ylabel("Aggregate True Success Rate (%)")
    ax.set_title("Figure 3: Operational Anchoring Cost vs Task Success Pareto Analysis")
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend(loc="lower right")

    plt.tight_layout()
    out_file = FIGURES_DIR / "fig3_next_anchor_efficiency_pareto.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"Generated {out_file}")


def plot_fig4_overshoot_comparison(summaries):
    """Figure 4: Mean Maximum Target Overshoot (m)."""
    policies = [
        "AEGIS_V6_DISCRIMINATIVE",
        "AEGIS_V7_MPC_BASELINE",
        "AEGIS_NEXT_MARTINGALE",
    ]
    labels = ["AEGIS V6", "AEGIS V7 MPC", "AEGIS-Next (V8)"]

    overshoots = []
    for pol in policies:
        sub = [r for r in summaries if r["policy"] == pol]
        vals = [float(r["mean_max_overshoot"]) for r in sub]
        overshoots.append(float(np.mean(vals)))

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(labels, overshoots, color=["#ff7f0e", "#1f77b4", "#2ca02c"], edgecolor="black", linewidth=0.8, width=0.45)

    ax.set_ylabel("Mean Maximum Overshoot (m)")
    ax.set_title("Figure 4: Target Overshoot Comparison Under MuJoCo Dynamics")
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for bar, val in zip(bars, overshoots):
        ax.annotate(f"{val:.4f} m", xy=(bar.get_x() + bar.get_width() / 2, val),
                    xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=10, weight="bold")

    plt.tight_layout()
    out_file = FIGURES_DIR / "fig4_next_overshoot_comparison.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"Generated {out_file}")


def main():
    if not (RESULTS_DIR / "benchmark_summary.csv").exists():
        print("benchmark_summary.csv not found. Wait for benchmark execution.")
        return

    summaries, episodes = load_data()
    plot_fig1_success_and_coverage(summaries)
    plot_fig2_covered_risk_safety(summaries)
    plot_fig3_anchor_efficiency_pareto(summaries)
    plot_fig4_overshoot_comparison(summaries)
    print("All publication figures successfully created!")


if __name__ == "__main__":
    main()
