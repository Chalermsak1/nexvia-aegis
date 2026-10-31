"""
Unit Tests for NEXVIA AEGIS — Deep Aerodynamics & Electromechanical Physics Engine.

Verifies:
1. Cheeseman-Bennett Ground Effect (IGE) analytical curve, boundary limits, and altitude decay.
2. Gyroscopic Precession cross-axis reaction moments (tau_gyro = - Omega x H_rotors).
3. 4S LiPo battery discharge dynamics, internal resistance voltage sag, and thrust derating.
4. Single 6-DOF quadrotor closed-loop flight with full deep aerodynamics active.
5. Multi-Agent 6-DOF swarm flight under deep aerodynamics with independent battery degradation.
"""

import math
import numpy as np
import pytest

from aegis.env.deep_aerodynamics import (
    DeepAerodynamicsConfig,
    DeepAerodynamicsEngine,
    DeepAerodynamicsState,
)
from aegis.env.quadrotor_6dof import (
    AegisQuadrotor6DOFEnvironment,
    QuadrotorConfig,
    quaternion_to_rotation_matrix,
)
from aegis.multiagent.swarm_6dof import (
    AegisMuJoCoSwarm6DOFEnvironment,
    Swarm6DOFConfig,
)


def test_ige_analytical_curve_and_decay():
    """Validates Cheeseman-Bennett formula and altitude decay."""
    engine = DeepAerodynamicsEngine(DeepAerodynamicsConfig(
        rotor_radius=0.10,
        max_ige_ratio=1.50,
        ige_enabled=True,
    ))

    base_thrusts = np.array([3.0, 3.0, 3.0, 3.0], dtype=np.float64)
    R_eye = np.eye(3, dtype=np.float64)

    # 1. High altitude: z = 1.5m (15 * R_rotor) -> IGE should be 1.0 (OGE)
    pos_high = np.array([0.0, 0.0, 1.5], dtype=np.float64)
    thrusts_high, ratios_high = engine.compute_ige_thrust(
        base_motor_thrusts=base_thrusts,
        pos_world=pos_high,
        rotation_matrix=R_eye,
        arm_length=0.22,
        floor_z=0.0,
    )
    np.testing.assert_allclose(ratios_high, 1.0, atol=1e-3)
    np.testing.assert_allclose(thrusts_high, base_thrusts, atol=1e-3)

    # 2. Near ground: z_rotor = 0.12m (~ 1.2 * R_rotor)
    # Theoretical ratio: 1 / (1 - (0.10 / (4 * 0.12))^2) = 1 / (1 - (0.2083)^2) = 1 / (1 - 0.0434) ~ 1.0454
    pos_low = np.array([0.0, 0.0, 0.10], dtype=np.float64) # rotor disc at 0.10 + 0.02 = 0.12m
    thrusts_low, ratios_low = engine.compute_ige_thrust(
        base_motor_thrusts=base_thrusts,
        pos_world=pos_low,
        rotation_matrix=R_eye,
        arm_length=0.22,
        floor_z=0.0,
    )
    expected_ratio = 1.0 / (1.0 - (0.10 / (4.0 * 0.12))**2)
    np.testing.assert_allclose(ratios_low, expected_ratio, atol=0.01)
    assert np.all(thrusts_low > base_thrusts)

    # 3. Floor contact: z -> 0 -> Clamped at max_ige_ratio (1.50) without NaN
    pos_floor = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    thrusts_floor, ratios_floor = engine.compute_ige_thrust(
        base_motor_thrusts=base_thrusts,
        pos_world=pos_floor,
        rotation_matrix=R_eye,
        arm_length=0.22,
        floor_z=0.0,
    )
    assert np.all(ratios_floor <= 1.50)
    assert np.all(ratios_floor >= 1.0)
    assert not np.isnan(ratios_floor).any()


