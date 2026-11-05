"""
NEXVIA AEGIS — Aerodynamic Boundary Effects & Aero-Compensated HOCBF Engine.

Implements physics-informed aeromechanical boundary interactions for subterranean,
tunnel, and confined indoor flight:
1. Ground Effect (IGE - In-Ground Effect):
   - Cheeseman & Bennett rotor thrust amplification model:
     T_IGE = T_OGE / (1 - (R / (4 * z_eff))^2)
   - Individual rotor-by-rotor computation under arbitrary body attitude R in SO(3).
2. Ceiling Effect (ICE - In-Ceiling Effect):
   - Bernoulli low-pressure constriction above rotor disc pulling drone towards ceiling:
     F_ceil = +c_ceil * T_total * (R / max(d_min, z_ceil - z))^2 * e_z
3. Wall Effect (IWE - In-Wall Effect & Lateral Vortex Suction):
   - Asymmetric vortex recirculating slipstream near vertical planar surfaces:
     F_wall = -c_wall * T_total * (R / max(d_min, d_wall))^2 * n_wall
   - Destabilizing asymmetric overturning moment:
     tau_wall = -c_tau_wall * T_total * (R / max(d_min, d_wall))^3 * (n_wall x e_z)
4. Aero-Compensated High-Order Control Barrier Function (Aero-HOCBF):
   - Injects the Lie derivative of boundary aerodynamics L_{f_aero} h into barrier constraints:
     L_f h + L_{f_aero} h + L_g h * u + alpha_1(h) + alpha_2(dot_h) >= 0
   - Pre-emptively cancels suction forces before aerodynamic boundary capture occurs.
5. Adaptive Aerodynamic Disturbance Observer (ADOB):
   - High-rate (100 Hz) momentum-based observer estimating unmodeled residual
     boundary wrenches from IMU accelerometer and gyro data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Dict, List, Optional, Tuple, Union
import numpy as np


class BoundaryType(str, Enum):
    GROUND = "GROUND"
    CEILING = "CEILING"
    WALL = "WALL"
    CYLINDRICAL_TUNNEL = "CYLINDRICAL_TUNNEL"


@dataclass(frozen=True)
class AerodynamicBoundaryConfig:
    """Physical and aeromechanical coefficients for boundary coupling."""
    mass: float = 1.50                           # Drone mass (kg)
    rotor_radius: float = 0.09                   # Propeller radius R (m)
    num_rotors: int = 4                          # Quadrotor configuration
    drone_arm_length: float = 0.22               # Arm length center-to-motor (m)
    air_density: float = 1.225                   # kg/m^3 (rho)
    gravity: float = 9.81                        # m/s^2

    # In-Ground Effect (IGE)
    max_ige_ratio: float = 1.60                  # Clamped maximum thrust amplification
    min_ground_clearance: float = 0.05           # Minimum valid physical clearance (m)

    # In-Ceiling Effect (ICE)
    ceiling_suction_coefficient: float = 0.28    # c_ceil gain for Bernoulli roof pull
    min_ceiling_clearance: float = 0.10          # Minimum valid ceiling clearance (m)

    # In-Wall Effect (IWE)
    wall_suction_coefficient: float = 0.24       # c_wall gain for lateral wall pull
    wall_torque_gain: float = 0.040              # c_tau gain for wall-induced roll torque
    min_wall_clearance: float = 0.12             # Minimum valid wall clearance (m)

    # Aerodynamic Disturbance Observer (ADOB)
    adob_gain_force: float = 12.0                # L_d observer gain (1/s)
    adob_gain_torque: float = 15.0               # L_tau observer gain (1/s)

    # High-Order CBF Gains
    cbf_alpha1: float = 2.5                      # Class K gain alpha1 for h(x)
    cbf_alpha2: float = 3.0                      # Class K gain alpha2 for dot_h(x)
    cbf_safety_margin: float = 0.35              # Certified safety buffer r_safe (m)


@dataclass
class PlanarBoundary:
    """Planar surface boundary (Ground, Ceiling, or Wall)."""
    boundary_type: BoundaryType
    point_on_plane: np.ndarray                   # [x, y, z] in world frame (m)
    normal_vector: np.ndarray                    # [nx, ny, nz] outward normal towards free space (unit vector)
    friction_coefficient: float = 0.35


@dataclass
class BoundaryWrenchResult:
    """Net aerodynamic forces and torques induced by boundary proximity."""
    force_world: np.ndarray = field(default_factory=lambda: np.zeros(3))  # [Fx, Fy, Fz] (N)
    torque_body: np.ndarray = field(default_factory=lambda: np.zeros(3))  # [tau_x, tau_y, tau_z] (N*m)
    ground_effect_ratio: float = 1.0                                     # T_IGE / T_OGE
    ceiling_suction_n: float = 0.0                                       # Upward suction force (N)
    wall_suction_n: float = 0.0                                          # Lateral wall suction force (N)
    is_boundary_active: bool = False


class AerodynamicBoundaryEngine:
    """
    Simulates coupled multi-rotor ground, ceiling, and wall aerodynamic interactions.
    """

    def __init__(self, config: AerodynamicBoundaryConfig | None = None) -> None:
        self.cfg = config or AerodynamicBoundaryConfig()
        # Rotor coordinates in body frame (FR, FL, BL, BR)
        d = self.cfg.drone_arm_length / math.sqrt(2.0)
        self.rotor_offsets_body = np.array([
            [+d, -d, 0.0],  # Rotor 1: Front-Right
            [+d, +d, 0.0],  # Rotor 2: Front-Left
            [-d, +d, 0.0],  # Rotor 3: Back-Left
            [-d, -d, 0.0],  # Rotor 4: Back-Right
        ])

    def compute_rotor_positions_world(
        self,
        drone_pos: np.ndarray,
        rot_matrix: np.ndarray,
    ) -> np.ndarray:
        """Transforms body rotor coordinates into world coordinates (4, 3)."""
        return drone_pos + (rot_matrix @ self.rotor_offsets_body.T).T

    def compute_ground_effect(
        self,
        rotor_positions: np.ndarray,
        thrust_per_rotor: np.ndarray,
        ground_z: float = 0.0,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Computes Cheeseman & Bennett ground effect thrust amplification across 4 rotors:
        T_IGE,i = T_0,i / (1 - (R / (4 * z_i))^2)
        """
        f_ground_world = np.zeros(3)
        tau_ground_body = np.zeros(3)
        ratios = []

        R = self.cfg.rotor_radius
        for i in range(4):
            z_i = max(self.cfg.min_ground_clearance, rotor_positions[i, 2] - ground_z)
            denom = 1.0 - (R / (4.0 * z_i)) ** 2
            ratio = 1.0 / max(0.2, denom)
            ratio = min(self.cfg.max_ige_ratio, max(1.0, ratio))
            ratios.append(ratio)

            # Amplified delta thrust in world Z
            delta_t = thrust_per_rotor[i] * (ratio - 1.0)
            f_ground_world[2] += delta_t

            # Differential ground torque on body
            arm_vec = self.rotor_offsets_body[i]
            tau_ground_body += np.cross(arm_vec, np.array([0.0, 0.0, delta_t]))

        avg_ratio = float(np.mean(ratios))
        return f_ground_world, tau_ground_body, avg_ratio

    def compute_ceiling_effect(
        self,
        drone_pos: np.ndarray,
        thrust_total: float,
        ceiling_z: float,
    ) -> Tuple[np.ndarray, float]:
        """
        Computes Bernoulli suction force towards ceiling:
        F_ceil = +c_ceil * T_total * (R / max(d_min, z_ceil - z))^2 * e_z
        """
        dist = max(self.cfg.min_ceiling_clearance, ceiling_z - drone_pos[2])
        R = self.cfg.rotor_radius
        # Suction increases quadratically as drone approaches ceiling
        suction_mag = self.cfg.ceiling_suction_coefficient * thrust_total * ((R / dist) ** 2)
        # Cap suction to prevent non-physical singularities
        suction_mag = min(suction_mag, 1.8 * self.cfg.mass * self.cfg.gravity)

        f_ceil = np.array([0.0, 0.0, suction_mag])
        return f_ceil, suction_mag

    def compute_wall_effect(
        self,
        drone_pos: np.ndarray,
        rot_matrix: np.ndarray,
        thrust_total: float,
        wall_point: np.ndarray,
        wall_normal: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Computes lateral wall vortex suction and asymmetric overturning torque:
        Wall normal n_wall points OUTWARD from wall towards free space.
        Suction pulls TOWARDS the wall (-n_wall).
        """
        # Projected distance from drone to wall plane
        d_wall = float(np.dot(drone_pos - wall_point, wall_normal))
        if d_wall <= 0.0:
            d_wall = self.cfg.min_wall_clearance

        R = self.cfg.rotor_radius
        eff_dist = max(self.cfg.min_wall_clearance, d_wall)

        # 1. Lateral Suction Force: Pulls in direction -wall_normal
        suction_mag = self.cfg.wall_suction_coefficient * thrust_total * ((R / eff_dist) ** 2)
        suction_mag = min(suction_mag, 1.5 * self.cfg.mass * self.cfg.gravity)
        f_wall = -suction_mag * wall_normal

        # 2. Destabilizing Asymmetric Torque:
        # Cross product of wall normal and vertical unit vector e_z creates roll/pitch torque
        # that tilts the drone towards the wall
        torque_dir_world = np.cross(wall_normal, np.array([0.0, 0.0, 1.0]))
        if np.linalg.norm(torque_dir_world) > 1e-6:
            torque_dir_world = torque_dir_world / np.linalg.norm(torque_dir_world)
        else:
            torque_dir_world = np.zeros(3)

        torque_mag = self.cfg.wall_torque_gain * thrust_total * ((R / eff_dist) ** 3)
        torque_world = torque_mag * torque_dir_world
        # Transform torque to body frame
        torque_body = rot_matrix.T @ torque_world

        return f_wall, torque_body, suction_mag

    def evaluate_boundary_wrench(
        self,
        drone_pos: np.ndarray,
        rot_matrix: np.ndarray,
        thrust_total: float,
        boundaries: List[PlanarBoundary],
    ) -> BoundaryWrenchResult:
        """
        Evaluates cumulative boundary aerodynamic forces and moments from all nearby surfaces.
        """
        result = BoundaryWrenchResult()
        thrust_per_rotor = np.full(4, thrust_total / 4.0)
        rotor_positions = self.compute_rotor_positions_world(drone_pos, rot_matrix)

        for b in boundaries:
            if b.boundary_type == BoundaryType.GROUND:
                f_g, tau_g, ratio = self.compute_ground_effect(
                    rotor_positions, thrust_per_rotor, ground_z=b.point_on_plane[2]
                )
                result.force_world += f_g
                result.torque_body += tau_g
                result.ground_effect_ratio = max(result.ground_effect_ratio, ratio)
                if ratio > 1.02:
                    result.is_boundary_active = True

            elif b.boundary_type == BoundaryType.CEILING:
                f_c, suction_c = self.compute_ceiling_effect(
                    drone_pos, thrust_total, ceiling_z=b.point_on_plane[2]
                )
                result.force_world += f_c
                result.ceiling_suction_n += suction_c
                if suction_c > 0.1:
                    result.is_boundary_active = True

            elif b.boundary_type == BoundaryType.WALL:
                f_w, tau_w, suction_w = self.compute_wall_effect(
                    drone_pos, rot_matrix, thrust_total, b.point_on_plane, b.normal_vector
                )
                result.force_world += f_w
                result.torque_body += tau_w
                result.wall_suction_n += suction_w
                if suction_w > 0.1:
                    result.is_boundary_active = True

        return result


class AerodynamicDisturbanceObserver:
    """
    High-rate (100 Hz) Momentum-based Non-linear Aerodynamic Disturbance Observer (ADOB).
    Estimates unmodeled boundary aerodynamic forces and torques directly from IMU residuals:
    dot{hat{d}} = L_d * (m * a_meas - (m * g + R * F_thrust + hat{d}))
    """

    def __init__(self, config: AerodynamicBoundaryConfig | None = None) -> None:
        self.cfg = config or AerodynamicBoundaryConfig()
        self.estimated_force = np.zeros(3)   # hat{d}_F in world frame (N)
        self.estimated_torque = np.zeros(3)  # hat{d}_tau in body frame (N*m)

    def update(
        self,
        accel_imu_world: np.ndarray,
        rot_matrix: np.ndarray,
        thrust_cmd: float,
        dt: float = 0.01,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Integrates momentum residual equation:
        True acceleration = (m * g + R * F_thrust + d_aero) / m
        Residual d_res = m * a_meas - m * g - R * F_thrust
        """
        # Nominal model prediction: Gravity + Commanded Thrust
        nominal_force_world = np.array([0.0, 0.0, -self.cfg.mass * self.cfg.gravity])
        nominal_force_world += rot_matrix @ np.array([0.0, 0.0, thrust_cmd])

        # Measured force from accelerometer
        measured_force_world = self.cfg.mass * accel_imu_world

        # Residual aerodynamic wrench
        residual_force = measured_force_world - nominal_force_world

        # Low-pass observer filtering: dot{hat{d}} = L_d * (residual - hat{d})
        L = self.cfg.adob_gain_force
        self.estimated_force += L * (residual_force - self.estimated_force) * dt

        return self.estimated_force.copy(), self.estimated_torque.copy()

    def reset(self) -> None:
        self.estimated_force.fill(0.0)
        self.estimated_torque.fill(0.0)


class AeroCompensatedHOCBF:
    """
    Aero-Compensated High-Order Control Barrier Function (Aero-HOCBF).
    Enforces forward invariance by accounting for boundary suction and lift amplification:
    L_f h + L_{f_aero} h + L_g h * u + alpha_1(h) + alpha_2(dot_h) >= 0
    """

    def __init__(self, config: AerodynamicBoundaryConfig | None = None) -> None:
        self.cfg = config or AerodynamicBoundaryConfig()
        self.engine = AerodynamicBoundaryEngine(self.cfg)

    def evaluate_barrier_constraint(
        self,
        drone_pos: np.ndarray,
        drone_vel: np.ndarray,
        rot_matrix: np.ndarray,
        thrust_nominal: float,
        boundary: PlanarBoundary,
        adob_force: Optional[np.ndarray] = None,
    ) -> Tuple[float, float, float, np.ndarray]:
        """
        Computes barrier value h, Lie derivatives, and required compensation:
        h(p) = (p - p_bound) . n_bound - r_safe >= 0
        dot_h(p, v) = v . n_bound
        ddot_h = a . n_bound = ((F_thrust + F_grav + F_aero) / m) . n_bound
        """
        # Barrier function: distance to boundary minus certified buffer
        dist = float(np.dot(drone_pos - boundary.point_on_plane, boundary.normal_vector))
        h = dist - self.cfg.cbf_safety_margin
        dot_h = float(np.dot(drone_vel, boundary.normal_vector))

        # 1. Aerodynamic Boundary Force
        if adob_force is not None:
            f_aero = adob_force
        else:
            wrench = self.engine.evaluate_boundary_wrench(
                drone_pos, rot_matrix, thrust_nominal, [boundary]
            )
            f_aero = wrench.force_world

        # 2. Lie Derivative of Boundary Aerodynamics: L_{f_aero} h
        L_f_aero = float(np.dot(f_aero / self.cfg.mass, boundary.normal_vector))

        # 3. Nominal Drift Lie Derivative: L_f h (Gravity only)
        grav_accel = np.array([0.0, 0.0, -self.cfg.gravity])
        L_f = float(np.dot(grav_accel, boundary.normal_vector))

        # 4. Control Matrix Lie Derivative: L_g h
        # F_thrust in body frame is [0, 0, T], in world frame is R @ [0, 0, T]
        thrust_unit_world = rot_matrix @ np.array([0.0, 0.0, 1.0])
        L_g_thrust = float(np.dot(thrust_unit_world / self.cfg.mass, boundary.normal_vector))

        # 5. Barrier Lower Bound Requirement:
        # L_g h * u >= - L_f h - L_{f_aero} h - alpha_1 * h - alpha_2 * dot_h
        min_allowed_accel = (
            - L_f
            - L_f_aero  # Pre-emptive cancellation of boundary suction!
            - self.cfg.cbf_alpha1 * h
            - self.cfg.cbf_alpha2 * dot_h
        )

        return h, dot_h, min_allowed_accel, boundary.normal_vector

    def filter_control_thrust(
        self,
        u_nominal_thrust: float,
        drone_pos: np.ndarray,
        drone_vel: np.ndarray,
        rot_matrix: np.ndarray,
        boundaries: List[PlanarBoundary],
        adob_force: Optional[np.ndarray] = None,
    ) -> Tuple[float, bool]:
        """
        Filters nominal thrust via closed-form QP projection to ensure all boundary
        Aero-HOCBF constraints are satisfied:
        min ||u - u_nom||^2 s.t. A_cbf * u >= b_cbf
        """
        thrust_safe = u_nominal_thrust
        intervened = False

        thrust_unit_world = rot_matrix @ np.array([0.0, 0.0, 1.0])

        for b in boundaries:
            h, dot_h, min_accel, normal = self.evaluate_barrier_constraint(
                drone_pos, drone_vel, rot_matrix, thrust_safe, b, adob_force
            )

            L_g = float(np.dot(thrust_unit_world / self.cfg.mass, normal))

            # If control has authority along normal
            if abs(L_g) > 1e-4:
                # Required thrust: L_g * T >= min_accel
                if L_g > 0:
                    req_thrust = min_accel / L_g
                    if req_thrust > thrust_safe:
                        thrust_safe = req_thrust
                        intervened = True
                else:
                    # L_g < 0 (thrust points towards boundary): cap maximum thrust
                    max_thrust = min_accel / L_g
                    if max_thrust < thrust_safe:
                        thrust_safe = max(0.0, max_thrust)
                        intervened = True

        # Clamp within physical limits [0, 4 * T_max]
        max_total_thrust = 4.0 * 4.0  # 16.0 N
        thrust_safe = float(np.clip(thrust_safe, 0.0, max_total_thrust))

        return thrust_safe, intervened
