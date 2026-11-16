"""
NEXVIA AEGIS — Differentiable Implicit-KKT Safe RL Layer.

Implements an end-to-end differentiable Quadratic Program (QP) layer using
the Implicit Function Theorem on the Karush-Kuhn-Tucker (KKT) conditions:

    u_safe* = argmin_{u} 1/2 ||u - u_nom||^2
              s.t.  A u <= b

At the optimal solution with active constraints A_act u* = b_act (lambda_act > 0):
    [ I       A_act^T ] [ du*      ] = [ du_nom ]
    [ A_act   0       ] [ dlambda  ]   [ db_act - dA_act u* ]

This yields the exact analytical sensitivity Jacobian:
    d u_safe* / d u_nom = I - A_act^T (A_act A_act^T)^(-1) A_act = P

During backpropagation, upstream loss gradients grad_u* flow backward to the
nominal neural policy parameters theta via:
    grad_u_nom = P @ grad_u*
    grad_b_act = (A_act A_act^T)^(-1) A_act @ grad_u*
    grad_A_act = -grad_b_act @ u*^T - lambda_act @ (grad_u* - A_act^T @ grad_b_act)^T

This breaks the gradient bottleneck in Safe RL, enabling Actor policy networks
to receive smooth sensitivity signals directly through the CLBF-CBF safety envelope.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Tuple

import numpy as np
import torch
import torch.nn as nn


class DifferentiableSafeQPLayer(torch.autograd.Function):
    """
    Differentiable QP Safety Projection Layer via Implicit KKT Sensitivity.

    Supports both unbatched (u_nom: (m,), A: (K, m), b: (K,)) and
    batched (u_nom: (B, m), A: (B, K, m) or (K, m), b: (B, K) or (K,)) inputs.
    """

    @staticmethod
    def forward(
        ctx: Any,
        u_nom: torch.Tensor,
        A: torch.Tensor,
        b: torch.Tensor,
        eps_damping: float = 1e-8,
        tol_primal: float = 1e-5,
    ) -> torch.Tensor:
        """
        Solves active-set QP and computes sensitivity projection matrix P.
        """
        is_batched = u_nom.dim() == 2
        orig_A_dim = A.dim()
        orig_b_dim = b.dim()

        if not is_batched:
            u_nom_batch = u_nom.unsqueeze(0)
            A_batch = A.unsqueeze(0) if orig_A_dim == 2 else A
            b_batch = b.unsqueeze(0) if orig_b_dim == 1 else b
        else:
            u_nom_batch = u_nom
            batch_size = u_nom.shape[0]
            if orig_A_dim == 2:
                A_batch = A.unsqueeze(0).expand(batch_size, -1, -1)
            else:
                A_batch = A
            if orig_b_dim == 1:
                b_batch = b.unsqueeze(0).expand(batch_size, -1)
            else:
                b_batch = b

        batch_size, m = u_nom_batch.shape
        _, K, _ = A_batch.shape
        device = u_nom.device
        dtype = u_nom.dtype

        u_star_list = []
        P_list = []
        A_act_list = []
        lam_list = []
        active_idx_list = []

        for b_idx in range(batch_size):
            u_i = u_nom_batch[b_idx]
            A_i = A_batch[b_idx]
            b_i = b_batch[b_idx]

            # 1. Check if u_nom is already strictly feasible
            viol = A_i @ u_i - b_i
            if torch.all(viol <= tol_primal):
                # No active constraints
                P_i = torch.eye(m, dtype=dtype, device=device)
                u_star_list.append(u_i.clone())
                P_list.append(P_i)
                A_act_list.append(torch.empty((0, m), dtype=dtype, device=device))
                lam_list.append(torch.empty((0,), dtype=dtype, device=device))
                active_idx_list.append(torch.empty((0,), dtype=torch.long, device=device))
                continue

            # 2. Active-set combinatorial search for m <= 3 (exact, fast, robust)
            candidate_indices = torch.where(viol > -tol_primal)[0].tolist()
            if len(candidate_indices) == 0:
                candidate_indices = list(range(K))

            best_u = None
            best_cost = float("inf")
            best_active = None
            best_lam = None
            best_P = None
            best_A_act = None

            # Test active combinations of size 1, 2, ..., min(m, len(candidate_indices))
            max_act = min(m, len(candidate_indices))
            for k in range(1, max_act + 1):
                for combo in combinations(candidate_indices, k):
                    idx = torch.tensor(combo, dtype=torch.long, device=device)
                    A_c = A_i[idx]
                    b_c = b_i[idx]

                    # Gram matrix
                    Gram = A_c @ A_c.T
                    if torch.linalg.matrix_rank(Gram) < len(idx):
                        continue

                    damped_Gram = Gram + eps_damping * torch.eye(len(idx), dtype=dtype, device=device)
                    try:
                        inv_Gram = torch.linalg.inv(damped_Gram)
                    except torch.linalg.LinAlgError:
                        continue

                    # Dual multipliers: lam = (A_c A_c^T)^(-1) (A_c u_nom - b_c)
                    lam_c = inv_Gram @ (A_c @ u_i - b_c)
                    if torch.any(lam_c < -1e-6):
                        # Violates dual positivity condition
                        continue

                    u_cand = u_i - A_c.T @ lam_c

                    # Check primal feasibility across all constraints
                    if torch.any(A_i @ u_cand > b_i + 1e-4):
                        continue

                    cost = float(torch.sum((u_cand - u_i) ** 2).item())
                    if cost < best_cost:
                        best_cost = cost
                        best_u = u_cand
                        best_active = idx
                        best_lam = lam_c
                        best_A_act = A_c
                        best_P = torch.eye(m, dtype=dtype, device=device) - A_c.T @ inv_Gram @ A_c

            if best_u is None:
                # Fallback: project onto most violated single constraint
                max_viol_idx = torch.argmax(viol)
                idx = torch.tensor([max_viol_idx], dtype=torch.long, device=device)
                A_c = A_i[idx]
                b_c = b_i[idx]
                denom = torch.dot(A_c[0], A_c[0]) + eps_damping
                lam_c = (torch.dot(A_c[0], u_i) - b_c) / denom
                best_u = u_i - (A_c.T @ lam_c).view(m)
                best_active = idx
                best_lam = lam_c
                best_A_act = A_c
                best_P = torch.eye(m, dtype=dtype, device=device) - (A_c.T @ A_c) / denom

            u_star_list.append(best_u)
            P_list.append(best_P)
            A_act_list.append(best_A_act)
            lam_list.append(best_lam)
            active_idx_list.append(best_active)

        u_star_out = torch.stack(u_star_list, dim=0)

        # Context saving for backward pass
        ctx.save_for_backward(u_nom_batch, A_batch, b_batch)
        ctx.u_star_batch = u_star_out
        ctx.P_batch = P_list
        ctx.A_act_batch = A_act_list
        ctx.lam_batch = lam_list
        ctx.active_idx_batch = active_idx_list
        ctx.is_batched = is_batched
        ctx.orig_A_dim = orig_A_dim
        ctx.orig_b_dim = orig_b_dim
        ctx.eps_damping = eps_damping

        if not is_batched:
            return u_star_out.squeeze(0)
        return u_star_out

    @staticmethod
    def backward(ctx: Any, grad_u_star: torch.Tensor) -> tuple[torch.Tensor | None, torch.Tensor | None, torch.Tensor | None, None, None]:
        """
        Analytic KKT sensitivity backpropagation.
        """
        u_nom_batch, A_batch, b_batch = ctx.saved_tensors
        is_batched = ctx.is_batched
        orig_A_dim = ctx.orig_A_dim
        orig_b_dim = ctx.orig_b_dim
        eps_damping = ctx.eps_damping

        if not is_batched:
            grad_u_star_batch = grad_u_star.unsqueeze(0)
        else:
            grad_u_star_batch = grad_u_star

        batch_size, m = u_nom_batch.shape
        _, K, _ = A_batch.shape
        device = u_nom_batch.device
        dtype = u_nom_batch.dtype

        grad_u_nom_list = []
        grad_A_list = []
        grad_b_list = []

        for b_idx in range(batch_size):
            g_i = grad_u_star_batch[b_idx]
            u_star_i = ctx.u_star_batch[b_idx]
            P_i = ctx.P_batch[b_idx]
            A_act_i = ctx.A_act_batch[b_idx]
            lam_i = ctx.lam_batch[b_idx]
            act_idx_i = ctx.active_idx_batch[b_idx]

            # 1. Gradient w.r.t nominal action u_nom: P @ grad_u*
            grad_u_nom_i = P_i @ g_i
            grad_u_nom_list.append(grad_u_nom_i)

            grad_A_i = torch.zeros((K, m), dtype=dtype, device=device)
            grad_b_i = torch.zeros((K,), dtype=dtype, device=device)

            if len(act_idx_i) > 0:
                k_act = len(act_idx_i)
                Gram = A_act_i @ A_act_i.T + eps_damping * torch.eye(k_act, dtype=dtype, device=device)
                inv_Gram = torch.linalg.inv(Gram)

                # w2 = (A_act A_act^T)^(-1) A_act @ grad_u*
                w2 = inv_Gram @ (A_act_i @ g_i)
                # w1 = grad_u* - A_act^T @ w2
                w1 = g_i - A_act_i.T @ w2

                # grad_b[active] = w2
                grad_b_i[act_idx_i] = w2

                # grad_A[active] = - (w2 (x) u* + lam (x) w1)
                dA_act = -(w2.unsqueeze(1) @ u_star_i.unsqueeze(0) + lam_i.unsqueeze(1) @ w1.unsqueeze(0))
                grad_A_i[act_idx_i] = dA_act

            grad_A_list.append(grad_A_i)
            grad_b_list.append(grad_b_i)

        grad_u_nom_out = torch.stack(grad_u_nom_list, dim=0)
        grad_A_out = torch.stack(grad_A_list, dim=0)
        grad_b_out = torch.stack(grad_b_list, dim=0)

        # Reduce gradients if original A or b were not batched
        if orig_A_dim == 2:
            grad_A_final = grad_A_out.sum(dim=0)
        else:
            grad_A_final = grad_A_out

        if orig_b_dim == 1:
            grad_b_final = grad_b_out.sum(dim=0)
        else:
            grad_b_final = grad_b_out

        if not is_batched:
            grad_u_nom_final = grad_u_nom_out.squeeze(0)
            if orig_A_dim == 2 and grad_A_final.dim() == 3:
                grad_A_final = grad_A_final.squeeze(0)
            if orig_b_dim == 1 and grad_b_final.dim() == 2:
                grad_b_final = grad_b_final.squeeze(0)
            return grad_u_nom_final, grad_A_final, grad_b_final, None, None

        return grad_u_nom_out, grad_A_final, grad_b_final, None, None


class JointCLBFCBFBuilder:
    """
    Constructs unified linear inequality constraints A u <= b for:
    1. Actuator saturation box limits: -u_max <= u <= u_max
    2. High-Order Control Barrier Functions (HOCBF) for static & dynamic obstacles:
       h_ddot + (alpha1 + alpha2) h_dot + alpha1 * alpha2 * h >= 0
    3. Control Lyapunov-Barrier Functions (CLBF) for exponential goal convergence:
       V_dot + gamma_V * V <= delta_slack
    """

    def __init__(
        self,
        mass: float = 1.0,
        gravity: float = 9.81,
        force_limit: float = 15.0,
        cbf_alpha: float = 2.5,
        clbf_gamma: float = 1.2,
        robot_radius: float = 0.22,
        safety_margin: float = 0.15,
    ) -> None:
        self.mass = mass
        self.gravity = gravity
        self.force_limit = force_limit
        self.cbf_alpha = cbf_alpha
        self.clbf_gamma = clbf_gamma
        self.robot_radius = robot_radius
        self.safety_margin = safety_margin

    def build_constraints(
        self,
        pos: np.ndarray,
        vel: np.ndarray,
        target_pos: np.ndarray,
        obstacles: list[Any],
        include_clbf: bool = True,
        clbf_slack: float = 5.0,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Builds A (K, 3) and b (K,) tensors for PyTorch optimization.
        """
        A_list: list[np.ndarray] = []
        b_list: list[float] = []

        m = self.mass
        g_vec = np.array([0.0, 0.0, -self.gravity], dtype=np.float64)

        # 1. Actuator box bounds
        for axis in range(3):
            # u_axis <= force_limit
            e_pos = np.zeros(3, dtype=np.float64)
            e_pos[axis] = 1.0
            A_list.append(e_pos)
            b_list.append(self.force_limit)

            # -u_axis <= force_limit  <=>  u_axis >= -force_limit
            e_neg = np.zeros(3, dtype=np.float64)
            e_neg[axis] = -1.0
            A_list.append(e_neg)
            b_list.append(self.force_limit)

        # 2. Obstacle HOCBF constraints
        r_safe_base = self.robot_radius + self.safety_margin
        alpha1 = self.cbf_alpha
        alpha2 = self.cbf_alpha

        for obs in obstacles:
            obs_center = obs.center if hasattr(obs, "center") else obs[0]
            obs_radius = obs.radius if hasattr(obs, "radius") else obs[1]
            obs_vel = obs.velocity if hasattr(obs, "velocity") else np.zeros(3)

            p_rel = pos - obs_center
            v_rel = vel - obs_vel
            r_safe = r_safe_base + obs_radius

            h = float(np.sum(p_rel**2) - r_safe**2)
            h_dot = 2.0 * float(np.dot(p_rel, v_rel))

            # h_ddot = 2 * ||v_rel||^2 + 2 * p_rel^T (u / m + g_vec)
            # Require: h_ddot + (alpha1 + alpha2) * h_dot + alpha1 * alpha2 * h >= 0
            # -2 * p_rel^T (u / m) <= 2 * ||v_rel||^2 + 2 * p_rel^T g_vec + (alpha1 + alpha2)*h_dot + alpha1*alpha2*h
            a_cbf = -2.0 * p_rel / m
            b_cbf = (
                2.0 * float(np.sum(v_rel**2))
                + 2.0 * float(np.dot(p_rel, g_vec))
                + (alpha1 + alpha2) * h_dot
                + alpha1 * alpha2 * h
            )
            A_list.append(a_cbf)
            b_list.append(b_cbf)

        # 3. Control Lyapunov Function (CLBF) convergence constraint
        if include_clbf:
            p_err = pos - target_pos
            k_p = 2.5
            # V(p, v) = 1/2 k_p ||p - p_tgt||^2 + 1/2 m ||v||^2
            V = 0.5 * k_p * float(np.sum(p_err**2)) + 0.5 * m * float(np.sum(vel**2))
            # V_dot = k_p p_err^T v + m v^T (u / m + g_vec) = k_p p_err^T v + v^T u + m v^T g_vec
            # Require: V_dot + gamma_V * V <= clbf_slack
            # v^T u <= - k_p p_err^T v - m v^T g_vec - gamma_V * V + clbf_slack
            a_clbf = vel.copy()
            b_clbf = -k_p * float(np.dot(p_err, vel)) - m * float(np.dot(vel, g_vec)) - self.clbf_gamma * V + clbf_slack
            A_list.append(a_clbf)
            b_list.append(b_clbf)

        A_tensor = torch.as_tensor(np.array(A_list, dtype=np.float32))
        b_tensor = torch.as_tensor(np.array(b_list, dtype=np.float32))

        return A_tensor, b_tensor


class DifferentiableHOCBFLayer(nn.Module):
    """
    PyTorch Module that shields nominal neural actions with Differentiable Safe QP.
    Gradients propagate through active barrier boundaries back to upstream neural weights.
    """

    def __init__(self, joint_builder: JointCLBFCBFBuilder | None = None) -> None:
        super().__init__()
        self.builder = joint_builder or JointCLBFCBFBuilder()

    def forward(
        self,
        u_nom: torch.Tensor,
        A: torch.Tensor,
        b: torch.Tensor,
    ) -> torch.Tensor:
        """
        Projects u_nom onto polytope A u <= b with analytical KKT gradients.
        """
        return DifferentiableSafeQPLayer.apply(u_nom, A, b)
