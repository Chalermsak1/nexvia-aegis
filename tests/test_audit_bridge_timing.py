from copy import deepcopy
import pytest
from scripts.research.audit_bridge_timing import audit
from scripts.research import recovery_execution_bridge as bridge
from scripts.research.development_ledger import DevelopmentLedger, inspect
import inspect as introspection


def config():
    c={n:p.default for n,p in introspection.signature(bridge.run_3d_episode).parameters.items()
       if n not in ('env','trace','on_trace','on_physics') and p.default is not introspection.Parameter.empty}
    c.update(seed=2256000,controller_type='AEGIS_3D_RECOVERY_MONITOR',sensor_bias=[0.,0.,0.],
             anchor_bias_xyz=[0.,0.,0.],velocity_bias_xyz=[0.,0.,0.],max_steps=3)
    return c


@pytest.mark.parametrize('sync',[True,False])
def test_actual_short_bridge_timing(tmp_path,sync):
    p=tmp_path/'raw.jsonl';bridge.execute(p,config(),synchronized=sync)
    r=audit(p)
    assert r['execution_status']=='COMPLETED' and r['decision_events']==r['physics_events']==3


@pytest.mark.parametrize('defect',['time','phase','dt','step','stage','terminal','source'])
def test_rehashed_contradictions_are_rejected(tmp_path,defect):
    p=tmp_path/'raw.jsonl';bridge.execute(p,config(),synchronized=True);s=inspect(p);records=deepcopy(s['records']);out=tmp_path/'bad.jsonl'
    event=next(r['details'] for r in records if r['kind']=='EVENT' and r['details']['type']=='PHYSICS')
    terminal=next(r['details'] for r in records if r['kind']=='TERMINAL')
    if defect=='time':event['simulation_time_seconds']+=.01
    elif defect=='phase':event['physical_state_phase']='PRE'
    elif defect=='dt':event['runtime_timestep_seconds']=.1
    elif defect=='step':event['record']['physics_step']+=1
    elif defect=='stage':event['record']['stage']='POST_STOP_BRAKE'
    elif defect=='terminal':terminal['episode']['steps']=2
    else:terminal['source_sha256_after'][bridge.FILES[0]]='0'*64
    with DevelopmentLedger.create(out,study=bridge.STUDY,assignments=records[0]['assignments'],record_events=True) as w:
        for r in records[1:]:
            if r['kind']=='START':w.start(r['id'])
            elif r['kind']=='EVENT':w.event(r['id'],details=r['details'])
            elif r['kind']=='TERMINAL':w.complete(r['id'],status=r['status'],details=r['details'])
            else:w.finalize()
    with pytest.raises(ValueError):audit(out)


def test_unstarted_assignment_is_not_completed(tmp_path):
    p=tmp_path/'partial.jsonl'
    a={'id':'development_case','configuration':config(),'environment_id':'AEGIS_MUJOCO_3D_SYNCHRONIZED_V1_DEVELOPMENT','source_sha256':bridge.hashes()}
    with DevelopmentLedger.create(p,study=bridge.STUDY,assignments=[a],record_events=True):pass
    r=audit(p)
    assert r['execution_status']=='ASSIGNED' and r['physics_events']==0 and r['runtime_timestep_seconds'] is None
