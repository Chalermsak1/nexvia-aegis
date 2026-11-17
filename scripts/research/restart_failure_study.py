"""Process-isolated DEVELOPMENT restart/failure campaign; six separate outcomes."""
from pathlib import Path
from fractions import Fraction as Q
from collections import Counter
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,time
from aegis.development import restart_process_experiment as actors
from aegis.development.durable_feedback_session import canonical,sha
from scripts.research import fair_physical_execution_study as prior
from scripts.research.development_ledger import DevelopmentLedger,inspect

ROOT=Path(__file__).resolve().parents[2]
FILES=prior.FILES+('src/aegis/development/restart_process_experiment.py','scripts/research/restart_failure_study.py',
 'tests/test_restart_actor_protocol.py','tests/test_restart_measurements.py','tests/test_restart_process_integration.py','docs/research/RESTART_EXPERIMENT_ACCEPTANCE_RP01_2026-11-17.md')
SCENARIOS=('nominal','terminate_before_consumption','terminate_after_consumption','lost_acknowledgements','duplicate_requests','replayed_feedback',
 'clock_reset','session_reset','progressive_staleness','power_loss_queued','backup_delayed','backup_unavailable','restart_lost_ack_replay',
 'conflicting_duplicate','unsupported_start','malformed_feedback')
CRASH={'terminate_before_consumption':'COMMAND_ACCEPTED','terminate_after_consumption':'COMMAND_CONSUMED','session_reset':'COMMAND_CONSUMED','restart_lost_ack_replay':'COMMAND_CONSUMED'}


def hashes():return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FILES}
def plan():return [dict(id=s,scenario=s,steps=140,wall_period=.015,outage_ticks=15,quiesce_ticks=4,power_loss_tick=1 if s=='power_loss_queued' else 30,initial_velocity='.8' if s=='unsupported_start' else '.3',protocol='RP01') for s in SCENARIOS]

