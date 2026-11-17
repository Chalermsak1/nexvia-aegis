from copy import deepcopy
from pathlib import Path
import json,shutil
import pytest
from aegis.development import live_recovery_contract as c
from aegis.development.live_recovery_processes import write_beacon
from aegis.development.restart_process_experiment import obs
from scripts.research.live_recovery_study import public_for


def fixture(tmp_path,*,arm='SIMULATION_CONTRACT_CHECKS',clock=None,finish=1010000000,sample_update=None,mode='SNAPSHOT_SAME_TICK'):
    root=tmp_path/'run';root.mkdir();public=public_for(dict(id='unit',arm=arm,steps=80,wall_period=.03,assessment_mode=mode),sources={});write_beacon(root,public,0,'sensor-0')
    sample=dict(id='sensor-0:0',tick=0,remote_time=1000,remote_epoch='sensor-0',clock_offset_ms=1000,source_id='SYNTHETIC_MEASURED_CHANNEL',frame='WORLD_X_SI',position_center='0',velocity_center='.3',emitted_host_ns=1000000000,reported_dynamics_id=public['model']['dynamics_id'],support_valid=True,topology=dict(controller=11,watchdog=12,plant=13),**obs(0,.3))
    sample.update(sample_update or {})
    times=iter([1000000000,finish]);kwargs={} if clock is None else dict(clock=clock)
    basis=c.assess_frame(root,'watchdog-0/assessments/00000000',sample,public,'watchdog-0',primary_healthy=True,controller_generation=0,host_clock=lambda:next(times),**kwargs)
    return root,public,sample,basis


def lease_fixture(tmp_path):
    root,p,s,b=fixture(tmp_path);assert b['reason'] is None
    lease=c.make_lease(b,'watchdog-0/assessments/00000000',p,generation=0,seq=1)
    args=dict(now_tick=1,now_host_ns=lease['issued_host_ns']+1,controller_generation=0,watchdog_generation=0,source_epoch='sensor-0',public_sha256=c.sha(p),revoked_seq=-1,primary_power=True,recovery_latched=False)
    return root,p,s,b,lease,args


def test_supported_live_frame_remains_conditional_and_immutable(tmp_path):
    root,p,s,b,lease,args=lease_fixture(tmp_path)
    assert c.lease_check(lease,**args)['allowed'] and c.load_basis(root,lease)==b
    assert b['future_physical_assumptions']==list(c.ASSUMED)
    assert not b['operational_authorization'] and not b['hardware_validation'] and not b['independent_attestation']


def test_strict_arm_preserves_unmeasured_future_properties_as_assertions(tmp_path):
    root,p,s,b=fixture(tmp_path,arm='STRICT_OBSERVATIONS')
    assert b['result']['development_action'] is None
    assert all(x['kind']=='ASSERTED' for x in b['provenance'] if x['premise'] in c.ASSUMED)


@pytest.mark.parametrize('key,value',[('now_tick',6),('controller_generation',1),('watchdog_generation',1),('source_epoch','sensor-1'),('public_sha256','0'*64),('revoked_seq',1),('primary_power',False),('recovery_latched',True),('now_tick',True)])
def test_issue_or_consumption_rejects_each_invalid_dimension(tmp_path,key,value):
    _,_,_,_,lease,args=lease_fixture(tmp_path);args[key]=value
    assert not c.lease_check(lease,**args)['allowed']


def test_exact_native_expiry_and_one_tick_before_are_distinct(tmp_path):
    _,_,_,_,lease,args=lease_fixture(tmp_path)
    args['now_host_ns']=lease['expires_host_ns']-1;assert c.lease_check(lease,**args)['allowed']
    args['now_host_ns']+=1;assert not c.lease_check(lease,**args)['allowed']


def test_new_lease_cannot_extend_an_old_command_lease(tmp_path):
    _,_,_,b,old,args=lease_fixture(tmp_path)
    newer=dict(old,id='w0:2',seq=2,issued_tick=2,expires_tick=8)
    args['now_tick']=6
    assert c.lease_check(newer,**args)['allowed'] and not c.lease_check(old,**args)['allowed']


