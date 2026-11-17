from copy import deepcopy
import pytest
from aegis.development.durable_feedback_session import runtime_identity,sha
from aegis.development.runtime_readiness import DeadlineGuard,restart_check,calibration_check,select_response
from scripts.research.temporal_feedback_study_1d import plan,run_case


def restart_args():
    checkpoint=dict(store_id='fixture',header_sha256='a'*64,seq=1,head_sha256='b'*64)
    return dict(actual_checkpoint=checkpoint,expected_checkpoint=deepcopy(checkpoint),actual_runtime=runtime_identity(),
        expected_runtime=runtime_identity(),boot_id='local-boot',boot_start_ns=100,now_ns=110,freshness_limit_ns=10,
        fresh_observations={key:dict(boot_id='local-boot',observed_ns=105,received_ns=106,evidence_asserted=True) for key in ('STATE','ACTUATOR','POWER','CLOCK_MAP')})


def profile():return dict(classification='SYNTHETIC_ONLY',device_id='synthetic-device',reference_id='synthetic-independent-reference',
                         frame='WORLD_X_SI',velocity_error_bound='.01',force_error_bound='.02')
def samples():return [dict(id='s1',device_id='synthetic-device',reference_id='synthetic-independent-reference',frame='WORLD_X_SI',
    sample_ns=105,velocity=['.5','.5'],force=['0','0'],reference_velocity=['.5','.5'],reference_force=['0','0'])]
def temporal():return run_case(plan()[0])['responses'][-1]['result']
def clock(values):
    values=iter(values);return lambda:next(values)


def good_inputs():
    t=temporal();g=DeadlineGuard(boot_id='local-boot',clock=clock([100,101,109]));b=g.begin(10)
    return t,dict(deadline=g.evaluate(b,lambda:t),restart=restart_check(**restart_args()),
        calibration=calibration_check(profile(),samples()),boot_id='local-boot',mode='DEVELOPMENT_SIMULATION')


def test_restart_needs_pins_and_all_fresh_components():
    r=restart_check(**restart_args());assert r['status']=='DEV_RESYNCHRONIZED_NO_OPERATIONAL_AUTHORITY'
    assert not r['operational_authorization'] and not r['hardware_validation']


@pytest.mark.parametrize('change',['checkpoint','runtime','missing','old_boot','old_time','stale_age','unasserted','clock_regression','missing_pins'])
def test_restart_blocks_stale_missing_or_mismatched_evidence(change):
    a=restart_args()
    if change=='checkpoint':a['expected_checkpoint']['head_sha256']='0'*64
    if change=='runtime':a['expected_runtime']={'untrusted':'source'}
    if change=='missing':a['fresh_observations'].pop('ACTUATOR')
    if change=='old_boot':a['fresh_observations']['POWER']['boot_id']='previous'
    if change=='old_time':a['fresh_observations']['STATE']['observed_ns']=99
    if change=='stale_age':a['now_ns']=200
    if change=='unasserted':a['fresh_observations']['CLOCK_MAP']['evidence_asserted']=False
    if change=='clock_regression':a['now_ns']=99
    if change=='missing_pins':a['actual_checkpoint']=a['expected_checkpoint']=None
    assert restart_check(**a)['status']=='RESTART_BLOCKED'


def test_successful_compute_is_one_shot_and_bound_to_result():
    guard=DeadlineGuard(boot_id='B',clock=clock([100,101,109]));budget=guard.begin(10);data={'value':1}
    r=guard.evaluate(budget,lambda:data)
    assert r['status']=='COMPUTED_WITHIN_BUDGET_NOT_DISPATCHED' and r['result_sha256']==sha(data)
    assert not r['actuation_dispatched']
    assert guard.evaluate(budget,lambda:data)['reason']=='UNKNOWN_OR_REUSED_BUDGET'


def test_expired_budget_prevents_computation():
    g=DeadlineGuard(boot_id='B',clock=clock([100,110]));b=g.begin(10);called=[]
    r=g.evaluate(b,lambda:called.append(1))
    assert not called and r['reason']=='DEADLINE_MISSED_BEFORE_COMPUTATION'


def test_late_completion_is_withheld_but_is_not_claimed_preempted():
    g=DeadlineGuard(boot_id='B',clock=clock([100,101,110]));b=g.begin(10);called=[]
    def computation():called.append(1);return {'synthetic':'result'}
    r=g.evaluate(b,computation)
    assert called==[1] and r['reason']=='DEADLINE_MISSED_AFTER_COMPUTATION' and r['result'] is None


