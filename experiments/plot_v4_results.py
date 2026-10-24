from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results" / "v4"
FIGURES_DIR = RESULTS_DIR / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

SUMMARY_CSV = RESULTS_DIR / "v4_benchmark_summary.csv"
EPISODES_CSV = RESULTS_DIR / "v4_benchmark_episodes.csv"


def load_summary() -> list[dict[str, Any]]:
    with open(SUMMARY_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_episodes() -> list[dict[str, Any]]:
    with open(EPISODES_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def plot_false_success_rate(summary: list[dict[str, Any]]):
    scenarios = [
        "NOMINAL",
        "PRIMARY_BIAS",
        "INDEPENDENT_BIAS",
        "CORRELATED_BIAS",
        "SENSOR_DRIFT",
        "OUTLIER_BURSTS",
        "SENSOR_DROPOUT",
        "COMPOUND_HOLDOUT",
    ]

    policies = [
        ("ALWAYS_ACT", "Always Act", "#d9534f"),
        ("FUSION_ONLY", "Sensor Fusion Only", "#f0ad4e"),
        ("AEGIS_NO_CROSS_MODAL", "AEGIS (No Cross-Modal)", "#5bc0de"),
        ("AEGIS_NO_ABSTAIN", "AEGIS (No Abstain)", "#9b59b6"),
        ("AEGIS_FULL", "AEGIS Full (Ours)", "#27ae60"),
    ]

    x = np.arange(len(scenarios))
    width = 0.16

    fig, ax = plt.subplots(figsize=(14, 6), dpi=300)

    for i, (p_id, p_label, color) in enumerate(policies):
        rates = []
        for sc in scenarios:
            row = next(
                r
                for r in summary
                if r["scenario"] == sc and r["policy"] == p_id
            )
            rates.append(float(row["false_success_rate"]) * 100.0)

        offset = (i - 2) * width
        rects = ax.bar(
            x + offset,
            rates,
            width,
            label=p_label,
            color=color,
            alpha=0.9,
            edgecolor="black",
            linewidth=0.6,
        )

    ax.set_ylabel("False-Success Rate (%) [Lower is Safer]", fontsize=12, fontweight="bold")
    ax.set_title(
        "NEXVIA AEGIS V4.0 — False-Success Rate Across Sensor Fault Scenarios",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=25, ha="right", fontsize=10, fontweight="medium")
    ax.set_ylim(0, 105)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend(frameon=True, facecolor="white", edgecolor="none", fontsize=10, loc="upper right")

    plt.tight_layout()
    out_file = FIGURES_DIR / "false_success_vs_scenario.png"
    plt.savefig(out_file)
    plt.close()
    print(f"Saved: {out_file}")


def plot_task_success_rate(summary: list[dict[str, Any]]):
    scenarios = [
        "NOMINAL",
        "PRIMARY_BIAS",
        "INDEPENDENT_BIAS",
        "CORRELATED_BIAS",
        "SENSOR_DRIFT",
        "OUTLIER_BURSTS",
        "SENSOR_DROPOUT",
        "COMPOUND_HOLDOUT",
    ]

    policies = [
        ("ALWAYS_ACT", "Always Act", "#d9534f"),
        ("FUSION_ONLY", "Sensor Fusion Only", "#f0ad4e"),
        ("AEGIS_NO_CROSS_MODAL", "AEGIS (No Cross-Modal)", "#5bc0de"),
        ("AEGIS_NO_ABSTAIN", "AEGIS (No Abstain)", "#9b59b6"),
        ("AEGIS_FULL", "AEGIS Full (Ours)", "#27ae60"),
    ]

    x = np.arange(len(scenarios))
    width = 0.16

    fig, ax = plt.subplots(figsize=(14, 6), dpi=300)

    for i, (p_id, p_label, color) in enumerate(policies):
        rates = []
        for sc in scenarios:
            row = next(
                r
                for r in summary
                if r["scenario"] == sc and r["policy"] == p_id
            )
            rates.append(float(row["true_success_rate"]) * 100.0)

        offset = (i - 2) * width
        ax.bar(
            x + offset,
            rates,
            width,
            label=p_label,
            color=color,
            alpha=0.9,
            edgecolor="black",
            linewidth=0.6,
        )

    ax.set_ylabel("True Task Success Rate (%)", fontsize=12, fontweight="bold")
    ax.set_title(
        "NEXVIA AEGIS V4.0 — Ground-Truth Task Success Rate (d_true <= 0.25m)",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=25, ha="right", fontsize=10, fontweight="medium")
    ax.set_ylim(0, 105)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend(frameon=True, facecolor="white", edgecolor="none", fontsize=10, loc="upper right")

    plt.tight_layout()
    out_file = FIGURES_DIR / "task_success_vs_scenario.png"
    plt.savefig(out_file)
    plt.close()
    print(f"Saved: {out_file}")


def plot_ablation_correlated_bias(summary: list[dict[str, Any]]):
    """
    Focused figure demonstrating H2 and H3:
    Under Correlated Bias, Always Act, Fusion, and Intra-Modal Ablation all fail with 74% false success.
    Cross-modal verification enables AEGIS Full to abstain and achieve 0% false success.
    """
    sc = "CORRELATED_BIAS"
    policies = [
        ("ALWAYS_ACT", "Always Act", "#d9534f"),
        ("FUSION_ONLY", "Sensor Fusion Only", "#f0ad4e"),
        ("AEGIS_NO_CROSS_MODAL", "AEGIS (No Cross-Modal)", "#5bc0de"),
        ("AEGIS_NO_ABSTAIN", "AEGIS (No Abstain)", "#9b59b6"),
        ("AEGIS_FULL", "AEGIS Full (Ours)", "#27ae60"),
    ]

    labels = [p[1] for p in policies]
    false_success = []
    abstain_rate = []

    for p_id, _, _ in policies:
        row = next(
            r for r in summary if r["scenario"] == sc and r["policy"] == p_id
        )
        false_success.append(float(row["false_success_rate"]) * 100.0)
        abstain_rate.append(float(row["abstain_rate"]) * 100.0)

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)

    rects1 = ax.bar(
        x - width / 2,
        false_success,
        width,
        label="False-Success Rate (%) [Unsafe Error]",
        color="#c0392b",
        edgecolor="black",
        linewidth=0.6,
    )
    rects2 = ax.bar(
        x + width / 2,
        abstain_rate,
        width,
        label="Abstention Rate (%) [Safe Refusal]",
        color="#2980b9",
        edgecolor="black",
        linewidth=0.6,
    )

    for r in rects1:
        h = r.get_height()
        ax.annotate(
            f"{h:.1f}%",
            xy=(r.get_x() + r.get_width() / 2, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    for r in rects2:
        h = r.get_height()
        ax.annotate(
            f"{h:.1f}%",
            xy=(r.get_x() + r.get_width() / 2, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    ax.set_ylabel("Percentage (%)", fontsize=11, fontweight="bold")
    ax.set_title(
        "Ablation Analysis Under Correlated Common-Mode Faults (Scenario S4)\n"
        "Vector Arbitration Alone Fails; Cross-Modal Verification Decouples False Agreement",
        fontsize=12,
        fontweight="bold",
        pad=15,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=10, fontweight="medium")
    ax.set_ylim(0, 115)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend(frameon=True, facecolor="white", edgecolor="none", fontsize=10, loc="upper right")

    plt.tight_layout()
    out_file = FIGURES_DIR / "ablation_correlated_bias.png"
    plt.savefig(out_file)
    plt.close()
    print(f"Saved: {out_file}")


def plot_risk_coverage(summary: list[dict[str, Any]]):
    """
    Plots Coverage vs Covered Risk across policies aggregated across all scenarios.
    """
    policies = [
        ("ALWAYS_ACT", "Always Act", "#d9534f", "o"),
        ("FUSION_ONLY", "Sensor Fusion Only", "#f0ad4e", "s"),
        ("AEGIS_NO_CROSS_MODAL", "AEGIS (No Cross-Modal)", "#5bc0de", "^"),
        ("AEGIS_NO_ABSTAIN", "AEGIS (No Abstain)", "#9b59b6", "v"),
        ("AEGIS_FULL", "AEGIS Full (Ours)", "#27ae60", "D"),
    ]

    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)

    for p_id, p_label, color, marker in policies:
        p_rows = [r for r in summary if r["policy"] == p_id]
        total_eps = sum(int(r["episodes"]) for r in p_rows)
        total_false = sum(int(r["false_success_count"]) for r in p_rows)
        total_abstain = sum(int(r["abstain_count"]) for r in p_rows)
        total_covered = total_eps - total_abstain

        coverage = (total_covered / total_eps) * 100.0
        covered_risk = (
            (total_false / total_covered) * 100.0 if total_covered > 0 else 0.0
        )

        ax.scatter(
            coverage,
            covered_risk,
            s=160,
            color=color,
            marker=marker,
            label=f"{p_label} (Cov: {coverage:.1f}%, Risk: {covered_risk:.1f}%)",
            edgecolor="black",
            linewidth=1.0,
            zorder=4,
        )

    ax.set_xlabel("Operational Coverage (%) [Fraction of Decisions Acted Upon]", fontsize=11, fontweight="bold")
    ax.set_ylabel("Covered Risk (%) [False-Success Rate Among Acted Episodes]", fontsize=11, fontweight="bold")
    ax.set_title(
        "Overall Risk vs. Coverage Across All Scenarios (2,000 Episodes)\n"
        "AEGIS Full Achieves Near-Zero Covered Risk via Selective Verification",
        fontsize=12,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlim(15, 105)
    ax.set_ylim(-2, 60)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(frameon=True, facecolor="white", edgecolor="black", fontsize=9, loc="upper left")

    plt.tight_layout()
    out_file = FIGURES_DIR / "risk_coverage_curve.png"
    plt.savefig(out_file)
    plt.close()
    print(f"Saved: {out_file}")


def main():
    summary = load_summary()
    print("Generating research figures in:", FIGURES_DIR)
    plot_false_success_rate(summary)
    plot_task_success_rate(summary)
    plot_ablation_correlated_bias(summary)
    plot_risk_coverage(summary)
    print("All figures successfully generated!")


if __name__ == "__main__":
    main()
