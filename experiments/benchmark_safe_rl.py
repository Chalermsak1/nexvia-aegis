"""
NEXVIA AEGIS — Adaptive Safe Reinforcement Learning (Safe RL) Benchmark.

Evaluates and compares:
1. Unshielded Vanilla RL (Standard PPO without safety barrier).
2. Static HOCBF-Shielded Safe RL (Standard fixed-decay barrier HOCBF).
3. Adaptive AEGIS Safe RL (Velocity-adaptive barrier decay + Energy/Jerk regularization + Dual Innovation Gate).

Key Objectives:
  - Maximize mission speed (shorter transit time).
  - Minimize control energy (integral ||F - F_hover||^2 dt) and jerk.
  - Strictly guarantee zero physical collisions and 0% Selective Risk under sensor degradation.

Outputs:
  - JSON data: results/data/safe_rl_benchmark.json
  - Publication-grade figure: results/data/safe_rl_adaptive_benchmark.png
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from aegis.rl.safe_env_wrapper import Safe6DOFQuadrotorEnv
from aegis.rl.safe_ppo_agent import PPOConfig, SafePPOAgent


def train_policy(
    shield_enabled: bool,
    adaptive_cbf: bool = False,
    num_episodes: int = 25,
    steps_per_episode: int = 150,
    seed: int = 42,
) -> dict[str, Any]:
    """Trains a PPO policy with specified safety shield and adaptive regularizers."""
    env = Safe6DOFQuadrotorEnv(
        shield_enabled=shield_enabled,
        adaptive_cbf=adaptive_cbf,
        enable_deep_aero=True,
        max_steps=steps_per_episode,
        intervention_penalty_weight=0.04,
        energy_penalty_weight=0.02 if adaptive_cbf else 0.0,
        smoothness_penalty_weight=0.01 if adaptive_cbf else 0.0,
    )
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    init_pos = np.array([-1.2, -1.2, 1.0], dtype=np.float64)

    cfg = PPOConfig(
        lr=4.0e-4,
        update_epochs=3,
        batch_size=32,
        hidden_dim=64,
    )
    agent = SafePPOAgent(state_dim=20, action_dim=3, config=cfg)

    episode_rewards = []
    cumulative_collisions = []
    intervention_norms = []
    arrival_successes = []

    total_crashes = 0

    for ep in range(num_episodes):
        obs = env.reset(rng=rng, initial_pos=init_pos)
        ep_reward = 0.0
        states, actions, log_probs, rewards, values, dones = [], [], [], [], [], []
        ep_interventions = 0.0

        for step in range(steps_per_episode):
            action, log_prob, value = agent.select_action(obs)
            next_obs, reward, terminated, truncated, info = env.step(action)

            states.append(obs)
            actions.append(action)
            log_probs.append(log_prob)
            rewards.append(reward)
            values.append(value)
            dones.append(float(terminated or truncated))

            ep_reward += reward
            ep_interventions += info["intervention_norm"]

            if info["collision"]:
                total_crashes += 1

            obs = next_obs
            if terminated or truncated:
                break

        # PPO Update
        _, _, next_val = agent.select_action(obs)
        if len(states) >= 16:
            agent.update(
                states=np.array(states, dtype=np.float32),
                actions=np.array(actions, dtype=np.float32),
                log_probs=np.array(log_probs, dtype=np.float32),
                rewards=np.array(rewards, dtype=np.float32),
                values=np.array(values, dtype=np.float32),
                dones=np.array(dones, dtype=np.float32),
                next_value=next_val,
            )

        episode_rewards.append(float(ep_reward))
        cumulative_collisions.append(total_crashes)
        intervention_norms.append(float(ep_interventions / max(1, len(states))))
        arrival_successes.append(1 if info["arrived"] else 0)

    return {
        "shield_enabled": shield_enabled,
        "adaptive_cbf": adaptive_cbf,
        "episode_rewards": episode_rewards,
        "cumulative_collisions": cumulative_collisions,
        "intervention_norms": intervention_norms,
        "arrival_successes": arrival_successes,
        "agent": agent,
    }


def evaluate_policy(
    agent: SafePPOAgent,
    shield_enabled: bool,
    adaptive_cbf: bool = False,
    enable_innovation_gate: bool = False,
    sensor_fault_config: dict[str, Any] | None = None,
    num_eval_episodes: int = 15,
    eval_steps: int = 210,
    seed: int = 101,
) -> dict[str, Any]:
    """Evaluates policy on dynamic obstacles under nominal or sensor-degraded conditions."""
    env = Safe6DOFQuadrotorEnv(
        shield_enabled=shield_enabled,
        adaptive_cbf=adaptive_cbf,
        enable_deep_aero=True,
        max_steps=eval_steps,
        enable_innovation_gate=enable_innovation_gate,
        sensor_fault_config=sensor_fault_config,
    )
    rng = np.random.default_rng(seed)
    init_pos = np.array([-1.2, -1.2, 1.0], dtype=np.float64)

    true_arrival_count = 0
    false_arrival_count = 0
    abstain_count = 0
    collision_count = 0

    transit_times = []
    control_energies = []
    mean_jerks = []
    final_distances = []

    trajectories = []
    obstacle_trajectories = []

    for ep in range(num_eval_episodes):
        obs = env.reset(rng=rng, initial_pos=init_pos)
        drone_path = []
        dyn_obs_path = []

        for step in range(eval_steps):
            action, _, _ = agent.select_action(obs, deterministic=True)
            obs, _, terminated, truncated, info = env.step(action)

            drone_path.append([float(x) for x in info["drone_pos"]])
            dyn_obs_path.append([[float(x) for x in d.center] for d in env.dynamic_obstacles])

            if info["collision"]:
                collision_count += 1
                if not shield_enabled:
                    break

            if terminated or truncated:
                break

        if info["true_arrival"]:
            true_arrival_count += 1
        if info["false_arrival"]:
            false_arrival_count += 1
        if info["abstain"]:
            abstain_count += 1

        transit_times.append(float(info["transit_time_s"]))
        control_energies.append(float(info["control_energy"]))
        mean_jerks.append(float(info["mean_jerk"]))
        final_distances.append(float(info["distance"]))

        if ep == 0:
            trajectories = drone_path
            obstacle_trajectories = dyn_obs_path

    total_arrivals = true_arrival_count + false_arrival_count
    selective_risk = (
        float(false_arrival_count / total_arrivals * 100.0)
        if total_arrivals > 0
        else 0.0
    )

    return {
        "true_arrival_rate_pct": float(true_arrival_count / num_eval_episodes * 100.0),
        "false_arrival_rate_pct": float(false_arrival_count / num_eval_episodes * 100.0),
        "selective_risk_pct": selective_risk,
        "abstain_rate_pct": float(abstain_count / num_eval_episodes * 100.0),
        "collision_count": collision_count,
        "mean_transit_time_s": float(np.mean(transit_times)),
        "mean_control_energy": float(np.mean(control_energies)),
        "mean_jerk": float(np.mean(mean_jerks)),
        "mean_final_distance_m": float(np.mean(final_distances)),
        "sample_trajectory": trajectories,
        "sample_dynamic_obs_trajectory": obstacle_trajectories,
    }


def plot_safe_rl_benchmark(
    training_data: dict[str, Any],
    nominal_eval: dict[str, Any],
    fault_eval: dict[str, Any],
    out_path: Path,
) -> None:
    """Renders 4-panel publication-grade evaluation figure."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor("#0b0f19")

    text_color = "#e2e8f0"
    grid_color = "#334155"

    for ax in axes.flat:
        ax.set_facecolor("#111827")
        ax.tick_params(colors=text_color, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(grid_color)
        ax.grid(True, linestyle="--", alpha=0.35, color=grid_color)

    # 1. Training Reward & Collision Avoidance
    ax1 = axes[0, 0]
    eps = range(1, len(training_data["unshielded"]["rewards"]) + 1)
    ax1.plot(eps, training_data["unshielded"]["rewards"], color="#f87171", label="Unshielded Vanilla RL", lw=2)
    ax1.plot(eps, training_data["static"]["rewards"], color="#38bdf8", label="Static HOCBF Safe RL", lw=2)
    ax1.plot(eps, training_data["adaptive"]["rewards"], color="#4ade80", label="Adaptive AEGIS Safe RL", lw=2.2)
    ax1.set_title("Training Convergence (PPO Reward)", color=text_color, fontweight="bold", pad=8)
    ax1.set_xlabel("Episode", color=text_color)
    ax1.set_ylabel("Episodic Return", color=text_color)
    ax1.legend(facecolor="#1e293b", edgecolor=grid_color, labelcolor=text_color, loc="lower right", fontsize=8)

    # 2. Control Energy vs Transit Time (Speed & Energy Trade-off)
    ax2 = axes[0, 1]
    controllers = ["Unshielded", "Static CBF", "Adaptive AEGIS"]
    energies = [
        nominal_eval["unshielded"]["mean_control_energy"],
        nominal_eval["static"]["mean_control_energy"],
        nominal_eval["adaptive"]["mean_control_energy"],
    ]
    transit_times = [
        nominal_eval["unshielded"]["mean_transit_time_s"],
        nominal_eval["static"]["mean_transit_time_s"],
        nominal_eval["adaptive"]["mean_transit_time_s"],
    ]
    colors = ["#f87171", "#38bdf8", "#4ade80"]

    scatter = ax2.scatter(transit_times, energies, c=colors, s=220, edgecolors="#ffffff", lw=1.8, zorder=5)
    for i, name in enumerate(controllers):
        ax2.annotate(
            f"{name}\n(E={energies[i]:.1f} N²s, T={transit_times[i]:.2f}s)",
            (transit_times[i], energies[i]),
            textcoords="offset points",
            xytext=(10, -5 if i != 2 else 10),
            color=text_color,
            fontweight="bold",
            fontsize=8.5,
        )
    ax2.set_title("Mission Speed vs Energy Efficiency (Nominal Scenario)", color=text_color, fontweight="bold", pad=8)
    ax2.set_xlabel("Mean Transit Time (seconds) [Lower = Faster]", color=text_color)
    ax2.set_ylabel("Control Energy (N²·s) [Lower = More Efficient]", color=text_color)

    # 3. Robustness & Selective Risk under Sensor Perturbation
    ax3 = axes[1, 0]
    x_pos = np.arange(len(controllers))
    bar_width = 0.35

    sel_risks = [
        fault_eval["unshielded"]["selective_risk_pct"],
        fault_eval["static"]["selective_risk_pct"],
        fault_eval["adaptive"]["selective_risk_pct"],
    ]
    true_arrivals = [
        fault_eval["unshielded"]["true_arrival_rate_pct"],
        fault_eval["static"]["true_arrival_rate_pct"],
        fault_eval["adaptive"]["true_arrival_rate_pct"],
    ]

    b1 = ax3.bar(x_pos - bar_width / 2, sel_risks, bar_width, label="Selective Risk (%)", color="#fb7185", alpha=0.9)
    b2 = ax3.bar(x_pos + bar_width / 2, true_arrivals, bar_width, label="True Arrival (%)", color="#34d399", alpha=0.9)

    ax3.set_xticks(x_pos)
    ax3.set_xticklabels(controllers, color=text_color, fontweight="semibold")
    ax3.set_ylabel("Rate (%)", color=text_color)
    ax3.set_title("Adversarial Sensor Degradation (Selective Risk vs True Arrival)", color=text_color, fontweight="bold", pad=8)
    ax3.legend(facecolor="#1e293b", edgecolor=grid_color, labelcolor=text_color, loc="upper right", fontsize=8)

    for bar in b1:
        h = bar.get_height()
        ax3.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                     textcoords="offset points", ha="center", va="bottom", color="#f43f5e", fontweight="bold", fontsize=8)
    for bar in b2:
        h = bar.get_height()
        ax3.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                     textcoords="offset points", ha="center", va="bottom", color="#10b981", fontweight="bold", fontsize=8)

    # 4. 2D Trajectory Projection (X-Y plane with Dynamic Obstacle)
    ax4 = axes[1, 1]
    traj_unshielded = np.array(nominal_eval["unshielded"]["sample_trajectory"])
    traj_static = np.array(nominal_eval["static"]["sample_trajectory"])
    traj_adaptive = np.array(nominal_eval["adaptive"]["sample_trajectory"])

    if len(traj_unshielded) > 0:
        ax4.plot(traj_unshielded[:, 0], traj_unshielded[:, 1], color="#f87171", ls="--", label="Unshielded (Crash)", lw=1.6)
    if len(traj_static) > 0:
        ax4.plot(traj_static[:, 0], traj_static[:, 1], color="#38bdf8", label="Static CBF (Sluggish)", lw=2.0)
    if len(traj_adaptive) > 0:
        ax4.plot(traj_adaptive[:, 0], traj_adaptive[:, 1], color="#4ade80", label="Adaptive AEGIS (Fluid)", lw=2.4)

    # Plot dynamic obstacle paths
    dyn_obs_hist = np.array(nominal_eval["adaptive"]["sample_dynamic_obs_trajectory"])
    if len(dyn_obs_hist) > 0:
        for obs_idx in range(dyn_obs_hist.shape[1]):
            ax4.plot(
                dyn_obs_hist[:, obs_idx, 0],
                dyn_obs_hist[:, obs_idx, 1],
                color="#cbd5e1",
                alpha=0.4,
                ls=":",
                lw=1.2,
            )
            # End position of obstacle
            circle = plt.Circle(
                (dyn_obs_hist[-1, obs_idx, 0], dyn_obs_hist[-1, obs_idx, 1]),
                0.35,
                color="#e11d48",
                alpha=0.35,
            )
            ax4.add_patch(circle)

    # Plot Target
    ax4.scatter([1.8], [1.8], color="#fbbf24", s=180, marker="*", label="Target [1.8, 1.8]", zorder=10)
    ax4.scatter([-1.2], [-1.2], color="#94a3b8", s=80, marker="o", label="Start [-1.2, -1.2]", zorder=10)

    ax4.set_title("Trajectory Profile (Horizontal X-Y Plane)", color=text_color, fontweight="bold", pad=8)
    ax4.set_xlabel("X Position (m)", color=text_color)
    ax4.set_ylabel("Y Position (m)", color=text_color)
    ax4.legend(facecolor="#1e293b", edgecolor=grid_color, labelcolor=text_color, loc="lower right", fontsize=8)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=220, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)


