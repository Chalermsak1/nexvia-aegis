"""
NEXVIA AEGIS — Deep Aerodynamics & Electromechanical Physics Engine.

Implements high-fidelity aerodynamic and power system dynamics for 6-DOF quadrotors:
1. Ground Effect (IGE - In-Ground Effect) via Cheeseman & Bennett Model:
   - Lift amplification near ground plane or boundary surfaces:
     T_IGE = T_OGE / (1 - (R_rotor / (4 * z_eff))^2)
   - Bounded by aerodynamic boundary layer limits to prevent unphysical numerical blowup.
   - Calculates effective distance for each of the 4 rotor discs independently.

2. Rotor Gyroscopic Precession Dynamics (tau_gyro):
   - Induced cross-axis reaction moment when quadrotor body rotates at angular velocity Omega_B:
     tau_gyro = - Omega_B x H_rotors
     where H_rotors = sum_{i=0}^3 (s_i * J_r * omega_i) * e_3
   - Couples body pitch rate to roll torque, and roll rate to pitch torque during agile maneuvers.

3. Battery Voltage Sag & Discharge Electromechanics:
   - 4S LiPo battery model with internal series resistance R_int (Ohms).
   - Dynamic load current I_load computed from rotor thrusts and avionics power.
   - Instantaneous terminal voltage sag: V_terminal = V_ocv(SoC) - I_load * R_int.
   - Voltage-dependent maximum thrust derating: T_max(t) = T_max,0 * (V_terminal / V_nominal)^2.

4. Dynamic Atmospheric Wind & Turbulence (Ornstein-Uhlenbeck):
   - Continuous stochastic wind drift with mean-reverting velocity dynamics:
     dw = -theta * (w - w_mean) * dt + sigma * sqrt(dt) * xi, xi ~ N(0, I_3).

5. Discrete 1-Cosine Wind Gusts (MIL-F-8785C Standard):
   - Discrete transient wind gust profile:
     w_gust(t) = 0.5 * A_gust * (1 - cos(2 * pi * tau)) for 0 <= tau <= 1.

6. Quadratic Aerodynamic Drag & Ground Vortex Shear Torque:
   - Quadratic relative-velocity body drag: F_drag = -0.5 * rho * (C_d * A) * ||v_rel|| * v_rel.
   - Ground vortex destabilizing shear torque near ground plane (z < 4 * R_rotor):
     tau_shear = c_shear * exp(-z / (2 * R_rotor)) * (v_rel,horiz x e_z).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Tuple

import numpy as np


@dataclass(frozen=True)
class DeepAerodynamicsConfig:
    """Configuration parameters for deep aerodynamic, environmental disturbance, and battery physics."""
    # Rotor Aerodynamics
    rotor_radius: float = 0.09                   # meters (propeller radius R)
    thrust_coefficient: float = 8.87e-6          # N / (rad/s)^2 (T = c_T * omega^2)
    rotor_inertia: float = 6.5e-5                # kg*m^2 (rotor propeller + motor bell J_r)
    max_ige_ratio: float = 1.50                  # maximum ground-effect thrust boost (50%)
    ige_enabled: bool = True                     # enable Cheeseman-Bennett IGE

    # Gyroscopic Precession
    gyroscopic_enabled: bool = True              # enable gyroscopic precession cross-moments

    # Battery & Electromechanics
    battery_enabled: bool = True                 # enable voltage sag & discharge
    nominal_voltage: float = 14.8                # Volts (4S LiPo nominal, 3.7V/cell)
    full_voltage: float = 16.8                   # Volts (4S LiPo full, 4.2V/cell)
    cutoff_voltage: float = 12.8                 # Volts (4S LiPo empty, 3.2V/cell)
    battery_capacity_ah: float = 2.2             # Amp-hours (2200 mAh pack)
    internal_resistance: float = 0.035           # Ohms (35 mOhm internal resistance R_int)
    avionics_current: float = 0.65               # Amps (flight controller, IMU, companion computer)
    motor_electrical_efficiency: float = 0.82    # electromechanical conversion efficiency eta_m
    power_coefficient: float = 4.0               # W / N^1.5 (P_mech = c_P * T^1.5 from momentum theory)

    # Stochastic Atmospheric Wind & Turbulence (Ornstein-Uhlenbeck Process)
    wind_enabled: bool = False                   # enable stochastic atmospheric wind
    wind_mean: tuple[float, float, float] = (0.0, 0.0, 0.0) # steady mean wind vector (m/s) in world frame
    wind_theta: float = 0.50                     # OU mean-reversion rate (1/s)
    wind_sigma: float = 0.25                     # OU turbulence intensity / volatility (m/s^1.5)

    # Discrete Wind Gust (MIL-F-8785C 1-cosine profile)
    gust_enabled: bool = False                   # enable discrete 1-cosine gust
    gust_amplitude: tuple[float, float, float] = (3.5, 2.0, -0.8) # peak gust amplitude vector (m/s)
    gust_start_time: float = 1.5                 # time when gust begins (s)
    gust_duration: float = 2.5                   # duration of 1-cosine gust (s)

    # Quadratic Aerodynamic Drag & Ground Vortex Shear
    drag_enabled: bool = True                    # enable quadratic body drag force
    air_density: float = 1.225                   # kg/m^3 (sea-level standard air density rho)
    drag_area_product: float = 0.045             # m^2 (effective drag area C_d * A_ref)
    rotational_drag_damping: float = 0.04        # N*m*s/rad (body angular rate damping D_rot)
    ground_shear_coefficient: float = 0.12       # N*m / (m/s) (ground vortex destabilizing shear moment)


@dataclass
class DeepAerodynamicsState:
    """Real-time physical state of aerodynamics, disturbances, and battery."""
    soc: float = 1.0                             # State of Charge [0.0, 1.0]
    v_ocv: float = 16.8                          # Open-circuit voltage (V)
    v_terminal: float = 16.8                     # Terminal voltage under load (V)
    load_current: float = 0.0                    # Total drawn current (A)
    thrust_derate_factor: float = 1.0            # (V_terminal / V_nominal)^2
    effective_max_thrust: float = 8.5            # Derated max thrust per motor (N)
    rotor_omega: np.ndarray = field(default_factory=lambda: np.zeros(4))  # rad/s per rotor
    ige_ratios: np.ndarray = field(default_factory=lambda: np.ones(4))    # IGE multipliers
    tau_gyro_body: np.ndarray = field(default_factory=lambda: np.zeros(3)) # N*m in body frame
    energy_consumed_wh: float = 0.0              # Watt-hours consumed

    # Environmental Disturbances & Aerodynamic State
    sim_time: float = 0.0                        # accumulated simulation time (s)
    wind_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))       # stochastic OU wind (m/s)
    gust_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))       # 1-cosine gust (m/s)
    total_wind: np.ndarray = field(default_factory=lambda: np.zeros(3))          # net wind w_total (m/s)
    relative_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))   # v_rel = v_drone - w_total
    aerodynamic_force: np.ndarray = field(default_factory=lambda: np.zeros(3))   # F_drag in world frame (N)
    ground_shear_torque: np.ndarray = field(default_factory=lambda: np.zeros(3)) # tau_shear in body frame (N*m)


class DeepAerodynamicsEngine:
    """
    High-fidelity aerodynamics, environmental disturbances, and battery dynamics evaluator for 6-DOF quadrotors.
    """

    def __init__(self, config: DeepAerodynamicsConfig | None = None) -> None:
        self.cfg = config or DeepAerodynamicsConfig()
        self.state = DeepAerodynamicsState()
        self.reset()

    def reset(self, initial_soc: float = 1.0, initial_wind: np.ndarray | None = None) -> None:
        """Resets battery state of charge, aerodynamic states, and environmental wind disturbances."""
        self.state.soc = float(np.clip(initial_soc, 0.0, 1.0))
        self.state.v_ocv = self._compute_ocv(self.state.soc)
        self.state.v_terminal = self.state.v_ocv
        self.state.load_current = self.cfg.avionics_current
        v_ratio = self.state.v_terminal / self.cfg.nominal_voltage
        self.state.thrust_derate_factor = float(v_ratio**2)
        self.state.effective_max_thrust = 8.5 * self.state.thrust_derate_factor
        self.state.rotor_omega = np.zeros(4, dtype=np.float64)
        self.state.ige_ratios = np.ones(4, dtype=np.float64)
        self.state.tau_gyro_body = np.zeros(3, dtype=np.float64)
        self.state.energy_consumed_wh = 0.0

        # Environmental Disturbances Reset
        self.state.sim_time = 0.0
        if initial_wind is not None:
            self.state.wind_velocity = np.array(initial_wind, dtype=np.float64)
        elif self.cfg.wind_enabled:
            self.state.wind_velocity = np.array(self.cfg.wind_mean, dtype=np.float64)
        else:
            self.state.wind_velocity = np.zeros(3, dtype=np.float64)
        self.state.gust_velocity = np.zeros(3, dtype=np.float64)
        self.state.total_wind = self.state.wind_velocity.copy()
        self.state.relative_velocity = np.zeros(3, dtype=np.float64)
        self.state.aerodynamic_force = np.zeros(3, dtype=np.float64)
        self.state.ground_shear_torque = np.zeros(3, dtype=np.float64)

    def _compute_ocv(self, soc: float) -> float:
        """
        Computes LiPo open-circuit voltage from SoC using an empirical 4S LiPo discharge curve.
        """
        soc_clamped = float(np.clip(soc, 0.0, 1.0))
        # Non-linear LiPo curve: steep drop near 0%, plateau around 30%-80%, peak at 100%
        v_span = self.cfg.full_voltage - self.cfg.cutoff_voltage
        curve_factor = 0.82 * soc_clamped + 0.18 * (soc_clamped ** 0.35)
        return self.cfg.cutoff_voltage + v_span * curve_factor

    def compute_ige_thrust(
        self,
        base_motor_thrusts: np.ndarray,
        pos_world: np.ndarray,
        rotation_matrix: np.ndarray,
        arm_length: float,
        floor_z: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Applies Cheeseman-Bennett In-Ground-Effect (IGE) to each rotor based on its distance to ground.

        Returns:
            (augmented_thrusts, ige_ratios)
        """
        if not self.cfg.ige_enabled:
            return base_motor_thrusts.copy(), np.ones(4, dtype=np.float64)

        d = arm_length / math.sqrt(2.0)
        h_rotor = 0.02  # height of rotor disc above fuselage CoM (meters)

        # Body-frame rotor offsets for X-configuration
        # Motor 0: (+d, +d), Motor 1: (-d, +d), Motor 2: (-d, -d), Motor 3: (+d, -d)
        rotor_offsets_body = np.array([
            [ d,  d, h_rotor],
            [-d,  d, h_rotor],
            [-d, -d, h_rotor],
            [ d, -d, h_rotor],
        ], dtype=np.float64)

        R_rotor = self.cfg.rotor_radius
        ige_ratios = np.ones(4, dtype=np.float64)
        augmented_thrusts = np.zeros(4, dtype=np.float64)

        for i in range(4):
            # Compute rotor world position
            p_rotor_world = pos_world + rotation_matrix @ rotor_offsets_body[i]
            z_clearance = float(p_rotor_world[2] - floor_z)

            # Aerodynamic boundary layer floor limit to avoid mathematical singularity
            z_eff = max(z_clearance, 0.45 * R_rotor)

            # Cheeseman-Bennett formula: T_IGE / T_OGE = 1 / (1 - (R / (4*z))^2)
            denom = 1.0 - (R_rotor / (4.0 * z_eff)) ** 2
            if denom <= 0.15:
                ratio = self.cfg.max_ige_ratio
            else:
                ratio = min(self.cfg.max_ige_ratio, 1.0 / denom)

            # Ground effect diminishes rapidly above z > 2.5 * R_rotor
            if z_clearance > 4.0 * R_rotor:
                ratio = 1.0

            ige_ratios[i] = ratio
            augmented_thrusts[i] = base_motor_thrusts[i] * ratio

        self.state.ige_ratios = ige_ratios.copy()
        return augmented_thrusts, ige_ratios

    def compute_gyroscopic_moments(
        self,
        actual_thrusts: np.ndarray,
        omega_body: np.ndarray,
    ) -> np.ndarray:
        """
        Calculates gyroscopic precession torque generated by high-speed spinning rotor blades
        under body angular rates:
            tau_gyro = - Omega_B x H_rotors
            H_rotors = sum (s_i * J_r * omega_i) * e_3

        Rotor spin conventions for X-configuration:
            Motor 0: CCW (+1)
            Motor 1: CW  (-1)
            Motor 2: CCW (+1)
            Motor 3: CW  (-1)

        Returns:
            tau_gyro_body: 3D torque vector in body frame (N*m)
        """
        if not self.cfg.gyroscopic_enabled:
            return np.zeros(3, dtype=np.float64)

        c_T = max(1e-9, self.cfg.thrust_coefficient)
        # Omega_i = sqrt(T_i / c_T)
        rotor_omega = np.sqrt(np.maximum(0.0, actual_thrusts) / c_T)
        self.state.rotor_omega = rotor_omega.copy()

        # Spin direction signs
        spin_signs = np.array([1.0, -1.0, 1.0, -1.0], dtype=np.float64)
        J_r = self.cfg.rotor_inertia

        # Net rotor angular momentum along body z-axis (e_3)
        H_z = float(np.sum(spin_signs * J_r * rotor_omega))

        # Gyroscopic reaction torque on body: tau = - Omega x H
        # Omega = [w_x, w_y, w_z], H = [0, 0, H_z]
        # Omega x H = [w_y * H_z, -w_x * H_z, 0]
        # tau_gyro = [-w_y * H_z, w_x * H_z, 0]
        tau_gyro_body = np.array([
            -omega_body[1] * H_z,
             omega_body[0] * H_z,
            0.0,
        ], dtype=np.float64)

        self.state.tau_gyro_body = tau_gyro_body.copy()
        return tau_gyro_body

    def step_battery_dynamics(
        self,
        actual_thrusts: np.ndarray,
        dt: float,
        nominal_max_thrust: float = 8.5,
    ) -> tuple[float, float, float]:
        """
        Simulates battery discharge and voltage sag over time dt.

        Returns:
            (v_terminal, thrust_derate_factor, effective_max_thrust)
        """
        if not self.cfg.battery_enabled:
            return self.cfg.nominal_voltage, 1.0, nominal_max_thrust

        # 1. Compute electrical power consumption
        # P_mech per motor ~ c_P * T^1.5 (actuator disk theory approximation)
        p_mech_total = float(np.sum(self.cfg.power_coefficient * np.maximum(0.0, actual_thrusts) ** 1.5))
        # P_elec = P_mech / eta_m
        p_elec_motors = p_mech_total / max(0.1, self.cfg.motor_electrical_efficiency)

        # Estimate operating current: I ~ P / V
        v_est = max(self.cfg.cutoff_voltage, self.state.v_terminal)
        i_motors = p_elec_motors / v_est
        i_total = i_motors + self.cfg.avionics_current
        self.state.load_current = i_total

        # 2. Compute OCV and Terminal Voltage Sag: V_terminal = V_ocv - I * R_int
        self.state.v_ocv = self._compute_ocv(self.state.soc)
        v_sag = i_total * self.cfg.internal_resistance
        v_term = max(self.cfg.cutoff_voltage - 0.5, self.state.v_ocv - v_sag)
        self.state.v_terminal = v_term

        # 3. Integrate battery discharge: d(SoC)/dt = -I / (C * 3600)
        capacity_as = self.cfg.battery_capacity_ah * 3600.0  # Ampere-seconds (Coulombs)
        delta_soc = (i_total * dt) / capacity_as
        self.state.soc = max(0.0, self.state.soc - delta_soc)

        # 4. Integrate energy consumed
        self.state.energy_consumed_wh += (v_term * i_total * dt) / 3600.0

        # 5. Thrust authority derating: T_max(t) = T_max,0 * (V_terminal / V_nominal)^2
        v_ratio = v_term / self.cfg.nominal_voltage
        derate = float(np.clip(v_ratio ** 2, 0.25, 1.35))
        self.state.thrust_derate_factor = derate
        effective_max = nominal_max_thrust * derate
        self.state.effective_max_thrust = effective_max

        return v_term, derate, effective_max

    def compute_gust_velocity(self, current_time: float) -> np.ndarray:
        """
        Computes the instantaneous 1-cosine discrete wind gust velocity according to MIL-F-8785C:
            w_gust(t) = 0.5 * A_gust * (1 - cos(2 * pi * tau)) for 0 <= tau <= 1
            where tau = (t - t_start) / d_gust
        """
        if not self.cfg.gust_enabled:
            return np.zeros(3, dtype=np.float64)

        t_start = self.cfg.gust_start_time
        t_dur = max(1e-4, self.cfg.gust_duration)
        if t_start <= current_time <= (t_start + t_dur):
            tau = (current_time - t_start) / t_dur
            cos_factor = 0.5 * (1.0 - math.cos(2.0 * math.pi * tau))
            amp = np.array(self.cfg.gust_amplitude, dtype=np.float64)
            return amp * cos_factor
        return np.zeros(3, dtype=np.float64)

    def step_wind_turbulence(
        self,
        dt: float,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """
        Integrates the continuous Ornstein-Uhlenbeck stochastic wind process:
            dw = -theta * (w - w_mean) * dt + sigma * sqrt(dt) * xi
            where xi ~ N(0, I_3).
        """
        if not self.cfg.wind_enabled:
            self.state.wind_velocity = np.zeros(3, dtype=np.float64)
            return self.state.wind_velocity

        mean = np.array(self.cfg.wind_mean, dtype=np.float64)
        if rng is None:
            xi = np.zeros(3, dtype=np.float64)
        else:
            xi = rng.normal(0.0, 1.0, size=3)

        theta = self.cfg.wind_theta
        sigma = self.cfg.wind_sigma
        dw = -theta * (self.state.wind_velocity - mean) * dt + sigma * math.sqrt(max(0.0, dt)) * xi
        self.state.wind_velocity = self.state.wind_velocity + dw
        return self.state.wind_velocity

    def compute_aerodynamic_drag(
        self,
        drone_velocity: np.ndarray,
        total_wind: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Computes quadratic aerodynamic body drag force in world frame:
            v_rel = v_drone - w_total
            F_drag = -0.5 * rho * (C_d * A) * ||v_rel|| * v_rel
        Returns:
            (F_drag_world, v_rel)
        """
        v_rel = np.array(drone_velocity, dtype=np.float64) - total_wind
        speed_rel = float(np.linalg.norm(v_rel))
        if not self.cfg.drag_enabled or speed_rel < 1e-6:
            f_drag = np.zeros(3, dtype=np.float64)
        else:
            # Quadratic aerodynamic drag: 0.5 * rho * CdA * |v_rel| * v_rel
            f_drag = -0.5 * self.cfg.air_density * self.cfg.drag_area_product * speed_rel * v_rel

        self.state.relative_velocity = v_rel.copy()
        self.state.aerodynamic_force = f_drag.copy()
        return f_drag, v_rel

    def compute_ground_shear_torque(
        self,
        pos_world: np.ndarray,
        v_rel_world: np.ndarray,
        rotation_matrix: np.ndarray,
        floor_z: float = 0.0,
    ) -> np.ndarray:
        """
        Computes ground vortex destabilizing shear torque induced by relative crossflow near ground:
            z_clearance = pos_z - floor_z
            Near ground (z < 4 * R_rotor), horizontal crossflow deflects rotor downwash asymmetrically:
                tau_shear_world = c_shear * exp(-z_clearance / (2 * R_rotor)) * (v_rel_horiz x e_z)
                tau_shear_body = R^T * tau_shear_world
        """
        if abs(self.cfg.ground_shear_coefficient) < 1e-9:
            return np.zeros(3, dtype=np.float64)

        z_clearance = max(0.01, float(pos_world[2] - floor_z))
        R_rotor = self.cfg.rotor_radius
        decay = math.exp(-z_clearance / max(1e-3, 2.0 * R_rotor))

        # Horizontal relative velocity crossflow
        v_horiz = np.array([v_rel_world[0], v_rel_world[1], 0.0], dtype=np.float64)
        e_z = np.array([0.0, 0.0, 1.0], dtype=np.float64)

        # Cross product: v_horiz x e_z = [v_y, -v_x, 0]
        v_cross_ez = np.cross(v_horiz, e_z)
        tau_shear_world = self.cfg.ground_shear_coefficient * decay * v_cross_ez
        tau_shear_body = rotation_matrix.T @ tau_shear_world

        self.state.ground_shear_torque = tau_shear_body.copy()
        return tau_shear_body

    def step_wind_and_aerodynamics(
        self,
        drone_velocity: np.ndarray,
        drone_pos: np.ndarray,
        rotation_matrix: np.ndarray,
        dt: float,
        rng: np.random.Generator | None = None,
        floor_z: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Steps wind and computes total aerodynamic disturbance wrench (force and torque).

        Returns:
            (F_aero_world, tau_aero_body, total_wind)
        """
        self.state.sim_time += dt

        # 1. Update wind components
        w_turb = self.step_wind_turbulence(dt=dt, rng=rng)
        w_gust = self.compute_gust_velocity(current_time=self.state.sim_time)
        w_total = w_turb + w_gust

        self.state.gust_velocity = w_gust.copy()
        self.state.total_wind = w_total.copy()

        # 2. Quadratic Drag Force
        f_drag, v_rel = self.compute_aerodynamic_drag(
            drone_velocity=drone_velocity,
            total_wind=w_total,
        )

        # 3. Ground Effect Vortex Shear Torque
        tau_shear = self.compute_ground_shear_torque(
            pos_world=drone_pos,
            v_rel_world=v_rel,
            rotation_matrix=rotation_matrix,
            floor_z=floor_z,
        )

        return f_drag, tau_shear, w_total

