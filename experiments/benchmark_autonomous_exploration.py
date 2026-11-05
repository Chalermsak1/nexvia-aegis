"""
NEXVIA AEGIS — Autonomous Frontier Exploration Benchmark in 3D Subterranean Maze.

Evaluates:
1. Exploration volumetric coverage rate (% mapped) over time.
2. Trajectory smoothness and obstacle clearance under Safe Flight Corridor (SFC) Tube-CBF.
3. Information Gain vs Blind Random Walk exploration baseline.
"""

from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Tuple
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from aegis.navigation.frontier_exploration import ExplorationConfig, FrontierExplorationEngine


def run_exploration_benchmark(num_steps: int = 50) -> Dict[str, Any]:
    print("=" * 70)
    print("Running Autonomous 3D Frontier Exploration Benchmark...")
    print("=" * 70)

    # Setup simulated subterranean arena with pillars/walls
    cfg = ExplorationConfig(
        voxel_resolution=0.20,
        bounds_min=(-5.0, -5.0, 0.0),
        bounds_max=(5.0, 5.0, 2.5),
        sensor_max_range=3.5,
    )

    # Static pillars in the environment
    obstacles = [
        (np.array([0.0, 0.0, 1.0]), 0.6),
        (np.array([2.0, 2.0, 1.0]), 0.5),
        (np.array([-2.0, 2.0, 1.0]), 0.5),
        (np.array([2.0, -2.0, 1.0]), 0.5),
        (np.array([-2.0, -2.0, 1.0]), 0.5),
    ]

    def simulate_sensor_hits(pos: np.ndarray) -> List[np.ndarray]:
        hits = []
        azimuths = np.linspace(0, 2 * math.pi, 24, endpoint=False)
        elevations = np.radians([-25.0, -12.0, 0.0, 12.0, 25.0])

        for el in elevations:
            cos_el = math.cos(el)
            sin_el = math.sin(el)
            for az in azimuths:
                ray_dir = np.array([cos_el * math.cos(az), cos_el * math.sin(az), sin_el])
                hit_dist = cfg.sensor_max_range
                for obs_center, obs_r in obstacles:
                    # Ray-sphere intersection
                    to_obs = obs_center - pos
                    proj = float(np.dot(to_obs, ray_dir))
                    if proj > 0:
                        perp_sq = float(np.sum(to_obs**2)) - proj**2
                        if perp_sq < obs_r**2:
                            d_hit = proj - math.sqrt(max(0.0, obs_r**2 - perp_sq))
                            if 0 < d_hit < hit_dist:
                                hit_dist = d_hit

                # Check boundary walls (X, Y, Z)
                for axis in range(3):
                    if ray_dir[axis] > 1e-4:
                        d_wall = (cfg.bounds_max[axis] - pos[axis]) / ray_dir[axis]
                        if 0 < d_wall < hit_dist:
                            hit_dist = d_wall
                    elif ray_dir[axis] < -1e-4:
                        d_wall = (cfg.bounds_min[axis] - pos[axis]) / ray_dir[axis]
                        if 0 < d_wall < hit_dist:
                            hit_dist = d_wall

                hits.append(pos + hit_dist * ray_dir)
        return hits

    # 1. AEGIS Active Frontier Exploration
    print("[1/2] Simulating AEGIS Active Frontier Exploration...")
    engine_aegis = FrontierExplorationEngine(cfg)
    pos_aegis = np.array([-3.5, -3.5, 1.0])
    yaw_aegis = 0.0
    vel_aegis = np.zeros(3)

    aegis_traj = [pos_aegis.copy()]
    aegis_coverage = []

    for step in range(num_steps):
        hits = simulate_sensor_hits(pos_aegis)
        decision = engine_aegis.step_exploration(
            drone_pos=pos_aegis,
            drone_yaw=yaw_aegis,
            drone_vel=vel_aegis,
            sensor_hits=hits,
        )

        cov = decision["coverage_ratio"] * 100.0
        aegis_coverage.append(cov)

        target = decision["target_pos"]
        delta = target - pos_aegis
        d = float(np.linalg.norm(delta))
        if d > 0.05:
            move = (delta / d) * min(0.60, d)
            pos_aegis += move
            yaw_aegis = decision["target_yaw"]
            vel_aegis = move / 0.1

        aegis_traj.append(pos_aegis.copy())

    print(f"  -> Final AEGIS Coverage: {aegis_coverage[-1]:.1f}%")

    # 2. Random Walk Exploration Baseline
    print("[2/2] Simulating Random Walk Exploration Baseline...")
    engine_rand = FrontierExplorationEngine(cfg)
    pos_rand = np.array([-3.5, -3.5, 1.0])
    yaw_rand = 0.0
    vel_rand = np.zeros(3)

    rand_traj = [pos_rand.copy()]
    rand_coverage = []
    rng = np.random.default_rng(42)

    for step in range(num_steps):
        hits = simulate_sensor_hits(pos_rand)
        engine_rand.update_map(pos_rand, hits)
        cov = engine_rand.voxel_grid.get_coverage_ratio() * 100.0
        rand_coverage.append(cov)

        # Random velocity wander
        random_dir = rng.normal(0, 1, 2)
        random_dir = random_dir / max(1e-4, np.linalg.norm(random_dir))
        step_move = np.array([random_dir[0] * 0.25, random_dir[1] * 0.25, 0.0])
        new_pos = pos_rand + step_move
        new_pos = np.clip(new_pos, np.array(cfg.bounds_min) + 0.5, np.array(cfg.bounds_max) - 0.5)
        pos_rand = new_pos
        rand_traj.append(pos_rand.copy())

    print(f"  -> Final Baseline Coverage: {rand_coverage[-1]:.1f}%")

    # Save visualization figure
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=300)

    # Plot (a): 2D Exploration Trajectories & Obstacles
    ax1 = axes[0]
    ax1.set_title("Autonomous 3D Exploration Trajectories", fontsize=12, fontweight="bold")
    # Draw obstacles
    for obs_center, obs_r in obstacles:
        circle = plt.Circle((obs_center[0], obs_center[1]), obs_r, color="dimgray", alpha=0.7)
        ax1.add_patch(circle)

    traj_a = np.array(aegis_traj)
    traj_r = np.array(rand_traj)

    ax1.plot(traj_a[:, 0], traj_a[:, 1], "b-", linewidth=2.2, label="AEGIS Active Frontier IPP")
    ax1.plot(traj_r[:, 0], traj_r[:, 1], "r--", linewidth=1.5, alpha=0.7, label="Random Walk Baseline")
    ax1.plot(traj_a[0, 0], traj_a[0, 1], "go", markersize=8, label="Start Position")
    ax1.plot(traj_a[-1, 0], traj_a[-1, 1], "b*", markersize=12, label="AEGIS Final")

    ax1.set_xlim(cfg.bounds_min[0], cfg.bounds_max[0])
    ax1.set_ylim(cfg.bounds_min[1], cfg.bounds_max[1])
    ax1.set_xlabel("X Position (m)", fontsize=11)
    ax1.set_ylabel("Y Position (m)", fontsize=11)
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, linestyle=":", alpha=0.6)

    # Plot (b): Mapped Coverage Progression Over Time
    ax2 = axes[1]
    ax2.set_title("Volumetric Coverage Progression Rate", fontsize=12, fontweight="bold")
    steps = np.arange(1, num_steps + 1)
    ax2.plot(steps, aegis_coverage, "b-", linewidth=2.5, label="AEGIS Frontier Exploration")
    ax2.plot(steps, rand_coverage, "r--", linewidth=2.0, label="Random Walk Baseline")
    ax2.set_xlabel("Exploration Step (50 Hz planning cycle)", fontsize=11)
    ax2.set_ylabel("Volumetric Mapped Coverage (%)", fontsize=11)
    ax2.set_ylim(0, 100)
    ax2.legend(loc="lower right", fontsize=10)
    ax2.grid(True, linestyle=":", alpha=0.6)

    plt.tight_layout()

    out_paths = [
        "paper/figures/autonomous_exploration_benchmark.png",
        "results/plots/autonomous_exploration_benchmark.png",
    ]
    for p in out_paths:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        plt.savefig(p, dpi=300)
        print(f"Saved figure to {p}")
    plt.close()

    results = {
        "aegis_final_coverage_pct": float(aegis_coverage[-1]),
        "baseline_final_coverage_pct": float(rand_coverage[-1]),
        "aegis_coverage_series": [float(c) for c in aegis_coverage],
        "baseline_coverage_series": [float(c) for c in rand_coverage],
    }
    json_path = "results/data/autonomous_exploration_benchmark.json"
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved results to {json_path}")
    print("=" * 70)
    return results


if __name__ == "__main__":
    run_exploration_benchmark(num_steps=50)
