"""Fail-closed input checks for exploratory 3D controller wrappers."""
import math
from numbers import Real
import numpy as np

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v7.anchor_sensor import AnchorReading


def finite_real(value, *, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        return False
    return math.isfinite(value) and (value > 0 if positive else value >= 0)


def boolean_flag(value):
    return isinstance(value, (bool, np.bool_))


def valid_range(reading):
    return bool(isinstance(reading, RangeReading)
                and all(boolean_flag(v) for v in (reading.valid, reading.dropped, reading.anomaly))
                and reading.valid and not reading.dropped
                and not reading.anomaly and finite_real(reading.distance)
                and finite_real(reading.sigma, positive=True))


def valid_anchor(reading):
    if not (isinstance(reading, AnchorReading) and boolean_flag(reading.valid) and boolean_flag(reading.queried)
            and reading.valid and reading.queried
            and finite_real(reading.sigma, positive=True)):
        return None
    try:
        vector = np.asarray(reading.estimate, dtype=float)
    except (TypeError, ValueError, OverflowError):
        return None
    if vector.shape != (3,) or not np.isfinite(vector).all():
        return None
    return vector
