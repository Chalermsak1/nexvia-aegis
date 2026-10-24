"""
NEXVIA AEGIS V7.0 — Publication-Quality Figure Generation Suite.

Generates 4 publication figures at 300 DPI from real empirical CSV records:
- fig1_v7_success_and_coverage.png: Task Success and Coverage Across Scenarios (V6 vs V7 variants)
- fig2_v7_common_mode_and_anchor_efficiency.png: Resolution of H4 Correlated Bias & Query Costs
- fig3_v7_overshoot_and_terminal_velocity.png: Physical Overshoot & Velocity Comparison (MPC vs V6)
- fig4_v7_ablation_contributions.png: Component Ablation Contributions (True Success vs Covered Risk)
"""

from __future__ import annotations

import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np


def set_aesthetics():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "axes.labelweight": "bold",
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.titlesize": 14,
        "figure.titleweight": "bold",
        "axes.grid": True,
        "grid.alpha": 0.4,
        "grid.linestyle": "--",
    })


def read_summary_csv(csv_path: str) -> list[dict]:
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def plot_fig1_success_and_coverage(summary_csv: str, output_path: str):
    rows = read_summary_csv(summary_csv)
    scenarios = list(dict.fromkeys(r["scenario"] for r in rows))
    policies = [
        "AEGIS_V6_BASELINE",
        "AEGIS_V7_MPC_NO_ANCHOR",
        "AEGIS_V7_MPC_ON_DEMAND",
        "AEGIS_V7_MPC_ALWAYS_ON",
    ]
    labels = ["V6 Baseline", "V7 MPC (No Anchor)", "V7 Full (On-Demand)", "V7 Always-On"]
    colors = ["#4A5568", "#3182CE", "#2F855A", "#805AD5"]

    x = np.arange(len(scenarios))
    width = 0.20

    fig, ax = plt.subplots(figsize=(14, 6.5), dpi=300)

    for i, (pol, label, color) in enumerate(zip(policies, labels, colors)):
        rates = []
        covs = []
        for scen in scenarios:
            match = next((r for r in rows if r["scenario"] == scen and r["policy"] == pol), None)
            if match:
                rates.append(float(match["true_success_rate"]) * 100.0)
                covs.append(float(match["task_coverage_rate"]) * 100.0)
            else:
                rates.append(0.0)
                covs.append(0.0)

        rates = np.array(rates)
        covs = np.array(covs)
        offset = (i - 1.5) * width
        ax.bar(x + offset, rates, width, label=label, color=color, alpha=0.9, edgecolor="black", linewidth=0.7)
        ax.bar(x + offset, covs - rates, width, bottom=rates, color=color, alpha=0.3, hatch="//", edgecolor="black", linewidth=0.5)

    ax.set_ylabel("Rate (%)")
    ax.set_title("V7.0 Empirical Main Benchmark: Task Success and Coverage Across 10 Scenarios")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=25, ha="right")
    ax.set_ylim(0, 105)
    ax.legend(title="Policy Architecture (Solid: True Success, Hatched: Coverage Margin)", loc="upper right")

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    print(f"Generated Figure 1: {output_path}")


