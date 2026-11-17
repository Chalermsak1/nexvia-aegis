"""LIVE01 independent-process development campaign and read-only evidence audit."""
from pathlib import Path
from fractions import Fraction as Q
from collections import Counter
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,time
from aegis.development import live_recovery_contract as contract
from aegis.development import evidence_recovery as adapter
from aegis.development.recovery_evidence import EvidenceReplay,inspect as inspect_evidence
from aegis.development.restart_process_experiment import Records,Endpoint,read_records,DT,extrema,backup_observation
from aegis.development.durable_feedback_session import canonical,sha
from scripts.research import evidence_recovery_study as prior
from scripts.research.development_ledger import DevelopmentLedger,inspect

ROOT=Path(__file__).resolve().parents[2]
NEW_FILES=('src/aegis/development/live_recovery_contract.py','src/aegis/development/live_recovery_processes.py','src/aegis/development/live_evidence_bundle.py','scripts/research/live_recovery_study.py','tests/test_live_recovery_contract.py','tests/test_live_recovery_processes.py','tests/test_live_recovery_study.py','docs/research/ADR_LIVE01_PROCESS_EVIDENCE_INTEGRATION_2026-11-17.md','docs/research/LIVE01_FRESHNESS_FALSIFICATION_ADDENDUM_2026-11-17.md','docs/research/LIVE01_COMPUTATION_WINDOW_ADDENDUM_2026-11-17.md','docs/research/LIVE01_ATOMIC_FRAME_PERSISTENCE_ADDENDUM_2026-11-17.md')
SCENARIOS=('nominal','terminate_before_consumption','terminate_after_consumption','watchdog_restart','lost_acknowledgements','duplicate_requests','conflicting_duplicate','replayed_feedback','progressive_staleness','clock_reset','session_reset','permanent_partition','queue_delay','revocation_queued','compute_delay','clock_reader_failure','storage_commit_delay','power_loss_queued','backup_delayed','backup_unavailable','malformed_feedback','source_mismatch','contradictory_model','restart_lost_ack_replay','retimestamped_freeze')
CRASH={'terminate_before_consumption':('controller','COMMAND_ACCEPTED'),'terminate_after_consumption':('controller','COMMAND_CONSUMED'),'session_reset':('controller','COMMAND_CONSUMED'),'restart_lost_ack_replay':('controller','COMMAND_CONSUMED'),'watchdog_restart':('watchdog','LEASE_ACCEPTED')}


def hashes():return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(tuple(prior.hashes())+NEW_FILES))}
def plan():return [dict(id=arm+'_'+s,arm=arm,scenario=s,steps=140,wall_period=.03,fault_tick=18,outage_ticks=12,initial_velocity='.3',assessment_mode='STATE_TUBE_WINDOW_V1',evidence_backend='ATOMIC_BUNDLE_V1') for arm,names in [('SIMULATION_CONTRACT_CHECKS',SCENARIOS),('STRICT_OBSERVATIONS',('nominal','clock_reset','permanent_partition','retimestamped_freeze'))] for s in names]
def public_for(a,*,sources):return dict(schema='LIVE01_PUBLIC',run_id=sha(a),sources=sources,model=contract.model_contract(),arm=a['arm'],steps=a['steps'],wall_period=a['wall_period'],assessment_mode=a.get('assessment_mode','SNAPSHOT_SAME_TICK'),evidence_backend=a.get('evidence_backend','PER_RECORD_JOURNAL_V1'),max_observation_host_ns=120000000,computation_budget_ns=25000000,lease_host_ns=160000000)
def save(path,value):contract.save(path,value)


