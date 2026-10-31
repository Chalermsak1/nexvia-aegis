"""Synthetic checks for the separate post-proposal monitoring candidate."""
import numpy as np
import pytest

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.recovery_monitor_candidate import RecoveryMonitorCandidate


def vec(value=(0.1, 0, 0), *, valid=True, dropped=False, anomaly=False, sigma=0.05):
    return SensorReading(estimate=np.asarray(value), sigma=sigma, valid=valid,
                         anomaly=anomaly, dropped=dropped, bias=np.zeros(3), drift=np.zeros(3))


def anchor(distance):
    return AnchorReading(np.array([distance, 0, 0]), 0.04, True, True, 0.05)


def setup():
    candidate = RecoveryMonitorCandidate(success_radius=0.25)
    candidate.base.update = lambda *args, **kwargs: (np.zeros(3), "STOP", np.zeros(3), False)
    result = candidate.update(vec(), vec(), RangeReading(0.1, 0.05), step=0)
    assert result[1] == "VERIFY" and candidate.phase == "BRAKING"
    return candidate


@pytest.mark.parametrize("phase", ["BRAKING", "ANCHOR", "RECOVERY"])
@pytest.mark.parametrize("a,b", [(None, None), (None, vec()), (vec(), None),
                                    (vec(dropped=True), vec()), (vec(anomaly=True), vec()),
                                    (vec(value=(float('nan'), 0, 0)), vec()),
                                    (vec(valid='false'), vec())])
def test_missing_or_invalid_vectors_abstain_in_each_monitored_phase(phase, a, b):
    c = setup()
    c.phase = phase
    action, decision, _, query = c.update(a, b, RangeReading(0.1, 0.05), anchor(0.1), step=1, velocity_reading=[0, 0, 0])
    assert decision == "ABSTAIN" and not query and np.all(action == 0)
    assert c.terminal_reason == "POSTPROPOSAL_VECTOR_UNAVAILABLE"
    assert c.update(vec(), vec(), RangeReading(0.1, 0.05), anchor(0.1), step=2, velocity_reading=[0, 0, 0])[1] == "ABSTAIN"


@pytest.mark.parametrize("phase", ["BRAKING", "ANCHOR", "RECOVERY"])
@pytest.mark.parametrize("reading", [None, RangeReading(0.1, 0.05, valid=False),
                                      RangeReading(0.1, 0.05, anomaly=True), RangeReading('bad', 0.05)])
def test_invalid_range_abstains_in_each_monitored_phase(phase, reading):
    c = setup()
    c.phase = phase
    assert c.update(vec(), vec(), reading, anchor(0.1), step=1, velocity_reading=[0, 0, 0])[1] == "ABSTAIN"
    assert c.terminal_reason == "POSTPROPOSAL_RANGE_UNAVAILABLE"


def test_monitor_updates_through_braking_and_anchor_confirmation():
    c = setup()
    assert c.update(vec(), vec(), RangeReading(0.1, 0.05), step=1, velocity_reading=[0.2, 0, 0])[1] == "VERIFY"
    assert c.postproposal_monitor_steps == 1
    assert c.update(vec(), vec(), RangeReading(0.1, 0.05), step=2, velocity_reading=[0, 0, 0])[3]
    assert c.phase == "ANCHOR" and c.postproposal_monitor_steps == 2
    assert c.update(vec(), vec(), RangeReading(0.1, 0.05), anchor(0.1), step=3, velocity_reading=[0, 0, 0])[1] == "STOP"
    assert c.postproposal_monitor_steps == 3


def test_monitor_updates_during_recovery_without_reinvoking_base_controller():
    c = setup()
    c.phase = "RECOVERY"
    result = c.update(vec((0.3, 0, 0)), vec((0.3, 0, 0)), RangeReading(0.3, 0.05),
                      anchor(0.3), step=1, velocity_reading=[0, 0, 0])
    assert result[1] == "NAVIGATE" and result[3]
    assert c.postproposal_monitor_steps == 1


def test_later_anomaly_latches_and_prevents_further_commands():
    c = setup()
    c.update(vec(), vec(), RangeReading(0.1, 0.05), step=1, velocity_reading=[0.2, 0, 0])
    result = c.update(vec(anomaly=True), vec(), RangeReading(0.1, 0.05), step=2, velocity_reading=[0.2, 0, 0])
    assert result[1] == "ABSTAIN" and not result[3]
    assert c.postproposal_monitor_steps == 1
    assert c.update(vec(), vec(), RangeReading(0.1, 0.05), step=3, velocity_reading=[0, 0, 0])[1] == "ABSTAIN"


def test_observation_residual_alarm_blocks_candidate():
    c = setup()
    decisions = []
    for step in range(1, 121):
        result = c.update(vec((3, 0, 0)), vec((0.1, 0, 0)), RangeReading(0.1, 0.05),
                          step=step, velocity_reading=[0.2, 0, 0])
        decisions.append(result[1])
        if result[1] == "ABSTAIN":
            break
    assert decisions[-1] == "ABSTAIN"
    assert c.terminal_reason == "POSTPROPOSAL_MONITOR_ALARM"
    assert c.postproposal_monitor_alarm


def test_sigma_change_fails_closed_and_reset_clears_history():
    c = setup()
    c.update(vec(), vec(), RangeReading(0.1, 0.05), step=1, velocity_reading=[0.2, 0, 0])
    assert c.update(vec(sigma=0.06), vec(), RangeReading(0.1, 0.05), step=2, velocity_reading=[0.2, 0, 0])[1] == "ABSTAIN"
    assert c.terminal_reason == "POSTPROPOSAL_SIGMA_CHANGED"
    c.reset()
    assert c.postproposal_monitor is None and c.postproposal_monitor_steps == 0


def test_extreme_finite_sigma_cannot_crash_monitor_initialization():
    c = setup()
    result = c.update(vec(sigma=1e308), vec(sigma=1e308), RangeReading(0.1, 0.05),
                      step=1, velocity_reading=[0, 0, 0])
    assert result[1] == "ABSTAIN" and not result[3]
    assert c.terminal_reason == "POSTPROPOSAL_MONITOR_INVALID"
