"""Exploratory timestamp and sequence gate; not a trusted sensor interface."""
from dataclasses import dataclass
import math
import numpy as np

from aegis.v9.sustained_stop_candidate import SustainedStopCandidate


@dataclass(frozen=True)
class TimedVelocity:
    vector: object
    sequence: int
    acquired_seconds: float


class VelocityFreshness:
    """Single-source monotonic gate using a caller-supplied common clock."""

    def __init__(self, max_age_seconds=0.01):
        if not math.isfinite(max_age_seconds) or max_age_seconds < 0:
            raise ValueError("invalid maximum age")
        self.max_age_seconds = max_age_seconds
        self.reset()

    def reset(self):
        self.last_sequence = None
        self.last_acquired = None
        self.last_now = None
        self.reason = "NO_SAMPLE"
        self.rejections = 0

    def accept(self, reading, now):
        def reject(reason):
            self.reason = reason
            self.rejections += 1
            return None
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
            return reject("INVALID_CLOCK")
        if self.last_now is not None and now <= self.last_now:
            return reject("NON_MONOTONIC_CLOCK")
        self.last_now = now
        if not isinstance(reading, TimedVelocity):
            return reject("MISSING_VELOCITY")
        if type(reading.sequence) is not int or reading.sequence < 0:
            return reject("INVALID_SEQUENCE")
        t = reading.acquired_seconds
        if not isinstance(t, (int, float)) or isinstance(t, bool) or not math.isfinite(t):
            return reject("INVALID_TIMESTAMP")
        if t > now or now - t > self.max_age_seconds:
            return reject("FUTURE_OR_STALE")
        if (self.last_sequence is not None and reading.sequence <= self.last_sequence) or (
            self.last_acquired is not None and t <= self.last_acquired
        ):
            return reject("REPLAY_OR_REORDER")
        try:
            vector = np.asarray(reading.vector, dtype=float)
            if vector.shape != (3,) or not np.isfinite(vector).all():
                return reject("INVALID_VECTOR")
        except (TypeError, ValueError):
            return reject("INVALID_VECTOR")
        self.last_sequence = reading.sequence
        self.last_acquired = t
        self.reason = "ACCEPTED"
        return vector.copy()


class FreshVelocityStopCandidate(SustainedStopCandidate):
    """Sustained-stop simulation arm with a freshness gate for velocity only."""

    def __init__(self, *, success_radius, max_velocity_age_seconds=0.01):
        self.velocity_gate = VelocityFreshness(max_velocity_age_seconds)
        super().__init__(success_radius=success_radius)

    def reset(self):
        super().reset()
        self.velocity_gate.reset()

    def update(self, a, b, r, anchor_reading=None, step=0, *, velocity_reading=None, now_seconds=None):
        fresh = self.velocity_gate.accept(velocity_reading, now_seconds)
        return super().update(a, b, r, anchor_reading=anchor_reading, step=step, velocity_reading=fresh)