def run_case(assignment,directory):
    d=Path(directory);d.mkdir(exist_ok=False);sources=hashes();public=public_for(assignment,sources=sources);save(d/'assignment.json',assignment);save(d/'public.json',public);save(d/'fault.json',{k:assignment[k] for k in ('scenario','fault_tick','initial_velocity')})
    ipc=Path(tempfile.mkdtemp(prefix='nxli-',dir='/private/tmp'));ep=Endpoint(ipc/'m.sock');log=Records(d/'orchestrator',dict(role='orchestrator',assignment_sha256=sha(assignment),public_sha256=sha(public),source_sha256=sources));children=[];streams=[];ready=set();tick=-1;kill_tick=None;killed=False;restarted=False;injected=False;finished=False;active={}
    def spawn(role,generation=0):
        if role=='watchdog' and generation and (ipc/'w.sock').exists():(ipc/'w.sock').unlink();log.append('IPC_STALE_SOCKET_REMOVED',role=role,generation=generation)
        stream=(d/f'{role}-{generation}.log').open('xb');streams.append(stream)
        argv=[sys.executable,'-m','aegis.development.live_recovery_processes',role,str(d/'public.json'),str(ipc),str(d),'--generation',str(generation)]
        if role=='plant':argv+=['--fault',str(d/'fault.json')]
        p=subprocess.Popen(argv,cwd=ROOT,env=dict(os.environ,PYTHONPATH='src:.',PYTHONDONTWRITEBYTECODE='1'),stdout=stream,stderr=subprocess.STDOUT);children.append((role,generation,p));active[role]=p;log.append('SPAWN',role=role,generation=generation,child_pid=p.pid,argv=argv);return p
    try:
        plant=spawn('plant');deadline=time.monotonic()+8
        while 'plant' not in ready and time.monotonic()<deadline:
            for m in ep.drain():
                if m['kind']=='READY':ready.add(m['role'])
            if plant.poll() is not None:raise RuntimeError('plant failed before readiness')
            time.sleep(.002)
        if 'plant' not in ready:raise TimeoutError('plant startup')
        spawn('watchdog');spawn('controller');deadline=time.monotonic()+8
        while len(ready)<3 and time.monotonic()<deadline:
            for m in ep.drain():
                if m['kind']=='READY':ready.add(m['role'])
            if any(p.poll() is not None for _,_,p in children):raise RuntimeError('actor failed before readiness')
            time.sleep(.002)
        if len(ready)<3:raise TimeoutError('worker startup')
        log.append('START',pids={r:p.pid for r,p in active.items()});ep.send(ipc/'p.sock',dict(kind='START'));deadline=time.monotonic()+max(12,assignment['steps']*assignment['wall_period']*4)
        while not finished and time.monotonic()<deadline:
            for m in ep.drain():
                if m['role']=='plant' and 'tick' in m:tick=max(tick,m['tick'])
                scenario=assignment['scenario']
                if scenario in CRASH and not killed and m['kind']==CRASH[scenario][1] and m.get('tick',-1)>=assignment['fault_tick']:
                    role=CRASH[scenario][0];p=active[role];kill_tick=m['tick'];log.append('KILL_REQUEST',role=role,tick=kill_tick,child_pid=p.pid,trigger=m['kind'],command_id=m.get('command_id'),lease_id=m.get('lease_id'))
                    p.kill();p.wait(timeout=2);log.append('TERMINATED',role=role,tick=kill_tick,child_pid=p.pid,returncode=p.returncode);killed=True
                if m['kind']=='READY' and m.get('generation')==1:log.append('RESTART_READY',role=m['role'],tick=tick,child_pid=m['pid'])
                if m['role']=='plant' and m['kind']=='FINISHED':finished=True
            if not injected and tick>=assignment['fault_tick']:
                message=None;target=None
                if assignment['scenario'] in ('duplicate_requests','conflicting_duplicate'):message=dict(kind='INJECT_DUPLICATES',changed=assignment['scenario']=='conflicting_duplicate');target=ipc/'c0.sock'
                if assignment['scenario']=='compute_delay':message=dict(kind='INJECT_COMPUTE_DELAY',seconds=.2);target=ipc/'w.sock'
                if assignment['scenario']=='clock_reader_failure':message=dict(kind='INJECT_CLOCK_FAILURE');target=ipc/'w.sock'
                if message is not None:sent=ep.send(target,message);log.append('ADMIN_FAULT_SENT',tick=tick,message=message,delivered_to_socket=sent)
                injected=True
            if killed and not restarted and tick>=kill_tick+assignment['outage_ticks']:
                role=CRASH[assignment['scenario']][0];spawn(role,1);log.append('RESTART_SPAWN',tick=tick,role=role);restarted=True
            if plant.poll() is not None and plant.returncode!=0:raise RuntimeError('plant process failed')
            time.sleep(.001)
        if not finished:raise TimeoutError('plant completion')
        log.append('ADMINISTRATIVE_END',tick=tick)
        ep.send(ipc/'w.sock',dict(kind='STOP',administrative=True));ep.send(ipc/('c1.sock' if restarted and CRASH.get(assignment['scenario'],('',''))[0]=='controller' else 'c0.sock'),dict(kind='STOP',administrative=True))
        for role,g,p in children:
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:log.append('SHUTDOWN_TIMEOUT',role=role,generation=g);p.kill();p.wait(timeout=2)
            log.append('EXIT',role=role,generation=g,child_pid=p.pid,returncode=p.returncode)
        log.append('FINISHED')
    except BaseException as exc:log.append('INCOMPLETE',error_type=type(exc).__name__,error=str(exc));raise
    finally:
        for role,g,p in children:
            if p.poll() is None:p.kill();p.wait(timeout=2);log.append('CLEANUP_KILL',role=role,generation=g)
        for f in streams:f.close()
        ep.close();shutil.rmtree(ipc)
    if hashes()!=sources:raise ValueError('source changed during case')
    r=analyze_case(d);save(d/'measurements.json',r);return r


