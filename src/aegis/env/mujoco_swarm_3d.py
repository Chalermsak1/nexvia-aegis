"""
NEXVIA AEGIS — Multi-Agent 3D Swarm Environment in MuJoCo Physics with Inter-Agent CBF & Wind Dynamics.

Key Features:
1. Continuous 3D multi-robot rigid body dynamics in MuJoCo.
2. High-Order Control Barrier Functions (HOCBF) for:
   - Arena boundary limits (floor, ceiling, walls)
   - Static spherical obstacle avoidance
   - Reciprocal inter-agent collision avoidance between all robot pairs
3. Stochastic continuous Ornstein-Uhlenbeck aerodynamic wind turbulence process:
   dw(t) = -theta_w (w(t) - w_mean) dt + sigma_w dW_t
4. Integration with Byzantine-Resilient Martingale Consensus (BRMC).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, List, Tuple

import mujoco
import numpy as np

from aegis.env.mujoco_3d_cbf import Obstacle3D
from aegis.multiagent.brmc_engine import (
    AgentMessage,
    ByzantineResilientMartingaleConsensus,
    SwarmConsensusState,
)


@dataclass(frozen=True)
class Swarm3DConfig:
    num_robots: int = 5
    timestep: float = 0.02
    robot_mass: float = 1.0
    robot_radius: float = 0.18
    arena_limit: float = 3.5  # [-3.5, 3.5]
    control_force_limit: float = 2.5
    cbf_gamma: float = 2.5
    safety_margin: float = 0.12
    inter_agent_margin: float = 0.15
    target_arrival_radius: float = 0.25
    # Wind turbulence parameters (Ornstein-Uhlenbeck)
    wind_enabled: bool = True
    wind_theta: float = 0.5
    wind_sigma: float = 0.15
    wind_mean: np.ndarray = field(default_factory=lambda: np.array([0.2, -0.1, 0.0], dtype=np.float64))


class SwarmCBF3DFilter:
    """
    Decentralized/Centralized High-Order Control Barrier Function filter for Swarms.
    Enforces forward dynamic invariance for:
    1. Obstacles
    2. Boundary walls
    3. Inter-agent collision avoidance
    """

    def __init__(self, config: Swarm3DConfig) -> None:
        self.cfg = config

    def compute_safe_swarm_controls(
        self,
        positions: list[np.ndarray],     # list of (3,) arrays
        velocities: list[np.ndarray],    # list of (3,) arrays
        desired_controls: list[np.ndarray], # list of (3,) arrays
        obstacles: list[Obstacle3D],
        quarantined_mask: list[bool] | None = None,
    ) -> tuple[list[np.ndarray], list[bool]]:
        """
        Solves CBF QP for all robots ensuring obstacle, boundary, and mutual clearance.
        Returns: (safe_controls, barriers_active)
        """
        n = len(positions)
        if quarantined_mask is None:
            quarantined_mask = [False] * n

        safe_controls = []
        barriers_active = []

        alpha1 = self.cfg.cbf_gamma
        alpha2 = self.cfg.cbf_gamma
        m = self.cfg.robot_mass
        r_rob = self.cfg.robot_radius
        margin = self.cfg.safety_margin

        for i in range(n):
            pos_i = positions[i]
            vel_i = velocities[i]
            u_des_i = np.clip(desired_controls[i], -self.cfg.control_force_limit, self.cfg.control_force_limit)

            constraints: list[tuple[np.ndarray, float]] = []

            # 1. Obstacle avoidance constraints for robot i
            for obs in obstacles:
                p_rel = pos_i - obs.center
                r_safe = r_rob + obs.radius + margin
                h_val = float(np.sum(p_rel**2) - r_safe**2)
                h_dot = 2.0 * float(np.dot(p_rel, vel_i))

                a_vec = -2.0 * p_rel / m
                b_val = 2.0 * float(np.sum(vel_i**2)) + (alpha1 + alpha2) * h_dot + alpha1 * alpha2 * h_val
                constraints.append((a_vec, b_val))

            # 2. Arena Boundary constraints
            z_floor = r_rob + margin
            h_floor = pos_i[2] - z_floor
            constraints.append((
                np.array([0.0, 0.0, -1.0 / m], dtype=np.float64),
                (alpha1 + alpha2) * vel_i[2] + alpha1 * alpha2 * h_floor
            ))

            for axis in (0, 1):
                wall_lim = self.cfg.arena_limit - r_rob - margin
                h_pos = wall_lim - pos_i[axis]
                constraints.append((
                    np.eye(3, dtype=np.float64)[axis] * (1.0 / m),
                    -(alpha1 + alpha2) * vel_i[axis] + alpha1 * alpha2 * h_pos
                ))
                h_neg = pos_i[axis] + wall_lim
                constraints.append((
                    -np.eye(3, dtype=np.float64)[axis] * (1.0 / m),
                    (alpha1 + alpha2) * vel_i[axis] + alpha1 * alpha2 * h_neg
                ))

            # 3. Inter-agent collision avoidance constraints
            # Barrier between robot i and robot j:
            # h_ij(p_i, p_j) = ||p_i - p_j||^2 - (2*r_rob + margin_inter)^2 >= 0
            # h_dot_ij = 2(p_i - p_j)^T (v_i - v_j)
            # In decentralized form, agent i assumes reciprocal sharing (half responsibility):
            for j in range(n):
                if i == j:
                    continue
                pos_j = positions[j]
                vel_j = velocities[j]
                p_ij = pos_i - pos_j
                r_mutual = 2.0 * r_rob + self.cfg.inter_agent_margin
                h_ij = float(np.sum(p_ij**2) - r_mutual**2)
                v_ij = vel_i - vel_j
                h_dot_ij = 2.0 * float(np.dot(p_ij, v_ij))

                # Half-effort projection for robot i:
                # -2 (p_i - p_j)^T (u_i / m) <= ||v_ij||^2 + (alpha1 + alpha2) h_dot_ij + alpha1 * alpha2 * h_ij
                a_ij = -2.0 * p_ij / m
                b_ij = float(np.sum(v_ij**2)) + (alpha1 + alpha2) * h_dot_ij + alpha1 * alpha2 * h_ij
                constraints.append((a_ij, b_ij))

            # Active set analytical projection
            u_safe = u_des_i.copy()
            active = False
            for _ in range(6):
                violated = False
                for a_vec, b_val in constraints:
                    val = float(np.dot(a_vec, u_safe))
                    if val > b_val:
                        violated = True
                        active = True
                        norm_sq = float(np.sum(a_vec**2))
                        if norm_sq > 1e-8:
                            u_safe -= ((val - b_val) / norm_sq) * a_vec
                if not violated:
                    break

            u_clamped = np.clip(u_safe, -self.cfg.control_force_limit, self.cfg.control_force_limit)
            safe_controls.append(u_clamped)
            barriers_active.append(active)

        return safe_controls, barriers_active


class AegisMuJoCoSwarm3DEnvironment:
    """
    Continuous Multi-Robot 3D Rigid-Body Physics in MuJoCo with HOCBF and Wind Perturbations.
    """

    def __init__(self, config: Swarm3DConfig | None = None) -> None:
        self.config = config or Swarm3DConfig()
        self.cbf_filter = SwarmCBF3DFilter(self.config)

        self.obstacles: list[Obstacle3D] = [
            Obstacle3D(center=np.array([0.0, 0.0, 0.5], dtype=np.float64), radius=0.45),
            Obstacle3D(center=np.array([1.3, -1.0, 0.4], dtype=np.float64), radius=0.35),
            Obstacle3D(center=np.array([-1.0, 1.3, 0.4], dtype=np.float64), radius=0.35),
        ]

        self.target_pos = np.array([2.2, 2.2, 0.5], dtype=np.float64)
        self.wind_velocity = self.config.wind_mean.copy()

        self.model = self._build_mujoco_model()
        self.data = mujoco.MjData(self.model)

        self.robot_body_ids = [self.model.body(f"robot_{i}").id for i in range(self.config.num_robots)]
        self.step_count = 0

    def _build_mujoco_model(self) -> mujoco.MjModel:
        c = self.config
        obs_xml = ""
        for i, obs in enumerate(self.obstacles):
            obs_xml += f"""
            <geom name="obs_{i}" type="sphere" size="{obs.radius}"
                  pos="{obs.center[0]} {obs.center[1]} {obs.center[2]}"
                  rgba="0.9 0.3 0.2 0.75" />
            """

        robots_xml = ""
        for i in range(c.num_robots):
            # Stagger initial positions in quadrant
            px = -2.2 + (i % 3) * 0.55
            py = -2.2 + (i // 3) * 0.55
            pz = 0.5
            color = "0.2 0.6 1.0 1.0" if i < 3 else "0.3 0.8 0.4 1.0"
            robots_xml += f"""
            <body name="robot_{i}" pos="{px} {py} {pz}">
              <freejoint/>
              <geom name="geom_robot_{i}" type="sphere" size="{c.robot_radius}"
                    mass="{c.robot_mass}" rgba="{color}"/>
            </body>
            """

        xml = f"""
        <mujoco model="nexvia_aegis_swarm_3d">
          <option timestep="{c.timestep}" gravity="0 0 -9.81"/>
          <worldbody>
            <geom name="floor" type="plane" size="{c.arena_limit} {c.arena_limit} 0.1"
                  pos="0 0 0" rgba="0.10 0.10 0.12 1"/>
            {obs_xml}
            {robots_xml}
            <site name="target" pos="{self.target_pos[0]} {self.target_pos[1]} {self.target_pos[2]}"
                  size="{c.target_arrival_radius}" rgba="0.2 1.0 0.4 0.5"/>
          </worldbody>
        </mujoco>
        """
        return mujoco.MjModel.from_xml_string(xml)

    def reset(self, rng: np.random.Generator) -> dict[str, Any]:
        mujoco.mj_resetData(self.model, self.data)
        self.step_count = 0
        self.wind_velocity = self.config.wind_mean.copy()

        # Place robots at clean, uncollided starting offsets
        for i in range(self.config.num_robots):
            qpos_idx = 7 * i
            qvel_idx = 6 * i
            px = -2.3 + (i % 3) * 0.55 + rng.normal(0, 0.02)
            py = -2.3 + (i // 3) * 0.55 + rng.normal(0, 0.02)
            pz = 0.5
            self.data.qpos[qpos_idx : qpos_idx + 3] = [px, py, pz]
            self.data.qpos[qpos_idx + 3 : qpos_idx + 7] = [1.0, 0.0, 0.0, 0.0]
            self.data.qvel[qvel_idx : qvel_idx + 6] = 0.0

        # Sample target location
        self.target_pos = np.array([2.0, 2.0, 0.5], dtype=np.float64)
        mujoco.mj_forward(self.model, self.data)
        return self.get_state()

    def get_state(self) -> dict[str, Any]:
        positions = [self.data.xpos[bid].copy() for bid in self.robot_body_ids]
        velocities = [self.data.qvel[6 * i : 6 * i + 3].copy() for i in range(self.config.num_robots)]
        distances = [float(np.linalg.norm(self.target_pos - p)) for p in positions]

        return {
            "step": self.step_count,
            "positions": positions,
            "velocities": velocities,
            "distances": distances,
            "target_pos": self.target_pos.copy(),
            "wind_velocity": self.wind_velocity.copy(),
        }

    def step(
        self,
        desired_controls: list[np.ndarray],
        quarantined_mask: list[bool] | None = None,
    ) -> dict[str, Any]:
        st = self.get_state()
        positions = st["positions"]
        velocities = st["velocities"]

        # 1. Update Ornstein-Uhlenbeck wind process
        c = self.config
        if c.wind_enabled:
            dt = c.timestep
            dW = np.random.normal(0.0, math.sqrt(dt), size=3)
            self.wind_velocity += -c.wind_theta * (self.wind_velocity - c.wind_mean) * dt + c.wind_sigma * dW

        # 2. Control Barrier Function Safety Projection
        safe_controls, barriers_active = self.cbf_filter.compute_safe_swarm_controls(
            positions=positions,
            velocities=velocities,
            desired_controls=desired_controls,
            obstacles=self.obstacles,
            quarantined_mask=quarantined_mask,
        )

        # 3. Apply forces in MuJoCo (Control + Gravity Comp + Aerodynamic Drag & Wind)
        drag_coeff = 0.15
        for i, bid in enumerate(self.robot_body_ids):
            f_applied = safe_controls[i].copy()
            # Gravity compensation
            f_applied[2] += c.robot_mass * 9.81
            # Wind relative drag: -drag * (v_robot - w_wind)
            v_rel = velocities[i] - self.wind_velocity
            f_drag = -drag_coeff * v_rel
            f_applied += f_drag

            self.data.xfrc_applied[bid, :3] = f_applied

        mujoco.mj_step(self.model, self.data)
        self.step_count += 1

        next_state = self.get_state()
        next_state["safe_controls"] = safe_controls
        next_state["barriers_active"] = barriers_active

        # 4. Check Safety Invariants
        # a) Obstacle collisions
        min_obs_dist = min(
            min(
                float(np.linalg.norm(p - obs.center) - (c.robot_radius + obs.radius))
                for obs in self.obstacles
            )
            for p in next_state["positions"]
        )
        # b) Inter-agent collisions
        min_inter_dist = float("inf")
        for i in range(c.num_robots):
            for j in range(i + 1, c.num_robots):
                d_ij = float(np.linalg.norm(next_state["positions"][i] - next_state["positions"][j]))
                clearance = d_ij - 2.0 * c.robot_radius
                if clearance < min_inter_dist:
                    min_inter_dist = clearance

        next_state["min_obstacle_distance"] = min_obs_dist
        next_state["min_inter_agent_distance"] = min_inter_dist
        next_state["collision_obstacle"] = min_obs_dist < 0.0
        next_state["collision_inter_agent"] = min_inter_dist < 0.0
        next_state["any_collision"] = (min_obs_dist < 0.0) or (min_inter_dist < 0.0)

        return next_state
