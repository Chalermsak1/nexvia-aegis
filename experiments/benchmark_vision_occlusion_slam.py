"""
NEXVIA AEGIS — Benchmark: Active Vision & LiDAR SLAM under Occlusion.

Compares 3 navigation controllers in a continuous 3D narrow-corridor scenario
with a moving obstacle hidden behind a foreground pillar:
1. Architecture A: Blind Baseline (Prior map only, unaware of dynamic occluded drift)
2. Architecture B: Passive Vision (Rigid forward camera, no active gaze saccade)
3. Architecture C: AEGIS Active Vision POMDP + UKF + Robust HOCBF Shield
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import mujoco
import numpy as np

from aegis.env.deep_aerodynamics import DeepAerodynamicsConfig
from aegis.env.quadrotor_6dof import (
    AegisQuadrotor6DOFEnvironment,
    QuadrotorConfig,
)
from aegis.vision.depth_lidar_sensor import (
    DepthCameraConfig,
    Lidar3DConfig,
    ObstacleTarget,
    SimulatedPerceptionSuite,
)
from aegis.vision.ukf_obstacle_tracker import (
    MultiObstacleUKFTracker,
    TrackedObstacle3D,
    UKFTrackerConfig,
)
from aegis.vision.active_pomdp_gaze import (
    ActiveVisionConfig,
    ActiveVisionPOMDPController,
)


def run_single_episode(
    controller_type: str,  # "blind", "passive", "aegis_active"
    seed: int = 42,
    max_steps: int = 150,
) -> Dict[str, Any]:
    rng = np.random.default_rng(seed)
    quad_cfg = QuadrotorConfig(
        enable_deep_aerodynamics=True,
        deep_aero_config=DeepAerodynamicsConfig(),
        max_thrust_per_motor=8.5,
        inner_dt=0.005,
        outer_dt=0.02,
    )
    start_pos = np.array([-1.2, 0.0, 1.0], dtype=np.float64)
    target_pos = np.array([1.6, 0.0, 1.0], dtype=np.float64)

    # Obstacles:
    # 1. Foreground Pillar at X=0.2, Y=0.22, radius 0.38
    # 2. Dynamic Obstacle hidden behind Pillar 1, creeping into transit slit
    # 3. Flanking Pillar at X=0.2, Y=-0.60, radius 0.38
    obs1 = ObstacleTarget(obs_id=1, center=np.array([0.2, 0.22, 1.0]), radius=0.38)
    obs2_init = np.array([0.9, 0.32, 1.0]) + rng.normal(0.0, 0.015, size=3)
    obs2_vel = np.array([-0.06, -0.08, 0.0]) + rng.normal(0.0, 0.005, size=3)
    obs2 = ObstacleTarget(obs_id=2, center=obs2_init, radius=0.28, velocity=obs2_vel)
    obs3 = ObstacleTarget(obs_id=3, center=np.array([0.2, -0.60, 1.0]), radius=0.38)
    obstacles = [obs1, obs2, obs3]

    from aegis.env.mujoco_3d_cbf import Obstacle3D
    env = AegisQuadrotor6DOFEnvironment(
        config=quad_cfg,
        obstacles=[
            Obstacle3D(center=obs1.center, radius=obs1.radius),
            Obstacle3D(center=obs3.center, radius=obs3.radius),
        ],
        target_pos=target_pos,
    )
    env.reset(rng)
    env.data.qpos[:3] = start_pos
    env.data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    env.data.qvel[:] = 0.0
    mujoco.mj_forward(env.model, env.data)
    env.target_pos = target_pos

    # Obstacles:
    # 1. Foreground Pillar at X=0.2, Y=0.22, radius 0.38
    # 2. Dynamic Obstacle hidden behind Pillar 1, creeping into transit slit
    # 3. Flanking Pillar at X=0.2, Y=-0.60, radius 0.38
    obs1 = ObstacleTarget(obs_id=1, center=np.array([0.2, 0.22, 1.0]), radius=0.38)
    obs2_init = np.array([0.9, 0.32, 1.0]) + rng.normal(0.0, 0.015, size=3)
    obs2_vel = np.array([-0.06, -0.08, 0.0]) + rng.normal(0.0, 0.005, size=3)
    obs2 = ObstacleTarget(obs_id=2, center=obs2_init, radius=0.28, velocity=obs2_vel)
    obs3 = ObstacleTarget(obs_id=3, center=np.array([0.2, -0.60, 1.0]), radius=0.38)
    obstacles = [obs1, obs2, obs3]

    perception = SimulatedPerceptionSuite(
        camera_cfg=DepthCameraConfig(range_noise_std=0.02),
        lidar_cfg=Lidar3DConfig(range_noise_std=0.015),
    )
    ukf = MultiObstacleUKFTracker(UKFTrackerConfig(confirmation_hits=1, dt=0.02))
    ukf.update_from_clusters([(o.center, o.radius) for o in obstacles])

    ctrl = ActiveVisionPOMDPController(ActiveVisionConfig(
        kappa_safety=2.0,
        max_uncertainty_margin=0.22,
        uncertainty_safe_thresh=0.08,
        nominal_speed=0.95,
        min_probing_speed=0.25,
    ))

    trajectory: List[List[float]] = []
    uncertainty_history: List[float] = []
    gaze_yaw_history: List[float] = []
    speed_history: List[float] = []
    occlusion_flags: List[bool] = []
    min_dist_to_obs = float("inf")
    collision_occurred = False
    active_probing_steps = 0

    drone_yaw_deg = 0.0

    for step in range(max_steps):
        st = env.get_state()
        p = st["pos"]
        v = st["vel"]
        R_drone = st["rotation_matrix"]

        # Dynamic obstacle motion
        obs2.center += obs2.velocity * 0.02

        # Physical clearance check
        for obs in obstacles:
            clr = float(np.linalg.norm(p - obs.center)) - (quad_cfg.robot_collision_radius + obs.radius)
            if clr < min_dist_to_obs:
                min_dist_to_obs = clr
            if clr <= 0.0:
                collision_occurred = True

        # Controller execution & camera gaze
        if controller_type == "aegis_active":
            dec = ctrl.plan_step(p, v, drone_yaw_deg, target_pos, ukf.get_confirmed_tracks())
            cam = perception.capture_depth_camera(
                p, R_drone, obstacles,
                gimbal_pan_deg=dec.desired_pan_deg,
                gimbal_tilt_deg=dec.desired_tilt_deg,
                rng=rng,
            )
            force_cmd = dec.safe_force
            drone_yaw_deg = dec.desired_yaw_deg
            if dec.is_actively_probing:
                active_probing_steps += 1

        elif controller_type == "passive":
            dec = ctrl.plan_step(p, v, 0.0, target_pos, ukf.get_confirmed_tracks())
            # Forward camera only: no gaze saccade
            cam = perception.capture_depth_camera(
                p, R_drone, obstacles,
                gimbal_pan_deg=0.0,
                gimbal_tilt_deg=0.0,
                rng=rng,
            )
            force_cmd = dec.safe_force
            drone_yaw_deg = 0.0

        else:  # blind
            cam = None
            to_tgt = target_pos - p
            dist_tgt = np.linalg.norm(to_tgt)
            vel_des = (to_tgt / max(1e-4, dist_tgt)) * 1.1
            acc = 2.4 * (target_pos - p) + 1.8 * (vel_des - v)
            force_cmd = quad_cfg.mass * (acc + np.array([0.0, 0.0, quad_cfg.gravity]))
            # Tilt clamping
            F_z = max(0.5 * quad_cfg.mass * quad_cfg.gravity, force_cmd[2])
            max_lat = F_z * math.tan(math.radians(35.0))
            lat = math.hypot(force_cmd[0], force_cmd[1])
            if lat > max_lat:
                force_cmd[0] *= (max_lat / lat)
                force_cmd[1] *= (max_lat / lat)
            force_cmd[2] = F_z
            drone_yaw_deg = 0.0

        # Point cloud to UKF measurement update
        is_obs2_occluded = (obs2.obs_id in cam.occluded_obstacle_ids) if cam else True
        if cam is not None and len(cam.point_cloud) > 0:
            clusters = [
                (obs.center + rng.normal(0.0, 0.015, size=3), obs.radius)
                for obs in obstacles if obs.obs_id in cam.visible_obstacle_ids
            ]
            ukf.update_from_clusters(clusters)

        tracks = ukf.get_confirmed_tracks()
        obs2_track = next((t for t in tracks if np.linalg.norm(t.position - obs2.center) < 0.9), None)
        obs2_unc = obs2_track.max_position_std if obs2_track else 0.40

        # Step 6-DOF MuJoCo
        env.step_outer(
            desired_force_world=force_cmd,
            shield_with_cbf=False,
            desired_yaw=math.radians(drone_yaw_deg),
        )

        trajectory.append(p.tolist())
        uncertainty_history.append(float(obs2_unc))
        gaze_yaw_history.append(float(drone_yaw_deg))
        speed_history.append(float(np.linalg.norm(v)))
        occlusion_flags.append(bool(is_obs2_occluded))

        if np.linalg.norm(p - target_pos) <= 0.25:
            break

    final_pos = env.get_state()["pos"]
    final_dist = float(np.linalg.norm(final_pos - target_pos))
    success = (final_dist <= 0.28) and not collision_occurred

    return {
        "controller": controller_type,
        "seed": seed,
        "success": success,
        "collision": collision_occurred,
        "min_clearance_m": float(min_dist_to_obs),
        "final_dist_to_target_m": final_dist,
        "steps": len(trajectory),
        "active_probing_steps": active_probing_steps,
        "final_obs2_uncertainty_std": float(uncertainty_history[-1]) if uncertainty_history else 0.0,
        "trajectory": trajectory,
        "uncertainty_history": uncertainty_history,
        "gaze_yaw_history": gaze_yaw_history,
        "speed_history": speed_history,
        "occlusion_flags": occlusion_flags,
    }


def run_full_benchmark(n_episodes: int = 15) -> Dict[str, Any]:
    print(f"[*] Running Active Vision & LiDAR SLAM Benchmark across {n_episodes} episodes...")
    controllers = ["blind", "passive", "aegis_active"]
    results: Dict[str, List[Dict[str, Any]]] = {c: [] for c in controllers}

    for c in controllers:
        for ep in range(n_episodes):
            seed = 1000 + ep * 17
            ep_res = run_single_episode(controller_type=c, seed=seed)
            results[c].append(ep_res)
            print(f"    [{c:12s}] Ep {ep+1:02d}/{n_episodes}: Success={ep_res['success']} Collision={ep_res['collision']} MinClr={ep_res['min_clearance_m']:.3f}m Steps={ep_res['steps']:3d} DistToTgt={ep_res['final_dist_to_target_m']:.2f}m")

    summary: Dict[str, Any] = {}
    for c in controllers:
        eps = results[c]
        n = len(eps)
        collisions = sum(1 for e in eps if e["collision"])
        successes = sum(1 for e in eps if e["success"])
        mean_clearance = float(np.mean([e["min_clearance_m"] for e in eps]))
        mean_steps = float(np.mean([e["steps"] for e in eps]))
        mean_probing = float(np.mean([e["active_probing_steps"] for e in eps]))
        mean_final_unc = float(np.mean([e["final_obs2_uncertainty_std"] for e in eps]))
        mean_final_dist = float(np.mean([e["final_dist_to_target_m"] for e in eps]))

        summary[c] = {
            "episodes": n,
            "collision_count": collisions,
            "collision_rate_pct": (collisions / n) * 100.0,
            "success_rate_pct": (successes / n) * 100.0,
            "mean_min_clearance_m": mean_clearance,
            "mean_steps": mean_steps,
            "mean_final_dist_to_target_m": mean_final_dist,
            "mean_active_probing_steps": mean_probing,
            "mean_final_uncertainty_std": mean_final_unc,
        }

    output_payload = {
        "summary": summary,
        "episodes": results,
    }

    out_path = Path("results/data/vision_occlusion_slam_benchmark.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")
    print(f"\n[+] Active Vision Benchmark successfully saved to {out_path}")
    print("=" * 80)
    for c, s in summary.items():
        print(f"[{c:12s}] Success: {s['success_rate_pct']:.1f}% | Collisions: {s['collision_rate_pct']:.1f}% | MinClr: {s['mean_min_clearance_m']:.3f}m | FinalDist: {s['mean_final_dist_to_target_m']:.2f}m | FinalUnc: {s['mean_final_uncertainty_std']:.3f}m")
    print("=" * 80)
    return output_payload


if __name__ == "__main__":
    run_full_benchmark(n_episodes=15)
