"""Exploratory sustained low-speed gate; simulation-only, not safety rated."""
import numpy as np
from aegis.v9.anchor_recovery_candidate import AnchorRecoveryCandidate


class SustainedStopCandidate(AnchorRecoveryCandidate):
    """Require consecutive valid low-speed observations before requesting anchor.

    A sample count assumes the caller delivers distinct fresh readings at the
    simulated step rate. This is not a continuous-time stopping guarantee.
    """

    def __init__(self, *, success_radius, required_low_speed_samples=20):
        if not isinstance(required_low_speed_samples, int) or isinstance(required_low_speed_samples, bool) or required_low_speed_samples <= 0:
            raise ValueError("required_low_speed_samples must be a positive integer")
        self.required_low_speed_samples = required_low_speed_samples
        super().__init__(success_radius=success_radius)
        self.speed_limit = 0.05
        self.max_wait = 220

    def reset(self):
        super().reset()
        self.low_speed_samples = 0

    def update(self, a, b, r, anchor_reading=None, step=0, *, velocity_reading=None):
        if self.phase == "BRAKING":
            try:
                velocity = np.asarray(velocity_reading, dtype=float)
                low_speed = velocity.shape == (3,) and np.isfinite(velocity).all() and np.linalg.norm(velocity) <= self.speed_limit
            except (TypeError, ValueError):
                low_speed = False
            if low_speed:
                self.low_speed_samples += 1
                if self.low_speed_samples < self.required_low_speed_samples:
                    self.wait_steps += 1
                    if self.wait_steps > self.max_wait:
                        return self._abstain("STABILIZATION_TIMEOUT")
                    self.missing_velocity_count = 0
                    self.reason = "VERIFYING_SUSTAINED_SPEED"
                    return np.zeros(3), "VERIFY", self.base.last_nav_vector_3d, False
            else:
                self.low_speed_samples = 0
        previous_phase = self.phase
        result = super().update(a, b, r, anchor_reading=anchor_reading, step=step, velocity_reading=velocity_reading)
        if self.phase != "ANCHOR" or previous_phase == "ANCHOR":
            self.low_speed_samples = 0
        return result
