import copy
import json
import pytest
from scripts.research import recovery_feedback_study_1d as study
from scripts.research.development_ledger import DevelopmentLedger, LedgerWriteError


@pytest.mark.parametrize('a',study.plan(),ids=lambda a:a['id'])
def test_fixed_counterexamples_and_unknowns(a):
    before=copy.deepcopy(a);result=study.run_case(a);summary=study.summarize(result)
    assert a==before and not summary['operational_authorization']
    assert summary['action'] is None and summary['future_position_containment']=='NOT_ESTABLISHED'
    if a['id']=='fresh_reset_feedback':assert summary['finite_horizon_containment'] is True
    if a['id'] in ('acknowledged_pending_acceleration','missing_all_acknowledgements','missing_current_force','expired_power_deadline'):
        assert summary['finite_horizon_containment'] is False
    if a['id'].startswith('conflicting_'):assert summary['conclusion']=='CONTRADICTORY_EVIDENCE'
    if a['id']=='force_conflicts_with_expired_power':assert summary['conclusion']=='CONTRADICTORY_EVIDENCE'
    if a['id'] in ('missing_state_observation','missing_power_evidence','unknown_evidence'):
        assert summary['conclusion']=='UNKNOWN_EVIDENCE'
    if a['id'] in ('incompatible_clock','future_receipt'):assert summary['conclusion']=='UNKNOWN_INPUT'
    if a['id']=='unasserted_ack_semantics':assert summary['conclusion']=='UNKNOWN_PHYSICAL_PREMISES'


def test_batch_reconstruction_and_no_overwrite(tmp_path):
    path=tmp_path/'batch';result=study.run(path)
    assert result==study.audit(path)
    assert result['counts']==dict(ASSIGNED=0,STARTED=0,COMPLETED=18,ERROR=0)
    assert result['ledger_state']=='FINALIZED' and result['physics_steps']==0
    assert not result['unreferenced_result_files']
    with pytest.raises(FileExistsError):study.run(path)


def test_corrupt_result_rejected(tmp_path):
    path=tmp_path/'batch';study.run(path)
    p=path/'fresh_reset_feedback.json';p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ValueError,match='hash mismatch'):study.audit(path)


def test_changed_sources_rejected(tmp_path,monkeypatch):
    path=tmp_path/'batch';study.run(path)
    monkeypatch.setattr(study,'hashes',lambda:{'false':'0'*64})
    with pytest.raises(ValueError,match='source/runtime mismatch'):study.audit(path)


def test_missing_final_record_never_becomes_complete(tmp_path):
    path=tmp_path/'batch';study.run(path)
    p=path/'assignments.jsonl';p.write_bytes(b'\n'.join(p.read_bytes().splitlines()[:-1])+b'\n')
    result=study.audit(path)
    assert result['ledger_state']=='INCOMPLETE' and result['counts']['COMPLETED']==18


def test_analysis_failure_retained_without_rerun(tmp_path,monkeypatch):
    monkeypatch.setattr(study,'run_case',lambda a:(_ for _ in ()).throw(RuntimeError('intentional synthetic analysis failure')))
    path=tmp_path/'failed'
    with pytest.raises(RuntimeError):study.run(path)
    result=study.audit(path)
    assert result['counts']==dict(ASSIGNED=17,STARTED=0,COMPLETED=0,ERROR=1)
    assert result['ledger_state']=='INCOMPLETE'


def test_post_analysis_terminal_write_failure_remains_unknown(tmp_path,monkeypatch):
    monkeypatch.setattr(DevelopmentLedger,'complete',lambda *a,**kw:(_ for _ in ()).throw(LedgerWriteError('intentional terminal sink failure')))
    path=tmp_path/'partial'
    with pytest.raises(LedgerWriteError):study.run(path)
    result=study.audit(path)
    assert result['counts']==dict(ASSIGNED=17,STARTED=1,COMPLETED=0,ERROR=0)
    assert result['unreferenced_result_files']==['fresh_reset_feedback.json']
    assert result['assignments'][0]['summary'] is None


def test_semantically_changed_derived_summary_rejected(tmp_path,monkeypatch):
    # Even a newly self-consistent unkeyed chain cannot replace recomputation.
    path=tmp_path/'batch';study.run(path)
    from scripts.research.development_ledger import _entry, _encode, ZERO_HASH
    p=path/'assignments.jsonl';rows=[json.loads(line)['payload'] for line in p.read_bytes().splitlines()]
    for row in rows:
        if row['kind']=='TERMINAL' and row['status']=='COMPLETED':
            row['details']['summary']['finite_horizon_containment']=not row['details']['summary']['finite_horizon_containment'];break
    raw=[];previous=ZERO_HASH
    for index,payload in enumerate(rows):
        entry=_entry(index,previous,payload);raw.append(_encode(entry)+b'\n');previous=entry['sha256']
    p.write_bytes(b''.join(raw))
    with pytest.raises(ValueError,match='reconstructed output/summary mismatch'):study.audit(path)
