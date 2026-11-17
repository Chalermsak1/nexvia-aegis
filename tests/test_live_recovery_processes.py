from copy import deepcopy
import pytest
from scripts.research import live_recovery_study as study


def config(scenario,arm='SIMULATION_CONTRACT_CHECKS'):
    a=deepcopy(next(a for a in study.plan() if a['scenario']==scenario and a['arm']==arm));a.update(steps=80,outage_ticks=10);return a


@pytest.mark.parametrize('scenario',['nominal','terminate_before_consumption','watchdog_restart','permanent_partition','queue_delay','storage_commit_delay','conflicting_duplicate'])
def test_live_processes_and_lifecycle_guards(scenario,tmp_path):
    r=study.run_case(config(scenario),tmp_path/'case')
    assert r['execution']['process_complete'] and r['execution']['distinct_actor_pids']
    assert r['execution']['injection_qualified']
    assert not r['unsupported_claims']['defects'] and not r['unsupported_claims']['replay_violations']
    assert not r['duplicate_effects']['repeated_consumptions'] and not r['nominal_control_availability']['unauthorized_new_consumptions']
    assert r['nominal_control_availability']['new_consumptions']>0
    if scenario in study.CRASH:assert len(r['execution']['outage_ticks'])>=8
    if scenario=='permanent_partition':assert r['uncertain_effects']['unresolved_ids'] and r['exposure']['partition_drops']>0
    if scenario=='conflicting_duplicate':assert r['duplicate_effects']['conflict_rejections']>0
    if scenario=='storage_commit_delay':
        from aegis.development.restart_process_experiment import read_records
        rows=read_records(tmp_path/'case'/'plant')['records'];delay=next(x for x in rows if x['kind']=='CONSUMPTION_COMMIT_DELAY');step=next(x for x in rows if x['kind']=='STEP_INTENT' and x['tick']==delay['tick'])
        assert step['active_arguments']['now_host_ns']>=delay['wall_ns']
        assert not step['active_check']['allowed'] and step['recovery_latched']
    assert study.analyze_case(tmp_path/'case')==r


def test_strict_live_arm_does_not_turn_assertions_into_permission(tmp_path):
    r=study.run_case(config('nominal','STRICT_OBSERVATIONS'),tmp_path/'case')
    assert r['execution']['process_complete']
    assert r['unsupported_claims']['conditional_leases_issued']==0 and r['nominal_control_availability']['new_consumptions']==0
    assert r['nominal_control_availability']['permission_steps']==0


def test_malformed_target_does_not_terminate_the_autonomous_plant(tmp_path):
    import time,json
    from concurrent.futures import ThreadPoolExecutor
    from aegis.development.restart_process_experiment import Endpoint,read_records
    a=config('nominal');a['steps']=60;directory=tmp_path/'case'
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(study.run_case,a,directory);deadline=time.monotonic()+8;injected=False
        while time.monotonic()<deadline and not future.done():
            try:
                orchestrator=read_records(directory/'orchestrator')['records'];argv=next(r['argv'] for r in orchestrator if r['kind']=='SPAWN' and r['role']=='plant');ipc=__import__('pathlib').Path(argv[5])
                rows=[json.loads(p.read_bytes())['payload'] for p in sorted((directory/'plant').glob('[0-9]'*8+'.json'),reverse=True)[:24]]
                lease=next(r['lease'] for r in rows if r['kind']=='LEASE_ACCEPTANCE_CHECK' and r['check']['allowed'])
                endpoint=Endpoint(ipc/'injected.sock')
                endpoint.send(ipc/'p.sock',dict(kind='COMMAND',command_id='c0:999999',generation=0,lease_id=lease['id'],basis_sha256=lease['basis_sha256'],target='bad',reply=str(ipc/'c0.sock')));endpoint.close();injected=True;break
            except (ValueError,FileNotFoundError,StopIteration):time.sleep(.01)
        assert injected
        result=future.result(timeout=12)
    assert result['execution']['process_complete']
    assert any(r['kind']=='MALFORMED_COMMAND_REJECTED' for r in read_records(directory/'plant')['records'])


def test_fresh_packet_metadata_does_not_prove_physical_value_freshness(tmp_path):
    r=study.run_case(config('retimestamped_freeze'),tmp_path/'case')
    assert r['execution']['process_complete'] and r['execution']['injection_qualified']
    assert r['unsupported_claims']['measurement_bound_failures']
    assert r['unsupported_claims']['leases_with_false_measurement_premise']
    assert r['nominal_control_availability']['consumptions_with_false_measurement_premise']
    assert not r['unsupported_claims']['unconditional_physical_claims']
