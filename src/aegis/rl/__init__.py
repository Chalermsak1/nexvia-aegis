"""
NEXVIA AEGIS — Safe Reinforcement Learning (Safe RL) Package.
Combines deep neural policy gradient learning (PPO) with Differentiable High-Order
Control Barrier Function (HOCBF) & Control Lyapunov Barrier Function (CLBF) action shielding.
"""

from aegis.rl.differentiable_cbf import (
    DifferentiableHOCBFLayer,
    DifferentiableSafeQPLayer,
    JointCLBFCBFBuilder,
)
from aegis.rl.neural_policy import ActorCritic6DOF
from aegis.rl.safe_env_wrapper import DynamicObstacle3D, Safe6DOFQuadrotorEnv
from aegis.rl.safe_ppo_agent import PPOConfig, SafePPOAgent

__all__ = [
    "ActorCritic6DOF",
    "DynamicObstacle3D",
    "Safe6DOFQuadrotorEnv",
    "PPOConfig",
    "SafePPOAgent",
    "DifferentiableSafeQPLayer",
    "DifferentiableHOCBFLayer",
    "JointCLBFCBFBuilder",
]
