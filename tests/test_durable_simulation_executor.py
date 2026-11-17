from copy import deepcopy
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import pytest
from aegis.development.durable_simulation_executor import DurableSimulationExecutor as Store,EffectUncertain
from aegis.development.durable_feedback_session import RestartRefused,sha


class Clock:
    def __init__(self,n=100):self.n=n
    def __call__(self):return self.n

def plan():return dict(status='DEVELOPMENT_BASELINE_ACTION',dispatch=False,operational_authorization=False,hardware_validation=False,gate_b='GATE_B_NOT_AUTHORIZED')
def create(tmp_path):
    c=Clock();s=Store.create(tmp_path/'store',store_id='test',boot_id='A',clock=c);return s,c

def marker(s):return s.directory/'effects'/(sha('cmd')+'.json')


def test_record_claim_effect_and_restart_prevent_second_effect(tmp_path):
    s,c=create(tmp_path);s.record('cmd',plan(),expires_ns=200);claim=s.claim('cmd')
    assert s.simulate_effect('cmd',token=claim['token'])['status']=='SYNTHETIC_EFFECT_OBSERVED'
    pin=s.checkpoint;raw=marker(s).read_bytes();s.close()
    with Store.open(tmp_path/'store',expected_checkpoint=pin,boot_id='A',clock=c) as s:
        assert s.state['commands']['cmd']['status']=='SYNTHETIC_EFFECT_OBSERVED' and s.state['commands']['cmd']['timeliness_established']
        with pytest.raises(ValueError):s.claim('cmd')
    assert (tmp_path/'store'/'effects'/(sha('cmd')+'.json')).read_bytes()==raw


def test_restart_claimed_command_is_uncertain_and_never_retried(tmp_path):
    s,c=create(tmp_path);s.record('cmd',plan(),expires_ns=200);s.claim('cmd');pin=s.checkpoint;s.close()
    with Store.open(tmp_path/'store',expected_checkpoint=pin,boot_id='B',clock=Clock(0)) as s:
        assert s.state['commands']['cmd']['status']=='EFFECT_UNCERTAIN'
        assert s.reconcile_marker('cmd',expected_marker_sha256='a'*64)['status']=='EFFECT_UNCERTAIN'
        assert not marker(s).exists()
        with pytest.raises(ValueError):s.claim('cmd')


def test_old_boot_unclaimed_command_is_expired(tmp_path):
    s,c=create(tmp_path);s.record('cmd',plan(),expires_ns=200);pin=s.checkpoint;s.close()
    with Store.open(tmp_path/'store',expected_checkpoint=pin,boot_id='B',clock=Clock(0)) as s:
        assert s.state['commands']['cmd']['status']=='EXPIRED'
        pin=s.checkpoint
    with pytest.raises(ValueError):Store.open(tmp_path/'store',expected_checkpoint=pin,boot_id='A',clock=c)


def test_expiry_boundary_does_not_create_marker(tmp_path):
    s,c=create(tmp_path);s.record('cmd',plan(),expires_ns=200);c.n=200
    assert s.claim('cmd')['status']=='EXPIRED';assert not marker(s).exists();s.close()


def test_post_effect_deadline_withholds_confirmation_and_requires_reopen(tmp_path,monkeypatch):
    s,c=create(tmp_path);s.record('cmd',plan(),expires_ns=200);claim=s.claim('cmd')
    monkeypatch.setattr(s,'_after_effect_sync',lambda:setattr(c,'n',200))
    r=s.simulate_effect('cmd',token=claim['token']);assert r['status']=='EFFECT_UNCERTAIN' and marker(s).exists()
    with pytest.raises(EffectUncertain):s.claim('cmd')
    pin=s.checkpoint;h=hashlib.sha256(marker(s).read_bytes()).hexdigest();s.close()
    with Store.open(tmp_path/'store',expected_checkpoint=pin,boot_id='A',clock=c) as s:
        r=s.reconcile_marker('cmd',expected_marker_sha256=h);assert r['status']=='SYNTHETIC_EFFECT_OBSERVED' and not r['timeliness_established']
        assert not s.state['commands']['cmd']['timeliness_established']


@pytest.mark.parametrize('after_commit',[False,True])
def test_commit_failure_does_not_return_effect_acceptance(after_commit,tmp_path,monkeypatch):
    s,c=create(tmp_path);pin=s.checkpoint;real=s._commit
    def fail():
        if after_commit:real()
        raise OSError('intentional commit uncertainty')
    monkeypatch.setattr(s,'_commit',fail)
    with pytest.raises(OSError):s.record('cmd',plan(),expires_ns=200)
    s.close()
    if after_commit:
        with pytest.raises(RestartRefused):Store.open(tmp_path/'store',expected_checkpoint=pin,boot_id='A',clock=c)
    else:
        with Store.open(tmp_path/'store',expected_checkpoint=pin,boot_id='A',clock=c) as s:assert not s.state['commands']


def test_two_connections_cannot_claim_from_same_head(tmp_path):
    a,c=create(tmp_path);a.record('cmd',plan(),expires_ns=200)
    b=Store.open(tmp_path/'store',expected_checkpoint=a.checkpoint,boot_id='A',clock=c)
    with pytest.raises(RestartRefused):a.claim('cmd')
    assert b.claim('cmd')['status']=='CLAIMED';a.close();b.close()


