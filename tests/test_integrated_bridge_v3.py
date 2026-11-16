from copy import deepcopy
import inspect as reflection
import pytest
from scripts.research import recovery_execution_bridge_v3 as bridge
from scripts.research.audit_bridge_v3 import audit
from scripts.research.development_ledger import DevelopmentLedger,LedgerWriteError,inspect


def config():
    c={n:p.default for n,p in reflection.signature(bridge.run_3d_episode).parameters.items()
       if n not in ('env','trace','on_trace','on_physics') and p.default is not reflection.Parameter.empty}
    c.update(seed=2256000,controller_type='AEGIS_3D_RECOVERY_MONITOR',sensor_bias=[0.,0.,0.],
             anchor_bias_xyz=[0.,0.,0.],velocity_bias_xyz=[0.,0.,0.],max_steps=3)
    return c


@pytest.mark.parametrize('sync',[False,True])
def test_actual_v3_geometry_and_timing(tmp_path,sync):
    p=tmp_path/'good.jsonl';bridge.execute(p,config(),synchronized=sync)
    r=audit(p)
    assert r['execution_status']=='COMPLETED' and r['physics_events']==3
    assert r['collision_observed'] is False


@pytest.mark.parametrize('defect',['clearance','collision','integrated','phase','geometry','outcomes','compiled_geometry'])
def test_valid_rehashed_geometry_contradictions_reject(tmp_path,defect):
    p=tmp_path/'good.jsonl';bridge.execute(p,config(),synchronized=True)
    records=deepcopy(inspect(p)['records']);out=tmp_path/'bad.jsonl'
    event=next(r['details'] for r in records if r['kind']=='EVENT' and r['details']['type']=='PHYSICS')
    runtime=next(r['details']['record'] for r in records if r['kind']=='EVENT' and r['details']['type']=='RUNTIME')
    terminal=next(r['details'] for r in records if r['kind']=='TERMINAL')
    if defect=='clearance':event['record']['min_obstacle_distance']+=1
    elif defect=='collision':event['record']['contact_floor']=True;event['record']['collision']=False
    elif defect=='integrated':event['record']['integrated_translation_qpos'][0]+=1
    elif defect=='phase':event['control_diagnostics_phase']='POST'
    elif defect=='geometry':runtime.pop('obstacles')
    elif defect=='compiled_geometry':runtime['geom_pos'][runtime['obstacles'][0]['geom_id']][0]+=.1
    else:terminal['episode']['true_success']=1
    with DevelopmentLedger.create(out,study=bridge.STUDY,assignments=records[0]['assignments'],record_events=True) as w:
        for r in records[1:]:
            if r['kind']=='START':w.start(r['id'])
            elif r['kind']=='EVENT':w.event(r['id'],details=r['details'])
            elif r['kind']=='TERMINAL':w.complete(r['id'],status=r['status'],details=r['details'])
            else:w.finalize()
    with pytest.raises(ValueError):audit(out)


def test_sink_failure_keeps_started_with_unknown_collision(tmp_path,monkeypatch):
    p=tmp_path/'partial.jsonl';original=DevelopmentLedger.event
    def fail(self,identifier,*,details):
        if details['type']=='PHYSICS':raise LedgerWriteError('synthetic')
        return original(self,identifier,details=details)
    monkeypatch.setattr(DevelopmentLedger,'event',fail)
    with pytest.raises(LedgerWriteError):bridge.execute(p,config(),synchronized=True)
    r=audit(p)
    assert r['execution_status']=='STARTED' and r['collision_observed'] is None


@pytest.mark.parametrize('stop,sync',[(True,False),(False,False),(False,True)])
def test_full_declared_terminal_horizons(tmp_path,stop,sync):
    from collections import Counter
    c=config();c.update(max_steps=400,navigation_force_method='DIRECTION_PRESERVING_PEAK',post_stop_steps=50,post_abstain_steps=25)
    if stop:c.update(controller_type='AEGIS_3D_ANCHOR_RECOVERY',sensor_bias=[.8,.8,-.3])
    p=tmp_path/'full.jsonl';bridge.execute(p,c,synchronized=sync);r=audit(p)
    assert r['execution_status']=='COMPLETED'
    counts=Counter(v['details']['record']['stage'] for v in inspect(p)['records'] if v['kind']=='EVENT' and v['details']['type']=='PHYSICS')
    if stop:assert counts['POST_STOP_BRAKE']==50
    else:assert counts['ABSTAIN_BRAKE']==1 and counts['POST_ABSTAIN_BRAKE']==25
