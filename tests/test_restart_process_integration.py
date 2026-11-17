from copy import deepcopy
import pytest
from scripts.research import restart_failure_study as study


def config(name):
    a=deepcopy(next(x for x in study.plan() if x['id']==name));a.update(steps=90,outage_ticks=12,wall_period=.015);return a


@pytest.mark.parametrize('name',['nominal','terminate_before_consumption','terminate_after_consumption','restart_lost_ack_replay','duplicate_requests'])
def test_real_processes_keep_plant_alive_and_preserve_separate_metrics(name,tmp_path):
    r=study.run_case(config(name),tmp_path/'case')
    assert r['execution']['plant_complete'] and r['execution']['distinct_actor_pids']
    assert not r['unsupported_claims']['at_issue'] and not r['unsupported_claims']['nominal_requests_after_recovery_observation']
    assert not r['duplicate_effects']['repeated_consumptions'] and not r['unsupported_claims']['causality_violations']
    assert not r['nominal_control_availability']['new_consumptions_without_permission']
    if name in study.CRASH:
        assert r['execution']['crash_injection_qualified'] and r['recovery_latency']['plant_updates_during_controller_outage']>=8
    if name=='duplicate_requests':assert r['duplicate_effects']['duplicate_rejections']>0
    assert study.analyze_case(tmp_path/'case')==r


def test_queued_power_loss_is_actually_exposed_and_audited(tmp_path):
    r=study.run_case(config('power_loss_queued'),tmp_path/'case')
    assert r['injections']['power_loss_while_queued_exposed']
    assert r['recovery_latency']['handoff']['ticks']>=0
    assert r['execution']['actuator_reconstruction']['steps']==90


def test_rehashed_force_reset_cannot_fool_independent_actuator_reconstruction(tmp_path):
    import json,shutil
    from aegis.development import restart_process_experiment as actors
    study.run_case(config('nominal'),tmp_path/'case')
    shutil.copytree(tmp_path/'case',tmp_path/'original_case')
    directory=tmp_path/'case'/'plant';previous=actors.ZERO
    for path in sorted(directory.glob('[0-9]'*8+'.json')):
        r=json.loads(path.read_bytes())
        if r['payload']['kind']=='STEP_INTENT' and r['payload']['tick']==5:r['payload']['force']='999'
        r['previous']=previous;r['sha256']=actors.sha({k:r[k] for k in ('seq','previous','payload')});path.write_bytes(actors.canonical(r)+b'\n');previous=r['sha256']
    with pytest.raises(ValueError,match='actuator'):study.analyze_case(tmp_path/'case')
