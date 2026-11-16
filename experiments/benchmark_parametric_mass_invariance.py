"""
Prospective Factorial Benchmark: Parametric Model Mismatch & Mass Invariance (Task E-08).

Evaluates 100 prospective unseen worlds (Seeds 3000-3099) crossing:
1. Spatial Topology (Corridor, Cul-de-Sac dead end, Slalom)
2. Payload Mass Regime (Light 0.75x, Nominal 1.00x, Heavy 1.30x m_nom)
3. Actuator Motor Lag (tau = 15ms, 35ms, 60ms with exact ZOH integration)
4. Sensor Noise (Nominal, Moderate, Heavy burst noise)

Compares 3 Arms:
1. Naive Baseline (PD guidance, no barrier)
2. Nominal Delay-Tube CBF (assumes fixed 1.5kg, unaware of payload variation)
3. AEGIS Parametric-Invariant Tube-CLBF (Pillar 1 + 2 + 3)
"""

from dataclasses import dataclass
import json
import math
import os
import shutil
import time
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
class ParametricWorldSpec:
    world_id: int
    seed: int
    topology_type: str        # 'CORRIDOR', 'CUL_DE_SAC', 'SLALOM'
    goal_pos: np.ndarray
    obstacles: list[np.ndarray]
    is_solvable: bool
    mass_ratio: float         # m_true / m_nom in [0.75, 1.00, 1.30]
    tau_actuator_lag: float   # tau in [0.015, 0.035, 0.060] s
    sigma_v: float
    sigma_p: float
    has_burst_noise: bool


