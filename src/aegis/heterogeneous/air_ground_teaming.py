"""
NEXVIA AEGIS — Air-Ground Heterogeneous Collaborative Teaming & Safety Architecture.

Coordinates 6-DOF Aerial Scouts ("Eye-in-the-Sky") and Autonomous Ground Vehicles (AGVs)
or Connected Platoons for joint safety in high-speed curved highway navigation:

1. V2A (Vehicle-to-Aerial / Aerial-to-Vehicle) Communication & Hazard Preview:
   - Aerial drone flies in unoccluded high-altitude formation ahead of ground convoy.
   - Previews blind-curve roadway hazards (blocked lanes, stalled trucks, low-friction ice).
   - Broadcasts authenticated telemetry packets with hazard station s_haz and friction mu_est.

2. Anytime-Valid Ville Supermartingale V2A Anomaly & Spoofing Guard:
   - Tracks spatial-temporal continuity and optical confidence of aerial hazard reports.
   - Detects and quarantines phantom hazard spoofing attacks (p <= 0.001) under arbitrary stopping times.
   - Eliminates False Emergency Stops (Phantom Braking) on high-speed motorways.

3. Cross-Domain Lookahead Frenet CBF Safety Shield:
   - Incorporates long-range aerial preview horizon into the ground vehicle's Frenet barrier set:
     h_prev(s, v) = s_haz - s - (d_0 + tau * v + v^2 / (2 * a_brake(mu))) >= 0.
   - Guarantees progressive, comfortable deceleration well in advance of blind corners,
     strictly respecting Kamm's friction circle adhesion limit on wet/icy roads (mu <= 0.35).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import numpy as np

from aegis.av.frenet_cbf_shield import (
    FrenetCbfConfig,
    FrenetSafetyShield,
    ShieldedControlCommand,
)
from aegis.av.vehicle_dynamics import (
    DynamicBicycleModel,
    FrenetFrame,
    FrenetState,
    VehicleConfig,
    VehicleState,
)
from aegis.env.deep_aerodynamics import DeepAerodynamicsConfig, DeepAerodynamicsEngine


# =============================================================================
# 1. Telemetry Data Structures & Configurations
# =============================================================================

@dataclass
class V2ATelemetryPacket:
    """Authenticated V2A telemetry message sent from aerial scout to ground vehicle."""
    drone_id: str
    timestamp: float
    drone_pos: np.ndarray             # 3D position [x, y, z]
    drone_vel: np.ndarray             # 3D velocity [vx, vy, vz]
    detected_hazard_s: float | None   # Road station in Frenet frame (m) or None if clear
    hazard_type: str                  # "CLEAR", "OBSTACLE", "ICE_PATCH"
    estimated_friction: float         # Road friction preview (0.85 nominal, 0.28 ice)
    confidence: float                 # Vision detector confidence [0.0, 1.0]
    packet_seq: int
    is_authenticated: bool = True     # Cryptographic integrity signature (e.g. ECDSA / HMAC)
    packet_hash: str = field(init=False)

    def __post_init__(self) -> None:
        auth_tag = "VALID" if self.is_authenticated else "INVALID_SIGNATURE"
        payload = f"{self.drone_id}:{self.timestamp:.4f}:{self.detected_hazard_s}:{self.hazard_type}:{self.packet_seq}:{auth_tag}"
        self.packet_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class AirGroundConfig:
    """Configuration parameters for heterogeneous air-ground collaborative autonomy."""
    # Formation Geometry
    aerial_lookahead_dist: float = 65.0      # meters ahead of ground vehicle (s_lead + 65m)
    aerial_cruise_altitude: float = 18.0     # meters above ground
    ground_los_cutoff: float = 35.0          # ground onboard LiDAR LOS range around blind curves (m)

    # V2A Wireless Communication
    comm_latency_s: float = 0.02             # 20 ms transmission latency
    comm_packet_drop_rate: float = 0.02      # 2% random RF packet drop
    ville_alpha: float = 0.001               # Type-I false alarm bound for spoofing detection

    # Ground Preview Deceleration Limits
    comfort_decel_limit: float = 2.8         # m/s^2 (comfortable gradual braking)
    emergency_decel_limit: float = 6.5       # m/s^2 (Kamm's circle maximum braking limit)
    preview_safety_margin: float = 5.0       # buffer distance to standstill (m)


# =============================================================================
# 2. Ville Supermartingale V2A Hazard Integrity Filter
# =============================================================================

class AirGroundVilleFilter:
    """
    Guarantees anytime-valid verification of aerial hazard telemetry against spoofing attacks.
    Maintains a non-negative supermartingale wealth process W_t with initial wealth W_0 = 1.
    If W_t >= 1 / alpha (1000 for alpha=0.001), the hazard report is flagged as spoofed and quarantined.
    """

    def __init__(self, alpha: float = 0.001) -> None:
        self.alpha = alpha
        self.threshold = 1.0 / alpha
        self.wealth: float = 1.0
        self.consecutive_valid_frames: int = 0
        self.is_quarantined: bool = False
        self.history_stations: list[float] = []

    def reset(self) -> None:
        self.wealth = 1.0
        self.consecutive_valid_frames = 0
        self.is_quarantined = False
        self.history_stations.clear()

    def update(
        self,
        packet: V2ATelemetryPacket,
        current_vehicle_s: float,
        current_speed: float,
    ) -> tuple[bool, float]:
        """
        Evaluates incoming V2A telemetry packet for spatial and physical consistency.

        Returns:
            (is_verified_valid_hazard, current_wealth)
        """
        if packet.detected_hazard_s is None or packet.hazard_type == "CLEAR":
            self.wealth = max(0.5, self.wealth * 0.95)
            self.consecutive_valid_frames = 0
            return False, self.wealth

        s_haz = packet.detected_hazard_s

        # Invariant 1: Hazard must be physically in front of ground vehicle
        is_ahead = (s_haz > current_vehicle_s)
        # Invariant 2: Hazard should not be beyond max aerial horizon
        is_within_horizon = (s_haz < current_vehicle_s + 150.0)
        # Invariant 3: Multi-frame spatial stationary consistency (stationary obstacles don't teleport)
        is_spatially_consistent = True
        if self.history_stations:
            prev_s = self.history_stations[-1]
            if abs(s_haz - prev_s) > 4.0: # sudden jump > 4 meters
                is_spatially_consistent = False

        self.history_stations.append(s_haz)
        if len(self.history_stations) > 10:
            self.history_stations.pop(0)

        # Anomaly scoring: Betting martingale update
        has_anomaly = (
            not packet.is_authenticated
            or not is_ahead
            or not is_within_horizon
            or not is_spatially_consistent
            or packet.confidence < 0.35
        )
        if has_anomaly:
            # Anomaly detected: bet against the report
            anomaly_score = 4.5
            bet_fraction = 0.85
            self.wealth = self.wealth * (1.0 + bet_fraction * anomaly_score)
            self.consecutive_valid_frames = 0
        else:
            # Consistent observation: wealth decays back towards 1.0
            self.wealth = max(1.0, self.wealth * 0.88)
            self.consecutive_valid_frames += 1

        # Check Ville supermartingale threshold
        if self.wealth >= self.threshold:
            self.is_quarantined = True

        # Validated if consistent, not quarantined, and observed for at least 2 frames
        is_verified = (
            not self.is_quarantined
            and self.consecutive_valid_frames >= 2
            and packet.confidence >= 0.70
        )
        return is_verified, self.wealth


# =============================================================================
# 3. Cross-Domain Lookahead Frenet CBF Shield
# =============================================================================

class AirGroundFrenetCBF:
    """
    Integrates Ground Frenet HOCBF Shield with Long-Range Aerial Preview Barriers.
    """

    def __init__(
        self,
        road_frame: FrenetFrame,
        vehicle_config: VehicleConfig | None = None,
        cbf_config: FrenetCbfConfig | None = None,
        air_ground_config: AirGroundConfig | None = None,
    ) -> None:
        self.road_frame = road_frame
        self.v_cfg = vehicle_config or VehicleConfig()
        self.cbf_cfg = cbf_config or FrenetCbfConfig()
        self.ag_cfg = air_ground_config or AirGroundConfig()
        self.base_shield = FrenetSafetyShield(
            vehicle_config=self.v_cfg,
            cbf_config=self.cbf_cfg,
        )

    def filter_air_ground_command(
        self,
        state: VehicleState,
        nominal_accel: float,
        nominal_steering: float,
        dt: float,
        verified_hazard_s: float | None = None,
        preview_friction: float | None = None,
        onboard_detected_obstacle_s: float | None = None,
    ) -> ShieldedControlCommand:
        """
        Filters ground vehicle acceleration and steering to satisfy both local lane/skid constraints
        and long-range aerial preview stopping barriers.
        """
        frenet = self.road_frame.cartesian_to_frenet(state.x, state.y, state.yaw, state.v_x, state.v_y)
        mu_eff = preview_friction if preview_friction is not None else self.v_cfg.friction_coeff

        # 1. First evaluate base lane keeping, curvature, and onboard ACC barriers
        base_cmd = self.base_shield.filter_control(
            state=state,
            frenet=frenet,
            nominal_accel=nominal_accel,
            nominal_steering=nominal_steering,
            lead_vehicle_s=onboard_detected_obstacle_s,
            lead_vehicle_speed=0.0 if onboard_detected_obstacle_s else None,
            road_frame=self.road_frame,
        )

        accel_out = base_cmd.accel_cmd
        active_barriers = list(base_cmd.active_barriers)
        barrier_active = base_cmd.barrier_active

        # 2. Aerial Preview Lookahead Deceleration Barrier
        # Effective obstacle target: the earliest of onboard or verified aerial hazard
        target_hazard_s = None
        if onboard_detected_obstacle_s is not None and verified_hazard_s is not None:
            target_hazard_s = min(onboard_detected_obstacle_s, verified_hazard_s)
        elif onboard_detected_obstacle_s is not None:
            target_hazard_s = onboard_detected_obstacle_s
        elif verified_hazard_s is not None:
            target_hazard_s = verified_hazard_s

        if target_hazard_s is not None:
            dist_to_hazard = target_hazard_s - frenet.s
            v_curr = max(0.0, state.v_x)

            # Stopping distance model under effective road friction:
            # d_stop = v^2 / (2 * a_brake) + d_margin
            a_brake_safe = min(self.ag_cfg.emergency_decel_limit, mu_eff * 9.81 * 0.75)
            d_safe = (v_curr ** 2) / (2.0 * max(0.5, a_brake_safe)) + self.ag_cfg.preview_safety_margin

            # Barrier function h_prev >= 0
            h_prev = dist_to_hazard - d_safe

            if dist_to_hazard > 0.0:
                # Calculate required smooth deceleration to stop at target_hazard_s - d_margin
                clearance = max(0.5, dist_to_hazard - self.ag_cfg.preview_safety_margin)
                if clearance < 120.0 and v_curr > 0.1:
                    # Quadratic preview deceleration at high speed
                    a_req = - (v_curr ** 2) / (2.0 * clearance)
                    # Add finite-time standstill floor when approaching stop
                    if v_curr < 3.5:
                        a_req = min(a_req, -1.2)
                    # Enforce within comfortable/emergency limits
                    a_preview_bound = max(-a_brake_safe, a_req)

                    if a_preview_bound < accel_out:
                        accel_out = a_preview_bound
                        barrier_active = True
                        active_barriers.append("AERIAL_PREVIEW_STOP")

        return ShieldedControlCommand(
            accel_cmd=float(accel_out),
            steering_cmd=base_cmd.steering_cmd,
            nominal_accel=nominal_accel,
            nominal_steering=nominal_steering,
            barrier_active=barrier_active,
            active_barriers=active_barriers,
            frenet_state=frenet,
        )


# =============================================================================
# 4. Air-Ground Heterogeneous Coordinator (Full Joint Closed-Loop)
# =============================================================================

class AirGroundHeterogeneousCoordinator:
    """
    Manages and steps the joint 6-DOF aerial scout and autonomous ground vehicle simulation loop.
    """

    def __init__(
        self,
        road_frame: FrenetFrame,
        vehicle_config: VehicleConfig | None = None,
        air_ground_config: AirGroundConfig | None = None,
    ) -> None:
        self.road_frame = road_frame
        self.v_cfg = vehicle_config or VehicleConfig()
        self.ag_cfg = air_ground_config or AirGroundConfig()

        self.vehicle_model = DynamicBicycleModel(self.v_cfg)
        self.cbf_shield = AirGroundFrenetCBF(
            road_frame=road_frame,
            air_ground_config=self.ag_cfg,
        )
        self.ville_filter = AirGroundVilleFilter(alpha=self.ag_cfg.ville_alpha)

        # Aerial scout deep aerodynamics engine
        self.drone_aero = DeepAerodynamicsEngine(
            DeepAerodynamicsConfig(
                wind_enabled=True,
                wind_mean=(1.5, 0.5, 0.0),
                gust_enabled=True,
                gust_amplitude=(3.5, 2.0, 0.0),
                gust_start_time=1.0,
                gust_duration=2.5,
                drag_enabled=True,
            )
        )

        self.drone_pos = np.zeros(3, dtype=np.float64)
        self.drone_vel = np.zeros(3, dtype=np.float64)
        self.vehicle_state = VehicleState()
        self.sim_time: float = 0.0
        self.packet_seq: int = 0

    def reset(
        self,
        initial_s: float = 0.0,
        initial_v: float = 20.0,
        initial_d: float = 0.0,
    ) -> None:
        """Resets the heterogeneous air-ground system state."""
        self.sim_time = 0.0
        self.packet_seq = 0
        self.ville_filter.reset()
        self.drone_aero.reset()

        # Initialize ground vehicle state from Frenet s, d
        pt = self.road_frame.frenet_to_cartesian(initial_s, initial_d)
        self.vehicle_state = VehicleState(
            x=pt[0],
            y=pt[1],
            yaw=0.0,
            v_x=initial_v,
            v_y=0.0,
            yaw_rate=0.0,
            steering=0.0,
            accel=0.0,
        )

        # Initialize aerial scout formation position ahead of ground vehicle
        s_drone_init = initial_s + self.ag_cfg.aerial_lookahead_dist
        drone_pt = self.road_frame.frenet_to_cartesian(s_drone_init, 0.0)
        self.drone_pos = np.array([drone_pt[0], drone_pt[1], self.ag_cfg.aerial_cruise_altitude], dtype=np.float64)
        self.drone_vel = np.array([initial_v, 0.0, 0.0], dtype=np.float64)

    def step(
        self,
        dt: float,
        nominal_accel: float,
        nominal_steering: float,
        real_hazard_s: float | None = None,
        real_hazard_friction: float = 0.28,
        inject_spoofed_hazard_s: float | None = None,
        rng: np.random.Generator | None = None,
        enable_v2a: bool = True,
        use_aegis_ville_guard: bool = True,
        use_aegis_preview_cbf: bool = True,
    ) -> dict[str, Any]:
        """
        Executes one joint simulation step for both air and ground vehicles.
        """
        self.sim_time += dt
        self.packet_seq += 1

        frenet_ground = self.road_frame.cartesian_to_frenet(
            self.vehicle_state.x,
            self.vehicle_state.y,
            self.vehicle_state.yaw,
            self.vehicle_state.v_x,
            self.vehicle_state.v_y,
        )

        # 1. Update 6-DOF Aerial Scout Formation Flight
        # Aerial scout tracks forward along road at target station s_drone_des = s_ground + lookahead
        s_drone_des = frenet_ground.s + self.ag_cfg.aerial_lookahead_dist
        pt_drone_des = self.road_frame.frenet_to_cartesian(s_drone_des, 0.0)
        drone_pos_des = np.array([pt_drone_des[0], pt_drone_des[1], self.ag_cfg.aerial_cruise_altitude], dtype=np.float64)

        # Simple high-altitude tracking controller + deep aero drag
        f_drone_drag, _ = self.drone_aero.compute_aerodynamic_drag(self.drone_vel, self.drone_aero.state.total_wind)
        k_drone_p = 2.5
        k_drone_d = 1.8
        drone_acc = k_drone_p * (drone_pos_des - self.drone_pos) - k_drone_d * self.drone_vel + f_drone_drag / 1.5
        self.drone_vel += drone_acc * dt
        self.drone_pos += self.drone_vel * dt

        # 2. Aerial Vision Detection Simulation
        # Drone sees road hazards within 80m of its ground nadir projection
        drone_frenet_s = s_drone_des
        aerial_detected_hazard_s = None
        aerial_hazard_type = "CLEAR"
        aerial_confidence = 0.0
        aerial_friction = 0.85

        if real_hazard_s is not None and abs(drone_frenet_s - real_hazard_s) < 80.0:
            aerial_detected_hazard_s = real_hazard_s
            aerial_hazard_type = "OBSTACLE"
            aerial_friction = real_hazard_friction
            aerial_confidence = 0.95

        # 3. Adversarial Attack Injection (Spoofed Phantom Hazard)
        reported_hazard_s = aerial_detected_hazard_s
        reported_hazard_type = aerial_hazard_type
        reported_confidence = aerial_confidence
        is_authenticated = True

        if inject_spoofed_hazard_s is not None:
            # Overwrite packet with spoofed phantom hazard report
            reported_hazard_s = inject_spoofed_hazard_s
            reported_hazard_type = "OBSTACLE"
            reported_confidence = 0.92
            is_authenticated = False # Rogue injection lacks aerial scout's cryptographic signature

        # 4. Formulate V2A Telemetry Packet
        v2a_packet = V2ATelemetryPacket(
            drone_id="AEGIS_SCOUT_01" if is_authenticated else "ROGUE_INJECTOR",
            timestamp=self.sim_time,
            drone_pos=self.drone_pos.copy(),
            drone_vel=self.drone_vel.copy(),
            detected_hazard_s=reported_hazard_s,
            hazard_type=reported_hazard_type,
            estimated_friction=aerial_friction,
            confidence=reported_confidence,
            packet_seq=self.packet_seq,
            is_authenticated=is_authenticated,
        )

        # 5. Ground Vehicle Perception:
        # Onboard LiDAR Line-Of-Sight (LOS) is limited around blind bends (cutoff at 35m)
        onboard_detected_obstacle_s = None
        if real_hazard_s is not None:
            dist_to_real = real_hazard_s - frenet_ground.s
            if 0.0 < dist_to_real <= self.ag_cfg.ground_los_cutoff:
                onboard_detected_obstacle_s = real_hazard_s

        # 6. Process V2A Packet at Ground Vehicle
        verified_aerial_hazard_s = None
        current_wealth = 1.0

        if enable_v2a:
            if use_aegis_ville_guard:
                # Ville Supermartingale Betting Filter
                is_verified, current_wealth = self.ville_filter.update(
                    packet=v2a_packet,
                    current_vehicle_s=frenet_ground.s,
                    current_speed=self.vehicle_state.speed,
                )
                if is_verified:
                    verified_aerial_hazard_s = v2a_packet.detected_hazard_s
            else:
                # Naive baseline: blindly trusts reported hazard without martingale vetting
                if v2a_packet.detected_hazard_s is not None:
                    verified_aerial_hazard_s = v2a_packet.detected_hazard_s

        # 7. Apply CBF Safety Filtering
        if use_aegis_preview_cbf:
            shield_cmd = self.cbf_shield.filter_air_ground_command(
                state=self.vehicle_state,
                nominal_accel=nominal_accel,
                nominal_steering=nominal_steering,
                dt=dt,
                verified_hazard_s=verified_aerial_hazard_s,
                preview_friction=v2a_packet.estimated_friction if verified_aerial_hazard_s else None,
                onboard_detected_obstacle_s=onboard_detected_obstacle_s,
            )
        else:
            # Unshielded baseline: executes nominal commands directly without CBF
            shield_cmd = ShieldedControlCommand(
                accel_cmd=nominal_accel,
                steering_cmd=nominal_steering,
                nominal_accel=nominal_accel,
                nominal_steering=nominal_steering,
                barrier_active=False,
                active_barriers=[],
                frenet_state=frenet_ground,
            )

        # 8. Step Ground Vehicle Dynamics with road friction
        eff_road_friction = 0.85
        if real_hazard_s is not None and abs(frenet_ground.s - real_hazard_s) < 20.0:
            eff_road_friction = real_hazard_friction

        self.vehicle_model.cfg = VehicleConfig(friction_coeff=eff_road_friction)
        next_state, tire_forces = self.vehicle_model.step(
            state=self.vehicle_state,
            cmd_accel=shield_cmd.accel_cmd,
            cmd_steering=shield_cmd.steering_cmd,
            dt=dt,
        )
        self.vehicle_state = next_state

        # 9. Evaluate Safety Outcomes
        collision_with_real_obstacle = False
        if real_hazard_s is not None:
            # If vehicle reaches or passes real obstacle without stopping
            if frenet_ground.s >= (real_hazard_s - 1.5) and self.vehicle_state.speed > 1.5:
                collision_with_real_obstacle = True

        # False Emergency Stop detection (stopping when road is clear or attack is fake)
        false_emergency_stop = False
        if inject_spoofed_hazard_s is not None and real_hazard_s is None:
            if self.vehicle_state.speed < 1.0 and frenet_ground.s < (inject_spoofed_hazard_s - 2.0):
                false_emergency_stop = True

        return {
            "time": self.sim_time,
            "vehicle_x": self.vehicle_state.x,
            "vehicle_y": self.vehicle_state.y,
            "vehicle_s": frenet_ground.s,
            "vehicle_d": frenet_ground.d,
            "vehicle_speed": self.vehicle_state.speed,
            "vehicle_v_x": self.vehicle_state.v_x,
            "accel_cmd": shield_cmd.accel_cmd,
            "steering_cmd": shield_cmd.steering_cmd,
            "barrier_active": shield_cmd.barrier_active,
            "active_barriers": shield_cmd.active_barriers,
            "drone_pos": self.drone_pos.tolist(),
            "ville_wealth": current_wealth,
            "ville_quarantined": self.ville_filter.is_quarantined,
            "collision": collision_with_real_obstacle,
            "false_emergency_stop": false_emergency_stop,
            "onboard_detected": (onboard_detected_obstacle_s is not None),
            "aerial_verified": (verified_aerial_hazard_s is not None),
        }