def test_ige_differential_bank_stiffness():
    """Tests that roll banking near the floor causes asymmetric ground cushion lift."""
    engine = DeepAerodynamicsEngine(DeepAerodynamicsConfig(
        rotor_radius=0.10,
        max_ige_ratio=1.50,
        ige_enabled=True,
    ))

    # Bank 20 deg roll to the right (positive roll: right motors are lower)
    roll_angle = math.radians(20.0)
    R_roll = np.array([
        [1.0, 0.0, 0.0],
        [0.0, math.cos(roll_angle), -math.sin(roll_angle)],
        [0.0, math.sin(roll_angle),  math.cos(roll_angle)],
    ], dtype=np.float64)

    pos = np.array([0.0, 0.0, 0.08], dtype=np.float64)
    base_thrusts = np.array([3.0, 3.0, 3.0, 3.0], dtype=np.float64)

    thrusts, ratios = engine.compute_ige_thrust(
        base_motor_thrusts=base_thrusts,
        pos_world=pos,
        rotation_matrix=R_roll,
        arm_length=0.22,
        floor_z=0.0,
    )

    # In X-configuration:
    # Motor 0 (+y) and Motor 1 (+y) are on one side; Motor 2 (-y) and Motor 3 (-y) are on the other side.
    # When rolling, one side is closer to the ground and experiences higher IGE ratio
    assert ratios[2] != ratios[1] or ratios[3] != ratios[0]
    assert np.max(ratios) > np.min(ratios)


def test_gyroscopic_precession_moments():
    """Validates cross-axis gyroscopic reaction torque tau_gyro = - Omega x H."""
    cfg = DeepAerodynamicsConfig(
        rotor_inertia=1.0e-4,
        thrust_coefficient=1.0e-5,
        gyroscopic_enabled=True,
    )
    engine = DeepAerodynamicsEngine(cfg)

    # 1. Balanced Hover: Motors 0 & 2 (CCW, +1), Motors 1 & 3 (CW, -1) have equal thrust
    balanced_thrusts = np.array([3.0, 3.0, 3.0, 3.0], dtype=np.float64)
    # Omega_body has pitch rate: w_y = 2.0 rad/s
    omega_pitch = np.array([0.0, 2.0, 0.0], dtype=np.float64)
    tau_balanced = engine.compute_gyroscopic_moments(balanced_thrusts, omega_pitch)
    # With identical rotor speeds, H_z = 0 -> tau_gyro = 0
    np.testing.assert_allclose(tau_balanced, np.zeros(3), atol=1e-8)

    # 2. Differentiated Rotors (e.g. Yaw Command): CCW rotors spin faster than CW rotors
    # Motor 0 & 2: 4.5N, Motor 1 & 3: 1.5N -> Net H_z > 0
    diff_thrusts = np.array([4.5, 1.5, 4.5, 1.5], dtype=np.float64)
    tau_pitching = engine.compute_gyroscopic_moments(diff_thrusts, omega_pitch)

    # Pitching up (w_y > 0) with H_z > 0 produces cross-axis roll moment tau_x = -w_y * H_z < 0
    assert tau_pitching[0] < 0.0
    assert abs(tau_pitching[1]) < 1e-8  # no direct pitch gyroscopic torque
    assert abs(tau_pitching[2]) < 1e-8  # no z-axis gyroscopic torque

    # 3. Rolling right (w_x > 0) with H_z > 0 produces cross-axis pitch moment tau_y = w_x * H_z > 0
    omega_roll = np.array([2.0, 0.0, 0.0], dtype=np.float64)
    tau_rolling = engine.compute_gyroscopic_moments(diff_thrusts, omega_roll)
    assert tau_rolling[1] > 0.0
    assert abs(tau_rolling[0]) < 1e-8


