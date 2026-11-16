import sys
import numpy as np
import pytest
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from scripts.research import study_recovery_physics_evidence as study
from scripts.research.analyze_recovery_physics_evidence import analyze
from scripts.research.development_ledger import DevelopmentLedger,inspect


def test_extra_abstention_physics_preserves_decisions_and_historical_counters():
    args=dict(controller_type='AEGIS_3D_RECOVERY_MONITOR',seed=2256000,sensor_bias=np.zeros(3),max_steps=150,
        navigation_force_method='DIRECTION_PRESERVING_PEAK',post_stop_steps=3)
    original_trace=[];extended_trace=[];physical=[]
    original=run_3d_episode(AegisMuJoCo3DEnvironment(),trace=original_trace,**args)
    extended=run_3d_episode(AegisMuJoCo3DEnvironment(),trace=extended_trace,on_physics=physical.append,post_abstain_steps=5,**args)
    assert original=={k:v for k,v in extended.items() if k!='post_abstain'}
    assert original_trace==extended_trace
    assert original['abstained']==1
    assert [r['stage'] for r in physical[-6:]]==['ABSTAIN_BRAKE']+['POST_ABSTAIN_BRAKE']*5
    assert len(extended['post_abstain']['steps'])==5
    assert extended['post_abstain']['initial_brake_distance']==physical[-6]['distance']


@pytest.mark.parametrize('value',[True,-1,1.5])
def test_horizon_parameter_rejected(value):
    with pytest.raises(ValueError):
        run_3d_episode(AegisMuJoCo3DEnvironment(),'AEGIS_3D_ANCHOR_RECOVERY',2256000,np.zeros(3),post_abstain_steps=value)


def test_new_horizon_restricted_to_recovery():
    with pytest.raises(ValueError):
        run_3d_episode(AegisMuJoCo3DEnvironment(),'CBF_ONLY',2256000,np.zeros(3),post_abstain_steps=5)


def create(tmp_path,monkeypatch):
    path=tmp_path/'study.jsonl'
    monkeypatch.setattr(sys,'argv',['study','--development-seed','2256000','--max-steps','150',
        '--post-stop-steps','3','--post-abstain-steps','5','--output',str(path)])
    study.main()
    return path


def test_completed_v2_horizon_and_legacy_v1_readability(tmp_path,monkeypatch):
    path=create(tmp_path,monkeypatch);result=analyze(path)
    assert result['ledger_state']=='FINALIZED'
    assert any(r['stage_counts'].get('POST_ABSTAIN_BRAKE')==5 for r in result['assignments'])
    legacy=tmp_path/'v1.jsonl'
    monkeypatch.setattr(sys,'argv',['study','--development-seed','2256000','--max-steps','2',
        '--post-stop-steps','3','--output',str(legacy)])
    study.main()
    old=analyze(legacy)
    assert old['ledger_state']=='FINALIZED'


@pytest.mark.parametrize('defect',['drop','stage','distance','overrun'])
def test_contradictory_v2_physics_rejected(tmp_path,monkeypatch,defect):
    path=create(tmp_path,monkeypatch);source=inspect(path);header=source['records'][0];out=tmp_path/'bad.jsonl';changed=False
    with DevelopmentLedger.create(out,study=header['study'],assignments=header['assignments'],record_events=True) as w:
        for r in source['records'][1:]:
            if r['kind']=='START':w.start(r['id'])
            elif r['kind']=='EVENT':
                detail=r['details']
                if not changed and detail['type']=='PHYSICS' and detail['record']['stage']=='POST_ABSTAIN_BRAKE':
                    changed=True
                    if defect=='drop':continue
                    if defect=='stage':detail['record']['stage']='MAIN'
                    elif defect=='distance':detail['record']['distance']+=1
                    elif defect=='overrun':
                        w.event(r['id'],details=detail)
                w.event(r['id'],details=detail)
            elif r['kind']=='TERMINAL':w.complete(r['id'],status=r['status'],details=r['details'])
            elif r['kind']=='FINAL':w.finalize()
    assert changed
    with pytest.raises(ValueError):analyze(out)


def test_process_exit_inside_extra_horizon_retains_partial_physics(tmp_path):
    import os,subprocess
    path=tmp_path/'interrupted.jsonl'
    script='''
import os,sys
import numpy as np
from scripts.research.development_ledger import DevelopmentLedger
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
ledger=DevelopmentLedger.create(sys.argv[1],study='V9-M5 recovery physical evidence v2',assignments=[{'id':'case','post_abstain_steps':5}],record_events=True)
ledger.start('case');extra=0
def decision(e):ledger.event('case',details={'type':'DECISION','record':e})
def physics(e):
 global extra
 ledger.event('case',details={'type':'PHYSICS','record':e})
 if e['stage']=='POST_ABSTAIN_BRAKE':
  extra+=1
  if extra==2:os._exit(42)
run_3d_episode(AegisMuJoCo3DEnvironment(),'AEGIS_3D_RECOVERY_MONITOR',2256000,np.zeros(3),max_steps=150,post_abstain_steps=5,navigation_force_method='DIRECTION_PRESERVING_PEAK',trace=[],on_trace=decision,on_physics=physics)
'''
    environment=dict(os.environ);environment['PYTHONPATH']='src:.'
    result=subprocess.run([sys.executable,'-c',script,str(path)],env=environment,capture_output=True,text=True)
    assert result.returncode==42,result.stderr
    assert inspect(path)['assignments']['case']=='STARTED'
    row=analyze(path)['assignments'][0]
    assert row['execution_status']=='INCOMPLETE'
    assert row['stage_counts']['ABSTAIN_BRAKE']==1
    assert row['stage_counts']['POST_ABSTAIN_BRAKE']==2


def test_runner_propagates_extra_horizon_sink_failure_without_terminal_retry(tmp_path,monkeypatch):
    from scripts.research.development_ledger import LedgerWriteError
    path=tmp_path/'failed.jsonl'
    monkeypatch.setattr(sys,'argv',['study','--development-seed','2256000','--max-steps','150',
        '--post-stop-steps','3','--post-abstain-steps','5','--output',str(path)])
    original=DevelopmentLedger.event
    failures=[]
    def failing(self,identifier,*,details):
        if details['type']=='PHYSICS' and details['record']['stage']=='POST_ABSTAIN_BRAKE':
            failures.append(identifier)
            raise LedgerWriteError('synthetic extra-horizon sink failure')
        return original(self,identifier,details=details)
    monkeypatch.setattr(DevelopmentLedger,'event',failing)
    with pytest.raises(LedgerWriteError,match='extra-horizon'):
        study.main()
    assert len(failures)==1
    state=inspect(path)
    assert state['counts']['STARTED']==1 and state['counts']['ASSIGNED']==3
    row=analyze(path)['assignments'][0]
    assert row['execution_status']=='INCOMPLETE'
    assert row['stage_counts']['ABSTAIN_BRAKE']==1
    assert row['stage_counts'].get('POST_ABSTAIN_BRAKE',0)==0
