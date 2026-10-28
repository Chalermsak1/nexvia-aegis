"""
experiments/benchmark_mujoco_swarm_3d.py — Comprehensive Benchmark for 3D Physical Swarm with CBF & BRMC.

Compares:
1. UNSHIELDED_NAIVE: No CBF + Naive Arithmetic Mean Consensus.
2. CBF_NAIVE: Swarm CBF + Naive Arithmetic Mean Consensus.
3. AEGIS_SWARM_BRMC: Swarm CBF + Byzantine-Resilient Martingale Consensus (BRMC).

Metrics Recorded:
- Obstacle Collision Rate (%)
- Inter-Agent Collision Rate (%)
- Total Physical Safety Violation Rate (%)
- Localization Error ||p_consensus - p_target|| (meters)
- False Alarm / False Quarantine Rate (%)
- Mission Completion / Success Rate (%)
"""

from __future__ import annotations

import csv
import math
import os
import sys
from typing import Dict, List, Tuple

# Ensure src in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from aegis.env.mujoco_swarm_3d import AegisMuJoCoSwarm3DEnvironment, Swarm3DConfig
from aegis.multiagent.brmc_engine import (
    AgentMessage,
    ByzantineResilientMartingaleConsensus,
)


def run_swarm_episode(
    env: AegisMuJoCoSwarm3DEnvironment,
    policy_type: str,  # "UNSHIELDED_NAIVE", "CBF_NAIVE", "AEGIS_SWARM_BRMC"
    seed: int,
    max_steps: int = 300,
) -> dict:
    rng = np.random.default_rng(seed)
    st = env.reset(rng)
    target = env.target_pos.copy()
    num_robots = env.config.num_robots

    # Byzantine Agent Configuration: Robot 4 is Byzantine
    byzantine_agent_id = 4

    brmc = None
    if policy_type == "AEGIS_SWARM_BRMC":
        brmc = ByzantineResilientMartingaleConsensus(
            num_agents=num_robots,
            max_byzantine_faults=1,
            alpha_swarm=0.05,
            byzantine_isolation_threshold=3.5,
        )

    agent_wealths = [1.0] * num_robots

    obstacle_collision = False
    inter_agent_collision = False
    false_alarm = False
    byzantine_isolated = False

    final_error = 0.0
    success = False

    # Swarm Inspection Formation offsets (radius = 0.55m around target)
    formation_radius = 0.55
    offsets = [
        np.array([
            formation_radius * math.cos(2 * math.pi * i / num_robots),
            formation_radius * math.sin(2 * math.pi * i / num_robots),
            0.0,
        ], dtype=np.float64)
        for i in range(num_robots)
    ]

    for t in range(max_steps):
        positions = st["positions"]
        velocities = st["velocities"]

        # 1. Generate local target-seeking formation control commands
        des_u = []
        for i, (p, v) in enumerate(zip(positions, velocities)):
            target_i = target + offsets[i]
            # Critically damped tracking: K_p = 2.2, K_d = 2.8
            u = 2.2 * (target_i - p) - 2.8 * v
            des_u.append(u)

        # 2. Safety shielding
        if policy_type == "UNSHIELDED_NAIVE":
            # Completely unshielded: bypass CBF filter
            c = env.config
            drag_coeff = 0.15
            for i, bid in enumerate(env.robot_body_ids):
                f_applied = np.clip(des_u[i], -c.control_force_limit, c.control_force_limit)
                f_applied[2] += c.robot_mass * 9.81
                v_rel = velocities[i] - env.wind_velocity
                f_applied += -drag_coeff * v_rel
                env.data.xfrc_applied[bid, :3] = f_applied

            import mujoco
            mujoco.mj_step(env.model, env.data)
            env.step_count += 1
            st = env.get_state()

            # Manual collision check
            min_obs = min(
                min(float(np.linalg.norm(p - obs.center) - (c.robot_radius + obs.radius)) for obs in env.obstacles)
                for p in st["positions"]
            )
            min_inter = float("inf")
            for i in range(num_robots):
                for j in range(i + 1, num_robots):
                    d_ij = float(np.linalg.norm(st["positions"][i] - st["positions"][j]))
                    cl = d_ij - 2.0 * c.robot_radius
                    if cl < min_inter:
                        min_inter = cl

            if min_obs < 0.0:
                obstacle_collision = True
            if min_inter < 0.0:
                inter_agent_collision = True

        else:
            # Shielded with Swarm CBF
            st = env.step(des_u)
            if st["collision_obstacle"]:
                obstacle_collision = True
            if st["collision_inter_agent"]:
                inter_agent_collision = True

        # 3. Collaborative Sensing & Consensus
        messages = []
        for i in range(num_robots):
            pos_i = st["positions"][i]
            # Honest sensing
            if i != byzantine_agent_id:
                noisy_est = target + rng.normal(0.0, 0.08, size=3)
                innov = float(np.linalg.norm(noisy_est - target))
                z = (innov - 0.08 * math.sqrt(3)) / 0.08
                agent_wealths[i] = max(0.01, agent_wealths[i] * math.exp(0.05 * z - 0.5 * (0.05**2)))
                messages.append(AgentMessage(
                    agent_id=i,
                    step=t,
                    pos_estimate=noisy_est,
                    sigma=0.08,
                    martingale_wealth=agent_wealths[i],
                ))
            else:
                # Byzantine agent: inject stealth drift + sporadic spoof
                drift = 0.3 * (t / 15.0) if t > 10 else 0.0
                byz_pos = target + np.array([drift + 1.5, -drift - 1.2, 0.8])
                agent_wealths[i] = agent_wealths[i] * 1.15
                messages.append(AgentMessage(
                    agent_id=i,
                    step=t,
                    pos_estimate=byz_pos,
                    sigma=0.08,
                    martingale_wealth=agent_wealths[i],
                ))

        if policy_type in ("UNSHIELDED_NAIVE", "CBF_NAIVE"):
            # Naive arithmetic average
            fused_pos = np.mean([m.pos_estimate for m in messages], axis=0)
        else:
            # AEGIS BRMC
            consensus_st = brmc.aggregate_step(messages, step=t)
            fused_pos = consensus_st.consensus_position
            if byzantine_agent_id in brmc.quarantine_registry:
                byzantine_isolated = True
            # False alarm if honest agents quarantined
            if any(honest_id in brmc.quarantine_registry for honest_id in range(num_robots) if honest_id != byzantine_agent_id):
                false_alarm = True

        final_error = float(np.linalg.norm(fused_pos - target))

        # Check swarm mission success:
        # Centroid distance < 0.30m, localization error < 0.15m, and no physical collision!
        centroid_dist = float(np.linalg.norm(np.mean(st["positions"], axis=0) - target))
        if centroid_dist < 0.30 and final_error < 0.15 and not (obstacle_collision or inter_agent_collision):
            success = True
            break

    return {
        "policy": policy_type,
        "seed": seed,
        "obstacle_collision": obstacle_collision,
        "inter_agent_collision": inter_agent_collision,
        "any_collision": obstacle_collision or inter_agent_collision,
        "false_alarm": false_alarm,
        "byzantine_isolated": byzantine_isolated,
        "final_error": final_error,
        "success": success,
        "steps": t + 1,
    }


