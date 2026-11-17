from copy import deepcopy
import json,os,subprocess,sys
from pathlib import Path
import pytest
from aegis.development import recovery_evidence as core
from aegis.development.durable_feedback_session import canonical,sha
from scripts.research import evidence_recovery_study as study
from aegis.development.evidence_recovery import statement_for


def opened(tmp_path):return core.EvidenceJournal.create(tmp_path/'journal',policy=study.policy(),boot_id='boot-A',clock_domain='local-A',now=100)
def submit_all(j,rows=None):
    for row in study.artifacts() if rows is None else rows:j.submit(row,now=100)
def evaluate(j,now=100):return j.evaluate(statement_for(study.inputs()),now=now)


@pytest.mark.parametrize('premise',core.PREMISE_NAMES)
@pytest.mark.parametrize('mode',['MISSING','ASSERTED','UNKNOWN','EXPIRED','CONTRADICTED'])
def test_each_premise_independently_withholds_support(premise,mode,tmp_path):
    rows=study.artifacts();row=next(x for x in rows if x['premise']==premise)
    if mode=='MISSING':rows.remove(row)
    elif mode=='CONTRADICTED':rows[rows.index(row)]=study.contradiction(row)
    elif mode=='EXPIRED':row.update(observed_tick=90,expires_tick=100)
    else:row.update(kind=mode,observations=None)
    with opened(tmp_path) as j:
        submit_all(j,rows);r=evaluate(j)
        assert r['status']=='EVIDENCE_INSUFFICIENT'
        assert r['premises'][premise]['status']==('UNKNOWN' if mode=='MISSING' else mode)


def test_replay_cannot_renew_half_open_expiration(tmp_path):
    with opened(tmp_path) as j:
        submit_all(j);assert evaluate(j)['status']=='SIMULATION_PREDICATES_SUPPORTED'
        assert j.submit(study.artifacts()[0],now=104)['status']=='REPLAY_IGNORED'
        assert evaluate(j,104)['status']=='SIMULATION_PREDICATES_SUPPORTED'
        assert evaluate(j,105)['status']=='EVIDENCE_INSUFFICIENT'


@pytest.mark.parametrize('evaluate_between',[False,True])
def test_contradiction_cannot_be_overwritten_or_cleared_by_restart(tmp_path,evaluate_between):
    with opened(tmp_path) as j:
        rows=study.artifacts();bad=study.contradiction(rows[0]);bad['id']='negative';j.submit(bad,now=100)
        if evaluate_between:evaluate(j)
        submit_all(j);r=evaluate(j);assert r['premises'][core.PREMISE_NAMES[0]]['status']=='CONTRADICTED'
        pin=j.checkpoint
    with core.EvidenceJournal.reopen(tmp_path/'journal',expected_checkpoint=pin) as j:
        j.begin_boot('boot-B','local-B',now=0)
        # A restart is not a contradiction-clear or review approval.
        assert evaluate(j,0)['premises'][core.PREMISE_NAMES[0]]['status']=='CONTRADICTED'


def test_late_negative_evidence_is_not_hidden_by_newer_positive(tmp_path):
    with opened(tmp_path) as j:
        submit_all(j);bad=study.contradiction(study.artifacts()[0]);bad.update(id='late-negative',observed_tick=99)
        j.submit(bad,now=101);assert evaluate(j,101)['premises'][bad['premise']]['status']=='CONTRADICTED'


def test_conflicting_replay_survives_reopen(tmp_path):
    with opened(tmp_path) as j:
        submit_all(j);j.submit(dict(study.artifacts()[0],expires_tick=106),now=100);pin=j.checkpoint
    with core.EvidenceJournal.reopen(tmp_path/'journal',expected_checkpoint=pin) as j:
        assert j.state['fault']=='EVIDENCE_ID_CONFLICT'
        assert evaluate(j)['status']=='EVIDENCE_INSUFFICIENT'