def test_plant_clock_advancement_during_computation_withholds(tmp_path):
    calls=[]
    def clock(root):
        b=c.read_beacon(root);calls.append(1)
        if len(calls)>1:b['tick']=1
        return b
    _,_,_,b=fixture(tmp_path,clock=clock)
    assert b['reason']=='PLANT_CLOCK_ADVANCED_OR_RESET'
    with pytest.raises(ValueError):c.make_lease(b,'watchdog-0/assessments/00000000',{},generation=0,seq=1)


def test_clock_reader_failure_is_preserved_without_candidate(tmp_path):
    def broken(root):raise OSError('synthetic disconnected clock')
    root,_,_,b=fixture(tmp_path,clock=broken)
    assert b['reason']=='COLLECTOR_OR_ASSESSMENT_FAILURE' and b['result'] is None
    assert (root/'watchdog-0/assessments/00000000/result.json').exists()


def test_computation_budget_boundary_is_withheld(tmp_path):
    _,_,_,b=fixture(tmp_path,finish=1025000000)
    assert b['reason']=='NATIVE_COMPUTATION_BUDGET_EXCEEDED'


def test_rehashed_foreign_authority_is_rejected(tmp_path):
    root,_,_,b,lease,_=lease_fixture(tmp_path);shutil.copytree(root,tmp_path/'original')
    b['result']['operational_authorization']=True;path=root/lease['basis_path'];path.write_bytes(c.canonical(b)+b'\n');lease['basis_sha256']=c.sha(b)
    with pytest.raises(ValueError,match='authority'):c.load_basis(root,lease)


def test_basis_path_traversal_is_rejected(tmp_path):
    root,_,_,_,lease,_=lease_fixture(tmp_path);lease['basis_path']='../outside.json'
    with pytest.raises(ValueError,match='path'):c.load_basis(root,lease)


def test_late_ack_cannot_downgrade_terminal_effect(tmp_path):
    b=c.EffectBeliefs();b.merge('id','UNKNOWN');b.merge('id','QUEUED');b.merge('id','CONSUMED')
    assert b.merge('id','QUEUED')=='CONSUMED'
    assert b.merge('id','REJECTED_AT_CONSUMPTION')=='EFFECT_UNCERTAIN'


def test_malformed_effect_status_remains_uncertain():
    b=c.EffectBeliefs()
    assert b.merge('id',{'bad':'status'})=='EFFECT_UNCERTAIN'


def test_transient_contradiction_is_not_masked_by_clock_advancement(tmp_path):
    calls=[]
    def advancing(root):
        b=c.read_beacon(root);calls.append(1)
        if len(calls)>1:b['tick']=1
        return b
    _,_,_,basis=fixture(tmp_path,clock=advancing,sample_update=dict(reported_dynamics_id='BAD_MODEL'))
    assert basis['reason']=='CONTRADICTORY_OR_INVALID_EVIDENCE'


def test_rehashed_outer_authority_metadata_is_rejected(tmp_path):
    root,_,_,basis,lease,_=lease_fixture(tmp_path);shutil.copytree(root,tmp_path/'original')
    basis['hardware_validation']=True;(root/lease['basis_path']).write_bytes(c.canonical(basis)+b'\n');lease['basis_sha256']=c.sha(basis)
    with pytest.raises(ValueError,match='authority|scope'):c.load_basis(root,lease)


def test_publisher_cannot_backdate_a_lease_before_assessment_completion(tmp_path):
    _,public,_,basis,_,_=lease_fixture(tmp_path)
    with pytest.raises(ValueError,match='time|publication'):c.make_lease(basis,'watchdog-0/assessments/00000000',public,generation=0,seq=2,issue_host_ns=basis['finish_host_ns']-1)


def test_explicit_uncertain_effect_report_remains_uncertain():
    b=c.EffectBeliefs();b.merge('id','CONSUMED')
    assert b.merge('id','EFFECT_UNCERTAIN')=='EFFECT_UNCERTAIN'


