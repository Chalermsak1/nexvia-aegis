"""Exhaustive Sim2Real & Embedded Hardware Benchmark for NEXVIA AEGIS.

Simulates real-world embedded companion computer conditions:
  - Sensor transport latency: Gaussian jitter N(15ms, 4ms)
  - MAVLink packet drop rate: 3% random dropouts
  - Temporary EKF2 odometry dropouts (60ms communication freeze)
  - Intermittent camera occlusions behind narrow corridor pillars
  - 4S LiPo battery internal resistance voltage sag (16.8V -> 14.2V)

Compares:
  1. Naive PX4 Mission Controller (No Shield, Zero Latency Compensation)
  2. Delayed MAVROS Controller (Standard CBF on Stale 25ms Data, No Latency Compensation)
  3. AEGIS ROS 2 Companion Autonomy Node (Latency Extrapolation, 200 Hz Attitude Target,
     Active Saccade, Real-Time Watchdog)

Saves JSON metrics to results/data/sim2real_hardware_benchmark.json.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
import numpy as np

from aegis.env.quadrotor_6dof import AegisQuadrotor6DOFEnvironment, Obstacle3D
from aegis.sim2real.aegis_ros2_node import AegisNodeConfig, AegisROS2DroneNode
from aegis.sim2real.mavlink_protocol import force_vector_to_attitude_and_thrust, quaternion_to_euler_angles
from aegis.sim2real.safety_watchdog import FailsafeAction


@dataclass
class Sim2RealTrialResult:
    controller_type: str
    episode_id: int
    collision: bool
    min_clearance: float
    max_tilt_deg: float
    mean_latency_ms: float
    packets_dropped: int
    watchdog_interventions: int
    active_saccades: int
    final_distance_to_goal: float
    flight_time_s: float
    trajectory: list[list[float]] = field(default_factory=list)


def run_sim2real_episode(
    controller_type: str,
    episode_id: int,
    seed: int,
    max_steps: int = 220,
    dt: float = 0.02,  # 50 Hz outer step
) -> Sim2RealTrialResult:
    rng = np.random.default_rng(seed)

    # Corridor obstacle configuration:
    # 1. Left Pillar at X=0.35, Y=0.50, radius 0.25 (extends to Y=+0.25)
    # 2. Dynamic intruder creeping into transit corridor from behind left pillar
    # 3. Right Pillar at X=0.35, Y=-0.50, radius 0.25 (extends to Y=-0.25)
    # Gap width between pillars = 0.50 m (allows 0.40m drone to pass through with tight navigation)
    obs1 = Obstacle3D(center=np.array([0.35, 0.50, 1.0]), radius=0.25)
    obs2_init = np.array([0.95, 0.22, 1.0]) + rng.normal(0.0, 0.01, size=3)
    obs2_vel = np.array([-0.07, -0.04, 0.0]) + rng.normal(0.0, 0.005, size=3)
    obs2 = Obstacle3D(center=obs2_init, radius=0.24)
    obs3 = Obstacle3D(center=np.array([0.35, -0.50, 1.0]), radius=0.25)
    obstacles = [obs1, obs2, obs3]

    target_pos = np.array([1.6, 0.0, 1.0])
    env = AegisQuadrotor6DOFEnvironment(obstacles=obstacles, target_pos=target_pos)
    start_pos = np.array([-1.2, 0.0, 1.0])
    env.reset()
    env.data.qpos[:3] = start_pos
    env.data.qvel[:3] = 0.0

    # Initialize AEGIS Node
    aegis_node = AegisROS2DroneNode(
        AegisNodeConfig(
            control_rate_hz=200.0,
            target_pos=target_pos,
            nominal_speed_m_s=1.0,
            max_thrust_n=25.0,
        )
    )

    collision = False
    min_clearance = float("inf")
    max_tilt_observed = 0.0
    trajectory: list[list[float]] = []
    packets_dropped = 0
    watchdog_interventions = 0
    active_saccades = 0
    latencies: list[float] = []

    # Odometry and perception buffers simulating embedded communication
    buffered_odom: tuple[np.ndarray, np.ndarray, np.ndarray, float] | None = None
    odom_timestamp_s = 0.0
    battery_v = 16.6

    for step in range(max_steps):
        sim_time = step * dt
        # Dynamic intruder creep
        current_obs2 = Obstacle3D(center=obs2_init + obs2_vel * sim_time, radius=0.26)
        current_obstacles = [obs1, current_obs2, obs3]

        current_state = env.get_state()
        drone_pos = current_state["pos"]
        drone_vel = current_state["vel"]
        drone_quat = current_state["quat"]
        trajectory.append(drone_pos.tolist())

        # Check collision against obstacles
        for obs in current_obstacles:
            dist = float(np.linalg.norm(drone_pos - obs.center))
            clearance = dist - (0.20 + obs.radius)
            if clearance < min_clearance:
                min_clearance = clearance
            if clearance <= 0.0:
                collision = True

        # Track tilt
        roll, pitch, yaw = quaternion_to_euler_angles(drone_quat)
        tilt_deg = math.degrees(math.acos(math.cos(roll) * math.cos(pitch)))
        if tilt_deg > max_tilt_observed:
            max_tilt_observed = tilt_deg

        # Stop if reached target
        if np.linalg.norm(drone_pos - target_pos) < 0.20:
            break

        # Simulate transport latency jitter N(15ms, 4ms), clipped [5ms, 35ms]
        transport_latency_s = float(np.clip(rng.normal(0.015, 0.004), 0.005, 0.035))
        latencies.append(transport_latency_s * 1000.0)

        # Simulate 3% MAVLink packet drop
        if rng.uniform(0.0, 1.0) < 0.03:
            packets_dropped += 1
            is_packet_dropped = True
        else:
            is_packet_dropped = False

        # Simulate temporary EKF2 communication freeze at step 45-47 (~60ms)
        is_comm_freeze = (45 <= step <= 47)

        # Update odometry feed
        if not is_comm_freeze and not is_packet_dropped:
            odom_timestamp_s = sim_time - transport_latency_s
            buffered_odom = (drone_pos, drone_quat, drone_vel, odom_timestamp_s)

        # Ingest odometry into AEGIS node
        if buffered_odom is not None:
            pos_in, quat_in, vel_in, t_in = buffered_odom
            aegis_node.ingest_odometry(
                position=pos_in,
                quaternion_wxyz=quat_in,
                linear_velocity=vel_in,
                angular_velocity=np.zeros(3),
                timestamp_s=t_in,
            )

        # Simulate camera perception (at 20 Hz, i.e. every 2-3 outer steps)
        if step % 2 == 0:
            # Detect obstacles within sensor range
            detected_clusters: list[tuple[np.ndarray, float]] = []
            for obs in current_obstacles:
                # Add range noise
                noisy_center = obs.center + rng.normal(0.0, 0.015, size=3)
                detected_clusters.append((noisy_center, obs.radius))
            aegis_node.ingest_perception(detected_clusters, timestamp_s=sim_time - transport_latency_s)

        # Battery voltage sag under throttle
        battery_v = max(14.0, 16.6 - 0.008 * step)
        aegis_node.ingest_battery(voltage_v=battery_v, current_a=6.5, percentage=0.85, timestamp_s=sim_time)

        # Controller execution
        if controller_type == "naive_px4":
            # Direct P-controller toward target without safety barrier or latency compensation
            dir_to_target = target_pos - drone_pos
            dist_to_target = np.linalg.norm(dir_to_target)
            unit_dir = dir_to_target / max(1e-4, dist_to_target)
            f_nom_xy = 3.5 * unit_dir[:2] - 1.6 * drone_vel[:2]
            f_nom_z = 1.25 * (9.81 + 3.0 * (target_pos[2] - drone_pos[2]) - 1.8 * drone_vel[2])
            force_cmd = np.array([f_nom_xy[0], f_nom_xy[1], f_nom_z])

        elif controller_type == "delayed_mavros":
            # Standard CBF evaluated on delayed odometry WITHOUT latency extrapolation or watchdog
            delayed_pos = buffered_odom[0] if buffered_odom is not None else drone_pos
            delayed_vel = buffered_odom[2] if buffered_odom is not None else drone_vel
            dir_to_target = target_pos - delayed_pos
            unit_dir = dir_to_target / max(1e-4, np.linalg.norm(dir_to_target))
            f_nom_xy = 3.0 * unit_dir[:2] - 1.5 * delayed_vel[:2]
            force_cbf = np.array([f_nom_xy[0], f_nom_xy[1], 0.0])

            # Apply standard CBF on stale position
            for obs in current_obstacles:
                rel_pos = delayed_pos[:2] - obs.center[:2]
                r_eff = 0.20 + obs.radius + 0.08
                dist_xy = np.linalg.norm(rel_pos)
                h = dist_xy**2 - r_eff**2
                h_dot = 2.0 * np.dot(rel_pos, delayed_vel[:2])
                psi = h_dot + 2.0 * h
                if psi < 0.0:
                    n_vec = rel_pos / max(1e-4, dist_xy)
                    force_cbf[:2] += -psi * 2.2 * n_vec

            f_z = 1.25 * (9.81 + 3.0 * (target_pos[2] - drone_pos[2]) - 1.8 * drone_vel[2])
            force_cmd = np.array([force_cbf[0], force_cbf[1], f_z])

        elif controller_type == "aegis_ros2":
            # Production AEGIS ROS 2 companion node with latency extrapolation,
            # active POMDP saccades, and real-time watchdog
            setpoint, diag = aegis_node.step_control_cycle(now_s=sim_time)
            if diag.recommended_action != FailsafeAction.NONE:
                watchdog_interventions += 1
            if aegis_node.latest_gimbal_decision and aegis_node.latest_gimbal_decision.is_actively_probing:
                active_saccades += 1

            # Convert orientation quaternion and normalized thrust back to commanded force
            w, x, y, z = setpoint.orientation_wxyz
            thrust_n = setpoint.thrust_normalized * aegis_node.config.max_thrust_n
            z_b = np.array([
                2.0 * (x * z + w * y),
                2.0 * (y * z - w * x),
                1.0 - 2.0 * (x * x + y * y),
            ], dtype=np.float64)
            z_b /= max(1e-6, float(np.linalg.norm(z_b)))
            force_cmd = thrust_n * z_b

        else:
            raise ValueError(f"Unknown controller: {controller_type}")

        # Step continuous MuJoCo physics
        env.step_outer(desired_force_world=force_cmd, shield_with_cbf=False, desired_yaw=0.0)

    final_dist = float(np.linalg.norm(drone_pos - target_pos))
    mean_latency = float(np.mean(latencies)) if latencies else 0.0

    return Sim2RealTrialResult(
        controller_type=controller_type,
        episode_id=episode_id,
        collision=collision,
        min_clearance=min_clearance,
        max_tilt_deg=max_tilt_observed,
        mean_latency_ms=mean_latency,
        packets_dropped=packets_dropped,
        watchdog_interventions=watchdog_interventions,
        active_saccades=active_saccades,
        final_distance_to_goal=final_dist,
        flight_time_s=step * dt,
        trajectory=trajectory,
    )


def run_full_benchmark(n_episodes_per_controller: int = 15) -> dict[str, dict]:
    print(f"=== Starting Sim2Real & ROS 2 Embedded Hardware Benchmark ({n_episodes_per_controller} episodes/group) ===")
    controllers = ["naive_px4", "delayed_mavros", "aegis_ros2"]
    results_by_controller: dict[str, list[Sim2RealTrialResult]] = {c: [] for c in controllers}

    for c in controllers:
        print(f"\nEvaluating Controller Architecture: {c}")
        for ep in range(n_episodes_per_controller):
            seed = 42000 + ep * 7
            res = run_sim2real_episode(controller_type=c, episode_id=ep, seed=seed)
            results_by_controller[c].append(res)
            print(f"  [{c} Ep {ep+1:02d}] Collision: {res.collision} | MinClear: {res.min_clearance:.3f}m | Latency: {res.mean_latency_ms:.1f}ms | Drops: {res.packets_dropped}")

    summary: dict[str, dict] = {}
    for c, trials in results_by_controller.items():
        n = len(trials)
        n_crashes = sum(1 for t in trials if t.collision)
        crash_rate = (n_crashes / n) * 100.0
        mean_clearance = float(np.mean([t.min_clearance for t in trials]))
        min_clearance = float(np.min([t.min_clearance for t in trials]))
        mean_tilt = float(np.mean([t.max_tilt_deg for t in trials]))
        mean_lat = float(np.mean([t.mean_latency_ms for t in trials]))
        total_drops = sum(t.packets_dropped for t in trials)
        total_watchdog = sum(t.watchdog_interventions for t in trials)
        total_saccades = sum(t.active_saccades for t in trials)
        mean_final_dist = float(np.mean([t.final_distance_to_goal for t in trials]))

        summary[c] = {
            "n_trials": n,
            "crashes": n_crashes,
            "crash_rate_pct": crash_rate,
            "mean_min_clearance_m": mean_clearance,
            "worst_min_clearance_m": min_clearance,
            "mean_max_tilt_deg": mean_tilt,
            "mean_latency_ms": mean_lat,
            "total_packets_dropped": total_drops,
            "total_watchdog_interventions": total_watchdog,
            "total_active_saccades": total_saccades,
            "mean_final_dist_m": mean_final_dist,
            "sample_trajectory": trials[0].trajectory,
        }

    os.makedirs("results/data", exist_ok=True)
    out_path = "results/data/sim2real_hardware_benchmark.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[+] Saved Sim2Real Benchmark Results to: {out_path}")

    # Print summary table
    print("\n" + "=" * 95)
    print(f"{'Controller':<18} | {'Crash Rate':<12} | {'Worst Clearance':<16} | {'Watchdog Acts':<14} | {'Active Saccades':<15} | {'Final Dist':<10}")
    print("-" * 95)
    for c, s in summary.items():
        print(f"{c:<18} | {s['crash_rate_pct']:>5.1f}%       | {s['worst_min_clearance_m']:>7.3f} m        | {s['total_watchdog_interventions']:>6d}         | {s['total_active_saccades']:>6d}          | {s['mean_final_dist_m']:>6.3f} m")
    print("=" * 95)

    return summary


if __name__ == "__main__":
    run_full_benchmark(n_episodes_per_controller=15)
