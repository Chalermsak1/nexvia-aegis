import json
import pytest
from scripts.research import backup_parameter_uncertainty_study as study


def test_twenty_designs_are_explicit_synthetic_and_deterministic():
    assert len(study.plan())==20 and study.plan()==study.plan()
    assert len({a['id'] for a in study.plan()})==20


def test_exclusive_completed_study_reconstructs_and_never_claims_native_or_hardware(tmp_path):
    directory=tmp_path/'batch';r=study.run(directory)
    assert r==study.audit(directory)
    assert r['counts']==dict(ASSIGNED=0,STARTED=0,COMPLETED=20,ERROR=0)
    assert r['physics_steps']==0 and not r['operational_authorization'] and not r['independent_hardware_validation']
    assert len(r['categories'])==3
    with pytest.raises(FileExistsError):study.run(directory)


@pytest.mark.parametrize('change',['result','missing_result','sources','plan'])
def test_changed_study_evidence_rejected(change,tmp_path,monkeypatch):
    directory=tmp_path/'batch';study.run(directory)
    if change=='result':(directory/'symmetric_width_0.json').write_text('{}\n')
    if change=='missing_result':(directory/'symmetric_width_0.json').unlink()
    if change=='sources':monkeypatch.setattr(study,'hashes',lambda:{})
    if change=='plan':monkeypatch.setattr(study,'plan',lambda:[])
    with pytest.raises((ValueError,FileNotFoundError)):study.audit(directory)


def test_failed_assignment_is_not_retried_or_promoted_to_complete(tmp_path,monkeypatch):
    monkeypatch.setattr(study,'certificate',lambda *a:(_ for _ in ()).throw(RuntimeError('intentional failure')))
    directory=tmp_path/'failed'
    with pytest.raises(RuntimeError):study.run(directory)
    r=study.audit(directory)
    assert r['ledger_state']=='INCOMPLETE' and r['counts']==dict(ASSIGNED=19,STARTED=0,COMPLETED=0,ERROR=1)
    assert not r['categories'] and all(a['result'] is None for a in r['assignments'])


@pytest.mark.parametrize('key,value',[('gate_b','AUTHORIZED'),('physics_steps',1),('physics_steps',False),('parent_commit','unknown'),('extra','unsupported')])
def test_contradictory_study_metadata_is_not_accepted(key,value,tmp_path):
    import platform
    from scripts.research.development_ledger import DevelopmentLedger
    meta=dict(source_sha256=study.hashes(),python=platform.python_version(),parent_commit='a'*40,gate_b='GATE_B_NOT_AUTHORIZED',physics_steps=0)
    meta[key]=value
    directory=tmp_path/'bad-metadata';directory.mkdir()
    assignments=[dict(a,metadata=meta) for a in study.plan()]
    with DevelopmentLedger.create(directory/'assignments.jsonl',study=study.STUDY,assignments=assignments):pass
    with pytest.raises(ValueError,match='provenance/physics'):study.audit(directory)
