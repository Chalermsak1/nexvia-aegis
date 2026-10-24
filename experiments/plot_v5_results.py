from __future__ import annotations

import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

OUTPUT_DIR = Path("results/v5/figures")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SUMMARY_CSV = Path("results/v5/v5_benchmark_summary.csv")
EPISODES_CSV = Path("results/v5/v5_benchmark_episodes.csv")


def load_summary_data() -> list[dict]:
    with open(SUMMARY_CSV, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def plot_coverage_and_success(summary_rows: list[dict]):
    scenarios = [
        "NOMINAL",
        "SENSOR_DRIFT",
        "OUTLIER_BURSTS",
        "SENSOR_DROPOUT",
        "PRIMARY_BIAS",
        "INDEPENDENT_BIAS",
        "CORRELATED_BIAS",
        "COMPOUND_HOLDOUT",
        "FAULTY_REFERENCE_SENSOR",
        "LOW_OBSERVABILITY",
    ]
    policies = ["AEGIS_V4_FULL", "AEGIS_V5_OLS", "AEGIS_V5_ROBUST"]
    labels = ["V4 Full (Conservative)", "V5 OLS", "V5 Robust (Huber)"]
    colors = ["#4A5568", "#3182CE", "#38A169"]

    # 1. Task Coverage Comparison
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    x = np.arange(len(scenarios))
    width = 0.25

    for idx, (p, label, c) in enumerate(zip(policies, labels, colors)):
        cov_vals = []
        suc_vals = []
        for sc in scenarios:
            row = [r for r in summary_rows if r["scenario"] == sc and r["policy"] == p][0]
            cov_vals.append(float(row["coverage_rate"]) * 100)
            suc_vals.append(float(row["true_success_rate"]) * 100)

        offset = (idx - 1) * width
        ax1.bar(x + offset, cov_vals, width, label=label, color=c, alpha=0.85, edgecolor="black", linewidth=0.8)
        ax2.bar(x + offset, suc_vals, width, label=label, color=c, alpha=0.85, edgecolor="black", linewidth=0.8)

    for ax, title, ylabel in zip(
        [ax1, ax2],
        ["Autonomous Task Coverage (%)", "Ground-Truth Task Success Rate (%)"],
        ["Coverage (%)", "Success Rate (%)"],
    ):
        ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(
            [s.replace("_", "\n") for s in scenarios],
            rotation=0,
            fontsize=8.5,
            fontweight="medium",
        )
        ax.set_ylim(0, 105)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        ax.legend(frameon=True, facecolor="white", edgecolor="none", fontsize=9.5)

    plt.tight_layout()
    plot_path = OUTPUT_DIR / "fig1_v5_coverage_and_success.png"
    plt.savefig(plot_path, dpi=300)
    plt.close()
    print(f"Saved: {plot_path}")


def plot_false_success_risk(summary_rows: list[dict]):
    scenarios = [
        "NOMINAL",
        "SENSOR_DRIFT",
        "OUTLIER_BURSTS",
        "SENSOR_DROPOUT",
        "PRIMARY_BIAS",
        "INDEPENDENT_BIAS",
        "CORRELATED_BIAS",
        "COMPOUND_HOLDOUT",
        "FAULTY_REFERENCE_SENSOR",
        "LOW_OBSERVABILITY",
    ]
    policies = ["AEGIS_V4_FULL", "AEGIS_V5_OLS", "AEGIS_V5_ROBUST", "AEGIS_V5_NO_OBS_GATE"]
    labels = ["V4 Full", "V5 OLS", "V5 Robust", "V5 No Obs Gate"]
    colors = ["#718096", "#3182CE", "#38A169", "#E53E3E"]

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(scenarios))
    width = 0.20

    for idx, (p, label, c) in enumerate(zip(policies, labels, colors)):
        risk_vals = []
        for sc in scenarios:
            row = [r for r in summary_rows if r["scenario"] == sc and r["policy"] == p][0]
            risk_vals.append(float(row["false_success_rate"]) * 100)

        offset = (idx - 1.5) * width
        ax.bar(x + offset, risk_vals, width, label=label, color=c, alpha=0.85, edgecolor="black", linewidth=0.8)

    ax.set_title("Overall False-Success Incidence Across All Episodes (%)", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("False Success Rate (%)", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("_", "\n") for s in scenarios], fontsize=8.5)
    ax.set_ylim(0, 35)
    ax.axhline(2.0, color="red", linestyle=":", linewidth=1.5, label="Target Safety Bound (2.0%)")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(frameon=True, facecolor="white", fontsize=9.5)

    plt.tight_layout()
    plot_path = OUTPUT_DIR / "fig2_v5_false_success_risk.png"
    plt.savefig(plot_path, dpi=300)
    plt.close()
    print(f"Saved: {plot_path}")


