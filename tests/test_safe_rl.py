"""
Unit Tests for NEXVIA AEGIS — Safe Reinforcement Learning (Safe RL) with HOCBF Action Shielding.

Verifies:
1. ActorCritic6DOF network output dimensions, sampling distribution, and gradient backpropagation.
2. Safe6DOFQuadrotorEnv observation space (20D), dynamic obstacle kinematics, and step transitions.
3. HOCBF Action Shielding intervention: projects unsafe neural actions onto safe half-space.
4. SafePPOAgent GAE advantage computation and clipped policy update step.
"""

import numpy as np
import pytest
import torch

from aegis.rl.neural_policy import ActorCritic6DOF
from aegis.rl.safe_env_wrapper import DynamicObstacle3D, Safe6DOFQuadrotorEnv
from aegis.rl.safe_ppo_agent import PPOConfig, SafePPOAgent


def test_actor_critic_shapes_and_gradients():
    """Validates ActorCritic6DOF tensor dimensions, entropy, and gradient computation."""
    ac = ActorCritic6DOF(state_dim=20, action_dim=3, hidden_dim=64)

    batch_size = 8
    states = torch.randn(batch_size, 20)

    # 1. Forward action and value
    action, log_prob, entropy, value = ac.get_action_and_value(states)

    assert action.shape == (batch_size, 3)
    assert log_prob.shape == (batch_size,)
    assert entropy.shape == (batch_size,)
    assert value.shape == (batch_size, 1)
    assert not torch.isnan(action).any()
    assert not torch.isnan(value).any()

    # 2. Gradient backpropagation via log_prob and value (standard PPO loss components)
    loss = log_prob.sum() + value.sum()
    loss.backward()

    for name, param in ac.named_parameters():
        assert param.grad is not None, f"Parameter {name} missing gradient"
        assert not torch.isnan(param.grad).any()


def test_safe_env_wrapper_reset_and_dimensions():
    """Validates 20D observation vector and dynamic obstacle kinematic updates."""
    env = Safe6DOFQuadrotorEnv(shield_enabled=True, max_steps=20)
    obs = env.reset()

    assert isinstance(obs, np.ndarray)
    assert obs.shape == (20,)
    assert not np.isnan(obs).any()

    # Check dynamic obstacle positions
    c0_init = env.dynamic_obstacles[0].center.copy()
    c1_init = env.dynamic_obstacles[1].center.copy()

    # Step environment
    dummy_action = np.zeros(3, dtype=np.float32)
    next_obs, reward, terminated, truncated, info = env.step(dummy_action)

    assert next_obs.shape == (20,)
    assert isinstance(reward, float)
    assert not np.isnan(reward)
    assert "intervention_norm" in info
    assert "barrier_active" in info
    assert "drone_pos" in info

    # Obstacles must have moved
    c0_next = env.dynamic_obstacles[0].center
    assert not np.allclose(c0_init, c0_next)


def test_hocbf_action_shielding_intervention():
    """Tests that HOCBF shield actively intervenes and prevents collision on dangerous commands."""
    # 1. Unshielded Env: Command aggressive thrust toward ground
    env_unshielded = Safe6DOFQuadrotorEnv(shield_enabled=False, max_steps=50)
    env_unshielded.reset()

    # Extreme downward force command (action_z = -1.0)
    suicidal_action = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    crashed = False
    for _ in range(30):
        _, _, terminated, _, info = env_unshielded.step(suicidal_action)
        if info["collision"]:
            crashed = True
            break
    assert crashed, "Unshielded quadrotor should crash under downward thrust"

    # 2. Shielded Env: Same suicidal command must be intercepted by HOCBF filter
    env_shielded = Safe6DOFQuadrotorEnv(shield_enabled=True, max_steps=50)
    env_shielded.reset()

    interventions = 0
    shielded_crashed = False
    for _ in range(30):
        _, _, _, _, info = env_shielded.step(suicidal_action)
        if info["barrier_active"]:
            interventions += 1
            assert info["intervention_norm"] > 0.0
        if info["collision"]:
            shielded_crashed = True

    assert interventions > 0, "HOCBF shield must intervene against suicidal downward commands"
    assert not shielded_crashed, "HOCBF shield must guarantee zero floor crashes"


