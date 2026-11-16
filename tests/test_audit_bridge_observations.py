import inspect as reflection
from copy import deepcopy
import pytest
from scripts.research import recovery_execution_bridge_v2 as bridge
from scripts.research.audit_bridge_observations import audit
from scripts.research.development_ledger import inspect,DevelopmentLedger


def config():
    c={n:p.default for n,p in reflection.signature(bridge.run_3d_episode).parameters.items()
       if n not in ('env','trace','on_trace','on_physics') and p.default is not reflection.Parameter.empty}
    c.update(seed=2256000,controller_type='AEGIS_3D_RECOVERY_MONITOR',sensor_bias=[0.,0.,0.],
             anchor_bias_xyz=[0.,0.,0.],velocity_bias_xyz=[0.,0.,0.],max_steps=3)
    return c


@pytest.mark.parametrize('sync',[False,True])
def test_actual_observation_arithmetic(tmp_path,sync):
    p=tmp_path/'good.jsonl';bridge.execute(p,config(),synchronized=sync)
    assert audit(p)['execution_status']=='COMPLETED'


@pytest.mark.parametrize('defect',['distance','vector','collision','residual','exclusive','label','final_distance'])
def test_rehashed_observation_contradictions_reject(tmp_path,defect):
    p=tmp_path/'good.jsonl';bridge.execute(p,config(),synchronized=True);records=deepcopy(inspect(p)['records']);out=tmp_path/'bad.jsonl'
    physical=next(r['details']['record'] for r in records if r['kind']=='EVENT' and r['details']['type']=='PHYSICS')
    e=next(r['details']['episode'] for r in records if r['kind']=='TERMINAL')
    if defect=='distance':physical['distance']+=1
    elif defect=='vector':physical['velocity']=[0,0]
    elif defect=='collision':physical['collision']=1
    elif defect=='residual':physical['cbf_residual']='unknown'
    elif defect=='exclusive':e['true_success']=1
    elif defect=='label':e['timeout']=0;e['abstained']=1
    else:e['final_distance']+=1
    with DevelopmentLedger.create(out,study=bridge.STUDY,assignments=records[0]['assignments'],record_events=True) as w:
        for r in records[1:]:
            if r['kind']=='START':w.start(r['id'])
            elif r['kind']=='EVENT':w.event(r['id'],details=r['details'])
            elif r['kind']=='TERMINAL':w.complete(r['id'],status=r['status'],details=r['details'])
            else:w.finalize()
    with pytest.raises(ValueError):audit(out)
