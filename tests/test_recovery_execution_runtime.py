import inspect as reflection
import pytest
from scripts.research import recovery_execution_bridge_v2 as bridge
from scripts.research.development_ledger import inspect, DevelopmentLedger, LedgerWriteError
from scripts.research.audit_bridge_timing import audit


def config():
    c={n:p.default for n,p in reflection.signature(bridge.run_3d_episode).parameters.items()
       if n not in ('env','trace','on_trace','on_physics') and p.default is not reflection.Parameter.empty}
    c.update(seed=2256000,controller_type='AEGIS_3D_RECOVERY_MONITOR',sensor_bias=[0.,0.,0.],
             anchor_bias_xyz=[0.,0.,0.],velocity_bias_xyz=[0.,0.,0.],max_steps=3)
    return c


@pytest.mark.parametrize('sync',[False,True])
def test_runtime_snapshot_precedes_reset_and_matches_completion(tmp_path,sync):
    p=tmp_path/'normal.jsonl';bridge.execute(p,config(),synchronized=sync);records=inspect(p)['records']
    events=[r['details'] for r in records if r['kind']=='EVENT']
    assert events[0]['type']=='RUNTIME' and events[1]['type']=='RESET'
    d=next(r['details'] for r in records if r['kind']=='TERMINAL')
    assert d['runtime_before']==d['runtime_after']==events[0]['record']
    assert inspect(p)['state']=='FINALIZED'
    with pytest.raises(ValueError,match='unsupported'):audit(p)


@pytest.mark.parametrize('field',['timestep','gravity','body_mass'])
def test_drift_after_physics_is_error_with_unlogged_step_explicit(tmp_path,monkeypatch,field):
    p=tmp_path/'drift.jsonl';original=bridge.SynchronizedAegisMuJoCo3DEnvironment.step;calls=[]
    def drift(self,*args,**kwargs):
        state=original(self,*args,**kwargs);calls.append(1)
        if field=='timestep':self.model.opt.timestep*=2
        elif field=='gravity':self.model.opt.gravity[0]=1
        else:self.model.body_mass[self.robot_body_id]*=2
        return state
    monkeypatch.setattr(bridge.SynchronizedAegisMuJoCo3DEnvironment,'step',drift)
    bridge.execute(p,config(),synchronized=True);data=inspect(p)
    assert data['state']=='FINALIZED_WITH_ERRORS' and len(calls)==1
    terminal=next(r for r in data['records'] if r['kind']=='TERMINAL')
    assert terminal['status']=='ERROR' and terminal['details']['runtime_before']!=terminal['details']['runtime_after']
    assert not any(r['kind']=='EVENT' and r['details']['type']=='PHYSICS' for r in data['records'])


def test_runtime_sink_failure_propagates_without_retry(tmp_path,monkeypatch):
    p=tmp_path/'sink.jsonl';calls=[]
    def fail(self,*args,**kwargs):calls.append(1);raise LedgerWriteError('synthetic runtime sink')
    monkeypatch.setattr(DevelopmentLedger,'event',fail)
    with pytest.raises(LedgerWriteError):bridge.execute(p,config(),synchronized=True)
    assert len(calls)==1 and inspect(p)['assignments']['development_case']=='STARTED'
