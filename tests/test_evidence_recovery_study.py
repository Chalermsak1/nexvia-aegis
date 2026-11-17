import json
from pathlib import Path
from scripts.research import evidence_recovery_study as study


def test_all_predeclared_cases_preserve_separate_meanings(tmp_path):
    root=tmp_path/'study';r=study.run(root);audit=study.audit(root)
    assert len(r['results'])==len(study.plan())==148
    assert audit['ledger_counts']['ERROR']==0 and not audit['incomplete']
    evidence=[x for x in r['results'] if x['assignment']['kind']=='EVIDENCE']
    supported=[x for x in evidence if x['result']['development_action'] is not None]
    assert len(supported)==1 and supported[0]['assignment']['mode']=='NOMINAL'
    stopping=[x for x in r['results'] if x['assignment']['kind']=='STOPPING']
    assert any(x['result']['first_stop_prefix_contained'] is False for x in stopping)
    assert any(x['result']['stopping_capability']=='NO_WORST_CASE_STOPPING_CAPABILITY' for x in stopping)
    assert all(x['result']['full_trajectory_containment'] is None for x in stopping)
    assert r['aggregate_pass_fail'] is None


def test_changed_result_is_rejected_even_if_other_runs_are_good(tmp_path):
    # Explicitly adversarial copy; the original remains byte-for-byte intact.
    import shutil,pytest
    root=tmp_path/'study';study.run(root);original=tmp_path/'original';shutil.copytree(root,original)
    path=root/'evidence_nominal'/'result.json';r=json.loads(path.read_bytes());r['result']['operational_authorization']=True;path.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='identity'):study.audit(root)
    assert study.audit(original)['ledger_counts']['COMPLETED']==148
