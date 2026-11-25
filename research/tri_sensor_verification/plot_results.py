"""
Publication-Grade Plotting Suite for My Tri-Sensor Maze Experiment.

Generates 4 high-resolution (300 DPI) figures directly from the saved run logs:
  1. fig1_rmse_across_all_scenarios.png : RMSE comparison across all 20 scenarios (3 Arms)
  2. fig2_maze_trajectories_showcase.png: Actual 2D maze exploration paths under faults
  3. fig3_drift_cusum_quarantine.png    : Time-series of S1 Heavy Drift + CUSUM + Quarantine
  4. fig4_sensor_fault_heatmap.png      : 3 Sensors x 6 Fault Types Matrix (RMSE & Latency)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any, Dict, List
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _load_latest_run_dir(run_dir: str | None = None) -> Path:
    if run_dir:
        return Path(run_dir)
    latest_file = Path("research/tri_sensor_verification/logs/LATEST_RUN.txt")
    return Path(latest_file.read_text(encoding="utf-8").strip())


def generate_all_plots(run_dir: str | None = None) -> List[Path]:
    root = _load_latest_run_dir(run_dir)
    fig_dir = root / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads((root / "dashboard_payload.json").read_text(encoding="utf-8"))
    summaries: List[Dict[str, Any]] = payload["summaries"]
    showcase: Dict[str, Dict[str, List[Dict[str, Any]]]] = payload["showcase"]
    pillars = payload["pillars"]

    generated: List[Path] = []

    # ------------------------------------------------------------------
    # Figure 1: RMSE Comparison Across All 20 Scenarios
    # ------------------------------------------------------------------
    scen_ids = list(dict.fromkeys(r["scenario_id"] for r in summaries))
    arms = ["NAIVE_AVG", "TWO_SENSOR_MIN_SIGMA", "TRI_SENSOR_VERIFIER"]
    arm_labels = ["Naive Avg (No Check)", "2-Sensor Min-Sigma (sensing.py)", "Tri-Sensor Verifier (Yours)"]
    arm_colors = ["#e74c3c", "#f39c12", "#10b981"]

    fig, ax = plt.subplots(figsize=(16, 6.5), dpi=300)
    x = np.arange(len(scen_ids))
    width = 0.27
    for i, (arm, label, col) in enumerate(zip(arms, arm_labels, arm_colors)):
        vals = [
            next(r["position_rmse_m"] for r in summaries if r["scenario_id"] == sid and r["arm"] == arm)
            for sid in scen_ids
        ]
        ax.bar(x + (i - 1) * width, vals, width, label=label, color=col, edgecolor="black", linewidth=0.5)

    ax.set_ylabel("Display Position RMSE (m) — Lower is Better", fontsize=11, fontweight="bold")
    ax.set_title("Tri-Sensor Self-Verification Benchmark: Display Position RMSE Across All 20 Maze Scenarios", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([s[3:] for s in scen_ids], rotation=35, ha="right", fontsize=8.5)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, axis="y", linestyle="--", alpha=0.45)
    plt.tight_layout()
    p1 = fig_dir / "fig1_rmse_across_all_scenarios.png"
    fig.savefig(p1)
    plt.close(fig)
    generated.append(p1)

    # ------------------------------------------------------------------
    # Figure 2: Maze Exploration Trajectories Showcase (2x3 Grid)
    # ------------------------------------------------------------------
    selected = [
        ("00_NOMINAL_ALL_HEALTHY", "Nominal (All 3 Healthy)"),
        ("04_S1_VIO_HEAVY_DRIFT", "S1_VIO Heavy Drift"),
        ("14_S2_LIDAR_RETIMESTAMPED_FREEZE", "S2_LIDAR Retimestamped Freeze"),
        ("09_S3_UWB_SUDDEN_BIAS", "S3_UWB Sudden Bias (+1.4m)"),
        ("10_S1_VIO_OUTLIER_BURSTS", "S1_VIO Outlier Bursts (30%)"),
        ("19_DUAL_S1_DRIFT_S2_FREEZE", "Dual Failure (Fail-Closed Stop)"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(16, 10), dpi=300)
    for ax, (sid, title) in zip(axes.flat, selected):
        for px, py, pr in pillars:
            ax.add_patch(plt.Circle((px, py), pr, color="#475569", alpha=0.8))

        naive_rows = showcase[sid]["NAIVE_AVG"]
        tri_rows = showcase[sid]["TRI_SENSOR_VERIFIER"]

        nx = [r["true_x"] for r in naive_rows]
        ny = [r["true_y"] for r in naive_rows]
        tx = [r["true_x"] for r in tri_rows]
        ty = [r["true_y"] for r in tri_rows]
        dx = [r["display_x"] for r in tri_rows if r["display_x"] != ""]
        dy = [r["display_y"] for r in tri_rows if r["display_y"] != ""]

        ax.plot(nx, ny, color="#ef4444", ls="--", lw=1.6, alpha=0.75, label="Naive True Path")
        ax.plot(tx, ty, color="#0ea5e9", ls="-", lw=2.4, label="Tri-Verifier True Path")
        ax.scatter(dx, dy, color="#10b981", s=14, alpha=0.85, zorder=4, label="Trusted Display Output")
        ax.plot(tx[0], ty[0], "ko", markersize=6)

        ax.set_xlim(-5.0, 5.0)
        ax.set_ylim(-5.0, 5.0)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.grid(True, ls=":", alpha=0.5)
        ax.legend(loc="upper left", fontsize=7.5)

    fig.suptitle("3D Subterranean Maze Trajectories: Naive Fusion vs. Tri-Sensor Self-Verification", fontsize=14, fontweight="bold")
    plt.tight_layout()
    p2 = fig_dir / "fig2_maze_trajectories_showcase.png"
    fig.savefig(p2)
    plt.close(fig)
    generated.append(p2)

    # ------------------------------------------------------------------
    # Figure 3: Time-Series of S1 Heavy Drift, Page CUSUM & Quarantine Exclusion
    # ------------------------------------------------------------------
    rows = showcase["04_S1_VIO_HEAVY_DRIFT"]["TRI_SENSOR_VERIFIER"]
    steps = [r["step"] for r in rows]
    true_x = [r["true_x"] for r in rows]
    s1_x = [r["s1_x"] for r in rows]
    s2_x = [r["s2_x"] for r in rows]
    s3_x = [r["s3_x"] for r in rows]
    disp_x = [r["display_x"] for r in rows]
    c12 = [r["cusum_s1_s2"] for r in rows]
    c23 = [r["cusum_s2_s3"] for r in rows]
    c13 = [r["cusum_s1_s3"] for r in rows]
    quar_steps = [r["step"] for r in rows if "S1_VIO" in r["quarantined_sensors"]]
    q_start = quar_steps[0] if quar_steps else None

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), dpi=300, sharex=True)
    ax1.plot(steps, true_x, "k-", lw=2.6, label="Ground Truth X (Hidden)")
    ax1.plot(steps, s1_x, "r--", lw=1.8, alpha=0.85, label="S1_VIO (Drifting — EXCLUDED after Quarantine)")
    ax1.plot(steps, s2_x, color="#3b82f6", lw=1.3, alpha=0.75, label="S2_LIDAR (Healthy)")
    ax1.plot(steps, s3_x, color="#8b5cf6", lw=1.3, alpha=0.75, label="S3_UWB (Healthy)")
    ax1.plot(steps, disp_x, color="#10b981", lw=2.4, ls="-.", label="Trusted Display & Control Output")
    ax1.axvline(12, color="#f59e0b", ls=":", lw=1.8, label="Fault Injection Start (Step 12)")
    if q_start is not None:
        ax1.axvline(q_start, color="#dc2626", ls="--", lw=1.8, label=f"S1 Quarantined & Excluded (Step {q_start})")
        ax1.axvspan(q_start, max(steps), color="#fee2e2", alpha=0.35)
    ax1.set_ylabel("X Position (m)", fontsize=11, fontweight="bold")
    ax1.set_title("Live Fault Isolation: S1_VIO Heavy Drift Rejected from Display & Control", fontsize=13, fontweight="bold")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, ls="--", alpha=0.45)

    ax2.plot(steps, c12, color="#ef4444", lw=2.0, label="Page CUSUM (S1 vs S2)")
    ax2.plot(steps, c13, color="#f97316", lw=2.0, ls="--", label="Page CUSUM (S1 vs S3)")
    ax2.plot(steps, c23, color="#10b981", lw=2.2, label="Page CUSUM (S2 vs S3 — Healthy Pair)")
    ax2.axhline(4.0, color="black", ls=":", lw=1.6, label="CUSUM Alarm Threshold (h = 4.0)")
    ax2.set_xlabel("Exploration Step", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Page CUSUM Statistic", fontsize=11, fontweight="bold")
    ax2.set_title("Pairwise Deterministic Page CUSUM Cross-Check (S1 disagrees with BOTH S2 & S3)", fontsize=12, fontweight="bold")
    ax2.legend(loc="upper left", fontsize=9)
    ax2.grid(True, ls="--", alpha=0.45)

    plt.tight_layout()
    p3 = fig_dir / "fig3_drift_cusum_quarantine.png"
    fig.savefig(p3)
    plt.close(fig)
    generated.append(p3)

    # ------------------------------------------------------------------
    # Figure 4: 3 Sensors x 6 Fault Types Matrix (RMSE + Latency)
    # ------------------------------------------------------------------
    sensors = ["S1_VIO", "S2_LIDAR", "S3_UWB"]
    fault_types = [
        "GRADUAL_DRIFT",
        "HEAVY_DRIFT",
        "SUDDEN_BIAS",
        "OUTLIER_BURSTS",
        "RETIMESTAMPED_FREEZE",
        "SENSOR_BLACKOUT",
    ]
    mat_rmse = np.zeros((len(sensors), len(fault_types)))
    mat_lat = np.zeros((len(sensors), len(fault_types)))

    for i, s in enumerate(sensors):
        for j, ft in enumerate(fault_types):
            row = next(
                r for r in summaries
                if r["target_sensor"] == s and r["fault_category"] == ft and r["arm"] == "TRI_SENSOR_VERIFIER"
            )
            mat_rmse[i, j] = row["position_rmse_m"]
            mat_lat[i, j] = row["detection_latency_steps"] if row["detection_latency_steps"] is not None else -1

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5), dpi=300)
    im1 = ax1.imshow(mat_rmse, cmap="YlGn", vmin=0.0, vmax=0.15, aspect="auto")
    ax1.set_xticks(range(len(fault_types)))
    ax1.set_xticklabels(fault_types, rotation=25, ha="right", fontsize=9)
    ax1.set_yticks(range(len(sensors)))
    ax1.set_yticklabels(sensors, fontsize=10, fontweight="bold")
    ax1.set_title("Tri-Sensor Verifier: Display RMSE (m)\n(All Sensors x All Fault Modes)", fontsize=11, fontweight="bold")
    for i in range(len(sensors)):
        for j in range(len(fault_types)):
            ax1.text(j, i, f"{mat_rmse[i, j]:.3f}m", ha="center", va="center", fontweight="bold", color="black")
    fig.colorbar(im1, ax=ax1, shrink=0.8)

    im2 = ax2.imshow(mat_lat, cmap="Blues", vmin=0, vmax=6, aspect="auto")
    ax2.set_xticks(range(len(fault_types)))
    ax2.set_xticklabels(fault_types, rotation=25, ha="right", fontsize=9)
    ax2.set_yticks(range(len(sensors)))
    ax2.set_yticklabels(sensors, fontsize=10, fontweight="bold")
    ax2.set_title("Detection & Quarantine Latency (Steps)\n(0 = Instant Rejection on Fault Step)", fontsize=11, fontweight="bold")
    for i in range(len(sensors)):
        for j in range(len(fault_types)):
            val = int(mat_lat[i, j])
            txt_color = "white" if val >= 4 else "black"
            unit = "step" if val == 1 else "steps"
            ax2.text(j, i, f"{val} {unit}", ha="center", va="center", fontweight="bold", color=txt_color)
    fig.colorbar(im2, ax=ax2, shrink=0.8)

    plt.tight_layout()
    p4 = fig_dir / "fig4_sensor_fault_heatmap.png"
    fig.savefig(p4)
    plt.close(fig)
    generated.append(p4)

    for p in generated:
        print(f"Saved plot: {p}")
    return generated


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    generate_all_plots(arg)
