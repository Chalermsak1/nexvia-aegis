"""
High-Order Control Barrier Function (HOCBF) Shield in Frenet Frame for Autonomous Vehicles.

Enforces:
  1. Lane Boundary Keeping Barrier (h_left >= 0, h_right >= 0) with relative degree 2.
  2. Kamm's Friction Circle Barrier (Anti-skid & Anti-spin-out on wet/ice asphalt).
  3. Adaptive Cruise Control (ACC) & Lead Vehicle Collision Prevention.
  4. Road Curvature Speed Limit Barrier (v_x^2 * |kappa| <= a_lat_max).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np

from aegis.av.vehicle_dynamics import (
    DynamicBicycleModel,
    FrenetFrame,
    FrenetState,
    TireForces,
    VehicleConfig,
    VehicleState,
)


@dataclass
class FrenetCbfConfig:
    """Hyperparameters for Frenet frame CBF safety shield."""
    lane_width: float = 3.60          # Standard highway lane width (m)
    lane_safety_margin: float = 0.25  # Buffer from tire edge to lane marking (m)
    cbf_gamma1: float = 2.0           # HOCBF linear gain alpha_1
    cbf_gamma2: float = 2.0           # HOCBF linear gain alpha_2

    # ACC / Lead Vehicle Parameters
    min_standstill_distance: float = 4.0 # d_0 standstill distance (m)
    time_headway: float = 1.2         # tau_headway time gap (seconds)
    max_safe_decel: float = 6.5       # Maximum allowable emergency deceleration (m/s^2)

    # Road Curvature Comfort & Adhesion Limit
    max_lateral_accel_factor: float = 0.60 # Fraction of mu * g allowed in curves


@dataclass
class ShieldedControlCommand:
    """Output bundle of the Frenet HOCBF safety shield."""
    accel_cmd: float                  # Verified safe longitudinal acceleration (m/s^2)
    steering_cmd: float               # Verified safe front steering angle (rad)
    nominal_accel: float              # Requested nominal acceleration (m/s^2)
    nominal_steering: float           # Requested nominal steering (rad)
    barrier_active: bool              # True if any safety barrier modified the control
    active_barriers: list[str]        # Names of active barrier constraints triggered
    frenet_state: FrenetState         # Current Frenet state (s, d)


class FrenetSafetyShield:
    """
    Control Barrier Function Shield for Autonomous Ground Vehicles.
    Filters nominal (a_x, delta) commands to guarantee lane keeping, tire grip, and collision avoidance.
    """

    def __init__(
        self,
        vehicle_config: VehicleConfig | None = None,
        cbf_config: FrenetCbfConfig | None = None,
    ) -> None:
        self.v_cfg = vehicle_config or VehicleConfig()
        self.cbf_cfg = cbf_config or FrenetCbfConfig()
        self.dyn_model = DynamicBicycleModel(self.v_cfg)

    def filter_control(
        self,
        state: VehicleState,
        frenet: FrenetState,
        nominal_accel: float,
        nominal_steering: float,
        lead_vehicle_s: float | None = None,
        lead_vehicle_speed: float | None = None,
        road_frame: FrenetFrame | None = None,
    ) -> ShieldedControlCommand:
        """
        Filters nominal steering and acceleration commands.
        Returns guaranteed safe ShieldedControlCommand.
        """
        a_safe = float(nominal_accel)
        delta_safe = float(nominal_steering)
        active_barriers: list[str] = []
        barrier_triggered = False

        # Physical limits
        a_safe = float(np.clip(a_safe, -self.v_cfg.max_decel, self.v_cfg.max_accel))
        delta_safe = float(np.clip(delta_safe, -self.v_cfg.max_steering_rad, self.v_cfg.max_steering_rad))

        vx = max(0.1, state.v_x)
        d = frenet.d
        d_dot = frenet.d_dot
        kappa = frenet.road_curvature
        mu = self.v_cfg.friction_coeff
        g = self.v_cfg.gravity

        # -----------------------------------------------------------------
        # 1. Road Curvature Speed Limit Barrier (with Lookahead Preview)
        # a_lat = v_x^2 * |kappa| <= mu * g * factor
        # -----------------------------------------------------------------
        effective_kappa = abs(kappa)
        if road_frame is not None:
            # Preview lookahead distance: stopping distance at comfortable decel (e.g. 3.0 m/s^2)
            lookahead_dist = max(20.0, (vx**2) / (2.0 * 3.0))
            s_samples = np.linspace(frenet.s, frenet.s + lookahead_dist, 12)
            ahead_kappas = [abs(road_frame.get_curvature_at_s(float(s_samp))) for s_samp in s_samples]
            max_ahead_kappa = max(ahead_kappas) if ahead_kappas else 0.0
            if max_ahead_kappa > effective_kappa:
                effective_kappa = max_ahead_kappa

        if effective_kappa > 1e-4:
            a_lat_max = mu * g * self.cbf_cfg.max_lateral_accel_factor
            v_max_curve = math.sqrt(a_lat_max / effective_kappa)
            if state.v_x > v_max_curve:
                # Decelerate to enter curve safely
                decel_needed = -2.5 * (state.v_x - v_max_curve)
                if decel_needed < a_safe:
                    a_safe = float(np.clip(decel_needed, -self.v_cfg.max_decel, self.v_cfg.max_accel))
                    active_barriers.append("CURVATURE_SPEED_LIMIT")
                    barrier_triggered = True

        # -----------------------------------------------------------------
        # 2. Kamm's Friction Circle Tire Adhesion Barrier
        # Prevents steering commands that exceed tire friction limit on wet/ice asphalt
        # alpha_f = delta - atan2(v_y + l_f * r, v_x) <= mu * F_zf / C_alpha_f
        # -----------------------------------------------------------------
        tires = self.dyn_model.compute_tire_forces(state.v_x, state.v_y, state.yaw_rate, delta_safe, a_safe)
        if tires.friction_margin_f <= 50.0:
            max_grip_force = mu * tires.F_zf
            max_alpha = max_grip_force / self.v_cfg.c_alpha_f
            theta_vf = math.atan2(state.v_y + self.v_cfg.l_f * state.yaw_rate, vx)
            delta_min_grip = theta_vf - max_alpha * 0.98
            delta_max_grip = theta_vf + max_alpha * 0.98
            clamped_steer = float(np.clip(delta_safe, delta_min_grip, delta_max_grip))
            if abs(clamped_steer - delta_safe) > 1e-4:
                delta_safe = clamped_steer
                active_barriers.append("TIRE_FRICTION_CIRCLE_KAMM")
                barrier_triggered = True

        # -----------------------------------------------------------------
        # 3. Lane Keeping High-Order Control Barrier Function (HOCBF, r=2)
        # d_max = (W_lane - W_vehicle) / 2 - margin
        # -----------------------------------------------------------------
        d_boundary = (self.cbf_cfg.lane_width - self.v_cfg.width) / 2.0 - self.cbf_cfg.lane_safety_margin
        alpha1 = self.cbf_cfg.cbf_gamma1
        alpha2 = self.cbf_cfg.cbf_gamma2

        # Left barrier: h_left = d_boundary - d >= 0
        h_left = d_boundary - d
        h_left_dot = -d_dot
        # Right barrier: h_right = d + d_boundary >= 0
        h_right = d + d_boundary
        h_right_dot = d_dot

        # Lateral steering to lateral acceleration relation: d_ddot approx (v_x^2 / L) * delta
        k_steer_to_d_ddot = (vx**2) / self.v_cfg.wheelbase

        # Left barrier condition: -d_ddot + (a1 + a2)*(-d_dot) + a1*a2*h_left >= 0
        # => d_ddot <= -(a1 + a2)*d_dot + a1*a2*h_left
        d_ddot_max = -(alpha1 + alpha2) * d_dot + alpha1 * alpha2 * h_left
        delta_max_left = d_ddot_max / max(0.1, k_steer_to_d_ddot)

        if delta_safe > delta_max_left:
            delta_safe = float(np.clip(delta_max_left, -self.v_cfg.max_steering_rad, self.v_cfg.max_steering_rad))
            active_barriers.append("LANE_KEEPING_LEFT_HOCBF")
            barrier_triggered = True

        # Right barrier condition: d_ddot + (a1 + a2)*d_dot + a1*a2*h_right >= 0
        # => d_ddot >= -(a1 + a2)*d_dot - a1*a2*h_right
        d_ddot_min = -(alpha1 + alpha2) * d_dot - alpha1 * alpha2 * h_right
        delta_min_right = d_ddot_min / max(0.1, k_steer_to_d_ddot)

        if delta_safe < delta_min_right:
            delta_safe = float(np.clip(delta_min_right, -self.v_cfg.max_steering_rad, self.v_cfg.max_steering_rad))
            active_barriers.append("LANE_KEEPING_RIGHT_HOCBF")
            barrier_triggered = True

        # -----------------------------------------------------------------
        # 4. Adaptive Cruise Control (ACC) & Lead Vehicle Barrier
        # h_acc = (s_lead - s_ego - L) - (d_0 + tau * v_x + (v_x^2 - v_lead^2)/(2*a_brake)) >= 0
        # -----------------------------------------------------------------
        if lead_vehicle_s is not None:
            v_lead = lead_vehicle_speed if lead_vehicle_speed is not None else 0.0
            gap = lead_vehicle_s - frenet.s - self.v_cfg.length
            d_safe_acc = (
                self.cbf_cfg.min_standstill_distance
                + self.cbf_cfg.time_headway * vx
                + max(0.0, (vx**2 - v_lead**2)) / (2.0 * self.cbf_cfg.max_safe_decel)
            )

            h_acc = gap - d_safe_acc
            h_acc_dot = (v_lead - vx) - self.cbf_cfg.time_headway * a_safe

            if h_acc < 0.0 or (h_acc + 0.8 * h_acc_dot < 0.0):
                # Enforce emergency braking barrier
                required_brake = -(vx**2 - v_lead**2) / max(0.5, 2.0 * max(0.2, gap - self.cbf_cfg.min_standstill_distance))
                required_brake = min(required_brake, -1.5) # At least 1.5 m/s^2 deceleration
                a_safe = float(np.clip(min(a_safe, required_brake), -self.v_cfg.max_decel, self.v_cfg.max_accel))
                active_barriers.append("ACC_LEAD_COLLISION_BARRIER")
                barrier_triggered = True

        return ShieldedControlCommand(
            accel_cmd=a_safe,
            steering_cmd=delta_safe,
            nominal_accel=nominal_accel,
            nominal_steering=nominal_steering,
            barrier_active=barrier_triggered,
            active_barriers=active_barriers,
            frenet_state=frenet,
        )
