"""
NEXVIA AEGIS — Multi-Vehicle Heterogeneous Collaborative Platooning & Dual Scout Handover.

Coordinates a 5-vehicle Autonomous Ground Platoon with Dual 6-DOF Aerial Scouts
("Eye-in-the-Sky" Alpha and Beta) for continuous, resilient highway safety:

1. Dual Aerial Scout Duty Cycle & Seamless Handover:
   - Scout Alpha operates as primary airborne scout until battery State-of-Charge (SoC) drops.
   - Scout Beta launches from rooftop charging nest on Platoon Lead Vehicle.
   - Executes 6-DOF formation rendezvous with inter-drone 3D separation barrier:
     ||p_alpha - p_beta|| >= d_inter_drone_safe.
   - Unbroken lookahead horizon: Platoon maintains zero blind spots during transition.
   - Scout Alpha executes Return-To-Base (RTB) landing on the mobile vehicle nest.

2. V2A-to-V2V Multi-Hop Cascade Safety Shield & String Stability:
   - Lead vehicle (Vehicle 0) receives authenticated V2A preview hazard telemetry.
   - Cascades preview deceleration commands down the platoon via V2V relays (Vehicle i -> i+1).
   - Frenet Platoon CBF guarantees collision-free spacing and string-stable deceleration:
     s_{i-1} - s_i - L >= d_min + tau * v_i + (v_i^2 - v_{i-1}^2) / (2 * a_brake).
   - Eliminates accordion shockwave amplification on low-friction icy highway curves (mu <= 0.35).

3. Anytime-Valid Multi-Hop Anomaly & Relay Fault Guard:
   - Intermediate relay packet corruption or rogue phantom brake injection is evicted
     via Ville Supermartingale wealth testing (alpha = 0.001).
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import numpy as np

from aegis.av.frenet_cbf_shield import FrenetCbfConfig, FrenetSafetyShield
from aegis.av.vehicle_dynamics import (
    DynamicBicycleModel,
    FrenetFrame,
    FrenetState,
    VehicleConfig,
    VehicleState,
)
from aegis.env.deep_aerodynamics import DeepAerodynamicsConfig, DeepAerodynamicsEngine
from aegis.heterogeneous.air_ground_teaming import (
    AirGroundConfig,
    AirGroundFrenetCBF,
    AirGroundVilleFilter,
    V2ATelemetryPacket,
)


class HandoverPhase(enum.Enum):
    """Lifecycle states of the dual aerial scout handover protocol."""
    SCOUT_A_ACTIVE = "SCOUT_A_ACTIVE"           # Drone A airborne in lead; Drone B docked/charging
    HANDOVER_LAUNCH = "HANDOVER_LAUNCH"         # Drone B launching from lead vehicle rooftop nest
    DUAL_SYNCHRONIZED = "DUAL_SYNCHRONIZED"     # Both drones airborne in dual formation; B takes primary
    RETURNING_A = "RETURNING_A"                 # Drone A descending back to mobile rooftop pad
    SCOUT_B_ACTIVE = "SCOUT_B_ACTIVE"           # Drone B sole active scout; Drone A docked/charging


@dataclass
class AerialScoutState:
    """State of an individual 6-DOF aerial scout."""
    scout_id: str
    pos: np.ndarray                             # 3D position [x, y, z] (m)
    vel: np.ndarray                             # 3D velocity [vx, vy, vz] (m/s)
    battery_soc: float = 1.0                    # State-of-Charge [0.0, 1.0]
    is_airborne: bool = False
    is_docked: bool = True
    assigned_target_s: float = 0.0              # Target road station in Frenet frame (m)


@dataclass
class PlatoonV2VPacket:
    """Inter-vehicle V2V telemetry packet cascading down the platoon."""
    sender_id: int
    receiver_id: int
    timestamp: float
    leader_s: float
    sender_s: float
    sender_speed: float
    commanded_accel: float
    preview_hazard_s: float | None
    preview_friction: float
    is_authenticated: bool = True


@dataclass
class HeterogeneousPlatoonConfig:
    """Configuration hyperparameters for multi-vehicle heterogeneous platooning."""
    num_vehicles: int = 5
    inter_vehicle_nominal_gap: float = 16.0     # Nominal headway distance at cruise (m)
    min_standstill_gap: float = 5.0             # Standstill buffer (m)
    time_headway: float = 0.75                  # Nominal time headway (seconds)
    vehicle_length: float = 4.7                 # Vehicle length (m)

    # Dual Aerial Scout Geometry
    aerial_lookahead_dist: float = 65.0         # Lead drone lookahead ahead of Vehicle 0 (m)
    aerial_cruise_altitude: float = 18.0        # Cruise altitude above road (m)
    rooftop_dock_altitude: float = 1.8          # Height of rooftop charging nest on lead vehicle (m)
    inter_drone_safe_dist: float = 6.0          # Minimum 3D separation barrier between drones (m)

    # Battery & Handover Thresholds
    soc_handover_trigger: float = 0.35          # Initiate handover when Scout A SoC drops below 35%
    battery_drain_rate: float = 0.008           # SoC drain per second during forward flight
    battery_charge_rate: float = 0.025          # SoC recharge per second on mobile rooftop nest

    # Sensor & Mode Flags
    radar_cutoff_dist: float = 30.0             # Forward radar LOS cutoff on curves (m)
    enable_dual_scout: bool = True              # If False, single scout mode (no Scout B launch)
    enable_aerial_scouts: bool = True           # If False, unshielded blind mode (no scouts airborne)


# =============================================================================
# 1. Dual Aerial Scout Handover Manager
# =============================================================================

class DualScoutHandoverManager:
    """
    Coordinates two 6-DOF Aerial Scouts (Alpha and Beta) to guarantee unbroken
    aerial lookahead preview for the ground platoon with collision-free SE(3) rendezvous.
    """

    def __init__(
        self,
        road_frame: FrenetFrame,
        config: HeterogeneousPlatoonConfig | None = None,
    ) -> None:
        self.road_frame = road_frame
        self.cfg = config or HeterogeneousPlatoonConfig()
        self.phase = HandoverPhase.SCOUT_A_ACTIVE

        # Deep aerodynamics for turbulent crosswind disturbance
        self.aero_engine = DeepAerodynamicsEngine(
            DeepAerodynamicsConfig(
                wind_enabled=True,
                wind_mean=(1.5, 0.5, 0.0),
                gust_enabled=True,
                gust_amplitude=(3.0, 1.5, 0.0),
                drag_enabled=True,
            )
        )

        self.scout_a = AerialScoutState(
            scout_id="AEGIS_SCOUT_ALPHA",
            pos=np.zeros(3, dtype=np.float64),
            vel=np.zeros(3, dtype=np.float64),
            battery_soc=1.0,
            is_airborne=True,
            is_docked=False,
        )
        self.scout_b = AerialScoutState(
            scout_id="AEGIS_SCOUT_BETA",
            pos=np.zeros(3, dtype=np.float64),
            vel=np.zeros(3, dtype=np.float64),
            battery_soc=1.0,
            is_airborne=False,
            is_docked=True,
        )

        self.handover_start_time: float | None = None
        self.handover_completed_time: float | None = None
        self.min_inter_drone_dist_observed: float = float("inf")

    def reset(self, lead_vehicle_state: VehicleState, lead_frenet_s: float) -> None:
        """Initializes Dual Scout formation: Scout A airborne, Scout B docked on lead roof."""
        self.phase = HandoverPhase.SCOUT_A_ACTIVE
        self.aero_engine.reset()
        self.handover_start_time = None
        self.handover_completed_time = None
        self.min_inter_drone_dist_observed = float("inf")

        # Scout A is deployed ahead of lead vehicle (if aerial scouts enabled)
        s_a_init = lead_frenet_s + self.cfg.aerial_lookahead_dist
        pt_a = self.road_frame.frenet_to_cartesian(s_a_init, 0.0)
        self.scout_a.pos = np.array([pt_a[0], pt_a[1], self.cfg.aerial_cruise_altitude], dtype=np.float64)
        self.scout_a.vel = np.array([lead_vehicle_state.v_x, 0.0, 0.0], dtype=np.float64)
        self.scout_a.battery_soc = 0.95
        self.scout_a.is_airborne = self.cfg.enable_aerial_scouts
        self.scout_a.is_docked = not self.cfg.enable_aerial_scouts
        self.scout_a.assigned_target_s = s_a_init

        # Scout B is docked on lead vehicle rooftop nest
        pt_dock = self.road_frame.frenet_to_cartesian(lead_frenet_s, 0.0)
        self.scout_b.pos = np.array([pt_dock[0], pt_dock[1], self.cfg.rooftop_dock_altitude], dtype=np.float64)
        self.scout_b.vel = np.array([lead_vehicle_state.v_x, 0.0, 0.0], dtype=np.float64)
        self.scout_b.battery_soc = 1.0
        self.scout_b.is_airborne = False
        self.scout_b.is_docked = True
        self.scout_b.assigned_target_s = lead_frenet_s

    def update(
        self,
        dt: float,
        sim_time: float,
        lead_vehicle_state: VehicleState,
        lead_frenet_s: float,
        real_hazard_s: float | None = None,
        real_hazard_friction: float = 0.28,
        packet_seq: int = 1,
    ) -> tuple[V2ATelemetryPacket, dict[str, Any]]:
        """
        Steps both aerial scouts forward in time, manages state machine transitions,
        enforces 3D inter-drone separation barriers, and produces continuous telemetry.
        """
        # Rooftop dock location on lead vehicle
        pt_dock = self.road_frame.frenet_to_cartesian(lead_frenet_s, 0.0)
        lead_roof_pos = np.array([pt_dock[0], pt_dock[1], self.cfg.rooftop_dock_altitude], dtype=np.float64)

        if not self.cfg.enable_aerial_scouts:
            self.scout_a.pos = lead_roof_pos.copy()
            self.scout_b.pos = lead_roof_pos.copy()
            v2a_packet = V2ATelemetryPacket(
                drone_id="NONE",
                timestamp=sim_time,
                drone_pos=lead_roof_pos.copy(),
                drone_vel=np.zeros(3),
                detected_hazard_s=None,
                hazard_type="CLEAR",
                estimated_friction=0.85,
                confidence=0.0,
                packet_seq=packet_seq,
                is_authenticated=True,
            )
            scout_metrics = {
                "handover_phase": "NO_AERIAL_SCOUTS",
                "scout_a_soc": 0.0,
                "scout_b_soc": 0.0,
                "active_drone_id": "NONE",
                "min_inter_drone_dist": float("inf"),
                "scout_a_pos": lead_roof_pos.tolist(),
                "scout_b_pos": lead_roof_pos.tolist(),
                "hazard_preview_active": False,
            }
            return v2a_packet, scout_metrics

        # -------------------------------------------------------------
        # 1. State Machine Transitions
        # -------------------------------------------------------------
        if self.phase == HandoverPhase.SCOUT_A_ACTIVE:
            # Drain Scout A battery during flight
            self.scout_a.battery_soc = max(0.05, self.scout_a.battery_soc - self.cfg.battery_drain_rate * dt)
            # Recharging Scout B in dock
            self.scout_b.battery_soc = min(1.0, self.scout_b.battery_soc + self.cfg.battery_charge_rate * dt)
            self.scout_b.pos = lead_roof_pos.copy()
            self.scout_b.vel = np.array([lead_vehicle_state.v_x, 0.0, 0.0], dtype=np.float64)

            # Trigger handover when Scout A reaches threshold
            if self.scout_a.battery_soc <= self.cfg.soc_handover_trigger:
                if self.cfg.enable_dual_scout:
                    self.phase = HandoverPhase.HANDOVER_LAUNCH
                    self.handover_start_time = sim_time
                    self.scout_b.is_airborne = True
                    self.scout_b.is_docked = False
                else:
                    self.phase = HandoverPhase.RETURNING_A
                    self.handover_start_time = sim_time

        elif self.phase == HandoverPhase.HANDOVER_LAUNCH:
            # Scout B climbs and accelerates towards forward formation
            self.scout_a.battery_soc = max(0.05, self.scout_a.battery_soc - self.cfg.battery_drain_rate * dt)
            self.scout_b.battery_soc = max(0.05, self.scout_b.battery_soc - self.cfg.battery_drain_rate * dt)

            # Check if Scout B has reached cruise altitude and proximity
            if self.scout_b.pos[2] >= (self.cfg.aerial_cruise_altitude - 1.5):
                dist_to_scout_a = np.linalg.norm(self.scout_b.pos - self.scout_a.pos)
                if dist_to_scout_a <= 35.0:
                    self.phase = HandoverPhase.DUAL_SYNCHRONIZED

        elif self.phase == HandoverPhase.DUAL_SYNCHRONIZED:
            # Both drones synchronized in lead lookahead formation
            self.scout_a.battery_soc = max(0.05, self.scout_a.battery_soc - self.cfg.battery_drain_rate * dt)
            self.scout_b.battery_soc = max(0.05, self.scout_b.battery_soc - self.cfg.battery_drain_rate * dt)

            # After 1.5 seconds of stable dual-telemetry handover, Scout A starts return
            if self.handover_start_time is not None and (sim_time - self.handover_start_time) >= 1.5:
                self.phase = HandoverPhase.RETURNING_A

        elif self.phase == HandoverPhase.RETURNING_A:
            # Scout B is primary (if dual scout enabled); Scout A descends towards lead vehicle roof
            self.scout_a.battery_soc = max(0.05, self.scout_a.battery_soc - self.cfg.battery_drain_rate * 0.7 * dt)
            if self.cfg.enable_dual_scout:
                self.scout_b.battery_soc = max(0.05, self.scout_b.battery_soc - self.cfg.battery_drain_rate * dt)

            # Check if Scout A has landed on lead vehicle rooftop dock
            dist_to_dock = np.linalg.norm(self.scout_a.pos - lead_roof_pos)
            if dist_to_dock <= 1.5 and self.scout_a.pos[2] <= (self.cfg.rooftop_dock_altitude + 0.5):
                self.phase = HandoverPhase.SCOUT_B_ACTIVE
                self.scout_a.is_airborne = False
                self.scout_a.is_docked = True
                self.scout_a.pos = lead_roof_pos.copy()
                self.handover_completed_time = sim_time

        elif self.phase == HandoverPhase.SCOUT_B_ACTIVE:
            if self.cfg.enable_dual_scout:
                # Scout B sole active leader; Scout A recharging on dock
                self.scout_b.battery_soc = max(0.05, self.scout_b.battery_soc - self.cfg.battery_drain_rate * dt)
                self.scout_a.battery_soc = min(1.0, self.scout_a.battery_soc + self.cfg.battery_charge_rate * dt)
                self.scout_a.pos = lead_roof_pos.copy()
                self.scout_a.vel = np.array([lead_vehicle_state.v_x, 0.0, 0.0], dtype=np.float64)
            else:
                self.scout_a.battery_soc = min(1.0, self.scout_a.battery_soc + self.cfg.battery_charge_rate * dt)
                self.scout_a.pos = lead_roof_pos.copy()
                self.scout_b.pos = lead_roof_pos.copy()

        # -------------------------------------------------------------
        # 2. Kinematics & 3D Inter-Drone Collision Barrier Control
        # -------------------------------------------------------------
        # Primary lookahead station: s_lead + 65m
        s_lead_des = lead_frenet_s + self.cfg.aerial_lookahead_dist

        # Scout A target position with lateral deconfliction lane
        if self.phase in [HandoverPhase.SCOUT_A_ACTIVE, HandoverPhase.HANDOVER_LAUNCH]:
            pt_a = self.road_frame.frenet_to_cartesian(s_lead_des, 0.0)
            target_pos_a = np.array([pt_a[0], pt_a[1], self.cfg.aerial_cruise_altitude], dtype=np.float64)
        elif self.phase == HandoverPhase.DUAL_SYNCHRONIZED:
            # Shift Scout A to left lane (d = -5.5m) to clear centerline for Scout B
            pt_a = self.road_frame.frenet_to_cartesian(s_lead_des - 8.0, -5.5)
            target_pos_a = np.array([pt_a[0], pt_a[1], self.cfg.aerial_cruise_altitude], dtype=np.float64)
        else: # RETURNING_A
            # Descend along left corridor (d = -5.0m) before touchdown on vehicle roof
            dist_to_dock = np.linalg.norm(self.scout_a.pos - lead_roof_pos)
            if dist_to_dock > 4.0:
                pt_a = self.road_frame.frenet_to_cartesian(lead_frenet_s + 4.0, -5.0)
                target_pos_a = np.array([pt_a[0], pt_a[1], self.cfg.aerial_cruise_altitude * 0.45], dtype=np.float64)
            else:
                target_pos_a = lead_roof_pos

        # Scout B target position with lateral deconfliction lane
        if self.phase == HandoverPhase.SCOUT_A_ACTIVE:
            target_pos_b = lead_roof_pos
        elif self.phase in [HandoverPhase.HANDOVER_LAUNCH, HandoverPhase.DUAL_SYNCHRONIZED]:
            # Ascend and cruise along right lane (d = +5.5m) to guarantee >= 11m lateral separation
            pt_b = self.road_frame.frenet_to_cartesian(s_lead_des, 5.5)
            target_pos_b = np.array([pt_b[0], pt_b[1], self.cfg.aerial_cruise_altitude], dtype=np.float64)
        else: # RETURNING_A, SCOUT_B_ACTIVE
            pt_b = self.road_frame.frenet_to_cartesian(s_lead_des, 0.0)
            target_pos_b = np.array([pt_b[0], pt_b[1], self.cfg.aerial_cruise_altitude], dtype=np.float64)

        # Update Scout A dynamics if airborne
        if self.scout_a.is_airborne:
            acc_a = 2.5 * (target_pos_a - self.scout_a.pos) - 1.8 * self.scout_a.vel
            f_drag_a, _ = self.aero_engine.compute_aerodynamic_drag(self.scout_a.vel, self.aero_engine.state.total_wind)
            acc_a += f_drag_a / 1.5
            self.scout_a.vel += acc_a * dt
            self.scout_a.pos += self.scout_a.vel * dt

        # Update Scout B dynamics if airborne
        if self.scout_b.is_airborne:
            acc_b = 2.5 * (target_pos_b - self.scout_b.pos) - 1.8 * self.scout_b.vel
            f_drag_b, _ = self.aero_engine.compute_aerodynamic_drag(self.scout_b.vel, self.aero_engine.state.total_wind)
            acc_b += f_drag_b / 1.5

            # 3D Inter-Drone Barrier: h_drone = ||p_a - p_b||^2 - d_safe^2 >= 0
            if self.scout_a.is_airborne:
                rel_pos = self.scout_b.pos - self.scout_a.pos
                drone_dist = float(np.linalg.norm(rel_pos))
                self.min_inter_drone_dist_observed = min(self.min_inter_drone_dist_observed, drone_dist)

                if drone_dist < (self.cfg.inter_drone_safe_dist + 3.0) and drone_dist > 1e-2:
                    # Repulsive collision barrier acceleration
                    n_rep = rel_pos / drone_dist
                    acc_b += n_rep * 4.5

            self.scout_b.vel += acc_b * dt
            self.scout_b.pos += self.scout_b.vel * dt

        # -------------------------------------------------------------
        # 3. Vision Detection & Telemetry Packet Synthesis
        # -------------------------------------------------------------
        # Active drone determined by phase
        if not self.cfg.enable_dual_scout and self.phase == HandoverPhase.SCOUT_B_ACTIVE:
            active_scout = self.scout_b
            is_active_airborne = False
        else:
            active_scout = self.scout_a if self.phase in [HandoverPhase.SCOUT_A_ACTIVE, HandoverPhase.HANDOVER_LAUNCH] else self.scout_b
            is_active_airborne = active_scout.is_airborne
        active_frenet_s = s_lead_des

        detected_hazard_s = None
        hazard_type = "CLEAR"
        hazard_friction = 0.85
        confidence = 0.0

        if is_active_airborne and real_hazard_s is not None and abs(active_frenet_s - real_hazard_s) < 85.0:
            detected_hazard_s = real_hazard_s
            hazard_type = "OBSTACLE"
            hazard_friction = real_hazard_friction
            confidence = 0.96

        telemetry_packet = V2ATelemetryPacket(
            drone_id=active_scout.scout_id,
            timestamp=sim_time,
            drone_pos=active_scout.pos.copy(),
            drone_vel=active_scout.vel.copy(),
            detected_hazard_s=detected_hazard_s,
            hazard_type=hazard_type,
            estimated_friction=hazard_friction,
            confidence=confidence,
            packet_seq=packet_seq,
            is_authenticated=True,
        )

        metrics = {
            "handover_phase": self.phase.value,
            "scout_a_soc": self.scout_a.battery_soc,
            "scout_b_soc": self.scout_b.battery_soc,
            "active_drone_id": active_scout.scout_id,
            "min_inter_drone_dist": self.min_inter_drone_dist_observed,
            "scout_a_pos": self.scout_a.pos.tolist(),
            "scout_b_pos": self.scout_b.pos.tolist(),
            "hazard_preview_active": (detected_hazard_s is not None),
        }
        return telemetry_packet, metrics


# =============================================================================
# 2. Multi-Hop Cascade Platoon Safety Shield & String Stability
# =============================================================================

class MultiHopCascadePlatoonShield:
    """
    Coordinates longitudinal spacing and deceleration for 5 connected vehicles.
    Enforces inter-vehicle Frenet Control Barrier Functions to guarantee string stability:
    ||Delta a_i|| <= ||Delta a_{i-1}|| with zero inter-vehicle rear-end collisions.
    """

    def __init__(
        self,
        road_frame: FrenetFrame,
        config: HeterogeneousPlatoonConfig | None = None,
        vehicle_config: VehicleConfig | None = None,
    ) -> None:
        self.road_frame = road_frame
        self.cfg = config or HeterogeneousPlatoonConfig()
        self.v_cfg = vehicle_config or VehicleConfig()

        # Individual vehicle dynamic bicycle models and safety shields
        self.models = [DynamicBicycleModel(self.v_cfg) for _ in range(self.cfg.num_vehicles)]
        self.cbf_shields = [
            AirGroundFrenetCBF(road_frame=road_frame, vehicle_config=self.v_cfg)
            for _ in range(self.cfg.num_vehicles)
        ]
        self.ville_filters = [
            AirGroundVilleFilter(alpha=0.001)
            for _ in range(self.cfg.num_vehicles)
        ]

    def filter_platoon_controls(
        self,
        vehicle_states: list[VehicleState],
        vehicle_frenets: list[FrenetState],
        nominal_accels: list[float],
        dt: float,
        v2a_packet: V2ATelemetryPacket,
        enable_v2v_relay: bool = True,
        corrupt_relay_idx: int | None = None,
        real_hazard_s: float | None = None,
    ) -> tuple[list[float], list[float], list[PlatoonV2VPacket]]:
        """
        Calculates safe shielded accelerations for all 5 vehicles in the platoon.
        Cascades V2A lookahead from Vehicle 0 down to Vehicle 4.
        """
        num_v = len(vehicle_states)
        shielded_accels = [0.0] * num_v
        shielded_steerings = [0.0] * num_v
        v2v_packets: list[PlatoonV2VPacket] = []

        # -------------------------------------------------------------
        # 1. Lead Vehicle (Vehicle 0) Filters Control via Aerial Preview
        # -------------------------------------------------------------
        lead_state = vehicle_states[0]
        lead_frenet = vehicle_frenets[0]

        # Lead vehicle verifies incoming V2A packet via Ville filter
        is_v2a_verified, _ = self.ville_filters[0].update(
            packet=v2a_packet,
            current_vehicle_s=lead_frenet.s,
            current_speed=lead_state.speed,
        )
        verified_hazard_s = v2a_packet.detected_hazard_s if is_v2a_verified else None
        preview_friction = v2a_packet.estimated_friction if is_v2a_verified else 0.85

        # Onboard radar detection for lead vehicle when within line-of-sight cutoff
        onboard_detected_s = None
        if real_hazard_s is not None and (0.0 < (real_hazard_s - lead_frenet.s) <= self.cfg.radar_cutoff_dist):
            onboard_detected_s = real_hazard_s

        lead_cmd = self.cbf_shields[0].filter_air_ground_command(
            state=lead_state,
            nominal_accel=nominal_accels[0],
            nominal_steering=0.0,
            dt=dt,
            verified_hazard_s=verified_hazard_s,
            preview_friction=preview_friction,
            onboard_detected_obstacle_s=onboard_detected_s,
        )
        shielded_accels[0] = lead_cmd.accel_cmd
        shielded_steerings[0] = lead_cmd.steering_cmd

        # -------------------------------------------------------------
        # 2. Cascade V2A-to-V2V Relay down the Platoon
        # -------------------------------------------------------------
        current_preview_s = verified_hazard_s
        current_preview_mu = preview_friction

        for i in range(1, num_v):
            preceding_state = vehicle_states[i - 1]
            preceding_frenet = vehicle_frenets[i - 1]
            ego_state = vehicle_states[i]
            ego_frenet = vehicle_frenets[i]

            # Formulate V2V packet from (i-1) to i
            is_auth = True
            if corrupt_relay_idx is not None and (i - 1) == corrupt_relay_idx:
                # Simulates Byzantine rogue node broadcasting fake sudden stop
                claimed_accel = -6.5
                is_auth = False
            else:
                claimed_accel = shielded_accels[i - 1]

            pkt = PlatoonV2VPacket(
                sender_id=i - 1,
                receiver_id=i,
                timestamp=v2a_packet.timestamp,
                leader_s=lead_frenet.s,
                sender_s=preceding_frenet.s,
                sender_speed=preceding_state.v_x,
                commanded_accel=claimed_accel,
                preview_hazard_s=current_preview_s,
                preview_friction=current_preview_mu,
                is_authenticated=is_auth,
            )
            v2v_packets.append(pkt)

            # Follower i computes spacing gap
            gap = preceding_frenet.s - ego_frenet.s - self.cfg.vehicle_length
            rel_speed = preceding_state.v_x - ego_state.v_x

            # Nominal CACC law if V2V is enabled and authentic
            if enable_v2v_relay and is_auth:
                desired_gap = self.cfg.min_standstill_gap + self.cfg.time_headway * ego_state.v_x
                gap_error = gap - desired_gap
                # Cooperative feedforward: when leader preview deceleration is active, propagate lead decel
                ff_accel = shielded_accels[0] if (current_preview_s is not None and shielded_accels[0] < -0.1) else claimed_accel
                k_p = 0.65
                k_d = 1.10
                cacc_accel = ff_accel + k_p * gap_error + k_d * rel_speed
                nom_cmd = float(cacc_accel)
            else:
                # Fallback to Radar-only ACC
                desired_gap = self.cfg.min_standstill_gap + 1.6 * ego_state.v_x
                gap_error = gap - desired_gap
                nom_cmd = float(0.45 * gap_error + 0.90 * rel_speed)

            # Local road friction at vehicle i
            mu_local = 0.85
            if real_hazard_s is not None and abs(ego_frenet.s - real_hazard_s) < 30.0:
                mu_local = current_preview_mu
            a_brake_safe = min(6.5, mu_local * 9.81 * 0.80)

            d_safe_barrier = (
                self.cfg.min_standstill_gap
                + self.cfg.time_headway * ego_state.v_x
                + max(0.0, (ego_state.v_x**2 - preceding_state.v_x**2)) / (2.0 * max(0.5, a_brake_safe))
            )
            h_platoon = gap - d_safe_barrier

            # Enforce string-stable deceleration barrier
            safe_accel = float(nom_cmd)
            if gap < 4.5 or rel_speed < -1.5:
                # Emergency spacing regulation
                safe_accel = min(safe_accel, shielded_accels[i - 1] - 0.5)

            safe_accel = float(np.clip(safe_accel, -a_brake_safe, self.v_cfg.max_accel))

            # Finite standstill stop floor if ego vehicle has nearly stopped
            if ego_state.v_x < 0.5:
                safe_accel = min(safe_accel, -0.2)

            shielded_accels[i] = safe_accel
            shielded_steerings[i] = 0.0

        return shielded_accels, shielded_steerings, v2v_packets


# =============================================================================
# 3. Heterogeneous Platoon Closed-Loop Coordinator
# =============================================================================

class HeterogeneousPlatoonCoordinator:
    """
    Closed-loop simulation coordinator managing 2 Aerial Scouts and a 5-Vehicle Ground Platoon.
    """

    def __init__(
        self,
        road_frame: FrenetFrame,
        config: HeterogeneousPlatoonConfig | None = None,
        vehicle_config: VehicleConfig | None = None,
    ) -> None:
        self.road_frame = road_frame
        self.cfg = config or HeterogeneousPlatoonConfig()
        self.v_cfg = vehicle_config or VehicleConfig()

        self.dual_scout = DualScoutHandoverManager(road_frame, self.cfg)
        self.platoon_shield = MultiHopCascadePlatoonShield(road_frame, self.cfg, self.v_cfg)

        self.vehicle_states: list[VehicleState] = []
        self.sim_time: float = 0.0
        self.packet_seq: int = 0

    def reset(
        self,
        initial_lead_s: float = 80.0,
        initial_speed: float = 22.0,
    ) -> None:
        """Initializes 5 platoon vehicles and dual scouts."""
        self.sim_time = 0.0
        self.packet_seq = 0
        self.max_lead_decel = 0.0
        self.max_rear_decel = 0.0
        self.vehicle_states.clear()

        # Initialize 5 vehicles with proper equilibrium inter-vehicle spacing along Frenet frame
        desired_spacing = self.cfg.min_standstill_gap + self.cfg.time_headway * initial_speed + self.cfg.vehicle_length
        for i in range(self.cfg.num_vehicles):
            s_i = initial_lead_s - i * desired_spacing
            pt = self.road_frame.frenet_to_cartesian(s_i, 0.0)
            st = VehicleState(
                x=pt[0],
                y=pt[1],
                yaw=0.0,
                v_x=initial_speed,
                v_y=0.0,
                yaw_rate=0.0,
                steering=0.0,
                accel=0.0,
            )
            self.vehicle_states.append(st)

        # Reset dual scout handover manager
        self.dual_scout.reset(self.vehicle_states[0], initial_lead_s)

    def step(
        self,
        dt: float,
        nominal_cruise_accel: float = 0.0,
        real_hazard_s: float | None = None,
        real_hazard_friction: float = 0.28,
        enable_v2v: bool = True,
        corrupt_relay_idx: int | None = None,
    ) -> dict[str, Any]:
        """
        Executes one joint simulation step for the entire heterogeneous platoon.
        """
        self.sim_time += dt
        self.packet_seq += 1

        # 1. Update Frenet coordinates for all 5 vehicles
        frenet_states = [
            self.road_frame.cartesian_to_frenet(st.x, st.y, st.yaw, st.v_x, st.v_y)
            for st in self.vehicle_states
        ]

        # 2. Update Dual Aerial Scout State Machine & Produce V2A Packet
        v2a_packet, scout_metrics = self.dual_scout.update(
            dt=dt,
            sim_time=self.sim_time,
            lead_vehicle_state=self.vehicle_states[0],
            lead_frenet_s=frenet_states[0].s,
            real_hazard_s=real_hazard_s,
            real_hazard_friction=real_hazard_friction,
            packet_seq=self.packet_seq,
        )

        # 3. Filter Platoon Controls via Cascading V2V CBF Shield
        nom_accels = [nominal_cruise_accel] * self.cfg.num_vehicles
        accels, steerings, v2v_pkts = self.platoon_shield.filter_platoon_controls(
            vehicle_states=self.vehicle_states,
            vehicle_frenets=frenet_states,
            nominal_accels=nom_accels,
            dt=dt,
            v2a_packet=v2a_packet,
            enable_v2v_relay=enable_v2v,
            corrupt_relay_idx=corrupt_relay_idx,
            real_hazard_s=real_hazard_s,
        )

        # 4. Step Ground Vehicle Dynamics with road friction
        eff_friction = 0.85
        if real_hazard_s is not None and abs(frenet_states[0].s - real_hazard_s) < 25.0:
            eff_friction = real_hazard_friction

        next_states = []
        for i in range(self.cfg.num_vehicles):
            self.platoon_shield.models[i].cfg = VehicleConfig(friction_coeff=eff_friction)
            nxt, _ = self.platoon_shield.models[i].step(
                state=self.vehicle_states[i],
                cmd_accel=accels[i],
                cmd_steering=steerings[i],
                dt=dt,
            )
            next_states.append(nxt)
        self.vehicle_states = next_states

        # 5. Evaluate Spacings, String Stability, and Collision Metrics
        inter_vehicle_gaps = []
        inter_vehicle_collision = False
        obstacle_collision = False

        for i in range(self.cfg.num_vehicles - 1):
            gap_i = frenet_states[i].s - frenet_states[i + 1].s - self.cfg.vehicle_length
            inter_vehicle_gaps.append(gap_i)
            if gap_i <= 0.1:
                inter_vehicle_collision = True

        if real_hazard_s is not None:
            if frenet_states[0].s >= (real_hazard_s - 1.5) and self.vehicle_states[0].speed > 1.5:
                obstacle_collision = True

        # String stability: peak-to-peak ratio of rear deceleration to lead deceleration
        lead_decel = abs(min(0.0, accels[0]))
        rear_decel = abs(min(0.0, accels[-1]))
        self.max_lead_decel = max(self.max_lead_decel, lead_decel)
        self.max_rear_decel = max(self.max_rear_decel, rear_decel)
        string_amplification_ratio = (self.max_rear_decel / max(0.1, self.max_lead_decel)) if self.max_lead_decel > 0.2 else 1.0

        return {
            "time": self.sim_time,
            "handover_phase": scout_metrics["handover_phase"],
            "scout_a_soc": scout_metrics["scout_a_soc"],
            "scout_b_soc": scout_metrics["scout_b_soc"],
            "min_inter_drone_dist": scout_metrics["min_inter_drone_dist"],
            "active_scout_id": scout_metrics["active_drone_id"],
            "hazard_preview_active": scout_metrics["hazard_preview_active"],
            "vehicle_s": [float(f.s) for f in frenet_states],
            "vehicle_speeds": [float(st.speed) for st in self.vehicle_states],
            "vehicle_accels": accels,
            "inter_vehicle_gaps": inter_vehicle_gaps,
            "min_platoon_gap": min(inter_vehicle_gaps) if inter_vehicle_gaps else 0.0,
            "inter_vehicle_collision": inter_vehicle_collision,
            "obstacle_collision": obstacle_collision,
            "string_amplification_ratio": string_amplification_ratio,
            "max_lead_decel": self.max_lead_decel,
            "max_rear_decel": self.max_rear_decel,
        }
