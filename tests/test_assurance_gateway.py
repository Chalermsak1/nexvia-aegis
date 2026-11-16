from dataclasses import replace
import math
import random
import pytest
from aegis.development.bounded_braking import BoundedStatePacket
from aegis.development.assurance_gateway import CaptureWitness, FreshnessGateway, CommandLease, LeaseWatchdog
from aegis.development.sampled_motion_reference import sampled_motion_reference
from aegis.env.mujoco_lease_brake import ForceLimitedBrakeEnvironment


def packet(tick=0, **kw):
    d = dict(position=[0., 0., 1.], velocity=[.5, 0., 0.], position_error_m=.01,
             velocity_error_m_s=.02, sequence=tick, acquired_seconds=tick * .02,
             frame='WORLD', source='SIM_PRIMARY', bound_basis='TEST_ASSERTION')
    d.update(kw); return BoundedStatePacket(**d)


def test_separately_recorded_capture_binds_payload_and_acquisition():
    w = CaptureWitness(); p = packet(); r = w.capture(p, tick=0)
    assert FreshnessGateway().check(p, r['id'], tick=0, witness=w)['accepted']
    with pytest.raises(ValueError): w.capture(p, tick=0)


@pytest.mark.parametrize('defect', ['time', 'position', 'velocity', 'radius', 'source', 'missing_receipt'])
def test_relabel_or_substitution_rejected_and_latched(defect):
    w = CaptureWitness(); p = packet(); r = w.capture(p, tick=0); rid = r['id']
    if defect == 'time': p = replace(p, acquired_seconds=.02, sequence=1)
    elif defect == 'position': p = replace(p, position=[.1, 0., 1.])
    elif defect == 'velocity': p = replace(p, velocity=[-.5, 0., 0.])
    elif defect == 'radius': p = replace(p, velocity_error_m_s=1.)
    elif defect == 'source': p = replace(p, source='SIM_SECONDARY')
    else: rid = 'missing'
    g = FreshnessGateway(); assert not g.check(p, rid, tick=1, witness=w)['accepted']
    assert g.check(packet(), r['id'], tick=1, witness=w)['reason'].startswith('LATCHED:')


def test_fresh_delivery_id_cannot_hide_old_payload():
    w = CaptureWitness(); p = packet(); w.capture(p, tick=0)
    new = packet(1, velocity=[.4, 0., 0.]); receipt = w.capture(new, tick=1)
    old = replace(p, sequence=1, acquired_seconds=.02)
    assert FreshnessGateway().check(old, receipt['id'], tick=1, witness=w)['reason'] == 'CAPTURE_PAYLOAD_MISMATCH'


def test_reuse_age_and_future_boundary():
    w = CaptureWitness(); p = packet(); r = w.capture(p, tick=0)
    g = FreshnessGateway(); assert g.check(p, r['id'], tick=0, witness=w)['accepted']
    assert g.check(replace(p, sequence=1), r['id'], tick=1, witness=w)['reason'] == 'CAPTURE_REUSED'
    assert FreshnessGateway().check(p, r['id'], tick=4, witness=w)['accepted']
    assert FreshnessGateway().check(p, r['id'], tick=5, witness=w)['reason'] == 'STALE_CAPTURE'
    new = packet(6); r = w.capture(new, tick=6)
    assert FreshnessGateway().check(new, r['id'], tick=5, witness=w)['reason'] == 'FUTURE_CAPTURE'


def test_witness_does_not_prove_semantic_accuracy_or_physical_freshness():
    # Both assertions are deliberately wrong but the modeled trusted layer vouches.
    w = CaptureWitness(); p = packet(2, velocity=[-.5, 0., 0.]); r = w.capture(p, tick=2)
    assert FreshnessGateway().check(p, r['id'], tick=2, witness=w)['accepted']
    assert p.velocity[0] != .5  # No truth/semantic test exists in this hash witness.


def lease(tick=0, **kw):
    d = dict(sequence=tick, issued_tick=tick, expires_tick=tick + 1, force_n=[-2., 0., 0.]); d.update(kw)
    return CommandLease(**d)


def test_lease_expires_before_next_physics_interval_and_cannot_recover():
    g = LeaseWatchdog(); assert g.advance(tick=0, command=lease())['state'] == 'LIVE_LEASE'
    r = g.advance(tick=1, command=None)
    assert r['reason'] == 'NO_LIVE_COMMAND_LEASE' and r['force_n'] == [0., 0., 0.]
    assert g.advance(tick=2, command=lease(2))['fallback_requested']


@pytest.mark.parametrize('kw,reason', [(dict(expires_tick=20),'INVALID_LEASE_DURATION'),
 (dict(expires_tick=0),'INVALID_LEASE_DURATION'),(dict(issued_tick=1),'LATE_OR_FUTURE_ISSUE'),
 (dict(sequence=True),'NONINTEGER_LEASE'),(dict(force_n=[3.,0.,0.]),'EXCESS_FORCE'),
 (dict(force_n=[float('nan'),0.,0.]),'nonfinite vector')])
