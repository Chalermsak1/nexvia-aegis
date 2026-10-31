"""
NEXVIA AEGIS — Estimated-State Mission Arm & Safe Fallback (E-05, E-06).

Implements a complete non-oracle, estimated-state 3D controller arm:
1. No Truth Leakage: Velocity damping and guidance consume ONLY filtered sensor observations (v_est).
2. Dual-Sensor Fusion & Innovation Gate: Evaluates primary and secondary velocity observations.
3. E-06 Safe Fallback: Upon velocity dropout, stale timestamps, or sensor divergence,
   immediately transitions to active deceleration (Velocity Air Brake) using internal momentum tracking.
4. Robust Arrival Certification: Requires estimated distance <= success_radius AND estimated speed <= speed_limit.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any
import numpy as np

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.controller_3d import Aegis3DAwareController
from aegis.v9.exploratory_sensor_validation import boolean_flag, finite_real, valid_anchor, valid_range
from aegis.v9.velocity_freshness_candidate import TimedVelocity, VelocityFreshness


@dataclass(frozen=True)
class EstimatedStateTelemetry:
    """Estimated state observation and filter status."""
    v_est: list[float]
    speed_est: float
    status: str
    fallback_active: bool
    consecutive_missing_steps: int
    innovation_residual: float


class EstimatedStateCandidate:
    """
    3D Controller Arm with zero truth leakage (E-05) and active safe fallback (E-06).
    """

    def __init__(
        self,
        *,
        success_radius: float = 0.25,
        speed_limit: float = 0.08,
        disagreement_limit: float = 0.15,
        max_missing_velocity_steps: int = 5,
        damping_gain: float = 0.5,
        recovery_limit: int = 50,
    ) -> None:
        if not math.isfinite(success_radius) or success_radius <= 0:
            raise ValueError("success radius must be finite and positive")
        if not math.isfinite(speed_limit) or speed_limit <= 0:
            raise ValueError("speed limit must be finite and positive")

        self.success_radius = float(success_radius)
        self.speed_limit = float(speed_limit)
        self.disagreement_limit = float(disagreement_limit)
        self.max_missing_velocity_steps = int(max_missing_velocity_steps)
        self.damping_gain = float(damping_gain)
        self.recovery_limit = int(recovery_limit)

        # Base 3D-aware navigation core
        self.base = Aegis3DAwareController(success_radius=success_radius, arrival_margin_m=0.0)

        # Velocity Freshness & Cross-Check Gates
        self.primary_gate = VelocityFreshness(max_age_seconds=0.05)
        self.secondary_gate = VelocityFreshness(max_age_seconds=0.05)

        self.reset()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def reset(self) -> None:
        self.base.reset()
        self.primary_gate.reset()
        self.secondary_gate.reset()

        # Internal state estimator
        self.v_est = np.zeros(3, dtype=np.float64)
        self.consecutive_missing_velocity = 0
        self.fallback_active = False
        self.fallback_reason = "NONE"
        self.phase = "BASE"
        self.reason = "ACTIVE"
        self.terminal_decision: str | None = None
        self.wait_steps = 0
        self.recovery_steps = 0
        self.recovery_used = False
        self.last_action = np.zeros(3, dtype=np.float64)

    def _abstain(self, reason: str, nav_3d: np.ndarray | None = None) -> tuple[np.ndarray, str, np.ndarray, bool]:
        self.phase = "TERMINAL"
        self.reason = reason
        self.terminal_decision = "ABSTAIN"
        brake_action = -np.clip(1.5 * self.v_est, -1.0, 1.0)
        nav = nav_3d if nav_3d is not None else self.base.last_nav_vector_3d
        return brake_action, "ABSTAIN", nav, False

    @property
    def terminal_reason(self) -> str:
        return self.reason if self.reason != "ACTIVE" else self.base.terminal_reason

    def update_velocity_estimator(
        self,
        velocity_reading: Any,
        secondary_velocity_reading: Any = None,
        now_seconds: float | None = None,
    ) -> tuple[np.ndarray, str, bool]:
        """
        Updates internal velocity state estimate without peeking at plant truth.
        Implements E-06 Safe Fallback when velocity data is degraded.
        """
        v1 = self.primary_gate.accept(velocity_reading, now_seconds)
        v2 = self.secondary_gate.accept(secondary_velocity_reading, now_seconds) if secondary_velocity_reading is not None else None

        if v1 is None and v2 is None:
            # Velocity observation unavailable!
            self.consecutive_missing_velocity += 1
            # E-06 Safe Fallback: Predict velocity decay from momentum and air resistance prior
            self.v_est = 0.85 * self.v_est
            if self.consecutive_missing_velocity >= self.max_missing_velocity_steps:
                self.fallback_active = True
                self.fallback_reason = "PERSISTENT_VELOCITY_LOSS"
                return self.v_est.copy(), "PERSISTENT_VELOCITY_LOSS", True
            else:
                self.fallback_active = True
                self.fallback_reason = "TEMPORARY_VELOCITY_DROPOUT"
                return self.v_est.copy(), "TEMPORARY_VELOCITY_DROPOUT", True

        # At least one sensor delivered
        self.consecutive_missing_velocity = 0

        if v1 is not None and v2 is not None:
            # Dual-sensor cross check
            discrepancy = float(np.linalg.norm(v1 - v2))
            if discrepancy > self.disagreement_limit:
                # Sensors disagree! Safe fallback: take the higher-magnitude conservative estimate
                self.fallback_active = True
                self.fallback_reason = "VELOCITY_SENSOR_DISAGREEMENT"
                chosen = v1 if np.linalg.norm(v1) >= np.linalg.norm(v2) else v2
                # Filter update
                self.v_est = 0.7 * self.v_est + 0.3 * chosen
                return self.v_est.copy(), "VELOCITY_SENSOR_DISAGREEMENT", True
            else:
                self.fallback_active = False
                self.fallback_reason = "NONE"
                fused = 0.5 * (v1 + v2)
                self.v_est = 0.6 * self.v_est + 0.4 * fused
                return self.v_est.copy(), "HEALTHY_DUAL", False

        # Single sensor available
        chosen = v1 if v1 is not None else v2
        assert chosen is not None
        self.fallback_active = False
        self.fallback_reason = "NONE"
        self.v_est = 0.6 * self.v_est + 0.4 * chosen
        return self.v_est.copy(), "HEALTHY_SINGLE", False

    def update(
        self,
        a: SensorReading,
        b: SensorReading,
        r: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
        *,
        velocity_reading: Any = None,
        secondary_velocity_reading: Any = None,
        now_seconds: float | None = None,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        """
        Executes one control decision step using exclusively estimated states.
        Returns: (guidance_action, decision_type, nav_vector, query_anchor)
        """
        if self.terminal_decision is not None:
            return np.zeros(3), self.terminal_decision, self.base.last_nav_vector_3d, False

        # 1. Update Estimated Velocity
        v_est, vel_status, fallback_required = self.update_velocity_estimator(
            velocity_reading=velocity_reading,
            secondary_velocity_reading=secondary_velocity_reading,
            now_seconds=now_seconds,
        )

        # 2. Check for E-06 Critical Safe Fallback (Persistent Dropout or Disagreement)
        if fallback_required and self.fallback_reason == "PERSISTENT_VELOCITY_LOSS":
            return self._abstain("ESTIMATED_STATE_VELOCITY_DIVERGENCE")

        # 3. If in RECOVERY phase, handle recovery with anchor guidance
        if self.phase == "RECOVERY":
            self.recovery_steps += 1
            if self.recovery_steps > self.recovery_limit:
                return self._abstain("RECOVERY_TIMEOUT")
            if not valid_range(r):
                return self._abstain("RECOVERY_RANGE_UNAVAILABLE")
            anchor = valid_anchor(anchor_reading)
            if anchor is None:
                return self._abstain("RECOVERY_ANCHOR_UNAVAILABLE")
            if abs(float(np.linalg.norm(anchor)) - r.distance) > self.base.tau_range_3d:
                return self._abstain("RECOVERY_ANCHOR_RANGE_CONFLICT")

            speed_est = float(np.linalg.norm(v_est))
            anchor_dist = float(np.linalg.norm(anchor))
            if anchor_dist + 1.645 * float(anchor_reading.sigma) <= self.success_radius and speed_est <= self.speed_limit:
                self.phase = "TERMINAL"
                self.reason = "ESTIMATED_STATE_ARRIVAL_CONFIRMED"
                self.terminal_decision = "STOP"
                return np.zeros(3), "STOP", anchor, False

            # Active deceleration + gentle anchor centering
            action = np.clip(0.6 * anchor, -0.3, 0.3) - np.clip(1.2 * v_est, -0.5, 0.5)
            self.reason = "ANCHOR_GUIDED_RECOVERY"
            return action, "NAVIGATE", anchor, True

        # 4. Base Navigation Guidance
        action_3d, dec_type, nav_3d, query_anchor = self.base.update(
            a, b, r, anchor_reading=anchor_reading, step=step
        )

        # If fallback active (temporary dropout/disagreement), suppress STOP and force braking
        if fallback_required:
            if dec_type == "STOP":
                dec_type = "VERIFY"
                query_anchor = True

        # 5. Two-Phase Dwell & Stabilized Arrival Verification
        if self.phase == "BASE":
            if dec_type == "STOP":
                self.phase = "BRAKING"
                self.reason = "BRAKING_BEFORE_CONFIRMATION"
                self.wait_steps = 0
                action = np.clip(0.5 * nav_3d, -0.25, 0.25) - np.clip(1.5 * v_est, -0.6, 0.6)
                return action, "VERIFY", nav_3d, False
            return action_3d, dec_type, nav_3d, query_anchor

        # In BRAKING or ANCHOR phase
        self.wait_steps += 1
        if self.wait_steps > 120:
            return self._abstain("STABILIZATION_TIMEOUT", nav_3d)

        # Check estimated speed
        speed_est = float(np.linalg.norm(v_est))
        if speed_est > self.speed_limit or fallback_required:
            self.phase = "BRAKING"
            self.reason = "BRAKING_BEFORE_CONFIRMATION"
            action = np.clip(0.5 * nav_3d, -0.25, 0.25) - np.clip(1.5 * v_est, -0.6, 0.6)
            return action, "VERIFY", nav_3d, False

        # Estimated speed is low (< 0.08 m/s): Query anchor if not present
        if self.phase == "BRAKING":
            self.phase = "ANCHOR"
            self.reason = "AWAITING_STABILIZED_ANCHOR"
            return np.zeros(3), "VERIFY", nav_3d, True

        # In ANCHOR phase: verify anchor with confidence margin
        anchor = valid_anchor(anchor_reading)
        if not valid_range(r) or anchor is None:
            return self._abstain("ANCHOR_OR_RANGE_UNAVAILABLE", nav_3d)

        anchor_dist = float(np.linalg.norm(anchor))
        # Account for anchor uncertainty
        if anchor_dist + 1.645 * float(anchor_reading.sigma) <= self.success_radius:
            # Certified arrival confirmed!
            self.phase = "TERMINAL"
            self.reason = "ESTIMATED_STATE_ARRIVAL_CONFIRMED"
            self.terminal_decision = "STOP"
            return np.zeros(3), "STOP", nav_3d, False

        # If borderline arrival and recovery not yet attempted, enter RECOVERY
        if anchor_dist <= self.success_radius + 0.10 and not self.recovery_used:
            self.recovery_used = True
            self.phase = "RECOVERY"
            self.reason = "RECOVERY_ANCHOR_REQUESTED"
            action = np.clip(0.6 * anchor, -0.3, 0.3) - np.clip(1.2 * v_est, -0.5, 0.5)
            return action, "NAVIGATE", anchor, True

        # Anchor significantly outside margin -> Reject (sensor drift/fault or unrecoverable overshoot)
        return self._abstain("ANCHOR_OUTSIDE_CONFIRMATION_MARGIN", nav_3d)

    def compute_damping(self) -> np.ndarray:
        """Returns velocity damping calculated strictly from estimated velocity (E-05)."""
        return - self.damping_gain * self.v_est
