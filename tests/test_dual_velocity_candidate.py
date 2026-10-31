import numpy as np
import pytest
from aegis.v9.dual_velocity_candidate import DualVelocityCandidate
from aegis.v9.velocity_freshness_candidate import TimedVelocity


def setup():
    c = DualVelocityCandidate(success_radius=0.25)
    c.base.update = lambda *args, **kwargs: (np.zeros(3), "STOP", np.zeros(3), False)
    c.update(None, None, None, velocity_reading=TimedVelocity([0, 0, 0], 0, 0),
             secondary_velocity_reading=TimedVelocity([0, 0, 0], 0, 0), now_seconds=0)
    return c


def reading(seq, value):
    return TimedVelocity([value, 0, 0], seq, seq * 0.02)


def test_disagreement_resets_and_missing_source_does_not_count():
    c = setup()
    c.update(None, None, None, velocity_reading=reading(1, 0), secondary_velocity_reading=reading(1, 0), now_seconds=.02)
    assert c.low_speed_samples == 1
    c.update(None, None, None, velocity_reading=reading(2, 0), secondary_velocity_reading=reading(2, .2), now_seconds=.04)
    assert c.low_speed_samples == 0 and c.crosscheck_reason == "VELOCITY_DISAGREEMENT"
    c.update(None, None, None, velocity_reading=reading(3, 0), secondary_velocity_reading=None, now_seconds=.06)
    assert c.low_speed_samples == 0 and c.crosscheck_reason == "SOURCE_UNAVAILABLE"


def test_common_low_error_cannot_be_detected_from_agreement_alone():
    c = setup()
    c.update(None, None, None, velocity_reading=reading(1, 0), secondary_velocity_reading=reading(1, 0), now_seconds=.02)
    assert c.crosscheck_reason == "VELOCITIES_CONSISTENT" and c.low_speed_samples == 1


def test_larger_consistent_speed_is_used_for_low_speed_gate():
    c = setup()
    c.update(None, None, None, velocity_reading=reading(1, .01), secondary_velocity_reading=reading(1, .06), now_seconds=.02)
    assert c.crosscheck_reason == "VELOCITIES_CONSISTENT" and c.low_speed_samples == 0


def test_secondary_replay_is_not_accepted():
    c = setup()
    c.update(None, None, None, velocity_reading=reading(1, 0), secondary_velocity_reading=reading(0, 0), now_seconds=.02)
    assert c.crosscheck_reason == "SOURCE_UNAVAILABLE" and c.low_speed_samples == 0


@pytest.mark.parametrize("limit", [0, -1, float('nan')])
def test_bad_disagreement_limit_rejected(limit):
    with pytest.raises(ValueError): DualVelocityCandidate(success_radius=0.25, disagreement_limit=limit)
