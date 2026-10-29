"""
NEXVIA AEGIS — Safe RL Environment Wrapper for 6-DOF Quadrotor Dynamics.

Provides:
1. Standard RL Step & Reset interface (compatible with PPO / Actor-Critic).
2. Dynamic Moving Obstacles with time-varying trajectories: c_obs(t) = c_0 + v_obs * t.
3. Differentiable HOCBF Safety Shielding between the neural actor policy and physical motors.
4. Barrier Intervention Cost computation: L_shield = ||u_safe - u_RL||^2.
5. Standardized 20-dimensional normalized observation vector.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Tuple

import numpy as np

from aegis.env.deep_aerodynamics import DeepAerodynamicsConfig
from aegis.env.mujoco_3d_cbf import Obstacle3D
from aegis.env.quadrotor_6dof import (
    AegisQuadrotor6DOFEnvironment,
    QuadrotorConfig,
    quaternion_to_rotation_matrix,
)


@dataclass
class DynamicObstacle3D:
    """Represents a moving spherical obstacle with linear velocity."""
    center: np.ndarray        # current position in R^3
    radius: float             # collision radius in meters
    velocity: np.ndarray      # velocity vector in R^3
    bounds: tuple[float, float] = (-2.0, 2.0)  # rebound boundaries along movement axis


class Safe6DOFQuadrotorEnv:
    """
    Continuous 6-DOF Quadrotor Safe RL Environment.
    Observation space: R^20 (continuous)
    Action space: R^3 (continuous force offset in [-1.0, 1.0])
    """

    def __init__(
        self,
        shield_enabled: bool = True,
        enable_deep_aero: bool = True,
        max_steps: int = 150,
        intervention_penalty_weight: float = 0.05,
    ) -> None:
        self.shield_enabled = shield_enabled
        self.max_steps = max_steps
        self.intervention_penalty_weight = intervention_penalty_weight

        # 6-DOF Quadrotor Physics Configuration
        deep_cfg = DeepAerodynamicsConfig(
            ige_enabled=True,
            gyroscopic_enabled=True,
            battery_enabled=True,
        ) if enable_deep_aero else None

        self.quad_cfg = QuadrotorConfig(
            enable_deep_aerodynamics=enable_deep_aero,
            deep_aero_config=deep_cfg,
            max_thrust_per_motor=8.5,
            inner_dt=0.005,
            outer_dt=0.02,
        )

        self.sim = AegisQuadrotor6DOFEnvironment(self.quad_cfg)
        self.target_pos = np.array([1.8, 1.8, 1.2], dtype=np.float64)
        self.sim.target_pos = self.target_pos

        # Dynamic obstacles with periodic rebounding velocity
        self.dynamic_obstacles: list[DynamicObstacle3D] = [
            DynamicObstacle3D(
                center=np.array([0.0, -0.6, 0.9], dtype=np.float64),
                radius=0.38,
                velocity=np.array([0.0, 0.65, 0.0], dtype=np.float64),
                bounds=(-0.9, 0.9),
            ),
            DynamicObstacle3D(
                center=np.array([1.0, 0.5, 0.8], dtype=np.float64),
                radius=0.35,
                velocity=np.array([-0.50, 0.0, 0.0], dtype=np.float64),
                bounds=(0.2, 1.4),
            ),
        ]

        self.step_idx = 0
        self.cumulative_interventions = 0
        self.cumulative_intervention_norm = 0.0

    def reset(self, rng: np.random.Generator | None = None) -> np.ndarray:
        """Resets simulation and obstacle states, returning initial observation."""
        self.step_idx = 0
        self.cumulative_interventions = 0
        self.cumulative_intervention_norm = 0.0

        # Reset dynamic obstacles to initial positions
        self.dynamic_obstacles[0].center = np.array([0.0, -0.6, 0.9], dtype=np.float64)
        self.dynamic_obstacles[0].velocity = np.array([0.0, 0.65, 0.0], dtype=np.float64)

        self.dynamic_obstacles[1].center = np.array([1.0, 0.5, 0.8], dtype=np.float64)
        self.dynamic_obstacles[1].velocity = np.array([-0.50, 0.0, 0.0], dtype=np.float64)

        raw_state = self.sim.reset(rng=rng, initial_soc=1.0)
        return self._get_obs(raw_state)

    def _step_dynamic_obstacles(self, dt: float) -> None:
        """Updates moving obstacle positions with bounding rebounds."""
        for obs in self.dynamic_obstacles:
            obs.center += obs.velocity * dt
            # Rebound along primary movement axis
            if obs.velocity[1] != 0.0:
                if obs.center[1] < obs.bounds[0] or obs.center[1] > obs.bounds[1]:
                    obs.velocity[1] *= -1.0
            if obs.velocity[0] != 0.0:
                if obs.center[0] < obs.bounds[0] or obs.center[0] > obs.bounds[1]:
                    obs.velocity[0] *= -1.0

    def _get_obs(self, st: dict[str, Any]) -> np.ndarray:
        """Constructs 20-dimensional normalized observation vector."""
        pos = st["pos"]
        vel = st["vel"]
        R = st["rotation_matrix"]
        omega = st["omega_body"]

        pos_err = (self.target_pos - pos) / 3.0
        vel_norm = vel / 4.0
        z_body = R[:, 2] # quadrotor vertical orientation vector
        omega_norm = omega / 5.0

        # Find nearest obstacle (combining static and dynamic obstacles)
        all_obs_centers = [obs.center for obs in self.sim.obstacles] + [dyn.center for dyn in self.dynamic_obstacles]
        dists = [float(np.linalg.norm(pos - c)) for c in all_obs_centers]
        min_idx = int(np.argmin(dists))
        nearest_center = all_obs_centers[min_idx]
        rel_obs = (nearest_center - pos) / 2.5

        if min_idx >= len(self.sim.obstacles):
            dyn_idx = min_idx - len(self.sim.obstacles)
            rel_vel = (self.dynamic_obstacles[dyn_idx].velocity - vel) / 4.0
        else:
            rel_vel = -vel / 4.0

        soc = st["deep_aero"]["soc"] if st["deep_aero"] is not None else 1.0
        tilt_rad = math.radians(st["tilt_deg"]) / (math.pi / 2.0)

        obs_vec = np.concatenate([
            pos_err,        # 3
            vel_norm,       # 3
            z_body,         # 3
            omega_norm,     # 3
            rel_obs,        # 3
            rel_vel,        # 3
            [soc],          # 1
            [tilt_rad],     # 1
        ]).astype(np.float32)

        return np.clip(obs_vec, -5.0, 5.0)

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        """
        Executes one RL environment step:
        1. Action mapping from continuous policy output to 3D force.
        2. Differentiable HOCBF Safety Shield projection (if enabled).
        3. Advances 6-DOF MuJoCo physics and dynamic obstacles.
        4. Calculates dense task reward + shield intervention penalty.
        """
        self.step_idx += 1
        action_clamped = np.clip(action, -1.0, 1.0)

        # Residual Safe RL Formulation:
        # F_net = F_nominal(target) + F_RL(s)
        # Nominal tracking force drives toward destination:
        pos_curr = self.sim.data.qpos[:3].copy()
        vel_curr = self.sim.data.qvel[:3].copy()
        mg = self.quad_cfg.mass * self.quad_cfg.gravity

        k_p = 2.8
        k_d = 1.4
        f_nominal = k_p * (self.target_pos - pos_curr) - k_d * vel_curr
        f_nominal[2] += mg

        # Policy outputs adaptive evasion offset
        f_scale_horiz = 10.0
        f_scale_vert = 14.0
        f_rl_offset = np.array([
            action_clamped[0] * f_scale_horiz,
            action_clamped[1] * f_scale_horiz,
            action_clamped[2] * f_scale_vert,
        ], dtype=np.float64)

        desired_force_rl = f_nominal + f_rl_offset

        # Combine static obstacles + current dynamic obstacles for CBF
        active_cbf_obstacles = list(self.sim.obstacles) + [
            Obstacle3D(center=d.center.copy(), radius=d.radius)
            for d in self.dynamic_obstacles
        ]
        self.sim.obstacles = active_cbf_obstacles

        # Step dynamic obstacles
        self._step_dynamic_obstacles(self.quad_cfg.outer_dt)

        # Apply HOCBF Safety Shield
        intervention_norm = 0.0
        barrier_active = False

        if self.shield_enabled:
            st_pre = self.sim.get_state()
            f_safe, barrier_active = self.sim.cbf.filter_safe_force(
                pos=st_pre["pos"],
                vel=st_pre["vel"],
                desired_force=desired_force_rl,
                obstacles=active_cbf_obstacles,
                current_tilt=math.radians(st_pre["tilt_deg"]),
            )
            intervention_norm = float(np.linalg.norm(f_safe - desired_force_rl))
            if barrier_active:
                self.cumulative_interventions += 1
                self.cumulative_intervention_norm += intervention_norm
            f_to_apply = f_safe
        else:
            f_to_apply = desired_force_rl

        # Execute 6-DOF step in MuJoCo
        st_next, _ = self.sim.step_outer(
            desired_force_world=f_to_apply,
            shield_with_cbf=False, # already filtered above
        )

        # Check collision with dynamic obstacles
        pos_drone = st_next["pos"]
        r_quad = self.quad_cfg.robot_collision_radius
        dyn_collision = any(
            float(np.linalg.norm(pos_drone - d.center)) < (r_quad + d.radius)
            for d in self.dynamic_obstacles
        )
        total_collision = st_next["collision"] or dyn_collision

        # Compute Rewards
        dist_to_target = float(np.linalg.norm(pos_drone - self.target_pos))
        vel_norm = float(np.linalg.norm(st_next["vel"]))
        arrived = dist_to_target < 0.28 and vel_norm < 0.40

        # Reward formulation:
        # Progress reward + speed regulation - action penalty - shield intervention penalty
        r_progress = -1.2 * dist_to_target
        r_vel = -0.08 * vel_norm
        r_action = -0.02 * float(np.sum(action_clamped**2))
        r_intervention = -self.intervention_penalty_weight * (intervention_norm ** 2)

        reward = r_progress + r_vel + r_action + r_intervention

        if arrived:
            reward += 100.0
        if total_collision:
            reward -= 80.0

        terminated = arrived or (total_collision and not self.shield_enabled)
        truncated = self.step_idx >= self.max_steps

        info = {
            "distance": dist_to_target,
            "arrived": arrived,
            "collision": total_collision,
            "barrier_active": barrier_active,
            "intervention_norm": intervention_norm,
            "cumulative_interventions": self.cumulative_interventions,
            "soc": st_next["deep_aero"]["soc"] if st_next["deep_aero"] is not None else 1.0,
            "tilt_deg": st_next["tilt_deg"],
            "drone_pos": pos_drone.copy(),
        }

        obs_next = self._get_obs(st_next)
        return obs_next, reward, terminated, truncated, info
