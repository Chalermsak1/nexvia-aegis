"""Exploratory velocity-gated arrival; no safety or statistical guarantee."""
import math
import numpy as np

from aegis.v9.controller_3d import Aegis3DAwareController
from aegis.v9.exploratory_sensor_validation import valid_range, valid_anchor


class StabilizedArrivalCandidate:
    """Brake until measured speed is low, then request one fresh anchor.

    Limits are development parameters, not approved stopping criteria. The
    caller must ensure freshness of observations and apply the VERIFY brake.
    """

    def __init__(self, *, success_radius, speed_limit=0.08, max_wait=120, max_missing_velocity=0):
        if not math.isfinite(success_radius) or success_radius <= 0:
            raise ValueError("success radius must be finite and positive")
        if not math.isfinite(speed_limit) or speed_limit <= 0 or not isinstance(max_wait, int) or isinstance(max_wait, bool) or max_wait <= 0:
            raise ValueError("invalid exploratory speed limit or wait")
        if not isinstance(max_missing_velocity, int) or isinstance(max_missing_velocity, bool) or max_missing_velocity < 0:
            raise ValueError("max_missing_velocity must be a nonnegative integer")
        self.base = Aegis3DAwareController(success_radius=success_radius, arrival_margin_m=0.0)
        self.success_radius = success_radius
        self.speed_limit = speed_limit
        self.max_wait = max_wait
        self.max_missing_velocity = max_missing_velocity
        self.reset()

    def __getattr__(self, name):
        return getattr(self.base, name)

    @property
    def terminal_reason(self):
        return self.reason if self.reason != "ACTIVE" else self.base.terminal_reason

    def reset(self):
        self.base.reset()
        self.phase = "BASE"
        self.reason = "ACTIVE"
        self.terminal_decision = None
        self.wait_steps = 0
        self.missing_velocity_count = 0

    def _abstain(self, reason):
        self.phase = "TERMINAL"
        self.reason = reason
        self.terminal_decision = "ABSTAIN"
        return np.zeros(3), "ABSTAIN", self.base.last_nav_vector_3d, False

    def update(self, a, b, r, anchor_reading=None, step=0, *, velocity_reading=None):
        if self.terminal_decision is not None:
            return np.zeros(3), self.terminal_decision, self.base.last_nav_vector_3d, False
        if self.phase == "BASE":
            action, decision, nav, query = self.base.update(a, b, r, anchor_reading=anchor_reading, step=step)
            if decision != "STOP":
                return action, decision, nav, query
            self.phase = "BRAKING"
            self.reason = "BRAKING_BEFORE_CONFIRMATION"
            return np.zeros(3), "VERIFY", nav, False

        self.wait_steps += 1
        if self.wait_steps > self.max_wait:
            return self._abstain("STABILIZATION_TIMEOUT")
        if velocity_reading is None:
            self.missing_velocity_count += 1
            if self.missing_velocity_count > self.max_missing_velocity:
                return self._abstain("INVALID_VELOCITY")
            # Discard any concurrently delivered anchor; a new one must be
            # requested after a fresh low-speed reading.
            self.phase = "BRAKING"
            self.reason = "WAITING_FOR_VELOCITY"
            return np.zeros(3), "VERIFY", self.base.last_nav_vector_3d, False
        try:
            velocity = np.asarray(velocity_reading, dtype=float)
        except (TypeError, ValueError):
            return self._abstain("INVALID_VELOCITY")
        if velocity.shape != (3,) or not np.isfinite(velocity).all():
            return self._abstain("INVALID_VELOCITY")
        self.missing_velocity_count = 0
        if np.linalg.norm(velocity) > self.speed_limit:
            self.phase = "BRAKING"
            self.reason = "BRAKING_BEFORE_CONFIRMATION"
            return np.zeros(3), "VERIFY", self.base.last_nav_vector_3d, False
        if self.phase == "BRAKING":
            self.phase = "ANCHOR"
            self.reason = "AWAITING_STABILIZED_ANCHOR"
            return np.zeros(3), "VERIFY", self.base.last_nav_vector_3d, True

        anchor = valid_anchor(anchor_reading)
        if not valid_range(r) or anchor is None:
            return self._abstain("ANCHOR_OR_RANGE_UNAVAILABLE")
        if np.linalg.norm(anchor) + 1.645 * anchor_reading.sigma > self.success_radius:
            return self._abstain("ANCHOR_OUTSIDE_CONFIRMATION_MARGIN")
        self.phase = "TERMINAL"
        self.reason = "EXPLORATORY_STABILIZED_ANCHOR_CONFIRMED"
        self.terminal_decision = "STOP"
        return np.zeros(3), "STOP", self.base.last_nav_vector_3d, False