def test_monotonic_regression_latches_clock_fault():
    g=DeadlineGuard(boot_id='B',clock=clock([100,101,99,102]));b=g.begin(10)
    assert g.evaluate(b,lambda:{})['reason']=='COMPUTATION_OR_CLOCK_FAILURE'
    with pytest.raises(ValueError):g.begin(10)


def test_computation_exception_does_not_release_result_or_renew_budget():
    g=DeadlineGuard(boot_id='B',clock=clock([100,101]));b=g.begin(10)
    def fail():raise RuntimeError('intentional pure computation failure')
    assert g.evaluate(b,fail)['result'] is None
    assert g.evaluate(b,lambda:{})['reason']=='UNKNOWN_OR_REUSED_BUDGET'


@pytest.mark.parametrize('change',['boot','start','deadline','boolean_start'])
def test_modified_or_foreign_budget_not_accepted(change):
    g=DeadlineGuard(boot_id='B',clock=clock([1]));b=g.begin(10)
    if change=='boot':b['boot_id']='other'
    if change=='start':b['start_ns']=2
    if change=='deadline':b['deadline_ns']=12
    if change=='boolean_start':b['start_ns']=True
    assert g.evaluate(b,lambda:{})['reason']=='UNKNOWN_OR_REUSED_BUDGET'


def test_actual_monotonic_clock_smoke_without_runtime_latency_claim():
    g=DeadlineGuard(boot_id='development-process');b=g.begin(1000000000)
    assert g.evaluate(b,lambda:{'pure':True})['status']=='COMPUTED_WITHIN_BUDGET_NOT_DISPATCHED'


def test_synthetic_calibration_consistency_is_never_hardware_validation():
    r=calibration_check(profile(),samples())
    assert r['status']=='WITHIN_DECLARED_ERROR_BOUNDS_NOT_VALIDATION'
    assert r['hardware_validation'] is False and r['independent_review'] is False


def test_point_error_witness_and_unevaluable_interval_case_differ():
    data=samples();data[0]['velocity']=['.52','.52'];r=calibration_check(profile(),data)
    assert r['status']=='ERROR_BOUND_NOT_ESTABLISHED' and r['point_violation_witnesses'][0]['error']=='1/50'
    data[0]['velocity']=['.48','.52'];r=calibration_check(profile(),data)
    assert r['status']=='ERROR_BOUND_NOT_ESTABLISHED' and r['point_violation_witnesses']==[]


@pytest.mark.parametrize('change',['empty','duplicate','reference','frame','authority'])
def test_missing_or_unsupported_calibration_cannot_be_promoted(change):
    p=profile();s=samples()
    if change=='empty':assert calibration_check(p,[])['status']=='UNKNOWN_CALIBRATION_EVIDENCE';return
    if change=='duplicate':s.append(deepcopy(s[0]))
    if change=='reference':s[0]['reference_id']='same-sensor-as-candidate'
    if change=='frame':s[0]['frame']='BODY_X'
    if change=='authority':p['classification']='HARDWARE_VALIDATED'
    with pytest.raises(ValueError):calibration_check(p,s)


def test_nominal_response_is_only_a_non_dispatchable_development_candidate():
    t,args=good_inputs();r=select_response(t,**args)
    assert r['status']=='DEVELOPMENT_RECOVERY_CANDIDATE_ONLY'
    assert r['dispatch'] is False and r['operational_authorization'] is False


@pytest.mark.parametrize('change',['deadline','wrong_result','restart','boot','calibration','unknown','prefix','terminal','authority','hardware'])
def test_response_selection_never_turns_missing_evidence_into_zero_or_brake(change):
    t,args=good_inputs()
    if change=='deadline':args['deadline']['status']='RESULT_WITHHELD'
    if change=='wrong_result':args['deadline']['result_sha256']='0'*64
    if change=='restart':args['restart']['status']='RESTART_BLOCKED'
    if change=='boot':args['boot_id']='other'
    if change=='calibration':args['calibration']['status']='UNKNOWN_CALIBRATION_EVIDENCE'
    if change=='unknown':t['status']='UNKNOWN_EVIDENCE'
    if change=='prefix':t['reaction_prefix_containment']=False
    if change=='terminal':t['assessment']['terminal_sample_condition']=False
    if change=='authority':t['operational_authorization']=True
    if change=='hardware':args['mode']='HARDWARE'
    if change in ('unknown','prefix','terminal','authority'):args['deadline']['result_sha256']=sha(t)
    r=select_response(t,**args)
    assert r['status']=='NO_JUSTIFIED_RESPONSE' and r['candidate'] is None and r['dispatch'] is False
