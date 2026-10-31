"""
Unit Tests for NEXVIA AEGIS — Air-Ground Heterogeneous Collaborative Teaming & Safety.

Verifies:
1. V2A Telemetry packet construction, hash integrity, and serialization.
2. Ville Supermartingale betting filter detection and quarantine of spoofed phantom hazard attacks.
3. Ville Supermartingale acceptance and verification of legitimate multi-frame aerial hazard reports.
4. Lookahead Frenet CBF progressive preview deceleration vs late emergency skidding.
5. Full closed-loop Air-Ground Heterogeneous Coordinator execution.
"""

import math
import numpy as np
import pytest

from aegis.av.vehicle_dynamics import FrenetFrame, VehicleConfig, VehicleState
from aegis.heterogeneous.air_ground_teaming import (
    AirGroundConfig,
    AirGroundFrenetCBF,
    AirGroundHeterogeneousCoordinator,
    AirGroundVilleFilter,
    V2ATelemetryPacket,
)


@pytest.fixture
def curved_road_frame() -> FrenetFrame:
    """Creates a curved highway Frenet frame (straight + 80m bend + straight)."""
    s_straight1 = np.linspace(0, 100, 50)
    theta_curve = np.linspace(0, math.pi / 3.0, 60)
    R_curve = 80.0
    curve_x = 100.0 + R_curve * np.sin(theta_curve)
    curve_y = R_curve * (1.0 - np.cos(theta_curve))
    s_straight2 = np.linspace(0, 100, 50)
    end_angle = math.pi / 3.0
    end_x = curve_x[-1] + s_straight2 * math.cos(end_angle)
    end_y = curve_y[-1] + s_straight2 * math.sin(end_angle)

    waypoints = np.column_stack([
        np.concatenate([s_straight1, curve_x, end_x]),
        np.concatenate([np.zeros(len(s_straight1)), curve_y, end_y]),
    ])
    return FrenetFrame(waypoints)


def test_v2a_telemetry_packet_and_hash():
    """Validates V2A telemetry creation, hashing, and field properties."""
    pkt = V2ATelemetryPacket(
        drone_id="DRONE_SCOUT_01",
        timestamp=1.24,
        drone_pos=np.array([120.0, 15.0, 18.0]),
        drone_vel=np.array([20.0, 2.0, 0.0]),
        detected_hazard_s=145.0,
        hazard_type="OBSTACLE",
        estimated_friction=0.35,
        confidence=0.96,
        packet_seq=42,
    )
    assert len(pkt.packet_hash) == 16
    assert pkt.detected_hazard_s == 145.0
    assert pkt.hazard_type == "OBSTACLE"


def test_ville_supermartingale_detects_spoofed_phantom_hazard():
    """Validates that erratic/unphysical phantom hazard reports trigger wealth explosion and quarantine."""
    v_filter = AirGroundVilleFilter(alpha=0.001) # threshold = 1000
    v_filter.reset()

    assert v_filter.wealth == 1.0
    assert not v_filter.is_quarantined

    # Simulate rogue attacker injecting erratic phantom hazards (jumping wildly from 60m to 120m to 20m)
    jump_stations = [60.0, 120.0, 30.0, 200.0, 15.0, 95.0]
    for i, s_fake in enumerate(jump_stations):
        pkt = V2ATelemetryPacket(
            drone_id="ROGUE_DRONE",
            timestamp=float(i) * 0.1,
            drone_pos=np.zeros(3),
            drone_vel=np.zeros(3),
            detected_hazard_s=s_fake,
            hazard_type="OBSTACLE",
            estimated_friction=0.20,
            confidence=0.90,
            packet_seq=i,
        )
        is_verified, wealth = v_filter.update(
            packet=pkt,
            current_vehicle_s=50.0, # car is at s = 50m
            current_speed=20.0,
        )
        assert not is_verified # must never verify sporadic spoofed attacks

    # Wealth must have exploded past 1000
    assert v_filter.wealth >= 1000.0
    assert v_filter.is_quarantined


