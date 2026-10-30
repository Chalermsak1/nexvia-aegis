"""Real-Time Safety Watchdog and Latency-Compensating State Machine for Embedded Flight.

Ensures that transport latency (20-30ms), sensor dropouts, and communication
jitter do not violate safety barrier forward invariance. Provides deterministic
failsafe degradation levels for companion computers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
import numpy as np

from aegis.sim2real.mavlink_protocol import FailsafeAction, PX4FlightMode


class WatchdogHealthState(Enum):
    """Real-time health status of companion computer safety loop."""
    UNINITIALIZED = auto()
    HEALTHY_NOMINAL = auto()
    LATENCY_COMPENSATED = auto()
    VISION_DEGRADED = auto()
    COMMUNICATION_TIMEOUT = auto()
    BATTERY_CRITICAL = auto()
    FAILSAFE_ACTIVE = auto()


@dataclass
class HardwareWatchdogConfig:
    """Configurable timing thresholds for real-time watchdog."""
    heartbeat_timeout_s: float = 0.050    # 50 ms loop heartbeat (20 Hz min)
    odometry_timeout_s: float = 0.040     # 40 ms state feedback (25 Hz min)
    perception_timeout_s: float = 0.150   # 150 ms vision pipeline timeout
    nominal_sensor_latency_s: float = 0.025  # 25 ms typical RealSense/Ouster latency
    max_latency_extrapolation_s: float = 0.060  # 60 ms max forward projection
    battery_warn_v: float = 14.4          # 3.6V per cell (4S LiPo)
    battery_critical_v: float = 13.6      # 3.4V per cell (4S LiPo)


@dataclass
class WatchdogDiagnostic:
    """Diagnostic telemetry snapshot emitted at each safety evaluation."""
    timestamp_s: float = 0.0
    health_state: WatchdogHealthState = WatchdogHealthState.HEALTHY_NOMINAL
    recommended_action: FailsafeAction = FailsafeAction.NONE
    odometry_age_ms: float = 0.0
    perception_age_ms: float = 0.0
    latency_comp_applied_ms: float = 0.0
    battery_voltage_v: float = 16.8
    failsafe_reason: str = "Nominal"


class RealtimeSafetyWatchdog:
    """Hardware watchdog monitoring message freshness, transport jitter, and battery limits."""

    def __init__(self, config: HardwareWatchdogConfig | None = None) -> None:
        self.config = config or HardwareWatchdogConfig()
        self.last_odometry_time_s: float = 0.0
        self.last_perception_time_s: float = 0.0
        self.last_heartbeat_time_s: float = 0.0
        self.consecutive_timeouts: int = 0
        self.current_state = WatchdogHealthState.HEALTHY_NOMINAL

    def record_heartbeat(self, now_s: float) -> None:
        self.last_heartbeat_time_s = now_s

    def record_odometry(self, now_s: float) -> None:
        self.last_odometry_time_s = now_s

    def record_perception(self, now_s: float) -> None:
        self.last_perception_time_s = now_s

    def extrapolate_state_for_latency(
        self,
        position: np.ndarray,
        velocity: np.ndarray,
        now_s: float,
        data_timestamp_s: float,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        """Forward-extrapolates position to compensate for sensor transport delay.

        p_projected = p + v * dt_comp
        """
        raw_latency = max(0.0, now_s - data_timestamp_s)
        dt_comp = min(raw_latency, self.config.max_latency_extrapolation_s)

        extrapolated_pos = position + velocity * dt_comp
        extrapolated_vel = velocity  # Constant-velocity model during short latency gap
        return extrapolated_pos, extrapolated_vel, dt_comp

    def evaluate_health(
        self,
        now_s: float,
        battery_voltage_v: float = 16.8,
        martingale_violation: bool = False,
    ) -> WatchdogDiagnostic:
        """Evaluates health criteria and determines safety actions."""
        has_odom = self.last_odometry_time_s > 0.0
        has_perc = self.last_perception_time_s > 0.0

        odom_age = (now_s - self.last_odometry_time_s) if has_odom else float("inf")
        perc_age = (now_s - self.last_perception_time_s) if has_perc else float("inf")

        diagnostic = WatchdogDiagnostic(
            timestamp_s=now_s,
            odometry_age_ms=odom_age * 1000.0 if has_odom else float("inf"),
            perception_age_ms=perc_age * 1000.0 if has_perc else float("inf"),
            battery_voltage_v=battery_voltage_v,
        )

        # 1. Critical Battery Failsafe
        if battery_voltage_v <= self.config.battery_critical_v:
            self.current_state = WatchdogHealthState.BATTERY_CRITICAL
            diagnostic.health_state = self.current_state
            diagnostic.recommended_action = FailsafeAction.EMERGENCY_LAND
            diagnostic.failsafe_reason = f"Battery critical ({battery_voltage_v:.2f}V <= {self.config.battery_critical_v:.2f}V)"
            return diagnostic

        # 2. Martingale Sensor Corruption Failsafe (Ville E-Process Detection)
        if martingale_violation:
            self.current_state = WatchdogHealthState.FAILSAFE_ACTIVE
            diagnostic.health_state = self.current_state
            diagnostic.recommended_action = FailsafeAction.SAFE_ABSTENTION_LOITER
            diagnostic.failsafe_reason = "Ville Supermartingale Wealth threshold crossed (Sensor Corrupted/Spoofed)"
            return diagnostic

        # 3. Uninitialized Odometry (no odometry telemetry received yet)
        if not has_odom:
            self.current_state = WatchdogHealthState.UNINITIALIZED
            diagnostic.health_state = self.current_state
            diagnostic.recommended_action = FailsafeAction.POSITION_HOLD_HOVER
            diagnostic.failsafe_reason = "Odometry uninitialized: no EKF2 state packet received yet"
            return diagnostic

        # 4. Odometry Communication Timeout
        if odom_age > self.config.odometry_timeout_s:
            self.consecutive_timeouts += 1
            if odom_age > self.config.odometry_timeout_s * 5.0:  # > 200 ms total loss
                self.current_state = WatchdogHealthState.FAILSAFE_ACTIVE
                diagnostic.health_state = self.current_state
                diagnostic.recommended_action = FailsafeAction.EMERGENCY_LAND
                diagnostic.failsafe_reason = f"Severe EKF2 Odometry Loss ({odom_age*1000:.1f}ms > 200ms)"
            else:
                self.current_state = WatchdogHealthState.COMMUNICATION_TIMEOUT
                diagnostic.health_state = self.current_state
                diagnostic.recommended_action = FailsafeAction.POSITION_HOLD_HOVER
                diagnostic.failsafe_reason = f"Odometry timeout ({odom_age*1000:.1f}ms > {self.config.odometry_timeout_s*1000:.1f}ms)"
            return diagnostic

        # 5. Perception Timeout or Uninitialized Perception Feed
        if not has_perc or perc_age > self.config.perception_timeout_s:
            self.current_state = WatchdogHealthState.VISION_DEGRADED
            diagnostic.health_state = self.current_state
            diagnostic.recommended_action = FailsafeAction.VELOCITY_AIR_BRAKE
            diagnostic.failsafe_reason = (
                "Perception uninitialized (no visual/LiDAR feed received yet) - Engaging air-brake"
                if not has_perc
                else f"Perception feed delayed ({perc_age*1000:.1f}ms > {self.config.perception_timeout_s*1000:.1f}ms) - Engaging air-brake"
            )
            return diagnostic

        # 6. Healthy Nominal State (with latency compensation)
        self.consecutive_timeouts = 0
        if odom_age > 0.010:
            self.current_state = WatchdogHealthState.LATENCY_COMPENSATED
        else:
            self.current_state = WatchdogHealthState.HEALTHY_NOMINAL

        diagnostic.health_state = self.current_state
        diagnostic.recommended_action = FailsafeAction.NONE
        diagnostic.failsafe_reason = "Nominal"
        return diagnostic
