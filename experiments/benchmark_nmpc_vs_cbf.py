"""
Comprehensive Benchmark: NMPC-CBF Lookahead vs Pointwise HOCBF Shield.

Evaluates high-speed flight through dynamic obstacles in continuous 6-DOF physics.
Metrics evaluated across 30 episodes:
  1. Minimum Obstacle Clearance (m)
  2. Control Smoothness / Jerk (Mean and Max ||Delta F|| / dt in N/s)
  3. Total Control Energy (integral of ||F - F_hover||^2 dt)
  4. Solver Latency / Step Time (ms)
  5. Goal Reaching Success Rate (%) and Transit Time (s)
"""

import json
import math
import os
import time
import numpy as np

from aegis.env.quadrotor_6dof import (
    AegisQuadrotor6DOFEnvironment,
    Obstacle3D,
    QuadrotorConfig,
    UnderactuatedCBF6DOF,
)
from aegis.nmpc.nmpc_cbf_optimizer import NmpcCbfConfig, NmpcCbfController


def run_benchmark(n_episodes_per_controller: int = 15) -> dict:
    print(f"=== Starting NMPC-CBF vs Pointwise HOCBF Benchmark ({n_episodes_per_controller * 2} episodes) ===")
    
    # 1. Setup Controllers
    quad_cfg = QuadrotorConfig(
        mass=1.25,
        gravity=9.81,
        arena_limit=1.5,
        robot_collision_radius=0.12,
        safety_margin=0.08,
        cbf_gamma=1.5,
    )
    pointwise_cbf = UnderactuatedCBF6DOF(quad_cfg)

    nmpc_cfg = NmpcCbfConfig(
        horizon_steps=15,
        dt=0.05,
        drone_mass=1.25,
        gravity=9.81,
        weight_pos=10.0,
        weight_pos_terminal=35.0,
        weight_vel=1.8,
        weight_thrust=0.06,
        weight_delta_u=0.45,
        arena_limit=1.5,
        robot_collision_radius=0.12,
        safety_margin=0.08,
    )
    nmpc_controller = NmpcCbfController(nmpc_cfg)

    controllers = ["Pointwise_HOCBF", "NMPC_CBF_Lookahead"]
    results = {
        "Pointwise_HOCBF": {
            "min_clearances": [],
            "max_jerks": [],
            "mean_jerks": [],
            "control_energies": [],
            "solve_times_ms": [],
            "success_rate": 0.0,
            "transit_times": [],
            "trajectories": [],
        },
        "NMPC_CBF_Lookahead": {
            "min_clearances": [],
            "max_jerks": [],
            "mean_jerks": [],
            "control_energies": [],
            "solve_times_ms": [],
            "success_rate": 0.0,
            "transit_times": [],
            "trajectories": [],
        },
    }

    env = AegisQuadrotor6DOFEnvironment(quad_cfg, obstacles=[])
    m = quad_cfg.mass
    g = quad_cfg.gravity
    hover_f = np.array([0.0, 0.0, m * g], dtype=np.float64)

    for ctrl_name in controllers:
        print(f"\n--- Benchmarking Controller: {ctrl_name} ---")
        successes = 0

        for ep in range(n_episodes_per_controller):
            env.reset()
            # Set high-speed flight corridor from X = -1.0 to X = +1.0
            start_pos = np.array([-0.95, -0.05, 1.0], dtype=np.float64)
            start_vel = np.array([0.5, 0.0, 0.0], dtype=np.float64) # entering with speed
            target_pos = np.array([0.95, 0.05, 1.0], dtype=np.float64)

            env.data.qpos[:3] = start_pos
            env.data.qvel[:3] = start_vel

            # Dynamic moving obstacle cutting across corridor
            obs_init = np.array([0.05, 0.45, 1.0], dtype=np.float64)
            obs_vel = np.array([0.0, -0.32, 0.0], dtype=np.float64) # cutting into path
            obs_radius = 0.22

            pos_hist = [start_pos.copy()]
            force_hist = [hover_f.copy()]
            step_times = []
            min_dist = 1e6

            sim_dt = 0.02 # 50 Hz outer loop step
            mpc_downsample = 2 # NMPC update at 25 Hz (every 40 ms)
            nmpc_controller.reset()
            last_cmd_force = hover_f.copy()

            ep_steps = 150 # 3.0 seconds max
            reached = False

            for step_idx in range(ep_steps):
                sim_time = step_idx * sim_dt
                curr_state = env.get_state()
                curr_p = curr_state["pos"].copy()
                curr_v = curr_state["vel"].copy()
                curr_quat = curr_state["quat"].copy()
                curr_omega = curr_state["omega_body"].copy()

                # Update dynamic obstacle
                obs_center = obs_init + obs_vel * sim_time
                current_obs = Obstacle3D(center=obs_center, radius=obs_radius)

                # Distance to obstacle
                d_curr = float(np.linalg.norm(curr_p - obs_center) - obs_radius - quad_cfg.robot_collision_radius)
                min_dist = min(min_dist, d_curr)

                # Check if reached target (within 0.15m)
                if np.linalg.norm(curr_p - target_pos) < 0.15:
                    reached = True
                    break

                # Control computation
                if step_idx % mpc_downsample == 0:
                    t_solve_start = time.perf_counter()

                    if ctrl_name == "Pointwise_HOCBF":
                        # Standard PD + Pointwise HOCBF Projection
                        e_p = target_pos - curr_p
                        e_v = -curr_v
                        f_nom = 6.0 * e_p + 2.5 * e_v + hover_f
                        tilt = float(np.arccos(np.clip(f_nom[2] / max(1e-4, float(np.linalg.norm(f_nom))), -1.0, 1.0)))

                        safe_f, _ = pointwise_cbf.filter_safe_force(
                            pos=curr_p,
                            vel=curr_v,
                            desired_force=f_nom,
                            obstacles=[current_obs],
                            current_tilt=tilt,
                        )
                        last_cmd_force = safe_f.copy()

                    else:
                        # NMPC-CBF Lookahead
                        opt_res = nmpc_controller.compute_optimal_control(
                            current_pos=curr_p,
                            current_vel=curr_v,
                            target_pos=target_pos,
                            obstacles=[current_obs],
                            obstacles_vel=[obs_vel],
                        )
                        last_cmd_force = opt_res.optimal_force_world.copy()

                    t_solve = (time.perf_counter() - t_solve_start) * 1000.0
                    step_times.append(t_solve)

                # Apply motor commands through 6-DOF geometric controller (50 Hz outer step)
                env.step_outer(
                    desired_force_world=last_cmd_force,
                    shield_with_cbf=False,
                    desired_yaw=0.0,
                )

                pos_hist.append(curr_p.copy())
                force_hist.append(last_cmd_force.copy())

            # Metrics Computation
            pos_arr = np.array(pos_hist)
            force_arr = np.array(force_hist)

            # Force Rate of Change (Jerk approximation) in N/s
            dF_dt = np.linalg.norm(np.diff(force_arr, axis=0), axis=1) / sim_dt
            max_jerk = float(np.max(dF_dt))
            mean_jerk = float(np.mean(dF_dt))

            # Control Energy
            ctrl_energy = float(np.sum(np.linalg.norm(force_arr - hover_f, axis=1)**2) * sim_dt)
            transit_time = len(pos_hist) * sim_dt

            if reached and min_dist >= 0.0:
                successes += 1

            results[ctrl_name]["min_clearances"].append(min_dist)
            results[ctrl_name]["max_jerks"].append(max_jerk)
            results[ctrl_name]["mean_jerks"].append(mean_jerk)
            results[ctrl_name]["control_energies"].append(ctrl_energy)
            results[ctrl_name]["solve_times_ms"].extend(step_times)
            results[ctrl_name]["transit_times"].append(transit_time)

            if ep == 0:
                # Save first trajectory for 3D visualization
                results[ctrl_name]["trajectories"].append(pos_arr.tolist())

            print(f"  Ep {ep+1:02d}: Min Clearance={min_dist:+.3f}m | Max Jerk={max_jerk:6.1f} N/s | Transit={transit_time:.2f}s | Success={reached and min_dist >= 0.0}")

        results[ctrl_name]["success_rate"] = float(successes / n_episodes_per_controller) * 100.0

    # Summary Statistics
    summary = {}
    for ctrl_name in controllers:
        res = results[ctrl_name]
        summary[ctrl_name] = {
            "success_rate_pct": res["success_rate"],
            "mean_min_clearance_m": float(np.mean(res["min_clearances"])),
            "std_min_clearance_m": float(np.std(res["min_clearances"])),
            "mean_max_jerk_N_per_s": float(np.mean(res["max_jerks"])),
            "std_max_jerk_N_per_s": float(np.std(res["max_jerks"])),
            "mean_control_energy": float(np.mean(res["control_energies"])),
            "mean_solve_time_ms": float(np.mean(res["solve_times_ms"])),
            "p95_solve_time_ms": float(np.percentile(res["solve_times_ms"], 95)),
            "mean_transit_time_s": float(np.mean(res["transit_times"])),
        }

    print("\n=== FINAL BENCHMARK SUMMARY ===")
    for ctrl_name, stats in summary.items():
        print(f"\n{ctrl_name}:")
        for k, v in stats.items():
            print(f"  {k}: {v:.3f}")

    out_path = "results/data/nmpc_cbf_benchmark.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)
    print(f"\nSaved benchmark results to {out_path}")
    return summary


if __name__ == "__main__":
    run_benchmark(n_episodes_per_controller=15)
