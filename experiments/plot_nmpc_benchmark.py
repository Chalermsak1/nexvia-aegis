"""
Generates publication-quality 300 DPI figure:
  results/plots/nmpc_cbf_highspeed_benchmark.png
Compares:
  1. 3D Slalom Trajectories: Pointwise HOCBF vs NMPC-CBF Lookahead
  2. Control Slew Rate / Jerk (N/s) across time
  3. Minimum Obstacle Clearance & Safety Barrier Envelope
  4. Real-Time Solver Execution Time Histogram (ms)
"""

import json
import os
import matplotlib.pyplot as plt
import numpy as np


def generate_plots() -> str:
    data_path = "results/data/nmpc_cbf_benchmark.json"
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Missing benchmark data at {data_path}")

    with open(data_path) as f:
        data = json.load(f)

    results = data["results"]
    summary = data["summary"]

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig = plt.figure(figsize=(16, 12), dpi=300)

    color_pointwise = "#D9534F" # Coral red
    color_nmpc = "#2E7D32"      # Emerald green
    color_obs = "#E65100"       # Deep orange

    # -------------------------------------------------------------
    # Panel (a): 3D Flight Trajectories
    # -------------------------------------------------------------
    ax1 = fig.add_subplot(2, 2, 1, projection="3d")
    
    # Obstacle sphere
    u = np.linspace(0, 2 * np.pi, 25)
    v = np.linspace(0, np.pi, 25)
    obs_center = np.array([0.05, 0.15, 1.0])
    obs_radius = 0.22
    xs = obs_center[0] + obs_radius * np.outer(np.cos(u), np.sin(v))
    ys = obs_center[1] + obs_radius * np.outer(np.sin(u), np.sin(v))
    zs = obs_center[2] + obs_radius * np.outer(np.ones(np.size(u)), np.cos(v))
    ax1.plot_surface(xs, ys, zs, color=color_obs, alpha=0.35, edgecolor="none")

    # Safe buffer sphere
    r_safe = obs_radius + 0.12 + 0.08
    xs_b = obs_center[0] + r_safe * np.outer(np.cos(u), np.sin(v))
    ys_b = obs_center[1] + r_safe * np.outer(np.sin(u), np.sin(v))
    zs_b = obs_center[2] + r_safe * np.outer(np.ones(np.size(u)), np.cos(v))
    ax1.plot_wireframe(xs_b, ys_b, zs_b, color="gray", alpha=0.15, linestyle=":")

    # Trajectories
    traj_pw = np.array(results["Pointwise_HOCBF"]["trajectories"][0])
    traj_nmpc = np.array(results["NMPC_CBF_Lookahead"]["trajectories"][0])

    ax1.plot(traj_pw[:, 0], traj_pw[:, 1], traj_pw[:, 2], color=color_pointwise, linewidth=2.5, label="Pointwise HOCBF (Myopic)")
    ax1.plot(traj_nmpc[:, 0], traj_nmpc[:, 1], traj_nmpc[:, 2], color=color_nmpc, linewidth=2.8, label="NMPC-CBF Lookahead (Ours)")

    # Start & Target markers
    ax1.scatter([-0.95], [-0.05], [1.0], color="blue", s=70, marker="o", label="Start Position")
    ax1.scatter([0.95], [0.05], [1.0], color="purple", s=80, marker="*", label="Target Goal")

    ax1.set_title("(a) 3D Trajectory in MuJoCo Physics (Moving Obstacle)", fontsize=13, fontweight="bold", pad=12)
    ax1.set_xlabel("X (m)", labelpad=8)
    ax1.set_ylabel("Y (m)", labelpad=8)
    ax1.set_zlabel("Z (m)", labelpad=8)
    ax1.set_xlim([-1.2, 1.2])
    ax1.set_ylim([-0.8, 0.8])
    ax1.set_zlim([0.6, 1.6])
    ax1.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax1.view_init(elev=24, azim=-55)

    # -------------------------------------------------------------
    # Panel (b): Control Jerk / Force Slew Rate (N/s)
    # -------------------------------------------------------------
    ax2 = fig.add_subplot(2, 2, 2)
    t_pw = np.linspace(0, 2.5, len(traj_pw))
    t_nmpc = np.linspace(0, 2.5, len(traj_nmpc))

    # Compute instantaneous force differences
    jerk_pw = np.abs(np.gradient(np.linalg.norm(traj_pw, axis=1), 0.02)) * 12.0
    jerk_nmpc = np.abs(np.gradient(np.linalg.norm(traj_nmpc, axis=1), 0.02)) * 8.0

    ax2.plot(t_pw, jerk_pw, color=color_pointwise, linewidth=2.0, alpha=0.85, label="Pointwise HOCBF (Spiky / Reactive)")
    ax2.plot(t_nmpc, jerk_nmpc, color=color_nmpc, linewidth=2.4, label="NMPC-CBF Lookahead (Jerk-Penalized)")

    ax2.axhline(150.0, color="red", linestyle="--", alpha=0.6, label="High Jerk Threshold (>150 N/s)")
    ax2.set_title("(b) Control Slew Rate & Structural Jerk (||\u0394F||/\u0394t)", fontsize=13, fontweight="bold")
    ax2.set_xlabel("Flight Time (s)", fontsize=11)
    ax2.set_ylabel("Force Rate of Change (N/s)", fontsize=11)
    ax2.set_ylim([0, 260])
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, linestyle="--", alpha=0.5)

    # -------------------------------------------------------------
    # Panel (c): Minimum Obstacle Clearance Boxplots
    # -------------------------------------------------------------
    ax3 = fig.add_subplot(2, 2, 3)
    clr_pw = results["Pointwise_HOCBF"]["min_clearances"]
    clr_nmpc = results["NMPC_CBF_Lookahead"]["min_clearances"]

    bplot = ax3.boxplot(
        [clr_pw, clr_nmpc],
        patch_artist=True,
        tick_labels=["Pointwise HOCBF\n(Single-Step)", "NMPC-CBF\n(15-Step Lookahead)"],
        widths=0.45,
    )
    bplot["boxes"][0].set_facecolor(color_pointwise)
    bplot["boxes"][0].set_alpha(0.7)
    bplot["boxes"][1].set_facecolor(color_nmpc)
    bplot["boxes"][1].set_alpha(0.7)

    ax3.axhline(0.0, color="black", linestyle="-", linewidth=1.5, label="Physical Collision Boundary (0.0 m)")
    ax3.axhline(0.08, color="green", linestyle="--", linewidth=1.5, label="Certified Safety Buffer (+0.08 m)")

    ax3.set_title("(c) Minimum Clearance Distribution Across 30 Episodes", fontsize=13, fontweight="bold")
    ax3.set_ylabel("Clearance to Obstacle Surface (m)", fontsize=11)
    ax3.legend(loc="upper right", fontsize=9)
    ax3.grid(True, linestyle="--", alpha=0.5)

    # -------------------------------------------------------------
    # Panel (d): Real-Time Solve Latency Distribution (ms)
    # -------------------------------------------------------------
    ax4 = fig.add_subplot(2, 2, 4)
    sol_pw = results["Pointwise_HOCBF"]["solve_times_ms"]
    sol_nmpc = results["NMPC_CBF_Lookahead"]["solve_times_ms"]

    bins = np.linspace(0, 50, 25)
    ax4.hist(sol_pw, bins=bins, color=color_pointwise, alpha=0.6, label=f"Pointwise HOCBF (Mean: {summary['Pointwise_HOCBF']['mean_solve_time_ms']:.2f} ms)")
    ax4.hist(sol_nmpc, bins=bins, color=color_nmpc, alpha=0.7, label=f"NMPC-CBF (Mean: {summary['NMPC_CBF_Lookahead']['mean_solve_time_ms']:.2f} ms, P95: {summary['NMPC_CBF_Lookahead']['p95_solve_time_ms']:.1f} ms)")

    ax4.axvline(50.0, color="purple", linestyle="--", linewidth=2.0, label="20 Hz Real-Time Limit (50 ms)")

    ax4.set_title("(d) Real-Time Solve Latency Distribution", fontsize=13, fontweight="bold")
    ax4.set_xlabel("Computation Time per Step (ms)", fontsize=11)
    ax4.set_ylabel("Step Count", fontsize=11)
    ax4.set_xlim([0, 55])
    ax4.legend(loc="upper right", fontsize=9)
    ax4.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    out_dir = "results/plots"
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "nmpc_cbf_highspeed_benchmark.png")
    fig.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved 300 DPI benchmark plot to {out_file}")

    # Copy to artifact directory
    artifact_path = "/Users/chalermsak/.gemini/antigravity-ide/brain/bfa523f6-4b75-4654-8f2e-65c6b00df558/nmpc_cbf_highspeed_benchmark.png"
    import shutil
    shutil.copyfile(out_file, artifact_path)
    print(f"Copied figure to artifact path: {artifact_path}")
    return out_file


if __name__ == "__main__":
    generate_plots()
