"""Malformed observations must not create a STOP or crash the prototype."""
import numpy as np
import pytest
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.controller_3d import Aegis3DAwareController
from aegis.v9.anchor_arrival_candidate import AnchorArrivalCandidate
from aegis.v9.stabilized_arrival_candidate import StabilizedArrivalCandidate
from aegis.v9.anchor_recovery_candidate import AnchorRecoveryCandidate


def anchor(sigma=0.04, estimate=None, valid=True, queried=True):
    return AnchorReading(np.array([0.1, 0, 0]) if estimate is None else estimate, sigma, valid, queried, 0.05)


def ready(cls):
    c = cls(success_radius=0.25)
    c.base.update = lambda *args, **kwargs: (np.zeros(3), "STOP", np.zeros(3), False)
    c.update(None, None, None)
    if isinstance(c, StabilizedArrivalCandidate):
        c.update(None, None, None, velocity_reading=[0, 0, 0])
    return c


def confirm(c, r, a):
    if isinstance(c, StabilizedArrivalCandidate):
        return c.update(None, None, r, a, velocity_reading=[0, 0, 0])
    return c.update(None, None, r, a)


@pytest.mark.parametrize("cls", [AnchorArrivalCandidate, StabilizedArrivalCandidate])
@pytest.mark.parametrize("reading", [RangeReading('bad', .05), RangeReading(None, .05), RangeReading(.1, 'bad'),
    RangeReading(.1, None), RangeReading(float('nan'), .05), RangeReading(-1, .05), RangeReading(.1, 0),
    RangeReading(.1, .05, valid='false'), RangeReading(.1, .05, dropped='false')])
def test_malformed_range_at_confirmation_abstains(cls, reading):
    c = ready(cls)
    action, decision, _, query = confirm(c, reading, anchor())
    assert decision == "ABSTAIN" and not query and np.all(action == 0)


@pytest.mark.parametrize("cls", [AnchorArrivalCandidate, StabilizedArrivalCandidate])
@pytest.mark.parametrize("reading", [anchor(sigma='bad'), anchor(sigma=None), anchor(sigma=0),
    anchor(estimate=['bad', 0, 0]), anchor(estimate=[0, 0]), anchor(valid='false'), anchor(queried='false')])
def test_malformed_anchor_at_confirmation_abstains(cls, reading):
    c = ready(cls)
    assert confirm(c, RangeReading(.1, .05), reading)[1] == "ABSTAIN"


@pytest.mark.parametrize("bad", ['bad', None, float('nan'), float('inf'), -1])
def test_base_invalid_range_cannot_confirm_arrival(bad):
    c = Aegis3DAwareController()
    for step in range(5):
        assert c.update(np.array([.1, 0, 0]), np.array([.1, 0, 0]), RangeReading(bad, .05), step=step)[1] != "STOP"
    assert c.arrival_range_samples == []


@pytest.mark.parametrize("bad", [anchor(sigma='bad'), anchor(sigma=None), anchor(estimate=['bad', 0, 0]), anchor(queried='false')])
def test_base_invalid_anchor_does_not_update_calibration(bad):
    c = Aegis3DAwareController()
    c.update(np.array([1., 0, 0]), np.array([1., 0, 0]), RangeReading(1., .05), bad)
    assert c.cal_a.sample_count == c.cal_b.sample_count == 0


def test_base_invalid_vector_fails_closed():
    c = Aegis3DAwareController()
    bad = SensorReading(estimate=['bad', 0, 0], sigma=.05, valid=True, anomaly=False,
                        dropped=False, bias=np.zeros(3), drift=np.zeros(3))
    assert c.update(bad, np.ones(3), RangeReading(1., .05))[1] == "ABSTAIN"


@pytest.mark.parametrize("r,a", [(RangeReading('bad', .05), anchor()),
    (RangeReading(.1, .05), anchor(sigma='bad')), (RangeReading(.1, .05), anchor(estimate=['bad', 0, 0]))])
def test_recovery_malformed_evidence_abstains_without_motion(r, a):
    c = AnchorRecoveryCandidate(success_radius=.25)
    c.phase = "RECOVERY"
    action, decision, _, query = c.update(None, None, r, a, velocity_reading=[0, 0, 0])
    assert decision == "ABSTAIN" and not query and np.all(action == 0)
