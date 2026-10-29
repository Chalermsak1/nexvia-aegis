"""
Unit tests for Autonomous Vehicle (AV) & Cyber-Resilient Platooning Stack.
"""

import math
import numpy as np
import pytest

from aegis.av.autoware_ros2_bridge import AckermannControlCommand, AegisAutowareVehicleNode
from aegis.av.frenet_cbf_shield import FrenetCbfConfig, FrenetSafetyShield
from aegis.av.platooning_brmc import CyberResilientPlatoonController, PlatoonConfig, V2XTelemetryPacket
from aegis.av.vehicle_dynamics import (
    DynamicBicycleModel,
    FrenetFrame,
    VehicleConfig,
    VehicleState,
)


def test_dynamic_bicycle_model_acceleration():
    """Verify RK4 integration, dynamic weight transfer, and forward kinematics."""
    cfg = VehicleConfig(mass=1500.0, friction_coeff=0.85)
    model = DynamicBicycleModel(cfg)

    state = VehicleState(x=0.0, y=0.0, yaw=0.0, v_x=10.0, v_y=0.0, yaw_rate=0.0)

    # Calculate static normal loads (at zero acceleration)
    tires_static = model.compute_tire_forces(10.0, 0.0, 0.0, 0.0, accel=0.0)

    # Accelerate at 2.0 m/s^2 for 0.1s (10 steps)
    dt = 0.01
    for _ in range(10):
        state, tires = model.step(state, cmd_accel=2.0, cmd_steering=0.0, dt=dt)

    assert state.x > 1.0, f"Vehicle should advance forward, got {state.x}"
    assert state.v_x > 10.15, f"Vehicle speed should increase, got {state.v_x}"
    # Acceleration causes dynamic weight transfer: rear load increases, front load decreases
    assert tires.F_zr > tires_static.F_zr, f"Rear load should increase under acceleration: {tires.F_zr} vs static {tires_static.F_zr}"
    assert tires.F_zf < tires_static.F_zf, f"Front load should decrease under acceleration: {tires.F_zf} vs static {tires_static.F_zf}"


def test_kamm_friction_circle_anti_skid():
    """Verify that Kamm's friction circle clamps excessive steering on wet/slippery asphalt."""
    wet_cfg = VehicleConfig(mass=1500.0, friction_coeff=0.35) # Slippery wet road
    shield = FrenetSafetyShield(wet_cfg)

    # Traveling at 20 m/s (~72 km/h)
    state = VehicleState(x=0.0, y=0.0, yaw=0.0, v_x=20.0, v_y=0.0, yaw_rate=0.0)
    waypoints = np.array([[0.0, 0.0], [200.0, 0.0]])
    frame = FrenetFrame(waypoints)
    frenet = frame.cartesian_to_frenet(state.x, state.y, state.yaw, state.v_x)

    # Dangerous driver command: full lock steering 30 degrees on wet asphalt
    dangerous_steer = math.radians(30.0)
    cmd = shield.filter_control(
        state=state,
        frenet=frenet,
        nominal_accel=0.0,
        nominal_steering=dangerous_steer,
    )

    # Shield must intervene and reduce steering angle to preserve adhesion
    assert cmd.barrier_active is True
    assert "TIRE_FRICTION_CIRCLE_KAMM" in cmd.active_barriers
    assert abs(cmd.steering_cmd) < abs(dangerous_steer), "Steering must be clamped to prevent spin-out"


def test_frenet_lane_keeping_hocbf():
    """Verify that high-order CBF enforces lane boundary safety when vehicle drifts."""
    cfg = VehicleConfig()
    cbf_cfg = FrenetCbfConfig(lane_width=3.6, lane_safety_margin=0.2)
    shield = FrenetSafetyShield(cfg, cbf_cfg)

    waypoints = np.array([[0.0, 0.0], [300.0, 0.0]])
    frame = FrenetFrame(waypoints)

    # Vehicle drifting close to the left lane marking (d = +0.62m, d_dot = +0.5 m/s)
    state = VehicleState(x=50.0, y=0.62, yaw=0.05, v_x=15.0, v_y=0.5, yaw_rate=0.0)
    frenet = frame.cartesian_to_frenet(state.x, state.y, state.yaw, state.v_x, state.v_y)

    # Driver requests steering further to the left (+0.10 rad)
    cmd = shield.filter_control(
        state=state,
        frenet=frenet,
        nominal_accel=0.0,
        nominal_steering=0.10,
    )

    assert cmd.barrier_active is True
    assert "LANE_KEEPING_LEFT_HOCBF" in cmd.active_barriers
    assert cmd.steering_cmd < 0.05, "Must counter-steer to prevent crossing left lane marking"


def test_cyber_resilient_platooning_phantom_brake():
    """Verify that Ville supermartingale detects phantom brake attack and evicts V2X sender."""
    p_cfg = PlatoonConfig(martingale_alpha=0.001, betting_lambda=0.4)
    controller = CyberResilientPlatoonController(vehicle_id=2, platoon_config=p_cfg)

    state = VehicleState(v_x=25.0, accel=0.0)
    radar_dist = 18.0
    radar_rel_speed = 0.0 # Following steadily

    # Preceding vehicle initiates Phantom Brake Attack: claims -8.0 m/s^2 brake in V2X,
    # but physical radar shows relative speed remains 0 (actual accel is 0)
    malicious_v2x = V2XTelemetryPacket(
        sender_id=1,
        timestamp=1.0,
        claimed_s=118.0,
        claimed_speed=25.0,
        claimed_accel=-8.0, # Attacker claims emergency brake!
        emergency_flag=True,
    )

    evicted = False
    for step in range(15): # 15 cycles @ 20ms = 0.3s
        t = 1.0 + step * 0.02
        accel_cmd, _, status = controller.update_v2x_and_control(
            current_state=state,
            current_time=t,
            radar_distance=radar_dist,
            radar_rel_speed=radar_rel_speed,
            v2x_packet=malicious_v2x,
        )
        if status.v2x_evicted:
            evicted = True
            break

    assert evicted is True, "Controller must evict malicious V2X sender"
    assert status.martingale_wealth >= 1000.0, f"Wealth must cross 1/alpha (1000), got {status.martingale_wealth}"
    assert status.eviction_timestamp is not None


def test_autoware_ros2_standalone_node():
    """Verify that Autoware node generates valid AckermannControlCommands in standalone mode."""
    straight_road = np.array([[0.0, 0.0], [100.0, 0.0], [200.0, 0.0], [300.0, 0.0]])
    node = AegisAutowareVehicleNode(vehicle_id=1, road_waypoints=straight_road)
    state = VehicleState(x=10.0, y=0.0, yaw=0.0, v_x=12.0)

    cmd, shielded = node.step_standalone(
        current_time=0.10,
        state=state,
        nom_accel=1.5,
        nom_steering=0.02,
    )

    assert isinstance(cmd, AckermannControlCommand)
    assert abs(cmd.steering_tire_angle - 0.02) < 0.05
    assert cmd.acceleration > 0.0
    assert cmd.speed > 12.0
