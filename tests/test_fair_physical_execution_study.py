from copy import deepcopy
import json
import pytest
from scripts.research import fair_physical_execution_study as study


def test_matched_groups_have_identical_physical_contract_and_faults():
    groups={}
    for a in study.plan():groups.setdefault((a['mass'],a['initial_velocity'],a['fault']),[]).append(a)
    assert len(groups)==16
    for rows in groups.values():
        assert {a['arm'] for a in rows}==set(study.ARMS)
        assert len({json.dumps(a['common_contract'],sort_keys=True) for a in rows})==1


@pytest.mark.parametrize('arm',study.ARMS)
def test_short_saved_physical_comparison_reconstructs_exactly(arm,tmp_path):
    a=deepcopy(next(x for x in study.plan() if x['arm']==arm));a['steps']=8;r=study.case(a)
    (tmp_path/'raw_result.json').write_text(json.dumps(r))
    assert study.case(a,saved=r)==r and not r['summary']['physical_hardware_validated']
    r['frames'][2]['position_after']='999'
    with pytest.raises(ValueError):study.case(a,saved=r)


def test_small_study_preserves_executor_and_detects_marker_corruption(tmp_path,monkeypatch):
    original=study.plan
    def small():
        a=original()[0];a['steps']=8;return [a]
    monkeypatch.setattr(study,'plan',small);d=tmp_path/'batch';r=study.run(d)
    assert r==study.audit(d) and r['counts']['COMPLETED']==1
    with pytest.raises(FileExistsError):study.run(d)
    marker=next(d.rglob('effects/*.json'));marker.write_text('{}')
    with pytest.raises(ValueError):study.audit(d)


def test_execution_error_does_not_retry_or_hide_unstarted_comparisons(tmp_path,monkeypatch):
    monkeypatch.setattr(study,'case',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('intentional error')))
    d=tmp_path/'failed'
    with pytest.raises(RuntimeError):study.run(d)
    r=study.audit(d);assert r['counts']==dict(ASSIGNED=63,STARTED=0,COMPLETED=0,ERROR=1)


def test_changed_contract_is_not_silently_simulated_as_old_fixture():
    a=study.plan()[0];a['common_contract']['dt']='.1'
    with pytest.raises(ValueError,match='contract'):study.case(a)


def test_degraded_request_preserves_unknown_claim_for_unsupported_start():
    a=next(x for x in study.plan() if x['arm']=='PHYSICAL_RESERVE_DEGRADED' and x['initial_velocity']=='.8' and x['fault']=='nominal');a['steps']=8
    r=study.case(a)
    assert r['summary']['request_tick']==0 and not r['summary']['initial_state_supported']
    assert r['frames'][0]['assessment']['status']=='UNRESOLVED_PHYSICAL_TIME_RESPONSE'
    assert r['frames'][0]['request_supported'] is False
