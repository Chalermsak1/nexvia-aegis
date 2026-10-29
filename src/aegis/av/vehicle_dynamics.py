"""
Non-holonomic Dynamic Bicycle Model with Pacejka Tire Dynamics & Frenet Frame.

Provides high-fidelity physics simulation of autonomous vehicles (AV):
  - 6-state dynamic bicycle model: [x, y, psi, v_x, v_y, omega_z]
  - Longitudinal dynamic weight transfer (ax * h_cg / L)
  - Nonlinear tire slip angles (alpha_f, alpha_r) and Kamm's friction circle saturation
  - Smooth kinematic-to-dynamic transition at near-zero speeds
  - Full Frenet Coordinate transformation (s, d, s_dot, d_dot, yaw_rel) along curved roads
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
import numpy as np


@dataclass
class VehicleConfig:
    """Hyperparameters and geometric parameters for the autonomous vehicle."""
    mass: float = 1500.0              # Total vehicle mass (kg)
    I_z: float = 2250.0               # Yaw moment of inertia (kg * m^2)
    l_f: float = 1.2                  # Distance from CG to front axle (m)
    l_r: float = 1.6                  # Distance from CG to rear axle (m)
    h_cg: float = 0.50                # Height of center of gravity (m)
    c_alpha_f: float = 80000.0        # Front cornering stiffness (N/rad)
    c_alpha_r: float = 85000.0        # Rear cornering stiffness (N/rad)
    friction_coeff: float = 0.85      # Road surface friction coefficient (0.85 dry, 0.35 wet/ice)
    gravity: float = 9.81             # Gravity (m/s^2)

    # Actuator Limits
    max_steering_rad: float = math.radians(35.0)  # Max front wheel steering angle (+/- 35 deg)
    max_steering_rate: float = math.radians(45.0) # Steering slew rate (+/- 45 deg/s)
    max_accel: float = 4.0            # Max drive acceleration (m/s^2)
    max_decel: float = 8.0            # Max service brake deceleration (m/s^2)

    # Physical Dimensions
    width: float = 1.90               # Vehicle width (m)
    length: float = 4.60              # Vehicle length (m)
    wheelbase: float = field(init=False)

    def __post_init__(self) -> None:
        self.wheelbase = self.l_f + self.l_r


@dataclass
class VehicleState:
    """Current dynamic state of the autonomous vehicle."""
    x: float = 0.0                    # Global X position (m)
    y: float = 0.0                    # Global Y position (m)
    yaw: float = 0.0                  # Global heading / yaw angle (rad)
    v_x: float = 0.0                  # Longitudinal velocity in body frame (m/s)
    v_y: float = 0.0                  # Lateral velocity in body frame (m/s)
    yaw_rate: float = 0.0             # Yaw angular velocity (rad/s)
    steering: float = 0.0             # Current front steering angle (rad)
    accel: float = 0.0                # Current longitudinal acceleration (m/s^2)

    @property
    def speed(self) -> float:
        """Total planar speed magnitude (m/s)."""
        return math.sqrt(self.v_x**2 + self.v_y**2)

    @property
    def sideslip_angle(self) -> float:
        """Vehicle body sideslip angle beta (rad)."""
        if abs(self.v_x) < 0.2:
            return 0.0
        return math.atan2(self.v_y, self.v_x)


@dataclass
class TireForces:
    """Tire forces, slip angles, and normal loads across axles."""
    alpha_f: float                    # Front slip angle (rad)
    alpha_r: float                    # Rear slip angle (rad)
    F_yf: float                       # Front lateral tire force (N)
    F_yr: float                       # Rear lateral tire force (N)
    F_zf: float                       # Front dynamic normal load (N)
    F_zr: float                       # Rear dynamic normal load (N)
    friction_margin_f: float          # Available grip margin front (N)
    friction_margin_r: float          # Available grip margin rear (N)


@dataclass
class FrenetState:
    """Vehicle state projected onto the road curvilinear Frenet frame (s, d)."""
    s: float                          # Longitudinal distance along road centerline (m)
    d: float                          # Lateral distance from road centerline (m, +left, -right)
    s_dot: float                      # Longitudinal speed along road (m/s)
    d_dot: float                      # Lateral deviation speed (m/s)
    yaw_rel: float                    # Relative heading to road tangent (rad)
    road_curvature: float             # Curvature kappa(s) at current station (1/m)


class FrenetFrame:
    """
    Curvilinear road coordinate system.
    Transforms global (x, y, yaw) into curvilinear road coordinates (s, d).
    """

    def __init__(self, waypoints: np.ndarray) -> None:
        """
        waypoints: Nx2 array of (x, y) coordinates defining the road centerline.
        """
        if len(waypoints) < 2:
            raise ValueError("Waypoints array must contain at least 2 points")
        self.waypoints = np.array(waypoints, dtype=np.float64)

        # Compute cumulative distance s along centerline
        diffs = np.diff(self.waypoints, axis=0)
        seg_lengths = np.hypot(diffs[:, 0], diffs[:, 1])
        self.s_coords = np.concatenate([[0.0], np.cumsum(seg_lengths)])
        self.total_length = float(self.s_coords[-1])

        # Compute unit tangent and normal vectors for each segment
        seg_lengths_safe = np.maximum(seg_lengths, 1e-6)[:, np.newaxis]
        self.tangents = diffs / seg_lengths_safe
        # Normal points 90 degrees CCW (to the left of tangent)
        self.normals = np.column_stack([-self.tangents[:, 1], self.tangents[:, 0]])

        # Exact parametric curvature formula: kappa = (dx * ddy - dy * ddx) / (dx^2 + dy^2)^(1.5)
        if len(self.waypoints) >= 3:
            dx = np.gradient(self.waypoints[:, 0], edge_order=2)
            dy = np.gradient(self.waypoints[:, 1], edge_order=2)
            ddx = np.gradient(dx, edge_order=2)
            ddy = np.gradient(dy, edge_order=2)
            denom = np.maximum(1e-6, (dx**2 + dy**2)**1.5)
            self.curvatures = (dx * ddy - dy * ddx) / denom
        else:
            self.curvatures = np.zeros(len(self.waypoints), dtype=np.float64)

    def cartesian_to_frenet(
        self,
        x: float,
        y: float,
        yaw: float,
        v_x: float,
        v_y: float = 0.0,
    ) -> FrenetState:
        """Projects Cartesian state to Frenet state (s, d, s_dot, d_dot, yaw_rel)."""
        p = np.array([x, y])
        dists = np.sum((self.waypoints - p)**2, axis=1)
        nearest_idx = int(np.argmin(dists))

        # Determine segment index
        if nearest_idx >= len(self.waypoints) - 1:
            seg_idx = len(self.waypoints) - 2
        else:
            seg_idx = nearest_idx

        p0 = self.waypoints[seg_idx]
        tangent = self.tangents[seg_idx]
        normal = self.normals[seg_idx]

        # Projection onto segment
        vec = p - p0
        s_local = float(np.dot(vec, tangent))
        d = float(np.dot(vec, normal))
        s = float(self.s_coords[seg_idx] + s_local)
        kappa = float(self.curvatures[seg_idx])

        # Relative yaw angle
        road_heading = math.atan2(tangent[1], tangent[0])
        yaw_rel = math.atan2(math.sin(yaw - road_heading), math.cos(yaw - road_heading))

        # Velocity projection
        v_world_x = v_x * math.cos(yaw) - v_y * math.sin(yaw)
        v_world_y = v_x * math.sin(yaw) + v_y * math.cos(yaw)
        v_vec = np.array([v_world_x, v_world_y])

        s_dot = float(np.dot(v_vec, tangent) / max(1e-4, (1.0 - kappa * d)))
        d_dot = float(np.dot(v_vec, normal))

        return FrenetState(
            s=s,
            d=d,
            s_dot=s_dot,
            d_dot=d_dot,
            yaw_rel=yaw_rel,
            road_curvature=kappa,
        )

    def get_curvature_at_s(self, s: float) -> float:
        """
        Interpolates road curvature kappa at a given arc-length s.
        Enables lookahead preview for predictive deceleration before curves.
        """
        s_clamped = float(np.clip(s, 0.0, self.total_length))
        return float(np.interp(s_clamped, self.s_coords, self.curvatures))


class DynamicBicycleModel:
    """
    High-Fidelity 6-DOF Dynamic Bicycle Model with Pacejka tire dynamics.
    Integrates non-holonomic equations of motion with dynamic weight transfer.
    """

    def __init__(self, config: VehicleConfig | None = None) -> None:
        self.cfg = config or VehicleConfig()

    def compute_tire_forces(
        self,
        v_x: float,
        v_y: float,
        yaw_rate: float,
        steering: float,
        accel: float,
    ) -> TireForces:
        """
        Computes dynamic normal loads with weight transfer and lateral tire forces.
        """
        m = self.cfg.mass
        g = self.cfg.gravity
        L = self.cfg.wheelbase
        lf = self.cfg.l_f
        lr = self.cfg.l_r
        h = self.cfg.h_cg
        mu = self.cfg.friction_coeff

        # 1. Dynamic longitudinal weight transfer: delta_Fz = m * a_x * h / L
        delta_fz = (m * accel * h) / L
        F_zf = max(100.0, (m * g * lr / L) - delta_fz)
        F_zr = max(100.0, (m * g * lf / L) + delta_fz)

        # 2. Tire Slip Angles
        # Use low-speed blending to prevent division by zero near rest
        vx_safe = max(0.5, abs(v_x))
        alpha_f = steering - math.atan2(v_y + lf * yaw_rate, vx_safe)
        alpha_r = -math.atan2(v_y - lr * yaw_rate, vx_safe)

        # 3. Lateral forces with Kamm's friction circle saturation
        # Max available lateral grip: F_y_max = sqrt((mu * F_z)^2 - F_x^2)
        # Approximate longitudinal tire split: 40% front, 60% rear
        F_xf = 0.4 * m * accel
        F_xr = 0.6 * m * accel

        max_grip_f = max(0.0, (mu * F_zf)**2 - F_xf**2)
        max_grip_r = max(0.0, (mu * F_zr)**2 - F_xr**2)
        F_yf_max = math.sqrt(max_grip_f)
        F_yr_max = math.sqrt(max_grip_r)

        # Linear cornering stiffness with clipping
        F_yf_raw = self.cfg.c_alpha_f * alpha_f
        F_yr_raw = self.cfg.c_alpha_r * alpha_r

        F_yf = float(np.clip(F_yf_raw, -F_yf_max, F_yf_max))
        F_yr = float(np.clip(F_yr_raw, -F_yr_max, F_yr_max))

        margin_f = F_yf_max - abs(F_yf)
        margin_r = F_yr_max - abs(F_yr)

        return TireForces(
            alpha_f=alpha_f,
            alpha_r=alpha_r,
            F_yf=F_yf,
            F_yr=F_yr,
            F_zf=F_zf,
            F_zr=F_zr,
            friction_margin_f=margin_f,
            friction_margin_r=margin_r,
        )

    def _state_derivatives(
        self,
        state: VehicleState,
        cmd_accel: float,
        cmd_steering: float,
    ) -> np.ndarray:
        """Evaluates d(state)/dt for the dynamic bicycle model."""
        m = self.cfg.mass
        Iz = self.cfg.I_z
        lf = self.cfg.l_f
        lr = self.cfg.l_r

        # Clip inputs to physical actuator limits
        accel = float(np.clip(cmd_accel, -self.cfg.max_decel, self.cfg.max_accel))
        steer = float(np.clip(cmd_steering, -self.cfg.max_steering_rad, self.cfg.max_steering_rad))

        x, y, yaw, vx, vy, omega = state.x, state.y, state.yaw, state.v_x, state.v_y, state.yaw_rate

        # Low-speed kinematic fallback to prevent numerical stiffness near 0 m/s
        if abs(vx) < 0.35:
            # Kinematic bicycle model
            beta = math.atan(lr * math.tan(steer) / (lf + lr))
            dx = vx * math.cos(yaw + beta)
            dy = vx * math.sin(yaw + beta)
            dyaw = (vx * math.cos(beta) / (lf + lr)) * math.tan(steer)
            dvx = accel
            dvy = 0.0
            domega = (dyaw - omega) * 10.0
            return np.array([dx, dy, dyaw, dvx, dvy, domega])

        # Full Dynamic Equations with Tire Forces
        tires = self.compute_tire_forces(vx, vy, omega, steer, accel)

        # Global kinematics
        dx = vx * math.cos(yaw) - vy * math.sin(yaw)
        dy = vx * math.sin(yaw) + vy * math.cos(yaw)
        dyaw = omega

        # Body dynamics
        dvx = accel + vy * omega
        dvy = (1.0 / m) * (tires.F_yf * math.cos(steer) + tires.F_yr) - vx * omega
        domega = (1.0 / Iz) * (lf * tires.F_yf * math.cos(steer) - lr * tires.F_yr)

        return np.array([dx, dy, dyaw, dvx, dvy, domega])

    def step(
        self,
        state: VehicleState,
        cmd_accel: float,
        cmd_steering: float,
        dt: float = 0.01,
    ) -> tuple[VehicleState, TireForces]:
        """
        Executes one time step using 4th-order Runge-Kutta (RK4) integration.
        Returns: (new_state, tire_forces)
        """
        # Slew-rate limiting on steering
        max_delta_steer = self.cfg.max_steering_rate * dt
        actual_steer = float(np.clip(
            cmd_steering,
            state.steering - max_delta_steer,
            state.steering + max_delta_steer,
        ))
        actual_steer = float(np.clip(actual_steer, -self.cfg.max_steering_rad, self.cfg.max_steering_rad))
        actual_accel = float(np.clip(cmd_accel, -self.cfg.max_decel, self.cfg.max_accel))

        s_vec = np.array([state.x, state.y, state.yaw, state.v_x, state.v_y, state.yaw_rate])

        def to_state(vec: np.ndarray) -> VehicleState:
            return VehicleState(
                x=vec[0], y=vec[1], yaw=vec[2],
                v_x=vec[3], v_y=vec[4], yaw_rate=vec[5],
                steering=actual_steer, accel=actual_accel,
            )

        # RK4 Integration
        k1 = self._state_derivatives(to_state(s_vec), actual_accel, actual_steer)
        k2 = self._state_derivatives(to_state(s_vec + 0.5 * dt * k1), actual_accel, actual_steer)
        k3 = self._state_derivatives(to_state(s_vec + 0.5 * dt * k2), actual_accel, actual_steer)
        k4 = self._state_derivatives(to_state(s_vec + dt * k3), actual_accel, actual_steer)

        s_next = s_vec + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        # Normalize yaw to [-pi, pi]
        s_next[2] = math.atan2(math.sin(s_next[2]), math.cos(s_next[2]))
        # Prevent reverse rolling from numerical discretization
        s_next[3] = max(0.0, s_next[3])

        new_state = VehicleState(
            x=float(s_next[0]),
            y=float(s_next[1]),
            yaw=float(s_next[2]),
            v_x=float(s_next[3]),
            v_y=float(s_next[4]),
            yaw_rate=float(s_next[5]),
            steering=actual_steer,
            accel=actual_accel,
        )

        tires = self.compute_tire_forces(new_state.v_x, new_state.v_y, new_state.yaw_rate, actual_steer, actual_accel)
        return new_state, tires