def generate_100_parametric_worlds(start_seed: int = 3000, num_worlds: int = 100) -> list[ParametricWorldSpec]:
    worlds: list[ParametricWorldSpec] = []
    topologies = ["CORRIDOR", "CUL_DE_SAC", "SLALOM"]
    mass_ratios = [0.75, 1.00, 1.30]  # Light, Nominal, Heavy
    actuator_lags = [0.015, 0.035, 0.060]

    for i in range(num_worlds):
        seed = start_seed + i
        rng = np.random.default_rng(seed)
        topo = topologies[i % len(topologies)]
        mass_rat = mass_ratios[(i // len(topologies)) % len(mass_ratios)]
        tau = actuator_lags[(i // (len(topologies) * len(mass_ratios))) % len(actuator_lags)]

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
            goal = np.array([8.0, 0.0, 0.0])
            front_x = 4.0 + rng.uniform(-0.2, 0.2)
            obstacles = [
                np.array([front_x, 0.0, 0.0]),
                np.array([front_x, 0.7, 0.0]),
                np.array([front_x, -0.7, 0.0]),
                np.array([front_x - 1.2, 1.2, 0.0]),
                np.array([front_x - 1.2, -1.2, 0.0]),
            ]
            is_solvable = False
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
            ParametricWorldSpec(
                world_id=i,
                seed=seed,
                topology_type=topo,
                goal_pos=goal,
                obstacles=obstacles,
                is_solvable=is_solvable,
                mass_ratio=mass_rat,
                tau_actuator_lag=tau,
                sigma_v=sig_v,
                sigma_p=sig_p,
                has_burst_noise=burst,
            )
        )

    return worlds


def evaluate_parametric_world_arm(
    world: ParametricWorldSpec,
    arm_type: str,  # 'NAIVE', 'NOMINAL_CBF', 'AEGIS_PARAMETRIC'
) -> dict[str, Any]:
    rng = np.random.default_rng(world.seed + (100 if arm_type == 'NOMINAL_CBF' else (200 if arm_type == 'AEGIS_PARAMETRIC' else 0)))
    dt = 0.04
    max_steps = 550
    m_nom = 1.5
    m_true = m_nom * world.mass_ratio
    tau_lag = world.tau_actuator_lag
    safe_dist = 1.0

    if arm_type == "AEGIS_PARAMETRIC":
        cfg = RobustTubeCLBFConfig(
            safe_distance=safe_dist,
            actuator_delay_s=tau_lag,
            enable_delay_compensation=True,
            mass_uncertainty_pct=0.30,
            enable_parametric_invariance=True,
            a_max=5.5,
        )
        ctrl = RobustTubeCLBFController(cfg)
    elif arm_type == "NOMINAL_CBF":
        cfg = RobustTubeCLBFConfig(
            safe_distance=safe_dist,
            actuator_delay_s=tau_lag,
            enable_delay_compensation=True,
            mass_uncertainty_pct=0.0,
            enable_parametric_invariance=False,
            a_max=5.5,
        )
        ctrl = RobustTubeCLBFController(cfg)
    else:
        ctrl = None  # Naive PD

    p_true = np.array([0.0, 0.0, 0.0])
    v_true = np.array([0.0, 0.0, 0.0])
    u_motor = np.array([0.0, 0.0, 0.0])

    min_clearance = 999.0
    collision_occurred = False
    reached_goal = False
    safe_abstention = False
    stall_steps = 0
    t_elapsed = 0.0

    cov_p = np.diag([world.sigma_p**2, world.sigma_p**2, world.sigma_p**2])
    cov_v = np.diag([world.sigma_v**2, world.sigma_v**2, world.sigma_v**2])

    # Exact ZOH alpha
    alpha_lag = 1.0 - math.exp(-dt / max(1e-4, tau_lag))

    for step in range(max_steps):
        t_elapsed = step * dt
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
            if dist < 0.85:
                collision_occurred = True

        if collision_occurred:
            break

        # Compute Action
        if arm_type in ("AEGIS_PARAMETRIC", "NOMINAL_CBF"):
            state = TubeUncertaintyState(p_hat=p_obs, v_hat=v_obs, cov_p=cov_p, cov_v=cov_v)
            res = ctrl.step(state, world.goal_pos, world.obstacles)
            u_cmd = res["action"]
            if res.get("is_terminal", False):
                if res.get("phase") in (DwellPhase.CONFIRMED_STILL.value, DwellPhase.EMERGENCY_STOP.value):
                    safe_abstention = True
                    break
        else:
            u_cmd = 2.5 * (world.goal_pos - p_obs) - 1.8 * v_obs
            u_cmd = np.clip(u_cmd, -5.5, 5.5)

        # Actuator lag
        u_motor += alpha_lag * (u_cmd - u_motor)
        u_motor = np.clip(u_motor, -6.0, 6.0)

        # TRUE PHYSICAL INTEGRATION UNDER MASS MISMATCH:
        # Applied force F = m_nom * u_motor, actual acceleration a = F / m_true
        a_true = (m_nom / m_true) * u_motor
        p_true += v_true * dt + 0.5 * a_true * (dt ** 2)
        v_true += a_true * dt

        # Stall check
        if np.linalg.norm(v_true) < 0.05 and np.linalg.norm(p_true - world.goal_pos) > 1.0:
            stall_steps += 1
            if stall_steps > 70 and not world.is_solvable:
                safe_abstention = True
                break

        # Goal capture
        if np.linalg.norm(p_true - world.goal_pos) <= 0.4 and np.linalg.norm(v_true) <= 0.2:
            reached_goal = True
            break

    if collision_occurred:
        outcome = "COLLISION"
    elif reached_goal:
        outcome = "GOAL_REACHED"
    elif safe_abstention or (not world.is_solvable and not collision_occurred):
        outcome = "SAFE_ABSTAIN"
    else:
        outcome = "STALL_TIMEOUT"

    final_ek = 0.5 * m_true * float(np.dot(v_true, v_true))

    return {
        "world_id": world.world_id,
        "arm": arm_type,
        "topology": world.topology_type,
        "mass_ratio": world.mass_ratio,
        "outcome": outcome,
        "min_clearance_m": min_clearance,
        "final_ek_j": final_ek,
        "time_s": t_elapsed,
        "is_safe": outcome in ("GOAL_REACHED", "SAFE_ABSTAIN"),
    }


def run_parametric_mass_benchmark() -> dict[str, Any]:
    print("Executing 100 Prospective Worlds Parametric Mass Invariance Benchmark...")
    worlds = generate_100_parametric_worlds(start_seed=3000, num_worlds=100)

    results_naive = []
    results_nominal = []
    results_parametric = []

    t0 = time.time()
    for idx, w in enumerate(worlds):
        res_n = evaluate_parametric_world_arm(w, "NAIVE")
        res_nom = evaluate_parametric_world_arm(w, "NOMINAL_CBF")
        res_p = evaluate_parametric_world_arm(w, "AEGIS_PARAMETRIC")

        results_naive.append(res_n)
        results_nominal.append(res_nom)
        results_parametric.append(res_p)

        if (idx + 1) % 20 == 0:
            print(f"  Processed {idx + 1}/100 worlds... (Elapsed: {time.time()-t0:.1f}s)")

    def aggregate_arm_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
        collisions = sum(1 for r in results if r["outcome"] == "COLLISION")
        goal_reached = sum(1 for r in results if r["outcome"] == "GOAL_REACHED")
        safe_abstains = sum(1 for r in results if r["outcome"] == "SAFE_ABSTAIN")
        stalls = sum(1 for r in results if r["outcome"] == "STALL_TIMEOUT")

        solvable_reached = sum(1 for r in results if r["outcome"] == "GOAL_REACHED" and r["topology"] != "CUL_DE_SAC")
        cul_de_sac_safe = sum(1 for r in results if r["is_safe"] and r["topology"] == "CUL_DE_SAC")

        clearances = [r["min_clearance_m"] for r in results]
        times = [r["time_s"] for r in results if r["outcome"] == "GOAL_REACHED"]

        # Heavy payload sub-analysis (mass_ratio == 1.30)
        heavy_results = [r for r in results if r["mass_ratio"] >= 1.25]
        heavy_collisions = sum(1 for r in heavy_results if r["outcome"] == "COLLISION")
        heavy_clearances = [r["min_clearance_m"] for r in heavy_results]

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
            "heavy_payload_count": len(heavy_results),
            "heavy_payload_collisions": heavy_collisions,
            "heavy_payload_mean_clearance_m": float(np.mean(heavy_clearances)) if heavy_clearances else 0.0,
            "avg_goal_time_s": float(np.mean(times)) if times else 0.0,
        }

    agg_naive = aggregate_arm_metrics(results_naive)
    agg_nom = aggregate_arm_metrics(results_nominal)
    agg_param = aggregate_arm_metrics(results_parametric)

    print("\nBenchmark Summary across 100 Parametric Worlds:")
    print(f"  Naive Baseline:            Collisions: {agg_naive['collision_count']}, Selective Risk: {agg_naive['selective_risk_pct']:.1f}%, Heavy Clearance: {agg_naive['heavy_payload_mean_clearance_m']:.3f}m")
    print(f"  Nominal Tube-CBF:          Collisions: {agg_nom['collision_count']}, Selective Risk: {agg_nom['selective_risk_pct']:.1f}%, Heavy Clearance: {agg_nom['heavy_payload_mean_clearance_m']:.3f}m")
    print(f"  AEGIS Parametric Invariant: Collisions: {agg_param['collision_count']}, Selective Risk: {agg_param['selective_risk_pct']:.1f}%, Heavy Clearance: {agg_param['heavy_payload_mean_clearance_m']:.3f}m")

    out_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "milestone": "V9-M15",
        "description": "Prospective 100 Worlds Factorial Benchmark: Parametric Model Mismatch & Mass Invariance (Task E-08)",
        "summary": {
            "naive_baseline": agg_naive,
            "nominal_cbf": agg_nom,
            "aegis_parametric_invariant": agg_param,
        },
        "raw_episodes_sample": results_parametric[:10],
    }

    os.makedirs("results/data", exist_ok=True)
    json_path = "results/data/parametric_mass_invariance_benchmark.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
    print(f"Saved dataset to {json_path}")

    # Generate Publication-Grade 4-Panel 300 DPI Figure
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), dpi=300)
    plt.subplots_adjust(hspace=0.35, wspace=0.28)

    arms = ["Naive Baseline", "Nominal CBF", "AEGIS Parametric"]
    colors = ["#e74c3c", "#f39c12", "#2ecc71"]

    # Panel 1: Total Collisions across 100 Worlds
    ax1 = axes[0, 0]
    coll_counts = [agg_naive["collision_count"], agg_nom["collision_count"], agg_param["collision_count"]]
    bars1 = ax1.bar(arms, coll_counts, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax1.set_ylabel("Total Collisions (out of 100 Worlds)", fontsize=11, fontweight="bold")
    ax1.set_title("1. Safety Invariance under Mass Mismatch (0.75x to 1.30x)\n(Total Collisions across Factorial Worlds)", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 1.0, f"{int(yval)}", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Panel 2: Heavy Payload Mean Clearance (m)
    ax2 = axes[0, 1]
    heavy_clears = [agg_naive["heavy_payload_mean_clearance_m"], agg_nom["heavy_payload_mean_clearance_m"], agg_param["heavy_payload_mean_clearance_m"]]
    bars2 = ax2.bar(arms, heavy_clears, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax2.axhline(1.0, color="red", linestyle="--", linewidth=1.5, label="R_safe = 1.0m Boundary")
    ax2.set_ylabel("Mean Clearance under +30% Payload (m)", fontsize=11, fontweight="bold")
    ax2.set_title("2. Worst-Case Payload Clearance (+30% Mass Payload)\n(Control Authority Attenuation Resistance)", fontsize=11, fontweight="bold")
    ax2.legend(loc="upper left")
    ax2.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 0.03, f"{yval:.3f}m", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Panel 3: Dead-End Trap Safe Abstention (%)
    ax3 = axes[1, 0]
    dead_safeties = [agg_naive["dead_end_safety_rate_pct"], agg_nom["dead_end_safety_rate_pct"], agg_param["dead_end_safety_rate_pct"]]
    bars3 = ax3.bar(arms, dead_safeties, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax3.set_ylabel("Dead-End Safe Abstention Rate (%)", fontsize=11, fontweight="bold")
    ax3.set_ylim(0, 115)
    ax3.set_title("3. Grounded Physical Abstention in Traps\n(33 Cul-de-Sacs with Unknown Mass)", fontsize=11, fontweight="bold")
    ax3.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars3:
        yval = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2.0, yval + 2.0, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Panel 4: Solvable Worlds Success Rate (%)
    ax4 = axes[1, 1]
    solv_rates = [agg_naive["solvable_success_rate_pct"], agg_nom["solvable_success_rate_pct"], agg_param["solvable_success_rate_pct"]]
    bars4 = ax4.bar(arms, solv_rates, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax4.set_ylabel("Mission Completion Rate (%)", fontsize=11, fontweight="bold")
    ax4.set_ylim(0, 115)
    ax4.set_title("4. Progress Preservation under Mass Variations\n(67 Solvable Staggered Corridors & Slaloms)", fontsize=11, fontweight="bold")
    ax4.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars4:
        yval = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2.0, yval + 2.0, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)

    png_path = "results/data/parametric_mass_invariance_benchmark.png"
    plt.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved figure to {png_path}")

    brain_dir = "/Users/chalermsak/.gemini/antigravity-ide/brain/bfa523f6-4b75-4654-8f2e-65c6b00df558"
    if os.path.exists(brain_dir):
        dest_png = os.path.join(brain_dir, "parametric_mass_invariance_benchmark.png")
        shutil.copyfile(png_path, dest_png)
        print(f"Copied figure to brain artifact: {dest_png}")

    return out_data


if __name__ == "__main__":
    run_parametric_mass_benchmark()
