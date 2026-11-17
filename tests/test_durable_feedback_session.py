from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import pytest
from aegis.development.durable_feedback_session import DurableFeedbackSession as Store,RestartRefused,DurabilityUncertain
from scripts.research.temporal_feedback_study_1d import plan,packet,ingest


def config():
    a=plan()[0]
    return {k:deepcopy(a[k]) for k in ('model','session_id','clock_id','start_tick','limits','assumptions')}


def op(sequence=0):
    return ingest(packet('STATE',100,sequence=sequence,position=['0','0'],velocity=['.5','.5']))


def test_replay_and_equivocation_remain_after_reopen(tmp_path):
    s=Store.create(tmp_path/'store',config(),store_id='fixture');r=s.apply(op());pin=r['checkpoint'];s.close()
    s=Store.open(tmp_path/'store',expected_checkpoint=pin)
    assert s.apply(op())['result']['status']=='REPLAY_IGNORED'
    different=op();different['packet']['payload']['position']=['9','9']
    r=s.apply(different);assert r['result']['status']=='CONTRADICTORY_EVIDENCE'
    pin=r['checkpoint'];s.close()
    with Store.open(tmp_path/'store',expected_checkpoint=pin) as s:
        assert s.apply(op(1))['result']['status']=='CONTRADICTORY_EVIDENCE'


def test_real_process_exit_after_commit_preserves_replay_state(tmp_path):
    root=Path(__file__).resolve().parents[1];inputfile=tmp_path/'input.json'
    inputfile.write_text(json.dumps(dict(config=config(),op=op())))
    code="""import json,os,sys
from pathlib import Path
from aegis.development.durable_feedback_session import DurableFeedbackSession as Store
raw=json.loads(Path(sys.argv[1]).read_text())
s=Store.create(sys.argv[2],raw['config'],store_id='subprocess-fixture')
r=s.apply(raw['op'])
with Path(sys.argv[3]).open('x') as f:json.dump(r['checkpoint'],f);f.flush();os.fsync(f.fileno())
os._exit(0)
"""
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(root/'src')+os.pathsep+str(root))
    subprocess.run([sys.executable,'-c',code,str(inputfile),str(tmp_path/'store'),str(tmp_path/'external-pin.json')],cwd=root,env=env,check=True)
    pin=json.loads((tmp_path/'external-pin.json').read_text())
    with Store.open(tmp_path/'store',expected_checkpoint=pin) as s:assert s.apply(op())['result']['status']=='REPLAY_IGNORED'


def test_external_checkpoint_detects_restored_old_database_without_overwriting_newer_evidence(tmp_path):
    s=Store.create(tmp_path/'store',config(),store_id='fixture');s.apply(op());old=s.checkpoint;s.close()
    shutil.copytree(tmp_path/'store',tmp_path/'old-copy')
    with Store.open(tmp_path/'store',expected_checkpoint=old) as s:s.apply(op(1));current=s.checkpoint
    shutil.copytree(tmp_path/'old-copy',tmp_path/'restored-copy')
    with pytest.raises(RestartRefused,match='checkpoint mismatch'):Store.open(tmp_path/'restored-copy',expected_checkpoint=current)
    # Rolling back the witness too defeats local-only detection: retain the limit.
    with Store.open(tmp_path/'restored-copy',expected_checkpoint=old) as s:assert s.apply(op(1))['result']['status']=='ACCEPTED'


def test_stale_concurrent_writer_cannot_commit_second_acceptance(tmp_path):
    a=Store.create(tmp_path/'store',config(),store_id='fixture');pin=a.checkpoint
    b=Store.open(tmp_path/'store',expected_checkpoint=pin)
    a.apply(op())
    with pytest.raises(RestartRefused,match='concurrent writer'):b.apply(op())
    with pytest.raises(DurabilityUncertain):b.apply(op())
    b.close();a.close()


