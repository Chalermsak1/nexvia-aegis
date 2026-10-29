"""
NEXVIA AEGIS — 300 DPI Publication Benchmark Plot for Active Vision & LiDAR SLAM under Occlusion.
"""

from __future__ import annotations

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def generate_benchmark_plot():
    json_path = Path("results/data/vision_occlusion_slam_benchmark.json")
    if not json_path.exists():
        raise FileNotFoundError(f"Missing benchmark data at {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    episodes = data["episodes"]

    plt.style.use("dark_background")
    fig = plt.figure(figsize=(16, 12), dpi=300)

    # 4 Subplots: (A) 3D Trajectory & Occlusion, (B) Uncertainty Evolution, (C) Active Gaze & Speed, (D) Metrics Comparison
    ax1 = fig.add_subplot(2, 2, 1, projection="3d")
    ax2 = fig.add_subplot(2, 2, 2)
    ax3 = fig.add_subplot(2, 2, 3)
    ax4 = fig.add_subplot(2, 2, 4)

    colors = {
        "blind": "#ef4444",         # Red
        "passive": "#f59e0b",       # Amber
        "aegis_active": "#10b981",  # Emerald Green
    }

    # -------------------------------------------------------------
    # Panel A: 3D Spatial Trajectory & Occluded Corridor
    # -------------------------------------------------------------
    ax1.set_title("(A) 3D Trajectory & Line-of-Sight Occlusion", fontsize=12, fontweight="bold", pad=12, color="#38bdf8")

    # Draw Obstacle 1 (Foreground Pillar)
    u = np.linspace(0, 2 * np.pi, 25)
    v = np.linspace(0, np.pi, 25)
    x_obs1 = 0.2 + 0.38 * np.outer(np.cos(u), np.sin(v))
    y_obs1 = 0.22 + 0.38 * np.outer(np.sin(u), np.sin(v))
    z_obs1 = 1.0 + 0.38 * np.outer(np.ones(np.size(u)), np.cos(v))
    ax1.plot_surface(x_obs1, y_obs1, z_obs1, color="#64748b", alpha=0.55, edgecolor="none")

    # Draw Obstacle 3 (Flanking Pillar)
    x_obs3 = 0.2 + 0.38 * np.outer(np.cos(u), np.sin(v))
    y_obs3 = -0.60 + 0.38 * np.outer(np.sin(u), np.sin(v))
    z_obs3 = 1.0 + 0.38 * np.outer(np.ones(np.size(u)), np.cos(v))
    ax1.plot_surface(x_obs3, y_obs3, z_obs3, color="#64748b", alpha=0.55, edgecolor="none")

    # Draw Moving Obstacle 2
    x_obs2 = 0.45 + 0.28 * np.outer(np.cos(u), np.sin(v))
    y_obs2 = 0.05 + 0.28 * np.outer(np.sin(u), np.sin(v))
    z_obs2 = 1.0 + 0.28 * np.outer(np.ones(np.size(u)), np.cos(v))
    ax1.plot_surface(x_obs2, y_obs2, z_obs2, color="#ec4899", alpha=0.75, edgecolor="none")

    # Draw Trajectories
    for c_name, c_color in colors.items():
        traj = np.array(episodes[c_name][0]["trajectory"])
        label = "Blind (Crash)" if c_name == "blind" else ("Passive Vision" if c_name == "passive" else "AEGIS Active Vision")
        ax1.plot(traj[:, 0], traj[:, 1], traj[:, 2], color=c_color, lw=2.5, label=label)

    # Plot Start and Target markers
    ax1.scatter([-1.2], [0.0], [1.0], color="#38bdf8", s=90, marker="o", label="Start Point")
    ax1.scatter([1.6], [0.0], [1.0], color="#22c55e", s=110, marker="*", label="Target Goal")

    ax1.set_xlabel("X (m)", fontsize=10, labelpad=6)
    ax1.set_ylabel("Y (m)", fontsize=10, labelpad=6)
    ax1.set_zlabel("Z (m)", fontsize=10, labelpad=6)
    ax1.set_xlim(-1.5, 1.8)
    ax1.set_ylim(-1.0, 1.0)
    ax1.set_zlim(0.2, 1.8)
    ax1.view_init(elev=28, azim=-62)
    ax1.legend(loc="upper left", fontsize=8, framealpha=0.6)

    # -------------------------------------------------------------
    # Panel B: Spatial Uncertainty Ellipsoid Evolution (UKF)
    # -------------------------------------------------------------
    ax2.set_title("(B) UKF Spatial Uncertainty Evolution $\sigma_{\max}(\mathbf{P})$", fontsize=12, fontweight="bold", pad=10, color="#38bdf8")

    ep_act = episodes["aegis_active"][0]
    ep_pas = episodes["passive"][0]
    ep_bli = episodes["blind"][0]

    steps = np.arange(len(ep_act["uncertainty_history"]))
    ax2.plot(steps, ep_bli["uncertainty_history"], color=colors["blind"], lw=2.2, linestyle="--", label="Blind (Stale Map $\sigma = 0.20\,$m)")
    ax2.plot(steps, ep_pas["uncertainty_history"], color=colors["passive"], lw=2.2, label="Passive Vision (Forward Camera)")
    ax2.plot(steps, ep_act["uncertainty_history"], color=colors["aegis_active"], lw=2.6, label="AEGIS Active POMDP Gaze")

    # Safety threshold line
    ax2.axhline(y=0.08, color="#f43f5e", linestyle=":", lw=1.8, label="Safety Threshold (0.08 m)")
    ax2.set_xlabel("Control Step (50 Hz)", fontsize=10)
    ax2.set_ylabel("Maximum Position Std $\sigma_{\max}$ (m)", fontsize=10)
    ax2.set_ylim(0.0, 0.45)
    ax2.grid(True, linestyle="--", alpha=0.3)
    ax2.legend(loc="upper right", fontsize=8.5, framealpha=0.6)

    # -------------------------------------------------------------
    # Panel C: Active Gaze Saccade & Adaptive Speed Profile
    # -------------------------------------------------------------
    ax3.set_title("(C) Active Gaze Saccade & Air-Brake Profile", fontsize=12, fontweight="bold", pad=10, color="#38bdf8")

    color_yaw = "#00e5ff"
    color_spd = "#ec4899"

    ax3.plot(steps, ep_act["gaze_yaw_history"], color=color_yaw, lw=2.2, label="Body Yaw / Gaze Angle $\psi$ (deg)")
    ax3.set_xlabel("Control Step (50 Hz)", fontsize=10)
    ax3.set_ylabel("Gaze Yaw Angle (deg)", fontsize=10, color=color_yaw)
    ax3.tick_params(axis="y", labelcolor=color_yaw)
    ax3.set_ylim(-35, 35)
    ax3.grid(True, linestyle="--", alpha=0.3)

    ax3_twin = ax3.twinx()
    ax3_twin.plot(steps, ep_act["speed_history"], color=color_spd, lw=2.2, linestyle="-.", label="Translational Speed (m/s)")
    ax3_twin.set_ylabel("Speed (m/s)", fontsize=10, color=color_spd)
    ax3_twin.tick_params(axis="y", labelcolor=color_spd)
    ax3_twin.set_ylim(0.0, 1.4)

    # Combine legends
    lines_1, labels_1 = ax3.get_legend_handles_labels()
    lines_2, labels_2 = ax3_twin.get_legend_handles_labels()
    ax3.legend(lines_1 + lines_2, labels_1 + labels_2, loc="upper right", fontsize=8.5, framealpha=0.6)

    # -------------------------------------------------------------
    # Panel D: Empirical Performance & Safety Comparison
    # -------------------------------------------------------------
    ax4.set_title("(D) Quantitative Comparison (15 Test Episodes)", fontsize=12, fontweight="bold", pad=10, color="#38bdf8")

    cat_labels = ["Collision Rate\n(%)", "Min Clearance\n(x10 cm)", "Final Uncertainty\n(x10 cm)"]
    x = np.arange(len(cat_labels))
    width = 0.26

    blind_vals = [
        summary["blind"]["collision_rate_pct"],
        summary["blind"]["mean_min_clearance_m"] * 10.0,
        summary["blind"]["mean_final_uncertainty_std"] * 10.0,
    ]
    passive_vals = [
        summary["passive"]["collision_rate_pct"],
        summary["passive"]["mean_min_clearance_m"] * 10.0,
        summary["passive"]["mean_final_uncertainty_std"] * 10.0,
    ]
    active_vals = [
        summary["aegis_active"]["collision_rate_pct"],
        summary["aegis_active"]["mean_min_clearance_m"] * 10.0,
        summary["aegis_active"]["mean_final_uncertainty_std"] * 10.0,
    ]

    ax4.bar(x - width, blind_vals, width, label="Blind Baseline", color=colors["blind"], alpha=0.85)
    ax4.bar(x, passive_vals, width, label="Passive Vision", color=colors["passive"], alpha=0.85)
    ax4.bar(x + width, active_vals, width, label="AEGIS Active POMDP", color=colors["aegis_active"], alpha=0.85)

    ax4.set_xticks(x)
    ax4.set_xticklabels(cat_labels, fontsize=9.5)
    ax4.set_ylabel("Metric Value", fontsize=10)
    ax4.grid(True, linestyle="--", alpha=0.3)
    ax4.legend(loc="upper right", fontsize=8.5, framealpha=0.6)

    plt.tight_layout()
    out_file = Path("results/plots/vision_occlusion_slam_benchmark.png")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_file, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    print(f"[+] High-resolution plot successfully saved to {out_file}")


if __name__ == "__main__":
    generate_benchmark_plot()
