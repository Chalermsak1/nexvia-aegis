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
import mujoco

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
        adaptive_cbf: bool = False,
        enable_deep_aero: bool = True,
        max_steps: int = 150,
        intervention_penalty_weight: float = 0.05,
        energy_penalty_weight: float = 0.015,
        smoothness_penalty_weight: float = 0.005,
        enable_innovation_gate: bool = False,
        sensor_fault_config: dict[str, Any] | None = None,
    ) -> None:
        self.shield_enabled = shield_enabled
        self.adaptive_cbf = adaptive_cbf
        self.max_steps = max_steps
        self.intervention_penalty_weight = intervention_penalty_weight
        self.energy_penalty_weight = energy_penalty_weight
        self.smoothness_penalty_weight = smoothness_penalty_weight
        self.enable_innovation_gate = enable_innovation_gate
        self.sensor_fault_config = sensor_fault_config

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
        self.cumulative_control_energy = 0.0
        self.cumulative_jerk = 0.0
        mg = self.quad_cfg.mass * self.quad_cfg.gravity
        self.last_applied_force = np.array([0.0, 0.0, mg], dtype=np.float64)
        self.dwell_steps = 0
        self.innovation_gate_open = False
        self.abstained = False
        self.estimated_pos = np.zeros(3, dtype=np.float64)
        self.estimated_vel = np.zeros(3, dtype=np.float64)

    def reset(
        self,
        rng: np.random.Generator | None = None,
        initial_pos: np.ndarray | None = None,
    ) -> np.ndarray:
        """Resets simulation and obstacle states, returning initial observation."""
        self.step_idx = 0
        self.cumulative_interventions = 0
        self.cumulative_intervention_norm = 0.0
        self.cumulative_control_energy = 0.0
        self.cumulative_jerk = 0.0
        mg = self.quad_cfg.mass * self.quad_cfg.gravity
        self.last_applied_force = np.array([0.0, 0.0, mg], dtype=np.float64)
        self.dwell_steps = 0
        self.innovation_gate_open = False
        self.abstained = False

        # Reset dynamic obstacles to initial positions
        self.dynamic_obstacles[0].center = np.array([0.0, -0.6, 0.9], dtype=np.float64)
        self.dynamic_obstacles[0].velocity = np.array([0.0, 0.65, 0.0], dtype=np.float64)

        self.dynamic_obstacles[1].center = np.array([1.0, 0.5, 0.8], dtype=np.float64)
        self.dynamic_obstacles[1].velocity = np.array([-0.50, 0.0, 0.0], dtype=np.float64)

        raw_state = self.sim.reset(rng=rng, initial_soc=1.0)
        if initial_pos is not None:
            self.sim.data.qpos[:3] = np.asarray(initial_pos, dtype=np.float64)
            self.sim.data.qvel[:] = 0.0
            mujoco.mj_forward(self.sim.model, self.sim.data)
            raw_state = self.sim.get_state()

        self.estimated_pos = raw_state["pos"].copy()
        self.estimated_vel = raw_state["vel"].copy()
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
        2. Sensor fault injection & Dual Innovation Gate evaluation.
        3. Adaptive HOCBF Safety Shield projection (if enabled).
        4. Advances 6-DOF MuJoCo physics and dynamic obstacles.
        5. Computes energy consumption, smoothness, and task rewards.
        6. Verifies Physical Dwell Rest (E-05) vs Perceived Arrival for 0% Selective Risk.
        """
        self.step_idx += 1
        action_clamped = np.clip(action, -1.0, 1.0)
        dt = self.quad_cfg.outer_dt

        pos_curr = self.sim.data.qpos[:3].copy()
        vel_curr = self.sim.data.qvel[:3].copy()
        mg = self.quad_cfg.mass * self.quad_cfg.gravity

        # 1. Sensor observation & fault perturbation
        sensor_fault_active = False
        pos_obs = pos_curr.copy()
        vel_obs = vel_curr.copy()

        if self.sensor_fault_config is not None:
            start_s = self.sensor_fault_config.get("start_step", 25)
            if self.step_idx >= start_s:
                sensor_fault_active = True
                f_type = self.sensor_fault_config.get("fault_type", "range_drift")
                if f_type == "spoof_arrival":
                    # Spoofs position directly to target (claims premature arrival)
                    pos_obs = self.target_pos.copy() + np.random.normal(0, 0.02, 3)
                    vel_obs = np.array([0.02, -0.01, 0.0], dtype=np.float64)
                elif f_type == "range_drift":
                    drift_dir = (self.target_pos - pos_curr)
                    norm_d = float(np.linalg.norm(drift_dir))
                    if norm_d > 1e-4:
                        drift_dir = drift_dir / norm_d
                    pos_obs += drift_dir * min(1.2, 0.05 * (self.step_idx - start_s))
                elif f_type == "velocity_noise":
                    vel_obs += np.random.normal(0, 0.35, 3)

        # 2. Dual-Sensor Fusion & Innovation Gate (E-05, E-06)
        # Update internal momentum model: F_net = F_applied - mg e3
        a_net = (self.last_applied_force / self.quad_cfg.mass) - np.array([0.0, 0.0, self.quad_cfg.gravity])
        self.estimated_vel = 0.85 * self.estimated_vel + 0.15 * (vel_curr + a_net * dt)
        self.estimated_pos += self.estimated_vel * dt

        innovation_residual = float(np.linalg.norm(pos_obs - self.estimated_pos))
        vel_innovation = float(np.linalg.norm(vel_obs - self.estimated_vel))

        if self.enable_innovation_gate and sensor_fault_active:
            if innovation_residual > 0.22 or vel_innovation > 0.30:
                self.innovation_gate_open = True
                self.abstained = True

        # 3. Residual Guidance Force
        if self.enable_innovation_gate and self.abstained:
            # Active safe fallback: velocity air-brake and level hover
            desired_force_rl = np.array([0.0, 0.0, mg], dtype=np.float64) - 2.5 * vel_curr
            desired_force_rl[2] = mg - 1.5 * vel_curr[2]
        else:
            k_p = 3.2
            dist_raw = float(np.linalg.norm(self.target_pos - pos_curr))
            k_d = 3.2 if dist_raw < 0.85 else 1.6
            f_nominal = k_p * (self.target_pos - pos_curr) - k_d * vel_curr
            f_nominal[2] += mg

            f_scale_horiz = 10.0
            f_scale_vert = 14.0
            f_rl_offset = np.array([
                action_clamped[0] * f_scale_horiz,
                action_clamped[1] * f_scale_horiz,
                action_clamped[2] * f_scale_vert,
            ], dtype=np.float64)

            desired_force_rl = f_nominal + f_rl_offset

        # 4. Dynamic obstacles update
        active_cbf_obstacles = list(self.sim.obstacles) + [
            Obstacle3D(center=d.center.copy(), radius=d.radius)
            for d in self.dynamic_obstacles
        ]
        self.sim.obstacles = active_cbf_obstacles
        self._step_dynamic_obstacles(self.quad_cfg.outer_dt)

        # 5. Adaptive HOCBF Safety Shield
        intervention_norm = 0.0
        barrier_active = False

        if self.shield_enabled:
            st_pre = self.sim.get_state()
            adaptive_gammas = None
            if self.adaptive_cbf:
                v_mag = float(np.linalg.norm(st_pre["vel"]))
                # Velocity-scaled contraction factor: proactive at high speeds, agile at low speeds
                g_adapt = self.quad_cfg.cbf_gamma * (1.0 + 0.35 * min(2.5, v_mag / 1.2))
                adaptive_gammas = (g_adapt, g_adapt)

            f_safe, barrier_active = self.sim.cbf.filter_safe_force(
                pos=st_pre["pos"],
                vel=st_pre["vel"],
                desired_force=desired_force_rl,
                obstacles=active_cbf_obstacles,
                current_tilt=math.radians(st_pre["tilt_deg"]),
                adaptive_gammas=adaptive_gammas,
            )
            intervention_norm = float(np.linalg.norm(f_safe - desired_force_rl))
            if barrier_active:
                self.cumulative_interventions += 1
                self.cumulative_intervention_norm += intervention_norm
            f_to_apply = f_safe
        else:
            f_to_apply = desired_force_rl

        # 6. Control Energy & Smoothness / Jerk Tracking
        f_hover = np.array([0.0, 0.0, mg], dtype=np.float64)
        step_energy = float(np.sum((f_to_apply - f_hover)**2)) * dt
        self.cumulative_control_energy += step_energy

        step_jerk = float(np.linalg.norm(f_to_apply - self.last_applied_force)) / dt
        self.cumulative_jerk += step_jerk * dt
        self.last_applied_force = f_to_apply.copy()

        # 7. Execute 6-DOF step in MuJoCo
        st_next, _ = self.sim.step_outer(
            desired_force_world=f_to_apply,
            shield_with_cbf=False,
        )

        # 8. Check collision
        pos_drone = st_next["pos"]
        r_quad = self.quad_cfg.robot_collision_radius
        dyn_collision = any(
            float(np.linalg.norm(pos_drone - d.center)) < (r_quad + d.radius)
            for d in self.dynamic_obstacles
        )
        total_collision = st_next["collision"] or dyn_collision

        # 9. Physical Dwell Rest (E-05) & Arrival Verification
        dist_to_target = float(np.linalg.norm(pos_drone - self.target_pos))
        vel_norm = float(np.linalg.norm(st_next["vel"]))

        is_phys_near = dist_to_target < 0.28 and vel_norm < 0.25
        if is_phys_near:
            self.dwell_steps += 1
        else:
            self.dwell_steps = 0
        phys_arrived = self.dwell_steps >= 5

        # Perceived arrival (what an unshielded or un-gated observer reports)
        dist_perceived = float(np.linalg.norm(pos_obs - self.target_pos))
        vel_perceived = float(np.linalg.norm(vel_obs))
        perceived_arrived = dist_perceived < 0.28 and vel_perceived < 0.35

        false_arrival = False
        true_arrival = False

        if self.enable_innovation_gate and self.abstained:
            arrived = False
        elif phys_arrived:
            true_arrival = True
            arrived = True
        elif perceived_arrived and not phys_arrived:
            false_arrival = True
            arrived = True
        else:
            arrived = False

        # 10. Multi-Objective Energy-Aware Reward
        r_progress = -1.2 * dist_to_target
        r_vel = -0.08 * vel_norm
        r_action = -0.02 * float(np.sum(action_clamped**2))
        r_intervention = -self.intervention_penalty_weight * (intervention_norm ** 2)
        r_energy = -self.energy_penalty_weight * (step_energy / ((mg**2) * dt))
        r_jerk = -self.smoothness_penalty_weight * (step_jerk / (mg * 10.0))

        reward = r_progress + r_vel + r_action + r_intervention + r_energy + r_jerk

        if true_arrival:
            reward += 120.0
        elif false_arrival:
            reward -= 50.0

        if total_collision:
            reward -= 80.0

        terminated = arrived or (total_collision and not self.shield_enabled)
        truncated = self.step_idx >= self.max_steps

        info = {
            "distance": dist_to_target,
            "arrived": arrived,
            "true_arrival": true_arrival,
            "false_arrival": false_arrival,
            "abstain": self.abstained,
            "collision": total_collision,
            "barrier_active": barrier_active,
            "intervention_norm": intervention_norm,
            "cumulative_interventions": self.cumulative_interventions,
            "control_energy": self.cumulative_control_energy,
            "mean_jerk": float(self.cumulative_jerk / max(1e-4, self.step_idx * dt)),
            "transit_time_s": float(self.step_idx * dt),
            "soc": st_next["deep_aero"]["soc"] if st_next["deep_aero"] is not None else 1.0,
            "tilt_deg": st_next["tilt_deg"],
            "drone_pos": pos_drone.copy(),
        }

        obs_next = self._get_obs(st_next)
        return obs_next, reward, terminated, truncated, info
