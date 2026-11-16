from dataclasses import replace
import math
import random
import pytest
from aegis.development.bounded_braking import BoundedStatePacket
from aegis.development.dual_source_braking import SourceBrakeSupervisor, SimulatedDamperSwitch, overlap


def packet(source='SIM_PRIMARY', **kw):
    fields = dict(position=[0., 0., 1.], velocity=[.5, 0., 0.], position_error_m=.01,
                  velocity_error_m_s=.02, sequence=0, acquired_seconds=0., frame='WORLD',
                  source=source, bound_basis='TEST_ASSERTION')
    fields.update(kw); return BoundedStatePacket(**fields)


def test_honest_pair_command_checked_over_union():
    c = SourceBrakeSupervisor().choose(packet(), packet('SIM_SECONDARY', velocity_error_m_s=.03), now_seconds=0.)
    assert c['status'] == 'COMMAND_PROPOSED' and c['force_n'] == [-2., -0., -0.]
    assert c['union_power_upper_w'] == pytest.approx(-.94)
    assert c['union_hold_energy_upper_j'] == pytest.approx(.02 * -.94 + .0008)


@pytest.mark.parametrize('bad_source', ['primary', 'secondary'])
def test_one_reversal_causes_contradiction_without_identifying_faulty_sensor(bad_source):
    a, b = packet(), packet('SIM_SECONDARY')
    if bad_source == 'primary': a = replace(a, velocity=[-.5, 0., 0.])
    else: b = replace(b, velocity=[-.5, 0., 0.])
    g = SourceBrakeSupervisor(); c = g.choose(a, b, now_seconds=0.)
    assert c['reason'] == 'CONTRADICTORY_SOURCE_BALLS' and c['velocity_compatible'] is False
    again = g.choose(packet(sequence=1, acquired_seconds=.02), packet('SIM_SECONDARY', sequence=1, acquired_seconds=.02), now_seconds=.02)
    assert again['reason'].startswith('LATCHED:') and again['primary'] is None


def test_shared_reversal_can_look_compatible_and_accelerate_truth():
    a = packet(velocity=[-.5, 0., 0.]); b = packet('SIM_SECONDARY', velocity=[-.5, 0., 0.])
    c = SourceBrakeSupervisor().choose(a, b, now_seconds=0.)
    assert c['velocity_compatible'] is True and c['status'] == 'COMMAND_PROPOSED'
    assert c['union_power_upper_w'] < 0 and c['force_n'][0] * .5 > 0


def test_intersection_fusion_would_hide_the_honest_wide_ball():
    # Primary small ball is false; secondary wide ball contains truth -.5.
    # Their intersection is near +.5 and would wrongly justify braking toward -x.
    a = packet(); b = packet('SIM_SECONDARY', velocity_error_m_s=1.02)
    c = SourceBrakeSupervisor().choose(a, b, now_seconds=0.)
    assert c['velocity_compatible'] is True and c['reason'] == 'UNION_BRAKE_UNSUPPORTED'
    assert c['union_power_upper_w'] > 0 and c['force_n'] is None


@pytest.mark.parametrize('defect', ['missing', 'source_alias', 'frame', 'future', 'absent_bound', 'empty_basis'])
def test_required_source_invalid_no_fallback_to_primary(defect):
    b = packet('SIM_SECONDARY')
    if defect == 'missing': b = None
    elif defect == 'source_alias': b = replace(b, source='SIM_PRIMARY')
    elif defect == 'frame': b = replace(b, frame='BODY')
    elif defect == 'future': b = replace(b, acquired_seconds=.1)
    elif defect == 'absent_bound': b = replace(b, velocity_error_m_s=None)
    else: b = replace(b, bound_basis='')
    c = SourceBrakeSupervisor().choose(packet(), b, now_seconds=0.)
    assert c['status'] == 'NO_COMMAND' and c['reason'] == 'REQUIRED_SOURCE_REJECTED'


def test_baseline_explicitly_ignores_secondary():
    c = SourceBrakeSupervisor(require_secondary=False).choose(packet(), None, now_seconds=0.)
    assert c['status'] == 'COMMAND_PROPOSED' and c['secondary'] is None
    assert c['input_reasons'][1] == 'NOT_USED_BASELINE'