def test_restart_requires_fresh_epoch_and_never_reuses_old_boot(tmp_path):
    with opened(tmp_path) as j:
        submit_all(j);evaluate(j);pin=j.checkpoint
    with core.EvidenceJournal.reopen(tmp_path/'journal',expected_checkpoint=pin) as j:
        j.begin_boot('boot-B','local-B',now=0)
        assert evaluate(j,0)['status']=='EVIDENCE_INSUFFICIENT'
        with pytest.raises(ValueError,match='reused'):j.begin_boot('boot-A','local-A',now=0)


def test_clock_regression_is_persistent(tmp_path):
    with opened(tmp_path) as j:
        submit_all(j);evaluate(j,104);assert evaluate(j,100)['status']=='EVIDENCE_INSUFFICIENT';pin=j.checkpoint
    with core.EvidenceJournal.reopen(tmp_path/'journal',expected_checkpoint=pin) as j:assert j.state['fault']=='CLOCK_REGRESSION'


def test_wrong_checkpoint_and_concurrent_writer_are_refused(tmp_path):
    with opened(tmp_path) as j:
        pin=j.checkpoint
        with pytest.raises(BlockingIOError):core.EvidenceJournal.reopen(tmp_path/'journal',expected_checkpoint=pin)
        submit_all(j)
    with pytest.raises(ValueError,match='checkpoint'):core.EvidenceJournal.reopen(tmp_path/'journal',expected_checkpoint=pin)


def test_pending_write_is_preserved_and_prevents_resume(tmp_path,monkeypatch):
    j=opened(tmp_path);pin=j.checkpoint
    def fail(*args):raise OSError('synthetic link failure after fsync')
    monkeypatch.setattr(core.os,'link',fail)
    with pytest.raises(OSError):j.submit(study.artifacts()[0],now=100)
    r=core.inspect(tmp_path/'journal');assert r['checkpoint']==pin and len(r['pending'])==1
    before=next((tmp_path/'journal').glob('pending_*')).read_bytes()
    with pytest.raises(ValueError,match='pending'):core.EvidenceJournal.reopen(tmp_path/'journal',expected_checkpoint=pin)
    assert next((tmp_path/'journal').glob('pending_*')).read_bytes()==before


def test_real_process_exit_preserves_committed_evidence(tmp_path):
    directory=tmp_path/'child'
    code='''import os,sys
from pathlib import Path
from aegis.development.recovery_evidence import EvidenceJournal
from scripts.research.evidence_recovery_study import policy,artifacts
j=EvidenceJournal.create(Path(sys.argv[1]),policy=policy(),boot_id='boot-A',clock_domain='local-A',now=100)
j.submit(artifacts()[0],now=100)
os._exit(23)
'''
    result=subprocess.run([sys.executable,'-c',code,str(directory)],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='src:.'),check=False)
    assert result.returncode==23
    r=core.inspect(directory);assert r['checkpoint']['seq']==1 and len(r['state']['seen'])==1
    with core.EvidenceJournal.reopen(directory,expected_checkpoint=r['checkpoint']) as j:assert evaluate(j)['status']=='EVIDENCE_INSUFFICIENT'


def test_rehashed_predicate_tamper_fails_semantic_reconstruction(tmp_path):
    with opened(tmp_path) as j:submit_all(j);evaluate(j)
    original=tmp_path/'original';import shutil;shutil.copytree(tmp_path/'journal',original)
    previous=core.ZERO
    for path in sorted((tmp_path/'journal').glob('[0-9]'*8+'.json')):
        r=json.loads(path.read_bytes())
        if r['payload'].get('kind')=='ARTIFACT' and r['payload']['artifact']['premise']==core.PREMISE_NAMES[0]:r['payload']['artifact']['observations'][0]='999'
        r['previous']=previous;r['sha256']=sha({k:r[k] for k in ('seq','previous','payload')});path.write_bytes(canonical(r)+b'\n');previous=r['sha256']
    with pytest.raises(ValueError,match='vector'):core.inspect(tmp_path/'journal')
    assert core.inspect(original)['state']['fault'] is None


