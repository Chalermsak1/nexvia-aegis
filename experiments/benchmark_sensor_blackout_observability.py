"""
Prospective Factorial Benchmark: Pure Estimated-State Sensor Blackout & Observability Gate (Tasks E-05 & E-06).

Evaluates 100 prospective unseen worlds (Seeds 4000-4099) crossing:
1. Spatial Topology (Corridor, Cul-de-Sac dead end, Slalom)
2. Observability / Blackout Regime:
   - NOMINAL: Continuous uncorrupted vision/LiDAR
   - TRANSIENT_BLACKOUT: 1.0s sensor dropout mid-course
   - SUSTAINED_BLACKOUT: Permanent sensor feed loss mid-course
3. Actuator Motor Lag (tau = 15ms, 35ms, 60ms with exact ZOH integration)
4. Payload Mass Uncertainty (+/- 30%)

Compares 3 Arms:
1. Naive Baseline (Blind PD, no barrier)
2. Standard Tube-CBF (Gate Disabled: acts blindly on drifted estimate during blackout)
3. AEGIS Observability Gate (Tasks E-05 + E-06: verifies observation reliability;
   refuses action and abstains via active dwell when covariance swells)
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
class BlackoutWorldSpec:
    world_id: int
    seed: int
    topology_type: str        # 'CORRIDOR', 'CUL_DE_SAC', 'SLALOM'
    goal_pos: np.ndarray
    obstacles: list[np.ndarray]
    is_solvable: bool
    blackout_regime: str      # 'NOMINAL', 'TRANSIENT_BLACKOUT', 'SUSTAINED_BLACKOUT'
    blackout_start_step: int  # Step when sensor feed drops out
    blackout_duration_steps: int # Duration of dropout (e.g. 25 steps = 1.0s, or 999 = permanent)
    mass_ratio: float         # Payload mass multiplier in [0.75, 1.00, 1.30]
    tau_actuator_lag: float   # Motor lag constant in [0.015, 0.035, 0.060] s
    sigma_v_nom: float
    sigma_p_nom: float


def generate_100_blackout_worlds(start_seed: int = 4000, num_worlds: int = 100) -> list[BlackoutWorldSpec]:
    worlds: list[BlackoutWorldSpec] = []
    topologies = ["CORRIDOR", "CUL_DE_SAC", "SLALOM"]
    blackout_types = ["NOMINAL", "TRANSIENT_BLACKOUT", "SUSTAINED_BLACKOUT"]
    mass_ratios = [0.85, 1.00, 1.25]
    actuator_lags = [0.015, 0.035, 0.060]

    for i in range(num_worlds):
        seed = start_seed + i
        rng = np.random.default_rng(seed)
        topo = topologies[i % len(topologies)]
        bo_type = blackout_types[(i // len(topologies)) % len(blackout_types)]
        mass_rat = mass_ratios[(i // (len(topologies) * len(blackout_types))) % len(mass_ratios)]
        tau = actuator_lags[(i // 9) % len(actuator_lags)]

        bo_start = int(rng.integers(25, 45))  # Blackout occurs between 1.0s and 1.8s
        if bo_type == "NOMINAL":
            bo_dur = 0
        elif bo_type == "TRANSIENT_BLACKOUT":
            bo_dur = 25  # 25 steps = 1.0s blackout
        else:
            bo_dur = 999  # Sustained until end of episode

        if topo == "CORRIDOR":
            goal = np.array([12.0, 0.0, 0.0])
            obs1 = np.array([3.5 + rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0.0])
            obs2 = np.array([7.5 + rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0.0])
            obs3 = np.array([10.0 + rng.uniform(-0.3, 0.3), rng.uniform(-0.25, 0.25), 0.0])
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
            BlackoutWorldSpec(
                world_id=i,
                seed=seed,
                topology_type=topo,
                goal_pos=goal,
                obstacles=obstacles,
                is_solvable=is_solvable,
                blackout_regime=bo_type,
                blackout_start_step=bo_start,
                blackout_duration_steps=bo_dur,
                mass_ratio=mass_rat,
                tau_actuator_lag=tau,
                sigma_v_nom=0.02,
                sigma_p_nom=0.02,
            )
        )

    return worlds


def evaluate_blackout_world_arm(
    world: BlackoutWorldSpec,
    arm_type: str,  # 'NAIVE', 'STANDARD_NO_GATE', 'AEGIS_OBSERVABILITY_GATE'
) -> dict[str, Any]:
    rng = np.random.default_rng(world.seed + (100 if arm_type == 'STANDARD_NO_GATE' else (200 if arm_type == 'AEGIS_OBSERVABILITY_GATE' else 0)))
    dt = 0.04
    max_steps = 550
    m_nom = 1.5
    m_true = m_nom * world.mass_ratio
    tau_lag = world.tau_actuator_lag
    safe_dist = 1.0

    if arm_type == "AEGIS_OBSERVABILITY_GATE":
        cfg = RobustTubeCLBFConfig(
            safe_distance=safe_dist,
            actuator_delay_s=tau_lag,
            enable_delay_compensation=True,
            mass_uncertainty_pct=0.30,
            enable_parametric_invariance=True,
            enable_observability_gate=True,
            max_position_uncertainty_m=0.25,
            max_velocity_uncertainty_mps=0.35,
            a_max=5.5,
        )
        ctrl = RobustTubeCLBFController(cfg)
    elif arm_type == "STANDARD_NO_GATE":
        cfg = RobustTubeCLBFConfig(
            safe_distance=safe_dist,
            actuator_delay_s=tau_lag,
            enable_delay_compensation=True,
            mass_uncertainty_pct=0.30,
            enable_parametric_invariance=True,
            enable_observability_gate=False,  # Unaware of observation reliability
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
    blackout_abstention = False
    stall_steps = 0
    t_elapsed = 0.0

    alpha_lag = 1.0 - math.exp(-dt / max(1e-4, tau_lag))

    # Dead-reckoning drift accumulator during blackout
    dead_reckon_drift = np.zeros(3)

    for step in range(max_steps):
        t_elapsed = step * dt

        # Determine if currently in blackout window
        in_blackout = (
            world.blackout_regime != "NOMINAL"
            and world.blackout_start_step <= step < (world.blackout_start_step + world.blackout_duration_steps)
        )

        if not in_blackout:
            # Nominal sensor visibility: low covariance, zero drift
            sig_p = world.sigma_p_nom
            sig_v = world.sigma_v_nom
            dead_reckon_drift *= 0.8  # Recovered sensor feed resets drift
            p_obs = p_true + rng.normal(0.0, sig_p, size=3) + dead_reckon_drift
            v_obs = v_true + rng.normal(0.0, sig_v, size=3)
        else:
            # SENSOR BLACKOUT: Optical lens glare / smoke / GPS denial
            # State estimation operates open-loop dead-reckoning; covariance swells quadratically
            bo_elapsed_s = (step - world.blackout_start_step) * dt
            sig_p = world.sigma_p_nom + 0.45 * bo_elapsed_s
            sig_v = world.sigma_v_nom + 0.30 * bo_elapsed_s
            # Random physical drift accumulates without sensor correction
            dead_reckon_drift += rng.normal(0.0, 0.04 * dt, size=3)
            p_obs = p_true + dead_reckon_drift
            v_obs = v_true + rng.normal(0.0, 0.02, size=3)

        cov_p = np.diag([sig_p**2, sig_p**2, sig_p**2])
        cov_v = np.diag([sig_v**2, sig_v**2, sig_v**2])

        # Physical clearance check (evaluated on ground truth, strictly external)
        for obs in world.obstacles:
            dist = float(np.linalg.norm(p_true - obs))
            min_clearance = min(min_clearance, dist)
            if dist < 0.85:
                collision_occurred = True

        if collision_occurred:
            break

        # Compute Action (Controller receives ONLY estimated state, ZERO ground truth - Task E-05)
        if arm_type in ("AEGIS_OBSERVABILITY_GATE", "STANDARD_NO_GATE"):
            state = TubeUncertaintyState(p_hat=p_obs, v_hat=v_obs, cov_p=cov_p, cov_v=cov_v)
            res = ctrl.step(state, world.goal_pos, world.obstacles)
            u_cmd = res["action"]

            if res.get("is_terminal", False):
                if res.get("reason") == "OBSERVATION_UNRELIABLE_BLACKOUT_GATE_REJECTED":
                    blackout_abstention = True
                    safe_abstention = True
                elif res.get("phase") in (DwellPhase.CONFIRMED_STILL.value, DwellPhase.EMERGENCY_STOP.value):
                    safe_abstention = True
                break
        else:
            u_cmd = 2.5 * (world.goal_pos - p_obs) - 1.8 * v_obs
            u_cmd = np.clip(u_cmd, -5.5, 5.5)

        # Actuator lag dynamics
        u_motor += alpha_lag * (u_cmd - u_motor)
        u_motor = np.clip(u_motor, -6.0, 6.0)

        # True physical integration
        a_true = (m_nom / m_true) * u_motor
        p_true += v_true * dt + 0.5 * a_true * (dt ** 2)
        v_true += a_true * dt

        # Velocity Stall check
        if np.linalg.norm(v_true) < 0.05 and np.linalg.norm(p_true - world.goal_pos) > 1.0:
            stall_steps += 1
            if stall_steps > 70 and not world.is_solvable:
                safe_abstention = True
                break

        # Goal arrival check
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
        "blackout_regime": world.blackout_regime,
        "outcome": outcome,
        "blackout_abstention": blackout_abstention,
        "min_clearance_m": min_clearance,
        "final_ek_j": final_ek,
        "time_s": t_elapsed,
        "is_safe": outcome in ("GOAL_REACHED", "SAFE_ABSTAIN"),
    }


def run_sensor_blackout_benchmark() -> dict[str, Any]:
    print("Executing 100 Prospective Worlds Sensor Blackout & Observability Gate Benchmark...")
    worlds = generate_100_blackout_worlds(start_seed=4000, num_worlds=100)

    results_naive = []
    results_standard = []
    results_aegis = []

    t0 = time.time()
    for idx, w in enumerate(worlds):
        res_n = evaluate_blackout_world_arm(w, "NAIVE")
        res_s = evaluate_blackout_world_arm(w, "STANDARD_NO_GATE")
        res_a = evaluate_blackout_world_arm(w, "AEGIS_OBSERVABILITY_GATE")

        results_naive.append(res_n)
        results_standard.append(res_s)
        results_aegis.append(res_a)

        if (idx + 1) % 20 == 0:
            print(f"  Processed {idx + 1}/100 worlds... (Elapsed: {time.time()-t0:.1f}s)")

    def aggregate_arm_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
        collisions = sum(1 for r in results if r["outcome"] == "COLLISION")
        goal_reached = sum(1 for r in results if r["outcome"] == "GOAL_REACHED")
        safe_abstains = sum(1 for r in results if r["outcome"] == "SAFE_ABSTAIN")
        stalls = sum(1 for r in results if r["outcome"] == "STALL_TIMEOUT")

        # Blackout-specific sub-analysis (66 worlds with Transient or Sustained blackout)
        bo_results = [r for r in results if r["blackout_regime"] != "NOMINAL"]
        bo_collisions = sum(1 for r in bo_results if r["outcome"] == "COLLISION")
        bo_abstains = sum(1 for r in bo_results if r["outcome"] == "SAFE_ABSTAIN")
        bo_clearances = [r["min_clearance_m"] for r in bo_results]

        # Nominal continuous worlds (34 worlds)
        nom_results = [r for r in results if r["blackout_regime"] == "NOMINAL"]
        nom_reached = sum(1 for r in nom_results if r["outcome"] == "GOAL_REACHED" and r["topology"] != "CUL_DE_SAC")
        nom_solvable_count = sum(1 for r in nom_results if r["topology"] != "CUL_DE_SAC")

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
            "blackout_worlds_count": len(bo_results),
            "blackout_collisions": bo_collisions,
            "blackout_collision_rate_pct": (bo_collisions / len(bo_results)) * 100.0 if bo_results else 0.0,
            "blackout_safe_abstain_count": bo_abstains,
            "blackout_mean_clearance_m": float(np.mean(bo_clearances)) if bo_clearances else 0.0,
            "nominal_solvable_success_rate_pct": (nom_reached / max(1, nom_solvable_count)) * 100.0,
            "selective_risk_pct": selective_risk,
            "mean_min_clearance_m": float(np.mean(clearances)),
            "avg_goal_time_s": float(np.mean(times)) if times else 0.0,
        }

    agg_naive = aggregate_arm_metrics(results_naive)
    agg_standard = aggregate_arm_metrics(results_standard)
    agg_aegis = aggregate_arm_metrics(results_aegis)

    print("\nBenchmark Summary across 100 Blackout Worlds:")
    print(f"  Naive Baseline:       Total Crashes: {agg_naive['collision_count']}, Blackout Crashes: {agg_naive['blackout_collisions']}/66 ({agg_naive['blackout_collision_rate_pct']:.1f}%), Blackout Clearance: {agg_naive['blackout_mean_clearance_m']:.3f}m")
    print(f"  Standard (No Gate):   Total Crashes: {agg_standard['collision_count']}, Blackout Crashes: {agg_standard['blackout_collisions']}/66 ({agg_standard['blackout_collision_rate_pct']:.1f}%), Blackout Clearance: {agg_standard['blackout_mean_clearance_m']:.3f}m")
    print(f"  AEGIS Observability:  Total Crashes: {agg_aegis['collision_count']}, Blackout Crashes: {agg_aegis['blackout_collisions']}/66 ({agg_aegis['blackout_collision_rate_pct']:.1f}%), Blackout Clearance: {agg_aegis['blackout_mean_clearance_m']:.3f}m")

    out_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "milestone": "V9-M16",
        "description": "Prospective 100 Worlds Factorial Benchmark: Sensor Blackout & Observability Gate (Tasks E-05 & E-06)",
        "summary": {
            "naive_baseline": agg_naive,
            "standard_no_gate": agg_standard,
            "aegis_observability_gate": agg_aegis,
        },
        "raw_episodes_sample": results_aegis[:10],
    }

    os.makedirs("results/data", exist_ok=True)
    json_path = "results/data/sensor_blackout_observability_benchmark.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
    print(f"Saved dataset to {json_path}")

    # Generate Publication-Grade 4-Panel 300 DPI Figure
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), dpi=300)
    plt.subplots_adjust(hspace=0.35, wspace=0.28)

    arms = ["Naive Baseline", "Standard (No Gate)", "AEGIS Observability"]
    colors = ["#e74c3c", "#f39c12", "#2ecc71"]

    # Panel 1: Blackout Collision Rate (%)
    ax1 = axes[0, 0]
    bo_coll_rates = [agg_naive["blackout_collision_rate_pct"], agg_standard["blackout_collision_rate_pct"], agg_aegis["blackout_collision_rate_pct"]]
    bars1 = ax1.bar(arms, bo_coll_rates, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax1.set_ylabel("Blackout Collision Rate (%)", fontsize=11, fontweight="bold")
    ax1.set_title("1. Blind Collision Prevention under Sensor Blackout\n(66 Worlds with Lens Flare / Smoke / GPS Loss)", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 1.5, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Panel 2: Mean Clearance during Blackout (m)
    ax2 = axes[0, 1]
    bo_clears = [agg_naive["blackout_mean_clearance_m"], agg_standard["blackout_mean_clearance_m"], agg_aegis["blackout_mean_clearance_m"]]
    bars2 = ax2.bar(arms, bo_clears, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax2.axhline(1.0, color="red", linestyle="--", linewidth=1.5, label="R_safe = 1.0m Boundary")
    ax2.set_ylabel("Mean Clearance in Blackout (m)", fontsize=11, fontweight="bold")
    ax2.set_title("2. Safe Distance Preservation in Degraded Sensing\n(Active Deceleration vs Blind Drift)", fontsize=11, fontweight="bold")
    ax2.legend(loc="upper left")
    ax2.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 0.03, f"{yval:.3f}m", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Panel 3: Grounded Safe Abstention Rate (%)
    ax3 = axes[1, 0]
    safe_abstains = [agg_naive["safe_abstain_count"], agg_standard["safe_abstain_count"], agg_aegis["safe_abstain_count"]]
    bars3 = ax3.bar(arms, safe_abstains, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax3.set_ylabel("Safe Physical Abstentions (out of 100 Worlds)", fontsize=11, fontweight="bold")
    ax3.set_title("3. Grounded Physical Abstention in Unsafe Conditions\n(Cul-de-Sacs + Unreliable Observability Streams)", fontsize=11, fontweight="bold")
    ax3.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars3:
        yval = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2.0, yval + 1.5, f"{int(yval)}", ha="center", va="bottom", fontweight="bold", fontsize=10)

    # Panel 4: Selective Risk (%)
    ax4 = axes[1, 1]
    sel_risks = [agg_naive["selective_risk_pct"], agg_standard["selective_risk_pct"], agg_aegis["selective_risk_pct"]]
    bars4 = ax4.bar(arms, sel_risks, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
    ax4.set_ylabel("Selective Risk P(Collision | Accepted) (%)", fontsize=11, fontweight="bold")
    ax4.set_title("4. Observation Verification Risk Control\n(Reject Action when Covariance > Threshold)", fontsize=11, fontweight="bold")
    ax4.grid(True, linestyle="--", alpha=0.5, axis="y")
    for bar in bars4:
        yval = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2.0, yval + 1.0, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold", fontsize=10)

    png_path = "results/data/sensor_blackout_observability_benchmark.png"
    plt.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved figure to {png_path}")

    brain_dir = "/Users/chalermsak/.gemini/antigravity-ide/brain/bfa523f6-4b75-4654-8f2e-65c6b00df558"
    if os.path.exists(brain_dir):
        dest_png = os.path.join(brain_dir, "sensor_blackout_observability_benchmark.png")
        shutil.copyfile(png_path, dest_png)
        print(f"Copied figure to brain artifact: {dest_png}")

    return out_data


if __name__ == "__main__":
    run_sensor_blackout_benchmark()
