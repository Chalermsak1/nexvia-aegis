"""
Prospective Factorial Benchmark: Bounded Active Probing POMDP & Epistemic Uncertainty Reduction (Task R-07).

Evaluates 100 prospective unseen worlds (Seeds 5000-5099) crossing:
1. Spatial Topologies:
   - SADDLE_CORRIDOR: Head-on symmetric obstacle inducing saddle point with open lateral bypass.
   - CUL_DE_SAC: 3-sided enclosed dead-end where all exits are blocked (unsolvable -> grounded abstention required).
   - NARROW_SLALOM: Constricted slalom corridor requiring lateral symmetry-breaking to navigate.
2. Actuator Motor Delay Lag: tau in [0.015, 0.035, 0.060] s (exact ZOH discretization).
3. Payload Mass Variation: m_ratio in [0.85, 1.00, 1.25] (+25% to -15% mismatch).

Compares 3 Experimental Arms:
1. Arm 1: Naive Baseline (Uncertified PD, no barrier, no probing)
2. Arm 2: Passive CLBF (Probing Disabled: Tube-CBF without active probing -> saddle stagnation freeze)
3. Arm 3: AEGIS Active Probing (Task R-07: Tube-shielded bounded active probing -> symmetry breaking in open
         corridors + grounded physical abstention in enclosed cul-de-sacs)
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
class ProbingWorldSpec:
    world_id: int
    seed: int
    topology_type: str        # 'SADDLE_CORRIDOR', 'CUL_DE_SAC', 'NARROW_SLALOM'
    goal_pos: np.ndarray
    obstacles: list[np.ndarray]
    is_solvable: bool
    mass_ratio: float         # [0.85, 1.00, 1.25]
    tau_actuator_lag: float   # [0.015, 0.035, 0.060] s
    safe_distance: float = 0.90


def generate_100_probing_worlds(start_seed: int = 5000, num_worlds: int = 100) -> list[ProbingWorldSpec]:
    """Generates 100 strictly unseen prospective worlds with symmetric and dead-end topologies."""
    worlds: list[ProbingWorldSpec] = []
    topologies = ["SADDLE_CORRIDOR", "CUL_DE_SAC", "NARROW_SLALOM"]
    mass_ratios = [0.85, 1.00, 1.25]
    actuator_lags = [0.015, 0.035, 0.060]

    for i in range(num_worlds):
        seed = start_seed + i
        rng = np.random.default_rng(seed)
        topo = topologies[i % len(topologies)]
        mass_rat = mass_ratios[(i // len(topologies)) % len(mass_ratios)]
        tau = actuator_lags[(i // 9) % len(actuator_lags)]

        raw_obstacles: list[np.ndarray] = []

        if topo == "SADDLE_CORRIDOR":
            # Head-on symmetric obstacle directly on the line connecting start (0,0) to goal (10,0)
            obs_x = 4.0 + float(rng.uniform(-0.3, 0.3))
            raw_obstacles.append(np.array([obs_x, 0.0, 0.0]))
            # Corridor boundary walls at y = +/- 2.0 to constrict flow while keeping side channels open
            for x_w in [1.5, 3.0, 4.5, 6.0]:
                raw_obstacles.append(np.array([x_w, 2.0, 0.0]))
                raw_obstacles.append(np.array([x_w, -2.0, 0.0]))
            goal = np.array([10.0 + float(rng.uniform(-0.2, 0.2)), 0.0, 0.0])
            is_solvable = True

        elif topo == "CUL_DE_SAC":
            # True fully-sealed enclosed dead-end corridor confining the vehicle
            front_x = 3.5 + float(rng.uniform(-0.1, 0.1))
            wall_y = 1.4 + float(rng.uniform(-0.05, 0.05))
            # Front impassable wall
            for y_w in [-wall_y, -0.7, 0.0, 0.7, wall_y]:
                raw_obstacles.append(np.array([front_x, y_w, 0.0]))
            # Left & Right side walls connecting seamlessly to front wall
            for x_w in [3.0, 2.0, 1.0, 0.0, -1.0]:
                raw_obstacles.append(np.array([x_w, wall_y, 0.0]))
                raw_obstacles.append(np.array([x_w, -wall_y, 0.0]))
            # Rear wall to prevent vehicle escaping backwards
            for y_w in [-0.7, 0.0, 0.7]:
                raw_obstacles.append(np.array([-1.0, y_w, 0.0]))

            goal = np.array([9.5, 0.0, 0.0])  # Goal behind front wall (true impassable cul-de-sac)
            is_solvable = False

        else:  # NARROW_SLALOM
            # Staggered obstacles inducing saddle slowing between pinch points
            ox1 = 3.0 + float(rng.uniform(-0.2, 0.2))
            ox2 = 6.0 + float(rng.uniform(-0.2, 0.2))
            raw_obstacles.append(np.array([ox1, 0.4, 0.0]))
            raw_obstacles.append(np.array([ox2, -0.4, 0.0]))
            goal = np.array([10.5, 0.0, 0.0])
            is_solvable = True

        # Expand obstacles with 3D vertical coverage to enforce physical barrier realism
        obstacles_3d: list[np.ndarray] = []
        for obs in raw_obstacles:
            for z_val in [-0.9, 0.0, 0.9]:
                obstacles_3d.append(np.array([obs[0], obs[1], z_val], dtype=np.float64))

        worlds.append(
            ProbingWorldSpec(
                world_id=i + 1,
                seed=seed,
                topology_type=topo,
                goal_pos=goal,
                obstacles=obstacles_3d,
                is_solvable=is_solvable,
                mass_ratio=mass_rat,
                tau_actuator_lag=tau,
                safe_distance=0.90,
            )
        )

    return worlds


def run_episode(
    arm_name: str,
    spec: ProbingWorldSpec,
    max_steps: int = 550,
    dt: float = 0.04,
) -> dict[str, Any]:
    """Runs a single closed-loop simulation episode."""
    p_true = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    v_true = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    u_motor_actual = np.zeros(3, dtype=np.float64)

    # Actuator lag ZOH coefficient
    alpha_lag = 1.0 - math.exp(-dt / spec.tau_actuator_lag)
    # Mass mismatch factor
    mass_eff = spec.mass_ratio

    enable_probing = (arm_name == "AEGIS_ACTIVE_PROBING")

    cfg = RobustTubeCLBFConfig(
        safe_distance=spec.safe_distance,
        actuator_delay_s=spec.tau_actuator_lag,
        enable_delay_compensation=True,
        enable_active_probing=enable_probing,
        probing_accel=2.5,
        stall_detection_steps=10,
        max_probing_steps=35,
        probing_budget_total=70,
        arrival_radius=0.45,
        speed_limit_at_goal=0.20,
        max_dwell_wait_steps=180,
    )
    ctrl = RobustTubeCLBFController(cfg)

    min_dist_to_obs = float("inf")
    collision_occurred = False
    probes_triggered_count = 0
    in_probing_mode = False

    trajectory: list[np.ndarray] = [p_true.copy()]
    final_phase = "RUNNING"
    final_reason = "STEP_LIMIT"

    for step in range(max_steps):
        # 1. State estimation (Gaussian noise)
        p_hat = p_true + np.random.normal(0, 0.01, size=3)
        v_hat = v_true + np.random.normal(0, 0.01, size=3)
        cov_p = np.eye(3) * (0.01 ** 2)
        cov_v = np.eye(3) * (0.01 ** 2)
        state = TubeUncertaintyState(p_hat=p_hat, v_hat=v_hat, cov_p=cov_p, cov_v=cov_v)

        # 2. Control computation
        if arm_name == "NAIVE_BASELINE":
            # Pure PD guidance without safety barrier or probing
            diff_g = spec.goal_pos - p_hat
            dist_g = float(np.linalg.norm(diff_g))
            if dist_g <= cfg.arrival_radius and float(np.linalg.norm(v_hat)) <= 0.1:
                u_cmd = -3.0 * v_hat
                step_phase = "CONFIRMED_STILL"
                step_reason = "NAIVE_GOAL_CAPTURE"
            else:
                u_cmd = 2.5 * diff_g - 1.8 * v_hat
                step_phase = "CRUISING"
                step_reason = "NAIVE_PD"
            u_cmd = np.clip(u_cmd, -cfg.a_max, cfg.a_max)
            is_probing = False
        else:
            res = ctrl.step(state, spec.goal_pos, obstacles=spec.obstacles)
            u_cmd = res["action"]
            step_phase = res["phase"]
            step_reason = res["reason"]
            is_probing = res.get("is_probing", False)

        if is_probing and not in_probing_mode:
            probes_triggered_count += 1
            in_probing_mode = True
        elif not is_probing:
            in_probing_mode = False

        # 3. Motor dynamics (actuator lag)
        u_motor_actual += alpha_lag * (u_cmd - u_motor_actual)

        # 4. Physical acceleration with mass variation
        a_true = (1.0 / mass_eff) * u_motor_actual
        v_true += dt * a_true
        p_true += dt * v_true
        trajectory.append(p_true.copy())

        # 5. Clearance check
        for obs in spec.obstacles:
            d = float(np.linalg.norm(p_true - obs))
            min_dist_to_obs = min(min_dist_to_obs, d)
            # Physical collision if penetration within hard vehicle radius (0.60m)
            if d < 0.60:
                collision_occurred = True

        final_phase = step_phase
        final_reason = step_reason

        if step_phase in (DwellPhase.CONFIRMED_STILL.value, "CONFIRMED_STILL"):
            break

    dist_to_goal = float(np.linalg.norm(p_true - spec.goal_pos))
    goal_captured = (dist_to_goal <= cfg.arrival_radius) and (
        final_phase in (DwellPhase.CONFIRMED_STILL.value, "CONFIRMED_STILL")
    )
    abstain_confirmed = (not spec.is_solvable) and (
        final_phase == DwellPhase.CONFIRMED_STILL.value
    ) and (not goal_captured)

    # Correct decision: completed if solvable, or grounded abstention if cul-de-sac
    if spec.is_solvable:
        correct_decision = goal_captured and (not collision_occurred)
    else:
        correct_decision = abstain_confirmed and (not collision_occurred)

    stalled_passive = (not goal_captured) and (not abstain_confirmed) and (not collision_occurred)
    e_kinetic = 0.5 * cfg.vehicle_mass_kg * float(np.dot(v_true, v_true))

    return {
        "world_id": spec.world_id,
        "seed": spec.seed,
        "topology": spec.topology_type,
        "is_solvable": spec.is_solvable,
        "arm": arm_name,
        "collision": collision_occurred,
        "min_dist_to_obs": min_dist_to_obs,
        "goal_captured": goal_captured,
        "abstain_confirmed": abstain_confirmed,
        "correct_decision": correct_decision,
        "stalled_passive": stalled_passive,
        "probes_triggered": probes_triggered_count,
        "probes_used": ctrl.total_probes_used if hasattr(ctrl, "total_probes_used") else 0,
        "final_kinetic_energy": e_kinetic,
        "dist_to_goal": dist_to_goal,
        "final_phase": final_phase,
        "final_reason": final_reason,
        "steps_taken": len(trajectory) - 1,
    }


def main() -> None:
    print("=" * 80)
    print("NEXVIA AEGIS MILESTONE V9-M17: BOUNDED ACTIVE PROBING FACTORIAL BENCHMARK")
    print("=" * 80)
    print("Generating 100 prospective unseen worlds across 3 topologies...")
    worlds = generate_100_probing_worlds(start_seed=5000, num_worlds=100)
    print(f"Total worlds generated: {len(worlds)}")

    arms = [
        "NAIVE_BASELINE",
        "PASSIVE_CLBF",
        "AEGIS_ACTIVE_PROBING",
    ]

    all_results: dict[str, list[dict[str, Any]]] = {arm: [] for arm in arms}
    start_time = time.perf_counter()

    for arm in arms:
        print(f"\n--- Running Arm: {arm} across 100 worlds ---")
        t0 = time.perf_counter()
        for idx, spec in enumerate(worlds):
            res = run_episode(arm, spec)
            all_results[arm].append(res)
            if (idx + 1) % 25 == 0 or (idx + 1) == len(worlds):
                print(f"  [{idx + 1}/100] worlds evaluated...")
        el = time.perf_counter() - t0
        print(f"  Finished {arm} in {el:.2f}s ({el/len(worlds)*1000:.1f} ms/world)")

    total_time = time.perf_counter() - start_time
    print(f"\nAll 300 evaluations completed in {total_time:.2f}s.")

    # Aggregate Metrics
    summary: dict[str, Any] = {}
    for arm in arms:
        results = all_results[arm]
        n_total = len(results)
        n_solvable = sum(1 for r in results if r["is_solvable"])
        n_unsolvable = n_total - n_solvable

        collisions = sum(1 for r in results if r["collision"])
        collision_rate = (collisions / n_total) * 100.0

        goals = sum(1 for r in results if r["goal_captured"])
        solvable_captured = sum(1 for r in results if r["is_solvable"] and r["goal_captured"])
        solvable_success_rate = (solvable_captured / n_solvable) * 100.0

        unstuck_abstains = sum(1 for r in results if (not r["is_solvable"]) and r["abstain_confirmed"])
        abstain_accuracy = (unstuck_abstains / n_unsolvable) * 100.0

        correct = sum(1 for r in results if r["correct_decision"])
        overall_correct_rate = (correct / n_total) * 100.0

        stalls = sum(1 for r in results if r["stalled_passive"])
        stall_rate = (stalls / n_total) * 100.0

        avg_min_dist = float(np.mean([r["min_dist_to_obs"] for r in results]))
        avg_probes = float(np.mean([r["probes_used"] for r in results]))

        summary[arm] = {
            "total_episodes": n_total,
            "collision_rate_pct": collision_rate,
            "solvable_success_rate_pct": solvable_success_rate,
            "abstain_accuracy_pct": abstain_accuracy,
            "overall_correct_decision_rate_pct": overall_correct_rate,
            "passive_stall_rate_pct": stall_rate,
            "avg_min_obstacle_distance_m": avg_min_dist,
            "avg_probes_used": avg_probes,
        }

    # Print Comparative Table
    print("\n" + "=" * 88)
    print(f"{'Metric':<34} | {'Naive Baseline':<16} | {'Passive CLBF':<16} | {'AEGIS Active Probe':<18}")
    print("-" * 88)
    print(f"{'Collision Rate (% - 0% ideal)':<34} | {summary['NAIVE_BASELINE']['collision_rate_pct']:>15.1f}% | {summary['PASSIVE_CLBF']['collision_rate_pct']:>15.1f}% | {summary['AEGIS_ACTIVE_PROBING']['collision_rate_pct']:>17.1f}%")
    print(f"{'Solvable Success Rate (%)':<34} | {summary['NAIVE_BASELINE']['solvable_success_rate_pct']:>15.1f}% | {summary['PASSIVE_CLBF']['solvable_success_rate_pct']:>15.1f}% | {summary['AEGIS_ACTIVE_PROBING']['solvable_success_rate_pct']:>17.1f}%")
    print(f"{'Cul-de-Sac Abstain Acc (%)':<34} | {summary['NAIVE_BASELINE']['abstain_accuracy_pct']:>15.1f}% | {summary['PASSIVE_CLBF']['abstain_accuracy_pct']:>15.1f}% | {summary['AEGIS_ACTIVE_PROBING']['abstain_accuracy_pct']:>17.1f}%")
    print(f"{'Overall Correct Decisions (%)':<34} | {summary['NAIVE_BASELINE']['overall_correct_decision_rate_pct']:>15.1f}% | {summary['PASSIVE_CLBF']['overall_correct_decision_rate_pct']:>15.1f}% | {summary['AEGIS_ACTIVE_PROBING']['overall_correct_decision_rate_pct']:>17.1f}%")
    print(f"{'Passive Stall Rate (% - 0% ideal)':<34} | {summary['NAIVE_BASELINE']['passive_stall_rate_pct']:>15.1f}% | {summary['PASSIVE_CLBF']['passive_stall_rate_pct']:>15.1f}% | {summary['AEGIS_ACTIVE_PROBING']['passive_stall_rate_pct']:>17.1f}%")
    print(f"{'Avg Min Obstacle Dist (m)':<34} | {summary['NAIVE_BASELINE']['avg_min_obstacle_distance_m']:>15.2f}m | {summary['PASSIVE_CLBF']['avg_min_obstacle_distance_m']:>15.2f}m | {summary['AEGIS_ACTIVE_PROBING']['avg_min_obstacle_distance_m']:>17.2f}m")
    print(f"{'Avg Micro-Probes Used':<34} | {summary['NAIVE_BASELINE']['avg_probes_used']:>16.1f} | {summary['PASSIVE_CLBF']['avg_probes_used']:>16.1f} | {summary['AEGIS_ACTIVE_PROBING']['avg_probes_used']:>18.1f}")
    print("=" * 88)

    # Save JSON results
    os.makedirs("results/data", exist_ok=True)
    json_path = "results/data/bounded_active_probing_benchmark.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": all_results}, f, indent=2)
    print(f"\nSaved benchmark results to {json_path}")

    # Generate Publication-Quality Figure
    os.makedirs("results/plots", exist_ok=True)
    plot_path = "results/plots/bounded_active_probing_benchmark.png"
    generate_benchmark_figure(summary, all_results, plot_path)
    print(f"Saved benchmark figure to {plot_path}")

    # Copy to Brain Artifact Directory
    brain_artifact_dir = "/Users/chalermsak/.gemini/antigravity-ide/brain/bfa523f6-4b75-4654-8f2e-65c6b00df558"
    if os.path.exists(brain_artifact_dir):
        dest_plot = os.path.join(brain_artifact_dir, "bounded_active_probing_benchmark.png")
        shutil.copy2(plot_path, dest_plot)
        print(f"Copied figure to brain artifact: {dest_plot}")


def generate_benchmark_figure(
    summary: dict[str, Any],
    all_results: dict[str, list[dict[str, Any]]],
    output_path: str,
) -> None:
    """Generates 4-panel publication visualization."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor("#0b0f19")
    for ax in axes.flat:
        ax.set_facecolor("#111827")
        ax.tick_params(colors="#9ca3af")
        ax.grid(True, linestyle="--", alpha=0.25, color="#374151")
        for spine in ax.spines.values():
            spine.set_color("#374151")

    arms = ["NAIVE_BASELINE", "PASSIVE_CLBF", "AEGIS_ACTIVE_PROBING"]
    labels = ["Naive Baseline\n(Uncertified)", "Passive CLBF\n(No Probing)", "AEGIS Active Probing\n(Task R-07)"]
    colors = ["#ef4444", "#f59e0b", "#10b981"]

    # Panel 1: Overall Correct Decision Rate & Collision Rate
    ax1 = axes[0, 0]
    x = np.arange(len(arms))
    width = 0.35
    correct_rates = [summary[a]["overall_correct_decision_rate_pct"] for a in arms]
    collision_rates = [summary[a]["collision_rate_pct"] for a in arms]

    b1 = ax1.bar(x - width/2, correct_rates, width, label="Correct Decisions (%)", color="#3b82f6", alpha=0.9)
    b2 = ax1.bar(x + width/2, collision_rates, width, label="Collisions (%)", color="#ef4444", alpha=0.9)
    ax1.set_title("Decision Correctness vs. Collisions (100 Worlds)", color="#f9fafb", fontsize=12, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, color="#e5e7eb", fontsize=10)
    ax1.set_ylabel("Percentage (%)", color="#e5e7eb")
    ax1.set_ylim(0, 110)
    ax1.legend(facecolor="#1f2937", edgecolor="#374151", labelcolor="#f3f4f6")
    for bar in b1:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2, f"{bar.get_height():.1f}%",
                 ha="center", va="bottom", color="#93c5fd", fontsize=9, fontweight="bold")
    for bar in b2:
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2, f"{bar.get_height():.1f}%",
                 ha="center", va="bottom", color="#fca5a5", fontsize=9, fontweight="bold")

    # Panel 2: Topology Breakdown (Saddle Corridor vs Cul-de-Sac)
    ax2 = axes[0, 1]
    topos = ["SADDLE_CORRIDOR", "CUL_DE_SAC", "NARROW_SLALOM"]
    topo_labels = ["Saddle Corridor\n(Solvable)", "Cul-de-Sac Dead End\n(Unsolvable)", "Narrow Slalom\n(Solvable)"]
    x_topo = np.arange(len(topos))
    w_topo = 0.25

    for idx, (arm, col, lbl) in enumerate(zip(arms, colors, ["Naive", "Passive", "AEGIS Probing"])):
        topo_acc = []
        for tp in topos:
            subset = [r for r in all_results[arm] if r["topology"] == tp]
            acc = (sum(1 for r in subset if r["correct_decision"]) / len(subset)) * 100.0 if subset else 0.0
            topo_acc.append(acc)
        bars = ax2.bar(x_topo + (idx - 1) * w_topo, topo_acc, w_topo, label=lbl, color=col, alpha=0.9)
        for b in bars:
            ax2.text(b.get_x() + b.get_width()/2, b.get_height() + 2, f"{b.get_height():.0f}%",
                     ha="center", va="bottom", color="#e5e7eb", fontsize=8)

    ax2.set_title("Topology-Specific Task Success Rate (%)", color="#f9fafb", fontsize=12, fontweight="bold")
    ax2.set_xticks(x_topo)
    ax2.set_xticklabels(topo_labels, color="#e5e7eb", fontsize=10)
    ax2.set_ylabel("Success Rate (%)", color="#e5e7eb")
    ax2.set_ylim(0, 115)
    ax2.legend(facecolor="#1f2937", edgecolor="#374151", labelcolor="#f3f4f6")

    # Panel 3: Passive Stalls vs Active Probing Resolutions
    ax3 = axes[1, 0]
    stalls = [summary[a]["passive_stall_rate_pct"] for a in arms]
    solvable_succ = [summary[a]["solvable_success_rate_pct"] for a in arms]

    b3 = ax3.bar(x - width/2, stalls, width, label="Passive Stall Rate (%)", color="#f59e0b", alpha=0.9)
    b4 = ax3.bar(x + width/2, solvable_succ, width, label="Solvable Goal Arrival (%)", color="#10b981", alpha=0.9)
    ax3.set_title("Elimination of Saddle-Point Stalls", color="#f9fafb", fontsize=12, fontweight="bold")
    ax3.set_xticks(x)
    ax3.set_xticklabels(labels, color="#e5e7eb", fontsize=10)
    ax3.set_ylabel("Percentage (%)", color="#e5e7eb")
    ax3.set_ylim(0, 115)
    ax3.legend(facecolor="#1f2937", edgecolor="#374151", labelcolor="#f3f4f6")
    for bar in b3:
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2, f"{bar.get_height():.1f}%",
                 ha="center", va="bottom", color="#fde68a", fontsize=9, fontweight="bold")
    for bar in b4:
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2, f"{bar.get_height():.1f}%",
                 ha="center", va="bottom", color="#a7f3d0", fontsize=9, fontweight="bold")

    # Panel 4: Clearance Safety Margin Distribution
    ax4 = axes[1, 1]
    for arm, col, lbl in zip(arms, colors, ["Naive", "Passive", "AEGIS Probing"]):
        dists = [r["min_dist_to_obs"] for r in all_results[arm]]
        ax4.hist(dists, bins=15, alpha=0.6, label=lbl, color=col, edgecolor="#111827", density=True)

    ax4.axvline(x=0.60, color="#ef4444", linestyle="--", linewidth=2, label="Hard Vehicle Limit (0.6m)")
    ax4.axvline(x=0.90, color="#10b981", linestyle=":", linewidth=2, label="Barrier Margin R_safe (0.9m)")
    ax4.set_title("Obstacle Clearance Safety Margin Distribution", color="#f9fafb", fontsize=12, fontweight="bold")
    ax4.set_xlabel("Minimum Distance to Obstacle (m)", color="#e5e7eb")
    ax4.set_ylabel("Density", color="#e5e7eb")
    ax4.legend(facecolor="#1f2937", edgecolor="#374151", labelcolor="#f3f4f6", fontsize=9)

    plt.suptitle("NEXVIA AEGIS Milestone V9-M17: Bounded Active Probing Factorial Benchmark\n"
                 "Epistemic Uncertainty Reduction via Tube-Shielded Micro-Actions in 100 Prospective Worlds",
                 color="#f9fafb", fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.94])
    plt.savefig(output_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()


if __name__ == "__main__":
    main()
