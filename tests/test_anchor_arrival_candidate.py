"""Synthetic state-machine tests for the exploratory anchor guard."""
import numpy as np
import pytest
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.anchor_arrival_candidate import AnchorArrivalCandidate


def anchor(vector=(0.1, 0, 0), sigma=0.04, valid=True, queried=True):
    return AnchorReading(np.asarray(vector), sigma, valid, queried, 0.05)


def pending_candidate():
    c = AnchorArrivalCandidate(success_radius=0.25)
    c.base.update = lambda *args, **kwargs: (np.zeros(3), "STOP", np.zeros(3), False)
    action, decision, _, query = c.update(None, None, RangeReading(0.1, 0.05))
    assert decision == "VERIFY" and query and np.all(action == 0)
    return c


def test_fresh_anchor_confirms_and_terminal_is_latched():
    c = pending_candidate()
    assert c.update(None, None, RangeReading(0.1, 0.05), anchor())[1] == "STOP"
    assert c.update(None, None, None)[1] == "STOP"


@pytest.mark.parametrize("reading", [None, anchor(valid=False), anchor(queried=False),
                                   anchor(vector=(0.3, 0, 0)), anchor(vector=(float('nan'), 0, 0)),
                                   anchor(vector=(0.1, 0)), anchor(sigma=0)])
def test_missing_invalid_or_distant_anchor_abstains(reading):
    c = pending_candidate()
    assert c.update(None, None, RangeReading(0.1, 0.05), reading)[1] == "ABSTAIN"
    assert c.update(None, None, RangeReading(0.1, 0.05), anchor())[1] == "ABSTAIN"


@pytest.mark.parametrize("reading", [None, RangeReading(0.1, 0.05, valid=False),
                                   RangeReading(0.1, 0.05, anomaly=True)])
def test_missing_invalid_or_anomalous_range_abstains(reading):
    c = pending_candidate()
    assert c.update(None, None, reading, anchor())[1] == "ABSTAIN"


def test_reset_clears_pending_and_terminal():
    c = pending_candidate()
    c.update(None, None, None, None)
    c.reset()
    assert not c.pending and c.terminal_decision is None and c.reason == "ACTIVE"