@pytest.mark.parametrize('target',['bad','nan','1e9999999','1/0',{},True,'9'*100,'-Infinity'])
def test_invalid_command_arithmetic_is_rejected_before_queueing(target):
    message=dict(kind='COMMAND',command_id='c0:1',generation=0,lease_id='w0:1',basis_sha256='0'*64,target=target,reply='/private/tmp/unit.sock')
    assert not c.command_check(message,expected_reply='/private/tmp/unit.sock')['valid']


def test_valid_command_rational_remains_unchanged():
    message=dict(kind='COMMAND',command_id='c0:1',generation=0,lease_id='w0:1',basis_sha256='0'*64,target='-3/5',reply='/private/tmp/unit.sock');before=deepcopy(message)
    assert c.command_check(message,expected_reply='/private/tmp/unit.sock')['valid'] and message==before


def test_old_watchdog_basis_cannot_be_republished_as_new_generation(tmp_path):
    _,public,_,basis,_,_=lease_fixture(tmp_path)
    with pytest.raises(ValueError,match='generation'):c.make_lease(basis,'watchdog-0/assessments/00000000',public,generation=1,seq=1)


def test_backlog_coalescing_cannot_hide_an_older_contradiction(tmp_path):
    _,public,sample,_=fixture(tmp_path)
    bad=dict(sample,reported_dynamics_id='BAD_MODEL');newer=dict(sample,id='sensor-0:1',tick=1,remote_time=1020)
    r=c.select_samples([bad,newer],seen=-1,known={},public=public)
    assert r['critical']=='REPORTED_MODEL_CONTRADICTION' and r['selected']==bad


def test_backlog_selects_latest_valid_sample_without_refreshing_old_data(tmp_path):
    _,public,sample,_=fixture(tmp_path);newer=dict(sample,id='sensor-0:1',tick=1,remote_time=1020)
    r=c.select_samples([sample,newer],seen=-1,known={},public=public)
    assert r['selected']==newer and r['critical'] is None
    assert any(e['kind']=='FEEDBACK_SUPERSEDED' and e['sample_id']==sample['id'] for e in r['events'])


def test_changed_replayed_packet_identity_is_a_material_fault(tmp_path):
    _,public,sample,_=fixture(tmp_path);changed=dict(sample,position_center='.01')
    r=c.select_samples([changed],seen=sample['tick'],known={sample['id']:c.sha(sample)},public=public)
    assert r['critical']=='SAMPLE_ID_CONFLICT' and r['selected'] is None


@pytest.mark.parametrize('advance',[1,2])
def test_time_tube_checks_actual_advance_instead_of_freezing_clock(tmp_path,advance):
    calls=[]
    def advancing(root):
        b=c.read_beacon(root);calls.append(1)
        if len(calls)>1:b['tick']=advance
        return b
    _,_,_,basis=fixture(tmp_path,mode='STATE_TUBE_WINDOW_V1',clock=advancing)
    assert basis['beacon_after']['tick']==advance
    assert (basis['reason'] is None)==(advance==1)


def test_time_tube_encloses_independent_exact_bounded_acceleration_paths(tmp_path):
    from fractions import Fraction as Q
    from itertools import product
    from aegis.development.recovery_feedback_state_1d import _bounds
    _,public,sample,basis=fixture(tmp_path,mode='STATE_TUBE_WINDOW_V1')
    a=c.input_bundle(sample,basis['beacon_before'],public,'watchdog-0',primary_healthy=True);p,v=_bounds(a['packet']['position']),_bounds(a['packet']['velocity'])
    for mass,force,w in product((Q('.9'),Q('1.1')),(-Q(1),Q(1)),(-Q('.01'),Q('.01'))):
        for n in range(41):
            t=Q(n,1000);acc=(force+w)/mass
            assert p.contains(Q('.3')*t+acc*t*t/2) and v.contains(Q('.3')+acc*t)
    assert a['now_local']==0 and basis['time_basis']['source_host_ns']==sample['emitted_host_ns']


