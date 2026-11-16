import inspect as reflection
from copy import deepcopy
import pytest
from scripts.research import recovery_execution_bridge_v2 as bridge
from scripts.research.audit_bridge_v2 import audit
from scripts.research.development_ledger import inspect,DevelopmentLedger


def config():
    c={n:p.default for n,p in reflection.signature(bridge.run_3d_episode).parameters.items()
       if n not in ('env','trace','on_trace','on_physics') and p.default is not reflection.Parameter.empty}
    c.update(seed=2256000,controller_type='AEGIS_3D_RECOVERY_MONITOR',sensor_bias=[0.,0.,0.],
             anchor_bias_xyz=[0.,0.,0.],velocity_bias_xyz=[0.,0.,0.],max_steps=3)
    return c


@pytest.mark.parametrize('sync',[False,True])
def test_normal_actual_v2_trace(tmp_path,sync):
    p=tmp_path/'good.jsonl';bridge.execute(p,config(),synchronized=sync);r=audit(p)
    assert r['execution_status']=='COMPLETED' and r['runtime_unchanged'] is True
    assert r['decision_events']==r['physics_events']==3


@pytest.mark.parametrize('defect',['missing_runtime','duplicate','baseline','after','reset','snapshot'])
def test_rehashed_runtime_contradictions_reject(tmp_path,defect):
    p=tmp_path/'good.jsonl';bridge.execute(p,config(),synchronized=True);records=deepcopy(inspect(p)['records']);out=tmp_path/'bad.jsonl'
    runtime=next(r for r in records if r['kind']=='EVENT' and r['details']['type']=='RUNTIME')
    terminal=next(r for r in records if r['kind']=='TERMINAL')
    reset=next(r for r in records if r['kind']=='EVENT' and r['details']['type']=='RESET')
    if defect=='missing_runtime':records.remove(runtime)
    elif defect=='duplicate':records.insert(records.index(runtime),deepcopy(runtime))
    elif defect=='baseline':terminal['details']['runtime_before']['integrator']+=1
    elif defect=='after':terminal['details']['runtime_after']['timestep']*=2
    elif defect=='reset':reset['details']['record']['gravity'][0]=1
    else:runtime['details']['record'].pop('geom_size')
    with DevelopmentLedger.create(out,study=bridge.STUDY,assignments=records[0]['assignments'],record_events=True) as w:
        for r in records[1:]:
            if r['kind']=='START':w.start(r['id'])
            elif r['kind']=='EVENT':w.event(r['id'],details=r['details'])
            elif r['kind']=='TERMINAL':w.complete(r['id'],status=r['status'],details=r['details'])
            else:w.finalize()
    with pytest.raises(ValueError):audit(out)


def test_error_runtime_drift_is_retained_not_completed(tmp_path,monkeypatch):
    p=tmp_path/'drift.jsonl';original=bridge.SynchronizedAegisMuJoCo3DEnvironment.step
    def drift(self,*args,**kwargs):
        state=original(self,*args,**kwargs);self.model.opt.timestep*=2;return state
    monkeypatch.setattr(bridge.SynchronizedAegisMuJoCo3DEnvironment,'step',drift)
    bridge.execute(p,config(),synchronized=True);r=audit(p)
    assert r['execution_status']=='ERROR' and r['runtime_unchanged'] is False
    assert r['physics_events']==0
