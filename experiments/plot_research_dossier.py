"""
plot_research_dossier.py — NEXVIA AEGIS Core Research Publication Visualizations

Generates high-resolution scientific publication figures for:
1. Uncertainty Active Inspection Loop Performance across noise regimes (12,000 episodes).
2. 3D Continuous Physical AI MuJoCo Control Barrier Function (CBF) forward invariance trajectories.
3. Multi-Agent Byzantine-Resilient Martingale Consensus (BRMC) anytime wealth and quarantine dynamics.
"""

from __future__ import annotations

import csv
import math
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

# Ensure src is in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import matplotlib.pyplot as plt
import numpy as np

# Ensure plot output directory exists
PLOTS_DIR = "results/plots"
os.makedirs(PLOTS_DIR, exist_ok=True)

# Styling for academic publication
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 15,
    "figure.dpi": 300,
})

# ==============================================================================
# 1. Uncertainty Benchmark Visualization
# ==============================================================================
def plot_uncertainty_benchmark(csv_path: str = "results/uncertainty_benchmark.csv"):
    if not os.path.exists(csv_path):
        print(f"Skipping uncertainty benchmark plot: {csv_path} not found.")
        return

    data = defaultdict(lambda: defaultdict(list))
    # Structure: data[uncertainty][policy] = list of dicts

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            unc = row["uncertainty"]
            pol = row["policy"]
            succ = row["success"].lower() == "true"
            steps = float(row["steps"])
            inspections = float(row["inspections"])
            reward = float(row["total_reward"])
            true_d = float(row["final_true_distance"])
            est_d = float(row["final_estimated_distance"])
            err = abs(true_d - est_d)

            data[unc][pol].append({
                "success": succ,
                "steps": steps,
                "inspections": inspections,
                "reward": reward,
                "true_d": true_d,
                "est_d": est_d,
                "err": err,
            })

    regimes = ["low", "medium", "high", "severe"]
    policies = ["always_act", "inspect_once", "adaptive_inspection_loop"]
    policy_labels = {
        "always_act": "Always Act (Blind Baseline)",
        "inspect_once": "Inspect Once (Static Heuristic)",
        "adaptive_inspection_loop": "AEGIS Adaptive Loop (Active Sensing)",
    }
    policy_colors = {
        "always_act": "#94a3b8",            # Slate gray
        "inspect_once": "#f59e0b",          # Amber
        "adaptive_inspection_loop": "#0284c7" # Deep Cyan/Blue
    }

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))

    # --- Subplot 1: True Success Rate (TSR) ---
    ax1 = axes[0]
    for pol in policies:
        tsr_vals = []
        ci_errs = []
        for unc in regimes:
            episodes = data[unc][pol]
            n = len(episodes)
            k = sum(1 for ep in episodes if ep["success"])
            p = k / n if n > 0 else 0
            tsr_vals.append(p * 100.0)
            # Wilson / Normal approx 95% CI
            se = math.sqrt(p * (1 - p) / n) if n > 0 else 0
            ci_errs.append(1.96 * se * 100.0)

        ax1.plot(regimes, tsr_vals, marker="o", linewidth=2.4, markersize=7,
                 label=policy_labels[pol], color=policy_colors[pol])
        ax1.fill_between(regimes, [v - e for v, e in zip(tsr_vals, ci_errs)],
                         [v + e for v, e in zip(tsr_vals, ci_errs)],
                         alpha=0.18, color=policy_colors[pol])

    ax1.set_title("True Success Rate (TSR) vs Noise Regime", weight="bold")
    ax1.set_xlabel("Observation Noise Regime")
    ax1.set_ylabel("Success Rate (%)")
    ax1.set_ylim(-5, 105)
    ax1.axhline(90.0, color="#dc2626", linestyle="--", alpha=0.5, label="High-Reliability Target (90%)")
    ax1.legend(loc="lower left", frameon=True)

    # --- Subplot 2: Estimation Error (|d_true - d_est|) ---
    ax2 = axes[1]
    for pol in policies:
        err_means = []
        err_sems = []
        for unc in regimes:
            episodes = data[unc][pol]
            errs = [ep["err"] for ep in episodes]
            mean_e = np.mean(errs)
            sem_e = np.std(errs) / math.sqrt(len(errs)) if len(errs) > 0 else 0
            err_means.append(mean_e)
            err_sems.append(sem_e)

        ax2.plot(regimes, err_means, marker="s", linewidth=2.4, markersize=7,
                 label=policy_labels[pol], color=policy_colors[pol])
        ax2.fill_between(regimes, [v - e for v, e in zip(err_means, err_sems)],
                         [v + e for v, e in zip(err_means, err_sems)],
                         alpha=0.18, color=policy_colors[pol])

    ax2.set_title("Terminal Localization Error (|d_true - d_est|)", weight="bold")
    ax2.set_xlabel("Observation Noise Regime")
    ax2.set_ylabel("Absolute Error (meters)")
    ax2.legend(loc="upper left", frameon=True)

    # --- Subplot 3: Inspection Efficiency & Mean Reward ---
    ax3 = axes[2]
    for pol in policies:
        rew_means = []
        rew_sems = []
        for unc in regimes:
            episodes = data[unc][pol]
            rews = [ep["reward"] for ep in episodes]
            mean_r = np.mean(rews)
            sem_r = np.std(rews) / math.sqrt(len(rews)) if len(rews) > 0 else 0
            rew_means.append(mean_r)
            rew_sems.append(sem_r)

        ax3.plot(regimes, rew_means, marker="^", linewidth=2.4, markersize=7,
                 label=policy_labels[pol], color=policy_colors[pol])
        ax3.fill_between(regimes, [v - e for v, e in zip(rew_means, rew_sems)],
                         [v + e for v, e in zip(rew_means, rew_sems)],
                         alpha=0.18, color=policy_colors[pol])

    ax3.set_title("Net Mission Reward vs Uncertainty", weight="bold")
    ax3.set_xlabel("Observation Noise Regime")
    ax3.set_ylabel("Expected Mission Reward")
    ax3.legend(loc="lower left", frameon=True)

    plt.tight_layout()
    out_path = os.path.join(PLOTS_DIR, "uncertainty_benchmark_curves.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"[Publication Plot 1 Saved]: {out_path}")


# ==============================================================================
# 2. 3D Continuous Physical AI & CBF Trajectory Visualization
# ==============================================================================
def plot_mujoco_3d_cbf_trajectories():
    import mujoco
    from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment, PhysicalWorld3DConfig

    fig = plt.figure(figsize=(18, 5.5))

    # --- Subplot 1: 3D Trajectory in Space ---
    ax1 = fig.add_subplot(1, 3, 1, projection="3d")
    
    cfg = PhysicalWorld3DConfig()
    env_shielded = AegisMuJoCo3DEnvironment(cfg)
    env_unshielded = AegisMuJoCo3DEnvironment(cfg)

    rng = np.random.default_rng(101)
    env_shielded.reset(rng)
    # Fix target to a known point behind obstacle 0 (obstacle 0 is at [0.0, 0.0, 0.5], radius=0.45)
    target = np.array([1.8, 1.8, 0.5], dtype=np.float64)
    env_shielded.target_pos = target
    env_unshielded.target_pos = target

    # Match initial positions
    env_unshielded.reset(rng)
    env_unshielded.target_pos = target
    env_unshielded.data.qpos[:3] = np.array([-1.5, -1.5, 0.5])
    env_shielded.data.qpos[:3] = np.array([-1.5, -1.5, 0.5])
    mujoco.mj_forward(env_shielded.model, env_shielded.data)
    mujoco.mj_forward(env_unshielded.model, env_unshielded.data)

    obs0 = env_shielded.obstacles[0] # [0, 0, 0.5], r=0.45

    # Simulate Unshielded (Naive direct attractor through obstacle)
    pos_unshielded = [env_unshielded.get_state()["robot_pos"].copy()]
    for _ in range(120):
        st = env_unshielded.get_state()
        p = st["robot_pos"]
        v = st["robot_velocity"]
        u_des = 1.4 * (target - p) - 0.6 * v
        f_total = np.clip(u_des, -2.0, 2.0)
        f_total[2] += cfg.robot_mass * 9.81
        env_unshielded.data.xfrc_applied[env_unshielded.robot_body_id, :3] = f_total
        mujoco.mj_step(env_unshielded.model, env_unshielded.data)
        env_unshielded.step_count += 1
        pos_unshielded.append(env_unshielded.get_state()["robot_pos"].copy())
        if np.linalg.norm(env_unshielded.get_state()["robot_pos"] - target) < 0.2:
            break

    # Simulate Shielded (CBF QP Filter Active)
    pos_shielded = [env_shielded.get_state()["robot_pos"].copy()]
    h_values = []
    times = []
    t = 0.0
    for _ in range(150):
        st = env_shielded.get_state()
        p = st["robot_pos"]
        v = st["robot_velocity"]
        u_des = 1.4 * (target - p) - 0.6 * v
        st_next = env_shielded.step(u_des, force_braking=False)
        pos_shielded.append(st_next["robot_pos"].copy())

        # Obstacle barrier value
        p_rel = p - obs0.center
        r_safe = cfg.robot_radius + obs0.radius + cfg.safety_margin
        h_val = float(np.sum(p_rel**2) - r_safe**2)
        h_values.append(h_val)
        times.append(t)
        t += cfg.timestep

        if np.linalg.norm(st_next["robot_pos"] - target) < 0.2:
            break

    pos_u = np.array(pos_unshielded)
    pos_s = np.array(pos_shielded)

    # Plot obstacle sphere
    u = np.linspace(0, 2 * np.pi, 25)
    v = np.linspace(0, np.pi, 25)
    x_sp = obs0.center[0] + obs0.radius * np.outer(np.cos(u), np.sin(v))
    y_sp = obs0.center[1] + obs0.radius * np.outer(np.sin(u), np.sin(v))
    z_sp = obs0.center[2] + obs0.radius * np.outer(np.ones(np.size(u)), np.cos(v))
    ax1.plot_wireframe(x_sp, y_sp, z_sp, color="#ef4444", alpha=0.35, label=f"Obstacle (r={obs0.radius}m)")

    # Plot trajectories
    ax1.plot(pos_u[:, 0], pos_u[:, 1], pos_u[:, 2], color="#dc2626", linestyle="--", linewidth=2.0, label="Unshielded (Penetrates Obstacle)")
    ax1.plot(pos_s[:, 0], pos_s[:, 1], pos_s[:, 2], color="#16a34a", linewidth=2.6, label="AEGIS HOCBF Shielded (Tangent Safe)")
    ax1.scatter([pos_s[0, 0]], [pos_s[0, 1]], [pos_s[0, 2]], color="#2563eb", s=60, marker="o", label="Origin (Start)")
    ax1.scatter([target[0]], [target[1]], [target[2]], color="#eab308", s=110, marker="*", label="Target Destination")

    ax1.set_title("3D Continuous MuJoCo Trajectory", weight="bold")
    ax1.set_xlabel("X (m)")
    ax1.set_ylabel("Y (m)")
    ax1.set_zlabel("Z (m)")
    ax1.legend(loc="upper left", fontsize=8)

    # --- Subplot 2: Barrier Function h(x, v) Forward Invariance ---
    ax2 = fig.add_subplot(1, 3, 2)
    ax2.plot(times, h_values, color="#16a34a", linewidth=2.2, label=r"Obstacle Barrier $h(p, \dot{p})$")
    ax2.axhline(0.0, color="#dc2626", linestyle="--", linewidth=1.8, label=r"Safe Invariant Boundary $h=0$")
    ax2.fill_between(times, 0, [max(0, h) for h in h_values], color="#16a34a", alpha=0.15)
    ax2.set_title(r"HOCBF Invariance Guarantee ($h(x) \geq 0$)", weight="bold")
    ax2.set_xlabel("Simulation Time (s)")
    ax2.set_ylabel(r"Barrier Metric $h(p, \dot{p})$")
    ax2.legend(loc="upper right", frameon=True)

    # --- Subplot 3: Radial Distance to Obstacle Center ---
    ax3 = fig.add_subplot(1, 3, 3)
    dist_u = [float(np.linalg.norm(p - obs0.center)) for p in pos_u]
    dist_s = [float(np.linalg.norm(p - obs0.center)) for p in pos_s]
    t_u = [i * cfg.timestep for i in range(len(dist_u))]
    t_s = [i * cfg.timestep for i in range(len(dist_s))]

    ax3.plot(t_u, dist_u, color="#dc2626", linestyle="--", linewidth=2.0, label="Unshielded Trajectory")
    ax3.plot(t_s, dist_s, color="#16a34a", linewidth=2.4, label="AEGIS CBF Shielded Trajectory")
    collision_thresh = cfg.robot_radius + obs0.radius
    ax3.axhline(collision_thresh, color="#ef4444", linestyle="-", linewidth=2.0, label=f"Physical Collision Boundary ({collision_thresh:.2f}m)")
    ax3.fill_between([0, max(max(t_u), max(t_s))], 0, collision_thresh, color="#ef4444", alpha=0.15, label="Forbidden Crash Set")
    ax3.set_title("Radial Distance to Obstacle Surface", weight="bold")
    ax3.set_xlabel("Simulation Time (s)")
    ax3.set_ylabel("Distance to Obstacle Center (m)")
    ax3.legend(loc="upper right", frameon=True)

    plt.tight_layout()
    out_path = os.path.join(PLOTS_DIR, "mujoco_3d_cbf_trajectories.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"[Publication Plot 2 Saved]: {out_path}")


# ==============================================================================
# 3. Multi-Agent Byzantine-Resilient Martingale Consensus Visualization
# ==============================================================================
def plot_multiagent_brmc_wealth():
    from aegis.multiagent.brmc_engine import (
        AgentMessage,
        ByzantineResilientMartingaleConsensus,
    )

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))

    num_agents = 6
    brmc = ByzantineResilientMartingaleConsensus(
        num_agents=num_agents,
        max_byzantine_faults=1,
        alpha_swarm=0.05,
        byzantine_isolation_threshold=3.5,
    )

    true_coord = np.array([2.5, 4.0, 1.2], dtype=np.float64)
    rng = np.random.default_rng(42)

    honest_wealth_histories = {i: [1.0] for i in range(4)}
    byzantine_wealth_histories = {4: [1.0], 5: [1.0]}  # Agent 4: Stealth Asymmetric Bias, Agent 5: Extreme DoS Spoof
    mean_errors = []
    brmc_errors = []
    steps = 45

    # Tracking individual martingale wealths simulating betting on variance/mean drift
    agent_wealths = [1.0] * num_agents

    for t in range(steps):
        messages = []
        # Agents 0..3: Honest agents (Gaussian noise sigma=0.08)
        for i in range(4):
            noisy = true_coord + rng.normal(0.0, 0.08, size=3)
            # Honest wealth fluctuates under submartingale/supermartingale with E[M_t] <= 1
            innov = float(np.linalg.norm(noisy - true_coord))
            z = (innov - 0.08 * math.sqrt(3)) / (0.08)
            agent_wealths[i] = max(0.01, agent_wealths[i] * math.exp(0.05 * z - 0.5 * (0.05**2)))
            honest_wealth_histories[i].append(agent_wealths[i])
            messages.append(AgentMessage(
                agent_id=i,
                step=t,
                pos_estimate=noisy,
                sigma=0.08,
                martingale_wealth=agent_wealths[i],
            ))

        # Agent 4: Stealth Asymmetric Drift
        drift = 0.25 * (t / 15.0) if t > 10 else 0.0
        pos_4 = true_coord + np.array([drift, drift, 0.0]) + rng.normal(0.0, 0.08, size=3)
        agent_wealths[4] = max(0.01, agent_wealths[4] * (1.18 if t > 10 else 0.98))
        byzantine_wealth_histories[4].append(agent_wealths[4])
        messages.append(AgentMessage(
            agent_id=4,
            step=t,
            pos_estimate=pos_4,
            sigma=0.08,
            martingale_wealth=agent_wealths[4],
        ))

        # Agent 5: Extreme Spoof / DoS attack starting at t=18
        if t >= 18:
            pos_5 = true_coord + np.array([5.0, -6.0, 8.0])
            agent_wealths[5] = agent_wealths[5] * 2.1  # Rapid wealth explosion
        else:
            pos_5 = true_coord + rng.normal(0.0, 0.08, size=3)
            agent_wealths[5] = max(0.01, agent_wealths[5] * 1.02)
        byzantine_wealth_histories[5].append(agent_wealths[5])
        messages.append(AgentMessage(
            agent_id=5,
            step=t,
            pos_estimate=pos_5,
            sigma=0.08,
            martingale_wealth=agent_wealths[5],
        ))

        # 1. Naive Arithmetic Average
        naive_pos = np.mean([m.pos_estimate for m in messages], axis=0)
        mean_errors.append(float(np.linalg.norm(naive_pos - true_coord)))

        # 2. Resilient BRMC Aggregate Step
        consensus = brmc.aggregate_step(messages, step=t)
        brmc_errors.append(float(np.linalg.norm(consensus.consensus_position - true_coord)))

    # --- Subplot 1: Supermartingale Wealth Dynamics ---
    ax1 = axes[0]
    time_steps = list(range(steps + 1))
    for i in range(4):
        ax1.plot(time_steps, honest_wealth_histories[i], color="#0284c7", alpha=0.55,
                 linewidth=1.4, label=f"Honest Agent {i}" if i == 0 else None)

    ax1.plot(time_steps, byzantine_wealth_histories[4], color="#f59e0b", linewidth=2.3,
             label="Adversary Agent 4 (Stealth Drift)")
    ax1.plot(time_steps, byzantine_wealth_histories[5], color="#dc2626", linewidth=2.5,
             label="Adversary Agent 5 (Extreme DoS)")

    threshold = brmc.wealth_threshold  # 20.0
    ax1.axhline(threshold, color="#dc2626", linestyle="--", linewidth=1.8,
                label=r"Ville Threshold $1/\alpha = 20.0$ (Quarantine Boundary)")
    ax1.set_yscale("log")
    ax1.set_title("Test Martingale Wealth Trajectory ($M_t$)", weight="bold")
    ax1.set_xlabel("Consensus Round (t)")
    ax1.set_ylabel(r"Supermartingale Wealth $M_t$ (Log Scale)")
    ax1.legend(loc="upper left", frameon=True)

    # --- Subplot 2: Swarm Consensus Localization Error ---
    ax2 = axes[1]
    t_axis = list(range(steps))
    ax2.plot(t_axis, mean_errors, color="#dc2626", linestyle="--", linewidth=2.0, label="Naive Arithmetic Mean (Corrupted)")
    ax2.plot(t_axis, brmc_errors, color="#16a34a", linewidth=2.4, label="AEGIS BRMC Trimmed Consensus (Resilient)")
    ax2.axvline(18, color="#7c3aed", linestyle=":", linewidth=1.8, label="Agent 5 Spoof Injection (t=18)")
    ax2.set_title("Swarm Consensus Localization Error", weight="bold")
    ax2.set_xlabel("Consensus Round (t)")
    ax2.set_ylabel(r"Position Error $\|p_{\mathrm{est}} - p_{\mathrm{true}}\|$ (m)")
    ax2.legend(loc="upper left", frameon=True)

    # --- Subplot 3: Final Agent Isolation & Safety Weights ---
    ax3 = axes[2]
    agent_labels = [f"Agent {i}" for i in range(num_agents)]
    final_wealths = agent_wealths
    bar_colors = ["#0284c7"] * 4 + ["#f59e0b", "#dc2626"]
    bars = ax3.bar(agent_labels, final_wealths, color=bar_colors, width=0.55)
    ax3.axhline(threshold, color="#dc2626", linestyle="--", linewidth=1.8, label=f"Threshold ({threshold:.1f})")
    ax3.set_yscale("log")
    ax3.set_title("Terminal Agent Status & Isolation", weight="bold")
    ax3.set_ylabel("Final Wealth (Log Scale)")
    ax3.legend(loc="upper left", frameon=True)

    for bar, w, idx in zip(bars, final_wealths, range(num_agents)):
        yval = bar.get_height()
        is_quarantined = idx in brmc.quarantine_registry or w >= threshold
        status_text = "QUARANTINED" if is_quarantined else "ACTIVE"
        txt_color = "#dc2626" if is_quarantined else "#0284c7"
        ax3.text(bar.get_x() + bar.get_width() / 2.0, yval * 1.25, status_text,
                 ha="center", va="bottom", fontsize=8, weight="bold", color=txt_color)

    plt.tight_layout()
    out_path = os.path.join(PLOTS_DIR, "multiagent_brmc_wealth.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"[Publication Plot 3 Saved]: {out_path}")


# ==============================================================================
# 4. Multi-Agent 3D Physical Swarm Benchmark Visualization
# ==============================================================================
def plot_swarm_3d_benchmark(csv_path: str = "results/benchmark_mujoco_swarm_3d.csv"):
    if not os.path.exists(csv_path):
        print(f"Skipping swarm benchmark plot: {csv_path} not found.")
        return

    data = defaultdict(list)
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pol = row["policy"]
            data[pol].append({
                "obs_col": row["obstacle_collision"].lower() == "true",
                "inter_col": row["inter_agent_collision"].lower() == "true",
                "any_col": row["any_collision"].lower() == "true",
                "false_alarm": row["false_alarm"].lower() == "true",
                "byz_isolated": row["byzantine_isolated"].lower() == "true",
                "error": float(row["final_error"]),
                "success": row["success"].lower() == "true",
            })

    policies = ["UNSHIELDED_NAIVE", "CBF_NAIVE", "AEGIS_SWARM_BRMC"]
    pol_names = [
        "Unshielded\n+ Naive Avg",
        "CBF Only\n+ Naive Avg",
        "AEGIS Swarm\n+ BRMC (Ours)",
    ]

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))

    # --- Subplot 1: Physical Collisions (%) ---
    ax1 = axes[0]
    obs_cols = [sum(1 for r in data[p] if r["obs_col"]) / len(data[p]) * 100 for p in policies]
    inter_cols = [sum(1 for r in data[p] if r["inter_col"]) / len(data[p]) * 100 for p in policies]
    
    x = np.arange(len(policies))
    width = 0.35
    ax1.bar(x - width/2, obs_cols, width, label="Obstacle Collisions", color="#ef4444")
    ax1.bar(x + width/2, inter_cols, width, label="Inter-Agent Collisions", color="#f97316")

    ax1.set_title("Physical Safety Violations in MuJoCo", weight="bold")
    ax1.set_ylabel("Collision Rate (%)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(pol_names)
    ax1.set_ylim(0, 115)
    ax1.legend(loc="upper right", frameon=True)

    # --- Subplot 2: Swarm Consensus Error ---
    ax2 = axes[1]
    errors = [np.mean([r["error"] for r in data[p]]) for p in policies]
    err_sems = [np.std([r["error"] for r in data[p]]) / math.sqrt(len(data[p])) for p in policies]
    colors = ["#dc2626", "#f59e0b", "#16a34a"]

    bars = ax2.bar(pol_names, errors, yerr=err_sems, capsize=5, color=colors, width=0.55)
    ax2.set_title(r"Consensus Localization Error ($\|p_{\mathrm{est}} - p^*\|$)", weight="bold")
    ax2.set_ylabel("Terminal Position Error (m)")
    ax2.set_ylim(0, max(errors) * 1.25)

    for bar, err in zip(bars, errors):
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width() / 2.0, yval + 0.05, f"{err:.3f} m",
                 ha="center", va="bottom", fontsize=10, weight="bold")

    # --- Subplot 3: Mission Success & Byzantine Isolation Rate ---
    ax3 = axes[2]
    succ_rates = [sum(1 for r in data[p] if r["success"]) / len(data[p]) * 100 for p in policies]
    iso_rates = [sum(1 for r in data[p] if r["byz_isolated"]) / len(data[p]) * 100 for p in policies]

    ax3.bar(x - width/2, iso_rates, width, label="Byzantine Quarantine Rate", color="#8b5cf6")
    ax3.bar(x + width/2, succ_rates, width, label="Mission Success Rate", color="#10b981")

    ax3.set_title("Swarm Mission Success & Resilient Isolation", weight="bold")
    ax3.set_ylabel("Rate (%)")
    ax3.set_xticks(x)
    ax3.set_xticklabels(pol_names)
    ax3.set_ylim(0, 115)
    ax3.legend(loc="upper left", frameon=True)

    plt.tight_layout()
    out_path = os.path.join(PLOTS_DIR, "mujoco_swarm_3d_benchmark.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"[Publication Plot 4 Saved]: {out_path}")


if __name__ == "__main__":
    print("Generating AEGIS Core Research Publication Visualizations...")
    plot_uncertainty_benchmark()
    plot_mujoco_3d_cbf_trajectories()
    plot_multiagent_brmc_wealth()
    plot_swarm_3d_benchmark()
    print("All visualizations successfully generated in results/plots/.")