def audit_frame(root,relative,public):
    path=root/relative;basis=json.loads(path.read_bytes())
    if canonical(basis)+b'\n'!=path.read_bytes() or basis['public_sha256']!=sha(public):raise ValueError('basis bytes/contract mismatch')
    if basis['result'] is None:
        if basis['reason']!='COLLECTOR_OR_ASSESSMENT_FAILURE':raise ValueError('unexplained missing assessment')
        return basis
    inputs,rows,provenance=contract.collect(basis['sample'],basis['beacon_before'],public,basis['boot'],primary_healthy=basis['primary_healthy'])
    directory=path.parent
    if rows!=json.loads((directory/'artifacts.json').read_bytes()) or provenance!=basis['provenance']:raise ValueError('collector witness reconstruction mismatch')
    if public.get('evidence_backend')=='ATOMIC_BUNDLE_V1':
        from aegis.development.live_evidence_bundle import BundleReplay
        replay=BundleReplay(directory/'evidence_bundle.json');records=replay.records;header=replay.header
    else:
        journal=inspect_evidence(directory/'evidence');records=journal['records'];header=journal['header'];replay=EvidenceReplay(directory/'evidence')
    if header['policy']!=contract.policy() or basis['evidence_backend']!=public['evidence_backend']:raise ValueError('frame policy/backend mismatch')
    recorded=[r['payload']['artifact'] for r in records if r['payload'].get('kind')=='ARTIFACT']
    if recorded!=rows:raise ValueError('committed witnesses differ')
    finish=basis['adapter_finish_beacon']
    tube=public.get('assessment_mode')=='STATE_TUBE_WINDOW_V1'
    rebuilt=adapter.assess(replay,inputs,finish_clock=lambda:0 if tube else 20*(basis['beacon_before'] if finish is None else finish)['tick'])
    if rebuilt!=basis['result'] or replay.index!=len(replay.records):raise ValueError('live EA01 assessment reconstruction mismatch')
    expected_time=dict(kind='STATE_TUBE_WINDOW_V1' if tube else 'SNAPSHOT_SAME_TICK',source_tick=basis['sample']['tick'],source_host_ns=basis['sample']['emitted_host_ns'],reference_tick=0 if tube else 20*basis['beacon_before']['tick'],max_cursor_advance=1 if tube else 0,state_transport_horizon_seconds=str(DT*(basis['beacon_before']['tick']-basis['sample']['tick']+2) if tube else DT))
    if basis['time_basis']!=expected_time:raise ValueError('time-window derivation differs')
    reason=contract.completion_reason(basis,public)
    if reason!=basis['reason']:raise ValueError('live completion gate reconstruction mismatch')
    return basis


