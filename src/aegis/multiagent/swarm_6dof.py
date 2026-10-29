"""
NEXVIA AEGIS — Multi-Agent 6-DOF Quadrotor Swarm Physics in MuJoCo Simulation.

Combines:
1. Full 6-DOF Underactuated Quadrotor Dynamics on SE(3) for N=5 simultaneous aerial robots.
2. 20 Independent Brushless Motors (4 per drone) with reaction drag torque and motor lag tau_m = 35ms.
3. SE(3) Geometric Attitude Tracking with strict tilt cone saturation (theta <= 35 deg).
4. Reciprocal Underactuated High-Order Control Barrier Functions (HOCBF):
   - Floor, ceiling, and arena boundary limits
   - Static 3D spherical obstacles
   - Reciprocal inter-agent collision avoidance across all 10 quadrotor pairs
5. Stochastic Ornstein-Uhlenbeck continuous aerodynamic wind turbulence.
6. Integration with Byzantine-Resilient Martingale Consensus (BRMC) defending against F=2 colluding attacks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, List, Tuple

import mujoco
import numpy as np

from aegis.env.mujoco_3d_cbf import Obstacle3D
from aegis.env.quadrotor_6dof import (
    QuadrotorConfig,
    SE3GeometricController,
    quaternion_to_rotation_matrix,
    vee_operator,
)
from aegis.multiagent.brmc_engine import (
    AgentMessage,
    ByzantineResilientMartingaleConsensus,
    SwarmConsensusState,
)


@dataclass(frozen=True)
class Swarm6DOFConfig:
    num_robots: int = 5
    mass: float = 1.2                         # kg per drone
    arm_length: float = 0.22                   # meters (motor to CoM)
    inertia_diag: tuple[float, float, float] = (0.015, 0.015, 0.028)  # kg*m^2
    torque_ratio: float = 0.016                # c_tau = Q_i / T_i
    motor_tau: float = 0.035                   # 35ms first-order motor lag
    max_thrust_per_motor: float = 8.5          # N
    min_thrust_per_motor: float = 0.1          # N
    max_tilt_angle_deg: float = 35.0           # deg
    gravity: float = 9.81                      # m/s^2
    robot_collision_radius: float = 0.28       # meters
    safety_margin: float = 0.12                # meters (for static obstacles)
    inter_agent_margin: float = 0.16           # meters (mutual separation buffer)
    arena_limit: float = 3.5                   # meters
    cbf_gamma: float = 2.2                     # Class-K barrier gain
    inner_dt: float = 0.005                    # 200 Hz inner loop
    outer_dt: float = 0.02                     # 50 Hz outer loop
    target_arrival_radius: float = 0.28        # meters
    start_origin: tuple[float, float, float] = (-2.0, -2.0, 0.5)
    # Wind turbulence parameters (Ornstein-Uhlenbeck)
    wind_enabled: bool = True
    wind_theta: float = 0.4
    wind_sigma: float = 0.12
    wind_mean: tuple[float, float, float] = (0.3, -0.2, 0.0)


class ReciprocalUnderactuatedCBF6DOF:
    """
    Reciprocal High-Order Control Barrier Function filter for 6-DOF Quadrotor Swarms.
    Enforces collision avoidance against:
    1. Static 3D obstacles
    2. Arena boundaries (floor, ceiling, walls)
    3. Mutual inter-agent separation between all pairs of 6-DOF quadrotors.
    """

    def __init__(self, cfg: Swarm6DOFConfig) -> None:
        self.cfg = cfg
        self.gamma1 = cfg.cbf_gamma
        self.gamma2 = cfg.cbf_gamma

    def filter_swarm_forces(
        self,
        positions: list[np.ndarray],
        velocities: list[np.ndarray],
        desired_forces: list[np.ndarray],
        obstacles: list[Obstacle3D],
        quarantined_mask: list[bool] | None = None,
    ) -> tuple[list[np.ndarray], list[bool]]:
        """
        Solves active-set projection for all quadrotors in the swarm.
        Returns: (safe_forces, barriers_active)
        """
        n = len(positions)
        if quarantined_mask is None:
            quarantined_mask = [False] * n

        m = self.cfg.mass
        r_quad = self.cfg.robot_collision_radius
        margin_obs = self.cfg.safety_margin
        margin_agent = self.cfg.inter_agent_margin
        alpha1, alpha2 = self.gamma1, self.gamma2

        safe_forces = []
        barriers_active = []

        for i in range(n):
            pos_i = positions[i]
            vel_i = velocities[i]
            f_des_i = desired_forces[i].copy()

            constraints: list[tuple[np.ndarray, float]] = []

            # 1. Static Obstacle Barriers
            for obs in obstacles:
                p_rel = pos_i - obs.center
                r_safe = r_quad + obs.radius + margin_obs
                h_val = float(np.sum(p_rel**2) - r_safe**2)
                h_dot = 2.0 * float(np.dot(p_rel, vel_i))

                a_vec = -2.0 * p_rel / m
                b_val = 2.0 * float(np.sum(vel_i**2)) + (alpha1 + alpha2) * h_dot + alpha1 * alpha2 * h_val - 2.0 * p_rel[2] * self.cfg.gravity
                constraints.append((a_vec, b_val))

            # 2. Arena Floor and Ceiling
            z_floor = r_quad + margin_obs
            h_floor = pos_i[2] - z_floor
            constraints.append((
                np.array([0.0, 0.0, -1.0 / m], dtype=np.float64),
                (alpha1 + alpha2) * vel_i[2] + alpha1 * alpha2 * h_floor - self.cfg.gravity
            ))

            z_ceil = self.cfg.arena_limit - r_quad - margin_obs
            h_ceil = z_ceil - pos_i[2]
            constraints.append((
                np.array([0.0, 0.0, 1.0 / m], dtype=np.float64),
                -(alpha1 + alpha2) * vel_i[2] + alpha1 * alpha2 * h_ceil + self.cfg.gravity
            ))

            for axis in (0, 1):
                wall_lim = self.cfg.arena_limit - r_quad - margin_obs
                h_pos = wall_lim - pos_i[axis]
                a_pos = np.zeros(3)
                a_pos[axis] = 1.0 / m
                constraints.append((a_pos, -(alpha1 + alpha2) * vel_i[axis] + alpha1 * alpha2 * h_pos))

                h_neg = pos_i[axis] + wall_lim
                a_neg = np.zeros(3)
                a_neg[axis] = -1.0 / m
                constraints.append((a_neg, (alpha1 + alpha2) * vel_i[axis] + alpha1 * alpha2 * h_neg))

            # 3. Reciprocal Inter-Agent Barriers between quadrotor i and quadrotor j
            for j in range(n):
                if i == j:
                    continue
                pos_j = positions[j]
                vel_j = velocities[j]
                p_ij = pos_i - pos_j
                v_ij = vel_i - vel_j
                r_mutual = 2.0 * r_quad + margin_agent
                h_ij = float(np.sum(p_ij**2) - r_mutual**2)
                h_dot_ij = 2.0 * float(np.dot(p_ij, v_ij))

                # Reciprocal sharing: quadrotor i assumes half responsibility
                # a_ij^T F_i <= b_ij
                a_ij = -2.0 * p_ij / m
                b_ij = float(np.sum(v_ij**2)) + (alpha1 + alpha2) * h_dot_ij + alpha1 * alpha2 * h_ij
                constraints.append((a_ij, b_ij))

            # Active-set iterative projection
            f_safe = f_des_i.copy()
            active = False
            for _ in range(8):
                violated = False
                for a_vec, b_val in constraints:
                    val = float(np.dot(a_vec, f_safe))
                    if val > b_val:
                        violated = True
                        active = True
                        norm_sq = float(np.sum(a_vec**2))
                        if norm_sq > 1e-8:
                            f_safe -= ((val - b_val) / norm_sq) * a_vec
                if not violated:
                    break

            # Bound total thrust authority
            max_thrust = 4.0 * self.cfg.max_thrust_per_motor
            norm_f = float(np.linalg.norm(f_safe))
            if norm_f > max_thrust:
                f_safe = (f_safe / norm_f) * max_thrust

            safe_forces.append(f_safe)
            barriers_active.append(active)

        return safe_forces, barriers_active


class AegisMuJoCoSwarm6DOFEnvironment:
    """
    Continuous Multi-Agent 6-DOF Quadrotor Dynamics Environment in MuJoCo Physics.
    """

    def __init__(self, config: Swarm6DOFConfig | None = None) -> None:
        self.cfg = config or Swarm6DOFConfig()
        self.quad_cfg = QuadrotorConfig(
            mass=self.cfg.mass,
            arm_length=self.cfg.arm_length,
            inertia_diag=self.cfg.inertia_diag,
            torque_ratio=self.cfg.torque_ratio,
            motor_tau=self.cfg.motor_tau,
            max_thrust_per_motor=self.cfg.max_thrust_per_motor,
            min_thrust_per_motor=self.cfg.min_thrust_per_motor,
            max_tilt_angle_deg=self.cfg.max_tilt_angle_deg,
            gravity=self.cfg.gravity,
            robot_collision_radius=self.cfg.robot_collision_radius,
            arena_limit=self.cfg.arena_limit,
            inner_dt=self.cfg.inner_dt,
            outer_dt=self.cfg.outer_dt,
        )

        # 5 Independent SE(3) Geometric Controllers (one per drone)
        self.controllers = [SE3GeometricController(self.quad_cfg) for _ in range(self.cfg.num_robots)]
        self.cbf_filter = ReciprocalUnderactuatedCBF6DOF(self.cfg)

        self.obstacles: list[Obstacle3D] = [
            Obstacle3D(center=np.array([0.0, 0.0, 0.8], dtype=np.float64), radius=0.45),
            Obstacle3D(center=np.array([1.2, -0.9, 0.7], dtype=np.float64), radius=0.35),
            Obstacle3D(center=np.array([-0.9, 1.2, 0.7], dtype=np.float64), radius=0.35),
        ]
        self.target_pos = np.array([2.0, 2.0, 1.2], dtype=np.float64)
        self.wind_velocity = np.array(self.cfg.wind_mean, dtype=np.float64)

        self.model = self._build_mujoco_model()
        self.data = mujoco.MjData(self.model)

        self.quad_body_ids = [self.model.body(f"quadrotor_{i}").id for i in range(self.cfg.num_robots)]
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
        colors = [
            "0.2 0.7 1.0 1",  # Agent 0: Cyan/Blue
            "0.2 1.0 0.4 1",  # Agent 1: Green
            "1.0 0.8 0.2 1",  # Agent 2: Yellow/Amber
            "0.8 0.3 1.0 1",  # Agent 3: Purple (Byzantine 1)
            "1.0 0.3 0.3 1",  # Agent 4: Red (Byzantine 2)
        ]

        drones_xml = ""
        for i in range(c.num_robots):
            px = -2.0 + (i % 3) * 0.70
            py = -2.0 + (i // 3) * 0.70
            pz = 0.5 + 0.15 * (i % 2)
            clr = colors[i % len(colors)]

            drones_xml += f"""
            <body name="quadrotor_{i}" pos="{px} {py} {pz}">
              <freejoint name="root_{i}"/>
              <inertial pos="0 0 0" mass="{c.mass}" diaginertia="{c.inertia_diag[0]} {c.inertia_diag[1]} {c.inertia_diag[2]}"/>
              <!-- Central Fuselage -->
              <geom name="fuselage_{i}" type="box" size="0.08 0.08 0.03" rgba="{clr}"/>
              <!-- Cross Arms -->
              <geom name="arm_f_{i}" type="capsule" fromto="{-d} {-d} 0 {d} {d} 0" size="0.012" rgba="0.4 0.4 0.5 1"/>
              <geom name="arm_r_{i}" type="capsule" fromto="{-d} {d} 0 {d} {-d} 0" size="0.012" rgba="0.4 0.4 0.5 1"/>
              <!-- 4 Rotor Propeller Discs -->
              <geom name="rotor_{i}_0" type="cylinder" size="0.09 0.003" pos="{d} {d} 0.02" rgba="0.2 0.8 1.0 0.6"/>
              <geom name="rotor_{i}_1" type="cylinder" size="0.09 0.003" pos="{-d} {d} 0.02" rgba="0.2 1.0 0.4 0.6"/>
              <geom name="rotor_{i}_2" type="cylinder" size="0.09 0.003" pos="{-d} {-d} 0.02" rgba="0.2 1.0 0.4 0.6"/>
              <geom name="rotor_{i}_3" type="cylinder" size="0.09 0.003" pos="{d} {-d} 0.02" rgba="0.2 0.8 1.0 0.6"/>
            </body>
            """

        xml = f"""
        <mujoco model="nexvia_aegis_swarm_6dof">
          <option timestep="{c.inner_dt}" gravity="0 0 -{c.gravity}"/>
          <worldbody>
            <geom name="floor" type="plane" size="{c.arena_limit} {c.arena_limit} 0.1"
                  pos="0 0 0" rgba="0.10 0.10 0.12 1"/>
            {obs_xml}
            {drones_xml}
            <site name="target" pos="{self.target_pos[0]} {self.target_pos[1]} {self.target_pos[2]}"
                  size="{c.target_arrival_radius}" rgba="0.2 1.0 0.4 0.5"/>
          </worldbody>
        </mujoco>
        """
        return mujoco.MjModel.from_xml_string(xml)

    def reset(
        self,
        rng: np.random.Generator | None = None,
        start_origin: tuple[float, float, float] | None = None,
    ) -> dict[str, Any]:
        mujoco.mj_resetData(self.model, self.data)
        self.step_count = 0
        self.wind_velocity = np.array(self.cfg.wind_mean, dtype=np.float64)

        for ctrl in self.controllers:
            ctrl.reset()

        origin = start_origin or self.cfg.start_origin

        # Initialize quadrotor starting poses staggered in formation
        for i in range(self.cfg.num_robots):
            qpos_idx = 7 * i
            qvel_idx = 6 * i

            px = origin[0] + (i % 3) * 0.70 + (rng.normal(0, 0.02) if rng else 0.0)
            py = origin[1] + (i // 3) * 0.70 + (rng.normal(0, 0.02) if rng else 0.0)
            pz = origin[2] + 0.15 * (i % 2)

            self.data.qpos[qpos_idx : qpos_idx + 3] = [px, py, pz]
            self.data.qpos[qpos_idx + 3 : qpos_idx + 7] = [1.0, 0.0, 0.0, 0.0]  # level attitude
            self.data.qvel[qvel_idx : qvel_idx + 6] = 0.0

        mujoco.mj_forward(self.model, self.data)
        return self.get_state()

    def get_state(self) -> dict[str, Any]:
        positions = []
        velocities = []
        quaternions = []
        tilt_degrees = []
        all_rotor_thrusts = []

        for i in range(self.cfg.num_robots):
            qpos_idx = 7 * i
            qvel_idx = 6 * i

            pos = self.data.qpos[qpos_idx : qpos_idx + 3].copy()
            quat = self.data.qpos[qpos_idx + 3 : qpos_idx + 7].copy()
            vel = self.data.qvel[qvel_idx : qvel_idx + 3].copy()

            R = quaternion_to_rotation_matrix(quat)
            tilt_rad = float(np.arccos(np.clip(R[2, 2], -1.0, 1.0)))

            positions.append(pos)
            velocities.append(vel)
            quaternions.append(quat)
            tilt_degrees.append(math.degrees(tilt_rad))
            all_rotor_thrusts.append(self.controllers[i].actual_motor_thrusts.copy())

        # Inter-agent and obstacle collision checks
        r_quad = self.cfg.robot_collision_radius
        obstacle_collisions = [False] * self.cfg.num_robots
        for i, pos in enumerate(positions):
            if any(float(np.linalg.norm(pos - obs.center)) < (r_quad + obs.radius) for obs in self.obstacles):
                obstacle_collisions[i] = True
            if pos[2] < (r_quad + 0.02):
                obstacle_collisions[i] = True

        # Inter-agent collision between any two quadrotors
        inter_agent_collision_count = 0
        n = self.cfg.num_robots
        for i in range(n):
            for j in range(i + 1, n):
                d_ij = float(np.linalg.norm(positions[i] - positions[j]))
                if d_ij < (2.0 * r_quad):
                    inter_agent_collision_count += 1

        distances_to_target = [float(np.linalg.norm(p - self.target_pos)) for p in positions]

        return {
            "positions": positions,
            "velocities": velocities,
            "quaternions": quaternions,
            "tilts_deg": tilt_degrees,
            "rotor_thrusts": all_rotor_thrusts,
            "obstacle_collisions": obstacle_collisions,
            "inter_agent_collisions": inter_agent_collision_count,
            "distances": distances_to_target,
            "wind": self.wind_velocity.copy(),
        }

    def step_outer(
        self,
        desired_forces: list[np.ndarray],
        shield_with_cbf: bool = True,
        quarantined_mask: list[bool] | None = None,
        rng: np.random.Generator | None = None,
    ) -> tuple[dict[str, Any], list[bool]]:
        """
        Executes one 50 Hz outer step (running 4 inner 200 Hz SE(3) steps).
        Returns: (state, barriers_active)
        """
        self.step_count += 1
        st = self.get_state()
        positions = st["positions"]
        velocities = st["velocities"]

        # 1. Update Ornstein-Uhlenbeck Wind Process
        if self.cfg.wind_enabled and rng is not None:
            dt_outer = self.cfg.outer_dt
            theta = self.cfg.wind_theta
            sigma = self.cfg.wind_sigma
            mean = np.array(self.cfg.wind_mean, dtype=np.float64)
            dw = -theta * (self.wind_velocity - mean) * dt_outer + sigma * math.sqrt(dt_outer) * rng.normal(0, 1, 3)
            self.wind_velocity += dw

        # 2. Reciprocal Underactuated CBF Safety Filtering
        barriers_active = [False] * self.cfg.num_robots
        if shield_with_cbf:
            forces_safe, barriers_active = self.cbf_filter.filter_swarm_forces(
                positions=positions,
                velocities=velocities,
                desired_forces=desired_forces,
                obstacles=self.obstacles,
                quarantined_mask=quarantined_mask,
            )
        else:
            forces_safe = [f.copy() for f in desired_forces]

        # 3. Inner 200 Hz SE(3) Attitude & Motor Loop (4 sub-steps)
        sub_steps = int(round(self.cfg.outer_dt / self.cfg.inner_dt))
        drag_trans = 0.12
        drag_rot = 0.04

        for _ in range(sub_steps):
            for i in range(self.cfg.num_robots):
                qpos_idx = 7 * i
                qvel_idx = 6 * i

                q_curr = self.data.qpos[qpos_idx + 3 : qpos_idx + 7].copy()
                w_curr = self.data.qvel[qvel_idx + 3 : qvel_idx + 6].copy()
                v_curr = self.data.qvel[qvel_idx : qvel_idx + 3].copy()

                # Geometric attitude controller computes individual rotor thrusts
                rotors, f_world, _ = self.controllers[i].compute_motor_commands(
                    desired_force_world=forces_safe[i],
                    current_quat=q_curr,
                    current_omega_body=w_curr,
                    desired_yaw=0.0,
                    dt=self.cfg.inner_dt,
                )

                # Aerodynamic relative wind damping
                v_rel = v_curr - self.wind_velocity
                f_world += -drag_trans * v_rel

                R = quaternion_to_rotation_matrix(q_curr)
                wrench_actual = self.controllers[i].mixer @ rotors
                tau_body = np.array([wrench_actual[1], wrench_actual[2], wrench_actual[3]]) - drag_rot * w_curr
                tau_world = R @ tau_body

                bid = self.quad_body_ids[i]
                self.data.xfrc_applied[bid, :3] = f_world
                self.data.xfrc_applied[bid, 3:6] = tau_world

            mujoco.mj_step(self.model, self.data)

        return self.get_state(), barriers_active
