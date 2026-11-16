from copy import deepcopy
import pytest
from scripts.research import freshness_lease_study as study
from scripts.research.development_ledger import DevelopmentLedger, LedgerWriteError, inspect


@pytest.fixture(scope='module')
def complete(tmp_path_factory):
    path = tmp_path_factory.mktemp('freshness_lease') / 'all.jsonl'
    result = study.run(path)
    return path, result


def rows(complete, case, arm):
    return [a['summary'] for a in complete[1]['assignments'] if a['id'].endswith(':'+case+':'+arm)]


def test_fixed_plan_and_all_physics_preserved(complete):
    assert len(study.plan()) == 117
    r = complete[1]; assert r['ledger_state'] == 'FINALIZED' and r['counts']['COMPLETED'] == 117
    assert len(r['matched_triples']) == 39
    assert all(v['status'] == 'MATCHED_RESET_RUNTIME_NOISE_ONLY' for v in r['matched_triples'])
    assert all(v['summary']['physics_steps'] == 80 for v in r['assignments'])


@pytest.mark.parametrize('case', ['retimed_cache','payload_substitution'])
def test_capture_witness_rejects_retime_or_substitution_at_fault_onset(complete, case):
    r = rows(complete,case,'WITNESS_LEASE')
    assert all(v['first_fallback_request_step'] == 6 and v['freshness_rejected_ticks'] == 74 for v in r)
    assert all(v['expired_lease_force_ticks'] == 0 and v['positive_command_power_ticks'] == 0 for v in r)


def test_controller_stall_expires_lease_before_any_stale_interval(complete):
    base = rows(complete,'controller_stall','DUAL_HOLD')
    assert all(r['expired_lease_force_ticks'] == 74 and r['first_fallback_request_step'] is None for r in base)
    for arm in ('LEASE','WITNESS_LEASE'):
        r = rows(complete,'controller_stall',arm)
        assert all(v['first_fallback_request_step'] == 6 and v['expired_lease_force_ticks'] == 0 for v in r)


@pytest.mark.parametrize('case', ['long_lease','watchdog_clock_freeze'])
def test_bad_lease_or_clock_requests_fallback_at_first_bad_tick(complete, case):
    assert all(v['first_fallback_request_step'] == 6 for v in rows(complete,case,'WITNESS_LEASE'))


@pytest.mark.parametrize('case', ['shared_reverse','compromised_witness'])
def test_witness_and_lease_cannot_detect_joint_trust_or_semantic_failure(complete, case):
    r = rows(complete,case,'WITNESS_LEASE')
    assert all(v['freshness_rejected_ticks'] == 0 and v['first_fallback_request_step'] is None for v in r)
    assert all(v['positive_command_power_ticks'] > 0 for v in r)


def test_shared_scheduler_failure_is_preserved_in_all_arms(complete):
    for arm in study.ARMS:
        r = rows(complete,'shared_scheduler_stall',arm)
        assert all(v['expired_lease_force_ticks'] == 74 and v['first_fallback_request_step'] is None for v in r)
        assert all(v['geometric_or_contact_violation_samples'] > 0 for v in r)


def test_unavailable_brake_and_saturation_are_not_success_labels(complete):
    assert all(v['unavailable_brake_ticks'] > 0 for v in rows(complete,'brake_unavailable','WITNESS_LEASE'))
    weak = rows(complete,'limited_brake_disturbance','WITNESS_LEASE')
    strong = rows(complete,'persistent_disturbance','WITNESS_LEASE')
    assert all(w['brake_saturation_ticks'] > 0 for w in weak)
    assert all(w['final_sampled_speed_m_s'] > s['final_sampled_speed_m_s'] for w,s in zip(weak,strong))


def test_contact_invalidates_the_sampled_free_mass_reference(complete):
    r = rows(complete,'mass_gravity_offset','WITNESS_LEASE')
    assert all(v['contact_samples'] > 0 for v in r)
    assert all(v['design_reference_evaluation'] == 'UNEVALUABLE_CONTACT' and v['path_exceeds_design_bound'] is None for v in r)


def test_saved_reader_and_exclusive_outputs(complete):
    path,r = complete
    assert study.audit(path) == r
    before = path.read_bytes()
    with pytest.raises(FileExistsError): study.run(path)
    assert path.read_bytes() == before


