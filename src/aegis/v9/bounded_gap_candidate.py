"""Exploratory bounded-gap velocity evidence; no empirical safety guarantee."""
import math
import numpy as np
from aegis.v9.sustained_stop_candidate import SustainedStopCandidate
from aegis.v9.velocity_freshness_candidate import FreshVelocityStopCandidate


class BoundedGapCandidate(FreshVelocityStopCandidate):
    """Preserve a low-speed sequence across a short *missing* observation.

    Missing observations never add to the fresh-sample count. A gap is bridged
    only under explicit assumed bounds on velocity error and acceleration.
    Those assumptions require independent measurement and are not guarantees.
    """

    def __init__(self, *, success_radius, max_gap_seconds=0.04,
                 velocity_error_bound=0.01, acceleration_bound=0.1):
        if any(not math.isfinite(x) or x < 0 for x in (max_gap_seconds, velocity_error_bound, acceleration_bound)):
            raise ValueError("gap and assumed bounds must be finite and nonnegative")
        self.max_gap_seconds = max_gap_seconds
        self.velocity_error_bound = velocity_error_bound
        self.acceleration_bound = acceleration_bound
        super().__init__(success_radius=success_radius)

    def reset(self):
        super().reset()
        self.last_low_velocity = None
        self.last_low_time = None
        self.last_gap_bound = None
        self.gap_bridged = False
        self.bridged_steps = 0

    def update(self, a, b, r, anchor_reading=None, step=0, *, velocity_reading=None, now_seconds=None):
        fresh = self.velocity_gate.accept(velocity_reading, now_seconds)
        self.gap_bridged = False
        self.last_gap_bound = None
        if self.phase == "BRAKING" and fresh is None and self.velocity_gate.reason == "MISSING_VELOCITY":
            if self.last_low_velocity is not None and self.low_speed_samples > 0:
                age = now_seconds - self.last_low_time
                bound = float(np.linalg.norm(self.last_low_velocity)) + self.velocity_error_bound + self.acceleration_bound * age
                self.last_gap_bound = bound
                if 0 <= age <= self.max_gap_seconds + 1e-12 and bound <= self.speed_limit:
                    self.wait_steps += 1
                    if self.wait_steps > self.max_wait:
                        return self._abstain("STABILIZATION_TIMEOUT")
                    self.gap_bridged = True
                    self.bridged_steps += 1
                    self.reason = "BRIDGING_MISSING_VELOCITY"
                    return np.zeros(3), "VERIFY", self.base.last_nav_vector_3d, False
        if self.phase == "BRAKING" and fresh is not None and np.linalg.norm(fresh) <= self.speed_limit:
            self.last_low_velocity = fresh.copy()
            self.last_low_time = self.velocity_gate.last_acquired
        else:
            self.last_low_velocity = None
            self.last_low_time = None
        # Call the sustained implementation directly so the gate is checked
        # exactly once; only genuinely fresh observations can advance a count.
        result = SustainedStopCandidate.update(self, a, b, r, anchor_reading=anchor_reading,
                                              step=step, velocity_reading=fresh)
        if self.phase != "BRAKING":
            self.last_low_velocity = None
            self.last_low_time = None
        return result