def main() -> None:
    print("=" * 75)
    print("NEXVIA AEGIS — Adaptive Safe Reinforcement Learning (Safe RL) Benchmark")
    print("Continuous 6-DOF Quadrotor: Speed, Energy & Zero Selective Risk Verification")
    print("=" * 75)

    # 1. Train Policies
    print("\n[1/3] Training Unshielded Vanilla PPO (No Shield)...")
    res_unshielded = train_policy(shield_enabled=False, adaptive_cbf=False, num_episodes=25, seed=42)
    print(f"  Unshielded Crashes: {res_unshielded['cumulative_collisions'][-1]}")
    print(f"  Final Reward: {np.mean(res_unshielded['episode_rewards'][-5:]):.2f}")

    print("\n[2/3] Training Static HOCBF-Shielded Safe PPO...")
    res_static = train_policy(shield_enabled=True, adaptive_cbf=False, num_episodes=25, seed=42)
    print(f"  Static CBF Crashes: {res_static['cumulative_collisions'][-1]}")
    print(f"  Final Reward: {np.mean(res_static['episode_rewards'][-5:]):.2f}")

    print("\n[3/3] Training Adaptive AEGIS Safe PPO (Velocity-Adaptive + Energy-Regularized)...")
    res_adaptive = train_policy(shield_enabled=True, adaptive_cbf=True, num_episodes=25, seed=42)
    print(f"  Adaptive AEGIS Crashes: {res_adaptive['cumulative_collisions'][-1]}")
    print(f"  Final Reward: {np.mean(res_adaptive['episode_rewards'][-5:]):.2f}")

    # 2. Evaluate on Nominal Scenarios (Speed, Energy, Jerk)
    print("\n--- Evaluating Nominal Scenarios (Dynamic Obstacles & Deep Aerodynamics) ---")
    eval_unshielded_nom = evaluate_policy(res_unshielded["agent"], shield_enabled=False, adaptive_cbf=False)
    eval_static_nom = evaluate_policy(res_static["agent"], shield_enabled=True, adaptive_cbf=False)
    eval_adaptive_nom = evaluate_policy(res_adaptive["agent"], shield_enabled=True, adaptive_cbf=True, enable_innovation_gate=False)

    print(f"  [Unshielded]   True Arrival: {eval_unshielded_nom['true_arrival_rate_pct']:.1f}%, Crashes: {eval_unshielded_nom['collision_count']}, Energy: {eval_unshielded_nom['mean_control_energy']:.1f} N²s, Transit: {eval_unshielded_nom['mean_transit_time_s']:.2f}s")
    print(f"  [Static CBF]   True Arrival: {eval_static_nom['true_arrival_rate_pct']:.1f}%, Crashes: {eval_static_nom['collision_count']}, Energy: {eval_static_nom['mean_control_energy']:.1f} N²s, Transit: {eval_static_nom['mean_transit_time_s']:.2f}s")
    print(f"  [Adaptive AEGIS] True Arrival: {eval_adaptive_nom['true_arrival_rate_pct']:.1f}%, Crashes: {eval_adaptive_nom['collision_count']}, Energy: {eval_adaptive_nom['mean_control_energy']:.1f} N²s, Transit: {eval_adaptive_nom['mean_transit_time_s']:.2f}s")

    # 3. Evaluate under Adversarial Sensor Degradation (Measuring Selective Risk)
    print("\n--- Evaluating Adversarial Sensor Degradation (Measuring Selective Risk) ---")
    fault_cfg = {"fault_type": "spoof_arrival", "start_step": 30}

    eval_unshielded_fault = evaluate_policy(
        res_unshielded["agent"],
        shield_enabled=False,
        sensor_fault_config=fault_cfg,
    )
    eval_static_fault = evaluate_policy(
        res_static["agent"],
        shield_enabled=True,
        adaptive_cbf=False,
        sensor_fault_config=fault_cfg,
    )
    eval_adaptive_fault = evaluate_policy(
        res_adaptive["agent"],
        shield_enabled=True,
        adaptive_cbf=True,
        enable_innovation_gate=True,
        sensor_fault_config=fault_cfg,
    )

    print(f"  [Unshielded]   False Arrival: {eval_unshielded_fault['false_arrival_rate_pct']:.1f}%, Selective Risk: {eval_unshielded_fault['selective_risk_pct']:.1f}%")
    print(f"  [Static CBF]   False Arrival: {eval_static_fault['false_arrival_rate_pct']:.1f}%, Selective Risk: {eval_static_fault['selective_risk_pct']:.1f}%")
    print(f"  [Adaptive AEGIS] False Arrival: {eval_adaptive_fault['false_arrival_rate_pct']:.1f}%, Selective Risk: {eval_adaptive_fault['selective_risk_pct']:.1f}%, Abstain: {eval_adaptive_fault['abstain_rate_pct']:.1f}%")

    # 4. Serialize JSON and Render Figure
    payload = {
        "training": {
            "episodes": list(range(1, 26)),
            "unshielded": {
                "rewards": res_unshielded["episode_rewards"],
                "collisions": res_unshielded["cumulative_collisions"],
            },
            "static": {
                "rewards": res_static["episode_rewards"],
                "collisions": res_static["cumulative_collisions"],
            },
            "adaptive": {
                "rewards": res_adaptive["episode_rewards"],
                "collisions": res_adaptive["cumulative_collisions"],
            },
        },
        "evaluation_nominal": {
            "unshielded": eval_unshielded_nom,
            "static": eval_static_nom,
            "adaptive": eval_adaptive_nom,
        },
        "evaluation_sensor_fault": {
            "unshielded": eval_unshielded_fault,
            "static": eval_static_fault,
            "adaptive": eval_adaptive_fault,
        },
    }

    out_json = Path("results/data/safe_rl_benchmark.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(payload, f, indent=2)

    out_png = Path("results/data/safe_rl_adaptive_benchmark.png")
    plot_safe_rl_benchmark(
        training_data=payload["training"],
        nominal_eval=payload["evaluation_nominal"],
        fault_eval=payload["evaluation_sensor_fault"],
        out_path=out_png,
    )

    print(f"\n[OK] Safe RL benchmark data saved to: {out_json}")
    print(f"[OK] Safe RL publication figure saved to: {out_png}")
    print("=" * 75)


if __name__ == "__main__":
    main()
