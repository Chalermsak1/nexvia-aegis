"""Exploratory post-proposal monitoring wrapper; not a safety-rated component.

This is a separate development candidate and does not change any registered
evaluation protocol or a controller's prior simulation records.
"""
from __future__ import annotations

import numpy as np

from aegis.v3.sensors.sensors import SensorReading
from aegis.v9.anchor_recovery_candidate import AnchorRecoveryCandidate
from aegis.v9.controller_3d import Aegis3DAwareController
from aegis.v9.exploratory_sensor_validation import boolean_flag, finite_real, valid_range


class RecoveryMonitorCandidate(AnchorRecoveryCandidate):
    """Observe both vector sensors and range during braking and recovery.

    The independent development monitor starts at the first update *after*
    the underlying controller proposes STOP. It does not inherit the base
    monitor's wealth/history, so it must not be interpreted as continuity of
    that monitor or as an independently validated anytime error guarantee.
    Sensor readings must be supplied by the caller; no timestamp or physical
    source authenticity is established by this wrapper.
    """

    _MONITORED_PHASES = frozenset({"BRAKING", "ANCHOR", "RECOVERY"})

    def __init__(self, *, success_radius: float, recovery_steps: int = 100):
        super().__init__(success_radius=success_radius, recovery_steps=recovery_steps)

    def reset(self):
        super().reset()
        self.postproposal_monitor = None
        self.postproposal_monitor_steps = 0
        self.postproposal_monitor_alarm = False
        self.postproposal_monitor_reason = "NOT_STARTED"
        self._postproposal_sigmas = None

    @staticmethod
    def _vector(reading):
        if not isinstance(reading, SensorReading):
            return None
        if not all(boolean_flag(flag) for flag in (reading.valid, reading.dropped, reading.anomaly)):
            return None
        if not reading.valid or reading.dropped or reading.anomaly or not finite_real(reading.sigma, positive=True):
            return None
        try:
            vector = np.asarray(reading.estimate, dtype=np.float64)
        except (TypeError, ValueError, OverflowError):
            return None
        if vector.shape != (3,) or not np.isfinite(vector).all():
            return None
        return vector

    def _observe(self, a, b, r):
        va, vb = self._vector(a), self._vector(b)
        if va is None or vb is None:
            return "POSTPROPOSAL_VECTOR_UNAVAILABLE"
        if not valid_range(r):
            return "POSTPROPOSAL_RANGE_UNAVAILABLE"

        sigmas = (float(a.sigma), float(b.sigma), float(r.sigma))
        if self.postproposal_monitor is None:
            monitor_factory = Aegis3DAwareController(success_radius=self.success_radius)
            try:
                monitor_factory._ensure_monitors(*sigmas)
            except (OverflowError, ValueError, FloatingPointError):
                return "POSTPROPOSAL_MONITOR_INVALID"
            self.postproposal_monitor = monitor_factory.ville_monitor
            self._postproposal_sigmas = sigmas
        elif sigmas != self._postproposal_sigmas:
            # Its null assumptions were set from the first reported sigmas;
            # don't silently continue with a different declared noise model.
            return "POSTPROPOSAL_SIGMA_CHANGED"

        residuals = {
            "diff_ab_3d": (float(np.linalg.norm(va - vb)), True),
            "range_vr_a_3d": (abs(float(np.linalg.norm(va)) - float(r.distance)), True),
            "range_vr_b_3d": (abs(float(np.linalg.norm(vb)) - float(r.distance)), True),
        }
        try:
            snapshot = self.postproposal_monitor.update(residuals)
        except (OverflowError, ValueError, FloatingPointError):
            return "POSTPROPOSAL_MONITOR_INVALID"
        self.postproposal_monitor_steps += 1
        self.postproposal_monitor_reason = "OBSERVED"
        if snapshot.is_alarm or snapshot.invalid_input_detected:
            self.postproposal_monitor_alarm = True
            return "POSTPROPOSAL_MONITOR_ALARM"
        return None

    def update(self, a, b, r, anchor_reading=None, step=0, *, velocity_reading=None):
        if self.terminal_decision is not None:
            return super().update(a, b, r, anchor_reading=anchor_reading, step=step,
                                  velocity_reading=velocity_reading)
        if self.phase in self._MONITORED_PHASES:
            reason = self._observe(a, b, r)
            if reason is not None:
                self.postproposal_monitor_reason = reason
                return self._abstain(reason)
        return super().update(a, b, r, anchor_reading=anchor_reading, step=step,
                              velocity_reading=velocity_reading)
