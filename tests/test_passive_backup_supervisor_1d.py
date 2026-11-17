from copy import deepcopy
from fractions import Fraction as Q
from itertools import product
import random
import pytest
from aegis.development import passive_backup_supervisor_1d as core
from aegis.development.runtime_readiness import DeadlineGuard,restart_check,calibration_check
from aegis.development.durable_feedback_session import runtime_identity
from scripts.research.temporal_feedback_study_1d import plan,run_case


def backup():return dict(dt='.02',mass='1',spring='4',damping='3',position_scale='1',velocity_scale='1',anchor='0',
    level='5',force_cap='4',disturbance='.01',safe_position=['-.5','.32'])
def state():return dict(boot_id='runtime-boot',epoch_tick=100,position=['0','0'],velocity=['.5','.5'],source_id='synthetic-backup-state',evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS')
def premises():return dict(state_bounds_asserted=True,active_cap_asserted=True,backup_model_asserted=True,independent_handoff_asserted=True,
    power_independent_backup_asserted=True,no_impulse_handoff_asserted=True)


def primary():
    a=plan()[0];a['model']['disturbance']='.01'
    t=run_case(a)['responses'][-1]['result'];clock=iter((1000,1001,1002));guard=DeadlineGuard(boot_id='runtime-boot',clock=lambda:next(clock));budget=guard.begin(10)
    pin=dict(store_id='fixture',header_sha256='a'*64,seq=1,head_sha256='b'*64)
    r=restart_check(actual_checkpoint=pin,expected_checkpoint=pin,actual_runtime=runtime_identity(),expected_runtime=runtime_identity(),boot_id='runtime-boot',boot_start_ns=1000,now_ns=1010,freshness_limit_ns=10,
        fresh_observations={key:dict(boot_id='runtime-boot',observed_ns=1005,received_ns=1006,evidence_asserted=True) for key in ('STATE','ACTUATOR','POWER','CLOCK_MAP')})
    p=dict(classification='SYNTHETIC_ONLY',device_id='synthetic-device',reference_id='synthetic-reference',frame='WORLD_X_SI',velocity_error_bound='.01',force_error_bound='.02')
    samples=[dict(id='s1',device_id='synthetic-device',reference_id='synthetic-reference',frame='WORLD_X_SI',sample_ns=1005,velocity=['.5','.5'],force=['0','0'],reference_velocity=['.5','.5'],reference_force=['0','0'])]
    return dict(temporal=t,deadline=guard.evaluate(budget,lambda:t),restart=r,calibration=calibration_check(p,samples))


def assess(**changes):
    args=dict(backup=backup(),state=state(),assessment_tick=100,boot_id='runtime-boot',active_force_cap='1',environment_force='.01',
        handoff_delay_ticks=[0,3],monitor_ticks=3,max_state_age_ticks=8,premises=premises(),primary=primary())
    args.update(changes);return core.assess_supervisor(**args)


def test_exact_matrix_identity_and_bound_conditions():
    raw=backup();s=core.model(raw);r=core.certificate(raw)
    assert r['status']=='CONDITIONAL_SAMPLED_INVARIANT_SET'
    assert all(r[k] for k in ('level_sufficient','force_cap_sufficient','safe_region_sufficient'))
    assert Q(0)<s['rho']<1 and s['minimum_level']<=s['level']
    assert r['physical_hardware_verified'] is False and not r['operational_authorization']


def test_exact_rational_sample_trajectories_remain_inside_declared_invariant_set():
    s=core.model(backup());rng=random.Random(1711)
    for _ in range(35):
        p=Q(rng.randint(-20,20),100);v=Q(rng.randint(-40,40),100)
        if core.energy_box(s,core.point(p),core.point(v))>s['level']:continue
        for k in range(100):
            w=Q(rng.choice((-1,0,1)),100);f=-s['spring']*p-s['damping']*v
            assert abs(f)<=s['force_cap']
            # Independent physical scalar equations, not matrix advancement.
            v+=s['dt']*(f+w)/s['mass'];p+=s['dt']*v
            assert core.energy_box(s,core.point(p),core.point(v))<=s['level']
            assert s['safe_position'].contains(p)


def test_box_energy_maximum_contains_independent_interior_samples():
    s=core.model(backup());p=core.internal(Q('-.1'),Q('.15'));v=core.internal(Q('-.2'),Q('.4'));upper=core.energy_box(s,p,v)
    for i,j in product(range(11),repeat=2):
        x=p.lo+(p.hi-p.lo)*i/10;y=v.lo+(v.hi-v.lo)*j/10
        assert core.energy_box(s,core.point(x),core.point(y))<=upper


@pytest.mark.parametrize('field,value',[('level','.0001'),('force_cap','.1'),('safe_position',['-.01','.01'])])
def test_invariance_conditions_are_not_inferred_or_weakened(field,value):
    raw=backup();raw[field]=value;r=core.certificate(raw)
    assert r['status']=='INVARIANCE_NOT_ESTABLISHED'
    assert assess(backup=raw)['development_action'] is None


@pytest.mark.parametrize('field,value',[('mass','0'),('spring','0'),('damping','0'),('dt','2'),('level',True),('spring','1e99999999')])
def test_invalid_or_unstable_models_are_unsupported(field,value):
    raw=backup();raw[field]=value
    assert assess(backup=raw)['status']=='UNKNOWN_INPUT'


def test_continuation_requires_future_backup_reserve_not_just_current_viability():
    now=assess(monitor_ticks=3);late=assess(monitor_ticks=5)
    assert now['development_action']=='CONTINUE_WITH_BACKUP_RESERVE'
    assert late['current_handoff_supported'] is True and late['continued_operation_reserve_supported'] is False
    assert late['development_action']=='HANDOFF_TO_PASSIVE_BACKUP'


def test_missing_primary_can_only_use_a_separately_supported_backup_state():
    r=assess(primary=None);assert r['development_action']=='HANDOFF_TO_PASSIVE_BACKUP'
    s=state();s['evidence_status']='UNKNOWN'
    r=assess(primary=None,state=s);assert r['development_action'] is None and r['reason']=='NO_SUPPORTED_BACKUP_STATE'


def test_deadline_failure_does_not_become_zero_force_or_assumed_braking():
    p=primary();p['deadline']['status']='RESULT_WITHHELD'
    r=assess(primary=p)
    assert r['development_action']=='HANDOFF_TO_PASSIVE_BACKUP'
    flags=premises();flags['independent_handoff_asserted']=False
    assert assess(primary=p,premises=flags)['development_action'] is None


@pytest.mark.parametrize('name',list(premises()))
def test_every_physical_premise_is_required(name):
    flags=premises();flags[name]=False;r=assess(premises=flags)
    assert r['development_action'] is None and not r['conditional_future_sampled_containment']


def test_expired_or_wrong_boot_backup_state_not_relabelled():
    s=state();s['boot_id']='old';assert assess(state=s)['reason']=='BOOT_MISMATCH'
    s=state();s['epoch_tick']=90;assert assess(state=s)['reason']=='STATE_EPOCH_UNSUPPORTED'
    s=state();s['epoch_tick']=101;assert assess(state=s)['reason']=='STATE_EPOCH_UNSUPPORTED'


def test_transport_retains_queued_acceleration_bound_instead_of_zero_default():
    r=assess(assessment_tick=102,primary=None)
    assert list(map(Q,r['transported_velocity']))==[Q('.4596'),Q('.5404')]
    assert r['transported_position']!=['0','0']


def test_stale_primary_result_is_not_reused_for_nominal_continuation():
    r=assess(assessment_tick=101)
    assert r['development_action'] is None and r['reason']=='PRIMARY_ASSESSMENT_EPOCH_MISMATCH'


def test_initial_state_outside_backup_region_does_not_receive_a_safe_fallback_label():
    s=state();s['velocity']=['1','1'];r=assess(state=s,primary=None)
    assert r['development_action'] is None and r['current_handoff_supported'] is False


def test_lost_backup_model_consistency_is_observable_but_not_a_physical_response():
    before=dict(position=['0','0'],velocity=['.5','.5'])
    valid=dict(position=['.0094','.0094'],velocity=['.47','.47'])
    r=core.check_backup_step(backup(),before,valid);assert r['status']=='COMPATIBLE_UNDER_ASSERTED_BACKUP_MODEL'
    missing=dict(position=['.01','.01'],velocity=['.5','.5'])
    assert core.check_backup_step(backup(),before,missing)['status']=='BACKUP_MODEL_OR_EVIDENCE_CONTRADICTION'
    assert core.check_backup_step(backup(),before,None)['status']=='UNKNOWN_BACKUP_OBSERVATION'


def test_all_admissible_handoff_delays_are_checked():
    a=assess(handoff_delay_ticks=[0,3],primary=None);b=assess(handoff_delay_ticks=[0,8],primary=None)
    assert a['development_action']=='HANDOFF_TO_PASSIVE_BACKUP'
    assert b['development_action'] is None and b['current_handoff_supported'] is False


def test_certificate_and_candidates_never_authorize_hardware():
    r=assess()
    assert r['conditional_future_sampled_containment'] is True
    assert r['dispatch'] is False and r['operational_authorization'] is False and r['hardware_validation'] is False


def test_zero_disturbance_has_asymptotic_claim_only_for_declared_backup_model():
    raw=backup();raw['disturbance']='0';r=core.certificate(raw)
    assert r['asymptotic_origin_convergence_under_zero_disturbance'] is True


def test_changing_operating_region_or_force_domain_cannot_reuse_nominal_claim():
    b=backup();b['safe_position']=['-.6','.6']
    assert assess(backup=b)['reason']=='PRIMARY_AND_BACKUP_PHYSICAL_CONTRACT_MISMATCH'
    assert assess(environment_force='.02')['status']=='UNKNOWN_INPUT'