def analyze_case(directory):
    d=Path(directory);assignment=json.loads((d/'assignment.json').read_bytes());public=json.loads((d/'public.json').read_bytes())
    if public!=public_for(assignment,sources=public['sources']):raise ValueError('public contract differs')
    fault=json.loads((d/'fault.json').read_bytes())
    if fault!={k:assignment[k] for k in ('scenario','fault_tick','initial_velocity')}:raise ValueError('fault plan differs')
    journals={p.name:read_records(p) for p in d.iterdir() if p.is_dir() and (p.name in ('plant','orchestrator') or p.name.startswith(('controller-','watchdog-')))}
    for name,j in journals.items():
        h=j['records'][0]
        if h['source_sha256']!=public['sources'] or h['public_sha256']!=sha(public) or any(x['pid']!=h['pid'] for x in j['records']):raise ValueError('role/source/public identity mismatch')
    plant=journals['plant']['records'];orches=journals['orchestrator']['records'];controllers=[r for n,j in journals.items() if n.startswith('controller-') for r in j['records']];watchdogs=[r for n,j in journals.items() if n.startswith('watchdog-') for r in j['records']]
    pids={n:j['records'][0]['pid'] for n,j in journals.items() if n!='orchestrator'}
    spawned={x['child_pid'] for x in orches if x['kind']=='SPAWN'}
    if set(pids.values())!=spawned:raise ValueError('spawned process identities differ')
    frames={};unsupported=[];withheld=Counter()
    for r in watchdogs:
        if r['kind']=='ASSESSMENT':
            basis=audit_frame(d,r['basis_path'],public)
            if sha(basis)!=r['basis_sha256']:raise ValueError('assessment record binding differs')
            if any(basis.get(k) is not False for k in ('operational_authorization','hardware_validation','independent_attestation')) or basis.get('future_physical_assumptions')!=list(contract.ASSUMED):raise ValueError('assessment scope/authority metadata differs')
            frames[r['basis_path']]=basis
            if basis['reason'] is not None:withheld[basis['reason']]+=1
        if r['kind']=='LEASE_ISSUED':
            lease=r['lease'];basis=contract.load_basis(d,lease)
            if lease['basis_path'] not in frames or frames[lease['basis_path']]!=basis:raise ValueError('lease precedes committed assessment')
            relative=str(Path(lease['basis_path']).parent)
            rebuilt=contract.make_lease(basis,relative,public,generation=lease['watchdog_generation'],seq=lease['seq'],issue_host_ns=lease['issued_host_ns'],issue_beacon=r['issue_beacon'])
            if rebuilt!=lease:raise ValueError('lease construction differs')
            if public['arm']=='STRICT_OBSERVATIONS' or r['wall_ns']>=lease['expires_host_ns']:unsupported.append(dict(kind='UNSUPPORTED_OR_EXPIRED_LEASE',lease_id=lease['id']))
    # Independently rebuild actuator history, queue, guard results and physics.
    position=Q(0);velocity=Q(assignment['initial_velocity']);force=Q(0);target=Q(0);queue=[];power=True;latched=False;engaged=False;backup_due=None;cg=0;wg=0;epoch='sensor-0';barrier=-1;leases={};latest=None;steps=[];intents=[];consumption_checks={};consumed=[];dispositions={};acceptance_checks={};commands={r['command']['command_id']:r for r in controllers if r['kind']=='COMMAND_INTENT'}
    for r in plant:
        kind=r['kind']
        if kind=='REGISTERED_CONTROLLER':cg=r['generation']
        if kind=='REGISTERED_WATCHDOG':wg=r['generation'];barrier=-1
        if kind=='CLOCK_EPOCH_RESET':epoch=r['epoch']
        if kind=='LOCAL_EVIDENCE_REVOKED':barrier=r['revoked_seq']
        if kind=='REVOCATION_RECEIVED':barrier=r['revoked_seq']
        if kind=='POWER_LOSS':
            if queue!=r['queue_before'] or Q(r['force_before'])!=force:raise ValueError('power loss hides queue/force')
            power=False;force=Q(0);target=Q(0)
        if kind=='BACKUP_REQUESTED':latched=True;target=Q(0)
        if kind=='BACKUP_ACCEPTED':
            expected_due=r['tick']+(15 if assignment['scenario']=='backup_delayed' else 3)
            if backup_due is not None or r['due']!=expected_due:raise ValueError('backup acceptance timing/state differs')
            backup_due=r['due']
        if kind=='BACKUP_ENGAGED':
            if engaged or backup_due is None or r['tick']<backup_due or assignment['scenario']=='backup_unavailable':raise ValueError('backup engagement differs')
            engaged=True
        if kind in ('LEASE_ACCEPTANCE_CHECK','COMMAND_ACCEPTANCE_CHECK','CONSUMPTION_CHECK'):
            args=r['arguments'];check=contract.lease_check(r['lease'],**args)
            if check!=r['check'] or any(args[k]!=v for k,v in dict(now_tick=r['tick'],controller_generation=cg,watchdog_generation=wg,source_epoch=epoch,public_sha256=sha(public),revoked_seq=barrier,primary_power=power,recovery_latched=latched).items()):raise ValueError('lifecycle guard/local state differs')
            if kind=='CONSUMPTION_CHECK':consumption_checks[r['command_id']]=r
            if kind=='COMMAND_ACCEPTANCE_CHECK':acceptance_checks[r['command_id']]=r
        if kind=='MALFORMED_COMMAND_REJECTED':
            m=r['command'];validation=contract.command_check(m,expected_reply=str(Path(next(x['argv'][5] for x in orches if x['kind']=='SPAWN' and x['role']=='plant'))/f'c{cg}.sock'))
            if validation!=r['validation'] or validation['valid']:raise ValueError('malformed request classification differs')
            if type(m.get('command_id')) is str and m['command_id'] not in dispositions:dispositions[m['command_id']]='REJECTED_MALFORMED'
        if kind=='LEASE_ACCEPTED':
            candidates=[x['lease'] for x in plant if x['kind']=='LEASE_ACCEPTANCE_CHECK' and x['lease']['id']==r['lease_id'] and x['check']['allowed'] and x['basis_error'] is None]
            if not candidates:raise ValueError('lease accepted without support')
            latest=candidates[-1];leases[latest['id']]=latest
        if kind=='COMMAND_ACCEPTED':
            m=r['command'];name=m['command_id']
            if name not in commands or commands[name]['command']!=m or commands[name]['wall_ns']>r['wall_ns']:raise ValueError('command intent missing or late')
            accepted=acceptance_checks.get(name)
            if name in dispositions or accepted is None or not accepted['check']['allowed'] or m['basis_sha256']!=accepted['lease']['basis_sha256'] or m['generation']!=cg or r['due']!=r['tick']+3:raise ValueError('command acceptance/evidence binding differs')
            dispositions[name]='QUEUED'
            queue.append(dict(command=m,due=r['due']))
        if kind=='COMMAND_REJECTED':dispositions[r['command_id']]='REJECTED_AT_ACCEPTANCE'
        if kind=='QUEUE_DELAY_INJECTED':
            if r['queue_before']!=queue or r['queue_after']!=[dict(x,due=x['due']+6) for x in queue]:raise ValueError('queue-delay history differs')
            queue=r['queue_after']
        if kind in ('COMMAND_CONSUMED','COMMAND_RETIRED'):
            name=r['command_id'];q=next((q for q in queue if q['command']['command_id']==name),None)
            if q is None:raise ValueError('effect/retirement without queued command')
            queue.remove(q)
            if kind=='COMMAND_CONSUMED':
                c=consumption_checks.get(name)
                if c is None or not c['check']['allowed'] or c['basis_error'] is not None or not c['allowed'] or q['due']>r['tick']:raise ValueError('consumption without valid guard')
                lease=c['lease'];contract.load_basis(d,lease)
                if contract.lease_check(lease,**r['final_arguments'])!=r['final_check'] or not r['final_check']['allowed']:raise ValueError('final consumption guard differs')
                if not r['final_arguments']['now_host_ns']<=r['applied_host_ns']<=r['wall_ns']:raise ValueError('effect timestamp ordering differs')
                if r['applied_host_ns']>=lease['expires_host_ns']:unsupported.append(dict(kind='NATIVE_EXPIRY_AT_TARGET_APPLICATION',command_id=name))
                target=max(Q(-1),min(Q(1),Q(q['command']['target'])))
                if str(target)!=r['target']:raise ValueError('target/clamp differs')
                consumed.append(r)
                dispositions[name]='CONSUMED'
            else:dispositions[name]=r['reason']
        if kind=='STEP_INTENT':
            if r['tick']!=len(intents) or Q(r['position'])!=position or Q(r['velocity'])!=velocity:raise ValueError('state/tick discontinuity')
            check=contract.lease_check(r['active_lease'],**r['active_arguments'])
            if check!=r['active_check'] or r['active_lease']!=latest or r['power']!=power or r['recovery_latched']!=latched or r['backup_engaged']!=engaged or any(r['active_arguments'][k]!=v for k,v in dict(now_tick=r['tick'],controller_generation=cg,watchdog_generation=wg,source_epoch=epoch,revoked_seq=barrier,primary_power=power,recovery_latched=latched,public_sha256=sha(public)).items()):raise ValueError('active guard/state differs')
            if not check['allowed'] or latched:target=Q(0)
            force=force+max(Q('-.08'),min(Q('.08'),target-force)) if power else Q(0)
            active=Q(0) if engaged else force;bf=max(Q(-4),min(Q(4),-4*position-3*velocity)) if engaged else Q(0)
            if queue!=r['queue'] or any(Q(r[k])!=v for k,v in dict(force=force,target=target,active_force=active,backup_force=bf).items()):raise ValueError('actuator force/FIFO differs')
            intents.append(r)
        if kind=='STEP_RESULT':
            intent=intents[len(steps)];acc=Q(intent['active_force'])+Q(intent['backup_force'])+Q('.01');pn=position+DT*velocity+DT*DT*acc/2;vn=velocity+DT*acc
            if r['tick']!=len(steps) or Q(r['position'])!=pn or Q(r['velocity'])!=vn or r['continuous_position']!=extrema(position,velocity,acc):raise ValueError('trajectory/intersample extremum differs')
            position,velocity=pn,vn;steps.append(r)
    if len(intents)!=len(steps):raise ValueError('unfinished physical step')
    truth={0:(Q(0),Q(assignment['initial_velocity']))};truth.update({r['tick']+1:(Q(r['position']),Q(r['velocity'])) for r in steps});emitted={};measurement_failures=set();calibration_records=[]
    from aegis.development.recovery_feedback_state_1d import _bounds
    for r in plant:
        if r['kind']=='SENSOR_EMITTED':
            sample=r['sample'];emitted.setdefault(sample['id'],set()).add(sha(sample))
            try:
                actual=truth[sample['tick']]
                if not _bounds(sample['position']).contains(actual[0]) or not _bounds(sample['velocity']).contains(actual[1]):measurement_failures.add(sample['id']);calibration_records.append(dict(sample_id=sample['id'],source_tick=sample['tick'],actual_position=str(actual[0]),actual_velocity=str(actual[1])))
            except (ValueError,TypeError,KeyError):pass  # malformed data are separately retained/rejected
    for r in controllers+watchdogs:
        if r['kind']=='FEEDBACK_ACCEPTED' and sha(r['sample']) not in emitted.get(r['sample']['id'],set()):raise ValueError('used observation lacks source emission evidence')
    for r in controllers:
        if r['kind']=='ISSUE_CHECK' and contract.lease_check(r['lease'],**r['arguments'])!=r['check']:raise ValueError('controller issue guard differs')
    for name,journal in journals.items():
        if not name.startswith('controller-'):continue
        latest_measurement=None;latest_grant=None
        for r in journal['records']:
            if r['kind']=='FEEDBACK_ACCEPTED':latest_measurement=r['sample']
            if r['kind']=='GRANT_RECEIVED':latest_grant=r['lease']
            if r['kind']=='COMMAND_INTENT':
                if latest_measurement is None or r['measurement_sample_id']!=latest_measurement['id'] or r['measurement_sha256']!=sha(latest_measurement) or r['lease']!=latest_grant or r['dispatch_snapshot']!='LATEST_GRANT_AND_MEASUREMENT':raise ValueError('controller dispatch did not use latest committed inputs')
    # Replay watermark and effect beliefs persist across actor generations.
    replay_violations=[]
    for records in (controllers,watchdogs):
        seen=-1
        for r in sorted(records,key=lambda x:x['wall_ns']):
            if r['kind']=='FEEDBACK_ACCEPTED':
                if r['sample']['tick']<=seen:replay_violations.append(r['sample']['id'])
                seen=max(seen,r['sample']['tick'])
    beliefs=contract.EffectBeliefs();peak_unknown=0;peak_queued=0
    for r in sorted(controllers,key=lambda x:x['wall_ns']):
        if r['kind']=='COMMAND_INTENT':beliefs.merge(r['command']['command_id'],'UNKNOWN')
        if r['kind']=='BELIEF':
            if beliefs.merge(r['command_id'],r['reported'])!=r['belief']:raise ValueError('effect belief transition differs')
        peak_unknown=max(peak_unknown,sum(v in ('UNKNOWN','EFFECT_UNCERTAIN') for v in beliefs.states.values()));peak_queued=max(peak_queued,sum(v=='QUEUED' for v in beliefs.states.values()))
    kill=next((r for r in orches if r['kind']=='KILL_REQUEST'),None);terminated=next((r for r in orches if r['kind']=='TERMINATED'),None);ready=next((r for r in orches if r['kind']=='RESTART_READY'),None)
    outage=[r['tick'] for r in steps if terminated is not None and r['wall_ns']>terminated['wall_ns'] and (ready is None or r['wall_ns']<ready['wall_ns'])]
    ordering=None;qualified=True
    if assignment['scenario'] in CRASH:
        qualified=kill is not None and terminated is not None and ready is not None and len(outage)>=8
        if kill is not None and kill['role']=='controller':
            effect=next((r for r in consumed if r['command_id']==kill['command_id']),None);ordering=effect is None or (effect['wall_ns']>kill['wall_ns'] if kill['trigger']=='COMMAND_ACCEPTED' else effect['wall_ns']<kill['wall_ns']);qualified=qualified and ordering
    queue_events=[r for r in plant if r['kind'] in ('POWER_LOSS','QUEUE_DELAY_INJECTED','LOCAL_EVIDENCE_REVOKED')]
    queued_braking=any(any(Q(x['command']['target'])<0 for x in r['queue_before']) for r in queue_events)
    if assignment['arm']=='SIMULATION_CONTRACT_CHECKS' and assignment['scenario'] in ('power_loss_queued','backup_delayed','backup_unavailable','queue_delay','revocation_queued'):qualified=qualified and queued_braking
    first_backup=next((r for r in plant if r['kind']=='BACKUP_ACCEPTED'),None)
    preempted=assignment['arm']=='SIMULATION_CONTRACT_CHECKS' and assignment['scenario']!='nominal' and first_backup is not None and first_backup['tick']<assignment['fault_tick']
    qualified=qualified and not preempted
    scenario=assignment['scenario']
    if scenario=='compute_delay':qualified=qualified and any(r['kind']=='COMPUTE_DELAY_ENABLED' for r in watchdogs) and any(b['finish_host_ns']-b['start_host_ns']>=200000000 for b in frames.values())
    if scenario=='clock_reader_failure':qualified=qualified and any(r['kind']=='CLOCK_READER_FAILURE_ENABLED' for r in watchdogs) and any(b.get('error_type')=='OSError' for b in frames.values())
    if scenario=='storage_commit_delay':qualified=qualified and any(r['kind']=='CONSUMPTION_COMMIT_DELAY' and r['duration_ns']>=200000000 for r in plant) and any(r['kind']=='COMMAND_RETIRED' and r['reason']=='REJECTED_NATIVE_EXPIRY_AT_FINALIZATION' for r in plant)
    if scenario in ('duplicate_requests','conflicting_duplicate'):qualified=qualified and any(r['kind']==('DUPLICATE_IGNORED' if scenario=='duplicate_requests' else 'CONFLICT_REJECTED') for r in plant)
    if scenario in ('replayed_feedback','restart_lost_ack_replay'):qualified=qualified and any(r['kind']=='FEEDBACK_REPLAY_INJECTED' for r in plant) and any(r['kind']=='REPLAY_IGNORED' for r in controllers+watchdogs)
    if scenario=='permanent_partition':qualified=qualified and any(r['kind']=='PARTITION_DROP' for r in plant)
    delayed_ids={q['command']['command_id'] for r in plant if r['kind']=='QUEUE_DELAY_INJECTED' for q in r['queue_before']}
    expired_delayed=[name for name,c in consumption_checks.items() if name in delayed_ids and not c['allowed'] and c['check']['reason'] in ('VIRTUAL_LEASE_EXPIRED_OR_FUTURE','NATIVE_LEASE_EXPIRED_OR_FUTURE')]
    if scenario=='queue_delay':qualified=qualified and bool(expired_delayed)
    if scenario=='retimestamped_freeze':qualified=qualified and bool(measurement_failures)
    onset=kill or next((r for r in plant if r['kind']=='FAULT_ONSET' and assignment['scenario']!='nominal'),None)
    def phase(rows,kind):
        event=next((r for r in sorted(rows,key=lambda r:r['wall_ns']) if r['kind']==kind and (onset is None or r['wall_ns']>=onset['wall_ns'])),None)
        if event is None or onset is None:return dict(status='NOT_OBSERVED_OR_NOT_APPLICABLE',host_ns=None,virtual_ticks=None)
        return dict(status='OBSERVED',host_ns=event['wall_ns']-onset['wall_ns'],virtual_ticks=None if event.get('tick') is None else event['tick']-onset['tick'],event_wall_ns=event['wall_ns'])
    violations=[r['tick'] for r in steps if Q(r['continuous_position'][0])<Q('-.5') or Q(r['continuous_position'][1])>Q('.32')]
    exits=[r for r in orches if r['kind']=='EXIT'];complete=len(steps)==assignment['steps'] and all(r['returncode']==0 or (r['returncode']==-9 and kill is not None and r['child_pid']==kill['child_pid']) for r in exits) and len(exits)==len(spawned) and not any(r['kind'] in ('INCOMPLETE','SHUTDOWN_TIMEOUT','CLEANUP_KILL') for r in orches)
    registry=next((r['registry'] for r in reversed(plant) if r['kind']=='FINISHED'),{})
    if registry!=dispositions:raise ValueError('final registry differs from reconstructed dispositions')
    invalid_measurement_leases=[r['lease']['id'] for r in watchdogs if r['kind']=='LEASE_ISSUED' and r['lease']['sample_id'] in measurement_failures]
    effect_on_invalid_measurement=[r['command_id'] for r in consumed if consumption_checks[r['command_id']]['lease']['sample_id'] in measurement_failures]
    orphan_frames=[str(p.relative_to(d)) for p in d.glob('watchdog-*/assessments/*') if str(p.relative_to(d))+'/result.json' not in frames]
    pending_frames=[str(p.relative_to(d)) for p in d.glob('watchdog-*/assessments/*/pending_*')]
    return dict(assignment=assignment,source_sha256=public['sources'],execution=dict(process_complete=complete,distinct_actor_pids=len(set(pids.values()))==len(pids),actor_pids=pids,plant_steps=len(steps),injection_qualified=bool(qualified),crash_ordering=ordering,outage_ticks=outage,pending_role_records={n:len(j['pending']) for n,j in journals.items()},pending_frame_files=pending_frames,orphan_or_unissued_frame_directories=orphan_frames),
        trajectory_containment=dict(continuous_ideal_contained=not violations,violation_ticks=violations,intersample_segments_checked=len(steps)),
        unsupported_claims=dict(defects=unsupported,replay_violations=replay_violations,unconditional_physical_claims=sum(b.get('operational_authorization') is not False or b.get('hardware_validation') is not False for b in frames.values()),conditional_leases_issued=sum(r['kind']=='LEASE_ISSUED' for r in watchdogs),leases_with_false_measurement_premise=invalid_measurement_leases,measurement_bound_failures=calibration_records,withheld_assessments=dict(withheld),backup_deadline_misses=[r for r in watchdogs if r['kind']=='BACKUP_DEADLINE_MISSED'],backup_model_contradictions=[r['sample']['tick'] for r in watchdogs if r['kind']=='BACKUP_OBSERVATION' and r['check']['status']=='BACKUP_MODEL_OR_FEEDBACK_CONTRADICTION'],assumed_future_premises=list(contract.ASSUMED)),
        uncertain_effects=dict(final_controller_states=beliefs.states,unresolved_ids=[k for k,v in beliefs.states.items() if v in ('UNKNOWN','QUEUED','EFFECT_UNCERTAIN')],peak_unknown_ids=peak_unknown,peak_queued_ids=peak_queued,contradictory_terminal_reports=beliefs.conflicts,auditor_only_plant_dispositions=registry),
        duplicate_effects=dict(repeated_consumptions={k:v for k,v in Counter(r['command_id'] for r in consumed).items() if v>1},duplicate_rejections=sum(r['kind']=='DUPLICATE_IGNORED' for r in plant),conflict_rejections=sum(r['kind']=='CONFLICT_REJECTED' for r in plant),backup_engagement_count=sum(r['kind']=='BACKUP_ENGAGED' for r in plant)),
        recovery_latency=dict(fault_onset=None if onset is None else dict(tick=onset['tick'],host_ns=onset['wall_ns']),watchdog_detection=phase(watchdogs,'RECOVERY_LATCHED'),plant_local_detection=phase(plant,'BACKUP_REQUESTED'),backup_acceptance=phase(plant,'BACKUP_ACCEPTED'),backup_engagement=phase(plant,'BACKUP_ENGAGED'),restart_ready=phase(orches,'RESTART_READY'),reconstruction=phase(controllers+watchdogs,'RECONSTRUCTION'),post_fault_assessment=phase(watchdogs,'ASSESSMENT'),post_restart_nominal_reauthorization='NOT_IMPLEMENTED_RECOVERY_LATCH_RETAINED'),
        nominal_control_availability=dict(permission_steps=sum(r['active_check']['allowed'] for r in intents),primary_power_steps=sum(r['power'] for r in intents),controller_alive_steps=len(steps)-(len(outage) if kill is not None and kill['role']=='controller' else 0),backup_engaged_steps=sum(r['backup_engaged'] for r in intents),carried_force_without_permission_steps=sum(not r['active_check']['allowed'] and Q(r['force'])!=0 and not r['backup_engaged'] for r in intents),new_consumptions=len(consumed),unauthorized_new_consumptions=[r['command_id'] for r in consumed if not consumption_checks[r['command_id']]['check']['allowed']],consumptions_with_false_measurement_premise=effect_on_invalid_measurement),
        exposure=dict(queued_negative_braking_exposed=queued_braking,preempted_by_earlier_recovery=preempted,expired_delayed_command_ids=expired_delayed,partition_drops=sum(r['kind']=='PARTITION_DROP' for r in plant),backup_requested_events=sum(r['kind']=='BACKUP_REQUESTED' for r in plant),backup_accepted_events=sum(r['kind']=='BACKUP_ACCEPTED' for r in plant)),classification='SIX_SEPARATE_LIVE_DEVELOPMENT_OUTCOMES',aggregate_pass_fail=None,gate_b='GATE_B_NOT_AUTHORIZED',hardware_validation=False)


