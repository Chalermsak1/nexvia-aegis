"""Exploratory arrival guard for simulation; not a safety certificate."""
import math
import numpy as np

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.controller_3d import Aegis3DAwareController


class AnchorArrivalCandidate:
    """Require an independently sampled anchor after a strict STOP proposal.

    The norm margin is a development heuristic, not a calibrated 3D bound.
    The simulated harness is responsible for requesting a fresh anchor.
    """

    def __init__(self, *, success_radius):
        self.base = Aegis3DAwareController(success_radius=success_radius, arrival_margin_m=0.0)
        self.success_radius = success_radius
        self.pending = False
        self.reason = "ACTIVE"
        self.terminal_decision = None

    def __getattr__(self, key):
        return getattr(self.base, key)

    @property
    def terminal_reason(self):
        if self.pending:
            return "AWAITING_ANCHOR_CONFIRMATION"
        return self.reason if self.reason != "ACTIVE" else self.base.terminal_reason

    def reset(self):
        self.base.reset()
        self.pending = False
        self.reason = "ACTIVE"
        self.terminal_decision = None

    def update(self, a, b, r, anchor_reading=None, step=0):
        if self.terminal_decision is not None:
            return np.zeros(3), self.terminal_decision, self.base.last_nav_vector_3d, False
        if self.pending:
            self.pending = False
            valid_range = (isinstance(r, RangeReading) and r.valid and not r.dropped and not r.anomaly
                           and math.isfinite(r.distance) and r.distance >= 0
                           and math.isfinite(r.sigma) and r.sigma > 0)
            valid_anchor = (isinstance(anchor_reading, AnchorReading) and anchor_reading.valid
                            and anchor_reading.queried and math.isfinite(anchor_reading.sigma)
                            and anchor_reading.sigma > 0)
            if valid_anchor:
                anchor = np.asarray(anchor_reading.estimate, dtype=float)
                valid_anchor = anchor.shape == (3,) and bool(np.isfinite(anchor).all())
            if valid_range and valid_anchor and np.linalg.norm(anchor) + 1.645 * anchor_reading.sigma <= self.success_radius:
                self.reason = "EXPLORATORY_ANCHOR_CONFIRMED"
                self.terminal_decision = "STOP"
                return np.zeros(3), "STOP", self.base.last_nav_vector_3d, False
            self.reason = ("ANCHOR_OR_RANGE_UNAVAILABLE" if not valid_range or not valid_anchor
                           else "ANCHOR_OUTSIDE_CONFIRMATION_MARGIN")
            self.terminal_decision = "ABSTAIN"
            return np.zeros(3), "ABSTAIN", self.base.last_nav_vector_3d, False

        action, decision, nav, query = self.base.update(a, b, r, anchor_reading=anchor_reading, step=step)
        if decision == "STOP":
            self.pending = True
            return np.zeros(3), "VERIFY", nav, True
        return action, decision, nav, query
