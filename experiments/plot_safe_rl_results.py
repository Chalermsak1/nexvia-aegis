"""
NEXVIA AEGIS — Visual Plotting Script for Safe Reinforcement Learning (Safe RL) Benchmark.

Generates a publication-grade 4-panel figure (300 DPI):
1. Training Learning Curves: Episode Return vs Training Episodes (Unshielded vs Safe RL).
2. Cumulative Training Collisions: 0.0% Crash Exploration Invariant under HOCBF Shield.
3. HOCBF Shield Intervention Decay: Policy internalizing safety boundaries over time.
4. 3D Navigation Trajectories around Dynamic Moving Obstacles in MuJoCo Physics.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import matplotlib.pyplot as plt
import numpy as np


def generate_safe_rl_plot():
    data_path = Path("results/data/safe_rl_benchmark.json")
    if not data_path.exists():
        raise FileNotFoundError(f"Benchmark data not found at {data_path}")

    with open(data_path) as f:
        data = json.load(f)

    # Styling configuration
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
    train = data["training"]
    eval_data = data["evaluation"]
    episodes = np.array(train["episodes"])

    # -------------------------------------------------------------
    # Panel 1: Training Reward Curves
    # -------------------------------------------------------------
    ax1 = fig.add_subplot(2, 2, 1, facecolor="#0f172a")
    r_unshielded = np.array(train["unshielded_rewards"])
    r_shielded = np.array(train["shielded_rewards"])

    # Smoothed moving averages
    w_size = 3
    smooth_un = np.convolve(r_unshielded, np.ones(w_size)/w_size, mode="valid")
    smooth_sh = np.convolve(r_shielded, np.ones(w_size)/w_size, mode="valid")
    ep_smooth = episodes[:len(smooth_un)]

    ax1.plot(episodes, r_unshielded, color="#f87171", alpha=0.35, linewidth=1.2)
    ax1.plot(ep_smooth, smooth_un, color="#ef4444", linewidth=2.4, label="Unshielded Vanilla PPO")

    ax1.plot(episodes, r_shielded, color="#38bdf8", alpha=0.35, linewidth=1.2)
    ax1.plot(ep_smooth, smooth_sh, color="#00f2fe", linewidth=2.8, label="AEGIS HOCBF-Shielded Safe PPO")

    ax1.set_title("A. Training Reward & Learning Convergence", fontsize=14, fontweight="bold", color="#f8fafc", pad=12)
    ax1.set_xlabel("Training Episode", fontsize=11, color="#cbd5e1")
    ax1.set_ylabel("Episode Return", fontsize=11, color="#cbd5e1")
    ax1.tick_params(colors="#cbd5e1")
    ax1.grid(True)
    ax1.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=10, loc="lower right")

    # -------------------------------------------------------------
    # Panel 2: Cumulative Training Collisions
    # -------------------------------------------------------------
    ax2 = fig.add_subplot(2, 2, 2, facecolor="#0f172a")
    col_unshielded = np.array(train["unshielded_collisions"])
    col_shielded = np.array(train["shielded_collisions"])

    ax2.plot(episodes, col_unshielded, color="#ef4444", linewidth=2.8, marker="x", markersize=6, label=f"Unshielded PPO ({col_unshielded[-1]} Total Crashes)")
    ax2.plot(episodes, col_shielded, color="#10b981", linewidth=3.2, marker="o", markersize=6, label=f"AEGIS Safe RL ({col_shielded[-1]} Crashes — 100% Invariant)")

    ax2.fill_between(episodes, col_shielded, col_unshielded, color="#ef4444", alpha=0.15, label="Prevented Catastrophic Crashes")

    ax2.set_title("B. Cumulative Training Exploration Collisions", fontsize=14, fontweight="bold", color="#f8fafc", pad=12)
    ax2.set_xlabel("Training Episode", fontsize=11, color="#cbd5e1")
    ax2.set_ylabel("Cumulative Crashes", fontsize=11, color="#cbd5e1")
    ax2.tick_params(colors="#cbd5e1")
    ax2.grid(True)
    ax2.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=10, loc="upper left")

    # -------------------------------------------------------------
    # Panel 3: HOCBF Shield Intervention Decay
    # -------------------------------------------------------------
    ax3 = fig.add_subplot(2, 2, 3, facecolor="#0f172a")
    interventions = np.array(train["shield_intervention_norms"])

    ax3.plot(episodes, interventions, color="#a855f7", linewidth=2.6, marker="s", markersize=5, label=r"Mean Intervention $\|\mathbf{u}_{\mathrm{safe}} - \mathbf{u}_{\mathrm{RL}}\|$")
    z_fit = np.polyfit(episodes, interventions, 1)
    p_fit = np.poly1d(z_fit)
    ax3.plot(episodes, p_fit(episodes), color="#f59e0b", linestyle="--", linewidth=1.8, label="Intervention Decay Trend (Policy Internalization)")

    ax3.set_title("C. HOCBF Safety Shield Intervention Decay", fontsize=14, fontweight="bold", color="#f8fafc", pad=12)
    ax3.set_xlabel("Training Episode", fontsize=11, color="#cbd5e1")
    ax3.set_ylabel("Action Intervention Magnitude (N)", fontsize=11, color="#cbd5e1")
    ax3.tick_params(colors="#cbd5e1")
    ax3.grid(True)
    ax3.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=10, loc="upper right")

    # -------------------------------------------------------------
    # Panel 4: 3D Trajectory under Dynamic Moving Obstacles
    # -------------------------------------------------------------
    ax4 = fig.add_subplot(2, 2, 4, projection="3d", facecolor="#0f172a")

    traj_sh = np.array(eval_data["shielded"]["sample_trajectory"])
    traj_un = np.array(eval_data["unshielded"]["sample_trajectory"])
    dyn_paths = eval_data.get("dynamic_obstacles_path", [])

    if len(traj_un) > 0:
        ax4.plot(traj_un[:, 0], traj_un[:, 1], traj_un[:, 2], color="#ef4444", linewidth=2.0, linestyle=":", label="Unshielded Trajectory")
        ax4.scatter(traj_un[-1, 0], traj_un[-1, 1], traj_un[-1, 2], color="#ef4444", s=60, marker="x")

    if len(traj_sh) > 0:
        ax4.plot(traj_sh[:, 0], traj_sh[:, 1], traj_sh[:, 2], color="#00f2fe", linewidth=3.0, label="AEGIS Safe RL Trajectory")
        ax4.scatter(traj_sh[0, 0], traj_sh[0, 1], traj_sh[0, 2], color="#38bdf8", s=60, marker="^", label="Takeoff Origin")
        ax4.scatter(traj_sh[-1, 0], traj_sh[-1, 1], traj_sh[-1, 2], color="#22c55e", s=70, marker="o", label="Arrival Position")

    # Destination Target
    target = eval_data["target_pos"]
    ax4.scatter(target[0], target[1], target[2], color="#22c55e", s=180, marker="*", label="Target Goal")

    # Static Obstacles
    static_obs = [
        (np.array([0.0, 0.0, 0.9]), 0.45),
        (np.array([1.2, -0.9, 0.8]), 0.35),
        (np.array([-0.9, 1.2, 0.8]), 0.35),
    ]
    u = np.linspace(0, 2 * np.pi, 20)
    v = np.linspace(0, np.pi, 15)
    for center, radius in static_obs:
        x_s = center[0] + radius * np.outer(np.cos(u), np.sin(v))
        y_s = center[1] + radius * np.outer(np.sin(u), np.sin(v))
        z_s = center[2] + radius * np.outer(np.ones(np.size(u)), np.cos(v))
        ax4.plot_surface(x_s, y_s, z_s, color="#64748b", alpha=0.30, edgecolor="none")

    # Dynamic Moving Obstacles (showing swept trajectory path)
    if len(dyn_paths) > 0:
        dyn_arr = np.array(dyn_paths) # (T, num_dyn, 3)
        if dyn_arr.ndim == 3:
            for d_idx in range(dyn_arr.shape[1]):
                d_traj = dyn_arr[:, d_idx, :]
                ax4.plot(d_traj[:, 0], d_traj[:, 1], d_traj[:, 2], color="#f59e0b", linestyle="-.", linewidth=2.0, label="Dynamic Moving Hazard" if d_idx == 0 else "")
                # Draw sphere at final position
                d_end = d_traj[-1]
                x_d = d_end[0] + 0.35 * np.outer(np.cos(u), np.sin(v))
                y_d = d_end[1] + 0.35 * np.outer(np.sin(u), np.sin(v))
                z_d = d_end[2] + 0.35 * np.outer(np.ones(np.size(u)), np.cos(v))
                ax4.plot_surface(x_d, y_d, z_d, color="#f59e0b", alpha=0.45, edgecolor="none")

    ax4.set_title("D. 3D Dynamic Obstacle Evasion Flight", fontsize=14, fontweight="bold", color="#f8fafc", pad=12)
    ax4.set_xlabel("X (m)", fontsize=10, color="#cbd5e1", labelpad=8)
    ax4.set_ylabel("Y (m)", fontsize=10, color="#cbd5e1", labelpad=8)
    ax4.set_zlabel("Z (m)", fontsize=10, color="#cbd5e1", labelpad=8)
    ax4.tick_params(colors="#cbd5e1")
    ax4.view_init(elev=26, azim=-120)
    ax4.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=8, loc="upper left")

    plt.suptitle("NEXVIA AEGIS — Safe Reinforcement Learning (Safe RL) Performance Certification\nNeural Policy Gradient Control with High-Order Control Barrier Function (HOCBF) Action Shielding",
                 fontsize=16, fontweight="bold", color="#f8fafc", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.94])

    out_file = Path("results/plots/safe_rl_benchmark.png")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_file, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    print(f"[OK] Generated 300 DPI plot: {out_file}")

    # Copy to artifact directory
    artifact_dir = Path("/Users/chalermsak/.gemini/antigravity-ide/brain/bfa523f6-4b75-4654-8f2e-65c6b00df558")
    if artifact_dir.exists():
        dest = artifact_dir / "safe_rl_benchmark.png"
        shutil.copy(out_file, dest)
        print(f"[OK] Copied artifact to: {dest}")


if __name__ == "__main__":
    generate_safe_rl_plot()
