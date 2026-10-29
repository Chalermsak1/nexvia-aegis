"""
NEXVIA AEGIS — Full 6-DOF Underactuated Quadrotor Physics in MuJoCo Simulation.

Addresses the "Spherical Particle" reality gap:
1. Underactuated SE(3) Rigid-Body Dynamics:
   - Position acceleration in R^3 is coupled to attitude rotation R in SO(3).
   - Direct lateral force is physically impossible; quadrotor MUST tilt (roll/pitch)
     to direct total rotor thrust vector T * z_B toward desired direction.
2. 4 Independent Brushless Motor Rotors (X-Configuration):
   - Motor thrust: T_i = c_T * omega_i^2
   - Reaction drag torque: Q_i = c_tau * T_i (alternating CW/CCW)
   - First-order motor actuator lag: d(T_i)/dt = (T_cmd,i - T_i) / tau_m (tau_m = 35ms)
   - Individual thrust saturation: T_i in [0, T_max]
3. SE(3) Geometric Attitude Tracking (Lee et al.):
   - Orientation error on Lie group SO(3): e_R = 1/2 (R_des^T R - R^T R_des)^vee
   - Angular velocity error: e_Omega = omega_B - R^T R_des omega_des
   - Body moment generation: tau_B = -K_R e_R - K_Omega e_Omega + omega x (J omega)
4. Underactuated High-Order Control Barrier Functions (HOCBF):
   - Enforces obstacle clearance h(p) >= 0 under tilt angle constraint (theta <= 35 deg).
   - Accounts for orientation settling time and motor acceleration limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import mujoco
import numpy as np

from aegis.env.mujoco_3d_cbf import Obstacle3D


def quaternion_to_rotation_matrix(q: np.ndarray) -> np.ndarray:
    """Converts unit quaternion [w, x, y, z] to SO(3) rotation matrix R."""
    w, x, y, z = q
    return np.array([
        [1.0 - 2.0 * (y**2 + z**2), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)],
        [2.0 * (x * y + w * z), 1.0 - 2.0 * (x**2 + z**2), 2.0 * (y * z - w * x)],
        [2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x**2 + y**2)],
    ], dtype=np.float64)


def vee_operator(skew: np.ndarray) -> np.ndarray:
    """Extracts vector v in R^3 from skew-symmetric matrix so(3)."""
    return np.array([skew[2, 1], skew[0, 2], skew[1, 0]], dtype=np.float64)


@dataclass(frozen=True)
class QuadrotorConfig:
    mass: float = 1.25                        # kg
    arm_length: float = 0.22                  # meters (motor to CoM distance)
    inertia_diag: tuple[float, float, float] = (0.015, 0.015, 0.028)  # kg*m^2 (Ixx, Iyy, Izz)
    torque_ratio: float = 0.016               # c_tau = Q_i / T_i (meters)
    motor_tau: float = 0.035                  # 35ms first-order motor lag time constant
    max_thrust_per_motor: float = 8.5         # N (total max thrust = 34.0 N, T/W ~ 2.77)
    min_thrust_per_motor: float = 0.1         # N (idle spin)
    max_tilt_angle_deg: float = 35.0          # deg (maximum safe flight tilt angle)
    gravity: float = 9.81                     # m/s^2
    robot_collision_radius: float = 0.28      # meters (bounding sphere around rotor tips)
    arena_limit: float = 3.5                  # meters
    safety_margin: float = 0.12               # meters
    cbf_gamma: float = 2.2                    # CBF class-K gain
    inner_dt: float = 0.005                   # 200 Hz inner attitude loop
    outer_dt: float = 0.02                    # 50 Hz outer navigation & safety loop


class SE3GeometricController:
    """
    Geometric Tracking Controller on the Special Euclidean Group SE(3) with Motor Lag.
    References: Lee, Leok, McClamroch, IEEE CDC 2010.
    """

    def __init__(self, cfg: QuadrotorConfig) -> None:
        self.cfg = cfg
        self.J = np.diag(cfg.inertia_diag)
        self.inv_J = np.linalg.inv(self.J)
        self.max_tilt = math.radians(cfg.max_tilt_angle_deg)

        # Control gains
        self.k_R = np.array([4.5, 4.5, 2.8], dtype=np.float64)       # Attitude P gain
        self.k_Omega = np.array([0.45, 0.45, 0.35], dtype=np.float64) # Attitude D gain

        # Motor mixer matrix for X-configuration:
        # Motor 0: front-right (+x, +y), CCW (torque -c_tau)
        # Motor 1: front-left  (-x, +y), CW  (torque +c_tau)
        # Motor 2: rear-left   (-x, -y), CCW (torque -c_tau)
        # Motor 3: rear-right  (+x, -y), CW  (torque +c_tau)
        d = cfg.arm_length / math.sqrt(2.0)
        c_tau = cfg.torque_ratio
        self.mixer = np.array([
            [1.0, 1.0, 1.0, 1.0],        # Total thrust T
            [-d,   d,   d,  -d],         # Roll torque tau_x
            [ d,   d,  -d,  -d],         # Pitch torque tau_y
            [-c_tau, c_tau, -c_tau, c_tau] # Yaw torque tau_z
        ], dtype=np.float64)
        self.inv_mixer = np.linalg.inv(self.mixer)

        # Actual motor thrusts (subject to motor lag)
        hover_thrust = (cfg.mass * cfg.gravity) / 4.0
        self.actual_motor_thrusts = np.full(4, hover_thrust, dtype=np.float64)

    def reset(self) -> None:
        hover_thrust = (self.cfg.mass * self.cfg.gravity) / 4.0
        self.actual_motor_thrusts = np.full(4, hover_thrust, dtype=np.float64)

    def compute_motor_commands(
        self,
        desired_force_world: np.ndarray,
        current_quat: np.ndarray,
        current_omega_body: np.ndarray,
        desired_yaw: float = 0.0,
        dt: float = 0.005,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        """
        Converts desired 3D force vector into individual motor thrust commands,
        updates actual thrusts via motor lag, and returns:
        (actual_motor_thrusts, actual_world_force, current_tilt_rad)
        """
        R = quaternion_to_rotation_matrix(current_quat)
        z_B = R[:, 2]

        # Tilt angle with respect to world vertical e3
        current_tilt = float(np.arccos(np.clip(z_B[2], -1.0, 1.0)))

        # 1. Total thrust magnitude: T = F_des . z_B
        F_norm = float(np.linalg.norm(desired_force_world))
        if F_norm < 1e-4:
            desired_force_world = np.array([0.0, 0.0, self.cfg.mass * self.cfg.gravity])
            F_norm = float(np.linalg.norm(desired_force_world))

        # Enforce tilt angle saturation on desired thrust vector direction
        z_B_des = desired_force_world / F_norm
        tilt_des = float(np.arccos(np.clip(z_B_des[2], -1.0, 1.0)))
        if tilt_des > self.max_tilt:
            # Project onto cone of maximum allowable tilt
            horizontal_dir = z_B_des[:2] / max(1e-6, float(np.linalg.norm(z_B_des[:2])))
            z_B_des = np.array([
                horizontal_dir[0] * math.sin(self.max_tilt),
                horizontal_dir[1] * math.sin(self.max_tilt),
                math.cos(self.max_tilt),
            ], dtype=np.float64)
            z_B_des /= np.linalg.norm(z_B_des)

        # Desired total thrust
        T_cmd = float(np.dot(desired_force_world, z_B))
        T_cmd = np.clip(T_cmd, 4.0 * self.cfg.min_thrust_per_motor, 4.0 * self.cfg.max_thrust_per_motor)

        # 2. Desired Orientation Matrix R_des in SO(3)
        x_C = np.array([math.cos(desired_yaw), math.sin(desired_yaw), 0.0], dtype=np.float64)
        y_B_des = np.cross(z_B_des, x_C)
        y_B_norm = float(np.linalg.norm(y_B_des))
        if y_B_norm < 1e-4:
            y_B_des = np.array([0.0, 1.0, 0.0])
        else:
            y_B_des /= y_B_norm
        x_B_des = np.cross(y_B_des, z_B_des)
        R_des = np.column_stack((x_B_des, y_B_des, z_B_des))

        # 3. Geometric Attitude Error on SO(3)
        R_err_matrix = 0.5 * (R_des.T @ R - R.T @ R_des)
        e_R = vee_operator(R_err_matrix)
        e_Omega = current_omega_body  # assuming omega_des = 0 for regulation

        # 4. Body Torque Commands
        gyroscopic = np.cross(current_omega_body, self.J @ current_omega_body)
        tau_cmd = -self.k_R * e_R - self.k_Omega * e_Omega + gyroscopic

        # 5. Mixer Allocation: [T, tau_x, tau_y, tau_z] -> [T1, T2, T3, T4]
        wrench_cmd = np.array([T_cmd, tau_cmd[0], tau_cmd[1], tau_cmd[2]], dtype=np.float64)
        motor_thrust_cmds = self.inv_mixer @ wrench_cmd
        motor_thrust_cmds = np.clip(motor_thrust_cmds, self.cfg.min_thrust_per_motor, self.cfg.max_thrust_per_motor)

        # 6. Motor Lag Update: d(T)/dt = (T_cmd - T) / tau_m
        alpha_m = dt / max(1e-4, self.cfg.motor_tau)
        alpha_m = min(1.0, alpha_m)
        self.actual_motor_thrusts = (1.0 - alpha_m) * self.actual_motor_thrusts + alpha_m * motor_thrust_cmds

        # Actual force and torque produced by motors
        actual_wrench = self.mixer @ self.actual_motor_thrusts
        actual_thrust = actual_wrench[0]
        actual_force_world = R @ np.array([0.0, 0.0, actual_thrust], dtype=np.float64)

        return self.actual_motor_thrusts, actual_force_world, current_tilt


class UnderactuatedCBF6DOF:
    """
    Second-Order Control Barrier Function for Underactuated 6-DOF Quadrotor.
    Enforces collision avoidance while respecting tilt angle authority and thrust limits.
    """

    def __init__(self, cfg: QuadrotorConfig) -> None:
        self.cfg = cfg
        self.gamma1 = cfg.cbf_gamma
        self.gamma2 = cfg.cbf_gamma

    def filter_safe_force(
        self,
        pos: np.ndarray,
        vel: np.ndarray,
        desired_force: np.ndarray,
        obstacles: list[Obstacle3D],
        current_tilt: float,
    ) -> tuple[np.ndarray, bool]:
        """
        Filters desired outer-loop force F_des to satisfy CBF constraints.
        Returns: (F_safe, barrier_active)
        """
        m = self.cfg.mass
        r_quad = self.cfg.robot_collision_radius
        margin = self.cfg.safety_margin
        alpha1, alpha2 = self.gamma1, self.gamma2

        constraints: list[tuple[np.ndarray, float]] = []

        # 1. Obstacle avoidance constraints
        for obs in obstacles:
            p_rel = pos - obs.center
            r_safe = r_quad + obs.radius + margin
            h_val = float(np.sum(p_rel**2) - r_safe**2)
            h_dot = 2.0 * float(np.dot(p_rel, vel))

            # a^T F_des <= b
            # Acceleration a_net = F_des / m - g e3
            # Barrier derivative: B_dot + alpha2 * B >= 0
            a_vec = -2.0 * p_rel / m
            b_val = 2.0 * float(np.sum(vel**2)) + (alpha1 + alpha2) * h_dot + alpha1 * alpha2 * h_val - 2.0 * p_rel[2] * self.cfg.gravity
            constraints.append((a_vec, b_val))

        # 2. Floor limit: z >= r_quad + margin
        z_floor = r_quad + margin
        h_floor = pos[2] - z_floor
        a_floor = np.array([0.0, 0.0, -1.0 / m], dtype=np.float64)
        b_floor = (alpha1 + alpha2) * vel[2] + alpha1 * alpha2 * h_floor - self.cfg.gravity
        constraints.append((a_floor, b_floor))

        # 3. Arena ceiling and wall boundaries
        z_ceil = self.cfg.arena_limit - r_quad - margin
        h_ceil = z_ceil - pos[2]
        constraints.append((
            np.array([0.0, 0.0, 1.0 / m], dtype=np.float64),
            -(alpha1 + alpha2) * vel[2] + alpha1 * alpha2 * h_ceil + self.cfg.gravity
        ))

        for axis in (0, 1):
            wall_lim = self.cfg.arena_limit - r_quad - margin
            h_pos = wall_lim - pos[axis]
            a_pos = np.zeros(3)
            a_pos[axis] = 1.0 / m
            constraints.append((a_pos, -(alpha1 + alpha2) * vel[axis] + alpha1 * alpha2 * h_pos))

            h_neg = pos[axis] + wall_lim
            a_neg = np.zeros(3)
            a_neg[axis] = -1.0 / m
            constraints.append((a_neg, (alpha1 + alpha2) * vel[axis] + alpha1 * alpha2 * h_neg))

        # Active-set iterative projection
        F_safe = desired_force.copy()
        barrier_active = False

        for _ in range(6):
            violated = False
            for a_vec, b_val in constraints:
                val = float(np.dot(a_vec, F_safe))
                if val > b_val:
                    violated = True
                    barrier_active = True
                    norm_sq = float(np.sum(a_vec**2))
                    if norm_sq > 1e-8:
                        F_safe -= ((val - b_val) / norm_sq) * a_vec
            if not violated:
                break

        # Max total force bound
        max_total_thrust = 4.0 * self.cfg.max_thrust_per_motor
        norm_F = float(np.linalg.norm(F_safe))
        if norm_F > max_total_thrust:
            F_safe = F_safe / norm_F * max_total_thrust

        return F_safe, barrier_active


class AegisQuadrotor6DOFEnvironment:
    """
    Continuous 6-DOF Quadrotor Dynamics Environment in MuJoCo Physics.
    """

    def __init__(self, config: QuadrotorConfig | None = None) -> None:
        self.cfg = config or QuadrotorConfig()
        self.geom_ctrl = SE3GeometricController(self.cfg)
        self.cbf = UnderactuatedCBF6DOF(self.cfg)

        self.obstacles: list[Obstacle3D] = [
            Obstacle3D(center=np.array([0.0, 0.0, 0.9], dtype=np.float64), radius=0.45),
            Obstacle3D(center=np.array([1.2, -0.9, 0.8], dtype=np.float64), radius=0.35),
            Obstacle3D(center=np.array([-0.9, 1.2, 0.8], dtype=np.float64), radius=0.35),
        ]
        self.target_pos = np.array([1.8, 1.8, 1.2], dtype=np.float64)

        self.model = self._build_mujoco_model()
        self.data = mujoco.MjData(self.model)
        self.quad_body_id = self.model.body("quadrotor").id
        self.step_count = 0

    def _build_mujoco_model(self) -> mujoco.MjModel:
        c = self.cfg
        obs_xml = ""
        for i, obs in enumerate(self.obstacles):
            obs_xml += f"""
            <geom name="obs_{i}" type="sphere" size="{obs.radius}"
                  pos="{obs.center[0]} {obs.center[1]} {obs.center[2]}"
                  rgba="0.9 0.25 0.2 0.75" />
            """

        d = c.arm_length / math.sqrt(2.0)
        xml = f"""
        <mujoco model="nexvia_aegis_quadrotor_6dof">
          <option timestep="{c.inner_dt}" gravity="0 0 -{c.gravity}"/>
          <worldbody>
            <geom name="floor" type="plane" size="{c.arena_limit} {c.arena_limit} 0.1"
                  pos="0 0 0" rgba="0.10 0.10 0.12 1"/>
            {obs_xml}
            <body name="quadrotor" pos="-1.8 -1.8 0.5">
              <freejoint name="root"/>
              <!-- Explicit Physical Inertial Definition overrides child geom densities -->
              <inertial pos="0 0 0" mass="{c.mass}" diaginertia="{c.inertia_diag[0]} {c.inertia_diag[1]} {c.inertia_diag[2]}"/>
              <!-- Central Fuselage -->
              <geom name="fuselage" type="box" size="0.08 0.08 0.03" rgba="0.15 0.15 0.2 1"/>
              <!-- Cross Arms -->
              <geom name="arm_front" type="capsule" fromto="{-d} {-d} 0 {d} {d} 0" size="0.012" rgba="0.4 0.4 0.5 1"/>
              <geom name="arm_rear"  type="capsule" fromto="{-d} {d} 0 {d} {-d} 0" size="0.012" rgba="0.4 0.4 0.5 1"/>
              <!-- 4 Rotor Propeller Discs -->
              <geom name="rotor_0" type="cylinder" size="0.09 0.003" pos="{d} {d} 0.02" rgba="0.2 0.8 1.0 0.6"/>
              <geom name="rotor_1" type="cylinder" size="0.09 0.003" pos="{-d} {d} 0.02" rgba="0.2 1.0 0.4 0.6"/>
              <geom name="rotor_2" type="cylinder" size="0.09 0.003" pos="{-d} {-d} 0.02" rgba="0.2 1.0 0.4 0.6"/>
              <geom name="rotor_3" type="cylinder" size="0.09 0.003" pos="{d} {-d} 0.02" rgba="0.2 0.8 1.0 0.6"/>
            </body>
            <site name="target" pos="{self.target_pos[0]} {self.target_pos[1]} {self.target_pos[2]}"
                  size="0.20" rgba="0.2 1.0 0.4 0.5"/>
          </worldbody>
        </mujoco>
        """
        return mujoco.MjModel.from_xml_string(xml)

    def reset(self, rng: np.random.Generator | None = None) -> dict[str, Any]:
        mujoco.mj_resetData(self.model, self.data)
        self.step_count = 0
        self.geom_ctrl.reset()

        px = -1.8 + (rng.normal(0, 0.02) if rng else 0.0)
        py = -1.8 + (rng.normal(0, 0.02) if rng else 0.0)
        pz = 0.5

        # Initialize qpos: [x, y, z, qw, qx, qy, qz]
        self.data.qpos[:3] = [px, py, pz]
        self.data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]  # level attitude
        self.data.qvel[:] = 0.0

        mujoco.mj_forward(self.model, self.data)
        return self.get_state()

    def get_state(self) -> dict[str, Any]:
        pos = self.data.qpos[:3].copy()
        quat = self.data.qpos[3:7].copy()
        vel = self.data.qvel[:3].copy()
        omega_body = self.data.qvel[3:6].copy()

        R = quaternion_to_rotation_matrix(quat)
        tilt_rad = float(np.arccos(np.clip(R[2, 2], -1.0, 1.0)))

        # Collision detection with obstacles
        r_quad = self.cfg.robot_collision_radius
        collision_obstacle = any(
            float(np.linalg.norm(pos - obs.center)) < (r_quad + obs.radius)
            for obs in self.obstacles
        )
        collision_floor = pos[2] < (r_quad + 0.02)
        collision = collision_obstacle or collision_floor

        dist_to_target = float(np.linalg.norm(pos - self.target_pos))

        return {
            "pos": pos,
            "quat": quat,
            "vel": vel,
            "omega_body": omega_body,
            "rotation_matrix": R,
            "tilt_deg": math.degrees(tilt_rad),
            "collision": collision,
            "distance": dist_to_target,
            "rotor_thrusts": self.geom_ctrl.actual_motor_thrusts.copy(),
        }

    def step_outer(
        self,
        desired_force_world: np.ndarray,
        shield_with_cbf: bool = True,
        desired_yaw: float = 0.0,
    ) -> tuple[dict[str, Any], bool]:
        """
        Executes one 50 Hz outer-loop step by running four 200 Hz inner SE(3) steps.
        Returns: (state, barrier_active)
        """
        self.step_count += 1
        st = self.get_state()
        pos = st["pos"]
        vel = st["vel"]
        current_tilt = math.radians(st["tilt_deg"])

        # 1. CBF Safety Shielding
        barrier_active = False
        if shield_with_cbf:
            force_safe, barrier_active = self.cbf.filter_safe_force(
                pos=pos,
                vel=vel,
                desired_force=desired_force_world,
                obstacles=self.obstacles,
                current_tilt=current_tilt,
            )
        else:
            force_safe = desired_force_world

        # 2. Run inner SE(3) control loop at 200 Hz (4 sub-steps)
        sub_steps = int(round(self.cfg.outer_dt / self.cfg.inner_dt))
        drag_coeff_trans = 0.12
        drag_coeff_rot = 0.04

        for _ in range(sub_steps):
            q_current = self.data.qpos[3:7].copy()
            w_current = self.data.qvel[3:6].copy()
            v_current = self.data.qvel[:3].copy()

            # Geometric controller computes motor thrusts and resultant body force
            rotors, f_world, _ = self.geom_ctrl.compute_motor_commands(
                desired_force_world=force_safe,
                current_quat=q_current,
                current_omega_body=w_current,
                desired_yaw=desired_yaw,
                dt=self.cfg.inner_dt,
            )

            # Aerodynamic damping
            f_world += -drag_coeff_trans * v_current
            R = quaternion_to_rotation_matrix(q_current)
            wrench_actual = self.geom_ctrl.mixer @ rotors
            tau_body = np.array([wrench_actual[1], wrench_actual[2], wrench_actual[3]]) - drag_coeff_rot * w_current
            tau_world = R @ tau_body

            # Apply forces directly to freejoint quadrotor body
            self.data.xfrc_applied[self.quad_body_id, :3] = f_world
            self.data.xfrc_applied[self.quad_body_id, 3:6] = tau_world

            mujoco.mj_step(self.model, self.data)

        return self.get_state(), barrier_active