def test_ville_supermartingale_passes_verified_consistent_hazard():
    """Validates that consistent multi-frame detection of real stationary obstacle passes the filter."""
    v_filter = AirGroundVilleFilter(alpha=0.001)
    v_filter.reset()

    # Simulate true obstacle at s = 145m with minor sensor noise (+/- 0.2m)
    verified_flag = False
    for i in range(5):
        s_meas = 145.0 + 0.1 * math.sin(i)
        pkt = V2ATelemetryPacket(
            drone_id="DRONE_SCOUT_01",
            timestamp=float(i) * 0.1,
            drone_pos=np.array([100.0, 10.0, 18.0]),
            drone_vel=np.array([20.0, 0.0, 0.0]),
            detected_hazard_s=s_meas,
            hazard_type="OBSTACLE",
            estimated_friction=0.28,
            confidence=0.95,
            packet_seq=i,
        )
        is_verified, wealth = v_filter.update(
            packet=pkt,
            current_vehicle_s=40.0 + i * 2.0, # car moving forward smoothly
            current_speed=20.0,
        )
        if is_verified:
            verified_flag = True

    assert verified_flag
    assert not v_filter.is_quarantined
    assert v_filter.wealth < 1000.0


def test_air_ground_frenet_cbf_preview_deceleration(curved_road_frame: FrenetFrame):
    """Validates that lookahead preview CBF commands smooth, progressive deceleration well in advance."""
    shield = AirGroundFrenetCBF(road_frame=curved_road_frame)

    # Car at s = 50m, traveling at 18 m/s (65 km/h)
    state = VehicleState(
        x=50.0,
        y=0.0,
        yaw=0.0,
        v_x=18.0,
        v_y=0.0,
        yaw_rate=0.0,
        steering=0.0,
        accel=0.0,
    )

    # 1. No hazard: car continues cruising
    cmd_clear = shield.filter_air_ground_command(
        state=state,
        nominal_accel=0.5,
        nominal_steering=0.0,
        dt=0.02,
        verified_hazard_s=None,
    )
    assert cmd_clear.accel_cmd > 0.0

    # 2. Aerial scout alerts of verified obstacle at s = 140m (90m ahead) on wet road (mu = 0.35)
    cmd_preview = shield.filter_air_ground_command(
        state=state,
        nominal_accel=0.5,
        nominal_steering=0.0,
        dt=0.02,
        verified_hazard_s=140.0,
        preview_friction=0.35,
    )
    # Must command safe deceleration
    assert cmd_preview.accel_cmd < 0.0
    # Must be within comfort limits (e.g. between -1.0 and -4.0 m/s^2), not emergency skidding (-8.0)
    assert -4.5 <= cmd_preview.accel_cmd <= -1.0
    assert "AERIAL_PREVIEW_STOP" in cmd_preview.active_barriers


def test_heterogeneous_coordinator_closed_loop_execution(curved_road_frame: FrenetFrame):
    """Validates joint closed-loop stepping of aerial scout and autonomous vehicle."""
    coordinator = AirGroundHeterogeneousCoordinator(road_frame=curved_road_frame)
    coordinator.reset(initial_s=20.0, initial_v=18.0)

    # Step for 30 cycles (0.6s) with verified obstacle at s = 150m
    for _ in range(30):
        step_res = coordinator.step(
            dt=0.02,
            nominal_accel=0.0,
            nominal_steering=0.0,
            real_hazard_s=150.0,
            real_hazard_friction=0.30,
            use_aegis_ville_guard=True,
            use_aegis_preview_cbf=True,
        )
        assert not math.isnan(step_res["vehicle_x"])
        assert not math.isnan(step_res["vehicle_y"])
        assert not math.isnan(step_res["vehicle_speed"])
        assert not step_res["collision"]

    # Aerial scout should have moved forward in formation
    assert coordinator.drone_pos[0] > 20.0
    assert coordinator.drone_pos[2] > 15.0 # maintaining altitude
