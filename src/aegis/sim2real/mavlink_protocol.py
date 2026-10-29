"""MAVLink and MAVROS Protocol Data Structures and State Conversions for PX4 Autopilot.

Provides pure-Python representation of MAVLink / MAVROS message schemas,
attitude-quaternion conversions, and normalized thrust allocation for
PX4 Autopilot companion computer integration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
import numpy as np


class PX4FlightMode(Enum):
    """PX4 Autopilot navigation and flight modes."""
    MANUAL = auto()
    ALTCTL = auto()
    POSCTL = auto()
    OFFBOARD = auto()
    AUTO_LOITER = auto()
    AUTO_RTL = auto()
    AUTO_LAND = auto()
    EMERGENCY_KILL = auto()


class FailsafeAction(Enum):
    """Failsafe emergency intervention levels."""
    NONE = auto()
    VELOCITY_AIR_BRAKE = auto()
    POSITION_HOLD_HOVER = auto()
    SAFE_ABSTENTION_LOITER = auto()
    AUTO_RETURN_TO_LAUNCH = auto()
    EMERGENCY_LAND = auto()


@dataclass
class MavState:
    """Represents current PX4 FCU connection and arming state."""
    connected: bool = True
    armed: bool = True
    guided: bool = True
    manual_input: bool = False
    mode: PX4FlightMode = PX4FlightMode.OFFBOARD
    system_status: int = 4  # MAV_STATE_ACTIVE


@dataclass
class DroneOdometry:
    """Local position and velocity odometry (e.g., from EKF2)."""
    timestamp_s: float = 0.0
    position: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    quaternion_wxyz: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64))
    linear_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    angular_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))


@dataclass
class BatteryTelemetry:
    """Battery state telemetry from PX4."""
    timestamp_s: float = 0.0
    voltage_v: float = 16.8  # 4S full charge
    current_a: float = 5.0
    percentage: float = 1.0
    temperature_c: float = 28.0


@dataclass
class AttitudeTargetSetpoint:
    """MAVLink SET_ATTITUDE_TARGET message representation.

    type_mask:
      1: ignore roll_rate
      2: ignore pitch_rate
      4: ignore yaw_rate
      64: ignore throttle
      128: ignore attitude
    """
    timestamp_s: float = 0.0
    type_mask: int = 0b00000111  # ignore body rates, use orientation quaternion + thrust
    orientation_wxyz: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64))
    body_rate_rad_s: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    thrust_normalized: float = 0.59  # [0.0, 1.0] throttle


def force_vector_to_attitude_and_thrust(
    desired_force_world: np.ndarray,
    desired_yaw_rad: float = 0.0,
    mass_kg: float = 1.5,
    max_thrust_n: float = 25.0,
    max_tilt_rad: float = math.radians(35.0),
) -> tuple[np.ndarray, float]:
    """Converts a 3D desired force vector into PX4 orientation quaternion and normalized thrust.

    Args:
        desired_force_world: 3D force vector [Fx, Fy, Fz] in world frame (N).
        desired_yaw_rad: Target heading angle in radians.
        mass_kg: Quadrotor mass in kg.
        max_thrust_n: Maximum total quadrotor thrust in N.
        max_tilt_rad: Maximum allowed tilt angle from vertical (rad).

    Returns:
        (quaternion_wxyz, normalized_thrust) where thrust is in [0.0, 1.0].
    """
    f = np.copy(desired_force_world).astype(np.float64)

    # Ensure positive vertical thrust
    min_fz = 0.2 * mass_kg * 9.81
    if f[2] < min_fz:
        f[2] = min_fz

    f_norm = float(np.linalg.norm(f))
    if f_norm < 1e-4:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64), 0.588

    # Desired body z-axis (thrust direction)
    z_b = f / f_norm

    # Enforce tilt constraint: z_b[2] >= cos(max_tilt)
    cos_max = math.cos(max_tilt_rad)
    if z_b[2] < cos_max:
        xy_len = math.sqrt(z_b[0]**2 + z_b[1]**2)
        if xy_len > 1e-6:
            scale = math.sin(max_tilt_rad) / xy_len
            z_b[0] *= scale
            z_b[1] *= scale
            z_b[2] = cos_max
            z_b /= np.linalg.norm(z_b)
        else:
            z_b = np.array([0.0, 0.0, 1.0], dtype=np.float64)

    # Reconstruct intermediate x-axis using desired yaw
    x_c = np.array([math.cos(desired_yaw_rad), math.sin(desired_yaw_rad), 0.0], dtype=np.float64)
    y_b = np.cross(z_b, x_c)
    y_b_len = np.linalg.norm(y_b)
    if y_b_len < 1e-4:
        # Singularity: pitch is 90 deg
        y_b = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    else:
        y_b /= y_b_len
    x_b = np.cross(y_b, z_b)
    x_b /= np.linalg.norm(x_b)

    # Rotation matrix R = [x_b, y_b, z_b]
    rot_mat = np.column_stack([x_b, y_b, z_b])

    # Convert rotation matrix to quaternion [w, x, y, z]
    trace = rot_mat[0, 0] + rot_mat[1, 1] + rot_mat[2, 2]
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (rot_mat[2, 1] - rot_mat[1, 2]) * s
        y = (rot_mat[0, 2] - rot_mat[2, 0]) * s
        z = (rot_mat[1, 0] - rot_mat[0, 1]) * s
    elif rot_mat[0, 0] > rot_mat[1, 1] and rot_mat[0, 0] > rot_mat[2, 2]:
        s = 2.0 * math.sqrt(1.0 + rot_mat[0, 0] - rot_mat[1, 1] - rot_mat[2, 2])
        w = (rot_mat[2, 1] - rot_mat[1, 2]) / s
        x = 0.25 * s
        y = (rot_mat[0, 1] + rot_mat[1, 0]) / s
        z = (rot_mat[0, 2] + rot_mat[2, 0]) / s
    elif rot_mat[1, 1] > rot_mat[2, 2]:
        s = 2.0 * math.sqrt(1.0 + rot_mat[1, 1] - rot_mat[0, 0] - rot_mat[2, 2])
        w = (rot_mat[0, 2] - rot_mat[2, 0]) / s
        x = (rot_mat[0, 1] + rot_mat[1, 0]) / s
        y = 0.25 * s
        z = (rot_mat[1, 2] + rot_mat[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + rot_mat[2, 2] - rot_mat[0, 0] - rot_mat[1, 1])
        w = (rot_mat[1, 0] - rot_mat[0, 1]) / s
        x = (rot_mat[0, 2] + rot_mat[2, 0]) / s
        y = (rot_mat[1, 2] + rot_mat[2, 1]) / s
        z = 0.25 * s

    quat = np.array([w, x, y, z], dtype=np.float64)
    quat /= np.linalg.norm(quat)

    # Normalize thrust to [0.0, 1.0]
    thrust_norm = float(np.clip(f_norm / max_thrust_n, 0.05, 1.0))

    return quat, thrust_norm


def quaternion_to_euler_angles(q_wxyz: np.ndarray) -> tuple[float, float, float]:
    """Extracts roll, pitch, yaw (rad) from a [w, x, y, z] quaternion."""
    w, x, y, z = q_wxyz
    # Roll (x-axis rotation)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return roll, pitch, yaw
