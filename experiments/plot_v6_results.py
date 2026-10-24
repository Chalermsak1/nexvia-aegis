"""
NEXVIA AEGIS V6.0 — Publication Figure Generation Suite.

Generates 4 publication-quality 300 DPI figures:
1. fig1_v6_success_and_coverage.png: True Success & Autonomous Task Coverage across policies.
2. fig2_v6_diagnostic_accuracy_and_entropy.png: Diagnostic Accuracy & Entropy by scenario.
3. fig3_v6_bias_rmse_by_trajectory.png: Parameter RMSE across trajectory probing strategies.
4. fig4_v6_ablation_contributions.png: Ablation impacts on safety and coverage.
"""

from __future__ import annotations

import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np


def plot_v6_figures(
    summary_csv_path: str = "results/v6/v6_benchmark_summary.csv",
    ablation_csv_path: str = "results/v6/v6_ablation_summary.csv",
    figures_dir: str = "results/v6/figures",
) -> None:
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    # Read summary CSV
    rows: list[dict] = []
    with open(summary_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    scenarios = list(dict.fromkeys(r["scenario"] for r in rows))
    policies = list(dict.fromkeys(r["policy"] for r in rows))

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.size"] = 11

    # -----------------------------------------------------------------------
    # Figure 1: True Success Rate and Autonomous Task Coverage
    # -----------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7), sharey=True)

    colors = {
        "AEGIS_V5_ROBUST": "#4A5568",
        "AEGIS_V6_FIXED_PROBE": "#4299E1",
        "AEGIS_V6_CIRCULAR": "#ED8936",
        "AEGIS_V6_FIGURE_EIGHT": "#9F7AEA",
        "AEGIS_V6_FIM_GUIDED": "#38B2AC",
        "AEGIS_V6_FULL_DISCRIMINATIVE": "#48BB78",
    }
    labels = {
        "AEGIS_V5_ROBUST": "V5 Robust (Baseline)",
        "AEGIS_V6_FIXED_PROBE": "V6 Fixed Probing",
        "AEGIS_V6_CIRCULAR": "V6 Circular Probing",
        "AEGIS_V6_FIGURE_EIGHT": "V6 Figure-8 Probing",
        "AEGIS_V6_FIM_GUIDED": "V6 FIM-Guided",
        "AEGIS_V6_FULL_DISCRIMINATIVE": "V6 Full (Discriminative)",
    }

    n_scen = len(scenarios)
    bar_width = 0.13
    indices = np.arange(n_scen)

    for i, pol in enumerate(policies):
        sub = [r for r in rows if r["policy"] == pol]
        cov_vals = [float(r["coverage_rate"]) * 100 for r in sub]
        succ_vals = [float(r["true_success_rate"]) * 100 for r in sub]
        offset = (i - len(policies) / 2 + 0.5) * bar_width

        ax1.bar(indices + offset, cov_vals, bar_width, label=labels.get(pol, pol), color=colors.get(pol, "#888888"), edgecolor="black", linewidth=0.6)
        ax2.bar(indices + offset, succ_vals, bar_width, label=labels.get(pol, pol), color=colors.get(pol, "#888888"), edgecolor="black", linewidth=0.6)

    ax1.set_title("Autonomous Task Coverage (%) across Fault Scenarios", fontsize=13, fontweight="bold", pad=12)
    ax1.set_ylabel("Task Coverage (%)", fontsize=12)
    ax1.set_xticks(indices)
    ax1.set_xticklabels([s.replace("_", "\n") for s in scenarios], fontsize=9)
    ax1.set_ylim(0, 105)
    ax1.legend(loc="upper right", framealpha=0.9, fontsize=9)

    ax2.set_title("True Task Success Rate (%) across Fault Scenarios", fontsize=13, fontweight="bold", pad=12)
    ax2.set_ylabel("True Success Rate (%)", fontsize=12)
    ax2.set_xticks(indices)
    ax2.set_xticklabels([s.replace("_", "\n") for s in scenarios], fontsize=9)
    ax2.set_ylim(0, 105)
    ax2.legend(loc="upper right", framealpha=0.9, fontsize=9)

    plt.tight_layout()
    f1_path = fig_path / "fig1_v6_success_and_coverage.png"
    plt.savefig(f1_path, dpi=300)
    plt.close()
    print(f"Generated Figure 1 -> {f1_path}")

    # -----------------------------------------------------------------------
    # Figure 2: Diagnostic Accuracy & Entropy
    # -----------------------------------------------------------------------
    v6_disc = [r for r in rows if r["policy"] == "AEGIS_V6_FULL_DISCRIMINATIVE"]
    if v6_disc:
        fig, ax1 = plt.subplots(figsize=(11, 5.5))
        ax2 = ax1.twinx()

        diag_accs = [float(r["diagnostic_accuracy"]) * 100 if r["diagnostic_accuracy"] != "N/A" else 0.0 for r in v6_disc]
        entropies = [float(r["mean_diagnostic_entropy"]) if r["mean_diagnostic_entropy"] != "N/A" else 0.0 for r in v6_disc]

        x = np.arange(len(scenarios))
        w = 0.38
        b1 = ax1.bar(x - w / 2, diag_accs, w, color="#3182CE", edgecolor="black", linewidth=0.7, label="Diagnostic Accuracy (%)")
        b2 = ax2.bar(x + w / 2, entropies, w, color="#DD6B20", edgecolor="black", linewidth=0.7, label="Diagnostic Entropy (nats)")

        ax1.set_title("AEGIS V6.0 Multi-Hypothesis Diagnostic Accuracy & Uncertainty", fontsize=13, fontweight="bold", pad=12)
        ax1.set_xticks(x)
        ax1.set_xticklabels([s.replace("_", "\n") for s in scenarios], fontsize=9)
        ax1.set_ylabel("Diagnostic Accuracy (%)", color="#2B6CB0", fontsize=12)
        ax1.set_ylim(0, 110)
        ax2.set_ylabel("Shannon Entropy (nats)", color="#C05621", fontsize=12)
        ax2.set_ylim(0, 2.2)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", framealpha=0.9)

        plt.tight_layout()
        f2_path = fig_path / "fig2_v6_diagnostic_accuracy_and_entropy.png"
        plt.savefig(f2_path, dpi=300)
        plt.close()
        print(f"Generated Figure 2 -> {f2_path}")

    # -----------------------------------------------------------------------
    # Figure 3: Bias Estimation RMSE by Trajectory Strategy
    # -----------------------------------------------------------------------
    stress_scens = ["PRIMARY_BIAS", "INDEPENDENT_BIAS", "CORRELATED_BIAS", "SENSOR_DRIFT", "OUTLIER_BURSTS"]
    fig, ax = plt.subplots(figsize=(11, 5.5))

    strat_policies = [
        "AEGIS_V5_ROBUST",
        "AEGIS_V6_FIXED_PROBE",
        "AEGIS_V6_CIRCULAR",
        "AEGIS_V6_FIGURE_EIGHT",
        "AEGIS_V6_FIM_GUIDED",
        "AEGIS_V6_FULL_DISCRIMINATIVE",
    ]
    x_sc = np.arange(len(stress_scens))
    bw = 0.13

    for i, p in enumerate(strat_policies):
        errs = []
        for sc in stress_scens:
            match = next((r for r in rows if r["scenario"] == sc and r["policy"] == p), None)
            val = float(match["mean_bias_error"]) if (match and match["mean_bias_error"] != "N/A") else 0.0
            errs.append(val)
        off = (i - len(strat_policies) / 2 + 0.5) * bw
        ax.bar(x_sc + off, errs, bw, label=labels.get(p, p), color=colors.get(p, "#888888"), edgecolor="black", linewidth=0.6)

    ax.set_title("Offline Bias Estimation RMSE (m) Across Trajectory Strategies", fontsize=13, fontweight="bold", pad=12)
    ax.set_xticks(x_sc)
    ax.set_xticklabels([s.replace("_", "\n") for s in stress_scens], fontsize=10)
    ax.set_ylabel("Mean Bias Estimation Error (m)", fontsize=12)
    ax.set_ylim(0, 1.4)
    ax.legend(loc="upper right", framealpha=0.9, fontsize=9)

    plt.tight_layout()
    f3_path = fig_path / "fig3_v6_bias_rmse_by_trajectory.png"
    plt.savefig(f3_path, dpi=300)
    plt.close()
    print(f"Generated Figure 3 -> {f3_path}")

    # -----------------------------------------------------------------------
    # Figure 4: Ablation Contributions (if ablation summary exists)
    # -----------------------------------------------------------------------
    if Path(ablation_csv_path).exists():
        ab_rows: list[dict] = []
        with open(ablation_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                ab_rows.append(r)

        if ab_rows:
            ab_cfgs = list(dict.fromkeys(r["ablation_configuration"] for r in ab_rows))
            fig, ax = plt.subplots(figsize=(12, 6))

            # Mean success rate across all ablation scenarios
            succ_means = []
            risk_means = []
            for cfg in ab_cfgs:
                sub = [r for r in ab_rows if r["ablation_configuration"] == cfg]
                succ_means.append(np.mean([float(r["true_success_rate"]) * 100 for r in sub]))
                r_vals = [float(r["covered_risk"]) * 100 for r in sub if r["covered_risk"] != "N/A"]
                risk_means.append(np.mean(r_vals) if r_vals else 0.0)

            y = np.arange(len(ab_cfgs))
            h = 0.38
            ax.barh(y - h / 2, succ_means, h, color="#38A169", edgecolor="black", linewidth=0.6, label="True Success Rate (%)")
            ax.barh(y + h / 2, risk_means, h, color="#E53E3E", edgecolor="black", linewidth=0.6, label="Covered Risk (%)")

            ax.set_yticks(y)
            clean_labels = [c.replace("ABLATION_", "").replace("_", " ") for c in ab_cfgs]
            ax.set_yticklabels(clean_labels, fontsize=10)
            ax.set_xlabel("Percentage (%)", fontsize=12)
            ax.set_title("Component Ablations: Trade-off between True Success and Covered Risk", fontsize=13, fontweight="bold", pad=12)
            ax.set_xlim(0, 100)
            ax.legend(loc="upper right", framealpha=0.9)
            ax.invert_yaxis()

            plt.tight_layout()
            f4_path = fig_path / "fig4_v6_ablation_contributions.png"
            plt.savefig(f4_path, dpi=300)
            plt.close()
            print(f"Generated Figure 4 -> {f4_path}")


if __name__ == "__main__":
    plot_v6_figures()
