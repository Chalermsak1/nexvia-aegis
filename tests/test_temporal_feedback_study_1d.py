from copy import deepcopy
import json
import pytest
from scripts.research import temporal_feedback_study_1d as study
from scripts.research.development_ledger import DevelopmentLedger, LedgerWriteError


@pytest.mark.parametrize('a',study.plan(),ids=lambda a:a['id'])
def test_temporal_integration_design(a):
    before=deepcopy(a);events=[];result=study.run_case(a,emit=events.append);s=study.summarize(result)
    assert a==before and len(events)==2*len(a['operations'])
    assert not s['operational_authorization'] and s['action'] is None
    assert s['future_position_containment']=='NOT_ESTABLISHED'
    if a['id']=='nominal_zero_reaction':assert s['combined_finite_horizon_containment'] is True
    if a['id']=='reaction_latency_three_ticks':assert s['combined_finite_horizon_containment'] is False
    if a['id'] in ('sequence_body_equivocation','power_deadline_renewal_rejected','consumption_wrong_static_delay','consumption_after_power_flush','inconsistent_static_delays'):
        assert s['status']=='CONTRADICTORY_EVIDENCE'
    if a['id'] in ('receipt_clock_rollback','assessment_clock_rollback','record_budget_requires_resync','stream_budget_requires_resync'):
        assert s['status']=='SESSION_RESYNC_REQUIRED'
    if a['id'] in ('new_session_old_packet_rejected','excess_transport_latency','expired_state_budget'):
        assert s['status']=='UNKNOWN_EVIDENCE'
    if a['id']=='new_session_missing_actuator_history':
        last=result['responses'][-1]['result'];assert last['preparation']['snapshot']['force']==['-1','1']
    if a['id']=='orphan_consumption_then_history':
        assert any(row['result']['status']=='UNKNOWN_COMMAND_HISTORY' for row in result['responses'])
        assert s['status']=='READY_CONDITIONAL_INPUTS'
    if a['id']=='elapsed_time_is_not_execution_ack':
        assert all(c['status']=='EXECUTION_UNCONFIRMED' for c in s['command_tracking'].values())
    if a['id']=='consumed_command_replay_not_requeued':
        assert s['command_tracking']['c97']['status']=='ACKNOWLEDGED_CONSUMED_NOT_PHYSICAL_OUTCOME_PROOF'
        assert s['replays_ignored']==1
    if a['id']=='consumption_narrows_delay':assert s['recovery_analysis_branches']==1
    if a['id']=='unsafe_reaction_start_safe_effect':
        assert s['post_reaction_containment'] is True and s['reaction_prefix_containment'] is False
        assert s['combined_finite_horizon_containment'] is False


def test_complete_study_reconstruction_and_exclusive_paths(tmp_path):
    directory=tmp_path/'complete';r=study.run(directory)
    assert r==study.audit(directory)
    assert r['counts']==dict(ASSIGNED=0,STARTED=0,COMPLETED=24,ERROR=0)
    assert r['ledger_state']=='FINALIZED' and r['physics_steps']==0
    assert not r['unreferenced_result_files']
    with pytest.raises(FileExistsError):study.run(directory)


def test_result_bytes_and_sources_are_verified(tmp_path,monkeypatch):
    directory=tmp_path/'complete';study.run(directory)
    p=directory/'nominal_zero_reaction.json';original=p.read_bytes();p.write_bytes(original+b' ')
    with pytest.raises(ValueError,match='hash mismatch'):study.audit(directory)
    p.write_bytes(original)
    monkeypatch.setattr(study,'hashes',lambda:{'false':'0'*64})
    with pytest.raises(ValueError,match='source/runtime mismatch'):study.audit(directory)


def test_missing_final_keeps_all_completed_operations_incomplete(tmp_path):
    directory=tmp_path/'partial';study.run(directory)
    p=directory/'assignments.jsonl';p.write_bytes(b'\n'.join(p.read_bytes().splitlines()[:-1])+b'\n')
    r=study.audit(directory)
    assert r['counts']['COMPLETED']==24 and r['ledger_state']=='INCOMPLETE'


def test_analysis_error_keeps_remaining_assignments_unstarted(tmp_path,monkeypatch):
    monkeypatch.setattr(study,'run_case',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('intentional temporal analysis failure')))
    directory=tmp_path/'failure'
    with pytest.raises(RuntimeError):study.run(directory)
    r=study.audit(directory)
    assert r['counts']==dict(ASSIGNED=23,STARTED=0,COMPLETED=0,ERROR=1)
    assert all(a['summary'] is None for a in r['assignments'])


def test_post_ingest_sink_failure_retains_intent_and_unknown_outcome(tmp_path,monkeypatch):
    event=DevelopmentLedger.event;seen=[]
    def failed(self,assignment_id,*,details):
        if details['phase']=='OPERATION_RESULT':
            seen.append(details['status'])
            raise LedgerWriteError('intentional sink failure after in-memory state mutation')
        return event(self,assignment_id,details=details)
    monkeypatch.setattr(DevelopmentLedger,'event',failed)
    directory=tmp_path/'failure'
    with pytest.raises(LedgerWriteError):study.run(directory)
    r=study.audit(directory)
    assert seen==['ACCEPTED']
    assert r['counts']==dict(ASSIGNED=23,STARTED=1,COMPLETED=0,ERROR=0)
    assert all(a['summary'] is None for a in r['assignments'])


def test_terminal_failure_retains_unreferenced_raw_result(tmp_path,monkeypatch):
    monkeypatch.setattr(DevelopmentLedger,'complete',lambda *a,**kw:(_ for _ in ()).throw(LedgerWriteError('intentional terminal sink failure')))
    directory=tmp_path/'failure'
    with pytest.raises(LedgerWriteError):study.run(directory)
    r=study.audit(directory)
    assert r['counts']==dict(ASSIGNED=23,STARTED=1,COMPLETED=0,ERROR=0)
    assert r['unreferenced_result_files']==['nominal_zero_reaction.json']


def test_rewritten_hash_chain_cannot_replace_durable_operation_reconstruction(tmp_path):
    directory=tmp_path/'complete';study.run(directory)
    from scripts.research.development_ledger import _entry,_encode,ZERO_HASH
    p=directory/'assignments.jsonl';records=[json.loads(line)['payload'] for line in p.read_bytes().splitlines()]
    for row in records:
        if row['kind']=='EVENT' and row['details']['phase']=='OPERATION_RESULT':
            row['details']['status']='REPLAY_IGNORED';break
    encoded=[];previous=ZERO_HASH
    for index,payload in enumerate(records):
        entry=_entry(index,previous,payload);encoded.append(_encode(entry)+b'\n');previous=entry['sha256']
    p.write_bytes(b''.join(encoded))
    with pytest.raises(ValueError,match='durable operations mismatch'):study.audit(directory)
