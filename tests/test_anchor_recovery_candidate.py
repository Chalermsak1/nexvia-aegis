import numpy as np
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.anchor_recovery_candidate import AnchorRecoveryCandidate


def vector():
    return SensorReading(estimate=np.array([0.2, 0, 0]), sigma=0.05, valid=True,
                         anomaly=False, dropped=False, bias=np.zeros(3), drift=np.zeros(3))


def anchor(distance, valid=True):
    return AnchorReading(np.array([distance, 0, 0]), 0.04, valid, True, 0.05)


def recovery(limit=100):
    c = AnchorRecoveryCandidate(success_radius=0.25, recovery_steps=limit)
    c.base.update = lambda *args, **kwargs: (np.zeros(3), "STOP", np.zeros(3), False)
    c.update(None, None, None)
    c.update(None, None, None, velocity_reading=[0, 0, 0])
    result = c.update(None, None, RangeReading(0.3, 0.05), anchor(0.3), velocity_reading=[0, 0, 0])
    assert result[1] == "VERIFY" and result[3] and c.phase == "RECOVERY"
    return c


def test_recovery_guides_with_fresh_anchor_then_brakes_and_reconfirms():
    c = recovery()
    action, decision, _, query = c.update(vector(), vector(), RangeReading(0.3, 0.05), anchor(0.3), velocity_reading=[0, 0, 0])
    assert decision == "NAVIGATE" and query and 0 < action[0] <= 0.3
    assert c.update(vector(), vector(), RangeReading(0.1, 0.05), anchor(0.1), velocity_reading=[0, 0, 0])[1] == "VERIFY"
    assert c.phase == "BRAKING"
    assert c.update(vector(), vector(), None, velocity_reading=[0, 0, 0])[3]
    assert c.update(vector(), vector(), RangeReading(0.1, 0.05), anchor(0.1), velocity_reading=[0, 0, 0])[1] == "STOP"


def test_recovery_fails_closed_for_missing_anchor_and_sensor_disagreement():
    c = recovery()
    assert c.update(vector(), vector(), RangeReading(0.3, 0.05), None, velocity_reading=[0, 0, 0])[1] == "ABSTAIN"
    c = recovery()
    assert c.update(vector(), vector(), RangeReading(1.0, 0.05), anchor(0.1), velocity_reading=[0, 0, 0])[1] == "ABSTAIN"
    assert c.terminal_reason == "RECOVERY_ANCHOR_RANGE_CONFLICT"


def test_recovery_is_bounded_and_reset_clears_state():
    c = recovery(limit=1)
    c.update(vector(), vector(), RangeReading(0.3, 0.05), anchor(0.3), velocity_reading=[0, 0, 0])
    assert c.update(vector(), vector(), RangeReading(0.3, 0.05), anchor(0.3), velocity_reading=[0, 0, 0])[1] == "ABSTAIN"
    assert c.terminal_reason == "RECOVERY_TIMEOUT"
    c.reset()
    assert c.phase == "BASE" and not c.recovery_used and c.recovery_steps == 0


def test_second_rejection_does_not_start_a_second_recovery():
    c = recovery()
    c.update(vector(), vector(), RangeReading(0.1, 0.05), anchor(0.1), velocity_reading=[0, 0, 0])
    c.update(vector(), vector(), None, velocity_reading=[0, 0, 0])
    result = c.update(vector(), vector(), RangeReading(0.3, 0.05), anchor(0.3), velocity_reading=[0, 0, 0])
    assert result[1] == "ABSTAIN" and not result[3]
    assert c.terminal_reason == "ANCHOR_OUTSIDE_CONFIRMATION_MARGIN"


def test_recovery_abstains_when_velocity_missing():
    c = recovery()
    result = c.update(vector(), vector(), RangeReading(0.3, 0.05), anchor(0.3), velocity_reading=None)
    assert result[1] == "ABSTAIN" and c.terminal_reason == "RECOVERY_SENSOR_INVALID"
