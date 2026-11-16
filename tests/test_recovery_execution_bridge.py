import inspect as python_inspect
import pytest
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from scripts.research import recovery_execution_bridge as bridge
from scripts.research.development_ledger import inspect,DevelopmentLedger,LedgerWriteError


def config():
    c={n:p.default for n,p in python_inspect.signature(run_3d_episode).parameters.items()
       if n not in ('env','trace','on_trace','on_physics') and p.default is not python_inspect.Parameter.empty}
    c.update(controller_type='AEGIS_3D_RECOVERY_MONITOR',seed=2256000,sensor_bias=[0.,0.,0.],max_steps=3,
             anchor_bias_xyz=[0.,0.,0.],velocity_bias_xyz=[0.,0.,0.])
    return c


@pytest.mark.parametrize('sync',[False,True])
def test_argument_map_reset_and_physics_are_persisted(tmp_path,sync):
    p=tmp_path/'run.jsonl';c=config();bridge.execute(p,c,synchronized=sync);data=inspect(p)
    assert data['state']=='FINALIZED'
    assert data['records'][0]['assignments'][0]['configuration']==c
    events=[r['details'] for r in data['records'] if r['kind']=='EVENT']
    assert [r['type'] for r in events]==['RESET','DECISION','PHYSICS','DECISION','PHYSICS','DECISION','PHYSICS']
    assert events[0]['physical_state_phase']=='FORWARD_REFRESH_RESET'
    assert events[-1]['simulation_time_seconds']==pytest.approx(.06)
    assert all(r['runtime_timestep_seconds']==.02 for r in events)
    terminal=next(r for r in data['records'] if r['kind']=='TERMINAL')
    assert terminal['status']=='COMPLETED' and terminal['details']['episode']['steps']==3


@pytest.mark.parametrize('defect',['missing','extra','unsupported'])
def test_bad_argument_map_never_starts(tmp_path,defect):
    p=tmp_path/'run.jsonl';c=config()
    if defect=='missing':c.pop('range_bias_m')
    elif defect=='extra':c['unknown']=1
    else:c['velocity_replay_probability']=.1
    with pytest.raises(ValueError):bridge.execute(p,c,synchronized=True)
    assert not p.exists()


def test_physics_persistence_failure_leaves_started_without_retry(tmp_path,monkeypatch):
    p=tmp_path/'run.jsonl';original=DevelopmentLedger.event;calls=[]
    def fail(self,identifier,*,details):
        if details['type']=='PHYSICS':calls.append(1);raise LedgerWriteError('synthetic')
        return original(self,identifier,details=details)
    monkeypatch.setattr(DevelopmentLedger,'event',fail)
    with pytest.raises(LedgerWriteError):bridge.execute(p,config(),synchronized=True)
    assert len(calls)==1 and inspect(p)['assignments']['development_case']=='STARTED'


def test_execution_exception_is_not_completed(tmp_path,monkeypatch):
    p=tmp_path/'run.jsonl'
    def fail(*args,**kwargs):raise RuntimeError('synthetic execution error')
    monkeypatch.setattr(bridge.SynchronizedAegisMuJoCo3DEnvironment,'step',fail)
    bridge.execute(p,config(),synchronized=True)
    assert inspect(p)['state']=='FINALIZED_WITH_ERRORS'
