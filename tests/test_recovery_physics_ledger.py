import sys
import pytest
from scripts.research import study_recovery_physics_evidence as study
from scripts.research.analyze_recovery_physics_evidence import analyze
from scripts.research.development_ledger import DevelopmentLedger,inspect


def test_short_actual_simulation_has_persisted_physics(tmp_path,monkeypatch):
    path=tmp_path/'physics.jsonl'
    monkeypatch.setattr(sys,'argv',['study','--development-seed','2256000','--max-steps','3','--post-stop-steps','2','--output',str(path)])
    study.main()
    result=analyze(path)
    assert result['ledger_state']=='FINALIZED'
    assert len(result['assignments'])==4
    assert all(r['decision_events']==r['physics_events']==3 for r in result['assignments'])


@pytest.mark.parametrize('defect',['stage','count','distance'])
def test_valid_hash_chain_does_not_hide_contradictory_physics(tmp_path,monkeypatch,defect):
    path=tmp_path/'source.jsonl'
    monkeypatch.setattr(sys,'argv',['study','--development-seed','2256000','--max-steps','2','--post-stop-steps','2','--output',str(path)])
    study.main();source=inspect(path);target=tmp_path/'corrupt.jsonl';header=source['records'][0]
    changed=False
    with DevelopmentLedger.create(target,study=header['study'],assignments=header['assignments'],record_events=True) as writer:
        for record in source['records'][1:]:
            if record['kind']=='START':writer.start(record['id'])
            elif record['kind']=='EVENT':
                detail=record['details']
                if not changed and detail['type']=='PHYSICS':
                    changed=True
                    if defect=='stage':detail['record']['stage']='POST_STOP_BRAKE'
                    elif defect=='distance':detail['record']['distance']+=1
                    else:continue
                writer.event(record['id'],details=detail)
            elif record['kind']=='TERMINAL':writer.complete(record['id'],status=record['status'],details=record['details'])
            elif record['kind']=='FINAL':writer.finalize()
    with pytest.raises(ValueError):analyze(target)


def test_process_exit_preserves_physics_and_incomplete_assignment(tmp_path):
    import subprocess
    path=tmp_path/'interrupted.jsonl'
    script='''
import os,sys
import numpy as np
from scripts.research.development_ledger import DevelopmentLedger
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
ledger=DevelopmentLedger.create(sys.argv[1],study='V9-M5 recovery physical evidence v1',assignments=[{'id':'case'}],record_events=True)
ledger.start('case')
def decision(event):ledger.event('case',details={'type':'DECISION','record':event})
def physics(event):
 ledger.event('case',details={'type':'PHYSICS','record':event})
 if event['physics_step']==2:os._exit(41)
run_3d_episode(AegisMuJoCo3DEnvironment(),'AEGIS_3D_ANCHOR_RECOVERY',2256000,np.zeros(3),max_steps=5,trace=[],on_trace=decision,on_physics=physics)
'''
    import os
    environment=dict(os.environ)
    environment['PYTHONPATH']='src:.'
    result=subprocess.run([sys.executable,'-c',script,str(path)],env=environment,capture_output=True,text=True)
    assert result.returncode==41,result.stderr
    state=inspect(path)
    assert state['assignments']['case']=='STARTED'
    row=analyze(path)['assignments'][0]
    assert row['execution_status']=='INCOMPLETE'
    assert row['decision_events']==row['physics_events']==2


@pytest.mark.parametrize('defect',['outcomes','budget','premature_timeout','terminal_chronology'])
def test_terminal_metadata_and_decisions_are_consistent(tmp_path,monkeypatch,defect):
    path=tmp_path/'source.jsonl'
    monkeypatch.setattr(sys,'argv',['study','--development-seed','2256000','--max-steps','2','--post-stop-steps','2','--output',str(path)])
    study.main();source=inspect(path);target=tmp_path/'bad.jsonl';header=source['records'][0]
    changed=False
    with DevelopmentLedger.create(target,study=header['study'],assignments=header['assignments'],record_events=True) as writer:
        for r in source['records'][1:]:
            if r['kind']=='START':writer.start(r['id'])
            elif r['kind']=='EVENT':
                d=r['details']
                if defect=='terminal_chronology' and not changed and d['type']=='DECISION':
                    d['record']['effective_decision']='ABSTAIN';changed=True
                elif defect=='terminal_chronology' and changed and d['type']=='PHYSICS' and d['record']['decision_step']==0:
                    d['record']['stage']='ABSTAIN_BRAKE'
                writer.event(r['id'],details=d)
            elif r['kind']=='TERMINAL':
                if not changed and defect!='terminal_chronology':
                    e=r['details']['episode'];changed=True
                    if defect=='outcomes':e['true_success']=e['false_arrival']=1;e['timeout']=0
                    elif defect=='budget':e['recovery_steps_limit']=300
                    else:e['steps']=1
                writer.complete(r['id'],status=r['status'],details=r['details'])
            elif r['kind']=='FINAL':writer.finalize()
    with pytest.raises(ValueError):analyze(target)