def run(directory,ids=None):
    d=Path(directory);d.mkdir(exist_ok=False);assignments=[a for a in plan() if ids is None or a['id'] in ids];sources=hashes();save(d/'declared_plan.json',dict(assignments=assignments,source_sha256=sources));results=[]
    with DevelopmentLedger.create(d/'assignments.jsonl',study='LIVE01 independent-process evidence development',assignments=assignments) as ledger:
        for a in assignments:
            ledger.start(a['id'])
            try:
                r=run_case(a,d/a['id']);status='COMPLETED' if r['execution']['process_complete'] and r['execution']['injection_qualified'] else 'ERROR';ledger.complete(a['id'],status=status,details=dict(measurements_sha256=sha(r),execution=r['execution']));results.append(r);print(json.dumps(dict(id=a['id'],status=status,steps=r['execution']['plant_steps'],consumptions=r['nominal_control_availability']['new_consumptions'],violations=len(r['trajectory_containment']['violation_ticks']),unresolved=len(r['uncertain_effects']['unresolved_ids']))),flush=True)
            except Exception as exc:ledger.complete(a['id'],status='ERROR',details=dict(error_type=type(exc).__name__,error=str(exc)));print(json.dumps(dict(id=a['id'],error=str(exc))),flush=True)
        ledger.finalize()
    return dict(source_sha256=sources,results=results,aggregate_pass_fail=None,gate_b='GATE_B_NOT_AUTHORIZED')