def test_battery_voltage_sag_and_thrust_derating():
    """Validates 4S LiPo battery discharge, internal resistance sag, and thrust derate."""
    cfg = DeepAerodynamicsConfig(
        nominal_voltage=14.8,
        full_voltage=16.8,
        cutoff_voltage=12.8,
        battery_capacity_ah=2.2,
        internal_resistance=0.035,
        avionics_current=0.5,
        battery_enabled=True,
    )
    engine = DeepAerodynamicsEngine(cfg)
    engine.reset(initial_soc=1.0)

    # Initially at SoC = 1.0, V_ocv = 16.8V
    assert math.isclose(engine.state.v_ocv, 16.8, abs_tol=0.05)

    # Test Voltage Sag: step under high motor thrust (4 x 6.0N = 24N)
    high_thrusts = np.array([6.0, 6.0, 6.0, 6.0], dtype=np.float64)
    v_term, derate, eff_max = engine.step_battery_dynamics(high_thrusts, dt=0.02, nominal_max_thrust=8.5)

    # Terminal voltage must sag below OCV: V_term = V_ocv - I * R_int
    assert v_term < engine.state.v_ocv
    assert engine.state.load_current > 10.0  # heavy current draw
    assert engine.state.soc < 1.0           # charge consumed
    assert engine.state.energy_consumed_wh > 0.0

    # Test Depleted Battery: start at SoC = 0.05 (near cutoff)
    engine.reset(initial_soc=0.05)
    v_depleted, derate_depleted, eff_max_depleted = engine.step_battery_dynamics(
        high_thrusts, dt=0.02, nominal_max_thrust=8.5
    )
    # Voltage should be near cutoff (~12.8V or below under load)
    assert v_depleted < 13.5
    # Max thrust derates as (V_term / 14.8)^2 < 1.0
    assert derate_depleted < 0.85
    assert eff_max_depleted < (8.5 * 0.85)


def test_single_quadrotor_6dof_deep_aero_flight():
    """Tests closed-loop flight of single 6-DOF quadrotor with deep aero active."""
    cfg = QuadrotorConfig(
        enable_deep_aerodynamics=True,
        deep_aero_config=DeepAerodynamicsConfig(
            ige_enabled=True,
            gyroscopic_enabled=True,
            battery_enabled=True,
        ),
    )
    env = AegisQuadrotor6DOFEnvironment(cfg)
    state = env.reset(initial_soc=0.90)

    assert state["deep_aero"] is not None
    assert state["deep_aero"]["soc"] == 0.90
    assert state["deep_aero"]["v_terminal"] > 14.0

    # Command flight toward target for 40 outer steps (0.8s)
    k_p = 3.5
    k_d = 2.0
    for step in range(40):
        pos = state["pos"]
        vel = state["vel"]
        f_nav = k_p * (env.target_pos - pos) - k_d * vel
        f_nav[2] += cfg.mass * cfg.gravity

        state, _ = env.step_outer(desired_force_world=f_nav, shield_with_cbf=True)

        assert not np.isnan(state["pos"]).any()
        assert not np.isnan(state["vel"]).any()
        assert state["deep_aero"] is not None
        assert state["deep_aero"]["soc"] <= 0.90
        assert len(state["deep_aero"]["ige_ratios"]) == 4

    # Quadrotor should have progressed towards target while remaining stable
    dist_final = state["distance"]
    dist_initial = float(np.linalg.norm(np.array([-1.8, -1.8, 0.5]) - env.target_pos))
    assert dist_final < dist_initial


def test_swarm_6dof_deep_aero_flight():
    """Tests multi-agent 6-DOF swarm with 5 quadrotors running deep aerodynamics."""
    cfg = Swarm6DOFConfig(
        num_robots=5,
        enable_deep_aerodynamics=True,
        deep_aero_config=DeepAerodynamicsConfig(
            ige_enabled=True,
            gyroscopic_enabled=True,
            battery_enabled=True,
        ),
    )
    env = AegisMuJoCoSwarm6DOFEnvironment(cfg)
    state = env.reset(initial_soc=0.85)

    assert state["deep_aero"] is not None
    assert len(state["deep_aero"]) == 5
    for a_info in state["deep_aero"]:
        assert math.isclose(a_info["soc"], 0.85, abs_tol=1e-3)
        assert a_info["effective_max_thrust"] > 0.0

    # Step swarm for 25 outer steps
    rng = np.random.default_rng(42)
    k_p = 3.0
    k_d = 1.8

    for _ in range(25):
        forces = []
        for i in range(cfg.num_robots):
            pos_i = state["positions"][i]
            vel_i = state["velocities"][i]
            f_i = k_p * (env.target_pos - pos_i) - k_d * vel_i
            f_i[2] += cfg.mass * cfg.gravity
            forces.append(f_i)

        state, barriers = env.step_outer(
            desired_forces=forces,
            shield_with_cbf=True,
            rng=rng,
        )

        for i in range(cfg.num_robots):
            assert not np.isnan(state["positions"][i]).any()
            assert not np.isnan(state["velocities"][i]).any()
            assert state["deep_aero"][i]["soc"] <= 0.85

    assert state["inter_agent_collisions"] == 0


