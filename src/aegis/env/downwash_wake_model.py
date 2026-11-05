"""
NEXVIA AEGIS — Multi-Rotor Downwash Wake & Inter-Drone Aerodynamic Coupling Engine.

Implements Rankine-Froude momentum slipstream theory and vortex cylinder dynamics
for multi-quadrotor flight in close proximity:
1. Downwash Slipstream Velocity Field:
   When quadrotor j (leader/upper) produces thrust T_j, it generates a downward
   slipstream velocity field v_wake(Delta p) that impinges on trailing quadrotor i (follower/lower).
   - Core downwash velocity:
     v_core(|Delta z|) = v_0 * [1 + |Delta z| / sqrt(R^2 + Delta z^2)] * exp(-gamma * |Delta z| / R)
     where v_0 = sqrt(T_j / (2 * rho * A_rotors)) is hover induced velocity (~6.8 m/s).
   - Radial turbulent wake expansion:
     r_wake(|Delta z|) = R_drone + k_wake * |Delta z|
   - Spatial induced velocity distribution:
     v_z,downwash(Delta p) = -v_core(|Delta z|) * exp(-||Delta p_xy||^2 / (2 * r_wake^2))
2. Induced Aerodynamic Downward Force & Asymmetric Tipping Moment:
   - Downward drag force: F_wake,z = -0.5 * rho * C_d * A_proj * |v_z| * v_z
   - Asymmetric shear torque: tau_wake = c_shear * (grad_xy v_z x e_z) that tilts the follower.
3. Wake-Aware Anisotropic High-Order Control Barrier Function (Wake-CBF):
   - Expands the safety barrier into a vertical prolate spheroid / cone to prevent
     drones from flying directly into another drone's destructive downwash column:
     h_wake(p_i, p_j) = (x_i - x_j)^2 + (y_i - y_j)^2 + (max(0, z_j - z_i) / kappa_wake)^2 - r_safe^2 >= 0
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import List, Tuple
import numpy as np


@dataclass(frozen=True)
class DownwashWakeConfig:
    """Aerodynamic parameters for multi-rotor downwash interaction."""
    rotor_radius: float = 0.09                   # Propeller radius R (m)
    num_rotors: int = 4                          # 4 rotors per drone
    drone_arm_length: float = 0.22               # Motor-to-center distance (m)
    air_density: float = 1.225                   # rho (kg/m^3)
    drag_coefficient_z: float = 1.15             # Vertical flat-plate body drag coefficient C_d
    projected_area_z: float = 0.038              # Top-view projected body area (m^2)
    wake_expansion_rate: float = 0.22            # Turbulent slipstream spread k_wake = dr/dz
    wake_decay_rate: float = 0.08                # Longitudinal dissipation factor gamma
    shear_torque_coefficient: float = 0.045      # Asymmetric tipping torque gain (N*m / (m/s))
    wake_cbf_kappa: float = 2.5                  # Vertical barrier expansion ratio kappa_wake
    min_safe_clearance_xy: float = 0.44          # 2 * r_quad (m)
    max_wake_influence_dist: float = 2.2         # Cutoff distance for wake computation (m)


@dataclass
class DroneWakeState:
    """Aerodynamic wake impact experienced by an individual drone."""
    agent_id: int
    induced_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))  # m/s in world frame
    wake_force: np.ndarray = field(default_factory=lambda: np.zeros(3))        # N in world frame
    wake_torque: np.ndarray = field(default_factory=lambda: np.zeros(3))       # N*m body torque
    in_wake_cone: bool = False
    wake_severity: float = 0.0  # Normalized [0, 1]


class DownwashWakeModel:
    """
    Computes reciprocal aerodynamic wake fields across N simultaneous 6-DOF quadrotors.
    """

    def __init__(self, config: DownwashWakeConfig | None = None) -> None:
        self.cfg = config or DownwashWakeConfig()
        # Total effective actuator disc area
        self.total_disc_area = self.cfg.num_rotors * math.pi * (self.cfg.rotor_radius ** 2)

    def compute_induced_hover_velocity(self, thrust_total_n: float) -> float:
        """Computes Rankine-Froude hover induced velocity v_0 = sqrt(T / (2 * rho * A))."""
        t_pos = max(0.1, float(thrust_total_n))
        denom = 2.0 * self.cfg.air_density * self.total_disc_area
        return math.sqrt(t_pos / max(1e-6, denom))

    def evaluate_pairwise_wake(
        self,
        pos_lead: np.ndarray,
        thrust_lead_n: float,
        pos_follow: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        """
        Calculates downwash velocity, force, and torque exerted by leading drone on follower drone.

        Returns:
            (v_wake, F_wake, tau_wake, severity)
        """
        # Relative vector from leader to follower
        delta_p = pos_follow - pos_lead
        dx, dy, dz = delta_p[0], delta_p[1], delta_p[2]

        # Wake only blows DOWNWARD from the leader (dz < 0 means follower is beneath leader)
        if dz >= 0.0:
            return np.zeros(3), np.zeros(3), np.zeros(3), 0.0

        depth = abs(dz)
        if depth > self.cfg.max_wake_influence_dist:
            return np.zeros(3), np.zeros(3), np.zeros(3), 0.0

        r_perp = math.sqrt(dx * dx + dy * dy)
        v0 = self.compute_induced_hover_velocity(thrust_lead_n)

        # 1. Longitudinal Wake Contraction & Expansion Profile
        r_lead_drone = self.cfg.drone_arm_length
        # Core slipstream velocity increases to 2*v0 before turbulent dissipation
        velocity_contraction = 1.0 + (depth / math.sqrt(r_lead_drone * r_lead_drone + depth * depth))
        dissipation = math.exp(-self.cfg.wake_decay_rate * depth / max(1e-4, r_lead_drone))
        v_core = v0 * velocity_contraction * dissipation

        # 2. Radial Turbulent Expansion: r_wake(z)
        r_wake = r_lead_drone + self.cfg.wake_expansion_rate * depth

        # 3. Radial Gaussian Profile
        gauss_factor = math.exp(-(r_perp * r_perp) / max(1e-6, 2.0 * r_wake * r_wake))
        v_z_downwash = -v_core * gauss_factor

        v_wake = np.array([0.0, 0.0, v_z_downwash], dtype=np.float64)

        # 4. Induced Aerodynamic Downward Force (quadratic drag against relative airflow)
        # F_z = 0.5 * rho * C_d * A_proj * (v_rel)^2
        f_z = -0.5 * self.cfg.air_density * self.cfg.drag_coefficient_z * self.cfg.projected_area_z * (v_z_downwash ** 2)
        f_wake = np.array([0.0, 0.0, f_z], dtype=np.float64)

        # 5. Asymmetric Tipping Moment (Shear Torque)
        # When follower sits on the shear edge of the wake (gradient d v_z / d r_perp),
        # one side of its airframe loses lift while the other side retains it.
        # d(v_z)/d(r_perp) = v_core * (r_perp / r_wake^2) * gauss_factor
        grad_shear = (v_core * r_perp / max(1e-6, r_wake * r_wake)) * gauss_factor
        tau_wake = np.zeros(3)
        if r_perp > 1e-4:
            # Unit orthogonal direction in horizontal plane: cross(e_z, delta_p_xy)
            unit_x = dx / r_perp
            unit_y = dy / r_perp
            # Roll and pitch tipping moments: push follower outward away from center of jet
            tau_mag = self.cfg.shear_torque_coefficient * grad_shear
            tau_wake[0] = tau_mag * (-unit_y)
            tau_wake[1] = tau_mag * (unit_x)

        # Severity metric: ratio of induced velocity to hover velocity
        severity = float(np.clip(abs(v_z_downwash) / max(1e-4, 2.0 * v0), 0.0, 1.0))
        return v_wake, f_wake, tau_wake, severity

    def compute_swarm_wake_disturbances(
        self,
        positions: List[np.ndarray],
        thrusts_n: List[float],
    ) -> List[DroneWakeState]:
        """
        Computes superposition of aerodynamic downwash wake disturbances across all drones.
        """
        n = len(positions)
        results: List[DroneWakeState] = []

        for i in range(n):
            tot_v_wake = np.zeros(3, dtype=np.float64)
            tot_f_wake = np.zeros(3, dtype=np.float64)
            tot_tau_wake = np.zeros(3, dtype=np.float64)
            max_severity = 0.0
            in_wake = False

            for j in range(n):
                if i == j:
                    continue
                v_w, f_w, tau_w, sev = self.evaluate_pairwise_wake(
                    pos_lead=positions[j],
                    thrust_lead_n=thrusts_n[j],
                    pos_follow=positions[i],
                )
                if sev > 0.05:
                    in_wake = True
                    max_severity = max(max_severity, sev)
                tot_v_wake += v_w
                tot_f_wake += f_w
                tot_tau_wake += tau_w

            results.append(DroneWakeState(
                agent_id=i,
                induced_velocity=tot_v_wake,
                wake_force=tot_f_wake,
                wake_torque=tot_tau_wake,
                in_wake_cone=in_wake,
                wake_severity=max_severity,
            ))

        return results


class WakeAwareHOCBF:
    """
    Wake-Aware High-Order Control Barrier Function (Wake-HOCBF).

    Enforces anisotropic safety envelope:
        h_wake(p_i, p_j) = ||p_i,xy - p_j,xy||^2 + [max(0, z_j - z_i) / kappa]^2 - r_safe^2 >= 0
    Prevents follower drone i from flying directly underneath leader drone j's downwash column.
    """

    def __init__(
        self,
        r_safe: float = 0.44,
        kappa_wake: float = 2.5,
        gamma1: float = 2.0,
        gamma2: float = 3.0,
        mass_kg: float = 1.2,
        gravity: float = 9.81,
    ) -> None:
        self.r_safe = r_safe
        self.kappa_wake = kappa_wake
        self.gamma1 = gamma1
        self.gamma2 = gamma2
        self.mass = mass_kg
        self.gravity = gravity

    def compute_barrier_constraint(
        self,
        pos_i: np.ndarray,
        vel_i: np.ndarray,
        pos_j: np.ndarray,
        vel_j: np.ndarray,
        mu_responsibility: float = 1.0,
    ) -> Tuple[np.ndarray, float, float]:
        """
        Computes linearized CBF constraint on acceleration/force F_i:
            a_vec^T F_i <= mu * b_val

        Returns:
            (a_vec, b_val, h_val)
        """
        p_ij = pos_i - pos_j
        v_ij = vel_i - vel_j

        dx, dy, dz = p_ij[0], p_ij[1], p_ij[2]
        vx, vy, vz = v_ij[0], v_ij[1], v_ij[2]

        r_xy_sq = dx * dx + dy * dy
        # Downwash penalty if agent i is below agent j (dz = z_i - z_j < 0)
        z_under = max(0.0, -dz)
        k_sq = self.kappa_wake * self.kappa_wake

        # Barrier function:
        # h(p) = r_xy^2 + (z_under / kappa)^2 - r_safe^2
        h_val = float(r_xy_sq + (z_under * z_under) / k_sq - self.r_safe * self.r_safe)

        # Time derivative h_dot:
        # dh/dt = 2*dx*vx + 2*dy*vy - 2*(z_under / k_sq)*vz (if dz < 0)
        grad_x = 2.0 * dx
        grad_y = 2.0 * dy
        grad_z = -2.0 * z_under / k_sq if dz < 0.0 else 0.0
        grad_p = np.array([grad_x, grad_y, grad_z], dtype=np.float64)

        h_dot = float(np.dot(grad_p, v_ij))

        # Second-order CBF formulation:
        # L_f^2 h + L_g L_f h u + (gamma1 + gamma2) h_dot + gamma1*gamma2 h >= 0
        # a_vec^T F_i <= b_val
        a_vec = -grad_p / self.mass

        alpha_sum = self.gamma1 + self.gamma2
        alpha_prod = self.gamma1 * self.gamma2

        # Quadratic velocity term from Hessian
        v_term = 2.0 * (vx * vx + vy * vy) + (2.0 / k_sq if dz < 0.0 else 0.0) * (vz * vz)
        grav_term = -grad_z * self.gravity

        b_val = float(v_term + grav_term + alpha_sum * h_dot + alpha_prod * h_val)

        return a_vec, mu_responsibility * b_val, h_val
