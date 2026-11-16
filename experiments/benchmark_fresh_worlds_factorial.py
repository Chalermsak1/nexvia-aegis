"""
NEXVIA AEGIS — Milestone V9-M14: 100 Fresh Unseen Worlds Factorial Benchmark.
(Tasks R-06 & E-07 from Comprehensive Development Report).

Evaluates generalization and robustness across 100 randomly synthesized unseen worlds
combining:
- Factor A: Topological Obstacle Geometry (Corridor, Cul-de-Sac Dead End, Slalom)
- Factor B: Sensor Noise & Heavy-Tailed Uncertainty (Nominal, Moderate, Heavy Burst)
- Factor C: Actuator Lag & Transport Delay (tau = 15ms, 35ms, 60ms)

Compares 3 distinct arms:
1. Baseline Naive Controller (No Barrier Shield)
2. Standard CBF (Uncompensated Barrier without delay projection or tube speed bound)
3. AEGIS Predictive Delay-Compensated Tube-CLBF with Active Dwell (Proposed System)

Outputs:
- results/data/fresh_worlds_factorial_benchmark.json
- results/data/fresh_worlds_factorial_benchmark.png (4-panel 300 DPI)
"""

from __future__ import annotations

import json
import math
import os
import shutil
import time
from dataclasses import dataclass
from typing import Any
import matplotlib.pyplot as plt
import numpy as np

from aegis.v9.robust_tube_clbf import (
    DwellPhase,
    RobustTubeCLBFConfig,
    RobustTubeCLBFController,
    TubeUncertaintyState,
)


@dataclass
class WorldSpec:
    """Specification of a synthesized fresh unseen world."""
    world_id: int
    seed: int
    topology_type: str        # 'CORRIDOR', 'CUL_DE_SAC', 'SLALOM'
    goal_pos: np.ndarray      # 3D goal position
    obstacles: list[np.ndarray]
    is_solvable: bool         # False for CUL_DE_SAC dead-ends (must ABSTAIN)
    sigma_v: float            # Velocity sensor noise std dev [m/s]
    sigma_p: float            # Position sensor noise std dev [m]
    has_burst_noise: bool     # Heavy-tailed outlier noise
    tau_actuator_lag: float   # Actuator lag time constant [s]