def main():
    print("=" * 80)
    print("NEXVIA AEGIS — Multi-Agent 3D Swarm Physical Simulation Benchmark")
    print("Physics: MuJoCo continuous rigid body + HOCBF + Ornstein-Uhlenbeck Wind")
    print("Consensus: Ville Supermartingale BRMC Engine")
    print("=" * 80)

    cfg = Swarm3DConfig(num_robots=5, timestep=0.02, wind_enabled=True)
    env = AegisMuJoCoSwarm3DEnvironment(cfg)

    policies = ["UNSHIELDED_NAIVE", "CBF_NAIVE", "AEGIS_SWARM_BRMC"]
    episodes_per_policy = 50
    seeds = list(range(91000, 91000 + episodes_per_policy))

    results = []

    for pol in policies:
        print(f"\nEvaluating Policy: {pol} (N={episodes_per_policy} episodes)...")
        pol_results = []
        for s in seeds:
            res = run_swarm_episode(env, policy_type=pol, seed=s)
            pol_results.append(res)
            results.append(res)

        obs_col = sum(1 for r in pol_results if r["obstacle_collision"]) / episodes_per_policy * 100.0
        inter_col = sum(1 for r in pol_results if r["inter_agent_collision"]) / episodes_per_policy * 100.0
        any_col = sum(1 for r in pol_results if r["any_collision"]) / episodes_per_policy * 100.0
        err_mean = np.mean([r["final_error"] for r in pol_results])
        succ_rate = sum(1 for r in pol_results if r["success"]) / episodes_per_policy * 100.0
        iso_rate = sum(1 for r in pol_results if r["byzantine_isolated"]) / episodes_per_policy * 100.0

        print(f"  -> Obstacle Collisions:    {obs_col:5.1f}%")
        print(f"  -> Inter-Agent Collisions: {inter_col:5.1f}%")
        print(f"  -> Any Physical Collision: {any_col:5.1f}%")
        print(f"  -> Mean Estimation Error:  {err_mean:5.3f} m")
        print(f"  -> Byzantine Quarantined:  {iso_rate:5.1f}%")
        print(f"  -> Mission Success Rate:   {succ_rate:5.1f}%")

    out_csv = "results/benchmark_mujoco_swarm_3d.csv"
    os.makedirs("results", exist_ok=True)
    with open(out_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[Saved Swarm Benchmark Results]: {out_csv}")


if __name__ == "__main__":
    main()
