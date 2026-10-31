"""Simulation-only cross-check of two separately modeled velocity readings."""
import math
import numpy as np
from aegis.v9.sustained_stop_candidate import SustainedStopCandidate
from aegis.v9.velocity_freshness_candidate import VelocityFreshness


class DualVelocityCandidate(SustainedStopCandidate):
    """Require fresh, mutually consistent sources before using either speed.

    The threshold and source independence are assumptions, not guarantees.
    """

    def __init__(self, *, success_radius, disagreement_limit=0.1):
        if not math.isfinite(disagreement_limit) or disagreement_limit <= 0:
            raise ValueError("disagreement limit must be finite and positive")
        self.disagreement_limit = disagreement_limit
        self.velocity_gate = VelocityFreshness()
        self.secondary_gate = VelocityFreshness()
        super().__init__(success_radius=success_radius)

    def reset(self):
        super().reset()
        self.velocity_gate.reset()
        self.secondary_gate.reset()
        self.crosscheck_reason = "NO_COMPARISON"
        self.comparisons = 0
        self.disagreements = 0

    def update(self, a, b, r, anchor_reading=None, step=0, *, velocity_reading=None,
               secondary_velocity_reading=None, now_seconds=None):
        first = self.velocity_gate.accept(velocity_reading, now_seconds)
        second = self.secondary_gate.accept(secondary_velocity_reading, now_seconds)
        selected = None
        if first is None or second is None:
            self.crosscheck_reason = "SOURCE_UNAVAILABLE"
        else:
            self.comparisons += 1
            if np.linalg.norm(first - second) > self.disagreement_limit:
                self.disagreements += 1
                self.crosscheck_reason = "VELOCITY_DISAGREEMENT"
            else:
                self.crosscheck_reason = "VELOCITIES_CONSISTENT"
                selected = first if np.linalg.norm(first) >= np.linalg.norm(second) else second
        return super().update(a, b, r, anchor_reading=anchor_reading, step=step, velocity_reading=selected)
