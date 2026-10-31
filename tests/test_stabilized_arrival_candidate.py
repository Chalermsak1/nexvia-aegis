import numpy as np
import pytest
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.stabilized_arrival_candidate import StabilizedArrivalCandidate


def setup_candidate(max_wait=120, max_missing_velocity=0):
    c = StabilizedArrivalCandidate(success_radius=0.25, max_wait=max_wait, max_missing_velocity=max_missing_velocity)
    c.base.update = lambda *args, **kwargs: (np.zeros(3), "STOP", np.zeros(3), False)
    result = c.update(None, None, None)
    assert result[1] == "VERIFY" and not result[3]
    return c


def sample_anchor(vec=(0.1, 0, 0), valid=True):
    return AnchorReading(np.asarray(vec), 0.04, valid, True, 0.05)


def test_brakes_then_requires_fresh_anchor_before_stop():
    c = setup_candidate()
    result = c.update(None, None, None, velocity_reading=[0.2, 0, 0])
    assert result[1] == "VERIFY" and not result[3]
    assert c.update(None, None, None, velocity_reading=[0, 0, 0])[3] is True
    assert c.update(None, None, RangeReading(0.1, 0.05), sample_anchor(), velocity_reading=[0, 0, 0])[1] == "STOP"
    assert c.update(None, None, None)[1] == "STOP"


@pytest.mark.parametrize("velocity", [None, [float('nan'), 0, 0], [0, 0], ['invalid', 0, 0]])
def test_missing_or_invalid_velocity_abstains(velocity):
    c = setup_candidate()
    assert c.update(None, None, None, velocity_reading=velocity)[1] == "ABSTAIN"
    assert c.terminal_reason == "INVALID_VELOCITY"


def test_timeout_and_reset():
    c = setup_candidate(max_wait=1)
    c.update(None, None, None, velocity_reading=[0.2, 0, 0])
    assert c.update(None, None, None, velocity_reading=[0.2, 0, 0])[1] == "ABSTAIN"
    assert c.terminal_reason == "STABILIZATION_TIMEOUT"
    c.reset()
    assert c.phase == "BASE" and c.terminal_decision is None


@pytest.mark.parametrize("reading", [None, sample_anchor(valid=False), sample_anchor(vec=(0.3, 0, 0))])
def test_missing_invalid_or_distant_anchor_abstains(reading):
    c = setup_candidate()
    c.update(None, None, None, velocity_reading=[0, 0, 0])
    assert c.update(None, None, RangeReading(0.1, 0.05), reading, velocity_reading=[0, 0, 0])[1] == "ABSTAIN"


def test_speed_rises_while_waiting_for_anchor_discards_it():
    c = setup_candidate()
    c.update(None, None, None, velocity_reading=[0, 0, 0])
    assert c.update(None, None, RangeReading(0.1, 0.05), sample_anchor(), velocity_reading=[0.2, 0, 0])[1:4:2] == ("VERIFY", False)
    assert c.update(None, None, None, velocity_reading=[0, 0, 0])[3]
    assert c.update(None, None, RangeReading(0.1, 0.05), None, velocity_reading=[0, 0, 0])[1] == "ABSTAIN"


def test_invalid_range_after_anchor_query_abstains():
    c = setup_candidate()
    c.update(None, None, None, velocity_reading=[0, 0, 0])
    assert c.update(None, None, RangeReading(0.1, 0.05, valid=False), sample_anchor(), velocity_reading=[0, 0, 0])[1] == "ABSTAIN"


def test_speed_limit_boundary_and_just_above():
    c = setup_candidate()
    assert c.update(None, None, None, velocity_reading=[0.080001, 0, 0])[3] is False
    assert c.update(None, None, None, velocity_reading=[0.08, 0, 0])[3] is True


def test_bounded_dropout_brakes_and_requires_new_anchor():
    c = setup_candidate(max_missing_velocity=2)
    assert c.update(None, None, None, velocity_reading=[0, 0, 0])[3]
    result = c.update(None, None, RangeReading(0.1, 0.05), sample_anchor(), velocity_reading=None)
    assert result[1] == "VERIFY" and not result[3] and c.phase == "BRAKING"
    assert c.update(None, None, None, velocity_reading=[0, 0, 0])[3]
    assert c.update(None, None, RangeReading(0.1, 0.05), None, velocity_reading=[0, 0, 0])[1] == "ABSTAIN"


def test_prolonged_dropout_abstains_and_valid_reading_resets_count():
    c = setup_candidate(max_missing_velocity=2)
    for _ in range(2):
        assert c.update(None, None, None, velocity_reading=None)[1] == "VERIFY"
    c.update(None, None, None, velocity_reading=[0.2, 0, 0])
    for _ in range(2):
        assert c.update(None, None, None, velocity_reading=None)[1] == "VERIFY"
    assert c.update(None, None, None, velocity_reading=None)[1] == "ABSTAIN"
