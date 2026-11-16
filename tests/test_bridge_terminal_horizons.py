"""Known development worlds exercise terminal horizon evidence, not safe stopping."""
import inspect as reflection
from copy import deepcopy
from collections import Counter
import pytest
from scripts.research import recovery_execution_bridge_v2 as bridge
from scripts.research.audit_bridge_observations import audit
from scripts.research.development_ledger import DevelopmentLedger,LedgerWriteError,inspect


def config(stop):
    c={n:p.default for n,p in reflection.signature(bridge.run_3d_episode).parameters.items()
       if n not in ('env','trace','on_trace','on_physics') and p.default is not reflection.Parameter.empty}
    c.update(seed=2256000,controller_type='AEGIS_3D_ANCHOR_RECOVERY' if stop else 'AEGIS_3D_RECOVERY_MONITOR',
             sensor_bias=[.8,.8,-.3] if stop else [0.,0.,0.],anchor_bias_xyz=[0.,0.,0.],velocity_bias_xyz=[0.,0.,0.],
             max_steps=400,navigation_force_method='DIRECTION_PRESERVING_PEAK',post_stop_steps=3,post_abstain_steps=5)
    return c


def events(path):
    return [r['details']['record'] for r in inspect(path)['records'] if r['kind']=='EVENT' and r['details']['type']=='PHYSICS']


@pytest.mark.parametrize('stop,sync',[(True,False),(False,False),(False,True)])
def test_actual_terminal_horizon_passes_observation_reader(tmp_path,stop,sync):
    path=tmp_path/'terminal.jsonl';bridge.execute(path,config(stop),synchronized=sync)
    result=audit(path);assert result['execution_status']=='COMPLETED'
    counts=Counter(e['stage'] for e in events(path))
    if stop:assert counts['POST_STOP_BRAKE']==3 and counts['ABSTAIN_BRAKE']==0
    else:assert counts['ABSTAIN_BRAKE']==1 and counts['POST_ABSTAIN_BRAKE']==5 and counts['POST_STOP_BRAKE']==0


@pytest.mark.parametrize('stop',[True,False])
def test_missing_last_horizon_sample_rejects_even_with_valid_chain(tmp_path,stop):
    path=tmp_path/'source.jsonl';bridge.execute(path,config(stop),synchronized=False)
    records=deepcopy(inspect(path)['records']);last=max(i for i,r in enumerate(records) if r['kind']=='EVENT' and r['details']['type']=='PHYSICS')
    records.pop(last);bad=tmp_path/'missing.jsonl'
    with DevelopmentLedger.create(bad,study=bridge.STUDY,assignments=records[0]['assignments'],record_events=True) as w:
        for r in records[1:]:
            if r['kind']=='START':w.start(r['id'])
            elif r['kind']=='EVENT':w.event(r['id'],details=r['details'])
            elif r['kind']=='TERMINAL':w.complete(r['id'],status=r['status'],details=r['details'])
            else:w.finalize()
    with pytest.raises(ValueError,match='missing final physics'):audit(bad)


@pytest.mark.parametrize('stop',[True,False])
def test_horizon_sink_failure_preserves_partial_evidence(tmp_path,monkeypatch,stop):
    path=tmp_path/'interrupted.jsonl';original=DevelopmentLedger.event;seen=[]
    stage='POST_STOP_BRAKE' if stop else 'POST_ABSTAIN_BRAKE'
    def fail(self,identifier,*,details):
        if details['type']=='PHYSICS' and details['record']['stage']==stage:
            seen.append(1)
            if len(seen)==2:raise LedgerWriteError('synthetic horizon failure')
        return original(self,identifier,details=details)
    monkeypatch.setattr(DevelopmentLedger,'event',fail)
    with pytest.raises(LedgerWriteError):bridge.execute(path,config(stop),synchronized=False)
    result=audit(path)
    assert result['execution_status']=='STARTED' and result['ledger_state']=='INCOMPLETE'
    assert len(seen)==2 and sum(e['stage']==stage for e in events(path))==1