@pytest.fixture(scope='module')
def episode(complete):
    log = inspect(complete[0]); a = next(v for v in log['records'][0]['assignments'] if v['id'] == 'v0:controller_stall:WITNESS_LEASE')
    ev = [r['details'] for r in log['records'] if r['kind']=='EVENT' and r['id']==a['id']]
    t = next(r['details'] for r in log['records'] if r['kind']=='TERMINAL' and r['id']==a['id'])
    return a,ev,t


@pytest.mark.parametrize('defect',['capture_hash','receipt','lease','watchdog','gain','force','phase','noise','impulse','contact','summary','missing_physics','source','xml','compiled_geometry','native_gain'])
def test_reader_rejects_contradictions(episode,defect):
    a,original,terminal=episode; ev,t=deepcopy(original),deepcopy(terminal)
    tick,physics=ev[1],ev[2]
    if defect=='capture_hash':tick['logic']['capture_receipts'][0]['payload_sha256']='0'*64
    elif defect=='receipt':tick['logic']['deliveries'][0]['receipt_id']='missing'
    elif defect=='lease':tick['logic']['lease_submitted']['expires_tick']+=1
    elif defect=='watchdog':ev[1+2*6]['logic']['watchdog']['fallback_requested']=False
    elif defect=='gain':ev[1+2*9]['logic']['brake_gain']=0.
    elif defect=='force':tick['plant']['actuator_force_pre_n'][0]+=1
    elif defect=='phase':tick['plant']['phase']='POST_INTEGRATION'
    elif defect=='noise':tick['noise'][0]['velocity'][0]+=.01
    elif defect=='impulse':physics['velocity'][0]+=.01
    elif defect=='contact':tick['contact_before_floor']=True
    elif defect=='summary':t['summary']['expired_lease_force_ticks']+=1
    elif defect=='missing_physics':ev.pop(2)
    elif defect=='xml':ev[0]['runtime']['xml_sha256']='0'*64
    elif defect=='compiled_geometry':ev[0]['runtime']['geometry_positions'][0][0]+=.1
    elif defect=='native_gain':tick['plant']['native_gain'][0]+=1
    else:t['sources_after']={}
    with pytest.raises(ValueError):study.audit_episode(a,ev,t,a['metadata'])


def test_valid_hash_chain_with_false_watchdog_record_rejects(episode,tmp_path):
    a,ev,t=episode;ev=deepcopy(ev);ev[1+2*6]['logic']['watchdog']['force_n']=[-2.,0.,0.]
    path=tmp_path/'false_guard.jsonl'
    with DevelopmentLedger.create(path,study=study.STUDY,assignments=[dict(p,metadata=a['metadata']) for p in study.plan()],record_events=True) as w:
        w.start(a['id'])
        for e in ev:w.event(a['id'],details=e)
        w.complete(a['id'],status='COMPLETED',details=t)
    with pytest.raises(ValueError):study.audit(path)


def test_failed_sink_preserves_started_and_does_not_integrate(tmp_path,monkeypatch):
    path=tmp_path/'sink_failure.jsonl';original=DevelopmentLedger.event
    def fail(self,identifier,*,details):
        if details['type']=='TICK':raise LedgerWriteError('synthetic sink failure')
        return original(self,identifier,details=details)
    monkeypatch.setattr(DevelopmentLedger,'event',fail)
    with pytest.raises(LedgerWriteError):study.run(path)
    r=study.audit(path)
    assert r['counts']=={'ASSIGNED':116,'STARTED':1,'COMPLETED':0,'ERROR':0}
    assert [r['details']['type'] for r in inspect(path)['records'] if r['kind']=='EVENT']==['RESET']


def test_failed_simulator_retains_error_and_unstarted_work(tmp_path,monkeypatch):
    path=tmp_path/'sim_failure.jsonl'
    def fail(a,emit):raise RuntimeError('synthetic unavailable simulator')
    monkeypatch.setattr(study,'run_episode',fail)
    with pytest.raises(RuntimeError):study.run(path)
    r=study.audit(path)
    assert r['counts']=={'ASSIGNED':116,'STARTED':0,'COMPLETED':0,'ERROR':1}
    assert all(v['status']=='UNEVALUABLE_INCOMPLETE' for v in r['matched_triples'])