def test_safe_ppo_agent_training_update():
    """Validates GAE advantage calculation and PPO parameter optimization step."""
    cfg = PPOConfig(
        batch_size=8,
        update_epochs=2,
        hidden_dim=32,
    )
    agent = SafePPOAgent(state_dim=20, action_dim=3, config=cfg)

    # Collect synthetic rollout of 16 steps
    n_steps = 16
    states = np.random.randn(n_steps, 20).astype(np.float32)
    actions = np.random.uniform(-1.0, 1.0, size=(n_steps, 3)).astype(np.float32)
    log_probs = np.random.randn(n_steps).astype(np.float32)
    rewards = np.random.randn(n_steps).astype(np.float32)
    values = np.random.randn(n_steps).astype(np.float32)
    dones = np.zeros(n_steps, dtype=np.float32)
    dones[-1] = 1.0

    metrics = agent.update(
        states=states,
        actions=actions,
        log_probs=log_probs,
        rewards=rewards,
        values=values,
        dones=dones,
        next_value=0.0,
    )

    assert "policy_loss" in metrics
    assert "value_loss" in metrics
    assert "entropy" in metrics
    assert not np.isnan(metrics["policy_loss"])
    assert not np.isnan(metrics["value_loss"])


def test_adaptive_cbf_and_energy_metrics():
    """Validates that Adaptive CBF tracks control energy, jerk, and modulates barrier decay."""
    env = Safe6DOFQuadrotorEnv(
        shield_enabled=True,
        adaptive_cbf=True,
        max_steps=20,
        energy_penalty_weight=0.02,
        smoothness_penalty_weight=0.01,
    )
    env.reset()

    # Step through with mild actions
    action = np.array([0.2, -0.1, 0.05], dtype=np.float32)
    for _ in range(10):
        _, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break

    assert "control_energy" in info
    assert "mean_jerk" in info
    assert "transit_time_s" in info
    assert info["control_energy"] >= 0.0
    assert info["mean_jerk"] >= 0.0
    assert info["transit_time_s"] > 0.0


def test_sensor_fault_and_innovation_gate_rejection():
    """Validates that innovation gate catches sensor spoofing and prevents false arrival."""
    fault_cfg = {"fault_type": "spoof_arrival", "start_step": 5}

    # 1. Without innovation gate: sensor spoof causes false arrival
    env_unguarded = Safe6DOFQuadrotorEnv(
        shield_enabled=True,
        enable_innovation_gate=False,
        sensor_fault_config=fault_cfg,
        max_steps=20,
    )
    env_unguarded.reset()
    action = np.zeros(3, dtype=np.float32)

    unguarded_false_arrival = False
    for _ in range(15):
        _, _, terminated, _, info = env_unguarded.step(action)
        if info["false_arrival"]:
            unguarded_false_arrival = True
            break
        if terminated:
            break

    assert unguarded_false_arrival, "Unguarded env must succumb to sensor spoofing (false arrival)"

    # 2. With innovation gate: sensor spoofing is intercepted; system abstains with 0 false arrivals
    env_guarded = Safe6DOFQuadrotorEnv(
        shield_enabled=True,
        enable_innovation_gate=True,
        sensor_fault_config=fault_cfg,
        max_steps=20,
    )
    env_guarded.reset()

    guarded_false_arrival = False
    guarded_abstained = False
    for _ in range(15):
        _, _, terminated, _, info = env_guarded.step(action)
        if info["false_arrival"]:
            guarded_false_arrival = True
        if info["abstain"]:
            guarded_abstained = True
        if terminated:
            break

    assert not guarded_false_arrival, "Guarded env must NEVER suffer false arrival (Selective Risk = 0%)"
    assert guarded_abstained, "Guarded env must successfully flag abstention upon sensor anomaly"