def run_case(config,directory):
    d=Path(directory);d.mkdir(exist_ok=False);ipc=Path(tempfile.mkdtemp(prefix='nxrp-',dir='/private/tmp'));ep=actors.Endpoint(ipc/'m.sock')
    config=dict(config,sources=hashes(),criteria_sha256=hashlib.sha256((ROOT/'docs/research/RESTART_EXPERIMENT_ACCEPTANCE_RP01_2026-11-17.md').read_bytes()).hexdigest());(d/'config.json').write_bytes(canonical(config)+b'\n')
    log=actors.Records(d/'orchestrator',dict(role='orchestrator',configuration_sha256=sha(config),source_sha256=config['sources']))
    children=[];streams=[];ready=set();tick=-1;killed=False;kill_tick=None;restarted=False;plant_finished=False;controller=None
    def spawn(role,generation=0,offset=0):
        path=d/(role+'-'+str(generation)+'.log');stream=path.open('xb');streams.append(stream)
        cmd=[sys.executable,'-m','aegis.development.restart_process_experiment',role,str(d/'config.json'),str(ipc),str(d),'--generation',str(generation),'--offset',str(offset)]
        p=subprocess.Popen(cmd,cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:.',PYTHONDONTWRITEBYTECODE='1'),stdout=stream,stderr=subprocess.STDOUT)
        children.append((role,generation,p));log.append('SPAWN',role=role,generation=generation,child_pid=p.pid);return p
    try:
        plant=spawn('plant');deadline=time.monotonic()+8
        while ('plant' not in ready) and time.monotonic()<deadline:
            for m in ep.drain():
                if m['kind']=='READY':ready.add(m['role'])
            if plant.poll() is not None:raise RuntimeError('plant failed before readiness')
            time.sleep(.002)
        if 'plant' not in ready:raise TimeoutError('plant startup')
        wd=spawn('watchdog');controller=spawn('controller');deadline=time.monotonic()+8
        while len(ready)<3 and time.monotonic()<deadline:
            for m in ep.drain():
                if m['kind']=='READY':ready.add(m['role'])
            if any(p.poll() is not None for _,_,p in children):raise RuntimeError('actor failed before readiness')
            time.sleep(.002)
        if len(ready)<3:raise TimeoutError('worker startup')
        ep.send(ipc/'w.sock',dict(kind='REGISTER_CONTROLLER',generation=0));log.append('START',pids={role:p.pid for role,_,p in children});ep.send(ipc/'p.sock',dict(kind='START'))
        deadline=time.monotonic()+max(10,config['steps']*config['wall_period']*4)
        while not plant_finished and time.monotonic()<deadline:
            for m in ep.drain():
                if m['role']=='plant' and 'tick' in m:tick=max(tick,m['tick'])
                if (not killed and config['scenario'] in CRASH and m['kind']==CRASH[config['scenario']] and m.get('tick',-1)>=20 and not m.get('command_id','').startswith('fixture-')):
                    log.append('CONTROLLER_KILL_REQUEST',tick=tick,child_pid=controller.pid,command_id=m['command_id'],trigger=m['kind'])
                    controller.kill();controller.wait(timeout=2);log.append('CONTROLLER_TERMINATED',tick=tick,child_pid=controller.pid,returncode=controller.returncode)
                    killed=True;kill_tick=tick
                if m['role']=='controller' and m['kind']=='READY' and m.get('generation')==1:log.append('RESTART_READY',tick=tick,child_pid=m['pid'])
                if m['role']=='plant' and m['kind']=='FINISHED':plant_finished=True
            if killed and not restarted and tick>=kill_tick+config['outage_ticks']:
                controller=spawn('controller',1,-20*tick);log.append('RESTART_SPAWN',tick=tick,child_pid=controller.pid);restarted=True
            if plant.poll() is not None and not plant_finished:
                # Drain final datagrams on next iteration before classifying exit.
                if plant.returncode!=0:raise RuntimeError('plant process failed')
            time.sleep(.001)
        if not plant_finished:raise TimeoutError('plant completion deadline')
        for role,g,p in children:
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                log.append('SHUTDOWN_TIMEOUT',role=role,generation=g,child_pid=p.pid);p.kill();p.wait(timeout=2)
            log.append('EXIT',role=role,generation=g,child_pid=p.pid,returncode=p.returncode)
        log.append('FINISHED',plant_finished=True,kill_injected=killed,restart_spawned=restarted)
    except BaseException as e:
        log.append('INCOMPLETE',error_type=type(e).__name__,error=str(e))
        raise
    finally:
        for role,g,p in children:
            if p.poll() is None:p.kill();p.wait(timeout=2);log.append('CLEANUP_KILL',role=role,generation=g,child_pid=p.pid)
        for stream in streams:stream.close()
        ep.close();shutil.rmtree(ipc)
    result=analyze_case(d)
    with (d/'measurements.json').open('xb') as f:f.write(canonical(result)+b'\n')
    return result


def reconstruct_actuator(config,events,commands):
    """Independent event reduction of queue, force, permission and power rules."""
    if config.get('protocol')!='RP01':return dict(status='NOT_ACTOR_PROTOCOL_FIXTURE',steps=0)
    special=config['scenario']=='power_loss_queued';force=Q('.8') if special else Q(0);target=force
    queue=[dict(id='fixture-'+str(n),target='.8',due=n,expires=10000,generation=-1,fixture=True) for n in range(3)] if special else []
    permission=None;previous_engaged=False;checked=0
    for r in events:
        kind=r['kind']
        if kind=='PERMISSION_RECEIVED':
            m=r['message']
            if m['issued_tick']<=r['tick'] and (permission is None or m['issued_tick']>=permission['issued_tick']):permission=m
        elif kind=='COMMAND_ACCEPTED':
            name=r['command_id'];m=r['command']
            if name not in commands or commands[name]['command']!=m or r['due_tick']!=r['tick']+3:raise ValueError('accepted command/intent mismatch')
            queue.append(dict(id=name,target=m['target'],due=r['due_tick'],expires=m['expires_tick'],generation=m['generation'],fixture=False))
        elif kind=='POWER_LOSS_FLUSH':
            if queue!=r['queue_before'] or str(force)!=r['force_before']:raise ValueError('power-loss queue/force mismatch')
            queue=[];force=Q(0);target=Q(0)
        elif kind in ('COMMAND_CONSUMED','COMMAND_RETIRED'):
            q=next((x for x in queue if x['id']==r['command_id']),None)
            if q is None or q['due']>r['tick']:raise ValueError('queue consumption/retirement mismatch')
            queue.remove(q)
            if kind=='COMMAND_CONSUMED':target=max(Q(-1),min(Q(1),Q(q['target'])))
        elif kind=='STEP_INTENT':
            allow=permission is not None and permission['allow'] and permission['expires_tick']>=r['tick'] and not previous_engaged and r['power']
            if bool(allow)!=r['permission_valid']:raise ValueError('plant permission reconstruction mismatch')
            if not allow and not special:target=Q(0)
            if r['power']:force+=max(Q('-.08'),min(Q('.08'),target-force))
            else:force=Q(0)
            if str(force)!=r['force'] or str(target)!=r['target'] or queue!=r['queue']:raise ValueError('actuator force/FIFO reconstruction mismatch')
            p,v=Q(r['position']),Q(r['velocity']);bf=max(Q(-4),min(Q(4),-4*p-3*v)) if r['backup_engaged'] else Q(0)
            if Q(r['active_force'])!=(Q(0) if r['backup_engaged'] else force) or Q(r['backup_force'])!=bf:raise ValueError('applied force/model mismatch')
            previous_engaged=r['backup_engaged'];checked+=1
    return dict(status='RECONSTRUCTED_FROM_COMMITTED_COMMAND_POWER_AND_PERMISSION_EVENTS',steps=checked)


def analyze_case(directory):
    d=Path(directory);config=json.loads((d/'config.json').read_bytes());journals={p.name:actors.read_records(p) for p in sorted(d.iterdir()) if p.is_dir()}
    if config.get('protocol')=='RP01':
        for name,j in journals.items():
            h=j['records'][0]
            if h.get('configuration_sha256')!=sha(config) or h.get('source_sha256')!=config['sources'] or any(r['pid']!=h['pid'] for r in j['records']):raise ValueError('role identity/configuration/source mismatch')
        spawned={r['child_pid'] for r in journals['orchestrator']['records'] if r['kind']=='SPAWN'}
        if any(j['records'][0]['pid'] not in spawned for name,j in journals.items() if name!='orchestrator'):raise ValueError('process spawn/header mismatch')
    plant=journals['plant']['records'];orches=journals['orchestrator']['records'];wd=journals['watchdog']['records'];controllers=[r for n,j in journals.items() if n.startswith('ctrl-') for r in j['records']]
    intents=[r for r in plant if r['kind']=='STEP_INTENT'];steps=[r for r in plant if r['kind']=='STEP_RESULT'];continuity=True;prior_p=Q(config.get('initial_position','0'));prior_v=Q(config['initial_velocity'])
    for n,(a,b) in enumerate(zip(intents,steps)):
        if a['tick']!=n or b['tick']!=n or Q(a['position'])!=prior_p or Q(a['velocity'])!=prior_v:raise ValueError('plant state/tick continuity mismatch')
        force=Q(a['active_force'])+Q(a['backup_force'])+Q('.01');p=prior_p+actors.DT*prior_v+actors.DT**2*force/2;v=prior_v+actors.DT*force
        if Q(b['position'])!=p or Q(b['velocity'])!=v or b['continuous_position']!=actors.extrema(prior_p,prior_v,force):raise ValueError('physical trajectory/extremum mismatch')
        prior_p,prior_v=p,v
    if len(intents)!=len(steps):continuity=False
    consumed=[r for r in plant if r['kind']=='COMMAND_CONSUMED' and not r['fixture']];counts=Counter(r['command_id'] for r in consumed)
    sends={r['command']['command_id']:r for r in controllers if r['kind']=='COMMAND_INTENT'}
    actuator_check=reconstruct_actuator(config,plant,sends)
    accepted={r['command_id']:r for r in plant if r['kind']=='COMMAND_ACCEPTED'}
    causal=[]
    for r in consumed:
        name=r['command_id']
        if name not in sends or name not in accepted or not sends[name]['wall_ns']<=accepted[name]['wall_ns']<=r['wall_ns']:causal.append(name)
    unsupported=[]
    highwater=-1
    for event in sorted((x for x in controllers if x['kind']=='FEEDBACK_ACCEPTED'),key=lambda x:x['wall_ns']):
        if event['sample']['tick']<=highwater:unsupported.append(dict(reason='REPLAY_ACCEPTED_ACROSS_BOOT',tick=event['tick']))
        highwater=max(highwater,event['sample']['tick'])
    for name,journal in journals.items():
        if not (name.startswith('ctrl-') or name=='watchdog'):continue
        clock=None;previous_sample=None;request_tick=None
        for r in journal['records']:
            if r['kind']=='BACKUP_SENT':request_tick=r['tick']
            if r['kind']=='BACKUP_OBSERVATION':
                expected=actors.backup_observation(previous_sample,r['sample']) if r['tick']>request_tick+4 else dict(status='HANDOFF_OBSERVATION_PENDING',operational_authorization=False)
                if expected!=r['check']:raise ValueError('backup observation reconstruction mismatch')
                previous_sample=r['sample']
            if r['kind']=='RECOVERY_LATCHED_OBSERVATION':
                if actors.backup_observation(previous_sample,r['sample'])!=r['check']:raise ValueError('controller recovery observation mismatch')
                previous_sample=r['sample']
            if r['kind']=='CLOCK_MAP':clock=actors.make_map(r['message'])
            if r['kind']=='ASSESSMENT':
                previous_sample=r['sample']
                result=r['result'];boot='wd-0' if name=='watchdog' else name
                rebuilt=actors.assessment(r['packet'],r['now_local'],clock,boot,boot,r.get('healthy',True))
                if result!=rebuilt:raise ValueError('claim/clock/input reconstruction mismatch')
                if result['conditional_continuous_containment']:
                    actual=max((s['tick']+1 for s in steps if s['wall_ns']<=r['wall_ns']),default=0)
                    if clock is None or result['status']!='CONDITIONAL_PHYSICAL_TIME_PLAN' or actual>r['valid_until_tick']:
                        unsupported.append(dict(role=name,tick=r['tick'],reason='UNSUPPORTED_OR_EXPIRED_AT_ISSUE',actual_plant_tick=actual))
    kill=next((r for r in orches if r['kind']=='CONTROLLER_KILL_REQUEST'),None);ready=next((r for r in orches if r['kind']=='RESTART_READY'),None)
    during=[r for r in steps if kill is not None and r['wall_ns']>kill['wall_ns'] and (ready is None or r['wall_ns']<ready['wall_ns'])]
    disposition={}
    for r in plant:
        if r['kind'] in ('COMMAND_ACCEPTED','COMMAND_REJECTED'):disposition[r['command_id']]=r['status']
        if r['kind']=='COMMAND_CONSUMED' and not r['fixture']:disposition[r['command_id']]='CONSUMED'
        if r['kind']=='COMMAND_RETIRED':disposition[r['command_id']]='REJECTED_AT_CONSUMPTION'
    belief={}
    for r in sorted(controllers,key=lambda x:x['wall_ns']):
        if r['kind']=='COMMAND_INTENT':belief[r['command']['command_id']]='UNKNOWN'
        if r['kind']=='ACK':belief[r['command_id']]=r['status']
        if r['kind']=='QUERY_RESULT':belief.update(r['states'])
    detect=next((r for r in wd if r['kind']=='FAILURE_DETECTED'),None);engage=next((r for r in plant if r['kind']=='BACKUP_ENGAGED'),None)
    reconstruct=next((r for r in journals.get('ctrl-1',dict(records=[]))['records'] if r['kind']=='RECONSTRUCTION'),None)
    post_assess=next((r for r in journals.get('ctrl-1',dict(records=[]))['records'] if r['kind']=='ASSESSMENT'),None)
    first_failure_tick=kill['tick'] if kill else (40 if config['scenario']=='clock_reset' else (config.get('power_loss_tick',30) if config['scenario'] in ('power_loss_queued','backup_delayed','backup_unavailable') else 30 if config['scenario'] in ('malformed_feedback','progressive_staleness') else (20 if config['scenario'] in ('duplicate_requests','conflicting_duplicate','replayed_feedback') else (0 if config['scenario'] in ('lost_acknowledgements','unsupported_start') else None))))
    candidates=[x for x in wd+controllers+plant if x['kind'] in ('FAILURE_DETECTED','REPLAY_IGNORED','ACK_TIMEOUT','DUPLICATE_IGNORED','CONFLICT_REJECTED','CLOCK_EPOCH_CHANGED') and first_failure_tick is not None and x.get('tick',-1)>=first_failure_tick]
    detect=min(candidates,key=lambda x:x['wall_ns']) if candidates else None
    if reconstruct is not None:reconstruct=dict(reconstruct,tick=max((x['tick']+1 for x in steps if x['wall_ns']<=reconstruct['wall_ns']),default=0))
    latency=lambda r:None if r is None or first_failure_tick is None or 'tick' not in r else (dict(classification='PREEXISTING_EVENT_NOT_RECOVERY',ticks=None,virtual_seconds=None) if r['tick']<first_failure_tick else dict(ticks=r['tick']-first_failure_tick,virtual_seconds=str((r['tick']-first_failure_tick)*actors.DT)))
    kval=not config['scenario'] in CRASH or (kill is not None and ready is not None and len(during)>=8)
    ordering=None
    if kill:
        target=kill['command_id'];effect=next((r for r in consumed if r['command_id']==target),None)
        ordering=dict(command_id=target,trigger=kill['trigger'],consumed_wall_ns=None if effect is None else effect['wall_ns'],kill_wall_ns=kill['wall_ns'],qualified=effect is None or (effect['wall_ns']>kill['wall_ns'] if kill['trigger']=='COMMAND_ACCEPTED' else effect['wall_ns']<kill['wall_ns']))
        kval=kval and ordering['qualified']
    pids={n:j['records'][0]['pid'] for n,j in journals.items() if n!='orchestrator'}
    distinct=len(set(pids.values()))==len(pids)
    exits=[x for x in orches if x['kind']=='EXIT']
    protocol_complete=bool(exits) and all(x['returncode']==0 or (config['scenario'] in CRASH and x['role']=='controller' and x['generation']==0 and x['returncode']==-9) for x in exits) and not any(x['kind'] in ('SHUTDOWN_TIMEOUT','INCOMPLETE','CLEANUP_KILL') for x in orches)
    violations=[r['tick'] for r in steps if Q(r['continuous_position'][0])<Q('-.5') or Q(r['continuous_position'][1])>Q('.32')]
    return dict(scenario=config['scenario'],configuration_sha256=sha(config),source_sha256=config['sources'],
        execution=dict(role_protocol_complete=protocol_complete,actuator_reconstruction=actuator_check,actor_exits=[x for x in orches if x['kind']=='EXIT'],plant_steps=len(steps),expected_steps=config['steps'],plant_complete=len(steps)==config['steps'] and continuity,distinct_actor_pids=distinct,actor_pids=pids,crash_injection_qualified=kval,crash_ordering=ordering,pending_record_counts={n:len(j['pending']) for n,j in journals.items()},uncommitted_pending_counts={n:sum(not x['committed_alias'] for x in j['pending']) for n,j in journals.items()}),
        trajectory_containment=dict(continuous_ideal_position_contained=not violations,violation_ticks=violations,between_sample_extrema_checked=len(steps)),
        unsupported_claims=dict(at_issue=unsupported,causality_violations=causal,nominal_requests_after_recovery_observation=[x['command']['command_id'] for name,j in journals.items() if name.startswith('ctrl-') for x in j['records'] if x['kind']=='COMMAND_INTENT' and any(y['kind']=='RECOVERY_LATCHED_OBSERVATION' and y['wall_ns']<x['wall_ns'] for y in j['records'])],conditional_claim_count=sum(r['kind']=='ASSESSMENT' and r['result']['conditional_continuous_containment'] for r in controllers+wd),backup_status_deadline_misses=[r for r in wd if r['kind']=='BACKUP_ENGAGEMENT_UNCONFIRMED'],backup_model_contradictions=[r['tick'] for r in wd if r['kind']=='BACKUP_OBSERVATION' and r['check']['status']=='BACKUP_MODEL_OR_FEEDBACK_CONTRADICTION'],actual_backup_premise_fault=config['scenario'] in ('backup_delayed','backup_unavailable')),
        uncertain_effects=dict(controller_unknown_ids=[k for k,v in belief.items() if v=='UNKNOWN'],controller_queued_ids=[k for k,v in belief.items() if v=='QUEUED'],plant_disposition=disposition,restart_reconstruction=None if reconstruct is None else reconstruct['uncertain']),
        duplicate_effects=dict(repeated_consumptions={k:n for k,n in counts.items() if n>1},duplicate_rejections=sum(r['kind']=='DUPLICATE_IGNORED' for r in plant),conflict_rejections=sum(r['kind']=='CONFLICT_REJECTED' for r in plant)),
        recovery_latency=dict(failure_onset_tick=first_failure_tick,detection=latency(detect),detection_kind=None if detect is None else detect['kind'],controller_reconstruction=latency(reconstruct),controller_reconstruction_wall_ns=None if reconstruct is None else reconstruct['wall_ns'],postrestart_assessment=latency(post_assess),handoff=latency(engage),handoff_tick=None if engage is None else engage['tick'],plant_updates_during_controller_outage=len(during)),
        nominal_control_availability=dict(new_consumptions_without_permission=[r['command_id'] for r in consumed if not r['permission_valid']],primary_powered_steps=sum(x['power'] for x in intents),permission_steps=sum(x['permission_valid'] for x in intents),backup_engaged_steps=sum(x['backup_engaged'] for x in intents)),
        injections=dict(replayed_feedback=sum(r['kind']=='FEEDBACK_REPLAY_INJECTED' for r in plant),replays_rejected=sum(r['kind']=='REPLAY_IGNORED' for r in controllers),acks_dropped=sum(r['kind']=='ACK_DROPPED' for r in plant),clock_resets=sum(r['kind']=='SENSOR_CLOCK_RESET' for r in plant),power_loss_while_queued_exposed=any(r['kind']=='POWER_LOSS_FLUSH' and len(r['queue_before'])>0 and not any(x['kind']=='BACKUP_ENGAGED' and x['tick']<=r['tick'] for x in plant) for r in plant),power_loss_queue_records=[r for r in plant if r['kind']=='POWER_LOSS_FLUSH']),
        governance=dict(gate_b='GATE_B_NOT_AUTHORIZED',hardware_validation=False,operational_authorization=False),classification='SIX_SEPARATE_DEVELOPMENT_OUTCOMES_NO_AGGREGATE_PASS_FAIL')


def run(directory,scenarios=None):
    d=Path(directory);d.mkdir(exist_ok=False);assignments=[a for a in plan() if scenarios is None or a['id'] in scenarios];sources=hashes();results=[]
    with DevelopmentLedger.create(d/'assignments.jsonl',study='RP01 independent-process restart development',assignments=[dict(a,source_sha256=sources) for a in assignments]) as ledger:
        for a in assignments:
            ledger.start(a['id'])
            try:
                r=run_case(a,d/a['id'])
                if hashes()!=sources:raise ValueError('source changed during experiment')
                status='COMPLETED' if r['execution']['plant_complete'] and r['execution']['role_protocol_complete'] and r['execution']['crash_injection_qualified'] else 'ERROR'
                ledger.complete(a['id'],status=status,details=dict(measurements_sha256=sha(r),plant_complete=r['execution']['plant_complete'],role_protocol_complete=r['execution']['role_protocol_complete'],crash_injection_qualified=r['execution']['crash_injection_qualified']));results.append(r)
                print(json.dumps(dict(case=a['id'],steps=r['execution']['plant_steps'],outage_updates=r['recovery_latency']['plant_updates_during_controller_outage'],violations=len(r['trajectory_containment']['violation_ticks']))),flush=True)
            except Exception as e:ledger.complete(a['id'],status='ERROR',details=dict(error_type=type(e).__name__,error=str(e)));print(json.dumps(dict(case=a['id'],error=str(e))),flush=True)
        ledger.finalize()
    return dict(source_sha256=sources,results=results,gate_b='GATE_B_NOT_AUTHORIZED',aggregate_pass_fail=None)


def audit(directory):
    d=Path(directory);ledger=inspect(d/'assignments.jsonl');header=ledger['records'][0];sources=hashes()
    if header['study']!='RP01 independent-process restart development':raise ValueError('study identity mismatch')
    expected={a['id']:a for a in plan()};assignments=header['assignments'];results=[]
    if any(a['id'] not in expected or {k:v for k,v in a.items() if k!='source_sha256'}!=expected[a['id']] or a['source_sha256']!=sources for a in assignments):raise ValueError('plan/source mismatch')
    terminals={r['id']:r for r in ledger['records'] if r['kind']=='TERMINAL'}
    expected_dirs={a['id'] for a in assignments if (d/a['id']).is_dir()}
    if {p.name for p in d.iterdir() if p.is_dir()}!=expected_dirs:raise ValueError('unexpected case directory')
    for a in assignments:
        terminal=terminals.get(a['id']);path=d/a['id']
        if terminal is None or terminal['status']!='COMPLETED':continue
        config=json.loads((path/'config.json').read_bytes())
        if config['sources']!=sources or {k:config[k] for k in expected[a['id']]}!=expected[a['id']]:raise ValueError('case configuration mismatch')
        if config['criteria_sha256']!=hashlib.sha256((ROOT/'docs/research/RESTART_EXPERIMENT_ACCEPTANCE_RP01_2026-11-17.md').read_bytes()).hexdigest():raise ValueError('criteria identity mismatch')
        rebuilt=analyze_case(path)
        if canonical(rebuilt)+b'\n'!=(path/'measurements.json').read_bytes() or terminal['details']['measurements_sha256']!=sha(rebuilt):raise ValueError('measurement/terminal reconstruction mismatch')
        results.append(rebuilt)
    return dict(source_sha256=sources,results=results,ledger_state=ledger['state'],counts=ledger['counts'],gate_b='GATE_B_NOT_AUTHORIZED',aggregate_pass_fail=None)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--scenarios',nargs='*');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    if a.mode=='run':r=run(a.directory,a.scenarios)
    else:r=audit(a.directory)
    with a.output.open('xb') as f:f.write(canonical(r)+b'\n')


if __name__=='__main__':main()
