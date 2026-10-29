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
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Tuple

import numpy as np


@dataclass(frozen=True)
class DeepAerodynamicsConfig:
    """Configuration parameters for deep aerodynamic and battery physics."""
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


@dataclass
class DeepAerodynamicsState:
    """Real-time physical state of aerodynamics and battery."""
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


class DeepAerodynamicsEngine:
    """
    High-fidelity aerodynamics and battery dynamics evaluator for 6-DOF quadrotors.
    """

    def __init__(self, config: DeepAerodynamicsConfig | None = None) -> None:
        self.cfg = config or DeepAerodynamicsConfig()
        self.state = DeepAerodynamicsState()
        self.reset()

    def reset(self, initial_soc: float = 1.0) -> None:
        """Resets battery state of charge and aerodynamic states."""
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