def test_ornstein_uhlenbeck_wind_turbulence():
    """Validates Ornstein-Uhlenbeck continuous stochastic wind dynamics and mean-reversion."""
    cfg = DeepAerodynamicsConfig(
        wind_enabled=True,
        wind_mean=(2.5, -1.0, 0.5),
        wind_theta=2.0,
        wind_sigma=0.30,
    )
    engine = DeepAerodynamicsEngine(cfg)
    engine.reset(initial_wind=np.zeros(3))
    np.testing.assert_allclose(engine.state.wind_velocity, np.zeros(3))

    rng = np.random.default_rng(1234)
    dt = 0.01
    # Run for 300 steps (3.0 seconds)
    for _ in range(300):
        engine.step_wind_turbulence(dt=dt, rng=rng)

    # After 3.0s, with theta=2.0 (time constant 0.5s), wind should have converged near mean
    mean_vec = np.array([2.5, -1.0, 0.5], dtype=np.float64)
    np.testing.assert_allclose(engine.state.wind_velocity, mean_vec, atol=0.65)


def test_discrete_1cosine_wind_gust_profile():
    """Validates MIL-F-8785C 1-cosine wind gust shape, midpoint peak, and boundaries."""
    cfg = DeepAerodynamicsConfig(
        gust_enabled=True,
        gust_amplitude=(4.0, 2.0, -1.0),
        gust_start_time=1.0,
        gust_duration=2.0,
    )
    engine = DeepAerodynamicsEngine(cfg)

    amp_vec = np.array([4.0, 2.0, -1.0], dtype=np.float64)

    # 1. Before gust start (t = 0.5s) -> 0
    w_before = engine.compute_gust_velocity(current_time=0.5)
    np.testing.assert_allclose(w_before, np.zeros(3), atol=1e-8)

    # 2. At gust start (t = 1.0s, tau = 0.0) -> 0
    w_start = engine.compute_gust_velocity(current_time=1.0)
    np.testing.assert_allclose(w_start, np.zeros(3), atol=1e-8)

    # 3. At peak midpoint (t = 2.0s, tau = 0.5) -> 100% amplitude
    w_peak = engine.compute_gust_velocity(current_time=2.0)
    np.testing.assert_allclose(w_peak, amp_vec, atol=1e-6)

    # 4. At quarter point (t = 1.5s, tau = 0.25) -> 0.5 * (1 - cos(pi/2)) = 0.5 * (1 - 0) = 0.5
    w_quarter = engine.compute_gust_velocity(current_time=1.5)
    np.testing.assert_allclose(w_quarter, 0.5 * amp_vec, atol=1e-6)

    # 5. At gust end (t = 3.0s, tau = 1.0) -> 0
    w_end = engine.compute_gust_velocity(current_time=3.0)
    np.testing.assert_allclose(w_end, np.zeros(3), atol=1e-8)

    # 6. After gust (t = 3.5s) -> 0
    w_after = engine.compute_gust_velocity(current_time=3.5)
    np.testing.assert_allclose(w_after, np.zeros(3), atol=1e-8)


def test_aerodynamic_drag_force_quadratic_scaling():
    """Validates quadratic body drag scaling F_drag = -0.5 * rho * CdA * ||v_rel|| * v_rel."""
    cfg = DeepAerodynamicsConfig(
        drag_enabled=True,
        air_density=1.225,
        drag_area_product=0.040,
    )
    engine = DeepAerodynamicsEngine(cfg)

    # Speed 1: v = [2.0, 0.0, 0.0], zero wind
    v1 = np.array([2.0, 0.0, 0.0], dtype=np.float64)
    w_zero = np.zeros(3, dtype=np.float64)
    f1, _ = engine.compute_aerodynamic_drag(drone_velocity=v1, total_wind=w_zero)

    # Expected: -0.5 * 1.225 * 0.040 * 2.0 * [2.0, 0, 0] = -0.098 N
    np.testing.assert_allclose(f1, np.array([-0.098, 0.0, 0.0]), atol=1e-5)

    # Speed 2: double airspeed v = [4.0, 0.0, 0.0] -> drag should quadruple
    v2 = np.array([4.0, 0.0, 0.0], dtype=np.float64)
    f2, _ = engine.compute_aerodynamic_drag(drone_velocity=v2, total_wind=w_zero)
    np.testing.assert_allclose(f2, 4.0 * f1, atol=1e-5)

    # Tail wind test: drone velocity = [4.0, 0, 0], tail wind = [4.0, 0, 0] -> v_rel = 0 -> F_drag = 0
    w_tail = np.array([4.0, 0.0, 0.0], dtype=np.float64)
    f_tail, _ = engine.compute_aerodynamic_drag(drone_velocity=v2, total_wind=w_tail)
    np.testing.assert_allclose(f_tail, np.zeros(3), atol=1e-8)


