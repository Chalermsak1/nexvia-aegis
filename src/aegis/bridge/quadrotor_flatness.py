"""
NEXVIA-AEGIS: SE(3) Differential Flatness Converter for Underactuated Quadrotors.

Maps 3D safety-certified acceleration commands a_safe in R^3 and desired heading psi_des
onto exact attitude (R_des in SO(3), unit quaternion q_des = [w, x, y, z], ZYX Euler
angles roll/pitch/yaw) and collective thrust setpoints T for Pixhawk / PX4 Offboard control,
while strictly enforcing aerodynamic tilt-cone bounds (theta <= theta_max).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Sequence, Union
import numpy as np


def _rotation_matrix_to_quaternion_wxyz(rot_mat: np.ndarray) -> np.ndarray:
    """Converts a 3x3 SO(3) rotation matrix into a canonical unit quaternion [w, x, y, z] (w >= 0)."""
    trace = float(rot_mat[0, 0] + rot_mat[1, 1] + rot_mat[2, 2])
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (rot_mat[2, 1] - rot_mat[1, 2]) * s
        y = (rot_mat[0, 2] - rot_mat[2, 0]) * s
        z = (rot_mat[1, 0] - rot_mat[0, 1]) * s
    elif rot_mat[0, 0] > rot_mat[1, 1] and rot_mat[0, 0] > rot_mat[2, 2]:
        s = 2.0 * math.sqrt(max(1e-12, 1.0 + rot_mat[0, 0] - rot_mat[1, 1] - rot_mat[2, 2]))
        w = (rot_mat[2, 1] - rot_mat[1, 2]) / s
        x = 0.25 * s
        y = (rot_mat[0, 1] + rot_mat[1, 0]) / s
        z = (rot_mat[0, 2] + rot_mat[2, 0]) / s
    elif rot_mat[1, 1] > rot_mat[2, 2]:
        s = 2.0 * math.sqrt(max(1e-12, 1.0 + rot_mat[1, 1] - rot_mat[0, 0] - rot_mat[2, 2]))
        w = (rot_mat[0, 2] - rot_mat[2, 0]) / s
        x = (rot_mat[0, 1] + rot_mat[1, 0]) / s
        y = 0.25 * s
        z = (rot_mat[1, 2] + rot_mat[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(max(1e-12, 1.0 + rot_mat[2, 2] - rot_mat[0, 0] - rot_mat[1, 1]))
        w = (rot_mat[1, 0] - rot_mat[0, 1]) / s
        x = (rot_mat[0, 2] + rot_mat[2, 0]) / s
        y = (rot_mat[1, 2] + rot_mat[2, 1]) / s
        z = 0.25 * s

    quat = np.array([w, x, y, z], dtype=np.float64)
    norm = float(np.linalg.norm(quat))
    if norm > 1e-12:
        quat /= norm
    else:
        quat = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)

    if quat[0] < 0.0:
        quat = -quat
    return quat


def _rotation_matrix_to_euler_zyx(rot_mat: np.ndarray) -> tuple[float, float, float]:
    """Extracts intrinsic ZYX Euler angles (roll phi, pitch theta, yaw psi) in radians from R_des."""
    sin_pitch = float(np.clip(-rot_mat[2, 0], -1.0, 1.0))
    pitch = math.asin(sin_pitch)
    if abs(sin_pitch) < 0.999999:
        roll = math.atan2(float(rot_mat[2, 1]), float(rot_mat[2, 2]))
        yaw = math.atan2(float(rot_mat[1, 0]), float(rot_mat[0, 0]))
    else:
        # Gimbal lock fallback (unreachable for max_tilt < 90 deg)
        roll = 0.0
        yaw = math.atan2(float(-rot_mat[0, 1]), float(rot_mat[1, 1]))
    return roll, pitch, yaw


@dataclass
class FlatnessSetpoint:
    """Differential flatness SE(3) attitude and collective thrust output."""

    a_app: np.ndarray          # Apparent acceleration vector [m/s^2] (clamped to tilt cone)
    thrust: float              # Collective rotor thrust T [N]
    thrust_normalized: float   # Normalized throttle in [0.0, 1.0] for PX4 Offboard
    x_b: np.ndarray            # Body x-axis unit vector in world frame
    y_b: np.ndarray            # Body y-axis unit vector in world frame
    z_b: np.ndarray            # Body z-axis unit vector in world frame
    R_des: np.ndarray          # Desired rotation matrix [x_B, y_B, z_B] in SO(3)
    q_des: np.ndarray          # Desired unit quaternion [w, x, y, z]
    roll_rad: float            # Desired roll angle phi_des [rad]
    pitch_rad: float           # Desired pitch angle theta_des [rad]
    yaw_rad: float             # Desired yaw angle psi_des [rad]
    tilt_rad: float            # Total tilt angle from world vertical [rad]
    tilt_clamped: bool         # True if tilt angle clamping was engaged

    @property
    def roll_deg(self) -> float:
        return math.degrees(self.roll_rad)

    @property
    def pitch_deg(self) -> float:
        return math.degrees(self.pitch_rad)

    @property
    def yaw_deg(self) -> float:
        return math.degrees(self.yaw_rad)

    @property
    def tilt_deg(self) -> float:
        return math.degrees(self.tilt_rad)


class QuadrotorFlatnessConverter:
    """
    Exact SE(3) Differential Flatness Mapping from 3D certified acceleration to
    attitude (SO(3), quaternion, Euler angles) and collective rotor thrust.
    """

    def __init__(
        self,
        mass: float = 1.5,
        gravity: Optional[Union[Sequence[float], np.ndarray, float]] = None,
        max_tilt_deg: float = 35.0,
        max_thrust_n: Optional[float] = None,
    ) -> None:
        if mass <= 0.0:
            raise ValueError(f"Vehicle mass must be positive, got {mass}")
        if not (0.0 < max_tilt_deg < 89.0):
            raise ValueError(f"max_tilt_deg must be in (0, 89), got {max_tilt_deg}")

        self.mass = float(mass)
        if gravity is None:
            self.gravity = np.array([0.0, 0.0, -9.81], dtype=np.float64)
        elif isinstance(gravity, (int, float)):
            self.gravity = np.array([0.0, 0.0, -abs(float(gravity))], dtype=np.float64)
        else:
            g_arr = np.asarray(gravity, dtype=np.float64)
            if g_arr.shape != (3,):
                raise ValueError(f"gravity vector must have shape (3,), got {g_arr.shape}")
            self.gravity = g_arr.copy()

        self.g_mag = float(np.linalg.norm(self.gravity))
        self.max_tilt_deg = float(max_tilt_deg)
        self.max_tilt_rad = math.radians(self.max_tilt_deg)
        self.max_thrust_n = (
            float(max_thrust_n)
            if max_thrust_n is not None
            else 2.5 * self.mass * max(self.g_mag, 9.81)
        )

    def convert(
        self,
        a_safe: Union[Sequence[float], np.ndarray],
        psi_des: float = 0.0,
        mass: Optional[float] = None,
    ) -> FlatnessSetpoint:
        """
        Maps certified 3D acceleration `a_safe` and desired yaw `psi_des` [rad]
        into SE(3) attitude and collective thrust setpoints.
        """
        m = float(mass) if mass is not None else self.mass
        if m <= 0.0:
            raise ValueError(f"Vehicle mass must be positive, got {m}")

        a_vec = np.asarray(a_safe, dtype=np.float64)
        if a_vec.shape != (3,):
            raise ValueError(f"a_safe must have shape (3,), got {a_vec.shape}")

        # 1. Apparent acceleration vector: a_app = a_safe - g
        a_app_raw = a_vec - self.gravity

        # Maintain minimum upward authority to prevent thrust inversion in free-fall commands
        min_az = max(1e-3, 0.1 * self.g_mag)
        az = float(a_app_raw[2])
        tilt_clamped = False
        if az < min_az:
            az = min_az
            tilt_clamped = True

        ax = float(a_app_raw[0])
        ay = float(a_app_raw[1])
        horiz_norm = math.hypot(ax, ay)
        max_horiz = az * math.tan(self.max_tilt_rad)

        # Enforce maximum allowable tilt cone (theta <= theta_max)
        if horiz_norm > max_horiz + 1e-12:
            scale = max_horiz / horiz_norm
            ax *= scale
            ay *= scale
            tilt_clamped = True

        a_app = np.array([ax, ay, az], dtype=np.float64)
        a_app_norm = float(np.linalg.norm(a_app))

        # 2. Collective rotor thrust: T = m * ||a_app||
        thrust = m * a_app_norm
        eff_max_thrust = (
            self.max_thrust_n * (m / self.mass) if mass is not None else self.max_thrust_n
        )
        thrust_normalized = float(np.clip(thrust / max(1e-6, eff_max_thrust), 0.0, 1.0))

        # 3. Normalized body z-axis: z_B = a_app / ||a_app||
        z_b = a_app / a_app_norm
        tilt_rad = math.acos(float(np.clip(z_b[2], -1.0, 1.0)))

        # 4. Intermediate heading vector: x_C = [cos(psi_des), sin(psi_des), 0]^T
        x_c = np.array([math.cos(psi_des), math.sin(psi_des), 0.0], dtype=np.float64)

        # 5. Body y-axis: y_B = (z_B x x_C) / ||z_B x x_C||
        y_b_raw = np.cross(z_b, x_c)
        y_b_norm = float(np.linalg.norm(y_b_raw))
        if y_b_norm < 1e-8:
            y_b = np.array([-math.sin(psi_des), math.cos(psi_des), 0.0], dtype=np.float64)
        else:
            y_b = y_b_raw / y_b_norm

        # 6. Body x-axis: x_B = y_B x z_B
        x_b = np.cross(y_b, z_b)
        x_b /= float(np.linalg.norm(x_b))

        # 7. Desired rotation matrix R_des = [x_B, y_B, z_B] in SO(3)
        r_des = np.column_stack((x_b, y_b, z_b))

        # 8. Unit quaternion q_des = [w, x, y, z] and ZYX Euler angles
        q_des = _rotation_matrix_to_quaternion_wxyz(r_des)
        roll_rad, pitch_rad, yaw_rad = _rotation_matrix_to_euler_zyx(r_des)

        return FlatnessSetpoint(
            a_app=a_app,
            thrust=thrust,
            thrust_normalized=thrust_normalized,
            x_b=x_b,
            y_b=y_b,
            z_b=z_b,
            R_des=r_des,
            q_des=q_des,
            roll_rad=roll_rad,
            pitch_rad=pitch_rad,
            yaw_rad=yaw_rad,
            tilt_rad=tilt_rad,
            tilt_clamped=tilt_clamped,
        )

    __call__ = convert
