"""
experiments/export_swarm_trajectories.py — Runs 3D MuJoCo Swarm Simulation with CBF & BRMC and exports telemetry.

Outputs JSON format for the standalone 3D WebGL visualizer.
"""

from __future__ import annotations

import json
import math
import os
import sys

# Ensure src in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from aegis.env.mujoco_swarm_3d import AegisMuJoCoSwarm3DEnvironment, Swarm3DConfig
from aegis.multiagent.brmc_engine import (
    AgentMessage,
    ByzantineResilientMartingaleConsensus,
)


def export_swarm_simulation_json(
    seed: int = 91000,
    max_steps: int = 250,
    output_path: str = "results/swarm_trajectories.json",
) -> None:
    cfg = Swarm3DConfig(num_robots=5, timestep=0.02, wind_enabled=True)
    env = AegisMuJoCoSwarm3DEnvironment(cfg)
    rng = np.random.default_rng(seed)
    st = env.reset(rng)
    target = env.target_pos.copy()
    num_robots = cfg.num_robots

    byzantine_agent_id = 4
    brmc = ByzantineResilientMartingaleConsensus(
        num_agents=num_robots,
        max_byzantine_faults=1,
        alpha_swarm=0.05,
        byzantine_isolation_threshold=3.5,
    )

    agent_wealths = [1.0] * num_robots

    formation_radius = 0.55
    offsets = [
        np.array([
            formation_radius * math.cos(2 * math.pi * i / num_robots),
            formation_radius * math.sin(2 * math.pi * i / num_robots),
            0.0,
        ], dtype=np.float64)
        for i in range(num_robots)
    ]

    frames = []

    for t in range(max_steps):
        positions = st["positions"]
        velocities = st["velocities"]

        # 1. Target formation controls
        des_u = []
        for i, (p, v) in enumerate(zip(positions, velocities)):
            target_i = target + offsets[i]
            u = 2.2 * (target_i - p) - 2.8 * v
            des_u.append(u)

        # 2. Step environment with Swarm CBF
        st = env.step(des_u)

        # 3. Collaborative Sensing & BRMC Consensus
        messages = []
        for i in range(num_robots):
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

        consensus_st = brmc.aggregate_step(messages, step=t)
        fused_pos = consensus_st.consensus_position
        final_error = float(np.linalg.norm(fused_pos - target))

        # Record telemetry frame
        frame = {
            "step": t,
            "time": round(t * cfg.timestep, 3),
            "robots": [
                {
                    "id": i,
                    "pos": [round(float(coord), 4) for coord in positions[i]],
                    "vel": [round(float(coord), 4) for coord in velocities[i]],
                    "wealth": round(float(agent_wealths[i]), 3),
                    "is_byzantine": i == byzantine_agent_id,
                    "is_quarantined": i in brmc.quarantine_registry,
                    "barrier_active": bool(st["barriers_active"][i]),
                }
                for i in range(num_robots)
            ],
            "consensus_pos": [round(float(coord), 4) for coord in fused_pos],
            "consensus_error": round(final_error, 4),
            "wind": [round(float(w), 4) for w in env.wind_velocity],
            "quarantined_agents": sorted(list(brmc.quarantine_registry)),
            "swarm_alarm": bool(consensus_st.swarm_alarm),
            "min_obs_distance": round(float(st["min_obstacle_distance"]), 4),
            "min_inter_distance": round(float(st["min_inter_agent_distance"]), 4),
        }
        frames.append(frame)

    telemetry = {
        "metadata": {
            "num_robots": num_robots,
            "robot_radius": cfg.robot_radius,
            "timestep": cfg.timestep,
            "total_steps": len(frames),
            "target_pos": [round(float(c), 4) for c in target],
            "target_arrival_radius": cfg.target_arrival_radius,
            "obstacles": [
                {
                    "center": [round(float(c), 4) for c in obs.center],
                    "radius": round(float(obs.radius), 4),
                }
                for obs in env.obstacles
            ],
            "ville_threshold": brmc.wealth_threshold,
        },
        "frames": frames,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, mode="w", encoding="utf-8") as f:
        json.dump(telemetry, f, indent=2)

    print(f"[Exported Telemetry]: {output_path} ({len(frames)} frames)")


if __name__ == "__main__":
    export_swarm_simulation_json()