def test_ground_effect_vortex_shear_torque():
    """Validates ground vortex destabilizing shear torque near ground and high altitude decay."""
    cfg = DeepAerodynamicsConfig(
        rotor_radius=0.10,
        ground_shear_coefficient=0.15,
    )
    engine = DeepAerodynamicsEngine(cfg)
    R_eye = np.eye(3, dtype=np.float64)

    # Drone flying forward: v_rel = [3.0, 0.0, 0.0]
    v_rel = np.array([3.0, 0.0, 0.0], dtype=np.float64)

    # 1. Close to ground: z = 0.05m (< 2 * R_rotor)
    pos_low = np.array([0.0, 0.0, 0.05], dtype=np.float64)
    tau_low = engine.compute_ground_shear_torque(
        pos_world=pos_low,
        v_rel_world=v_rel,
        rotation_matrix=R_eye,
        floor_z=0.0,
    )
    # Cross product [3, 0, 0] x [0, 0, 1] = [0, -3, 0] -> pitch down torque
    assert tau_low[1] < -0.20
    assert abs(tau_low[0]) < 1e-8
    assert abs(tau_low[2]) < 1e-8

    # 2. High altitude: z = 1.20m (12 * R_rotor) -> decays towards zero
    pos_high = np.array([0.0, 0.0, 1.20], dtype=np.float64)
    tau_high = engine.compute_ground_shear_torque(
        pos_world=pos_high,
        v_rel_world=v_rel,
        rotation_matrix=R_eye,
        floor_z=0.0,
    )
    assert abs(tau_high[1]) < 0.002
    assert abs(tau_high[1]) < abs(tau_low[1]) * 0.01


def test_quadrotor_6dof_flight_under_crosswind_gust():
    """Validates single 6-DOF quadrotor closed-loop flight under wind turbulence and 1-cosine gust."""
    cfg = QuadrotorConfig(
        enable_deep_aerodynamics=True,
        deep_aero_config=DeepAerodynamicsConfig(
            ige_enabled=True,
            gyroscopic_enabled=True,
            battery_enabled=True,
            wind_enabled=True,
            wind_mean=(1.5, 0.0, 0.0),
            gust_enabled=True,
            gust_amplitude=(3.0, 1.5, 0.0),
            gust_start_time=0.2,
            gust_duration=0.6,
            drag_enabled=True,
            ground_shear_coefficient=0.10,
        ),
    )
    env = AegisQuadrotor6DOFEnvironment(cfg)
    state = env.reset(initial_pos=np.array([-1.5, -1.5, 0.6], dtype=np.float64))

    assert "wind_velocity" in state["deep_aero"]
    assert "gust_velocity" in state["deep_aero"]
    assert "aerodynamic_force" in state["deep_aero"]

    k_p = 3.8
    k_d = 2.2
    for step in range(50):
        pos = state["pos"]
        vel = state["vel"]
        f_nav = k_p * (env.target_pos - pos) - k_d * vel
        f_nav[2] += cfg.mass * cfg.gravity

        state, _ = env.step_outer(desired_force_world=f_nav, shield_with_cbf=True)

        assert not np.isnan(state["pos"]).any()
        assert not np.isnan(state["vel"]).any()
        assert not np.isnan(state["deep_aero"]["aerodynamic_force"]).any()

    # Total wind should have been active and recorded
    assert np.linalg.norm(state["deep_aero"]["total_wind"]) > 0.5
    # Quadrotor must not have collided
    assert not state["collision"]