def test_time_tube_does_not_refresh_a_stale_source(tmp_path):
    def stale(root):
        b=c.read_beacon(root);b['tick']=4;return b
    _,_,_,basis=fixture(tmp_path,mode='STATE_TUBE_WINDOW_V1',clock=stale)
    assert basis['result'] is None and basis['reason']=='COLLECTOR_OR_ASSESSMENT_FAILURE'


def test_time_tube_preserves_native_deadline_and_strict_assertions(tmp_path):
    _,_,_,basis=fixture(tmp_path,mode='STATE_TUBE_WINDOW_V1',finish=1025000000)
    assert basis['reason']=='NATIVE_COMPUTATION_BUDGET_EXCEEDED'
    other=tmp_path/'strict';other.mkdir();_,_,_,strict=fixture(other,mode='STATE_TUBE_WINDOW_V1',arm='STRICT_OBSERVATIONS')
    assert strict['result']['development_action'] is None


def test_atomic_bundle_preserves_exact_ea01_semantics_and_checkpoint(tmp_path):
    from aegis.development.live_evidence_bundle import FrameTransaction,BundleReplay
    from aegis.development.recovery_evidence import EvidenceJournal
    from scripts.research import evidence_recovery_study as prior
    statement=__import__('aegis.development.evidence_recovery',fromlist=['statement_for']).statement_for(prior.inputs())
    with EvidenceJournal.create(tmp_path/'per_record',policy=prior.policy(),boot_id='boot-A',clock_domain='local-A',now=100) as old, FrameTransaction(policy=prior.policy(),boot_id='boot-A',clock_domain='local-A',now=100) as new:
        for row in prior.artifacts():assert old.submit(row,now=100)==new.submit(row,now=100)
        expected=old.evaluate(statement,now=100);assert new.evaluate(statement,now=100)==expected
        new.persist(tmp_path/'bundle.json')
    assert BundleReplay(tmp_path/'bundle.json').evaluate(statement,now=100)==expected


def test_bundle_commit_failure_preserves_pending_bytes_and_cannot_publish(tmp_path,monkeypatch):
    import os
    from aegis.development.live_evidence_bundle import FrameTransaction
    from scripts.research import evidence_recovery_study as prior
    journal=FrameTransaction(policy=prior.policy(),boot_id='boot-A',clock_domain='local-A',now=100)
    def fail(*args):raise OSError('synthetic link failure')
    monkeypatch.setattr(os,'link',fail)
    with pytest.raises(OSError):journal.persist(tmp_path/'bundle.json')
    assert journal.closed and not (tmp_path/'bundle.json').exists() and (tmp_path/'pending_bundle.json').exists()
    with pytest.raises(ValueError):journal.persist(tmp_path/'bundle.json')


def test_rehashed_bundle_predicate_tampering_is_rejected(tmp_path):
    from aegis.development.live_evidence_bundle import FrameTransaction,BundleReplay
    from scripts.research import evidence_recovery_study as prior
    from aegis.development.evidence_recovery import statement_for
    with FrameTransaction(policy=prior.policy(),boot_id='boot-A',clock_domain='local-A',now=100) as j:
        for row in prior.artifacts():j.submit(row,now=100)
        j.evaluate(statement_for(prior.inputs()),now=100);j.persist(tmp_path/'bundle.json')
    shutil.copyfile(tmp_path/'bundle.json',tmp_path/'original_bundle.json');b=json.loads((tmp_path/'bundle.json').read_bytes());previous='0'*64
    for record in b['records']:
        if record['payload'].get('kind')=='ARTIFACT' and record['payload']['artifact']['premise']=='state_bounds_asserted':record['payload']['artifact']['observations'][0]='999'
        record['previous']=previous;record['sha256']=c.sha({k:record[k] for k in ('seq','previous','payload')});previous=record['sha256']
    b['checkpoint']['head_sha256']=previous;(tmp_path/'bundle.json').write_bytes(c.canonical(b)+b'\n')
    with pytest.raises(ValueError,match='vector'):BundleReplay(tmp_path/'bundle.json')
