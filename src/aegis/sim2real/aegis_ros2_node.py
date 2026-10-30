"""Experimental companion-computer control model for NEXVIA AEGIS.

Implements real-time 200 Hz inner-loop attitude setpoint generation,
latency-compensated HOCBF safety filtering, UKF obstacle tracking, and
Active POMDP camera saccade control for PX4 Autopilot.

Provides a standalone pure-Python test harness. Live ROS 2 transport is not
implemented; the live interface fails explicitly until it can be validated.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any
import numpy as np

from aegis.sim2real.mavlink_protocol import (
    AttitudeTargetSetpoint,
    BatteryTelemetry,
    DroneOdometry,
    FailsafeAction,
    PX4FlightMode,
    force_vector_to_attitude_and_thrust,
    quaternion_to_euler_angles,
)
from aegis.sim2real.safety_watchdog import (
    HardwareWatchdogConfig,
    RealtimeSafetyWatchdog,
    WatchdogDiagnostic,
    WatchdogHealthState,
)
from aegis.vision.active_pomdp_gaze import (
    ActiveGazeDecision,
    ActiveVisionConfig,
    ActiveVisionPOMDPController,
)
from aegis.vision.depth_lidar_sensor import SensorObservation
from aegis.vision.ukf_obstacle_tracker import (
    MultiObstacleUKFTracker,
    TrackedObstacle3D,
    UKFTrackerConfig,
)

# Optional ROS 2 rclpy import
try:
    import rclpy
    from rclpy.node import Node as RclpyNode
    _HAS_RCLPY = True
except ImportError:
    _HAS_RCLPY = False
    RclpyNode = object  # type: ignore


@dataclass
class AegisNodeConfig:
    """Configuration parameters for AEGIS ROS 2 Node."""
    control_rate_hz: float = 200.0       # 200 Hz inner loop to PX4
    perception_rate_hz: float = 20.0    # 20 Hz vision/LiDAR update loop
    drone_mass_kg: float = 1.25
    max_thrust_n: float = 25.0
    max_tilt_deg: float = 35.0
    target_pos: np.ndarray = field(default_factory=lambda: np.array([2.5, 0.0, 1.0], dtype=np.float64))
    nominal_speed_m_s: float = 1.0
    obstacle_detection_timeout_s: float = 0.25
    ville_alpha: float = 0.05            # Ville threshold = 1/alpha = 20.0


class AegisROS2DroneNode(RclpyNode):
    """Standalone companion-computer control model.

    Intended future ROS 2 subscriptions (not implemented here):
      - /mavros/local_position/pose (geometry_msgs/msg/PoseStamped)
      - /mavros/local_position/velocity_local (geometry_msgs/msg/TwistStamped)
      - /perception/obstacles (custom list of SensorObservation or PoseArray)
      - /mavros/battery (sensor_msgs/msg/BatteryState)

    Intended future ROS 2 publishers (current methods record in memory only):
      - /mavros/setpoint_raw/attitude (mavros_msgs/msg/AttitudeTarget) @ 200 Hz
      - /camera/gimbal_setpoint (geometry_msgs/msg/Vector3) @ 20 Hz
      - /aegis/diagnostics (telemetry JSON / diagnostic message)
    """

    def __init__(self, config: AegisNodeConfig | None = None) -> None:
        if _HAS_RCLPY:
            raise RuntimeError("ROS 2 transport is not implemented or validated; use the standalone simulation harness")
        self.config = config or AegisNodeConfig()

        # Initialize sub-modules
        self.watchdog = RealtimeSafetyWatchdog(HardwareWatchdogConfig())
        self.ukf_tracker = MultiObstacleUKFTracker(UKFTrackerConfig(confirmation_hits=2))
        self.pomdp_controller = ActiveVisionPOMDPController(
            ActiveVisionConfig(
                drone_radius=0.20,
                uncertainty_safe_thresh=0.08,
                nominal_speed=self.config.nominal_speed_m_s,
                robot_mass=self.config.drone_mass_kg,
            )
        )

        # State storage
        self.current_odom = DroneOdometry()
        self.current_battery = BatteryTelemetry()
        self.martingale_wealth: float = 1.0
        self.martingale_violation: bool = False
        self.latest_attitude_target = AttitudeTargetSetpoint()
        self.latest_gimbal_decision: ActiveGazeDecision | None = None
        self.telemetry_history: list[dict[str, Any]] = []

        # ROS 2 Publisher setpoint queues / streams
        self.published_attitude_setpoints: list[dict[str, Any]] = []
        self.published_gimbal_setpoints: list[dict[str, Any]] = []
        self.published_diagnostics: list[dict[str, Any]] = []

    def _init_ros2_interfaces(self) -> None:
        """Prevent a live node from silently using in-memory test recorders."""
        raise RuntimeError("ROS 2 transport is not implemented or validated; use the standalone simulation harness")

    def publish_attitude_target(self, setpoint: AttitudeTargetSetpoint) -> None:
        """Record a simulated attitude setpoint in memory; no ROS message is sent."""
        data = {
            "timestamp_s": setpoint.timestamp_s,
            "orientation_wxyz": setpoint.orientation_wxyz.copy(),
            "thrust_normalized": float(setpoint.thrust_normalized),
            "body_rate_rad_s": setpoint.body_rate_rad_s.copy(),
            "type_mask": int(setpoint.type_mask),
        }
        self.published_attitude_setpoints.append(data)

    def publish_gimbal_target(self, pan_deg: float, tilt_deg: float) -> None:
        """Record a simulated camera setpoint in memory."""
        data = {
            "pan_deg": float(pan_deg),
            "tilt_deg": float(tilt_deg),
            "timestamp_s": time.time(),
        }
        self.published_gimbal_setpoints.append(data)

    def publish_diagnostics(self, diag: WatchdogDiagnostic) -> None:
        """Record simulated health and safety diagnostics in memory."""
        data = {
            "timestamp_s": diag.timestamp_s,
            "health_state": diag.health_state.name,
            "recommended_action": diag.recommended_action.name,
            "failsafe_reason": diag.failsafe_reason,
            "odometry_age_ms": diag.odometry_age_ms,
            "perception_age_ms": diag.perception_age_ms,
            "battery_voltage_v": diag.battery_voltage_v,
        }
        self.published_diagnostics.append(data)

    # ------------------------------------------------------------------
    # Data Ingestion Callbacks (can be called by ROS 2 or test harness)
    # ------------------------------------------------------------------
    def ingest_odometry(
        self,
        position: np.ndarray,
        quaternion_wxyz: np.ndarray,
        linear_velocity: np.ndarray,
        angular_velocity: np.ndarray,
        timestamp_s: float,
    ) -> None:
        """Ingests state estimate from PX4 EKF2."""
        vectors = (position, quaternion_wxyz, linear_velocity, angular_velocity)
        shapes = ((3,), (4,), (3,), (3,))
        if any(np.shape(value) != shape or not np.all(np.isfinite(value))
               for value, shape in zip(vectors, shapes)):
            return
        if np.linalg.norm(quaternion_wxyz) <= 1e-8:
            return
        if not self.watchdog.record_odometry(timestamp_s):
            return
        self.current_odom.timestamp_s = timestamp_s
        self.current_odom.position = np.copy(position)
        self.current_odom.quaternion_wxyz = np.copy(quaternion_wxyz)
        self.current_odom.linear_velocity = np.copy(linear_velocity)
        self.current_odom.angular_velocity = np.copy(angular_velocity)

    def ingest_perception_clusters(
        self,
        clusters: list[tuple[np.ndarray, float]],
        timestamp_s: float,
        dt: float = 0.05,
    ) -> None:
        """Ingests 3D obstacle clusters (centroid_xyz, radius) from LiDAR/camera clustering."""
        if not math.isfinite(dt) or dt <= 0.0:
            return
        if any(np.shape(center) != (3,) or not np.all(np.isfinite(center))
               or not math.isfinite(radius) or radius < 0.0 for center, radius in clusters):
            return
        if not self.watchdog.record_perception(timestamp_s):
            return
        self.ukf_tracker.update_from_clusters(clusters, dt=dt)

    def ingest_perception(
        self,
        clusters: list[tuple[np.ndarray, float]],
        timestamp_s: float,
        dt: float = 0.05,
    ) -> None:
        """Standard perception callback."""
        self.ingest_perception_clusters(clusters, timestamp_s, dt)

    def ingest_battery(
        self,
        voltage_v: float,
        current_a: float,
        percentage: float,
        timestamp_s: float,
    ) -> None:
        """Ingests battery power telemetry."""
        if (not all(math.isfinite(v) for v in (voltage_v, current_a, percentage, timestamp_s))
                or voltage_v <= 0.0 or timestamp_s <= self.current_battery.timestamp_s):
            return
        self.current_battery.timestamp_s = timestamp_s
        self.current_battery.voltage_v = voltage_v
        self.current_battery.current_a = current_a
        self.current_battery.percentage = percentage

    def update_martingale_sensor_check(
        self,
        cross_modal_residual: float,
        threshold_sigma: float = 0.15,
    ) -> None:
        """Updates anytime-valid Ville supermartingale betting process.

        If cross-modal sensor discrepancy persists, wealth M_t exponentially
        grows until crossing 1 / alpha (e.g. 20.0), triggering abstention.
        """
        # Ville betting score
        betting_factor = math.exp(0.5 * (abs(cross_modal_residual) / threshold_sigma - 1.0))
        betting_factor = float(np.clip(betting_factor, 0.5, 3.0))
        self.martingale_wealth *= betting_factor

        if self.martingale_wealth >= (1.0 / self.config.ville_alpha):
            self.martingale_violation = True
        elif cross_modal_residual < 0.05:
            # Slow recovery if nominal
            self.martingale_wealth = max(1.0, self.martingale_wealth * 0.95)
            if self.martingale_wealth < (0.5 / self.config.ville_alpha):
                self.martingale_violation = False

    # ------------------------------------------------------------------
    # 200 Hz Core Control and Safety Evaluation Cycle
    # ------------------------------------------------------------------
    def step_control_cycle(self, now_s: float) -> tuple[AttitudeTargetSetpoint, WatchdogDiagnostic]:
        """Execute one simulated control cycle; real-time timing is not established."""
        self.watchdog.record_heartbeat(now_s)

        # 1. Evaluate Watchdog Health & Latency Compensation
        if math.isfinite(now_s) and self.current_battery.timestamp_s > now_s:
            # Discard a packet from another clock domain so a later valid one can recover.
            self.current_battery.timestamp_s = 0.0
        diag = self.watchdog.evaluate_health(
            now_s=now_s,
            battery_voltage_v=(self.current_battery.voltage_v
                               if self.current_battery.timestamp_s > 0.0 else float("nan")),
            martingale_violation=self.martingale_violation,
        )

        # Apply latency extrapolation for HOCBF forward projection
        extrapolated_pos, extrapolated_vel, dt_comp = self.watchdog.extrapolate_state_for_latency(
            position=self.current_odom.position,
            velocity=self.current_odom.linear_velocity,
            now_s=now_s,
            data_timestamp_s=self.current_odom.timestamp_s,
        )
        diag.latency_comp_applied_ms = dt_comp * 1000.0

        # Extract current yaw
        _, _, current_yaw = quaternion_to_euler_angles(self.current_odom.quaternion_wxyz)

        # 2. Check Failsafe Emergency Actions
        if diag.recommended_action == FailsafeAction.EMERGENCY_LAND:
            # Commanded emergency vertical descent
            safe_force = np.array([0.0, 0.0, 0.7 * self.config.drone_mass_kg * 9.81], dtype=np.float64)
            quat, thrust = force_vector_to_attitude_and_thrust(
                desired_force_world=safe_force,
                desired_yaw_rad=current_yaw,
                mass_kg=self.config.drone_mass_kg,
                max_thrust_n=self.config.max_thrust_n,
            )
            setpoint = AttitudeTargetSetpoint(
                timestamp_s=now_s,
                orientation_wxyz=quat,
                thrust_normalized=thrust,
            )
            self.latest_attitude_target = setpoint
            self.publish_attitude_target(setpoint)
            self.publish_diagnostics(diag)
            return setpoint, diag

        if diag.recommended_action in (FailsafeAction.POSITION_HOLD_HOVER, FailsafeAction.SAFE_ABSTENTION_LOITER):
            # Commanded hover in place (zero horizontal acceleration)
            v_err_xy = -1.5 * self.current_odom.linear_velocity[:2]
            f_xy = np.clip(v_err_xy, -3.0, 3.0)
            f_z = self.config.drone_mass_kg * 9.81
            safe_force = np.array([f_xy[0], f_xy[1], f_z], dtype=np.float64)
            quat, thrust = force_vector_to_attitude_and_thrust(
                desired_force_world=safe_force,
                desired_yaw_rad=current_yaw,
                mass_kg=self.config.drone_mass_kg,
                max_thrust_n=self.config.max_thrust_n,
            )
            setpoint = AttitudeTargetSetpoint(
                timestamp_s=now_s,
                orientation_wxyz=quat,
                thrust_normalized=thrust,
            )
            self.latest_attitude_target = setpoint
            self.publish_attitude_target(setpoint)
            self.publish_diagnostics(diag)
            return setpoint, diag

        if diag.recommended_action == FailsafeAction.VELOCITY_AIR_BRAKE:
            # Commanded active aerodynamic deceleration opposing horizontal motion
            v_brake_xy = -3.0 * self.current_odom.linear_velocity[:2]
            f_xy = np.clip(v_brake_xy, -6.0, 6.0)
            f_z = self.config.drone_mass_kg * 9.81
            safe_force = np.array([f_xy[0], f_xy[1], f_z], dtype=np.float64)
            quat, thrust = force_vector_to_attitude_and_thrust(
                desired_force_world=safe_force,
                desired_yaw_rad=current_yaw,
                mass_kg=self.config.drone_mass_kg,
                max_thrust_n=self.config.max_thrust_n,
                max_tilt_rad=math.radians(self.config.max_tilt_deg),
            )
            setpoint = AttitudeTargetSetpoint(
                timestamp_s=now_s,
                orientation_wxyz=quat,
                thrust_normalized=thrust,
            )
            self.latest_attitude_target = setpoint
            self.publish_attitude_target(setpoint)
            self.publish_diagnostics(diag)
            return setpoint, diag

        # 3. Active Vision POMDP Saccade & Shielded Navigation
        confirmed_tracks = self.ukf_tracker.get_confirmed_tracks()
        gaze_decision = self.pomdp_controller.plan_step(
            drone_pos=extrapolated_pos,
            drone_vel=extrapolated_vel,
            drone_yaw_deg=math.degrees(current_yaw),
            target_pos=self.config.target_pos,
            tracked_obstacles=confirmed_tracks,
        )
        self.latest_gimbal_decision = gaze_decision
        self.publish_gimbal_target(gaze_decision.desired_pan_deg, gaze_decision.desired_tilt_deg)

        # Convert 3D safe force to PX4 orientation quaternion and normalized thrust
        quat, thrust = force_vector_to_attitude_and_thrust(
            desired_force_world=gaze_decision.safe_force,
            desired_yaw_rad=current_yaw,
            mass_kg=self.config.drone_mass_kg,
            max_thrust_n=self.config.max_thrust_n,
            max_tilt_rad=math.radians(self.config.max_tilt_deg),
        )

        setpoint = AttitudeTargetSetpoint(
            timestamp_s=now_s,
            orientation_wxyz=quat,
            thrust_normalized=thrust,
        )
        self.latest_attitude_target = setpoint
        self.publish_attitude_target(setpoint)
        self.publish_diagnostics(diag)

        # Record telemetry
        barrier_active = not np.allclose(gaze_decision.safe_force, gaze_decision.nominal_force, atol=1e-3)
        min_clearance = min(gaze_decision.effective_clearance_margins) if gaze_decision.effective_clearance_margins else 999.0
        self.telemetry_history.append({
            "timestamp_s": now_s,
            "pos": extrapolated_pos.tolist(),
            "thrust": thrust,
            "health": diag.health_state.name,
            "barrier_active": barrier_active,
            "saccade_active": gaze_decision.is_actively_probing,
            "martingale_wealth": self.martingale_wealth,
            "min_clearance": min_clearance,
        })

        return setpoint, diag

    def _on_control_cycle(self) -> None:
        """Internal ROS 2 timer callback."""
        now_s = time.time()
        self.step_control_cycle(now_s)
