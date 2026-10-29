"""
NEXVIA AEGIS — Phase 3: Comprehensive Multi-Agent 3D Swarm Resilience Benchmark.

Evaluates 3D Aerial Swarm Performance in MuJoCo Physics under:
1. Nominal conditions with stochastic aerodynamic wind turbulence.
2. Single stealthy Byzantine drift (F=1).
3. Coordinated colluding Byzantine spatial spoofing (F=2).
4. Byzantine Martingale Wealth Denial-of-Service (DoS) injection (F=2).
5. Wireless mesh communication packet loss (25% dropout rate).

Policy Architectures Compared:
1. SWARM_UNSHIELDED_NAIVE: No CBF + Sample Mean Consensus.
2. SWARM_CBF_NAIVE: Swarm CBF + Sample Mean Consensus.
3. SWARM_AEGIS_DECENTRALIZED_BRMC: Decentralized AegisDecentralizedSwarmAgent
   with Reciprocal HOCBF + Coordinate-Trimmed Ville BRMC.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np

from aegis.env.mujoco_swarm_3d import AegisMuJoCoSwarm3DEnvironment, Swarm3DConfig
from aegis.multiagent.brmc_engine import AgentMessage
from aegis.multiagent.swarm_agent import AegisDecentralizedSwarmAgent
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading


def run_phase3_swarm_episode(
    env: AegisMuJoCoSwarm3DEnvironment,
    policy_type: str,
    threat_model: str,  # "NOMINAL", "BYZANTINE_DRIFT_F1", "COLLUDING_BYZANTINE_F2", "WEALTH_DOS_F2", "PACKET_LOSS_25"
    seed: int,
    max_steps: int = 250,
) -> dict:
    rng = np.random.default_rng(seed)
    st = env.reset(rng)
    target = env.target_pos.copy()
    num_robots = env.config.num_robots
    assert num_robots >= 5, "Swarm benchmark requires at least 5 robots."

    # Determine Byzantine agents based on threat model
    byzantine_agents: set[int] = set()
    if threat_model == "BYZANTINE_DRIFT_F1":
        byzantine_agents = {num_robots - 1}
    elif threat_model in ("COLLUDING_BYZANTINE_F2", "WEALTH_DOS_F2"):
        byzantine_agents = {num_robots - 2, num_robots - 1}

    packet_loss_prob = 0.25 if threat_model == "PACKET_LOSS_25" else 0.0

    # Instantiate decentralized swarm agents if using AEGIS architecture
    agents = []
    if policy_type == "SWARM_AEGIS_DECENTRALIZED_BRMC":
        agents = [
            AegisDecentralizedSwarmAgent(
                agent_id=i,
                num_swarm_agents=num_robots,
                max_byzantine_faults=2,
                alpha_swarm=0.05,
                packet_drop_prob=packet_loss_prob,
                config=env.config,
            )
            for i in range(num_robots)
        ]

    # Symmetric inspection formation offsets (radius = 0.65m around target)
    formation_radius = 0.65
    offsets = [
        np.array([
            formation_radius * math.cos(2 * math.pi * i / num_robots),
            formation_radius * math.sin(2 * math.pi * i / num_robots),
            0.10 * math.sin(math.pi * i / 2.0),
        ], dtype=np.float64)
        for i in range(num_robots)
    ]

    obstacle_collision = False
    inter_agent_collision = False
    false_alarm = False
    byzantine_isolated_count = 0
    final_error = 0.0
    success = False
    steps_taken = 0

    # Running message pool for broadcast
    last_messages: list[AgentMessage] = []

    for t in range(max_steps):
        steps_taken = t + 1
        positions = st["positions"]
        velocities = st["velocities"]

        # 1. Message Generation and Exchange
        current_messages = []
        for i in range(num_robots):
            pos_i = positions[i]
            vel_i = velocities[i]

            if i in byzantine_agents:
                if threat_model == "WEALTH_DOS_F2":
                    # Byzantine DoS: inject normal position but astronomical wealth
                    current_messages.append(AgentMessage(
                        agent_id=i, step=t,
                        pos_estimate=target + rng.normal(0.0, 0.08, size=3),
                        sigma=0.08, martingale_wealth=15000.0,
                    ))
                else:
                    # Spatial Spoofing: coordinated fake offset
                    spoof_offset = np.array([2.8, -2.5, 1.2]) if threat_model == "COLLUDING_BYZANTINE_F2" else np.array([0.3 * (t / 15.0) + 1.5, -1.8, 0.8])
                    current_messages.append(AgentMessage(
                        agent_id=i, step=t,
                        pos_estimate=target + spoof_offset,
                        sigma=0.08, martingale_wealth=1.0,
                    ))
            else:
                # Honest agent
                est_target = target + rng.normal(0.0, 0.06, size=3)
                current_messages.append(AgentMessage(
                    agent_id=i, step=t,
                    pos_estimate=est_target,
                    sigma=0.06, martingale_wealth=1.0,
                ))

        # 2. Control Execution
        if policy_type == "SWARM_UNSHIELDED_NAIVE":
            # Naive arithmetic mean of all messages (vulnerable to Byzantine spoofing)
            fused_target = np.mean([m.pos_estimate for m in current_messages], axis=0)
            final_error = float(np.linalg.norm(fused_target - target))

            des_u = []
            for i in range(num_robots):
                target_i = fused_target + offsets[i]
                u = 2.2 * (target_i - positions[i]) - 2.5 * velocities[i]
                des_u.append(u)

            # Bypass CBF filter completely: manual physics step
            c = env.config
            drag = 0.15
            for i, bid in enumerate(env.robot_body_ids):
                f_app = np.clip(des_u[i], -c.control_force_limit, c.control_force_limit)
                f_app[2] += c.robot_mass * 9.81
                f_app += -drag * (velocities[i] - env.wind_velocity)
                env.data.xfrc_applied[bid, :3] = f_app

            import mujoco
            mujoco.mj_step(env.model, env.data)
            env.step_count += 1
            st = env.get_state()

            # Manual physical collision checks
            min_obs = min(min(float(np.linalg.norm(p - o.center) - (c.robot_radius + o.radius)) for o in env.obstacles) for p in st["positions"])
            min_inter = float("inf")
            for i in range(num_robots):
                for j in range(i + 1, num_robots):
                    cl = float(np.linalg.norm(st["positions"][i] - st["positions"][j])) - 2.0 * c.robot_radius
                    if cl < min_inter:
                        min_inter = cl

            if min_obs < 0.0:
                obstacle_collision = True
            if min_inter < 0.0:
                inter_agent_collision = True

        elif policy_type == "SWARM_CBF_NAIVE":
            # Swarm CBF shielded, but uses naive sample mean for target
            fused_target = np.mean([m.pos_estimate for m in current_messages], axis=0)
            final_error = float(np.linalg.norm(fused_target - target))

            des_u = []
            for i in range(num_robots):
                target_i = fused_target + offsets[i]
                u = 2.2 * (target_i - positions[i]) - 2.5 * velocities[i]
                des_u.append(u)

            st = env.step(des_u)
            if st["collision_obstacle"]:
                obstacle_collision = True
            if st["collision_inter_agent"]:
                inter_agent_collision = True

        elif policy_type == "SWARM_AEGIS_DECENTRALIZED_BRMC":
            # True Decentralized AEGIS Multi-Agent Swarm with Reciprocal CBF & BRMC
            agent_controls = []
            consensus_targets = []

            for i in range(num_robots):
                ag = agents[i]
                # 1. Peer message reception & BRMC fusion
                c_state = ag.receive_and_fuse_peer_messages(current_messages, step=t, rng=rng)
                consensus_targets.append(c_state.consensus_position)

                # Check false alarms (quarantining honest agents)
                for q_id in c_state.quarantined_agents:
                    if q_id not in byzantine_agents:
                        false_alarm = True

                # 2. Local sensor readings
                delta_true = target - positions[i]
                dist_true = float(np.linalg.norm(delta_true))
                rd_a = SensorReading(estimate=delta_true + rng.normal(0.0, 0.05, size=3), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))
                rd_b = SensorReading(estimate=delta_true + rng.normal(0.0, 0.05, size=3), sigma=0.05, valid=True, anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))
                rg = RangeReading(distance=dist_true + float(rng.normal(0.0, 0.04)), sigma=0.04, valid=True, dropped=False)

                # 3. Local control step
                u_safe_i, telem_i, _ = ag.step_control(
                    local_pos=positions[i],
                    local_vel=velocities[i],
                    peer_positions=positions,
                    peer_velocities=velocities,
                    obstacles=env.obstacles,
                    formation_offset=offsets[i],
                    reading_a=rd_a,
                    reading_b=rd_b,
                    range_reading=rg,
                    wind_velocity=env.wind_velocity,
                    step=t,
                )
                agent_controls.append(u_safe_i)

            # Step physical environment with decentralized controls
            st = env.step(agent_controls)
            if st["collision_obstacle"]:
                obstacle_collision = True
            if st["collision_inter_agent"]:
                inter_agent_collision = True

            # Track average consensus error among honest agents
            honest_targets = [consensus_targets[idx] for idx in range(num_robots) if idx not in byzantine_agents]
            final_error = float(np.linalg.norm(np.mean(honest_targets, axis=0) - target))

            # Check if Byzantine agents were quarantined by all honest agents
            if byzantine_agents:
                all_isolated = all(
                    byz_id in agents[h_id].local_brmc.quarantine_registry
                    for h_id in range(num_robots) if h_id not in byzantine_agents
                    for byz_id in byzantine_agents
                )
                if all_isolated:
                    byzantine_isolated_count += 1

        # Check Swarm Mission Success Condition:
        # Honest swarm centroid distance < 0.35m from target, final_error < 0.15m, and zero physical collisions!
        honest_positions = [st["positions"][idx] for idx in range(num_robots) if idx not in byzantine_agents]
        swarm_centroid_dist = float(np.linalg.norm(np.mean(honest_positions, axis=0) - target))
        if swarm_centroid_dist < 0.35 and final_error < 0.15 and not (obstacle_collision or inter_agent_collision):
            success = True
            break

    return {
        "policy": policy_type,
        "threat_model": threat_model,
        "seed": seed,
        "steps": steps_taken,
        "final_error": round(final_error, 4),
        "obstacle_collision": int(obstacle_collision),
        "inter_agent_collision": int(inter_agent_collision),
        "any_collision": int(obstacle_collision or inter_agent_collision),
        "false_alarm": int(false_alarm),
        "byzantine_isolated": int(byzantine_isolated_count > 0 or len(byzantine_agents) == 0),
        "success": int(success),
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 3 Multi-Agent 3D Swarm Resilience Benchmark")
    parser.add_argument("--n-seeds", type=int, default=10, help="Number of matched seeds per condition")
    parser.add_argument("--seed-start", type=int, default=66000, help="Starting random seed")
    parser.add_argument("--max-steps", type=int, default=250, help="Maximum steps per episode")
    args = parser.parse_args()

    env = AegisMuJoCoSwarm3DEnvironment(Swarm3DConfig(num_robots=7))
    seeds = range(args.seed_start, args.seed_start + args.n_seeds)

    threat_models = [
        "NOMINAL",
        "BYZANTINE_DRIFT_F1",
        "COLLUDING_BYZANTINE_F2",
        "WEALTH_DOS_F2",
        "PACKET_LOSS_25",
    ]

    policies = [
        "SWARM_UNSHIELDED_NAIVE",
        "SWARM_CBF_NAIVE",
        "SWARM_AEGIS_DECENTRALIZED_BRMC",
    ]

    print("=" * 88)
    print("NEXVIA AEGIS — PHASE 3: MULTI-AGENT 3D SWARM RESILIENCE & BRMC BENCHMARK")
    print(f"Robots N = 7 | Timestep dt = 0.02s | Wind: Ornstein-Uhlenbeck (sigma=0.15)")
    print("=" * 88)

    for pol in policies:
        print(f"\n>>> POLICY ARCHITECTURE: {pol}")
        for threat in threat_models:
            n_tot = 0
            n_succ = 0
            n_obs_col = 0
            n_inter_col = 0
            n_any_col = 0
            n_fa = 0
            n_byz_iso = 0
            errors = []

            for s in seeds:
                res = run_phase3_swarm_episode(env, pol, threat, s, max_steps=args.max_steps)
                n_tot += 1
                n_succ += res["success"]
                n_obs_col += res["obstacle_collision"]
                n_inter_col += res["inter_agent_collision"]
                n_any_col += res["any_collision"]
                n_fa += res["false_alarm"]
                n_byz_iso += res["byzantine_isolated"]
                errors.append(res["final_error"])

            tsr = 100.0 * n_succ / n_tot
            col_rate = 100.0 * n_any_col / n_tot
            mean_err = float(np.mean(errors))
            iso_rate = 100.0 * n_byz_iso / n_tot

            print(f"  [{threat:<24}] TSR: {tsr:5.1f}% | Collisions: {col_rate:5.1f}% | Mean Error: {mean_err:.4f}m | Isolated: {iso_rate:5.1f}% | False Alarms: {n_fa}/{n_tot}")


if __name__ == "__main__":
    main()
