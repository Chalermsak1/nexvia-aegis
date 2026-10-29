"""
NEXVIA AEGIS — Safe Reinforcement Learning (Safe RL) Benchmark.

Trains and evaluates:
1. Unshielded Vanilla RL (Standard PPO without safety shield).
2. HOCBF-Shielded Safe RL (AEGIS PPO with action shielding & intervention penalty).
3. Evaluates both policies on held-out test episodes with dynamic moving obstacles and wind turbulence.

Saves benchmark metrics to results/data/safe_rl_benchmark.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from aegis.rl.safe_env_wrapper import Safe6DOFQuadrotorEnv
from aegis.rl.safe_ppo_agent import PPOConfig, SafePPOAgent


def train_policy(
    shield_enabled: bool,
    num_episodes: int = 35,
    steps_per_episode: int = 80,
    seed: int = 42,
) -> dict[str, Any]:
    """Trains a PPO policy with or without HOCBF action shielding."""
    env = Safe6DOFQuadrotorEnv(
        shield_enabled=shield_enabled,
        enable_deep_aero=True,
        max_steps=steps_per_episode,
        intervention_penalty_weight=0.04,
    )
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)

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
        obs = env.reset(rng=rng)
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
        "episode_rewards": episode_rewards,
        "cumulative_collisions": cumulative_collisions,
        "intervention_norms": intervention_norms,
        "arrival_successes": arrival_successes,
        "agent": agent,
    }


def evaluate_policy(
    agent: SafePPOAgent,
    shield_enabled: bool,
    num_eval_episodes: int = 15,
    seed: int = 101,
) -> dict[str, Any]:
    """Evaluates policy on deterministic test episodes with dynamic obstacles."""
    env = Safe6DOFQuadrotorEnv(
        shield_enabled=shield_enabled,
        enable_deep_aero=True,
        max_steps=100,
    )
    rng = np.random.default_rng(seed)

    success_count = 0
    collision_count = 0
    trajectories = []
    obstacle_trajectories = []
    final_distances = []

    for ep in range(num_eval_episodes):
        obs = env.reset(rng=rng)
        drone_path = []
        dyn_obs_path = []

        for _ in range(100):
            action, _, _ = agent.select_action(obs, deterministic=True)
            obs, _, terminated, truncated, info = env.step(action)

            drone_path.append([float(x) for x in info["drone_pos"]])
            dyn_obs_path.append([[float(x) for x in d.center] for d in env.dynamic_obstacles])

            if info["collision"]:
                collision_count += 1
                if not shield_enabled:
                    break

            if info["arrived"]:
                success_count += 1
                break

            if terminated or truncated:
                break

        if ep == 0:
            trajectories = drone_path
            obstacle_trajectories = dyn_obs_path
        final_distances.append(float(info["distance"]))

    return {
        "success_rate_pct": float(success_count / num_eval_episodes * 100.0),
        "collision_count": collision_count,
        "mean_final_distance_m": float(np.mean(final_distances)),
        "sample_trajectory": trajectories,
        "sample_dynamic_obs_trajectory": obstacle_trajectories,
    }


def main() -> None:
    print("=" * 70)
    print("NEXVIA AEGIS — Safe Reinforcement Learning (Safe RL) Benchmark")
    print("Continuous 6-DOF Quadrotor Navigation under Dynamic Obstacles")
    print("=" * 70)

    # 1. Train Unshielded Vanilla RL
    print("\n[1/3] Training Unshielded Vanilla PPO (No Safety Shield)...")
    res_unshielded = train_policy(shield_enabled=False, num_episodes=30, seed=42)
    print(f"  Unshielded Cumulative Collisions during Training: {res_unshielded['cumulative_collisions'][-1]}")
    print(f"  Final 5-ep Mean Reward: {np.mean(res_unshielded['episode_rewards'][-5:]):.2f}")

    # 2. Train HOCBF-Shielded Safe RL
    print("\n[2/3] Training HOCBF-Shielded Safe PPO (AEGIS Shielded RL)...")
    res_shielded = train_policy(shield_enabled=True, num_episodes=30, seed=42)
    print(f"  AEGIS Shielded Cumulative Collisions during Training: {res_shielded['cumulative_collisions'][-1]}")
    print(f"  Final 5-ep Mean Reward: {np.mean(res_shielded['episode_rewards'][-5:]):.2f}")
    print(f"  Mean Shield Intervention Decay: {res_shielded['intervention_norms'][0]:.3f} -> {res_shielded['intervention_norms'][-1]:.3f}")

    # 3. Evaluate Both Policies on Test Scenarios
    print("\n[3/3] Evaluating Trained Policies on Dynamic Obstacle Scenarios...")
    eval_unshielded = evaluate_policy(res_unshielded["agent"], shield_enabled=False)
    eval_shielded = evaluate_policy(res_shielded["agent"], shield_enabled=True)

    print(f"  [Unshielded PPO] Success Rate: {eval_unshielded['success_rate_pct']:.1f}%, Crashes: {eval_unshielded['collision_count']}, Mean Dist: {eval_unshielded['mean_final_distance_m']:.3f}m")
    print(f"  [AEGIS Safe RL]  Success Rate: {eval_shielded['success_rate_pct']:.1f}%, Crashes: {eval_shielded['collision_count']}, Mean Dist: {eval_shielded['mean_final_distance_m']:.3f}m")

    # Serialize results to JSON
    benchmark_payload = {
        "training": {
            "episodes": list(range(1, 31)),
            "unshielded_rewards": res_unshielded["episode_rewards"],
            "unshielded_collisions": res_unshielded["cumulative_collisions"],
            "shielded_rewards": res_shielded["episode_rewards"],
            "shielded_collisions": res_shielded["cumulative_collisions"],
            "shield_intervention_norms": res_shielded["intervention_norms"],
        },
        "evaluation": {
            "unshielded": {
                "success_rate_pct": eval_unshielded["success_rate_pct"],
                "collision_count": eval_unshielded["collision_count"],
                "mean_final_dist_m": eval_unshielded["mean_final_distance_m"],
                "sample_trajectory": eval_unshielded["sample_trajectory"],
            },
            "shielded": {
                "success_rate_pct": eval_shielded["success_rate_pct"],
                "collision_count": eval_shielded["collision_count"],
                "mean_final_dist_m": eval_shielded["mean_final_distance_m"],
                "sample_trajectory": eval_shielded["sample_trajectory"],
            },
            "dynamic_obstacles_path": eval_shielded["sample_dynamic_obs_trajectory"],
            "target_pos": [1.8, 1.8, 1.2],
        },
    }

    out_file = Path("results/data/safe_rl_benchmark.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(benchmark_payload, f, indent=2)

    print(f"\n[OK] Safe RL benchmark data saved to: {out_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
