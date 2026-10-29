"""
Autoware.Universe & ROS 2 Humble Integration Bridge for Autonomous Ground Vehicles.

Maps:
  - Subscriptions: /localization/kinematic_state (nav_msgs/Odometry)
  - Subscriptions: /perception/object_recognition/objects
  - Subscriptions: /v2x/platoon_telemetry
  - Publishers: /control/command/control_cmd (AckermannControlCommand)
  - Publishers: /aegis/av_safety_state (std_msgs/String)

Supports dynamic fallback to standalone execution when rclpy is not installed.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
import numpy as np

from aegis.av.frenet_cbf_shield import FrenetCbfConfig, FrenetSafetyShield, ShieldedControlCommand
from aegis.av.platooning_brmc import CyberResilientPlatoonController, PlatoonConfig, V2XTelemetryPacket
from aegis.av.vehicle_dynamics import DynamicBicycleModel, FrenetFrame, FrenetState, VehicleConfig, VehicleState

try:
    import rclpy
    from rclpy.node import Node
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    Node = object # type: ignore


@dataclass
class AckermannControlCommand:
    """Standard Autoware / ROS 2 Ackermann control command."""
    stamp_sec: float
    steering_tire_angle: float        # Desired front wheel angle (rad)
    steering_tire_rotation_rate: float # Desired steering rate (rad/s)
    speed: float                      # Target velocity (m/s)
    acceleration: float               # Commanded longitudinal acceleration (m/s^2)
    jerk: float                       # Commanded jerk (m/s^3)


class AegisAutowareVehicleNode(Node if ROS2_AVAILABLE else object):
    """
    ROS 2 Autoware Bridge Companion Node.
    Filters high-level path tracking commands through Frenet HOCBF and Kamm's friction circle.
    """

    def __init__(
        self,
        vehicle_id: int = 1,
        vehicle_config: VehicleConfig | None = None,
        cbf_config: FrenetCbfConfig | None = None,
        platoon_config: PlatoonConfig | None = None,
        road_waypoints: np.ndarray | None = None,
    ) -> None:
        if ROS2_AVAILABLE:
            super().__init__(f"aegis_av_node_{vehicle_id}")

        self.vehicle_id = vehicle_id
        self.v_cfg = vehicle_config or VehicleConfig()
        self.cbf_cfg = cbf_config or FrenetCbfConfig()
        self.p_cfg = platoon_config or PlatoonConfig()

        default_waypoints = road_waypoints if road_waypoints is not None else np.array([
            [0.0, 0.0], [50.0, 0.0], [100.0, 10.0], [150.0, 30.0], [200.0, 30.0],
        ])
        self.road_frame = FrenetFrame(default_waypoints)
        self.dyn_model = DynamicBicycleModel(self.v_cfg)
        self.shield = FrenetSafetyShield(self.v_cfg, self.cbf_cfg)
        self.platoon_ctrl = CyberResilientPlatoonController(self.vehicle_id, self.v_cfg, self.p_cfg)

        self.current_state = VehicleState()
        self.latest_command: AckermannControlCommand | None = None
        self.step_count = 0

    def step_standalone(
        self,
        current_time: float,
        state: VehicleState,
        nom_accel: float,
        nom_steering: float,
        radar_dist: float | None = None,
        radar_rel_speed: float | None = None,
        v2x_packet: V2XTelemetryPacket | None = None,
    ) -> tuple[AckermannControlCommand, ShieldedControlCommand]:
        """
        Executes one control cycle in standalone simulation (50 Hz).
        Returns: (ackermann_cmd, shielded_details)
        """
        self.step_count += 1
        self.current_state = state

        # 1. Project onto Frenet Frame
        frenet = self.road_frame.cartesian_to_frenet(
            state.x, state.y, state.yaw, state.v_x, state.v_y,
        )

        # 2. Check Platoon Cyber-Resilience if telemetry present
        if radar_dist is not None and radar_rel_speed is not None:
            safe_a, safe_delta, _ = self.platoon_ctrl.update_v2x_and_control(
                current_state=state,
                current_time=current_time,
                radar_distance=radar_dist,
                radar_rel_speed=radar_rel_speed,
                v2x_packet=v2x_packet,
                road_frame=self.road_frame,
            )
            # Re-evaluate with shield for safety guarantee
            lead_s = frenet.s + radar_dist
            lead_v = state.v_x + radar_rel_speed
            shielded = self.shield.filter_control(
                state=state,
                frenet=frenet,
                nominal_accel=safe_a,
                nominal_steering=nom_steering,
                lead_vehicle_s=lead_s,
                lead_vehicle_speed=lead_v,
            )
        else:
            shielded = self.shield.filter_control(
                state=state,
                frenet=frenet,
                nominal_accel=nom_accel,
                nominal_steering=nom_steering,
            )

        # 3. Format as Ackermann Control Command
        target_v = max(0.0, state.v_x + shielded.accel_cmd * 0.02)
        cmd = AckermannControlCommand(
            stamp_sec=current_time,
            steering_tire_angle=shielded.steering_cmd,
            steering_tire_rotation_rate=0.0,
            speed=target_v,
            acceleration=shielded.accel_cmd,
            jerk=0.0,
        )
        self.latest_command = cmd
        return cmd, shielded