@pytest.mark.parametrize('field,value',[('dispatch',True),('operational_authorization',True),('hardware_validation',True),('gate_b','AUTHORIZED'),('status','PRODUCTION_COMMAND')])
def test_foreign_authority_or_production_plan_is_rejected(field,value,tmp_path):
    s,c=create(tmp_path);p=plan();p[field]=value
    with pytest.raises(ValueError):s.record('cmd',p,expires_ns=200)
    s.close()


def test_wrong_token_cannot_create_marker(tmp_path):
    s,c=create(tmp_path);s.record('cmd',plan(),expires_ns=200);s.claim('cmd')
    with pytest.raises(ValueError):s.simulate_effect('cmd',token='f'*64)
    assert not marker(s).exists();s.close()


def test_process_exit_after_effect_before_observation_retains_uncertainty(tmp_path):
    script='''import json,os,sys
from pathlib import Path
from aegis.development.durable_simulation_executor import DurableSimulationExecutor as S
p=Path(sys.argv[1]);clock=lambda:100
s=S.create(p/'store',store_id='child',boot_id='A',clock=clock)
s.record('cmd',dict(status='DEVELOPMENT_BASELINE_ACTION',dispatch=False,operational_authorization=False,hardware_validation=False,gate_b='GATE_B_NOT_AUTHORIZED'),expires_ns=200)
c=s.claim('cmd')
def crash():
    with (p/'pin.json').open('x') as f:json.dump(s.checkpoint,f);f.flush();os.fsync(f.fileno())
    os._exit(23)
s._after_effect_sync=crash
s.simulate_effect('cmd',token=c['token'])
'''
    completed=subprocess.run([sys.executable,'-c',script,str(tmp_path)],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    assert completed.returncode==23;pin=json.loads((tmp_path/'pin.json').read_text())
    with Store.open(tmp_path/'store',expected_checkpoint=pin,boot_id='B',clock=Clock(0)) as s:
        assert s.state['commands']['cmd']['status']=='EFFECT_UNCERTAIN'
        raw=marker(s).read_bytes();r=s.reconcile_marker('cmd',expected_marker_sha256=hashlib.sha256(raw).hexdigest())
        assert r['status']=='SYNTHETIC_EFFECT_OBSERVED' and not r['timeliness_established']
        assert not s.state['commands']['cmd']['timeliness_established']


def test_external_newer_pin_rejects_database_rollback_but_colocated_rollback_is_undetectable(tmp_path):
    s,c=create(tmp_path);pin0=s.checkpoint;s.close();shutil.copytree(tmp_path/'store',tmp_path/'old')
    s=Store.open(tmp_path/'store',expected_checkpoint=pin0,boot_id='A',clock=c);s.record('cmd',plan(),expires_ns=200);pin1=s.checkpoint;s.close()
    with pytest.raises(RestartRefused):Store.open(tmp_path/'old',expected_checkpoint=pin1,boot_id='A',clock=c)
    with Store.open(tmp_path/'old',expected_checkpoint=pin0,boot_id='A',clock=c) as rolled:
        assert 'cmd' not in rolled.state['commands']  # negative control, unresolved custody


def test_marker_symlink_and_altered_content_are_not_accepted(tmp_path):
    s,c=create(tmp_path);s.record('cmd',plan(),expires_ns=200);cl=s.claim('cmd');s._append(dict(kind='BEGIN',now=100,command_id='cmd',token=cl['token']))
    target=tmp_path/'external';target.write_text('wrong');marker(s).symlink_to(target)
    with pytest.raises(RestartRefused):s.reconcile_marker('cmd',expected_marker_sha256='a'*64)
    marker(s).unlink();marker(s).write_text('{}')
    with pytest.raises(RestartRefused):s.reconcile_marker('cmd',expected_marker_sha256=hashlib.sha256(b'{}').hexdigest())
    s.close()


def test_sealed_audit_is_read_only_and_reconstructs_persisted_timing(tmp_path):
    s,c=create(tmp_path);s.record('cmd',plan(),expires_ns=200);cl=s.claim('cmd');s.simulate_effect('cmd',token=cl['token']);pin=s.checkpoint;s.close()
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp_path/'store').rglob('*') if p.is_file()}
    r=Store.audit_closed(tmp_path/'store',expected_checkpoint=pin)
    assert r['state']['commands']['cmd']['timeliness_established']
    assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp_path/'store').rglob('*') if p.is_file()}


def test_regressed_clock_refuses_effect_and_old_boot_cannot_resume_record(tmp_path):
    s,c=create(tmp_path);s.record('cmd',plan(),expires_ns=200);c.n=99
    with pytest.raises(ValueError):s.claim('cmd')
    assert not marker(s).exists();pin=s.checkpoint;s.close()
    with Store.open(tmp_path/'store',expected_checkpoint=pin,boot_id='B',clock=Clock(0)) as s:
        assert s.state['commands']['cmd']['status']=='EXPIRED'
