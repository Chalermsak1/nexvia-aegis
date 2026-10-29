"""
NEXVIA AEGIS — Physical AI: 3D Continuous MuJoCo Simulation with Control Barrier Functions (CBF).

Integrates:
1. Continuous 3D rigid-body dynamics in MuJoCo with full 6-DOF translation and rotation.
2. High-order CBF-inspired constraints for monitored safe-set control:
   - Arena boundary containment barriers
   - 3D spherical obstacle avoidance barriers
3. Iterative halfspace projection with an exact active-set fallback for
   residuals. Infeasible states are reported; no forward-invariance proof is claimed.
4. Martingale-Gated Safety Overrides:
   - When Ville e-process monitor triggers alarm, the desired action is
     dissipative braking before the same CBF feasibility checks are applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any
import math
import numpy as np
import mujoco


@dataclass(frozen=True)
class Obstacle3D:
    """3D spherical obstacle specification."""
    center: np.ndarray  # shape (3,)
    radius: float       # meters


@dataclass(frozen=True)
class PhysicalWorld3DConfig:
    timestep: float = 0.02
    robot_mass: float = 1.0
    robot_radius: float = 0.20
    arena_limit: float = 3.0  # [-3, 3] in X, Y; [0.2, 3.0] in Z
    control_force_limit: float = 2.0  # Newtons
    cbf_gamma: float = 2.5     # CBF decay rate parameter
    safety_margin: float = 0.15 # meters buffer around obstacles
    success_radius: float = 0.25 # arrival tolerance


class ControlBarrierFilter3D:
    """
    High-Order Control Barrier Function (HOCBF) Safety Filter for 3D continuous double-integrator dynamics:
        p_dot = v
        v_dot = (1/m) * u

    Approximates the QP at each time step:
        min_u ||u - u_des||^2
        s.t.  a_i^T u <= b_i for all barriers i
    """

    def __init__(
        self,
        mass: float = 1.0,
        robot_radius: float = 0.20,
        arena_limit: float = 3.0,
        force_limit: float = 2.0,
        gamma: float = 2.5,
        safety_margin: float = 0.15,
    ) -> None:
        if not all(math.isfinite(v) for v in (mass, robot_radius, arena_limit, force_limit, gamma, safety_margin)):
            raise ValueError("CBF physical parameters must be finite")
        if mass <= 0 or force_limit <= 0 or gamma <= 0:
            raise ValueError("CBF mass, force limit, and gamma must be positive")
        self.mass = mass
        self.robot_radius = robot_radius
        self.arena_limit = arena_limit
        self.force_limit = force_limit
        self.gamma = gamma
        self.safety_margin = safety_margin
        self.last_constraint_residual: float | None = None
        self.last_qp_feasible: bool | None = None
        self.last_projection_method: str = "NOT_RUN"

    def _exact_feasible_projection(
        self,
        desired: np.ndarray,
        constraints: list[tuple[np.ndarray, float]],
    ) -> np.ndarray | None:
        """Project onto a feasible 3D polytope by enumerating up to 3 active planes.

        Called only when the fast iterative projection leaves a residual. Box
        bounds are included. If the intersection is empty, return None rather
        than labeling a clipped command as CBF-valid.
        """
        bounded = list(constraints)
        for axis in range(3):
            normal = np.zeros(3, dtype=np.float64)
            normal[axis] = 1.0
            bounded.append((normal, self.force_limit))
            bounded.append((-normal, self.force_limit))
        normals = np.asarray([item[0] for item in bounded], dtype=np.float64)
        bounds = np.asarray([item[1] for item in bounded], dtype=np.float64)
        tolerance = 1e-8

        # A single halfspace that excludes the entire actuator box proves
        # infeasibility and avoids expensive active-set enumeration.
        box_minimum = -self.force_limit * np.sum(np.abs(normals), axis=1)
        if np.any(box_minimum > bounds + tolerance):
            return None

        best: np.ndarray | None = None
        best_cost = math.inf
        for count in (0, 1, 2, 3):
            for active in combinations(range(len(bounded)), count):
                if count:
                    active_normals = normals[list(active)]
                    active_bounds = bounds[list(active)]
                    gram = active_normals @ active_normals.T
                    try:
                        multiplier = np.linalg.solve(
                            gram, active_normals @ desired - active_bounds
                        )
                    except np.linalg.LinAlgError:
                        continue
                    candidate = desired - active_normals.T @ multiplier
                else:
                    candidate = desired
                if not np.all(np.isfinite(candidate)):
                    continue
                if np.any(normals @ candidate > bounds + tolerance):
                    continue
                cost = float(np.sum((candidate - desired) ** 2))
                if cost < best_cost:
                    best, best_cost = candidate.copy(), cost
        return best

    def compute_safe_control(
        self,
        pos: np.ndarray,
        vel: np.ndarray,
        desired_u: np.ndarray,
        obstacles: list[Obstacle3D],
        force_braking: bool = False,
    ) -> tuple[np.ndarray, bool]:
        """
        Filters desired_u through the CBF constraints.
        Returns: (safe_u, barrier_active)
        """
        u_des = np.clip(desired_u, -self.force_limit, self.force_limit).astype(np.float64)

        if force_braking:
            # Use dissipative braking as the desired action, then pass it
            # through the same actuator-bounded CBF projection as navigation.
            speed = float(np.linalg.norm(vel))
            if speed > 1e-4:
                brake_dir = -vel / speed
                u_des = brake_dir * min(self.force_limit, 2.0 * self.mass * speed)
            else:
                u_des = np.zeros(3, dtype=np.float64)

        constraints: list[tuple[np.ndarray, float]] = []
        max_accel = self.force_limit / self.mass

        def add_stopping_envelope(distance: float, outward_speed: float, outward_axis: np.ndarray) -> None:
            """Brake before the distance needed for a full-force stop is exhausted."""
            if outward_speed <= 1e-8:
                return
            stopping_slack = distance - outward_speed**2 / (2.0 * max_accel)
            a_vec = outward_axis * (outward_speed / (max_accel * self.mass))
            b_val = self.gamma * stopping_slack - outward_speed
            constraints.append((a_vec, b_val))

        # 1. Obstacle Avoidance Barriers
        # Barrier function: h(x) = ||p - p_obs||^2 - (r_rob + r_obs + margin)^2 >= 0
        # h_dot = 2 (p - p_obs)^T v
        # B(x) = h_dot + alpha1 * h >= 0
        # B_dot = 2 ||v||^2 + 2(p - p_obs)^T (u/m) + alpha1 * h_dot
        # Constraint: B_dot + alpha2 * B >= 0
        #   ==> -2(p - p_obs)^T u / m <= 2 ||v||^2 + (alpha1 + alpha2) h_dot + alpha1 * alpha2 * h
        alpha1 = self.gamma
        alpha2 = self.gamma

        for obs in obstacles:
            p_rel = pos - obs.center
            r_safe = self.robot_radius + obs.radius + self.safety_margin
            h_val = float(np.sum(p_rel**2) - r_safe**2)
            h_dot = 2.0 * float(np.dot(p_rel, vel))

            # a^T u <= b
            # a = -2 * p_rel / m
            # b = 2 * ||v||^2 + (alpha1 + alpha2) * h_dot + alpha1 * alpha2 * h_val
            a_vec = -2.0 * p_rel / self.mass
            b_val = 2.0 * float(np.sum(vel**2)) + (alpha1 + alpha2) * h_dot + alpha1 * alpha2 * h_val
            constraints.append((a_vec, b_val))

        # 2. Arena Boundary Limits (Floor and Walls)
        # Floor: z >= r_rob + margin  ==> h_z(z) = z - (r_rob + margin) >= 0
        z_floor = self.robot_radius + self.safety_margin
        h_floor = pos[2] - z_floor
        h_dot_floor = vel[2]
        a_floor = np.array([0.0, 0.0, -1.0 / self.mass], dtype=np.float64)
        b_floor = (alpha1 + alpha2) * h_dot_floor + alpha1 * alpha2 * h_floor
        constraints.append((a_floor, b_floor))
        add_stopping_envelope(h_floor, -vel[2], np.array([0.0, 0.0, -1.0]))

        # Upper Z boundary, matching the documented 3D arena envelope.
        z_ceiling = self.arena_limit - self.robot_radius - self.safety_margin
        h_ceiling = z_ceiling - pos[2]
        a_ceiling = np.array([0.0, 0.0, 1.0 / self.mass], dtype=np.float64)
        b_ceiling = -(alpha1 + alpha2) * vel[2] + alpha1 * alpha2 * h_ceiling
        constraints.append((a_ceiling, b_ceiling))
        add_stopping_envelope(h_ceiling, vel[2], np.array([0.0, 0.0, 1.0]))

        # Horizontal walls: |x| <= arena_limit - margin, |y| <= arena_limit - margin
        for axis in (0, 1):
            wall_lim = self.arena_limit - self.robot_radius - self.safety_margin
            # Positive wall: (wall_lim - pos[axis]) >= 0
            h_w_pos = wall_lim - pos[axis]
            h_dot_w_pos = -vel[axis]
            a_w_pos = np.zeros(3, dtype=np.float64)
            a_w_pos[axis] = 1.0 / self.mass
            b_w_pos = (alpha1 + alpha2) * h_dot_w_pos + alpha1 * alpha2 * h_w_pos
            constraints.append((a_w_pos, b_w_pos))
            outward_pos = np.zeros(3, dtype=np.float64)
            outward_pos[axis] = 1.0
            add_stopping_envelope(h_w_pos, vel[axis], outward_pos)

            # Negative wall: (pos[axis] + wall_lim) >= 0
            h_w_neg = pos[axis] + wall_lim
            h_dot_w_neg = vel[axis]
            a_w_neg = np.zeros(3, dtype=np.float64)
            a_w_neg[axis] = -1.0 / self.mass
            b_w_neg = (alpha1 + alpha2) * h_dot_w_neg + alpha1 * alpha2 * h_w_neg
            constraints.append((a_w_neg, b_w_neg))
            add_stopping_envelope(h_w_neg, -vel[axis], -outward_pos)

        # Active set projection / analytical iterative clipping for 3D QP
        u_safe = u_des.copy()
        barrier_active = force_braking

        for _ in range(5):  # multiple constraint resolution passes
            violated = False
            for a_vec, b_val in constraints:
                val = float(np.dot(a_vec, u_safe))
                if val > b_val:
                    violated = True
                    barrier_active = True
                    # Orthogonal projection onto halfspace: u_new = u - (val - b) / ||a||^2 * a
                    norm_sq = float(np.sum(a_vec**2))
                    if norm_sq > 1e-8:
                        u_safe -= ((val - b_val) / norm_sq) * a_vec
            if not violated:
                break

        # Hard physical actuator box constraints
        u_final = np.clip(u_safe, -self.force_limit, self.force_limit)
        self.last_constraint_residual = max(
            (max(0.0, float(np.dot(a_vec, u_final) - b_val)) for a_vec, b_val in constraints),
            default=0.0,
        )
        if self.last_constraint_residual > 1e-8:
            exact = self._exact_feasible_projection(u_des, constraints)
            if exact is None:
                self.last_qp_feasible = False
                self.last_projection_method = "INFEASIBLE_WITHIN_ACTUATOR_BOX"
            else:
                u_final = exact
                self.last_constraint_residual = max(
                    (max(0.0, float(np.dot(a_vec, u_final) - b_val))
                     for a_vec, b_val in constraints),
                    default=0.0,
                )
                self.last_qp_feasible = self.last_constraint_residual <= 1e-8
                self.last_projection_method = "EXACT_ACTIVE_SET"
        else:
            self.last_qp_feasible = True
            self.last_projection_method = "ITERATIVE_FEASIBLE"
        return u_final, barrier_active


class AegisMuJoCo3DEnvironment:
    """
    Continuous 3D Rigid-Body Physics Environment in MuJoCo with Control Barrier Functions (CBF).
    """

    def __init__(self, config: PhysicalWorld3DConfig | None = None) -> None:
        self.config = config or PhysicalWorld3DConfig()
        self.cbf = ControlBarrierFilter3D(
            mass=self.config.robot_mass,
            robot_radius=self.config.robot_radius,
            arena_limit=self.config.arena_limit,
            force_limit=self.config.control_force_limit,
            gamma=self.config.cbf_gamma,
            safety_margin=self.config.safety_margin,
        )

        self.obstacles: list[Obstacle3D] = [
            Obstacle3D(center=np.array([0.0, 0.0, 0.5], dtype=np.float64), radius=0.45),
            Obstacle3D(center=np.array([1.2, -1.0, 0.4], dtype=np.float64), radius=0.35),
            Obstacle3D(center=np.array([-1.0, 1.2, 0.4], dtype=np.float64), radius=0.35),
        ]

        self.model = self._build_mujoco_model()
        self.data = mujoco.MjData(self.model)
        self.robot_body_id = self.model.body("robot").id
        self.robot_geom_id = self.model.geom("robot_geom").id
        self.obstacle_geom_ids = {self.model.geom(f"obs_{i}").id for i in range(len(self.obstacles))}
        self.floor_geom_id = self.model.geom("floor").id

        self.step_count = 0
        self.target_pos = np.array([2.0, 2.0, 0.5], dtype=np.float64)

    def _build_mujoco_model(self) -> mujoco.MjModel:
        c = self.config
        obs_xml = ""
        for i, obs in enumerate(self.obstacles):
            obs_xml += f"""
            <geom name="obs_{i}" type="sphere" size="{obs.radius}"
                  pos="{obs.center[0]} {obs.center[1]} {obs.center[2]}"
                  rgba="0.9 0.3 0.2 0.8" />
            """

        xml = f"""
        <mujoco model="nexvia_aegis_3d_cbf">
          <option timestep="{c.timestep}" gravity="0 0 -9.81"/>
          <worldbody>
            <geom name="floor" type="plane" size="{c.arena_limit} {c.arena_limit} 0.1"
                  pos="0 0 0" rgba="0.12 0.12 0.15 1"/>
            {obs_xml}
            <body name="robot" pos="-2.0 -2.0 0.5">
              <freejoint/>
              <geom name="robot_geom" type="sphere" size="{c.robot_radius}"
                    mass="{c.robot_mass}" rgba="0.2 0.6 1.0 1.0"/>
            </body>
            <site name="target" pos="2.0 2.0 0.5" size="{c.success_radius}"
                  rgba="0.2 1.0 0.4 0.5"/>
          </worldbody>
        </mujoco>
        """
        return mujoco.MjModel.from_xml_string(xml)

    def reset(self, rng: np.random.Generator) -> dict[str, Any]:
        mujoco.mj_resetData(self.model, self.data)
        self.step_count = 0

        # Initial robot position in safe quadrant
        init_pos = np.array([-2.0, -2.0, 0.5], dtype=np.float64)
        self.data.qpos[:3] = init_pos
        self.data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
        self.data.qvel[:] = 0.0

        # Sample 3D target position away from obstacles
        for _ in range(50):
            cand_target = np.array([
                rng.uniform(-2.5, 2.5),
                rng.uniform(-2.5, 2.5),
                rng.uniform(0.3, 1.5),
            ], dtype=np.float64)
            # Ensure target is not inside an obstacle
            if all(np.linalg.norm(cand_target - obs.center) > obs.radius + 0.30 for obs in self.obstacles):
                self.target_pos = cand_target
                break

        mujoco.mj_forward(self.model, self.data)
        return self.get_state()

    def get_state(self) -> dict[str, Any]:
        pos = self.data.xpos[self.robot_body_id].copy()
        vel = self.data.qvel[:3].copy()
        dist = float(np.linalg.norm(self.target_pos - pos))
        min_obs_dist = min(
            float(np.linalg.norm(pos - obs.center) - (self.config.robot_radius + obs.radius))
            for obs in self.obstacles
        ) if self.obstacles else math.inf
        wall_limit = self.config.arena_limit - self.config.robot_radius
        boundary_clearance = min(
            pos[2] - self.config.robot_radius,
            self.config.arena_limit - self.config.robot_radius - pos[2],
            wall_limit - abs(pos[0]),
            wall_limit - abs(pos[1]),
        )
        contact_obstacle = False
        contact_floor = False
        for contact in self.data.contact[: self.data.ncon]:
            pair = {int(contact.geom1), int(contact.geom2)}
            if self.robot_geom_id in pair:
                contact_obstacle |= bool(pair & self.obstacle_geom_ids)
                contact_floor |= self.floor_geom_id in pair
        return {
            "robot_pos": pos,
            "robot_velocity": vel,
            "target_pos": self.target_pos.copy(),
            "distance": dist,
            "step": self.step_count,
            "min_obstacle_distance": min_obs_dist,
            "boundary_clearance": float(boundary_clearance),
            "contact_obstacle": contact_obstacle,
            "contact_floor": contact_floor,
            "safety_violation": bool(
                min_obs_dist < 0.0 or boundary_clearance < 0.0
                or contact_obstacle or contact_floor
            ),
        }

    def step(self, desired_control: np.ndarray, force_braking: bool = False) -> dict[str, Any]:
        pos = self.data.xpos[self.robot_body_id].copy()
        vel = self.data.qvel[:3].copy()

        # Apply Control Barrier Function (CBF) filter
        safe_action, barrier_active = self.cbf.compute_safe_control(
            pos=pos,
            vel=vel,
            desired_u=desired_control,
            obstacles=self.obstacles,
            force_braking=force_braking,
        )

        # Apply force in 3D (including gravity compensation to hover/fly or roll smoothly)
        f_total = safe_action.copy()
        f_total[2] += self.config.robot_mass * 9.81  # gravity compensation for 3D aerial/levitation regime

        self.data.xfrc_applied[self.robot_body_id, :3] = f_total
        mujoco.mj_step(self.model, self.data)
        self.step_count += 1

        state = self.get_state()
        state["safe_action"] = safe_action
        state["barrier_active"] = barrier_active
        state["cbf_constraint_residual"] = self.cbf.last_constraint_residual
        state["cbf_qp_feasible"] = self.cbf.last_qp_feasible
        state["cbf_projection_method"] = self.cbf.last_projection_method
        state["cbf_constraints_satisfied"] = (
            self.cbf.last_constraint_residual is not None
            and self.cbf.last_constraint_residual <= 1e-8
        )
        return state
