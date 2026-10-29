"""NEXVIA AEGIS Sim2Real Deployment and ROS 2 / PX4 Autopilot Hardware Bridge.

Modules:
    mavlink_protocol: MAVLink / MAVROS message definitions and attitude conversions.
    safety_watchdog: Real-time watchdog, latency compensation, and failsafe state machine.
    aegis_ros2_node: Production ROS 2 Humble companion computer autonomy node.
"""

from aegis.sim2real.mavlink_protocol import (
    AttitudeTargetSetpoint,
    BatteryTelemetry,
    DroneOdometry,
    FailsafeAction,
    MavState,
    PX4FlightMode,
    force_vector_to_attitude_and_thrust,
    quaternion_to_euler_angles,
)
from aegis.sim2real.safety_watchdog import (
    HardwareWatchdogConfig,
    RealtimeSafetyWatchdog,
    WatchdogDiagnostic,
    WatchdogHealthState,
)
from aegis.sim2real.aegis_ros2_node import (
    AegisNodeConfig,
    AegisROS2DroneNode,
)

__all__ = [
    "AttitudeTargetSetpoint",
    "BatteryTelemetry",
    "DroneOdometry",
    "FailsafeAction",
    "MavState",
    "PX4FlightMode",
    "force_vector_to_attitude_and_thrust",
    "quaternion_to_euler_angles",
    "HardwareWatchdogConfig",
    "RealtimeSafetyWatchdog",
    "WatchdogDiagnostic",
    "WatchdogHealthState",
    "AegisNodeConfig",
    "AegisROS2DroneNode",
]
