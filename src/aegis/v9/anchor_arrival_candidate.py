"""Exploratory arrival guard for simulation; not a safety certificate."""
import numpy as np

from aegis.v9.controller_3d import Aegis3DAwareController
from aegis.v9.exploratory_sensor_validation import valid_range, valid_anchor


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
            is_valid_range = valid_range(r)
            anchor = valid_anchor(anchor_reading)
            if is_valid_range and anchor is not None and np.linalg.norm(anchor) + 1.645 * anchor_reading.sigma <= self.success_radius:
                self.reason = "EXPLORATORY_ANCHOR_CONFIRMED"
                self.terminal_decision = "STOP"
                return np.zeros(3), "STOP", self.base.last_nav_vector_3d, False
            self.reason = ("ANCHOR_OR_RANGE_UNAVAILABLE" if not is_valid_range or anchor is None
                           else "ANCHOR_OUTSIDE_CONFIRMATION_MARGIN")
            self.terminal_decision = "ABSTAIN"
            return np.zeros(3), "ABSTAIN", self.base.last_nav_vector_3d, False

        action, decision, nav, query = self.base.update(a, b, r, anchor_reading=anchor_reading, step=step)
        if decision == "STOP":
            self.pending = True
            return np.zeros(3), "VERIFY", nav, True
        return action, decision, nav, query
