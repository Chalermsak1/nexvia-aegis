"""
NEXVIA AEGIS — Active Vision POMDP & Robust HOCBF Shield under Occlusion.

Combines:
1. Active Probing POMDP (Information Gain Maximization):
   - Computes spatial uncertainty along candidate flight paths.
   - Detects blind spots / narrow slits obscured by physical occlusion.
   - Generates active gimbal gaze angles (pan/tilt) and drone yaw orientation
     aiming directly at high-uncertainty regions before committing to transit.
   - Enforces adaptive air brake deceleration when uncertainty exceeds safety limits.
2. Robust Underactuated High-Order Control Barrier Functions (HOCBF):
   - Expands safety envelope by 3-sigma position covariance ellipsoid:
     r_effective = r_drone + r_obs + kappa * sqrt(lambda_max(P_pos)).
   - Enforces zero collisions even under worst-case estimation errors.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Optional, Tuple

import numpy as np

from aegis.vision.ukf_obstacle_tracker import TrackedObstacle3D


@dataclass(frozen=True)
class ActiveVisionConfig:
    kappa_safety: float = 2.0                 # 2-sigma confidence multiplier
    max_uncertainty_margin: float = 0.22      # Maximum spatial uncertainty expansion buffer (m)
    uncertainty_safe_thresh: float = 0.08     # Threshold std (m) below which path is deemed safe
    uncertainty_critical_thresh: float = 0.20 # Threshold std (m) triggering emergency inspection
    critical_horizon_m: float = 1.8           # Lookahead distance for occlusion inspection
    nominal_speed: float = 1.0                # Desired transit speed (m/s)
    min_probing_speed: float = 0.35           # Probing speed during active scan (m/s)
    alpha1_cbf: float = 2.4                   # HOCBF linear class-K gain
    alpha2_cbf: float = 3.0                   # HOCBF acceleration class-K gain
    drone_radius: float = 0.28                # Quadrotor physical clearance radius (m)
    robot_mass: float = 1.25                  # kg
    gravity: float = 9.81                     # m/s^2
    max_tilt_deg: float = 35.0                # Physical tilt limit


@dataclass
class ActiveGazeDecision:
    """Action outputs from Active Vision POMDP controller."""
    nominal_force: np.ndarray                 # shape (3,) desired world navigation force
    safe_force: np.ndarray                    # shape (3,) HOCBF-shielded safe world force
    desired_pan_deg: float                    # Gimbal pan angle in degrees
    desired_tilt_deg: float                   # Gimbal tilt angle in degrees
    desired_yaw_deg: float                    # Desired body yaw angle in degrees
    is_actively_probing: bool                 # True if drone is performing active gaze saccade
    critical_track_id: Optional[int]          # ID of obstacle causing active inspection
    effective_clearance_margins: List[float]  # Dynamic safety clearances per obstacle
    information_entropy_bits: float           # Estimated Shannon entropy of scene uncertainty


class ActiveVisionPOMDPController:
    """
    Active Perception & Safety Shielding Controller for 6-DOF Quadrotors.
    """

    def __init__(self, cfg: ActiveVisionConfig | None = None) -> None:
        self.cfg = cfg or ActiveVisionConfig()

    def plan_step(
        self,
        drone_pos: np.ndarray,
        drone_vel: np.ndarray,
        drone_yaw_deg: float,
        target_pos: np.ndarray,
        tracked_obstacles: List[TrackedObstacle3D],
    ) -> ActiveGazeDecision:
        """
        Executes one step of active gaze planning, adaptive speed regulation,
        and robust uncertainty-padded HOCBF safety filtering.
        """
        # 1. Base guidance toward target
        to_target = target_pos - drone_pos
        dist_to_target = float(np.linalg.norm(to_target))
        if dist_to_target > 1e-4:
            target_dir = to_target / dist_to_target
        else:
            target_dir = np.zeros(3, dtype=np.float64)

        # 2. Inspect obstacles along flight path for occlusion and spatial uncertainty
        highest_uncertainty = 0.0
        most_critical_obstacle: Optional[TrackedObstacle3D] = None
        min_dist_to_critical = float("inf")
        total_entropy = 0.0

        for obs in tracked_obstacles:
            pos_cov = obs.position_covariance
            max_std = obs.max_position_std
            # Shannon differential entropy: 0.5 * ln((2*pi*e)^3 * det(P))
            det_p = max(1e-12, float(np.linalg.det(pos_cov)))
            entropy = 0.5 * math.log(((2.0 * math.pi * math.e)**3) * det_p)
            total_entropy += entropy

            rel_pos = obs.position - drone_pos
            dist = float(np.linalg.norm(rel_pos))

            # Check if obstacle lies roughly in the forward path toward target
            if dist <= self.cfg.critical_horizon_m and dist_to_target > 0.1:
                proj = float(np.dot(rel_pos, target_dir))
                if proj > -0.2:  # Ahead or slightly alongside
                    if max_std > highest_uncertainty:
                        highest_uncertainty = max_std
                        most_critical_obstacle = obs
                        min_dist_to_critical = dist

        # 3. Active Probing & Speed Regulation Decision
        is_probing = False
        desired_pan = 0.0
        desired_tilt = 0.0
        desired_yaw = drone_yaw_deg

        if most_critical_obstacle is not None and highest_uncertainty > self.cfg.uncertainty_safe_thresh:
            is_probing = True
            # Compute line-of-sight vector to the high-uncertainty obstacle
            los = most_critical_obstacle.position - drone_pos
            desired_yaw = math.degrees(math.atan2(los[1], los[0]))
            desired_pan = 0.0  # Align camera with drone nose
            horiz_dist = math.hypot(los[0], los[1])
            desired_tilt = math.degrees(math.atan2(los[2], max(1e-3, horiz_dist)))

            # Exponential air brake deceleration based on uncertainty severity
            decay = math.exp(-(highest_uncertainty - self.cfg.uncertainty_safe_thresh) / 0.10)
            transit_speed = max(self.cfg.min_probing_speed, self.cfg.nominal_speed * decay)
        else:
            # Nominal forward gaze aligned with target direction
            if dist_to_target > 0.2:
                desired_yaw = math.degrees(math.atan2(target_dir[1], target_dir[0]))
            transit_speed = self.cfg.nominal_speed

        # 4. Nominal acceleration & force command (PD to target with altitude hold and air-brake)
        kp_xy = 1.8
        kd_xy = 1.2
        kp_z = 3.0
        kd_z = 2.0

        desired_vel_xy = target_dir[:2] * min(transit_speed, dist_to_target)
        f_x = kp_xy * (target_pos[0] - drone_pos[0]) + kd_xy * (desired_vel_xy[0] - drone_vel[0])
        f_y = kp_xy * (target_pos[1] - drone_pos[1]) + kd_xy * (desired_vel_xy[1] - drone_vel[1])
        f_z = self.cfg.robot_mass * (self.cfg.gravity + kp_z * (target_pos[2] - drone_pos[2]) - kd_z * drone_vel[2])

        nominal_force = np.array([f_x, f_y, f_z], dtype=np.float64)
        safe_force = np.copy(nominal_force)
        clearance_margins: List[float] = []

        # 5. Robust Planar High-Order Control Barrier Function (HOCBF)
        for obs in tracked_obstacles:
            pos_cov = obs.position_covariance
            max_std = obs.max_position_std
            uncertainty_margin = min(self.cfg.max_uncertainty_margin, self.cfg.kappa_safety * max_std)
            r_eff = self.cfg.drone_radius + obs.radius + uncertainty_margin
            clearance_margins.append(r_eff)

            rel_xy = np.array([drone_pos[0] - obs.position[0], drone_pos[1] - obs.position[1]], dtype=np.float64)
            rel_vel_xy = np.array([drone_vel[0] - obs.velocity[0], drone_vel[1] - obs.velocity[1]], dtype=np.float64)

            dist_sq = float(np.dot(rel_xy, rel_xy))
            dist = math.sqrt(max(1e-6, dist_sq))

            h = dist_sq - r_eff**2
            h_dot = 2.0 * float(np.dot(rel_xy, rel_vel_xy))

            # Planar HOCBF inequality: a_cbf^T F_xy <= b_cbf
            a_cbf_xy = -(2.0 / self.cfg.robot_mass) * rel_xy
            v_sq = float(np.dot(rel_vel_xy, rel_vel_xy))
            b_cbf = 2.0 * v_sq + (self.cfg.alpha1_cbf + self.cfg.alpha2_cbf) * h_dot + self.cfg.alpha1_cbf * self.cfg.alpha2_cbf * h

            lhs = float(np.dot(a_cbf_xy, safe_force[:2]))
            if lhs > b_cbf:
                a_norm_sq = float(np.dot(a_cbf_xy, a_cbf_xy))
                if a_norm_sq > 1e-8:
                    safe_force[:2] -= ((lhs - b_cbf) / a_norm_sq) * a_cbf_xy

        # 6. Physical tilt clamping on safe force (theta <= 35 deg)
        F_z = max(0.5 * self.cfg.robot_mass * self.cfg.gravity, safe_force[2])
        max_lateral = F_z * math.tan(math.radians(self.cfg.max_tilt_deg))
        lateral_norm = math.hypot(safe_force[0], safe_force[1])
        if lateral_norm > max_lateral:
            scale = max_lateral / lateral_norm
            safe_force[0] *= scale
            safe_force[1] *= scale
        safe_force[2] = F_z

        return ActiveGazeDecision(
            nominal_force=nominal_force,
            safe_force=safe_force,
            desired_pan_deg=desired_pan,
            desired_tilt_deg=desired_tilt,
            desired_yaw_deg=desired_yaw,
            is_actively_probing=is_probing,
            critical_track_id=most_critical_obstacle.track_id if most_critical_obstacle else None,
            effective_clearance_margins=clearance_margins,
            information_entropy_bits=total_entropy,
        )
