import pytest
from scripts.research import family_recovery_composition_study as study


def test_fixed_designs_complete_and_reconstruct_without_promoting_unknown(tmp_path):
    directory=tmp_path/'study';r=study.run(directory)
    assert r==study.audit(directory) and len(study.plan())==30
    assert r['counts']==dict(ASSIGNED=0,STARTED=0,COMPLETED=30,ERROR=0)
    assert r['study_native_steps']==0 and not r['operational_authorization']
    results={a['id']:a['details']['result'] for a in r['assignments']}
    assert results['held_force_interior_escape']['physical_endpoints_contained']
    assert not results['held_force_interior_escape']['continuous_segment_containment']
    assert results['singleton_primary']['development_action']=='CONTINUE_WITH_FAMILY_RESERVE'
    with pytest.raises(FileExistsError):study.run(directory)


@pytest.mark.parametrize('change',['result','missing','sources','plan'])
def test_corrupted_or_mismatched_evidence_is_rejected(change,tmp_path,monkeypatch):
    directory=tmp_path/'study';study.run(directory)
    if change=='result':(directory/'singleton_primary.json').write_text('{}\n')
    if change=='missing':(directory/'singleton_primary.json').unlink()
    if change=='sources':monkeypatch.setattr(study,'hashes',lambda:{})
    if change=='plan':monkeypatch.setattr(study,'plan',lambda:[])
    with pytest.raises((ValueError,FileNotFoundError)):study.audit(directory)


def test_execution_error_retained_without_retrying_remaining_designs(tmp_path,monkeypatch):
    monkeypatch.setattr(study,'run_case',lambda *a:(_ for _ in ()).throw(RuntimeError('intentional development failure')))
    directory=tmp_path/'failed'
    with pytest.raises(RuntimeError):study.run(directory)
    r=study.audit(directory)
    assert r['ledger_state']=='INCOMPLETE' and r['counts']==dict(ASSIGNED=29,STARTED=0,COMPLETED=0,ERROR=1)
    assert not r['categories'] and all(a['details'] is None for a in r['assignments'])
