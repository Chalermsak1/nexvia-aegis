import numpy as np
import pytest
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.sustained_stop_candidate import SustainedStopCandidate


def setup(samples=3):
    c = SustainedStopCandidate(success_radius=0.25, required_low_speed_samples=samples)
    c.base.update = lambda *args, **kwargs: (np.zeros(3), "STOP", np.zeros(3), False)
    assert c.update(None, None, None)[1] == "VERIFY"
    return c


def update(c, velocity, anchor=None):
    return c.update(None, None, RangeReading(0.1, 0.05), anchor, velocity_reading=velocity)


def test_requires_consecutive_readings_then_fresh_anchor():
    c = setup()
    for _ in range(2):
        result = update(c, [0.01, 0, 0])
        assert result[1] == "VERIFY" and not result[3]
    assert update(c, [0.01, 0, 0])[3]
    anc = AnchorReading(np.array([0.1, 0, 0]), 0.04, True, True, 0.05)
    assert update(c, [0.01, 0, 0], anc)[1] == "STOP"


@pytest.mark.parametrize("interruption", [[0.06, 0, 0], None])
def test_speed_or_missing_reading_restarts_dwell(interruption):
    c = setup()
    update(c, [0.01, 0, 0])
    update(c, [0.01, 0, 0])
    assert update(c, interruption)[1] == "VERIFY"
    for _ in range(2):
        assert not update(c, [0.01, 0, 0])[3]
    assert update(c, [0.01, 0, 0])[3]


def test_high_speed_on_anchor_step_discards_anchor_and_restarts():
    c = setup(samples=1)
    assert update(c, [0, 0, 0])[3]
    anc = AnchorReading(np.array([0.1, 0, 0]), 0.04, True, True, 0.05)
    assert update(c, [0.1, 0, 0], anc)[1] == "VERIFY"
    assert c.phase == "BRAKING"
    assert update(c, [0, 0, 0])[3]
    assert update(c, [0, 0, 0], None)[1] == "ABSTAIN"


def test_wait_budget_applies_during_dwell():
    c = setup(samples=3)
    c.max_wait = 1
    assert update(c, [0, 0, 0])[1] == "VERIFY"
    assert update(c, [0, 0, 0])[1] == "ABSTAIN"
    assert c.terminal_reason == "STABILIZATION_TIMEOUT"


@pytest.mark.parametrize("samples", [0, -1, 1.5, True])
def test_invalid_sample_count_rejected(samples):
    with pytest.raises(ValueError):
        SustainedStopCandidate(success_radius=0.25, required_low_speed_samples=samples)