def audit(directory):
    d=Path(directory);declared=json.loads((d/'declared_plan.json').read_bytes());ledger=inspect(d/'assignments.jsonl');expected={a['id']:a for a in plan()};sources=hashes()
    if declared['source_sha256']!=sources or declared['assignments']!=ledger['records'][0]['assignments'] or any(expected.get(a['id'])!=a for a in declared['assignments']):raise ValueError('study plan/source identity differs')
    terminals={r['id']:r for r in ledger['records'] if r['kind']=='TERMINAL'};results=[];incomplete=[]
    for a in declared['assignments']:
        t=terminals.get(a['id']);path=d/a['id']
        if t is None or t['status']!='COMPLETED':incomplete.append(dict(assignment=a,terminal=t));continue
        r=analyze_case(path)
        if r['assignment']!=a or r['source_sha256']!=sources or (path/'measurements.json').read_bytes()!=canonical(r)+b'\n' or t['details']['measurements_sha256']!=sha(r):raise ValueError('saved measurements differ')
        results.append(r)
    return dict(source_sha256=sources,results=results,incomplete=incomplete,ledger_counts=ledger['counts'],aggregate_pass_fail=None,gate_b='GATE_B_NOT_AUTHORIZED')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--ids',nargs='*');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    save(a.output,run(a.directory,a.ids) if a.mode=='run' else audit(a.directory))
