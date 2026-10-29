"""
NEXVIA AEGIS — Proximal Policy Optimization (PPO) Agent for Safe RL.

Features:
1. Generalized Advantage Estimation (GAE-lambda) with value bootstrapping.
2. Clipped surrogate policy objective L_CLIP(theta).
3. Value function mean-squared error loss with gradient clipping.
4. Entropy bonus for exploration.
5. Tensor-based rollout buffer and mini-batch stochastic gradient descent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from aegis.rl.neural_policy import ActorCritic6DOF


@dataclass
class PPOConfig:
    """Hyperparameters for Safe PPO training."""
    lr: float = 3.0e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.20
    vf_coef: float = 0.50
    ent_coef: float = 0.01
    max_grad_norm: float = 0.50
    update_epochs: int = 4
    batch_size: int = 64
    hidden_dim: int = 128


class SafePPOAgent:
    """
    Proximal Policy Optimization Agent with Differentiable HOCBF Safety Interventions.
    """

    def __init__(
        self,
        state_dim: int = 20,
        action_dim: int = 3,
        config: PPOConfig | None = None,
        device: str = "cpu",
    ) -> None:
        self.cfg = config or PPOConfig()
        self.device = torch.device(device)
        self.ac = ActorCritic6DOF(
            state_dim=state_dim,
            action_dim=action_dim,
            hidden_dim=self.cfg.hidden_dim,
        ).to(self.device)

        self.optimizer = optim.Adam(self.ac.parameters(), lr=self.cfg.lr, eps=1e-5)

    def select_action(
        self,
        state: np.ndarray,
        deterministic: bool = False,
    ) -> tuple[np.ndarray, float, float]:
        """
        Samples an action from the policy for the given state.
        Returns: (action_np, log_prob, value)
        """
        with torch.no_grad():
            s_tensor = torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
            action, log_prob, _, value = self.ac.get_action_and_value(s_tensor, deterministic=deterministic)

        return action.squeeze(0).cpu().numpy(), float(log_prob.item()), float(value.item())

    def update(
        self,
        states: np.ndarray,
        actions: np.ndarray,
        log_probs: np.ndarray,
        rewards: np.ndarray,
        values: np.ndarray,
        dones: np.ndarray,
        next_value: float,
    ) -> dict[str, float]:
        """
        Executes GAE advantage computation and PPO clipped policy updates over rollout buffer.
        """
        n_steps = len(rewards)
        advantages = np.zeros(n_steps, dtype=np.float32)
        last_gae_lam = 0.0

        for t in reversed(range(n_steps)):
            if t == n_steps - 1:
                next_non_terminal = 1.0 - float(dones[t])
                next_val = next_value
            else:
                next_non_terminal = 1.0 - float(dones[t])
                next_val = values[t + 1]

            delta = rewards[t] + self.cfg.gamma * next_val * next_non_terminal - values[t]
            advantages[t] = last_gae_lam = delta + self.cfg.gamma * self.cfg.gae_lambda * next_non_terminal * last_gae_lam

        returns = advantages + values

        # Convert to PyTorch tensors
        b_states = torch.as_tensor(states, dtype=torch.float32, device=self.device)
        b_actions = torch.as_tensor(actions, dtype=torch.float32, device=self.device)
        b_logprobs = torch.as_tensor(log_probs, dtype=torch.float32, device=self.device)
        b_advantages = torch.as_tensor(advantages, dtype=torch.float32, device=self.device)
        b_returns = torch.as_tensor(returns, dtype=torch.float32, device=self.device)

        # Normalize advantages
        b_advantages = (b_advantages - b_advantages.mean()) / (b_advantages.std() + 1e-8)

        total_pg_loss = 0.0
        total_v_loss = 0.0
        total_entropy = 0.0
        updates_count = 0

        dataset_size = len(states)
        indices = np.arange(dataset_size)

        for _ in range(self.cfg.update_epochs):
            np.random.shuffle(indices)
            for start in range(0, dataset_size, self.cfg.batch_size):
                end = start + self.cfg.batch_size
                mb_idx = indices[start:end]

                _, new_logprob, entropy, new_value = self.ac.get_action_and_value(
                    b_states[mb_idx], b_actions[mb_idx]
                )

                log_ratio = new_logprob - b_logprobs[mb_idx]
                ratio = torch.exp(log_ratio)

                mb_advantages = b_advantages[mb_idx]

                # Policy Loss (PPO-Clip)
                pg_loss1 = -mb_advantages * ratio
                pg_loss2 = -mb_advantages * torch.clamp(ratio, 1.0 - self.cfg.clip_eps, 1.0 + self.cfg.clip_eps)
                pg_loss = torch.max(pg_loss1, pg_loss2).mean()

                # Value Loss
                v_loss = 0.5 * ((new_value.squeeze(-1) - b_returns[mb_idx]) ** 2).mean()

                # Total Loss
                entropy_loss = entropy.mean()
                loss = pg_loss - self.cfg.ent_coef * entropy_loss + self.cfg.vf_coef * v_loss

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.ac.parameters(), self.cfg.max_grad_norm)
                self.optimizer.step()

                total_pg_loss += float(pg_loss.item())
                total_v_loss += float(v_loss.item())
                total_entropy += float(entropy_loss.item())
                updates_count += 1

        return {
            "policy_loss": total_pg_loss / max(1, updates_count),
            "value_loss": total_v_loss / max(1, updates_count),
            "entropy": total_entropy / max(1, updates_count),
        }
