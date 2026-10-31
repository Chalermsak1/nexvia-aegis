"""Exploratory anchor-guided recovery in simulation; not safety rated."""
import math
import numpy as np

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.stabilized_arrival_candidate import StabilizedArrivalCandidate


class AnchorRecoveryCandidate(StabilizedArrivalCandidate):
    """After one rejected anchor, attempt one bounded anchor-guided approach."""

    def __init__(self, *, success_radius, recovery_steps=100):
        if not isinstance(recovery_steps, int) or isinstance(recovery_steps, bool) or recovery_steps <= 0:
            raise ValueError("recovery_steps must be a positive integer")
        self.recovery_limit = recovery_steps
        super().__init__(success_radius=success_radius, max_missing_velocity=2)

    def reset(self):
        super().reset()
        self.recovery_used = False
        self.recovery_steps = 0

    def update(self, a, b, r, anchor_reading=None, step=0, *, velocity_reading=None):
        if self.phase == "RECOVERY":
            self.recovery_steps += 1
            if self.recovery_steps > self.recovery_limit:
                return self._abstain("RECOVERY_TIMEOUT")
            if not (isinstance(r, RangeReading) and r.valid and not r.dropped and not r.anomaly
                    and math.isfinite(r.distance) and r.distance >= 0 and math.isfinite(r.sigma) and r.sigma > 0):
                return self._abstain("RECOVERY_RANGE_UNAVAILABLE")
            if not (isinstance(anchor_reading, AnchorReading) and anchor_reading.valid and anchor_reading.queried
                    and math.isfinite(anchor_reading.sigma) and anchor_reading.sigma > 0):
                return self._abstain("RECOVERY_ANCHOR_UNAVAILABLE")
            try:
                anchor = np.asarray(anchor_reading.estimate, dtype=float)
                velocity = np.asarray(velocity_reading, dtype=float)
                vectors = [np.asarray(x.estimate, dtype=float) for x in (a, b) if isinstance(x, SensorReading) and x.valid and not x.dropped and not x.anomaly]
                if (anchor.shape != (3,) or velocity.shape != (3,) or len(vectors) != 2
                        or any(v.shape != (3,) or not np.isfinite(v).all() for v in vectors)
                        or not np.isfinite(anchor).all() or not np.isfinite(velocity).all()):
                    return self._abstain("RECOVERY_SENSOR_INVALID")
            except (TypeError, ValueError):
                return self._abstain("RECOVERY_SENSOR_INVALID")
            if abs(float(np.linalg.norm(anchor)) - r.distance) > self.base.tau_range_3d:
                return self._abstain("RECOVERY_ANCHOR_RANGE_CONFLICT")
            if float(np.linalg.norm(anchor)) + 1.645 * anchor_reading.sigma <= self.success_radius:
                self.phase = "BRAKING"
                self.reason = "BRAKING_AFTER_RECOVERY"
                self.wait_steps = 0
                return np.zeros(3), "VERIFY", self.base.last_nav_vector_3d, False
            # Bounded, low-force guidance from the current anchor, not truth.
            action = np.clip(0.5 * anchor, -0.3, 0.3)
            self.reason = "ANCHOR_GUIDED_RECOVERY"
            return action, "NAVIGATE", anchor, True

        result = super().update(a, b, r, anchor_reading=anchor_reading, step=step, velocity_reading=velocity_reading)
        if result[1] == "ABSTAIN" and self.reason == "ANCHOR_OUTSIDE_CONFIRMATION_MARGIN" and not self.recovery_used:
            self.recovery_used = True
            self.terminal_decision = None
            self.phase = "RECOVERY"
            self.reason = "RECOVERY_ANCHOR_REQUESTED"
            return np.zeros(3), "VERIFY", self.base.last_nav_vector_3d, True
        return result
