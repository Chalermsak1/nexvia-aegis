"""
NEXVIA AEGIS — Unit Tests for Differentiable Implicit-KKT Safe RL Layer.

Verifies:
1. Mathematical Jacobian precision using torch.autograd.gradcheck (analytical vs numerical).
2. Strict barrier satisfaction: projected u* satisfies A u* <= b.
3. Invariant pass-through when nominal action is strictly interior (unconstrained P = I).
4. Batched forward and backward propagation (B = 4).
5. End-to-end policy gradient flow from downstream task loss through CLBF-CBF into Actor network.
"""

import numpy as np
import pytest
import torch
from torch.autograd import gradcheck

from aegis.rl.differentiable_cbf import (
    DifferentiableHOCBFLayer,
    DifferentiableSafeQPLayer,
    JointCLBFCBFBuilder,
)
from aegis.rl.neural_policy import ActorCritic6DOF


def test_differentiable_qp_gradcheck():
    """Validates analytical KKT gradients against numerical finite differences via torch.autograd.gradcheck."""
    # Active constraint setting
    u_nom = torch.tensor([2.0, 1.2, -0.5], dtype=torch.float64, requires_grad=True)
    A = torch.tensor([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ], dtype=torch.float64, requires_grad=True)
    b = torch.tensor([1.0, 0.8], dtype=torch.float64, requires_grad=True)

    # gradcheck with strict tolerance
    test_passed = gradcheck(
        DifferentiableSafeQPLayer.apply,
        (u_nom, A, b),
        eps=1e-6,
        atol=1e-4,
        rtol=1e-3,
    )
    assert test_passed, "Gradcheck failed for DifferentiableSafeQPLayer"


def test_differentiable_qp_interior_passthrough():
    """Verifies that interior nominal commands pass through unmodified with identity sensitivity."""
    u_nom = torch.tensor([0.2, -0.3, 0.1], dtype=torch.float32, requires_grad=True)
    A = torch.tensor([
        [1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0],
    ], dtype=torch.float32)
    b = torch.tensor([2.0, 2.0, 2.0, 2.0], dtype=torch.float32)

    u_star = DifferentiableSafeQPLayer.apply(u_nom, A, b)
    assert torch.allclose(u_star, u_nom, atol=1e-5), "Interior action should not be modified"

    # Loss = ||u*||^2 -> grad_u_nom should be exactly 2 * u_nom
    loss = torch.sum(u_star**2)
    loss.backward()
    assert torch.allclose(u_nom.grad, 2.0 * u_nom, atol=1e-5), "Sensitivity Jacobian should be Identity for interior actions"


def test_differentiable_qp_barrier_enforcement():
    """Verifies that an unsafe nominal action is projected strictly onto the barrier surface."""
    # Commanded forward force is 10.0 N, but barrier limits it to <= 2.5 N
    u_nom = torch.tensor([10.0, 0.0, 0.0], dtype=torch.float32, requires_grad=True)
    A = torch.tensor([[1.0, 0.0, 0.0]], dtype=torch.float32)
    b = torch.tensor([2.5], dtype=torch.float32)

    u_star = DifferentiableSafeQPLayer.apply(u_nom, A, b)

    # u* should be [2.5, 0.0, 0.0]
    assert torch.allclose(u_star[0], torch.tensor(2.5), atol=1e-4)
    assert torch.allclose(u_star[1], torch.tensor(0.0), atol=1e-4)
    assert torch.allclose(u_star[2], torch.tensor(0.0), atol=1e-4)

    # Backpropagate loss pulling towards target: L = (u*[0] - 5.0)^2
    loss = (u_star[0] - 5.0) ** 2
    loss.backward()

    # Sensitivity: since u* is pinned at b, d(u*[0]) / d(u_nom[0]) = 0 along the normal!
    # Projection matrix P has 0 along x-axis
    assert abs(u_nom.grad[0].item()) < 1e-4, "Normal sensitivity should be projected out"


def test_differentiable_qp_batched_forward_backward():
    """Verifies batched operations across multiple diverse constraint configurations."""
    B = 4
    u_nom = torch.randn(B, 3, dtype=torch.float32, requires_grad=True)
    A = torch.tensor([
        [1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=torch.float32).unsqueeze(0).repeat(B, 1, 1)
    b = torch.tensor([1.5, 1.5, 1.5, 1.5], dtype=torch.float32).unsqueeze(0).repeat(B, 1)

    u_star = DifferentiableSafeQPLayer.apply(u_nom, A, b)
    assert u_star.shape == (B, 3)

    # Check that all elements satisfy constraints
    for i in range(B):
        viol = A[i] @ u_star[i] - b[i]
        assert torch.all(viol <= 1e-4), f"Batch element {i} violated constraints"

    loss = u_star.sum()
    loss.backward()
    assert u_nom.grad is not None
    assert u_nom.grad.shape == (B, 3)
    assert not torch.isnan(u_nom.grad).any()


def test_joint_clbf_cbf_builder_and_actor_gradient_flow():
    """
    Verifies end-to-end integration:
    ActorCritic6DOF -> nominal action -> DifferentiableHOCBFLayer -> task loss -> Actor network weights.
    """
    actor = ActorCritic6DOF(state_dim=20, action_dim=3, hidden_dim=64)
    builder = JointCLBFCBFBuilder(mass=1.0, gravity=9.81, force_limit=12.0)
    safe_layer = DifferentiableHOCBFLayer(builder)

    state = torch.randn(1, 20)
    u_nom, log_prob, _, value = actor.get_action_and_value(state, reparameterize=True)

    pos = np.array([0.0, 0.0, 1.0])
    vel = np.array([1.2, 0.0, 0.0])
    tgt = np.array([2.0, 0.0, 1.0])

    class MockObs:
        center = np.array([1.0, 0.0, 1.0])
        radius = 0.4
        velocity = np.zeros(3)

    A_t, b_t = builder.build_constraints(pos, vel, tgt, [MockObs()], include_clbf=True)

    # Shield nominal action
    u_safe = safe_layer(u_nom, A_t, b_t)

    assert u_safe.shape == (1, 3)
    # Verify all constraints satisfied
    viol = A_t @ u_safe.squeeze(0) - b_t
    assert torch.all(viol <= 1e-3), "Safe action must satisfy all Joint CLBF-CBF constraints"

    # Compute loss on safe action and backpropagate directly into Actor network parameters
    target_force = torch.tensor([[5.0, 0.0, 9.81]])
    loss = torch.sum((u_safe - target_force) ** 2)
    loss.backward()

    # Actor network weights must receive non-zero gradients through the KKT layer!
    grad_found = False
    for name, param in actor.actor_mean.named_parameters():
        if param.grad is not None and torch.norm(param.grad) > 1e-6:
            grad_found = True
            break

    assert grad_found, "Actor network weights must receive gradient signal through Differentiable KKT Layer"
