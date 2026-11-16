from dataclasses import replace
import math
import random
import pytest
from aegis.development.bounded_braking import BoundedStatePacket, BoundedStateGate, braking_command


def packet(**kw):
    fields = dict(position=[1., 2., 3.], velocity=[.5, 0., 0.], position_error_m=.01,
                  velocity_error_m_s=.02, sequence=0, acquired_seconds=0., frame='WORLD',
                  source='SIM_STATE_SENSOR_V1', bound_basis='SYNTHETIC_ASSERTION')
    fields.update(kw)
    return BoundedStatePacket(**fields)


def gate(**kw):
    fields = dict(max_age_seconds=.1, acceleration_norm_upper_m_s2=2.)
    fields.update(kw)
    return BoundedStateGate(**fields)


def test_age_transport_exact_analytic_bound():
    state, _ = gate().accept(packet(), now_seconds=.1)
    assert state.position == (1.05, 2., 3.)
    assert state.position_error_m == pytest.approx(.022)
    assert state.velocity_error_m_s == pytest.approx(.22)
    assert state.age_seconds == .1


@pytest.mark.parametrize('fields', [dict(position=[1., 2.]), dict(position=[True, 2., 3.]),
    dict(position=['1', 2., 3.]), dict(velocity=[float('nan'), 0., 0.]),
    dict(velocity=None), dict(position_error_m=None), dict(position_error_m=-1.),
    dict(velocity_error_m_s=True), dict(velocity_error_m_s=float('inf')),
    dict(sequence=True), dict(sequence=-1), dict(sequence=0.), dict(acquired_seconds=-1.),
    dict(acquired_seconds=.1), dict(frame='BODY'), dict(source='UNKNOWN'), dict(bound_basis='')])
def test_bad_packets_reject_and_latch(fields):
    g = gate()
    assert g.accept(packet(**fields), now_seconds=0.)[0] is None
    assert g.accept(packet(sequence=1), now_seconds=.01)[1].startswith('LATCHED:')


@pytest.mark.parametrize('now', [True, None, '0', float('nan'), -1., 10**500])
def test_bad_clock_rejects(now):
    assert gate().accept(packet(), now_seconds=now)[0] is None


def test_stale_exact_boundary_and_replay():
    assert gate().accept(packet(), now_seconds=.1)[0] is not None
    assert gate().accept(packet(), now_seconds=math.nextafter(.1, math.inf))[0] is None
    g = gate(); assert g.accept(packet(), now_seconds=0.)[0] is not None
    assert g.accept(packet(), now_seconds=.01)[1] == 'REPLAY_OR_CLOCK_REGRESSION'


def test_clock_regression_and_source_switch_reject():
    g = gate(); g.accept(packet(acquired_seconds=.02), now_seconds=.02)
    assert g.accept(packet(sequence=1), now_seconds=.01)[1] == 'REPLAY_OR_CLOCK_REGRESSION'
    assert gate().accept(packet(source='OTHER'), now_seconds=0.)[0] is None


def test_snapshot_has_no_mutable_input_alias():
    p = packet(); state, _ = gate().accept(p, now_seconds=0.)
    p.position[0] = 900; p.velocity[0] = -900
    assert state.position[0] == 1. and state.velocity[0] == .5


def test_numeric_overflow_is_not_an_accepted_bound():
    state, reason = gate(max_age_seconds=1e300, acceleration_norm_upper_m_s2=1e300).accept(packet(), now_seconds=1e300)
    assert state is None and 'NUMERIC' in reason


@pytest.mark.parametrize('speed,radius,accepted', [(1., .99, True), (1., 1., False), (1., 1.01, False), (0., 0., False)])
def test_direction_boundary_and_zero_speed(speed, radius, accepted):
    state, _ = gate().accept(packet(velocity=[speed, 0., 0.], velocity_error_m_s=radius), now_seconds=0.)
    c = braking_command(state, force_norm_limit_n=2.)
    assert (c['status'] == 'COMMAND_PROPOSED') is accepted
    if accepted: assert c['worst_case_power_w'] < 0