def test_invalid_lease_never_applied(kw, reason):
    r = LeaseWatchdog().advance(tick=0, command=lease(**kw))
    assert r['reason'] == reason and r['force_n'] == [0.,0.,0.]


@pytest.mark.parametrize('flags,reason', [(dict(refusal=True),'CONTROLLER_REFUSED'),(dict(freshness_ok=False),'FRESHNESS_REJECTED')])
def test_refusal_preempts_even_a_new_command(flags, reason):
    assert LeaseWatchdog().advance(tick=0, command=lease(), **flags)['reason'] == reason


def test_watchdog_clock_gap_and_freeze_fail_closed():
    for bad in (0, 2):
        g = LeaseWatchdog(); g.advance(tick=0, command=lease())
        assert g.advance(tick=bad, command=lease(bad))['reason'] == 'WATCHDOG_CLOCK_DISCONTINUITY'


def test_timely_semantically_wrong_commands_are_not_detected_by_a_lease():
    g = LeaseWatchdog()
    for tick in range(5):
        assert g.advance(tick=tick, command=lease(tick, force_n=[2.,0.,0.]))['state'] == 'LIVE_LEASE'


def test_leases_are_snapshots_and_heartbeats_do_not_extend_expiry():
    force = [-2., 0., 0.]; g = LeaseWatchdog()
    g.advance(tick=0, command=lease(force_n=force)); force[0] = 900.
    r = g.advance(tick=1, command=None)
    assert r['state'] == 'FALLBACK_REQUESTED'


def reference(**kw):
    args = dict(initial_speed_upper_m_s=.6, steps=10, dt_seconds=.02, mass_lower_kg=1.,
                command_force_upper_n=2., disturbance_force_upper_n=.2, damping_gain_upper_kg_s=2.)
    args.update(kw); return sampled_motion_reference(**args)


def test_sampled_horizon_matches_no_braking_worst_force_trajectory():
    # Exact semi-implicit sum from v_{k+1}=v_k+2.2*.02, no brake credit.
    v = .6; path = 0.
    for _ in range(10): v += 2.2 * .02; path += v * .02
    r = reference()
    assert r['sampled_path_upper_m'] == pytest.approx(path)
    assert r['sampled_speed_upper_m_s'] == pytest.approx(v)
    assert r['braking_credit'] is False


def test_clipped_damping_nonexpansive_map_and_disturbance_bound():
    rng = random.Random(20261116)
    for _ in range(100):
        v = [rng.uniform(-2,2) for _ in range(3)]; norm = math.hypot(*v)
        for cap in (.05, 1.):
            after = [x - .02 * max(-cap, min(cap, 2.*x)) for x in v]
            assert math.hypot(*after) <= norm + 1e-12


@pytest.mark.parametrize('kw,classification', [(dict(damping_gain_upper_kg_s=51.),'UNSUPPORTED_DAMPING_STEP'),
 (dict(initial_speed_upper_m_s=1e308,steps=10**300),'UNSUPPORTED_NUMERIC_RANGE'),
 (dict(initial_speed_upper_m_s=1e-300,dt_seconds=1e-300,command_force_upper_n=0.,disturbance_force_upper_n=0.),'UNSUPPORTED_NUMERIC_RANGE')])
def test_reference_unsupported_numeric_or_step(kw, classification):
    assert reference(**kw)['classification'] == classification


@pytest.mark.parametrize('kw', [dict(steps=True),dict(steps=-1),dict(mass_lower_kg=0.),dict(disturbance_force_upper_n=-1.),dict(initial_speed_upper_m_s=None)])
def test_reference_invalid_input(kw):
    with pytest.raises(ValueError): reference(**kw)


def test_native_capped_brake_and_nominal_gravity_response():
    env = ForceLimitedBrakeEnvironment(brake_cap_per_axis_n=.05)
    env.reset_development(.5)
    pre = env.prepare_forces([0.,0.,0.],[0.,0.,0.],brake_gain=2.)
    assert pre['actuator_force_pre_n'] == pytest.approx([-.05,0.,0.])
    p = env.advance_prepared()
    assert p['velocity'] == pytest.approx([.499,0.,0.])
    assert p['position'][2] == pytest.approx(1.3)
    assert env.runtime_record()['actuator_forcelimited'] == [1,1,1]


def test_mass_mismatch_retains_gravity_error_and_unprepared_step_rejects():
    env = ForceLimitedBrakeEnvironment(actual_mass_kg=1.25)
    env.reset_development(.5)
    with pytest.raises(ValueError): env.advance_prepared()
    env.prepare_forces([0.,0.,0.],[0.,0.,0.],brake_gain=0.)
    p = env.advance_prepared()
    assert p['velocity'][2] == pytest.approx(.02*(9.81/1.25-9.81))
    with pytest.raises(NotImplementedError): env.reset(None)
