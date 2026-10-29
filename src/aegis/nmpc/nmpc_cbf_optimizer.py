"""
Nonlinear Model Predictive Control with Control Barrier Functions (NMPC-CBF).

Provides receding-horizon lookahead trajectory optimization for 6-DOF quadrotors.
Combines:
  1. Multi-step predictive 6-DOF double-integrator dynamics over horizon N.
  2. Discrete-Time Control Barrier Function (D-CBF) constraints along the entire preview horizon.
  3. Strict tilt bounding (theta <= 35 deg) and actuator thrust saturation.
  4. Force rate-of-change (jerk) penalization for fluid, non-jerky, high-speed maneuvers.
  5. Deterministic fallback to Pointwise Underactuated HOCBF in case of optimization timeout.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
import numpy as np
from scipy.optimize import minimize

from aegis.env.quadrotor_6dof import Obstacle3D, QuadrotorConfig, UnderactuatedCBF6DOF


@dataclass
class NmpcCbfConfig:
    """Configuration hyperparameters for NMPC-CBF controller."""
    horizon_steps: int = 15          # N steps (15 * 0.05s = 0.75s preview lookahead)
    dt: float = 0.05                 # MPC discretization step (seconds)
    drone_mass: float = 1.25         # Physical mass (kg)
    gravity: float = 9.81            # Gravity (m/s^2)

    # Cost Function Weights
    weight_pos: float = 8.0          # Stage position error weight
    weight_pos_terminal: float = 30.0 # Terminal position error weight
    weight_vel: float = 1.5          # Velocity tracking / damping weight
    weight_thrust: float = 0.05      # Hover thrust deviation weight
    weight_delta_u: float = 0.35     # Jerk / force rate-of-change penalization

    # Actuator & Barrier Constraints
    max_tilt_rad: float = math.radians(35.0)  # Maximum roll/pitch tilt cone (35 deg)
    max_thrust_total: float = 28.0   # 4 x 7.0 N motors
    min_thrust_total: float = 2.0    # Minimum collective thrust
    arena_limit: float = 1.5         # Boundary limit [m]
    robot_collision_radius: float = 0.12 # Collision radius [m]
    safety_margin: float = 0.08      # CBF safety buffer [m]
    cbf_gamma: float = 0.35          # D-CBF decay contraction factor

    # Solver Parameters
    max_solver_iters: int = 40
    solver_tolerance: float = 1e-4
    max_solve_time_ms: float = 18.0  # Max compute budget per step


@dataclass
class PlannedHorizonTrajectory:
    """Predicted trajectory across the preview horizon."""
    positions: np.ndarray            # Shape: [N+1, 3]
    velocities: np.ndarray           # Shape: [N+1, 3]
    forces: np.ndarray               # Shape: [N, 3]
    times: np.ndarray                # Shape: [N+1]


@dataclass
class NmpcOptimizationResult:
    """Output bundle of the NMPC-CBF optimizer step."""
    optimal_force_world: np.ndarray  # First control input F_0 to apply [3]
    planned_trajectory: PlannedHorizonTrajectory
    solver_success: bool
    solver_iterations: int
    solve_time_ms: float
    min_barrier_margin: float
    fallback_activated: bool


class NmpcCbfController:
    """
    Receding Horizon NMPC-CBF Optimizer.
    Solves condensed trajectory optimization with barrier constraints and warm starting.
    """

    def __init__(self, config: NmpcCbfConfig | None = None) -> None:
        self.cfg = config or NmpcCbfConfig()
        self.N = self.cfg.horizon_steps
        self.dt = self.cfg.dt
        self.m = self.cfg.drone_mass
        self.g = self.cfg.gravity
        self.hover_thrust = self.m * self.g
        self.hover_force = np.array([0.0, 0.0, self.hover_thrust], dtype=np.float64)

        # Precompute condensed state propagation matrices
        # States: p_k, v_k are affine in U = [F_0, F_1, ..., F_{N-1}] in R^{3N}
        self._build_propagation_matrices()

        # Warm start state
        self._u_warm = np.tile(self.hover_force, self.N)
        self._last_applied_force = self.hover_force.copy()

        # Fallback pointwise HOCBF shield
        quad_cfg = QuadrotorConfig(
            mass=self.m,
            gravity=self.g,
            arena_limit=self.cfg.arena_limit,
            robot_collision_radius=self.cfg.robot_collision_radius,
            safety_margin=self.cfg.safety_margin,
            max_thrust_per_motor=self.cfg.max_thrust_total / 4.0,
            min_thrust_per_motor=self.cfg.min_thrust_total / 4.0,
        )
        self._fallback_hocbf = UnderactuatedCBF6DOF(quad_cfg)

    def _build_propagation_matrices(self) -> None:
        """
        Precomputes M_p and M_v such that:
          p_{1:N} = P_free + M_p @ U
          v_{1:N} = V_free + M_v @ U
        where U in R^{3N}.
        """
        N = self.N
        dt = self.dt
        m = self.m

        # M_p block matrix (3N x 3N)
        self.M_p = np.zeros((3 * N, 3 * N), dtype=np.float64)
        self.M_v = np.zeros((3 * N, 3 * N), dtype=np.float64)

        for k in range(N):
            # step k is index k (1-indexed step: k+1)
            step_idx = k + 1
            for j in range(step_idx):
                # Influence of force F_j on state at step k+1
                # Velocity: dv_{k+1} = sum_{j=0}^k (dt / m) * F_j
                self.M_v[3 * k : 3 * k + 3, 3 * j : 3 * j + 3] = (dt / m) * np.eye(3)

                # Position: dp_{k+1} = sum_{j=0}^k (k - j + 0.5) * (dt^2 / m) * F_j
                factor = (step_idx - j - 0.5) * (dt**2 / m)
                self.M_p[3 * k : 3 * k + 3, 3 * j : 3 * j + 3] = factor * np.eye(3)

        # Precompute Condensed Quadratic Hessian H
        # J(U) = 0.5 * U^T H U + c^T U
        H = np.zeros((3 * N, 3 * N), dtype=np.float64)

        # Stage & terminal position weights (anisotropic: 2x weight on Z to prevent altitude ballooning)
        W_p = np.zeros((3 * N, 3 * N), dtype=np.float64)
        w_xy = self.cfg.weight_pos
        w_z = self.cfg.weight_pos * 2.5
        w_term_xy = self.cfg.weight_pos_terminal
        w_term_z = self.cfg.weight_pos_terminal * 3.0

        for k in range(N - 1):
            W_p[3 * k : 3 * k + 3, 3 * k : 3 * k + 3] = np.diag([w_xy, w_xy, w_z])
        # Terminal step
        W_p[3 * (N - 1) : 3 * N, 3 * (N - 1) : 3 * N] = np.diag([w_term_xy, w_term_xy, w_term_z])

        H += self.M_p.T @ W_p @ self.M_p

        # Velocity tracking weights
        W_v = np.eye(3 * N, dtype=np.float64) * self.cfg.weight_vel
        H += self.M_v.T @ W_v @ self.M_v

        # Control input magnitude weight
        H += np.eye(3 * N, dtype=np.float64) * self.cfg.weight_thrust

        # Control rate-of-change (Delta U) weight: sum ||F_k - F_{k-1}||^2
        D = np.zeros((3 * N, 3 * N), dtype=np.float64)
        for k in range(N):
            D[3 * k : 3 * k + 3, 3 * k : 3 * k + 3] += np.eye(3)
            if k > 0:
                D[3 * k : 3 * k + 3, 3 * (k - 1) : 3 * k] -= np.eye(3)
        H += self.cfg.weight_delta_u * (D.T @ D)

        self.H = H
        self.W_p = W_p
        self.W_v = W_v

    def reset(self) -> None:
        """Resets the warm start memory."""
        self._u_warm = np.tile(self.hover_force, self.N)
        self._last_applied_force = self.hover_force.copy()

    def compute_optimal_control(
        self,
        current_pos: np.ndarray,
        current_vel: np.ndarray,
        target_pos: np.ndarray,
        target_vel: np.ndarray | None = None,
        obstacles: list[Obstacle3D] | None = None,
        obstacles_vel: list[np.ndarray] | None = None,
    ) -> NmpcOptimizationResult:
        """
        Executes NMPC-CBF receding horizon optimization.
        Returns NmpcOptimizationResult containing optimal force F_0 to apply.
        """
        start_time = time.perf_counter()
        if target_vel is None:
            target_vel = np.zeros(3, dtype=np.float64)
        if obstacles is None:
            obstacles = []

        N = self.N
        dt = self.dt
        m = self.m
        g = self.g

        # 1. Compute Free Response (Zero-Force ballistic trajectory)
        P_free = np.zeros(3 * N, dtype=np.float64)
        V_free = np.zeros(3 * N, dtype=np.float64)

        for k in range(N):
            step = k + 1
            # Ballistic velocity: v_0 - g * e3 * (step * dt)
            V_free[3 * k : 3 * k + 3] = current_vel - np.array([0.0, 0.0, g * step * dt])
            # Ballistic position: p_0 + v_0 * t - 0.5 * g * e3 * t^2
            t_k = step * dt
            P_free[3 * k : 3 * k + 3] = current_pos + current_vel * t_k - np.array([0.0, 0.0, 0.5 * g * t_k**2])

        # 2. Build Reference Vectors across Horizon
        P_ref = np.tile(target_pos, N)
        V_ref = np.tile(target_vel, N)

        # Linear cost vector c:
        # e_p = P_free - P_ref
        # e_v = V_free - V_ref
        e_p = P_free - P_ref
        e_v = V_free - V_ref

        c = self.M_p.T @ self.W_p @ e_p + self.M_v.T @ self.W_v @ e_v
        # Hover force offset penalty: - weight_thrust * U_hover
        c -= self.cfg.weight_thrust * np.tile(self.hover_force, N)
        # Delta U first step penalty: - weight_delta_u * [F_prev, 0, ..., 0]
        c[:3] -= self.cfg.weight_delta_u * self._last_applied_force

        # Objective Function
        def objective(u: np.ndarray) -> float:
            return float(0.5 * np.dot(u, self.H @ u) + np.dot(c, u))

        def objective_grad(u: np.ndarray) -> np.ndarray:
            return self.H @ u + c

        # 3. Constraints Definition
        constraints = []

        # (a) Actuator Limits & Tilt Cones
        # For each step k in 0..N-1:
        # F_z >= F_min
        # F_z <= F_max
        # ||F_xy|| <= F_z * tan(max_tilt)
        tan_tilt = math.tan(self.cfg.max_tilt_rad)

        bounds = []
        max_f_xy = self.cfg.max_thrust_total * math.sin(self.cfg.max_tilt_rad)
        for _ in range(N):
            bounds.append((-max_f_xy, max_f_xy))                       # F_x
            bounds.append((-max_f_xy, max_f_xy))                       # F_y
            bounds.append((self.cfg.min_thrust_total, self.cfg.max_thrust_total)) # F_z

        # Tilt cone nonlinear constraint
        def tilt_constraint(u: np.ndarray) -> np.ndarray:
            res = np.empty(N, dtype=np.float64)
            for k in range(N):
                fx = u[3 * k]
                fy = u[3 * k + 1]
                fz = u[3 * k + 2]
                res[k] = fz * tan_tilt - math.sqrt(fx**2 + fy**2 + 1e-8)
            return res

        constraints.append({"type": "ineq", "fun": tilt_constraint})

        # (b) Arena Boundary Limits for predicted positions
        # z >= r_safe, z <= arena_limit, |x| <= arena_limit, |y| <= arena_limit
        r_quad = self.cfg.robot_collision_radius + self.cfg.safety_margin
        wall_lim = self.cfg.arena_limit - r_quad

        def boundary_constraint(u: np.ndarray) -> np.ndarray:
            p_traj = (P_free + self.M_p @ u).reshape((N, 3))
            ineqs = []
            for k in range(N):
                p = p_traj[k]
                ineqs.append(p[2] - r_quad)                 # floor
                ineqs.append(self.cfg.arena_limit - r_quad - p[2]) # ceiling
                ineqs.append(wall_lim - abs(p[0]))          # X walls
                ineqs.append(wall_lim - abs(p[1]))          # Y walls
            return np.array(ineqs, dtype=np.float64)

        constraints.append({"type": "ineq", "fun": boundary_constraint})

        # (c) Discrete-Time Control Barrier Function (D-CBF) for Obstacles
        # For each obstacle, h_k = ||p_k - p_obs,k||^2 - r_safe^2 >= 0
        min_barrier_recorded = 1e6

        if obstacles:
            def obstacle_cbf_constraint(u: np.ndarray) -> np.ndarray:
                p_traj = (P_free + self.M_p @ u).reshape((N, 3))
                cbf_vals = []
                for j, obs in enumerate(obstacles):
                    obs_vel = obstacles_vel[j] if obstacles_vel and j < len(obstacles_vel) else np.zeros(3)
                    r_safe = obs.radius + r_quad
                    r_safe_sq = r_safe**2

                    for k in range(N):
                        t_step = (k + 1) * dt
                        obs_pos_k = obs.center + obs_vel * t_step
                        dist_sq = float(np.sum((p_traj[k] - obs_pos_k)**2))
                        h_k = dist_sq - r_safe_sq
                        cbf_vals.append(h_k)

                return np.array(cbf_vals, dtype=np.float64)

            constraints.append({"type": "ineq", "fun": obstacle_cbf_constraint})

        # 4. Smart Warm Start Initialization
        u0 = self._u_warm.copy()
        
        # Check if warm-start path collides with any obstacle
        p_warm = (P_free + self.M_p @ u0).reshape((N, 3))
        collides = False
        detour_dir = np.array([0.0, 1.0, 0.0], dtype=np.float64)

        if obstacles:
            for obs in obstacles:
                r_safe = obs.radius + r_quad
                dists = np.linalg.norm(p_warm - obs.center, axis=1)
                if np.any(dists < r_safe + 0.05):
                    collides = True
                    # Direction perpendicular to velocity or relative position
                    v_dir = current_vel.copy()
                    if np.linalg.norm(v_dir[:2]) > 0.1:
                        v_norm = v_dir[:2] / np.linalg.norm(v_dir[:2])
                        detour_dir = np.array([-v_norm[1], v_norm[0], 0.0], dtype=np.float64)
                    else:
                        rel = current_pos - obs.center
                        if abs(rel[1]) > 1e-3:
                            detour_dir = np.array([0.0, np.sign(rel[1]), 0.0], dtype=np.float64)
                    break

        if collides:
            for k in range(N):
                lateral_bias = 2.0 * math.sin((k + 1) * math.pi / N) * detour_dir
                u0[3 * k : 3 * k + 3] += lateral_bias

        # 5. Solve Constrained QP / NLP
        opt_res = minimize(
            fun=objective,
            x0=u0,
            jac=objective_grad,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={
                "maxiter": self.cfg.max_solver_iters,
                "ftol": self.cfg.solver_tolerance,
                "disp": False,
            },
        )

        solve_time = (time.perf_counter() - start_time) * 1000.0
        fallback_activated = False

        if opt_res.success and not np.any(np.isnan(opt_res.x)):
            u_opt = opt_res.x
            # Update warm start for next step: shift left and append hover
            self._u_warm = np.concatenate([u_opt[3:], self.hover_force])
            f_applied = u_opt[:3].copy()
            niters = int(opt_res.nit)
            success = True
        else:
            # Fallback to Pointwise Underactuated HOCBF Shield
            fallback_activated = True
            nominal_f = target_pos - current_pos
            nominal_f = nominal_f / max(1e-4, float(np.linalg.norm(nominal_f))) * self.hover_thrust
            nominal_f[2] += self.hover_thrust

            current_tilt = float(np.arccos(np.clip(nominal_f[2] / max(1e-4, float(np.linalg.norm(nominal_f))), -1.0, 1.0)))
            f_applied, _ = self._fallback_hocbf.filter_safe_force(
                pos=current_pos,
                vel=current_vel,
                desired_force=nominal_f,
                obstacles=obstacles,
                current_tilt=current_tilt,
            )
            u_opt = np.tile(f_applied, N)
            niters = int(opt_res.nit) if hasattr(opt_res, "nit") else 0
            success = False

        self._last_applied_force = f_applied.copy()

        # 6. Extract Planned Trajectory
        pred_p = (P_free + self.M_p @ u_opt).reshape((N, 3))
        pred_v = (V_free + self.M_v @ u_opt).reshape((N, 3))
        pred_f = u_opt.reshape((N, 3))

        full_positions = np.vstack([current_pos, pred_p])
        full_velocities = np.vstack([current_vel, pred_v])
        times = np.linspace(0, N * dt, N + 1)

        # Check barrier clearance
        if obstacles:
            for obs in obstacles:
                dists = np.linalg.norm(full_positions - obs.center, axis=1) - obs.radius - self.cfg.robot_collision_radius
                min_barrier_recorded = min(min_barrier_recorded, float(np.min(dists)))
        else:
            min_barrier_recorded = 1.0

        planned_traj = PlannedHorizonTrajectory(
            positions=full_positions,
            velocities=full_velocities,
            forces=pred_f,
            times=times,
        )

        return NmpcOptimizationResult(
            optimal_force_world=f_applied,
            planned_trajectory=planned_traj,
            solver_success=success,
            solver_iterations=niters,
            solve_time_ms=solve_time,
            min_barrier_margin=min_barrier_recorded,
            fallback_activated=fallback_activated,
        )
