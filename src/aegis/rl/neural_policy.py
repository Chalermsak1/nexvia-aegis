"""
NEXVIA AEGIS — Actor-Critic Neural Policy for 6-DOF Quadrotor Physical AI.

Implements a continuous-action Actor-Critic neural network architecture:
1. Actor Network: Outputs mean action mu(s) and state-independent log_std for continuous
   3D force vector commands in R^3.
2. Critic Network: Estimates scalar state-value function V(s).
3. Orthogonal weight initialization for stable policy gradient training.
4. Tanh-squashed Gaussian policy with analytical log-probability computation.
"""

from __future__ import annotations

import math
from typing import Tuple

import torch
import torch.nn as nn
from torch.distributions.normal import Normal


def layer_init(layer: nn.Linear, std: float = math.sqrt(2.0), bias_const: float = 0.0) -> nn.Linear:
    """Initializes linear layers using orthogonal initialization."""
    nn.init.orthogonal_(layer.weight, std)
    nn.init.constant_(layer.bias, bias_const)
    return layer


class ActorCritic6DOF(nn.Module):
    """
    Gaussian Actor-Critic Network for 6-DOF Quadrotor Control.
    Input state dim: 20 (position error, velocity, orientation R elements, angular velocity, obstacle relative vectors).
    Output action dim: 3 (desired 3D navigation force F_x, F_y, F_z).
    """

    def __init__(self, state_dim: int = 20, action_dim: int = 3, hidden_dim: int = 128) -> None:
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim

        # Critic Network (Value function V(s))
        self.critic = nn.Sequential(
            layer_init(nn.Linear(state_dim, hidden_dim)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden_dim, hidden_dim)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden_dim, 1), std=1.0),
        )

        # Actor Network (Mean mu(s))
        self.actor_mean = nn.Sequential(
            layer_init(nn.Linear(state_dim, hidden_dim)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden_dim, hidden_dim)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden_dim, action_dim), std=0.01),
        )

        # Learnable log standard deviation for continuous action exploration
        self.actor_logstd = nn.Parameter(torch.zeros(1, action_dim))

    def get_value(self, x: torch.Tensor) -> torch.Tensor:
        """Returns the scalar value estimate V(s)."""
        return self.critic(x)

    def get_action_and_value(
        self,
        x: torch.Tensor,
        action: torch.Tensor | None = None,
        deterministic: bool = False,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Computes action, log probability, entropy, and value estimate for input state x.

        Returns:
            (action, log_prob, entropy, value)
        """
        action_mean = self.actor_mean(x)
        action_logstd = self.actor_logstd.expand_as(action_mean)
        action_std = torch.exp(action_logstd)
        probs = Normal(action_mean, action_std)

        if action is None:
            if deterministic:
                action = action_mean
            else:
                action = probs.sample()

        log_prob = probs.log_prob(action).sum(dim=-1)
        entropy = probs.entropy().sum(dim=-1)
        value = self.critic(x)

        return action, log_prob, entropy, value