def plot_fig2_common_mode_and_anchor(summary_csv: str, output_path: str):
    rows = read_summary_csv(summary_csv)
    target_scens = ["CORRELATED_BIAS", "COMPOUND_HOLDOUT", "CORRUPTED_ANCHOR_STRESS"]

    policies = [
        "AEGIS_V6_BASELINE",
        "AEGIS_V7_MPC_NO_ANCHOR",
        "AEGIS_V7_MPC_ON_DEMAND",
        "AEGIS_V7_MPC_ALWAYS_ON",
    ]
    labels = ["V6 Base", "V7 (No Anchor)", "V7 On-Demand", "V7 Always-On"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5), dpi=300)

    x = np.arange(len(target_scens))
    width = 0.20
    for i, (pol, lbl) in enumerate(zip(policies, labels)):
        rates = []
        for scen in target_scens:
            match = next((r for r in rows if r["scenario"] == scen and r["policy"] == pol), None)
            rates.append(float(match["true_success_rate"]) * 100.0 if match else 0.0)
        ax1.bar(x + (i - 1.5) * width, rates, width, label=lbl, edgecolor="black", linewidth=0.7)

    ax1.set_ylabel("True Success Rate (%)")
    ax1.set_title("Common-Mode Fault Recovery ($H_4$)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(target_scens, rotation=15, ha="right")
    ax1.set_ylim(0, 105)
    ax1.legend(loc="upper right")

    # Queries and Costs
    on_sub = [r for r in rows if r["policy"] == "AEGIS_V7_MPC_ON_DEMAND"]
    al_sub = [r for r in rows if r["policy"] == "AEGIS_V7_MPC_ALWAYS_ON"]

    mean_queries = [
        np.mean([float(r["mean_anchor_queries"]) for r in on_sub]),
        np.mean([float(r["mean_anchor_queries"]) for r in al_sub]),
    ]
    mean_costs = [
        np.mean([float(r["mean_anchor_cost"]) for r in on_sub]),
        np.mean([float(r["mean_anchor_cost"]) for r in al_sub]),
    ]

    anchor_lbls = ["On-Demand (Selective)", "Always-On (Unconditional)"]
    x_bar = np.arange(2)
    ax2_twin = ax2.twinx()
    ax2.bar(x_bar - 0.15, mean_queries, width=0.3, color="#2B6CB0", label="Mean Queries", edgecolor="black")
    ax2_twin.bar(x_bar + 0.15, mean_costs, width=0.3, color="#C53030", label="Mean Query Cost", edgecolor="black")

    ax2.set_ylabel("Mean Queries per Episode", color="#2B6CB0")
    ax2_twin.set_ylabel("Mean Query Cost Accrued", color="#C53030")
    ax2.set_title("Anchor Efficiency: Selective vs. Always-On")
    ax2.set_xticks(x_bar)
    ax2.set_xticklabels(anchor_lbls)
    ax2.grid(False)

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    print(f"Generated Figure 2: {output_path}")


def plot_fig3_overshoot_comparison(summary_csv: str, output_path: str):
    rows = read_summary_csv(summary_csv)
    scenarios = list(dict.fromkeys(r["scenario"] for r in rows))

    v6_overshoot = []
    v7_overshoot = []
    for scen in scenarios:
        m6 = next((r for r in rows if r["scenario"] == scen and r["policy"] == "AEGIS_V6_BASELINE"), None)
        m7 = next((r for r in rows if r["scenario"] == scen and r["policy"] == "AEGIS_V7_MPC_NO_ANCHOR"), None)
        v6_overshoot.append(float(m6["mean_max_overshoot"]) if m6 else 0.0)
        v7_overshoot.append(float(m7["mean_max_overshoot"]) if m7 else 0.0)

    x = np.arange(len(scenarios))
    width = 0.35

    fig, ax = plt.subplots(figsize=(13, 5.5), dpi=300)
    ax.bar(x - width/2, v6_overshoot, width, label="V6 Baseline (Open-Loop Probing)", color="#E53E3E", edgecolor="black", alpha=0.9)
    ax.bar(x + width/2, v7_overshoot, width, label="V7 Risk-Constrained MPC (Terminal Braking)", color="#319795", edgecolor="black", alpha=0.9)

    ax.set_ylabel("Mean Physical Overshoot (m)")
    ax.set_title("Physical Feasibility: Maximum Target Overshoot (MPC vs. V6 Probing)")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=25, ha="right")
    ax.legend(loc="upper right")

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    print(f"Generated Figure 3: {output_path}")


def plot_fig4_ablation_contributions(ablation_csv: str, output_path: str):
    rows = read_summary_csv(ablation_csv)
    configs = list(dict.fromkeys(r["configuration"] for r in rows))

    avg_success = []
    avg_risk = []

    for cfg in configs:
        sub = [r for r in rows if r["configuration"] == cfg]
        avg_success.append(np.mean([float(r["true_success_rate"]) for r in sub]) * 100.0)
        valid_risk = [float(r["covered_risk"]) for r in sub if r["covered_risk"] != "N/A"]
        avg_risk.append(np.mean(valid_risk) * 100.0 if valid_risk else 0.0)

    clean_labels = [
        "V7 Full On-Demand",
        "A: No MPC (Open-Loop)",
        "B: No Terminal Braking",
        "C: Generic FIM Only",
        "D: No Anchor (Two Sensors)",
        "E: Unconditional Anchor",
        "F: No Anchor Gate",
        "H: Fixed Orthogonal Probe",
    ]

    y = np.arange(len(configs))
    height = 0.35

    fig, ax = plt.subplots(figsize=(11, 6), dpi=300)

    ax.barh(y - height/2, avg_success, height, label="True Success Rate (%)", color="#2F855A", edgecolor="black")
    ax.barh(y + height/2, avg_risk, height, label="Covered Risk (%)", color="#E53E3E", edgecolor="black")

    ax.set_yticks(y)
    ax.set_yticklabels(clean_labels)
    ax.invert_yaxis()
    ax.set_xlabel("Percentage (%)")
    ax.set_xlim(0, 100)
    ax.set_title("V7 Component Ablation Suite: Success and Selective Risk Trade-offs")
    ax.legend(loc="upper right")

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    print(f"Generated Figure 4: {output_path}")


def main():
    set_aesthetics()
    results_dir = Path("results/v7")
    fig_dir = results_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    sum_csv = results_dir / "v7_benchmark_summary.csv"
    abl_csv = results_dir / "v7_ablation_summary.csv"

    if sum_csv.exists():
        plot_fig1_success_and_coverage(str(sum_csv), str(fig_dir / "fig1_v7_success_and_coverage.png"))
        plot_fig2_common_mode_and_anchor(str(sum_csv), str(fig_dir / "fig2_v7_common_mode_and_anchor_efficiency.png"))
        plot_fig3_overshoot_comparison(str(sum_csv), str(fig_dir / "fig3_v7_overshoot_and_terminal_velocity.png"))

    if abl_csv.exists():
        plot_fig4_ablation_contributions(str(abl_csv), str(fig_dir / "fig4_v7_ablation_contributions.png"))


if __name__ == "__main__":
    main()