def test_capacity_exhaustion_cannot_evict_replay_history(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'MAX_EVENTS',2)
    with opened(tmp_path) as j:
        j.submit(study.artifacts()[0],now=100);evaluate(j)
        with pytest.raises(ValueError,match='capacity'):j.submit(study.artifacts()[1],now=100)
        assert len(j.state['seen'])==1


def test_read_only_replay_matches_evaluation_and_preserves_bytes(tmp_path):
    with opened(tmp_path) as j:submit_all(j);expected=evaluate(j)
    before={p.name:p.read_bytes() for p in (tmp_path/'journal').iterdir()}
    replay=core.EvidenceReplay(tmp_path/'journal');assert replay.evaluate(statement_for(study.inputs()),now=100)==expected
    assert before=={p.name:p.read_bytes() for p in (tmp_path/'journal').iterdir()}


def test_negative_witness_identity_survives_favorable_update_and_restart(tmp_path):
    with opened(tmp_path) as j:
        bad=study.contradiction(study.artifacts()[0]);bad['id']='negative-witness';j.submit(bad,now=100);submit_all(j)
        r=evaluate(j);row=r['premises'][bad['premise']]
        assert row['contradiction_artifact_ids']==['negative-witness']
        pin=j.checkpoint
    with core.EvidenceJournal.reopen(tmp_path/'journal',expected_checkpoint=pin) as j:
        j.begin_boot('boot-B','local-B',now=0)
        assert evaluate(j,0)['premises'][bad['premise']]['contradiction_artifact_ids']==['negative-witness']


def test_real_process_exit_during_commit_keeps_pending_bytes_uncommitted(tmp_path):
    directory=tmp_path/'interrupted'
    code='''import os,sys
from pathlib import Path
from aegis.development import recovery_evidence as c
from scripts.research.evidence_recovery_study import policy,artifacts
j=c.EvidenceJournal.create(Path(sys.argv[1]),policy=policy(),boot_id='boot-A',clock_domain='local-A',now=100)
def die_before_link(*args):os._exit(24)
c.os.link=die_before_link
j.submit(artifacts()[0],now=100)
'''
    r=subprocess.run([sys.executable,'-c',code,str(directory)],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='src:.'),check=False)
    assert r.returncode==24
    state=core.inspect(directory);assert not state['state']['seen'] and len(state['pending'])==1
    with pytest.raises(ValueError,match='pending'):core.EvidenceJournal.reopen(directory,expected_checkpoint=state['checkpoint'])


def test_permanent_loss_of_evidence_expires_instead_of_reconciling_itself(tmp_path):
    with opened(tmp_path) as j:
        submit_all(j);assert evaluate(j,100)['status']=='SIMULATION_PREDICATES_SUPPORTED'
        r=evaluate(j,10000)
        assert all(v['status']=='EXPIRED' for v in r['premises'].values())
        assert j.state['seen'] and len(j.state['seen'])==9


def test_exact_expiry_is_rejected_even_while_maximum_age_allows_it(tmp_path):
    with opened(tmp_path) as j:
        submit_all(j,study.artifacts(expires=104))
        assert evaluate(j,103)['status']=='SIMULATION_PREDICATES_SUPPORTED'
        assert all(v['status']=='EXPIRED' for v in evaluate(j,104)['premises'].values())


def test_age_boundary_is_checked_independently_of_artifact_expiry(tmp_path):
    with opened(tmp_path) as j:
        submit_all(j,study.artifacts(expires=1000))
        assert evaluate(j,104)['status']=='SIMULATION_PREDICATES_SUPPORTED'
        assert all(v['status']=='EXPIRED' for v in evaluate(j,105)['premises'].values())
