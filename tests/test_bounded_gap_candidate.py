import numpy as np
import pytest
from aegis.v9.bounded_gap_candidate import BoundedGapCandidate
from aegis.v9.velocity_freshness_candidate import TimedVelocity


def csetup():
    c = BoundedGapCandidate(success_radius=0.25)
    c.required_low_speed_samples = 3
    c.base.update = lambda *args, **kwargs: (np.zeros(3), "STOP", np.zeros(3), False)
    c.update(None, None, None, velocity_reading=TimedVelocity([0, 0, 0], 0, 0.), now_seconds=0.)
    return c


def call(c, step, value=0.0, reading=True):
    time = step * 0.02
    obs = TimedVelocity([value, 0, 0], step, time) if reading else None
    return c.update(None, None, None, velocity_reading=obs, step=step, now_seconds=time)


def test_missing_gap_is_bridged_without_counting_a_new_sample():
    c = csetup()
    call(c, 1)
    assert c.low_speed_samples == 1
    assert call(c, 2, reading=False)[1] == "VERIFY"
    assert c.gap_bridged and c.low_speed_samples == 1
    call(c, 3)
    assert c.low_speed_samples == 2
    assert call(c, 4)[3] is True


def test_too_long_or_unbounded_gap_resets_evidence():
    c = csetup()
    call(c, 1)
    call(c, 2, reading=False)
    call(c, 3, reading=False)
    assert c.low_speed_samples == 1
    call(c, 4, reading=False)
    assert not c.gap_bridged and c.low_speed_samples == 0
    c = csetup()
    call(c, 1, value=0.045)
    call(c, 2, reading=False)
    assert not c.gap_bridged and c.low_speed_samples == 0


def test_replay_is_not_treated_as_a_missing_gap():
    c = csetup()
    call(c, 1)
    result = c.update(None, None, None, velocity_reading=TimedVelocity([0, 0, 0], 1, 0.02), step=2, now_seconds=0.04)
    assert result[1] == "VERIFY" and not c.gap_bridged and c.low_speed_samples == 0


def test_invalid_parameters_rejected():
    for val in (-1., float('nan'), float('inf')):
        with pytest.raises(ValueError):
            BoundedGapCandidate(success_radius=0.25, acceleration_bound=val)