def plot_bias_estimation_error(summary_rows: list[dict]):
    scenarios = [
        "PRIMARY_BIAS",
        "INDEPENDENT_BIAS",
        "CORRELATED_BIAS",
        "SENSOR_DRIFT",
        "OUTLIER_BURSTS",
        "COMPOUND_HOLDOUT",
        "LOW_OBSERVABILITY",
    ]
    policies = ["AEGIS_V5_OLS", "AEGIS_V5_ROBUST"]
    labels = ["V5 OLS", "V5 Robust (Huber)"]
    colors = ["#3182CE", "#38A169"]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(scenarios))
    width = 0.35

    for idx, (p, label, c) in enumerate(zip(policies, labels, colors)):
        errors = []
        for sc in scenarios:
            row = [r for r in summary_rows if r["scenario"] == sc and r["policy"] == p][0]
            val = float(row["mean_bias_error"]) if row["mean_bias_error"] != "N/A" else 0.0
            errors.append(val)

        offset = (idx - 0.5) * width
        ax.bar(x + offset, errors, width, label=label, color=c, alpha=0.85, edgecolor="black", linewidth=0.8)

    ax.set_title("Offline Bias Estimation Error RMSE Against Ground Truth (m)", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel("Mean Estimation Error (m)", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("_", "\n") for s in scenarios], fontsize=9)
    ax.set_ylim(0, 1.5)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(frameon=True, facecolor="white", fontsize=10)

    plt.tight_layout()
    plot_path = OUTPUT_DIR / "fig3_v5_bias_rmse.png"
    plt.savefig(plot_path, dpi=300)
    plt.close()
    print(f"Saved: {plot_path}")


def plot_observability_ablation(summary_rows: list[dict]):
    scenarios = ["PRIMARY_BIAS", "CORRELATED_BIAS", "FAULTY_REFERENCE_SENSOR", "LOW_OBSERVABILITY"]
    policies = ["AEGIS_V5_ROBUST", "AEGIS_V5_NO_OBS_GATE", "AEGIS_V5_NO_VALIDATION"]
    labels = ["V5 Robust (Full Gated)", "Ablation: No Obs Gate", "Ablation: No Validation Gate"]
    colors = ["#38A169", "#E53E3E", "#DD6B20"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    x = np.arange(len(scenarios))
    width = 0.25

    for idx, (p, label, c) in enumerate(zip(policies, labels, colors)):
        cal_rates = []
        steps = []
        for sc in scenarios:
            row = [r for r in summary_rows if r["scenario"] == sc and r["policy"] == p][0]
            cal_rates.append(float(row["calibrated_rate"]) * 100)
            steps.append(float(row["avg_steps"]))

        offset = (idx - 1) * width
        ax1.bar(x + offset, cal_rates, width, label=label, color=c, alpha=0.85, edgecolor="black", linewidth=0.8)
        ax2.bar(x + offset, steps, width, label=label, color=c, alpha=0.85, edgecolor="black", linewidth=0.8)

    ax1.set_title("Calibration Acceptance Rate (%)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Calibration Acceptance (%)")
    ax1.set_xticks(x)
    ax1.set_xticklabels([s.replace("_", "\n") for s in scenarios], fontsize=9)
    ax1.set_ylim(0, 105)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)
    ax1.legend(frameon=True, facecolor="white", fontsize=9)

    ax2.set_title("Average Steps Spent Wandering in Uncertified Modes", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Average Steps per Episode")
    ax2.set_xticks(x)
    ax2.set_xticklabels([s.replace("_", "\n") for s in scenarios], fontsize=9)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)
    ax2.legend(frameon=True, facecolor="white", fontsize=9)

    plt.tight_layout()
    plot_path = OUTPUT_DIR / "fig4_v5_ablation_gates.png"
    plt.savefig(plot_path, dpi=300)
    plt.close()
    print(f"Saved: {plot_path}")


def main():
    print("Generating AEGIS V5.0 Research Figures...")
    rows = load_summary_data()
    plot_coverage_and_success(rows)
    plot_false_success_risk(rows)
    plot_bias_estimation_error(rows)
    plot_observability_ablation(rows)
    print("All research figures generated successfully.")


if __name__ == "__main__":
    main()
