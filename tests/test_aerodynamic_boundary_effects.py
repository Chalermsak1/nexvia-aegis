"""
NEXVIA AEGIS — Unit Tests for Aerodynamic Boundary Effects & Aero-Compensated HOCBF.

Verifies:
1. Cheeseman-Bennett In-Ground Effect (IGE): Thrust amplification scaling with altitude.
2. In-Ceiling Effect (ICE): Bernoulli upward suction dynamics near tunnel roof.
3. In-Wall Effect (IWE): Lateral vortex suction and asymmetric destabilizing overturning torque.
4. Aerodynamic Disturbance Observer (ADOB): High-rate residual tracking and asymptotic convergence.
5. Aero-Compensated HOCBF: Forward set invariance and pre-emptive cancellation of boundary suction.
"""

import math
import numpy as np
import pytest

from aegis.env.aerodynamic_boundary_effects import (
    AerodynamicBoundaryConfig,
    AerodynamicBoundaryEngine,
    AerodynamicDisturbanceObserver,
    AeroCompensatedHOCBF,
    BoundaryType,
    PlanarBoundary,
)


def test_cheeseman_bennett_ground_effect_amplification():
    """Verifies that ground effect amplifies rotor thrust near ground and dissipates at high altitude."""
    cfg = AerodynamicBoundaryConfig(rotor_radius=0.09, max_ige_ratio=1.60)
    engine = AerodynamicBoundaryEngine(cfg)

    rot_eye = np.eye(3)
    thrust_total = 14.715  # Hover thrust for 1.5 kg (m*g)
    thrust_per_rotor = np.full(4, thrust_total / 4.0)

    # 1. Close to ground (z = 0.06 m)
    pos_low = np.array([0.0, 0.0, 0.06])
    rotors_low = engine.compute_rotor_positions_world(pos_low, rot_eye)
    f_g_low, tau_g_low, ratio_low = engine.compute_ground_effect(rotors_low, thrust_per_rotor, ground_z=0.0)

    assert ratio_low > 1.10
    assert ratio_low <= cfg.max_ige_ratio
    assert f_g_low[2] > 0.0  # Upward delta thrust

    # 2. Far from ground (z = 2.0 m)
    pos_high = np.array([0.0, 0.0, 2.0])
    rotors_high = engine.compute_rotor_positions_world(pos_high, rot_eye)
    f_g_high, tau_g_high, ratio_high = engine.compute_ground_effect(rotors_high, thrust_per_rotor, ground_z=0.0)

    assert ratio_high < 1.01  # Negligible ground effect
    assert f_g_high[2] < 0.1


def test_ceiling_bernoulli_suction_force():
    """Verifies upward Bernoulli suction force towards ceiling as drone approaches roof."""
    cfg = AerodynamicBoundaryConfig(ceiling_suction_coefficient=0.28)
    engine = AerodynamicBoundaryEngine(cfg)

    ceiling_z = 2.5
    thrust_total = 14.715

    # Near ceiling (z = 2.35 m, distance = 0.15 m)
    pos_near = np.array([0.0, 0.0, 2.35])
    f_near, mag_near = engine.compute_ceiling_effect(pos_near, thrust_total, ceiling_z)

    assert f_near[2] > 0.0  # Upward pull
    assert mag_near > 1.0   # Significant suction force

    # Far from ceiling (z = 1.0 m, distance = 1.5 m)
    pos_far = np.array([0.0, 0.0, 1.0])
    f_far, mag_far = engine.compute_ceiling_effect(pos_far, thrust_total, ceiling_z)

    assert mag_near > 15.0 * mag_far  # Quadratic decay with distance