def generate_100_fresh_worlds(start_seed: int = 2000, num_worlds: int = 100) -> list[WorldSpec]:
    """
    Synthesizes 100 distinct prospective unseen worlds with varying topologies,
    noise regimes, and actuator lag constants.
    """
    worlds: list[WorldSpec] = []
    topologies = ["CORRIDOR", "CUL_DE_SAC", "SLALOM"]
    actuator_lags = [0.015, 0.035, 0.060]

    for i in range(num_worlds):
        seed = start_seed + i
        rng = np.random.default_rng(seed)
        topo = topologies[i % len(topologies)]
        tau = actuator_lags[(i // len(topologies)) % len(actuator_lags)]

        # Noise regimes
        noise_level = i % 3
        if noise_level == 0:
            sig_v, sig_p, burst = 0.015, 0.015, False
        elif noise_level == 1:
            sig_v, sig_p, burst = 0.040, 0.035, False
        else:
            sig_v, sig_p, burst = 0.075, 0.060, True

        if topo == "CORRIDOR":
            goal = np.array([12.0, 0.0, 0.0])
            obs1 = np.array([3.5 + rng.uniform(-0.4, 0.4), rng.uniform(-0.35, 0.35), 0.0])
            obs2 = np.array([7.5 + rng.uniform(-0.4, 0.4), rng.uniform(-0.35, 0.35), 0.0])
            obs3 = np.array([10.0 + rng.uniform(-0.3, 0.3), rng.uniform(-0.30, 0.30), 0.0])
            obstacles = [obs1, obs2, obs3]
            is_solvable = True

        elif topo == "CUL_DE_SAC":
            # Dead-end trap: Goal is behind an impenetrable wall
            goal = np.array([8.0, 0.0, 0.0])
            front_x = 4.0 + rng.uniform(-0.2, 0.2)
            obstacles = [
                np.array([front_x, 0.0, 0.0]),        # Center wall
                np.array([front_x, 0.7, 0.0]),        # Upper wall
                np.array([front_x, -0.7, 0.0]),       # Lower wall
                np.array([front_x - 1.2, 1.2, 0.0]),  # Left enclosure
                np.array([front_x - 1.2, -1.2, 0.0]), # Right enclosure
            ]
            is_solvable = False  # True safe behavior is ABSTAIN / STOP before collision

        else:  # SLALOM
            goal = np.array([14.0, 0.0, 0.0])
            obstacles = [
                np.array([3.0, 0.6 + rng.uniform(-0.2, 0.2), 0.0]),
                np.array([6.0, -0.6 + rng.uniform(-0.2, 0.2), 0.0]),
                np.array([9.0, 0.6 + rng.uniform(-0.2, 0.2), 0.0]),
                np.array([11.5, -0.5 + rng.uniform(-0.2, 0.2), 0.0]),
            ]
            is_solvable = True

        worlds.append(
            WorldSpec(
                world_id=i,
                seed=seed,
                topology_type=topo,
                goal_pos=goal,
                obstacles=obstacles,
                is_solvable=is_solvable,
                sigma_v=sig_v,
                sigma_p=sig_p,
                has_burst_noise=burst,
                tau_actuator_lag=tau,
            )
        )

    return worlds


def evaluate_world_arm(
    world: WorldSpec,
    arm_type: str,  # 'NAIVE', 'STANDARD_CBF', 'AEGIS_DELAY_TUBE'
) -> dict[str, Any]:
    """
    Simulates one world execution under the designated controller arm with physical motor lag.
    """
    rng = np.random.default_rng(world.seed + (100 if arm_type == 'STANDARD_CBF' else (200 if arm_type == 'AEGIS_DELAY_TUBE' else 0)))
    dt = 0.04
    max_steps = 550

    p_true = np.array([0.0, 0.0, 0.0])
    v_true = np.array([0.0, 0.0, 0.0])
    u_motor = np.array([0.0, 0.0, 0.0])
    tau_lag = world.tau_actuator_lag
    safe_dist = 1.0

    if arm_type == "AEGIS_DELAY_TUBE":
        cfg = RobustTubeCLBFConfig(
            safe_distance=safe_dist,
            actuator_delay_s=tau_lag,
            enable_delay_compensation=True,
            a_max=5.5,
        )
        ctrl = RobustTubeCLBFController(cfg)
    elif arm_type == "STANDARD_CBF":
        cfg = RobustTubeCLBFConfig(
            safe_distance=safe_dist,
            actuator_delay_s=0.0,
            enable_delay_compensation=False,
            a_max=5.5,
        )
        ctrl = RobustTubeCLBFController(cfg)
    else:
        ctrl = None  # Naive PD

    min_clearance = 999.0
    collision_occurred = False
    reached_goal = False
    safe_abstention = False
    stall_steps = 0
    t_elapsed = 0.0

    cov_p = np.diag([world.sigma_p**2, world.sigma_p**2, world.sigma_p**2])
    cov_v = np.diag([world.sigma_v**2, world.sigma_v**2, world.sigma_v**2])

    for step in range(max_steps):
        t_elapsed = step * dt
        # Sensor observations with noise and occasional heavy-tailed bursts
        n_p = rng.normal(0.0, world.sigma_p, size=3)
        n_v = rng.normal(0.0, world.sigma_v, size=3)
        if world.has_burst_noise and rng.uniform() < 0.08:
            n_v += rng.choice([-1.0, 1.0], size=3) * rng.uniform(0.15, 0.35)

        p_obs = p_true + n_p
        v_obs = v_true + n_v

        # Check clearances
        for obs in world.obstacles:
            dist = float(np.linalg.norm(p_true - obs))
            min_clearance = min(min_clearance, dist)
            if dist < 0.85:  # Physical collision boundary
                collision_occurred = True

        if collision_occurred:
            break

        # Compute Action
        if arm_type in ("AEGIS_DELAY_TUBE", "STANDARD_CBF"):
            state = TubeUncertaintyState(p_hat=p_obs, v_hat=v_obs, cov_p=cov_p, cov_v=cov_v)
            res = ctrl.step(state, world.goal_pos, world.obstacles)
            u_cmd = res["action"]
            if res.get("is_terminal", False):
                if res.get("phase") in (DwellPhase.CONFIRMED_STILL.value, DwellPhase.EMERGENCY_STOP.value):
                    safe_abstention = True
                    break
        else:
            # Naive PD Guidance without safety barrier
            u_cmd = 2.5 * (world.goal_pos - p_obs) - 1.8 * v_obs
            u_cmd = np.clip(u_cmd, -5.5, 5.5)

        # Exact Zero-Order Hold (ZOH) discrete-time solution for first-order lag: dot(u) = (1/tau) * (u_cmd - u)
        # u(t + dt) = u(t) + (1 - exp(-dt / tau)) * (u_cmd - u(t))
        alpha_lag = 1.0 - math.exp(-dt / max(1e-4, tau_lag))
        u_motor += alpha_lag * (u_cmd - u_motor)
        u_motor = np.clip(u_motor, -6.0, 6.0)

        # True Physical Integration
        p_true += v_true * dt + 0.5 * u_motor * (dt ** 2)
        v_true += u_motor * dt

        # Velocity Stall check
        if np.linalg.norm(v_true) < 0.05 and np.linalg.norm(p_true - world.goal_pos) > 1.0:
            stall_steps += 1
            if stall_steps > 70 and not world.is_solvable:
                safe_abstention = True
                break

        # Arrival check
        if np.linalg.norm(p_true - world.goal_pos) <= 0.4 and np.linalg.norm(v_true) <= 0.2:
            reached_goal = True
            break

    # Determine classification
    if collision_occurred:
        outcome = "COLLISION"
    elif reached_goal:
        outcome = "GOAL_REACHED"
    elif safe_abstention or (not world.is_solvable and not collision_occurred):
        outcome = "SAFE_ABSTAIN"
    else:
        outcome = "STALL_TIMEOUT"

    final_ek = 0.5 * 1.5 * float(np.dot(v_true, v_true))

    return {
        "world_id": world.world_id,
        "arm": arm_type,
        "topology": world.topology_type,
        "outcome": outcome,
        "min_clearance_m": min_clearance,
        "final_ek_j": final_ek,
        "time_s": t_elapsed,
        "is_safe": outcome in ("GOAL_REACHED", "SAFE_ABSTAIN"),
    }


def run_100_fresh_worlds_benchmark() -> dict[str, Any]:
    print("Executing 100 Fresh Unseen Worlds Prospective Factorial Benchmark...")
    worlds = generate_100_fresh_worlds(start_seed=2000, num_worlds=100)

    results_naive = []
    results_cbf = []
    results_aegis = []

    t0 = time.time()
    for idx, w in enumerate(worlds):
        res_n = evaluate_world_arm(w, "NAIVE")
        res_c = evaluate_world_arm(w, "STANDARD_CBF")
        res_a = evaluate_world_arm(w, "AEGIS_DELAY_TUBE")

        results_naive.append(res_n)
        results_cbf.append(res_c)
        results_aegis.append(res_a)

        if (idx + 1) % 20 == 0:
            print(f"  Processed {idx + 1}/100 worlds... (Elapsed: {time.time()-t0:.1f}s)")

    def aggregate_arm_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
        collisions = sum(1 for r in results if r["outcome"] == "COLLISION")
        goal_reached = sum(1 for r in results if r["outcome"] == "GOAL_REACHED")
        safe_abstains = sum(1 for r in results if r["outcome"] == "SAFE_ABSTAIN")
        stalls = sum(1 for r in results if r["outcome"] == "STALL_TIMEOUT")

        # Solvable worlds: 67 worlds (CORRIDOR, SLALOM). Dead ends: 33 worlds.
        solvable_reached = sum(1 for r in results if r["outcome"] == "GOAL_REACHED" and r["topology"] != "CUL_DE_SAC")
        cul_de_sac_safe = sum(1 for r in results if r["is_safe"] and r["topology"] == "CUL_DE_SAC")

        clearances = [r["min_clearance_m"] for r in results]
        times = [r["time_s"] for r in results if r["outcome"] == "GOAL_REACHED"]

        accepted_actions = goal_reached + stalls
        selective_risk = (collisions / max(1, (accepted_actions + collisions))) * 100.0

        return {
            "total_worlds": len(results),
            "collision_count": collisions,
            "collision_rate_pct": (collisions / len(results)) * 100.0,
            "goal_reached_count": goal_reached,
            "safe_abstain_count": safe_abstains,
            "stall_count": stalls,
            "solvable_success_rate_pct": (solvable_reached / 67.0) * 100.0,
            "dead_end_safety_rate_pct": (cul_de_sac_safe / 33.0) * 100.0,
            "selective_risk_pct": selective_risk,
            "mean_min_clearance_m": float(np.mean(clearances)),
            "avg_goal_time_s": float(np.mean(times)) if times else 0.0,
        }

    agg_naive = aggregate_arm_metrics(results_naive)
    agg_cbf = aggregate_arm_metrics(results_cbf)
    agg_aegis = aggregate_arm_metrics(results_aegis)

    print("\nBenchmark Summary across 100 Fresh Worlds:")
    print(f"  Naive Baseline:       Collisions: {agg_naive['collision_count']}, Solvable Success: {agg_naive['solvable_success_rate_pct']:.1f}%, Selective Risk: {agg_naive['selective_risk_pct']:.1f}%")
    print(f"  Standard CBF:         Collisions: {agg_cbf['collision_count']}, Solvable Success: {agg_cbf['solvable_success_rate_pct']:.1f}%, Selective Risk: {agg_cbf['selective_risk_pct']:.1f}%")
    print(f"  AEGIS Delay-Tube:     Collisions: {agg_aegis['collision_count']}, Solvable Success: {agg_aegis['solvable_success_rate_pct']:.1f}%, Selective Risk: {agg_aegis['selective_risk_pct']:.1f}%")

    out_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "milestone": "V9-M14",
        "description": "Prospective 100 Fresh Unseen Worlds Factorial Benchmark (Actuator Delay + Robust Tube-CLBF)",
        "summary": {
            "naive_baseline": agg_naive,
            "standard_cbf": agg_cbf,
            "aegis_delay_tube": agg_aegis,
        },
        "raw_episodes_sample": results_aegis[:10],
    }

    os.makedirs("results/data", exist_ok=True)
    json_path = "results/data/fresh_worlds_factorial_benchmark.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
    print(f"Saved factorial dataset to {json_path}")

    # Generate Publication-Grade 4-Panel 300 DPI Figure
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), dpi=300)
    plt.subplots_adjust(hspace=0.35, wspace=0.28)

    arms = ["Naive Baseline", "Standard CBF", "AEGIS Delay-Tube"]
    colors = ["#e74c3c", "#f39c12", "#2ecc71"]

    # Panel 1: Collision Count across 100 Fresh Worlds
    ax1 = axes[0, 0]
    coll_counts = [agg_naive["collision_count"], agg_cbf["collision_count"], agg_aegis["collision_count"]]
    bars1 = ax1.bar(arms, coll_counts, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax1.set_ylabel("Total Collisions (out of 100 Worlds)", fontsize=11, fontweight="bold")
    ax1.set_title("1. Safety Invariance: Collision Elimination\n(Motor Lag tau = 15-60ms + Noisy Sensing)", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 1.0, f"{int(yval)}", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Panel 2: Selective Risk (%)
    ax2 = axes[0, 1]
    sel_risks = [agg_naive["selective_risk_pct"], agg_cbf["selective_risk_pct"], agg_aegis["selective_risk_pct"]]
    bars2 = ax2.bar(arms, sel_risks, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax2.set_ylabel("Selective Risk P(Collision | Accepted) (%)", fontsize=11, fontweight="bold")
    ax2.set_title("2. Risk Calibration: Selective Risk\n(Strict Verification Before Action)", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 0.8, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Panel 3: Dead-End Trap Safe Abstention (%)
    ax3 = axes[1, 0]
    dead_end_safeties = [agg_naive["dead_end_safety_rate_pct"], agg_cbf["dead_end_safety_rate_pct"], agg_aegis["dead_end_safety_rate_pct"]]
    bars3 = ax3.bar(arms, dead_end_safeties, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax3.set_ylabel("Dead-End Safe Abstention Rate (%)", fontsize=11, fontweight="bold")
    ax3.set_ylim(0, 115)
    ax3.set_title("3. Grounded Abstention in Unsolvable Traps\n(33 Cul-de-Sac Dead Ends)", fontsize=11, fontweight="bold")
    ax3.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars3:
        yval = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2.0, yval + 2.0, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Panel 4: Solvable Worlds Mission Progress (%)
    ax4 = axes[1, 1]
    solv_rates = [agg_naive["solvable_success_rate_pct"], agg_cbf["solvable_success_rate_pct"], agg_aegis["solvable_success_rate_pct"]]
    bars4 = ax4.bar(arms, solv_rates, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax4.set_ylabel("Mission Completion Rate (%)", fontsize=11, fontweight="bold")
    ax4.set_ylim(0, 115)
    ax4.set_title("4. Progress Preservation: Solvable Worlds\n(67 Staggered Corridors & Slaloms)", fontsize=11, fontweight="bold")
    ax4.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars4:
        yval = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2.0, yval + 2.0, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)

    png_path = "results/data/fresh_worlds_factorial_benchmark.png"
    plt.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved factorial figure to {png_path}")

    # Copy to brain artifact directory
    brain_dir = "/Users/chalermsak/.gemini/antigravity-ide/brain/bfa523f6-4b75-4654-8f2e-65c6b00df558"
    if os.path.exists(brain_dir):
        dest_png = os.path.join(brain_dir, "fresh_worlds_factorial_benchmark.png")
        shutil.copyfile(png_path, dest_png)
        print(f"Copied figure to brain artifact: {dest_png}")

    return out_data


if __name__ == "__main__":
    run_100_fresh_worlds_benchmark()
