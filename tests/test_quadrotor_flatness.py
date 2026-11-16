import math
import numpy as np
import pytest

from aegis.bridge.quadrotor_flatness import QuadrotorFlatnessConverter


def _assert_so3_and_unit_quat(sp):
    # R_des^T R_des = I_3 and det(R_des) = +1
    assert np.allclose(sp.R_des.T @ sp.R_des, np.eye(3), atol=1e-9)
    assert math.isclose(float(np.linalg.det(sp.R_des)), 1.0, abs_tol=1e-9)
    # Unit quaternion [w, x, y, z]
    assert sp.q_des.shape == (4,)
    assert math.isclose(float(np.linalg.norm(sp.q_des)), 1.0, abs_tol=1e-9)


def test_quadrotor_flatness_hover():
    """Hover test: a_safe = [0, 0, 0] => phi = 0 deg, theta = 0 deg, T = m * g."""
    mass = 1.5
    converter = QuadrotorFlatnessConverter(
        mass=mass,
        gravity=np.array([0.0, 0.0, -9.81]),
        max_tilt_deg=35.0,
    )
    sp = converter.convert(np.array([0.0, 0.0, 0.0]), psi_des=0.0)

    _assert_so3_and_unit_quat(sp)
    assert math.isclose(sp.roll_deg, 0.0, abs_tol=1e-9)
    assert math.isclose(sp.pitch_deg, 0.0, abs_tol=1e-9)
    assert math.isclose(sp.yaw_deg, 0.0, abs_tol=1e-9)
    assert math.isclose(sp.thrust, mass * 9.81, rel_tol=1e-9)
    assert np.allclose(sp.q_des, np.array([1.0, 0.0, 0.0, 0.0]), atol=1e-9)
    assert not sp.tilt_clamped


def test_quadrotor_flatness_forward_acceleration_pure_pitch():
    """Forward acceleration: a_safe = [2.0, 0, 0] => pure pitch tilt forward."""
    converter = QuadrotorFlatnessConverter(mass=1.5, max_tilt_deg=35.0)
    sp = converter.convert(np.array([2.0, 0.0, 0.0]), psi_des=0.0)

    _assert_so3_and_unit_quat(sp)
    expected_pitch_deg = math.degrees(math.atan2(2.0, 9.81))
    assert math.isclose(sp.pitch_deg, expected_pitch_deg, abs_tol=1e-6)
    assert sp.pitch_deg > 0.0
    assert math.isclose(sp.roll_deg, 0.0, abs_tol=1e-9)
    assert math.isclose(sp.yaw_deg, 0.0, abs_tol=1e-9)
    assert sp.z_b[0] > 0.0 and math.isclose(sp.z_b[1], 0.0, abs_tol=1e-9)
    assert not sp.tilt_clamped


def test_quadrotor_flatness_lateral_acceleration_pure_roll():
    """Lateral acceleration: a_safe = [0, 2.0, 0] => pure roll tilt."""
    converter = QuadrotorFlatnessConverter(mass=1.5, max_tilt_deg=35.0)
    sp = converter.convert(np.array([0.0, 2.0, 0.0]), psi_des=0.0)

    _assert_so3_and_unit_quat(sp)
    expected_roll_mag_deg = math.degrees(math.atan2(2.0, 9.81))
    assert math.isclose(abs(sp.roll_deg), expected_roll_mag_deg, abs_tol=1e-6)
    assert math.isclose(sp.pitch_deg, 0.0, abs_tol=1e-9)
    assert math.isclose(sp.yaw_deg, 0.0, abs_tol=1e-9)
    assert sp.z_b[1] > 0.0 and math.isclose(sp.z_b[0], 0.0, abs_tol=1e-9)
    assert not sp.tilt_clamped


def test_quadrotor_flatness_max_tilt_clamping():
    """Extreme acceleration a_safe = [20.0, 0, 0] clamped strictly to <= 35 deg."""
    converter = QuadrotorFlatnessConverter(mass=1.5, max_tilt_deg=35.0)
    sp = converter.convert(np.array([20.0, 0.0, 0.0]), psi_des=0.0)

    _assert_so3_and_unit_quat(sp)
    assert sp.tilt_clamped is True
    assert sp.tilt_deg <= 35.0 + 1e-7
    assert math.isclose(sp.tilt_deg, 35.0, abs_tol=1e-6)
    assert abs(sp.pitch_deg) <= 35.0 + 1e-7
    assert math.isclose(sp.roll_deg, 0.0, abs_tol=1e-9)


def test_quadrotor_flatness_arbitrary_heading_and_diagonal_accel():
    """Verify SE(3) orthogonality and heading tracking under arbitrary yaw and 3D acceleration."""
    converter = QuadrotorFlatnessConverter(mass=1.8, max_tilt_deg=35.0)
    psi_des = math.radians(42.0)
    sp = converter.convert(np.array([1.5, -1.2, 1.0]), psi_des=psi_des)

    _assert_so3_and_unit_quat(sp)
    assert sp.tilt_deg <= 35.0
    # Thrust vector T * z_B must equal m * (a_safe - g) when unclamped
    expected_force = 1.8 * np.array([1.5, -1.2, 1.0 + 9.81])
    assert np.allclose(sp.thrust * sp.z_b, expected_force, atol=1e-8)