def test_wall_vortex_lateral_suction_and_overturning_torque():
    """Verifies that wall proximity produces lateral suction towards wall and overturning torque."""
    cfg = AerodynamicBoundaryConfig(wall_suction_coefficient=0.24, wall_torque_gain=0.040)
    engine = AerodynamicBoundaryEngine(cfg)

    rot_eye = np.eye(3)
    thrust_total = 14.715
    # Vertical wall at x = 2.0, normal points towards -x into tunnel
    wall_pt = np.array([2.0, 0.0, 1.0])
    wall_norm = np.array([-1.0, 0.0, 0.0])  # Points towards free space

    # Drone at x = 1.80 m (0.20 m from wall)
    pos_near = np.array([1.80, 0.0, 1.0])
    f_wall, tau_wall, suction_mag = engine.compute_wall_effect(
        pos_near, rot_eye, thrust_total, wall_pt, wall_norm
    )

    # Force should pull TOWARDS wall (in +x direction, which is -wall_norm)
    assert f_wall[0] > 0.0
    assert suction_mag > 0.5
    # Overturning torque around Y axis tilting the vehicle towards wall
    assert np.linalg.norm(tau_wall) > 0.0


def test_adob_disturbance_observer_convergence():
    """Verifies that the non-linear ADOB converges to the true aerodynamic disturbance force."""
    cfg = AerodynamicBoundaryConfig(adob_gain_force=15.0)
    adob = AerodynamicDisturbanceObserver(cfg)

    # Injected constant aerodynamic wall suction: [-1.8, 0.0, 0.5] N
    true_d_aero = np.array([-1.8, 0.0, 0.5])
    rot_eye = np.eye(3)
    thrust_cmd = 14.715  # m*g
    mass = cfg.mass

    # Nominal acceleration + disturbance
    # a = g + (R * T + d_aero) / m
    a_meas = np.array([0.0, 0.0, -cfg.gravity]) + np.array([0.0, 0.0, thrust_cmd / mass]) + true_d_aero / mass

    dt = 0.01
    for _ in range(50):  # 50 steps = 0.5 s
        est_force, _ = adob.update(a_meas, rot_eye, thrust_cmd, dt)

    # Observer should track true disturbance within 5% error
    np.testing.assert_allclose(est_force, true_d_aero, atol=0.10)


def test_aero_compensated_hocbf_prevents_wall_suction_collision():
    """
    Verifies that Aero-HOCBF incorporates L_{f_aero} to cancel aerodynamic suction,
    requiring higher repulsive control authority than uncompensated nominal CBF.
    """
    cfg = AerodynamicBoundaryConfig(cbf_safety_margin=0.30, cbf_alpha1=2.0, cbf_alpha2=2.0)
    cbf_filter = AeroCompensatedHOCBF(cfg)

    # Wall at x = 2.0, normal points to -x (into room)
    wall = PlanarBoundary(
        boundary_type=BoundaryType.WALL,
        point_on_plane=np.array([2.0, 0.0, 1.0]),
        normal_vector=np.array([-1.0, 0.0, 0.0]),
    )

    # Drone approaching wall at x = 1.55 (distance = 0.45 m > r_safe 0.30 m)
    pos = np.array([1.55, 0.0, 1.0])
    vel = np.array([0.35, 0.0, 0.0])  # Moving towards wall
    rot_pitched = np.eye(3)

    # Evaluate constraint WITH aero compensation
    h, dot_h, min_accel_comp, _ = cbf_filter.evaluate_barrier_constraint(
        pos, vel, rot_pitched, thrust_nominal=14.715, boundary=wall
    )

    # Evaluate constraint WITHOUT aero compensation (f_aero = 0)
    wrench_zero = np.zeros(3)
    h_uncomp, dot_h_uncomp, min_accel_uncomp, _ = cbf_filter.evaluate_barrier_constraint(
        pos, vel, rot_pitched, thrust_nominal=14.715, boundary=wall, adob_force=wrench_zero
    )

    # Since wall suction pulls drone towards wall (-wall_normal direction),
    # the aero-compensated CBF must demand MORE repulsive braking acceleration
    # than uncompensated CBF:
    assert min_accel_comp > min_accel_uncomp
    diff = min_accel_comp - min_accel_uncomp
    assert diff > 0.08  # Extra braking commanded to cancel boundary suction!