def test_reported_reversal_refused_but_point_baseline_can_accelerate_truth():
    state, _ = gate().accept(packet(velocity=[-.5, 0., 0.], velocity_error_m_s=1.02), now_seconds=0.)
    assert braking_command(state, force_norm_limit_n=2.)['status'] == 'NO_COMMAND'
    point = braking_command(state, force_norm_limit_n=2., use_uncertainty=False)
    assert point['force_n'][0] * .5 > 0
    assert point['worst_case_power_w'] > 0


def test_undeclared_common_mode_error_cannot_be_detected_by_this_contract():
    state, _ = gate().accept(packet(velocity=[-.5, 0., 0.]), now_seconds=0.)
    c = braking_command(state, force_norm_limit_n=2.)
    assert c['worst_case_power_w'] < 0
    assert c['force_n'][0] * .5 > 0  # Truth OUTSIDE asserted ball; no unconditional claim.


def test_support_function_upper_bound_and_force_norm_over_synthetic_balls():
    rng = random.Random(20261116)
    for _ in range(200):
        v = [rng.uniform(-3, 3) for _ in range(3)]
        radius = .3 * math.hypot(*v)
        state, _ = gate().accept(packet(velocity=v, velocity_error_m_s=radius), now_seconds=0.)
        c = braking_command(state, force_norm_limit_n=2.)
        f = c['force_n']; assert math.hypot(*f) == pytest.approx(2.)
        extreme = [x + radius * y / math.hypot(*f) for x, y in zip(v, f)]
        assert math.fsum(x * y for x, y in zip(f, extreme)) == pytest.approx(c['worst_case_power_w'])
        assert c['worst_case_power_w'] < 0


def test_transport_contains_constant_extreme_acceleration_trajectory():
    # Analytic adversarial directions, not generated from implementation output.
    for sign in (-1, 1):
        p = packet(position=[0., 0., 0.], velocity=[1., 0., 0.], position_error_m=.01, velocity_error_m_s=.02)
        state, _ = gate().accept(p, now_seconds=.1)
        actual_p = sign * .01 + (1. + sign * .02) * .1 + .5 * sign * 2. * .1**2
        actual_v = 1. + sign * .02 + sign * 2. * .1
        assert abs(actual_p - state.position[0]) <= state.position_error_m + 1e-14
        assert abs(actual_v - state.velocity[0]) <= state.velocity_error_m_s + 1e-14


@pytest.mark.parametrize('limit', [True, 0., -1., float('nan'), None])
def test_invalid_force_limit(limit):
    with pytest.raises(ValueError): braking_command(None, force_norm_limit_n=limit)


def test_instantaneous_dissipation_can_add_energy_over_one_hold_interval():
    state, _ = gate().accept(packet(velocity=[.01, 0., 0.], velocity_error_m_s=0.), now_seconds=0.)
    instantaneous = braking_command(state, force_norm_limit_n=2.)
    assert instantaneous['worst_case_power_w'] < 0
    point = braking_command(state, force_norm_limit_n=2., use_uncertainty=False, hold_seconds=.02)
    assert point['worst_case_hold_energy_change_j'] > 0
    bounded = braking_command(state, force_norm_limit_n=2., hold_seconds=.02)
    assert bounded['status'] == 'NO_COMMAND' and bounded['reason'] == 'HOLD_ENERGY_BOUND_UNSUPPORTED'


def test_finite_hold_energy_matches_exact_corner_dynamics():
    state, _ = gate().accept(packet(velocity=[.5, 0., 0.], velocity_error_m_s=.02), now_seconds=0.)
    c = braking_command(state, force_norm_limit_n=2., hold_seconds=.02)
    f = c['force_n'][0]; worst_v = .5 - .02
    actual_change = .5 * ((worst_v + f * .02)**2 - worst_v**2)
    assert actual_change == pytest.approx(c['worst_case_hold_energy_change_j'])
    assert actual_change < 0


@pytest.mark.parametrize('hold', [0., .02, 1e308])
def test_extreme_force_and_duration_are_explicitly_unsupported(hold):
    state, _ = gate().accept(packet(), now_seconds=0.)
    c = braking_command(state, force_norm_limit_n=1e308, hold_seconds=hold)
    if hold > 0:
        assert c['status'] == 'NO_COMMAND'
    else:
        assert c['status'] in ('NO_COMMAND', 'COMMAND_PROPOSED')
