"""
NEXVIA-AEGIS: Autonomous Vehicle (AV) & Cyber-Resilient Platooning Stack.
Covers:
  1. Non-holonomic Dynamic Bicycle Model with Pacejka tire dynamics & dynamic weight transfer.
  2. Frenet Frame road coordinate transformation (s, d).
  3. Kamm's Friction Circle & High-Order Control Barrier Functions (HOCBF).
  4. Byzantine-Resilient Connected Platooning (C-V2X) with Ville Supermartingale Betting Filter.
  5. Autoware.Universe / ROS 2 Ackermann Control Bridge.
"""

from aegis.av.vehicle_dynamics import (
    DynamicBicycleModel,
    FrenetFrame,
    FrenetState,
    TireForces,
    VehicleConfig,
    VehicleState,
)
from aegis.av.frenet_cbf_shield import (
    FrenetCbfConfig,
    FrenetSafetyShield,
    ShieldedControlCommand,
)
from aegis.av.platooning_brmc import (
    CyberResilientPlatoonController,
    PlatoonConfig,
    PlatoonVehicleState,
    V2XTelemetryPacket,
)
from aegis.av.autoware_ros2_bridge import (
    AckermannControlCommand,
    AegisAutowareVehicleNode,
)

__all__ = [
    "AckermannControlCommand",
    "AegisAutowareVehicleNode",
    "CyberResilientPlatoonController",
    "DynamicBicycleModel",
    "FrenetCbfConfig",
    "FrenetFrame",
    "FrenetSafetyShield",
    "FrenetState",
    "PlatoonConfig",
    "PlatoonVehicleState",
    "ShieldedControlCommand",
    "TireForces",
    "V2XTelemetryPacket",
    "VehicleConfig",
    "VehicleState",
]
