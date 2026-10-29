"""
NEXVIA AEGIS — Visual Plotting Script for Deep Aerodynamics Benchmark.

Generates a publication-grade 4-panel figure (300 DPI):
1. Cheeseman-Bennett In-Ground-Effect (IGE) Thrust Amplification Curve vs Altitude.
2. Gyroscopic Precession Cross-Axis Reaction Torques vs Body Angular Rates.
3. 4S LiPo Terminal Voltage Sag, Discharge Current, and Dynamic Thrust Derating.
4. 3D Multi-Agent 6-DOF Swarm Trajectories under Combined Aerodynamic Stress.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import matplotlib.pyplot as plt
import numpy as np


def generate_deep_aerodynamics_plot():
    data_path = Path("results/data/deep_aerodynamics_benchmark.json")
    if not data_path.exists():
        raise FileNotFoundError(f"Benchmark data not found at {data_path}")

    with open(data_path) as f:
        data = json.load(f)

    # Style configuration
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "axes.edgecolor": "#334155",
        "axes.linewidth": 1.2,
        "grid.color": "#1e293b",
        "grid.linestyle": "--",
        "grid.alpha": 0.6,
    })

    fig = plt.figure(figsize=(18, 12), facecolor="#090d16")

    # -------------------------------------------------------------
    # Panel 1: In-Ground-Effect (IGE) Thrust Amplification Curve
    # -------------------------------------------------------------
    ax1 = fig.add_subplot(2, 2, 1, facecolor="#0f172a")
    ige_data = data["ige_profile"]
    altitudes = np.array(ige_data["altitudes_m"])
    measured = np.array(ige_data["measured_ige_ratios"])
    theory = np.array(ige_data["theoretical_ige_ratios"])

    ax1.plot(altitudes, theory, color="#38bdf8", linestyle="--", linewidth=2.0, label=r"Cheeseman-Bennett Theory: $\frac{1}{1 - (R/4z)^2}$")
    ax1.plot(altitudes, measured, color="#00f2fe", linewidth=2.8, marker="o", markersize=4, label="MuJoCo 6-DOF Rotor Simulation")
    ax1.axhline(1.0, color="#64748b", linestyle=":", linewidth=1.2, label="OGE Baseline (1.0x)")
    ax1.axvline(0.09 * 4.0, color="#f59e0b", linestyle="-.", linewidth=1.2, label=r"Boundary Transition $z = 4R$")

    ax1.set_title("A. In-Ground-Effect (IGE) Aerodynamics", fontsize=14, fontweight="bold", color="#f8fafc", pad=12)
    ax1.set_xlabel("Altitude Above Floor $z$ (meters)", fontsize=11, color="#cbd5e1")
    ax1.set_ylabel(r"Thrust Amplification Ratio $T_{\mathrm{IGE}} / T_{\mathrm{OGE}}$", fontsize=11, color="#cbd5e1")
    ax1.set_ylim(0.95, 1.25)
    ax1.tick_params(colors="#cbd5e1")
    ax1.grid(True)
    ax1.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=9, loc="upper right")

    # -------------------------------------------------------------
    # Panel 2: Gyroscopic Precession Reaction Torques
    # -------------------------------------------------------------
    ax2 = fig.add_subplot(2, 2, 2, facecolor="#0f172a")
    gyro_data = data["gyroscopic_slalom"]
    t_gyro = np.array(gyro_data["time_s"])
    w_pitch = np.array(gyro_data["omega_pitch_rad_s"])
    tau_x = np.array(gyro_data["tau_gyro_roll_nm"])
    tau_y = np.array(gyro_data["tau_gyro_pitch_nm"])

    ax2.plot(t_gyro, tau_x, color="#ec4899", linewidth=2.4, label=r"Induced Roll Moment $\tau_{\mathrm{gyro}, x} = -H_z \Omega_y$")
    ax2.plot(t_gyro, tau_y, color="#a855f7", linewidth=2.4, label=r"Induced Pitch Moment $\tau_{\mathrm{gyro}, y} = H_z \Omega_x$")

    # Twin axis for angular rate
    ax2_twin = ax2.twinx()
    ax2_twin.plot(t_gyro, w_pitch, color="#f59e0b", linestyle=":", linewidth=1.8, alpha=0.85, label=r"Pitch Rate $\Omega_y$ (rad/s)")
    ax2_twin.set_ylabel("Body Angular Rate (rad/s)", fontsize=11, color="#f59e0b")
    ax2_twin.tick_params(colors="#f59e0b")

    ax2.set_title(r"B. Gyroscopic Precession Moments ($\boldsymbol{\tau}_{\mathrm{gyro}} = -\boldsymbol{\Omega} \times \mathbf{H}_r$)", fontsize=14, fontweight="bold", color="#f8fafc", pad=12)
    ax2.set_xlabel("Simulation Time (seconds)", fontsize=11, color="#cbd5e1")
    ax2.set_ylabel("Gyroscopic Torque (N·m)", fontsize=11, color="#cbd5e1")
    ax2.tick_params(colors="#cbd5e1")
    ax2.grid(True)

    lines_1, labels_1 = ax2.get_legend_handles_labels()
    lines_2, labels_2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines_1 + lines_2, labels_1 + labels_2, facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=9, loc="upper right")

    # -------------------------------------------------------------
    # Panel 3: 4S LiPo Battery Voltage Sag & Thrust Derating
    # -------------------------------------------------------------
    ax3 = fig.add_subplot(2, 2, 3, facecolor="#0f172a")
    bat_data = data["battery_sag"]
    t_bat = np.array(bat_data["time_s"])
    v_ocv = np.array(bat_data["v_ocv_v"])
    v_term = np.array(bat_data["v_terminal_v"])
    current = np.array(bat_data["current_a"])
    t_max = np.array(bat_data["max_thrust_n"])

    ax3.plot(t_bat, v_ocv, color="#10b981", linestyle="--", linewidth=2.0, label=r"Open-Circuit Voltage $V_{\mathrm{ocv}}(\mathrm{SoC})$")
    ax3.plot(t_bat, v_term, color="#34d399", linewidth=2.6, label=r"Terminal Voltage $V_{\mathrm{term}} = V_{\mathrm{ocv}} - I R_{\mathrm{int}}$")
    ax3.fill_between(t_bat, v_term, v_ocv, color="#10b981", alpha=0.15, label="Internal Resistance Voltage Sag")

    ax3_twin = ax3.twinx()
    ax3_twin.plot(t_bat, current, color="#ef4444", linewidth=1.8, linestyle="-.", label=r"Load Current $I_{\mathrm{load}}$ (A)")
    ax3_twin.set_ylabel("Current Draw (Amperes)", fontsize=11, color="#ef4444")
    ax3_twin.tick_params(colors="#ef4444")

    ax3.set_title("C. 4S LiPo Voltage Sag & Load Dynamics", fontsize=14, fontweight="bold", color="#f8fafc", pad=12)
    ax3.set_xlabel("Time (seconds)", fontsize=11, color="#cbd5e1")
    ax3.set_ylabel("Battery Voltage (Volts)", fontsize=11, color="#cbd5e1")
    ax3.tick_params(colors="#cbd5e1")
    ax3.grid(True)

    lines_3a, labels_3a = ax3.get_legend_handles_labels()
    lines_3b, labels_3b = ax3_twin.get_legend_handles_labels()
    ax3.legend(lines_3a + lines_3b, labels_3a + labels_3b, facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=9, loc="lower left")

    # -------------------------------------------------------------
    # Panel 4: 3D Swarm 6-DOF Trajectories under Combined Deep Aero
    # -------------------------------------------------------------
    ax4 = fig.add_subplot(2, 2, 4, projection="3d", facecolor="#0f172a")
    swarm_data = data["swarm_flight"]
    trajectories = swarm_data["trajectories"]
    colors = ["#38bdf8", "#4ade80", "#fbbf24", "#c084fc", "#f87171"]
    labels = ["Leader Drone 0", "Follower Drone 1", "Follower Drone 2", "Follower Drone 3", "Follower Drone 4"]

    for i in range(5):
        traj = np.array(trajectories[i])
        ax4.plot(traj[:, 0], traj[:, 1], traj[:, 2], color=colors[i], linewidth=2.2, label=labels[i])
        # Start and end markers
        ax4.scatter(traj[0, 0], traj[0, 1], traj[0, 2], color=colors[i], s=50, marker="^")
        ax4.scatter(traj[-1, 0], traj[-1, 1], traj[-1, 2], color=colors[i], s=50, marker="o")

    # Target site
    target_pos = swarm_data["target_pos"]
    ax4.scatter(target_pos[0], target_pos[1], target_pos[2], color="#22c55e", s=180, marker="*", label="Target Destination")

    # Static Obstacles
    obstacles = [
        (np.array([0.0, 0.0, 0.8]), 0.45),
        (np.array([1.2, -0.9, 0.7]), 0.35),
        (np.array([-0.9, 1.2, 0.7]), 0.35),
    ]
    u = np.linspace(0, 2 * np.pi, 20)
    v = np.linspace(0, np.pi, 15)
    for center, radius in obstacles:
        x_s = center[0] + radius * np.outer(np.cos(u), np.sin(v))
        y_s = center[1] + radius * np.outer(np.sin(u), np.sin(v))
        z_s = center[2] + radius * np.outer(np.ones(np.size(u)), np.cos(v))
        ax4.plot_surface(x_s, y_s, z_s, color="#ef4444", alpha=0.35, edgecolor="none")

    ax4.set_title("D. 3D Swarm 6-DOF Flight (IGE + Gyro + Sag)", fontsize=14, fontweight="bold", color="#f8fafc", pad=12)
    ax4.set_xlabel("X (m)", fontsize=10, color="#cbd5e1", labelpad=8)
    ax4.set_ylabel("Y (m)", fontsize=10, color="#cbd5e1", labelpad=8)
    ax4.set_zlabel("Z (m)", fontsize=10, color="#cbd5e1", labelpad=8)
    ax4.tick_params(colors="#cbd5e1")
    ax4.view_init(elev=28, azim=-125)
    ax4.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=8, loc="upper left")

    plt.suptitle("NEXVIA AEGIS — Deep Aerodynamics & Electromechanical Physics Certification\nCheeseman-Bennett Ground Effect (IGE), Gyroscopic Precession Dynamics & 4S LiPo Voltage Sag",
                 fontsize=16, fontweight="bold", color="#f8fafc", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.94])

    out_file = Path("results/plots/deep_aerodynamics_benchmark.png")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_file, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    print(f"[OK] Generated 300 DPI plot: {out_file}")

    # Copy to artifact directory
    artifact_dir = Path("/Users/chalermsak/.gemini/antigravity-ide/brain/bfa523f6-4b75-4654-8f2e-65c6b00df558")
    if artifact_dir.exists():
        dest = artifact_dir / "deep_aerodynamics_benchmark.png"
        shutil.copy(out_file, dest)
        print(f"[OK] Copied artifact to: {dest}")


if __name__ == "__main__":
    generate_deep_aerodynamics_plot()