@pytest.mark.parametrize('axis', [0, 1, 2])
def test_position_disagreement_blocks_velocity_compatible_command(axis):
    p = [0., 0., 1.]; p[axis] += .4
    c = SourceBrakeSupervisor().choose(packet(), packet('SIM_SECONDARY', position=p), now_seconds=0.)
    assert c['position_compatible'] is False and c['velocity_compatible'] is True
    assert c['force_n'] is None


def test_compatibility_boundary_and_numeric_range():
    assert overlap([0., 0., 0.], .5, [1., 0., 0.], .5)
    assert not overlap([0., 0., 0.], .5, [math.nextafter(1., math.inf), 0., 0.], .5)
    with pytest.raises(ValueError): overlap([1e308, 0., 0.], .01, [-1e308, 0., 0.], .01)


def test_union_support_bounds_adversarial_extremes_of_either_source():
    rng = random.Random(20261116)
    for _ in range(100):
        v = [rng.uniform(.5, 2.), rng.uniform(-.1, .1), 0.]
        b = [v[0] + .01, v[1], 0.]
        c = SourceBrakeSupervisor().choose(packet(velocity=v, velocity_error_m_s=.05), packet('SIM_SECONDARY', velocity=b, velocity_error_m_s=.06), now_seconds=0.)
        assert c['status'] == 'COMMAND_PROPOSED'
        f = c['force_n']; norm = math.hypot(*f)
        for center, radius in ((v, .05), (b, .06)):
            extreme = [x + radius * y / norm for x, y in zip(center, f)]
            assert math.fsum(x * y for x, y in zip(extreme, f)) <= c['union_power_upper_w'] + 1e-12


def test_no_command_near_rest_is_not_a_rest_certificate():
    c = SourceBrakeSupervisor().choose(packet(velocity=[.01, 0., 0.]), packet('SIM_SECONDARY', velocity=[.01, 0., 0.]), now_seconds=0.)
    assert c['status'] == 'NO_COMMAND' and c['force_n'] is None
    assert 'rest' not in c


def test_replay_and_clock_regression_do_not_reset_session():
    g = SourceBrakeSupervisor(); g.choose(packet(), packet('SIM_SECONDARY'), now_seconds=0.)
    c = g.choose(packet(), packet('SIM_SECONDARY'), now_seconds=.02)
    assert c['reason'] == 'REQUIRED_SOURCE_REJECTED'
    assert c['input_reasons'] == ['REPLAY_OR_CLOCK_REGRESSION'] * 2


def test_damper_delay_is_three_complete_ticks_and_stays_requested():
    s = SimulatedDamperSwitch(enabled=True)
    assert s.advance(step=0, request=False, available=True)['state'] == 'NOT_REQUESTED'
    for k in (1, 2, 3):
        r = s.advance(step=k, request=k == 1, available=True)
        assert r['state'] == 'PENDING' and r['activation_due_step'] == 4
    r = s.advance(step=4, request=False, available=True)
    assert r['state'] == 'ACTIVE_ASSUMED' and r['requested_damping_kg_s'] == 2.


def test_missing_damper_latches_failed_even_if_available_later():
    s = SimulatedDamperSwitch(enabled=True, delay_steps=0)
    assert s.advance(step=0, request=True, available=False)['state'] == 'FAILED_UNAVAILABLE'
    assert s.advance(step=1, request=False, available=True)['state'] == 'FAILED_UNAVAILABLE'


def test_damper_disabled_and_clock_replay():
    s = SimulatedDamperSwitch(enabled=False)
    assert s.advance(step=0, request=True, available=False)['state'] == 'DISABLED_COAST_BASELINE'
    with pytest.raises(ValueError): s.advance(step=0, request=True, available=True)
    with pytest.raises(ValueError): s.advance(step=2, request=True, available=True)


@pytest.mark.parametrize('kw', [dict(enabled=1), dict(enabled=True, delay_steps=True), dict(enabled=True, delay_steps=-1), dict(enabled=True, damping_kg_s=0)])
def test_invalid_switch_configuration(kw):
    with pytest.raises(ValueError): SimulatedDamperSwitch(**kw)
