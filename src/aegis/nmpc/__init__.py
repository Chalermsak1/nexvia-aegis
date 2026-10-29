"""
NEXVIA-AEGIS: Nonlinear Model Predictive Control with Control Barrier Functions (NMPC-CBF).
Provides receding-horizon lookahead trajectory optimization with guaranteed safety barriers,
smooth jerk minimization, and real-time QP execution for 6-DOF aerial quadrotors.
"""

from aegis.nmpc.nmpc_cbf_optimizer import (
    NmpcCbfConfig,
    NmpcCbfController,
    NmpcOptimizationResult,
    PlannedHorizonTrajectory,
)

__all__ = [
    "NmpcCbfConfig",
    "NmpcCbfController",
    "NmpcOptimizationResult",
    "PlannedHorizonTrajectory",
]