@pytest.mark.parametrize('phase',['before','after'])
def test_commit_failure_never_returns_acceptance_and_does_not_auto_retry(tmp_path,monkeypatch,phase):
    s=Store.create(tmp_path/'store',config(),store_id='fixture');old=s.checkpoint;commit=s._commit
    def failed():
        if phase=='after':commit()
        raise OSError('intentional '+phase+' commit response failure')
    monkeypatch.setattr(s,'_commit',failed)
    with pytest.raises(OSError):s.apply(op())
    with pytest.raises(DurabilityUncertain):s.apply(op())
    s.close()
    if phase=='after':
        with pytest.raises(RestartRefused,match='checkpoint mismatch'):Store.open(tmp_path/'store',expected_checkpoint=old)
    else:
        with Store.open(tmp_path/'store',expected_checkpoint=old) as reopened:assert reopened.apply(op())['result']['status']=='ACCEPTED'


def test_existing_or_missing_store_never_recreated_or_overwritten(tmp_path):
    s=Store.create(tmp_path/'store',config(),store_id='fixture');pin=s.checkpoint;s.close()
    with pytest.raises(FileExistsError):Store.create(tmp_path/'store',config(),store_id='other')
    with pytest.raises(RestartRefused,match='missing store'):Store.open(tmp_path/'missing',expected_checkpoint=pin)


def test_tampered_chain_refused(tmp_path):
    s=Store.create(tmp_path/'store',config(),store_id='fixture');s.apply(op());pin=s.checkpoint;s.close()
    with sqlite3.connect(tmp_path/'store/state.sqlite') as con:con.execute("UPDATE events SET operation='{}' WHERE seq=1")
    with pytest.raises(RestartRefused,match='chain mismatch'):Store.open(tmp_path/'store',expected_checkpoint=pin)


def test_changed_runtime_or_source_identity_refuses_restart(tmp_path,monkeypatch):
    from aegis.development import durable_feedback_session as module
    s=Store.create(tmp_path/'store',config(),store_id='fixture');pin=s.checkpoint;s.close()
    monkeypatch.setattr(module,'runtime_identity',lambda:{'false':'pin'})
    with pytest.raises(RestartRefused,match='pin mismatch'):Store.open(tmp_path/'store',expected_checkpoint=pin)


def test_retired_session_ids_persist_across_process_object_reconstruction(tmp_path):
    s=Store.create(tmp_path/'store',config(),store_id='fixture')
    s.apply(dict(type='BEGIN_SESSION',session_id='boot-B',clock_id='clock-B',start_tick=0));pin=s.checkpoint;s.close()
    with Store.open(tmp_path/'store',expected_checkpoint=pin) as s:
        with pytest.raises(ValueError,match='reuse'):s.apply(dict(type='BEGIN_SESSION',session_id='boot-A',clock_id='clock-A',start_tick=0))


@pytest.mark.parametrize('change',['missing','bool','wrong_store','wrong_head'])
def test_checkpoint_is_not_optional_or_coercible(tmp_path,change):
    s=Store.create(tmp_path/'store',config(),store_id='fixture');s.apply(op());pin=s.checkpoint;s.close()
    if change=='missing':pin=None
    if change=='bool':pin['seq']=True
    if change=='wrong_store':pin['store_id']='other'
    if change=='wrong_head':pin['head_sha256']='0'*64
    with pytest.raises(RestartRefused):Store.open(tmp_path/'store',expected_checkpoint=pin)


def test_sqlite_full_sync_is_set_and_one_shot_assessment_reconstructs(tmp_path):
    a=plan()[0];s=Store.create(tmp_path/'store',config(),store_id='fixture')
    for operation in a['operations']:r=s.apply(operation)
    assert r['result']['combined_finite_horizon_containment'] is True
    assert s._con.execute('PRAGMA journal_mode').fetchone()==('wal',)
    assert s._con.execute('PRAGMA synchronous').fetchone()==(2,)
    pin=s.checkpoint;s.close()
    with Store.open(tmp_path/'store',expected_checkpoint=pin) as s:assert s.checkpoint==pin
