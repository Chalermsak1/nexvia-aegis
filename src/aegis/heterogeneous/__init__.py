"""
NEXVIA AEGIS — Heterogeneous Autonomous Systems Package.
Integrates Aerial 6-DOF Robotics and Autonomous Ground Vehicles (AVs).
"""

from aegis.heterogeneous.air_ground_teaming import (
    AirGroundConfig,
    AirGroundFrenetCBF,
    AirGroundHeterogeneousCoordinator,
    AirGroundVilleFilter,
    V2ATelemetryPacket,
)
from aegis.heterogeneous.platoon_scout_handover import (
    AerialScoutState,
    DualScoutHandoverManager,
    HandoverPhase,
    HeterogeneousPlatoonConfig,
    HeterogeneousPlatoonCoordinator,
    MultiHopCascadePlatoonShield,
    PlatoonV2VPacket,
)

__all__ = [
    "AirGroundConfig",
    "AirGroundFrenetCBF",
    "AirGroundHeterogeneousCoordinator",
    "AirGroundVilleFilter",
    "V2ATelemetryPacket",
    "AerialScoutState",
    "DualScoutHandoverManager",
    "HandoverPhase",
    "HeterogeneousPlatoonConfig",
    "HeterogeneousPlatoonCoordinator",
    "MultiHopCascadePlatoonShield",
    "PlatoonV2VPacket",
]
