"""
NEXVIA AEGIS-Next (V8) — Architecture Package.

Provides:
- Anytime-valid sequential risk monitoring via betting supermartingales.
- Kinematic velocity-profile control eliminating timeout and coasting overshoot.
- Classical and architectural baseline controllers for empirical benchmarking.
- Integrated AEGIS-Next recovery controller.
"""

from __future__ import annotations

from aegis.next.martingale_monitor import AnytimeValidSequentialMonitor, MartingaleConfig
from aegis.next.velocity_controller import KinematicVelocityController, VelocityProfileConfig
from aegis.next.agent_next import AegisNextController
from aegis.next.baselines import (
    UnshieldedAlwaysActController,
    ChiSquareNISGatingController,
    EKFConsistencyController,
    AegisV4PassiveController,
    AegisV5HuberController,
    AegisV6DiscriminativeController,
    AegisV7MPCBaselineController,
)

__all__ = [
    "AnytimeValidSequentialMonitor",
    "MartingaleConfig",
    "KinematicVelocityController",
    "VelocityProfileConfig",
    "AegisNextController",
    "UnshieldedAlwaysActController",
    "ChiSquareNISGatingController",
    "EKFConsistencyController",
    "AegisV4PassiveController",
    "AegisV5HuberController",
    "AegisV6DiscriminativeController",
    "AegisV7MPCBaselineController",
]
