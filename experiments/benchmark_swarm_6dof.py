"""
NEXVIA AEGIS — Multi-Agent 6-DOF Quadrotor Swarm Benchmark in MuJoCo Physics.

Evaluates 5 simultaneous 6-DOF Quadrotors under:
- Continuous stochastic Ornstein-Uhlenbeck wind turbulence.
- Coordinated F=2 Byzantine spoofing attacks (Agents 3 and 4 broadcasting false targets).
- Reciprocal inter-agent collision risk and static spherical obstacles.

Architectures Evaluated:
1. SWARM_6DOF_UNSHIELDED_NAIVE: Arithmetic mean target, no safety shield.
2. SWARM_6DOF_CBF_ONLY: Arithmetic mean target + Reciprocal HOCBF.
3. SWARM_6DOF_AEGIS_BRMC: Byzantine-Resilient Martingale Consensus + Reciprocal HOCBF.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

import mujoco
import numpy as np

from aegis.multiagent.brmc_engine import (
    AgentMessage,
    ByzantineResilientMartingaleConsensus,
)
from aegis.multiagent.swarm_6dof import (
    AegisMuJoCoSwarm6DOFEnvironment,
    Swarm6DOFConfig,
)


def run_swarm_episode(
    env: AegisMuJoCoSwarm6DOFEnvironment,
    policy_type: str,
    seed: int,
    max_steps: int = 80,
    byzantine_agents: tuple[int, ...] = (3, 4),
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    st = env.reset(rng)
    cfg = env.cfg
    target = env.target_pos.copy()
    num_robots = cfg.num_robots

    # V-formation offsets
    formation_offsets = [
        np.array([0.0, 0.0, 0.0]),
        np.array([-0.6, -0.6, 0.1]),
        np.array([0.6, -0.6, -0.1]),
        np.array([-1.2, -1.2, 0.2]),
        np.array([1.2, -1.2, -0.2]),
    ]

    brmc = ByzantineResilientMartingaleConsensus(
        num_agents=num_robots,
        max_byzantine_faults=len(byzantine_agents),
        alpha_swarm=0.05,
    )

    inter_agent_collisions_total = 0
    obstacle_collisions_total = 0
    max_tilts_observed = [0.0] * num_robots
    fused_errors = []
    quarantined_agents_set = set()

    for step in range(max_steps):
        positions = st["positions"]
        velocities = st["velocities"]

        # Track collisions and tilts
        if st["inter_agent_collisions"] > 0:
            inter_agent_collisions_total += st["inter_agent_collisions"]
        if any(st["obstacle_collisions"]):
            obstacle_collisions_total += sum(st["obstacle_collisions"])
        for i, t_deg in enumerate(st["tilts_deg"]):
            max_tilts_observed[i] = max(max_tilts_observed[i], t_deg)

        # 1. Message Broadcast
        msgs = []
        for i in range(num_robots):
            if i in byzantine_agents:
                # Byzantine coordinated attack: false target with offset (+2.5, -2.5, 0.8)
                spoof_target = target + np.array([2.5, -2.5, 0.8])
                wealth = 30.0 + step * 2.5
                msgs.append(AgentMessage(
                    agent_id=i, step=step, pos_estimate=spoof_target, sigma=0.06, martingale_wealth=wealth,
                ))
            else:
                # Honest agent
                est_target = target + rng.normal(0, 0.05, 3)
                msgs.append(AgentMessage(
                    agent_id=i, step=step, pos_estimate=est_target, sigma=0.05, martingale_wealth=1.0,
                ))

        # 2. Consensus Determination
        if policy_type in ("SWARM_6DOF_UNSHIELDED_NAIVE", "SWARM_6DOF_CBF_ONLY"):
            # Arithmetic mean of all active messages (vulnerable to Byzantine manipulation)
            consensus_target = np.mean([m.pos_estimate for m in msgs], axis=0)
            quarantined_mask = [False] * num_robots
            shield = (policy_type == "SWARM_6DOF_CBF_ONLY")
        else:
            # AEGIS BRMC: Trimmed martingale aggregation & coordinate centerpoint
            consensus_st = brmc.aggregate_step(msgs, step)
            consensus_target = consensus_st.consensus_position
            quarantined_agents_set.update(consensus_st.quarantined_agents)
            quarantined_mask = [i in quarantined_agents_set for i in range(num_robots)]
            shield = True

        err = float(np.linalg.norm(consensus_target - target))
        fused_errors.append(err)

        # 3. Outer Formation Guidance
        desired_forces = []
        for i in range(num_robots):
            if quarantined_mask[i]:
                # Quarantined agent commanded to hover safely in place
                f = np.array([0.0, 0.0, cfg.mass * cfg.gravity]) - 1.5 * velocities[i]
            else:
                goal_i = consensus_target + formation_offsets[i]
                delta = goal_i - positions[i]
                f = 1.8 * delta - 1.2 * velocities[i]
                f[2] += cfg.mass * cfg.gravity
            desired_forces.append(f)

        st, _ = env.step_outer(
            desired_forces=desired_forces,
            shield_with_cbf=shield,
            quarantined_mask=quarantined_mask,
            rng=rng,
        )

    # Honest agents evaluation
    honest_indices = [i for i in range(num_robots) if i not in byzantine_agents]
    honest_distances = [float(np.linalg.norm(st["positions"][i] - (target + formation_offsets[i]))) for i in honest_indices]
    mean_honest_dist = float(np.mean(honest_distances))
    arrival_success = mean_honest_dist <= (cfg.target_arrival_radius + 0.15) and (obstacle_collisions_total == 0) and (inter_agent_collisions_total == 0)

    byzantine_isolated = all(b in quarantined_agents_set for b in byzantine_agents)

    return {
        "policy_type": policy_type,
        "seed": seed,
        "inter_agent_collisions": inter_agent_collisions_total,
        "obstacle_collisions": obstacle_collisions_total,
        "mean_consensus_error": round(float(np.mean(fused_errors)), 3),
        "mean_honest_dist": round(mean_honest_dist, 3),
        "arrival_success": arrival_success,
        "byzantine_isolated": byzantine_isolated,
        "avg_max_tilt_deg": round(float(np.mean(max_tilts_observed)), 1),
    }


def run_benchmark(num_episodes: int = 15) -> dict[str, Any]:
    cfg = Swarm6DOFConfig(num_robots=5, mass=1.2)
    env = AegisMuJoCoSwarm6DOFEnvironment(cfg)

    policies = [
        "SWARM_6DOF_UNSHIELDED_NAIVE",
        "SWARM_6DOF_CBF_ONLY",
        "SWARM_6DOF_AEGIS_BRMC",
    ]
    results: dict[str, list[dict[str, Any]]] = {p: [] for p in policies}

    print("=" * 82)
    print("NEXVIA AEGIS — Multi-Agent 6-DOF Quadrotor Swarm Benchmark (MuJoCo Physics)")
    print(f"5 Quadrotors on SE(3) | 20 Brushless Rotors (tau_m=35ms) | F=2 Byzantine Attacks")
    print(f"Episodes: {num_episodes} per policy | Continuous Ornstein-Uhlenbeck Wind")
    print("=" * 82)

    for pol in policies:
        for seed in range(num_episodes):
            res = run_swarm_episode(env, pol, seed=seed)
            results[pol].append(res)

    summary = {}
    print(f"{'Policy Architecture':<28} | {'Inter-Drone Col':<16} | {'Obstacle Col':<13} | {'Consensus Err':<14} | {'Success Rate':<12}")
    print("-" * 92)

    for pol in policies:
        res_list = results[pol]
        n = len(res_list)
        inter_col_rate = sum(1 for r in res_list if r["inter_agent_collisions"] > 0) / n * 100.0
        obs_col_rate = sum(1 for r in res_list if r["obstacle_collisions"] > 0) / n * 100.0
        avg_err = float(np.mean([r["mean_consensus_error"] for r in res_list]))
        succ_rate = sum(1 for r in res_list if r["arrival_success"]) / n * 100.0
        byz_rate = sum(1 for r in res_list if r["byzantine_isolated"]) / n * 100.0

        summary[pol] = {
            "episodes": n,
            "inter_agent_collision_rate_pct": round(inter_col_rate, 1),
            "obstacle_collision_rate_pct": round(obs_col_rate, 1),
            "mean_consensus_error_m": round(avg_err, 3),
            "mission_success_rate_pct": round(succ_rate, 1),
            "byzantine_quarantine_rate_pct": round(byz_rate, 1),
        }
        print(f"{pol:<28} | {inter_col_rate:>14.1f}% | {obs_col_rate:>11.1f}% | {avg_err:>12.3f}m | {succ_rate:>10.1f}%")

    print("=" * 92)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=15)
    args = parser.parse_args()

    summary = run_benchmark(num_episodes=args.episodes)
    out_file = Path("results/swarm_6dof_benchmark.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Artifact saved to {out_file}")
