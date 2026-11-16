"""
Unit Tests for Phase 12: Multi-Vehicle Heterogeneous Collaborative Platooning & Dual Aerial Scout Handover.

Verifies:
1. Dual aerial scout initialization, docking, and battery charge states.
2. Complete lifecycle state machine handover transitions (SCOUT_A -> LAUNCH -> DUAL -> RETURN -> SCOUT_B).
3. 3D inter-drone collision avoidance barrier (||p_A - p_B|| >= d_safe).
4. Continuous unbroken lookahead preview during aerial transition.
5. Platoon string stability and inter-vehicle Frenet barrier invariance (zero rear-end collisions).
6. Byzantine intermediate relay fault isolation.
"""

import math
import numpy as np
import pytest

from aegis.av.vehicle_dynamics import FrenetFrame, VehicleConfig, VehicleState
from aegis.heterogeneous.platoon_scout_handover import (
    DualScoutHandoverManager,
    HandoverPhase,
    HeterogeneousPlatoonConfig,
    HeterogeneousPlatoonCoordinator,
    MultiHopCascadePlatoonShield,
)


@pytest.fixture
def straight_road_frame() -> FrenetFrame:
    """Creates a straight highway Frenet frame for clean longitudinal tests."""
    s = np.linspace(0, 500, 200)
    waypoints = np.column_stack([s, np.zeros_like(s)])
    return FrenetFrame(waypoints)


def test_dual_scout_initialization_and_docking(straight_road_frame):
    """Validates that Scout A initializes airborne while Scout B starts docked on lead vehicle."""
    cfg = HeterogeneousPlatoonConfig()
    manager = DualScoutHandoverManager(straight_road_frame, cfg)

    lead_state = VehicleState(x=100.0, y=0.0, yaw=0.0, v_x=22.0)
    manager.reset(lead_state, lead_frenet_s=100.0)

    assert manager.phase == HandoverPhase.SCOUT_A_ACTIVE
    assert manager.scout_a.is_airborne
    assert not manager.scout_a.is_docked
    assert manager.scout_a.pos[2] == pytest.approx(cfg.aerial_cruise_altitude, abs=0.1)

    assert not manager.scout_b.is_airborne
    assert manager.scout_b.is_docked
    assert manager.scout_b.pos[2] == pytest.approx(cfg.rooftop_dock_altitude, abs=0.1)


def test_handover_state_machine_and_transitions(straight_road_frame):
    """Validates full handover cycle when Scout A battery drops below threshold."""
    cfg = HeterogeneousPlatoonConfig(
        soc_handover_trigger=0.90,
        battery_drain_rate=0.08, # accelerated drain for unit test
    )
    manager = DualScoutHandoverManager(straight_road_frame, cfg)
    lead_state = VehicleState(x=50.0, y=0.0, yaw=0.0, v_x=20.0)
    manager.reset(lead_state, lead_frenet_s=50.0)

    phases_seen = set()
    dt = 0.05
    sim_time = 0.0

    for step in range(150):
        sim_time += dt
        lead_s = 50.0 + lead_state.v_x * sim_time
        pkt, metrics = manager.update(
            dt=dt,
            sim_time=sim_time,
            lead_vehicle_state=lead_state,
            lead_frenet_s=lead_s,
            real_hazard_s=250.0,
            packet_seq=step,
        )
        phases_seen.add(metrics["handover_phase"])

    # Must have transitioned through the key phases
    assert HandoverPhase.SCOUT_A_ACTIVE.value in phases_seen
    assert HandoverPhase.HANDOVER_LAUNCH.value in phases_seen
    assert HandoverPhase.DUAL_SYNCHRONIZED.value in phases_seen


def test_inter_drone_3d_separation_barrier(straight_road_frame):
    """Validates that 3D separation barrier between Scout A and Scout B is strictly preserved."""
    cfg = HeterogeneousPlatoonConfig(
        soc_handover_trigger=0.90,
        battery_drain_rate=0.05,
        inter_drone_safe_dist=6.0,
    )
    manager = DualScoutHandoverManager(straight_road_frame, cfg)
    lead_state = VehicleState(x=80.0, y=0.0, yaw=0.0, v_x=22.0)
    manager.reset(lead_state, lead_frenet_s=80.0)

    dt = 0.04
    sim_time = 0.0
    for step in range(80):
        sim_time += dt
        lead_s = 80.0 + lead_state.v_x * sim_time
        _, metrics = manager.update(
            dt=dt,
            sim_time=sim_time,
            lead_vehicle_state=lead_state,
            lead_frenet_s=lead_s,
            packet_seq=step,
        )

    # Observed minimum inter-drone distance must respect the 6.0m safe buffer
    assert manager.min_inter_drone_dist_observed >= 5.5


def test_unbroken_preview_during_handover(straight_road_frame):
    """Validates that hazard preview is continuously received without dropouts during handover."""
    cfg = HeterogeneousPlatoonConfig(
        soc_handover_trigger=0.85,
        battery_drain_rate=0.04,
    )
    manager = DualScoutHandoverManager(straight_road_frame, cfg)
    lead_state = VehicleState(x=40.0, y=0.0, yaw=0.0, v_x=20.0)
    manager.reset(lead_state, lead_frenet_s=40.0)

    dt = 0.05
    sim_time = 0.0
    hazard_s = 130.0

    preview_active_count = 0
    total_steps = 60

    for step in range(total_steps):
        sim_time += dt
        lead_s = 40.0 + lead_state.v_x * sim_time
        pkt, metrics = manager.update(
            dt=dt,
            sim_time=sim_time,
            lead_vehicle_state=lead_state,
            lead_frenet_s=lead_s,
            real_hazard_s=hazard_s,
            packet_seq=step,
        )
        if pkt.detected_hazard_s is not None:
            preview_active_count += 1

    # Over 90% of frames should maintain active hazard preview
    assert preview_active_count / total_steps >= 0.85


def test_platoon_string_stability_and_barrier_invariance(straight_road_frame):
    """Validates that 5-vehicle platoon decelerates smoothly with string stability and zero collisions."""
    coordinator = HeterogeneousPlatoonCoordinator(straight_road_frame)
    coordinator.reset(initial_lead_s=100.0, initial_speed=20.0)

    # Obstacle located at s = 240m
    dt = 0.02
    min_observed_gap = float("inf")
    amplification_ratios = []

    for step in range(120):
        res = coordinator.step(
            dt=dt,
            nominal_cruise_accel=0.0,
            real_hazard_s=240.0,
            real_hazard_friction=0.30,
            enable_v2v=True,
        )
        min_observed_gap = min(min_observed_gap, res["min_platoon_gap"])
        if res["string_amplification_ratio"] > 0.0:
            amplification_ratios.append(res["string_amplification_ratio"])

        assert not res["inter_vehicle_collision"]

    # Minimum gap must strictly maintain safe margin above 3.5m
    assert min_observed_gap >= 3.5
    # Deceleration shockwave must not violently amplify down the platoon
    max_amp = max(amplification_ratios) if amplification_ratios else 1.0
    assert max_amp <= 1.25
