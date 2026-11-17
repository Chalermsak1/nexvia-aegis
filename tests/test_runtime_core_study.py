from copy import deepcopy
import hashlib
import json
import pytest
from scripts.research import runtime_core_study as study
from scripts.research.development_ledger import DevelopmentLedger,LedgerWriteError


@pytest.mark.parametrize('a',study.plan(),ids=lambda a:a['id'])
def test_all_runtime_designs_and_readonly_original_store_audit(a,tmp_path):
    before=deepcopy(a);events=[];r=study.run_case(a,tmp_path/'case',emit=events.append)
    assert before==a
    assert study.audit_case(a,r,tmp_path/'case',tmp_path/'audit')==events
    s=study.summary(r)
    assert not s['dispatch'] and not s['hardware_validation'] and not s['operational_authorization']
    if a['id'] in ('nominal_candidate','restart_replay'):assert s['response']=='DEVELOPMENT_RECOVERY_CANDIDATE_ONLY'
    else:assert s['response']=='NO_JUSTIFIED_RESPONSE'
    if a['id']=='restart_replay':assert s['replay_status']=='REPLAY_IGNORED'
    if a['id']=='asymmetric_clock':assert r['mapping']['local_interval']==['90','110'] and r['temporal']['status']=='UNKNOWN_EVIDENCE'
    if a['id']=='deadline_before_compute':assert r['temporal'] is None and s['durable_operations']==6
    if a['id']=='deadline_after_compute':assert r['temporal'] is not None and r['deadline']['result'] is None
    if a['id']=='unsafe_recovery_prefix':assert r['temporal']['assessment']['finite_horizon_containment'] is True and s['combined_containment'] is False


def test_full_study_and_audit_never_overwrite_or_mutate_original_stores(tmp_path):
    path=tmp_path/'run';study.run(path)
    before={str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}
    r=study.audit(path,tmp_path/'audit')
    assert r['ledger_state']=='FINALIZED' and r['counts']==dict(ASSIGNED=0,STARTED=0,COMPLETED=14,ERROR=0)
    assert before=={str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}
    with pytest.raises(FileExistsError):study.run(path)
    with pytest.raises(FileExistsError):study.audit(path,tmp_path/'audit')


def test_changed_closed_sqlite_evidence_is_rejected_before_open(tmp_path):
    a=study.plan()[0];r=study.run_case(a,tmp_path/'case');db=tmp_path/'case/store/state.sqlite'
    with db.open('ab') as f:f.write(b'corruption')
    with pytest.raises(ValueError,match='hash mismatch'):study.audit_case(a,r,tmp_path/'case',tmp_path/'audit')


def test_source_pin_change_refuses_audit(tmp_path,monkeypatch):
    path=tmp_path/'run';study.run(path);monkeypatch.setattr(study,'hashes',lambda:{'false':'pin'})
    with pytest.raises(ValueError,match='source/runtime'):study.audit(path,tmp_path/'audit')


def test_analysis_error_retains_unstarted_assignments(tmp_path,monkeypatch):
    monkeypatch.setattr(study,'run_case',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('intentional runtime study error')))
    path=tmp_path/'failed'
    with pytest.raises(RuntimeError):study.run(path)
    r=study.audit(path,tmp_path/'audit')
    assert r['counts']==dict(ASSIGNED=13,STARTED=0,COMPLETED=0,ERROR=1)


def test_post_commit_ledger_sink_failure_keeps_unknown_outcome_and_database(tmp_path,monkeypatch):
    event=DevelopmentLedger.event
    def failed(self,name,*,details):
        if details['phase']=='DURABLE_OPERATION_RESULT':raise LedgerWriteError('intentional sink failure after SQLite commit')
        return event(self,name,details=details)
    monkeypatch.setattr(DevelopmentLedger,'event',failed);path=tmp_path/'failed'
    with pytest.raises(LedgerWriteError):study.run(path)
    assert (path/'nominal_candidate/store/state.sqlite').exists()
    r=study.audit(path,tmp_path/'audit')
    assert r['counts']==dict(ASSIGNED=13,STARTED=1,COMPLETED=0,ERROR=0)
    assert all(a['summary'] is None for a in r['assignments'])


def test_missing_final_keeps_completed_store_work_incomplete(tmp_path):
    path=tmp_path/'run';study.run(path);p=path/'assignments.jsonl'
    p.write_bytes(b'\n'.join(p.read_bytes().splitlines()[:-1])+b'\n')
    r=study.audit(path,tmp_path/'audit')
    assert r['counts']['COMPLETED']==14 and r['ledger_state']=='INCOMPLETE'


def test_rewritten_unkeyed_ledger_cannot_replace_expected_commit_events(tmp_path):
    path=tmp_path/'run';study.run(path)
    from scripts.research.development_ledger import _entry,_encode,ZERO_HASH
    p=path/'assignments.jsonl';records=[json.loads(line)['payload'] for line in p.read_bytes().splitlines()]
    for record in records:
        if record['kind']=='EVENT' and record['details']['phase']=='DURABLE_OPERATION_RESULT':record['details']['result_sha256']='0'*64;break
    previous=ZERO_HASH;data=[]
    for index,payload in enumerate(records):
        entry=_entry(index,previous,payload);data.append(_encode(entry)+b'\n');previous=entry['sha256']
    p.write_bytes(b''.join(data))
    with pytest.raises(ValueError,match='intent/result'):study.audit(path,tmp_path/'audit')
