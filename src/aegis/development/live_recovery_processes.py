"""Independent LIVE01 simulation actors. No hardware adapter or Gate B authority."""
from pathlib import Path
from fractions import Fraction as Q
import argparse,json,os,time
from .restart_process_experiment import Records,Endpoint,obs,extrema,backup_observation,DT
from .durable_feedback_session import canonical,sha
from . import live_recovery_contract as contract


def write_beacon(root,public,tick,epoch):
    body=dict(tick=tick,sensor_epoch=epoch,plant_pid=os.getpid(),host_ns=time.monotonic_ns(),public_sha256=sha(public));tmp=root/('clock_%d_%d.tmp'%(os.getpid(),tick))
    with tmp.open('xb') as f:f.write(canonical(dict(payload=body,sha256=sha(body)))+b'\n');f.flush()
    os.replace(tmp,root/'clock.json');return body


def plant(public,fault,ipc,root):
    ep=Endpoint(ipc/'p.sock');log=Records(root/'plant',dict(role='plant',generation=0,public_sha256=sha(public),source_sha256=public['sources']))
    def event(kind,**data):
        r=log.append(kind,**data);ep.send(ipc/'m.sock',dict(kind=kind,role='plant',pid=os.getpid(),**{k:v for k,v in data.items() if k in ('tick','command_id','lease_id')}));return r
    controller=None;watchdog=None;cg=-1;wg=-1;cpid=-1;wpid=-1;started=False
    event('READY')
    while not (started and controller is not None and watchdog is not None):
        for m in ep.drain():
            if m['kind']=='REGISTER_CONTROLLER':controller=Path(m['path']);cg=m['generation'];cpid=m['pid'];event('REGISTERED_CONTROLLER',tick=0,generation=cg,child_pid=cpid)
            elif m['kind']=='REGISTER_WATCHDOG':watchdog=Path(m['path']);wg=m['generation'];wpid=m['pid'];event('REGISTERED_WATCHDOG',tick=0,generation=wg,child_pid=wpid)
            elif m['kind']=='START':started=True
        time.sleep(.001)
    p=Q(0);v=Q(fault['initial_velocity']);force=Q(0);target=Q(0);queue=[];registry={};leases={};latest=None;barrier=-1;latched=False;backup=None;engaged=False;epoch='sensor-0';offset=1000;history=[];power=True;support=True;dynamics=public['model']['dynamics_id'];partition=False;ever_lease=False
    scenario=fault['scenario'];onset=fault['fault_tick'];last_wall=time.monotonic();current_tick=0;commit_delay_done=False
    def send(path,message,*,operational=True):
        if partition and operational:event('PARTITION_DROP',tick=current_tick,message_kind=message['kind']);return False
        return ep.send(path,message)
    def backup_request(name,origin):
        nonlocal backup,latched,target
        event('BACKUP_REQUESTED',tick=current_tick,command_id=name,origin=origin);latched=True;target=Q(0)
        if backup is None:
            backup=dict(id=name,origin=origin,accepted_tick=current_tick,due=current_tick+(15 if scenario=='backup_delayed' else 3));event('BACKUP_ACCEPTED',tick=current_tick,command_id=name,origin=origin,due=backup['due'])
        else:event('BACKUP_DUPLICATE_IGNORED',tick=current_tick,command_id=name,origin=origin)
    def publish(tick):
        nonlocal history
        measured_p,measured_v=(Q(0),Q(0)) if scenario=='retimestamped_freeze' and tick>=onset else (p,v)
        bounds=obs(measured_p,measured_v);row=dict(kind='OBS',id=epoch+':'+str(tick),tick=tick,remote_time=20*tick+offset,remote_epoch=epoch,clock_offset_ms=offset,source_id=public['model']['measurement_source'],frame='WORLD_X_SI',position_center=format(float(measured_p),'.8f'),velocity_center=format(float(measured_v),'.8f'),emitted_host_ns=time.monotonic_ns(),reported_dynamics_id=dynamics,support_valid=support,topology=dict(controller=cpid,watchdog=wpid,plant=os.getpid()),**bounds)
        history.append(row);sample=row
        if scenario in ('replayed_feedback','restart_lost_ack_replay') and tick>=onset and tick%4==0:
            sample=history[max(0,len(history)-5)];event('FEEDBACK_REPLAY_INJECTED',tick=tick,sample_id=sample['id'])
        if scenario=='progressive_staleness' and tick>=onset:sample=history[max(0,len(history)-1-min(30,1+(tick-onset)//2))]
        if scenario=='malformed_feedback' and onset<=tick<onset+8:sample=dict(row,velocity=['bad','bad'])
        if scenario=='source_mismatch' and tick>=onset:sample=dict(sample,source_id='UNREGISTERED_SOURCE')
        status=dict(kind='STATUS',tick=tick,primary_power=power,backup_requested=backup is not None,backup_accepted=backup is not None,backup_engaged=engaged,controller_generation=cg,watchdog_generation=wg,sensor_epoch=epoch)
        event('SENSOR_EMITTED',tick=tick,sample=sample,status=status)
        for path in (controller,watchdog):send(path,status);send(path,sample)
    write_beacon(root,public,0,epoch);publish(0)
    for current_tick in range(public['steps']):
        # A no-catch-up clock: plant pace is independent of worker responses.
        while time.monotonic()-last_wall<public['wall_period']:time.sleep(.001)
        last_wall=time.monotonic()
        if current_tick==onset:
            event('FAULT_ONSET',tick=current_tick,scenario=scenario)
            if scenario in ('power_loss_queued','backup_delayed','backup_unavailable'):
                power=False;event('POWER_LOSS',tick=current_tick,queue_before=queue,force_before=str(force));backup_request('local-power','PLANT_POWER_GUARD')
                for q in queue:registry[q['command']['command_id']]['status']='REJECTED_POWER_LOSS';event('COMMAND_RETIRED',tick=current_tick,command_id=q['command']['command_id'],reason='REJECTED_POWER_LOSS')
                queue=[];force=Q(0);target=Q(0)
            if scenario=='queue_delay':
                before=json.loads(canonical(queue));queue=[dict(q,due=q['due']+6) for q in queue];event('QUEUE_DELAY_INJECTED',tick=current_tick,queue_before=before,queue_after=queue)
            if scenario=='revocation_queued':support=False;barrier=max([x['seq'] for x in leases.values()],default=-1);event('LOCAL_EVIDENCE_REVOKED',tick=current_tick,queue_before=queue,revoked_seq=barrier);backup_request('local-revocation','PLANT_EVIDENCE_GUARD')
            if scenario=='contradictory_model':dynamics='UNSUPPORTED_DYNAMICS'
            if scenario=='clock_reset':epoch='sensor-1';offset=200;event('CLOCK_EPOCH_RESET',tick=current_tick,epoch=epoch);backup_request('local-clock','PLANT_EPOCH_GUARD')
            if scenario=='permanent_partition':partition=True;event('PARTITION_STARTED',tick=current_tick)
        for m in ep.drain():
            kind=m['kind']
            if partition and kind not in ('REGISTER_CONTROLLER','REGISTER_WATCHDOG'):
                event('PARTITION_DROP',tick=current_tick,message_kind=kind);continue
            if kind=='REGISTER_CONTROLLER' and m['generation']>cg:
                cg=m['generation'];controller=Path(m['path']);cpid=m['pid'];event('REGISTERED_CONTROLLER',tick=current_tick,generation=cg,child_pid=cpid);backup_request('local-controller-epoch','PLANT_BOOT_GUARD')
            elif kind=='REGISTER_WATCHDOG' and m['generation']>wg:
                wg=m['generation'];watchdog=Path(m['path']);wpid=m['pid'];barrier=-1;event('REGISTERED_WATCHDOG',tick=current_tick,generation=wg,child_pid=wpid);backup_request('local-watchdog-epoch','PLANT_BOOT_GUARD')
            elif kind=='LEASE':
                lease=m['lease'];reason=None
                try:contract.load_basis(root,lease)
                except Exception as exc:reason='BASIS_INVALID:'+type(exc).__name__
                args=dict(now_tick=current_tick,now_host_ns=time.monotonic_ns(),controller_generation=cg,watchdog_generation=wg,source_epoch=epoch,public_sha256=sha(public),revoked_seq=barrier,primary_power=power,recovery_latched=latched);check=contract.lease_check(lease,**args)
                if latest is not None and lease['watchdog_generation']==latest['watchdog_generation'] and lease['seq']<=latest['seq']:reason='OLD_LEASE_SEQUENCE'
                event('LEASE_ACCEPTANCE_CHECK',tick=current_tick,lease=lease,arguments=args,check=check,basis_error=reason)
                if check['allowed'] and reason is None:
                    leases[lease['id']]=lease;latest=lease;ever_lease=True;event('LEASE_ACCEPTED',tick=current_tick,lease_id=lease['id']);send(controller,dict(kind='GRANT',lease=lease))
            elif kind=='REVOKE':
                if m['generation']==wg:barrier=max(barrier,m['seq']);event('REVOCATION_RECEIVED',tick=current_tick,revoked_seq=barrier);backup_request('watchdog-revoke','WATCHDOG_REVOCATION')
            elif kind=='BACKUP':backup_request(m['command_id'],'WATCHDOG_REQUEST')
            elif kind=='QUERY':
                states={x:registry.get(x,dict(status='UNKNOWN'))['status'] for x in m['ids']};event('QUERY_ANSWERED',tick=current_tick,states=states);send(Path(m['reply']),dict(kind='QUERY_RESULT',tick=current_tick,states=states))
            elif kind=='COMMAND':
                validation=contract.command_check(m,expected_reply=str(controller))
                if not validation['valid']:
                    event('MALFORMED_COMMAND_REJECTED',tick=current_tick,command=m,validation=validation)
                    if type(m.get('command_id')) is str and m['command_id'] not in registry:registry[m['command_id']]=dict(digest=sha(m),status='REJECTED_MALFORMED',command=m)
                    continue
                name=m['command_id'];digest=sha({k:v for k,v in m.items() if k!='reply'})
                if name in registry:event('DUPLICATE_IGNORED' if digest==registry[name]['digest'] else 'CONFLICT_REJECTED',tick=current_tick,command_id=name)
                else:
                    lease=leases.get(m['lease_id']);args=dict(now_tick=current_tick,now_host_ns=time.monotonic_ns(),controller_generation=cg,watchdog_generation=wg,source_epoch=epoch,public_sha256=sha(public),revoked_seq=barrier,primary_power=power,recovery_latched=latched);check=contract.lease_check(lease,**args)
                    okay=check['allowed'] and m['generation']==cg and lease['basis_sha256']==m['basis_sha256']
                    status='QUEUED' if okay else 'REJECTED_AT_ACCEPTANCE';registry[name]=dict(digest=digest,status=status,command=m)
                    event('COMMAND_ACCEPTANCE_CHECK',tick=current_tick,command_id=name,command=m,lease=lease,arguments=args,check=check,generation_match=m['generation']==cg)
                    if okay:queue.append(dict(command=m,due=current_tick+3));event('COMMAND_ACCEPTED',tick=current_tick,command_id=name,command=m,due=current_tick+3)
                    else:event('COMMAND_REJECTED',tick=current_tick,command_id=name,reason=check['reason'])
                if scenario not in ('lost_acknowledgements','restart_lost_ack_replay'):send(Path(m['reply']),dict(kind='ACK',tick=current_tick,command_id=name,status=registry[name]['status']))
                else:event('ACK_DROPPED',tick=current_tick,command_id=name)
        active_args=dict(now_tick=current_tick,now_host_ns=time.monotonic_ns(),controller_generation=cg,watchdog_generation=wg,source_epoch=epoch,public_sha256=sha(public),revoked_seq=barrier,primary_power=power,recovery_latched=latched);active_check=contract.lease_check(latest,**active_args)
        if not active_check['allowed'] and backup is None and (ever_lease or current_tick>=6):
            backup_request('local-lease-expiry','PLANT_LEASE_GUARD');active_args.update(recovery_latched=latched,now_host_ns=time.monotonic_ns());active_check=contract.lease_check(latest,**active_args)
        due=[q for q in queue if q['due']<=current_tick];queue=[q for q in queue if q['due']>current_tick]
        for q in due:
            m=q['command'];lease=leases.get(m['lease_id']);basis_error=None
            try:contract.load_basis(root,lease)
            except Exception as exc:basis_error='BASIS_INVALID:'+type(exc).__name__
            args=dict(now_tick=current_tick,now_host_ns=time.monotonic_ns(),controller_generation=cg,watchdog_generation=wg,source_epoch=epoch,public_sha256=sha(public),revoked_seq=barrier,primary_power=power,recovery_latched=latched)
            check=contract.lease_check(lease,**args);okay=check['allowed'] and basis_error is None and m['generation']==cg
            event('CONSUMPTION_CHECK',tick=current_tick,command_id=m['command_id'],lease=lease,arguments=args,check=check,basis_error=basis_error,allowed=okay)
            if scenario=='storage_commit_delay' and current_tick>=onset and not commit_delay_done and okay:
                start_delay=time.monotonic_ns();time.sleep(.2);event('CONSUMPTION_COMMIT_DELAY',tick=current_tick,command_id=m['command_id'],duration_ns=time.monotonic_ns()-start_delay);commit_delay_done=True
            # Persistence can consume the remaining lease. Recheck after it.
            candidate_target=max(Q(-1),min(Q(1),Q(m['target'])))
            final_args=dict(args,now_host_ns=time.monotonic_ns());final_check=contract.lease_check(lease,**final_args);okay=okay and final_check['allowed']
            late_application=None
            if okay:
                old_target=target;target=candidate_target;applied=time.monotonic_ns()
                if applied>=lease['expires_host_ns']:
                    target=old_target;okay=False;late_application=applied  # no physics step has occurred
                else:
                    registry[m['command_id']]['status']='CONSUMED';event('COMMAND_CONSUMED',tick=current_tick,command_id=m['command_id'],target=str(target),lease_id=lease['id'],final_arguments=final_args,final_check=final_check,applied_host_ns=applied)
            if not okay:
                reason='REJECTED_NATIVE_EXPIRY_AT_FINALIZATION' if check['allowed'] and (not final_check['allowed'] or late_application is not None) else 'REJECTED_AT_CONSUMPTION'
                registry[m['command_id']]['status']=reason;event('COMMAND_RETIRED',tick=current_tick,command_id=m['command_id'],reason=reason,final_arguments=final_args,final_check=final_check,attempted_application_host_ns=late_application)
        # File persistence above may have exhausted the active lease as well.
        active_args.update(now_host_ns=time.monotonic_ns(),recovery_latched=latched)
        active_check=contract.lease_check(latest,**active_args)
        if not active_check['allowed'] and backup is None and (ever_lease or current_tick>=6):
            backup_request('local-post-commit-expiry','PLANT_POST_COMMIT_GUARD');active_args.update(now_host_ns=time.monotonic_ns(),recovery_latched=latched);active_check=contract.lease_check(latest,**active_args)
        if not active_check['allowed'] or latched:target=Q(0)
        if power:force+=max(Q('-.08'),min(Q('.08'),target-force))
        else:force=Q(0)
        if backup is not None and not engaged and current_tick>=backup['due'] and scenario!='backup_unavailable':engaged=True;event('BACKUP_ENGAGED',tick=current_tick,command_id=backup['id'])
        active=Q(0) if engaged else force;bf=max(Q(-4),min(Q(4),-4*p-3*v)) if engaged else Q(0);a=active+bf+Q('.01')
        event('STEP_INTENT',tick=current_tick,position=str(p),velocity=str(v),force=str(force),target=str(target),active_force=str(active),backup_force=str(bf),power=power,backup_engaged=engaged,recovery_latched=latched,queue=queue,active_lease=latest,active_arguments=active_args,active_check=active_check,controller_generation=cg,watchdog_generation=wg,source_epoch=epoch,revoked_seq=barrier)
        pn=p+DT*v+DT*DT*a/2;vn=v+DT*a
        event('STEP_RESULT',tick=current_tick,position=str(pn),velocity=str(vn),continuous_position=extrema(p,v,a));p,v=pn,vn
        write_beacon(root,public,current_tick+1,epoch);publish(current_tick+1)
    event('FINISHED',tick=public['steps'],registry={k:v['status'] for k,v in registry.items()})
    # Administrative end never reconciles unknown effects or supplies a final snapshot.
    ep.send(controller,dict(kind='STOP',administrative=True));ep.send(watchdog,dict(kind='STOP',administrative=True));ep.close()


def controller(public,ipc,root,generation):
    boot=f'controller-{generation}';ep=Endpoint(ipc/(f'c{generation}.sock'));log=Records(root/boot,dict(role='controller',generation=generation,public_sha256=sha(public),source_sha256=public['sources']))
    beliefs=contract.EffectBeliefs();seen=-1;known={}
    for old in sorted(root.glob('controller-*')):
        if old==log.directory or not old.is_dir():continue
        from .restart_process_experiment import read_records
        for r in read_records(old)['records']:
            if r['kind']=='FEEDBACK_ACCEPTED':seen=max(seen,r['sample']['tick'])
            if r['kind']=='FEEDBACK_DIGEST':known[r['sample_id']]=r['sample_sha256']
            if r['kind']=='COMMAND_INTENT':beliefs.merge(r['command']['command_id'],'UNKNOWN')
            if r['kind']=='BELIEF':beliefs.merge(r['command_id'],r['reported'])
    log.append('RECONSTRUCTION',seen=seen,beliefs=beliefs.states)
    ep.send(ipc/'p.sock',dict(kind='REGISTER_CONTROLLER',generation=generation,pid=os.getpid(),path=ep.path));ep.send(ipc/'m.sock',dict(kind='READY',role='controller',generation=generation,pid=os.getpid()))
    lease=None;status=None;last_hb=0;last_query=0;duplicates=False;changed=False;latest_sample=None;latched=False;last_attempt=None
    def try_issue(m):
        nonlocal last_attempt
        if lease is None or status is None or latched or m['tick']>=public['steps']-6 or f'c{generation}:{m["tick"]}' in beliefs.states:return
        key=(m['id'],lease['id'],status['controller_generation'],status['watchdog_generation'])
        if key==last_attempt:return
        last_attempt=key
        try:
            beacon=contract.read_beacon(root)
            if m['remote_epoch']!=beacon['sensor_epoch'] or beacon['tick']-m['tick']>3 or time.monotonic_ns()-m['emitted_host_ns']>public['max_observation_host_ns']:return
            contract.load_basis(root,lease);beacon=contract.read_beacon(root)
            args=dict(now_tick=beacon['tick'],now_host_ns=time.monotonic_ns(),controller_generation=generation,watchdog_generation=status['watchdog_generation'],source_epoch=beacon['sensor_epoch'],public_sha256=sha(public),revoked_seq=-1,primary_power=status['primary_power'],recovery_latched=latched)
            check=contract.lease_check(lease,**args)
            target=-2*(Q(m['velocity'][0])+Q(m['velocity'][1]))/2
            if not check['allowed']:log.append('ISSUE_WITHHELD',arguments=args,check=check);return
            command=dict(kind='COMMAND',command_id=f'c{generation}:{m["tick"]}',generation=generation,lease_id=lease['id'],basis_sha256=lease['basis_sha256'],target=str(target),reply=ep.path)
            log.append('COMMAND_INTENT',command=command,lease=lease,measurement_sample_id=m['id'],measurement_sha256=sha(m),dispatch_snapshot='LATEST_GRANT_AND_MEASUREMENT');beliefs.merge(command['command_id'],'UNKNOWN')
            beacon=contract.read_beacon(root);args.update(now_tick=beacon['tick'],now_host_ns=time.monotonic_ns(),source_epoch=beacon['sensor_epoch']);check=contract.lease_check(lease,**args);log.append('ISSUE_CHECK',command_id=command['command_id'],lease=lease,arguments=args,check=check)
            if check['allowed']:
                ep.send(ipc/'p.sock',command)
                if duplicates:
                    repeated=dict(command)
                    if changed:repeated['target']='0.5'
                    ep.send(ipc/'p.sock',repeated);log.append('DUPLICATE_SENT',command_id=command['command_id'],changed=changed)
            else:beliefs.merge(command['command_id'],'REJECTED_LOCAL_BEFORE_SEND');log.append('BELIEF',command_id=command['command_id'],reported='REJECTED_LOCAL_BEFORE_SEND',belief=beliefs.states[command['command_id']],origin='LOCAL')
        except Exception as exc:log.append('ISSUE_WITHHELD_ERROR',error_type=type(exc).__name__,error=str(exc))
    while True:
        for m in ep.drain():
            kind=m['kind']
            if kind=='STOP':log.append('FINISHED',beliefs=beliefs.states,conflicts=beliefs.conflicts);ep.close();return
            if kind=='INJECT_DUPLICATES':duplicates=True;changed=m['changed'];log.append('DUPLICATE_INJECTION_ENABLED',changed=changed)
            if kind=='GRANT':lease=m['lease'];log.append('GRANT_RECEIVED',lease=lease)
            if kind=='STATUS':status=m;latched|=m['backup_requested'];log.append('STATUS_RECEIVED',status=m)
            if kind in ('ACK','QUERY_RESULT'):
                values=m['states'] if kind=='QUERY_RESULT' else {m['command_id']:m['status']}
                for name,value in values.items():beliefs.merge(name,value);log.append('BELIEF',command_id=name,reported=value,belief=beliefs.states[name],origin=kind)
            if kind=='OBS':
                selection=contract.select_samples([m],seen=seen,known=known,public=public)
                for item in selection['events']:log.append(item['kind'],**{k:v for k,v in item.items() if k!='kind'})
                known.update(selection['digest_updates'])
                if selection['critical'] is not None:latched=True
                if selection['selected'] is None:continue
                seen=m['tick'];latest_sample=m;log.append('FEEDBACK_ACCEPTED',sample=m)
        if latest_sample is not None:try_issue(latest_sample)
        now=time.monotonic_ns()
        if now-last_hb>=20000000:
            ready=not latched and latest_sample is not None and now-latest_sample['emitted_host_ns']<=public['max_observation_host_ns']
            ep.send(ipc/'w.sock',dict(kind='HEARTBEAT',generation=generation,pid=os.getpid(),ready=ready,last_sample=None if latest_sample is None else latest_sample['id']));last_hb=now
        if now-last_query>=80000000:
            ids=[k for k,v in beliefs.states.items() if v in ('UNKNOWN','QUEUED','EFFECT_UNCERTAIN')][:8]
            if ids:ep.send(ipc/'p.sock',dict(kind='QUERY',ids=ids,reply=ep.path));log.append('QUERY_SENT',ids=ids)
            last_query=now
        time.sleep(.001)


def watchdog(public,ipc,root,generation):
    boot=f'watchdog-{generation}';ep=Endpoint(ipc/'w.sock');log=Records(root/boot,dict(role='watchdog',generation=generation,public_sha256=sha(public),source_sha256=public['sources']))
    seen=-1;latched=False;known={}
    from .restart_process_experiment import read_records
    for old in sorted(root.glob('watchdog-*')):
        if old==log.directory or not old.is_dir():continue
        for r in read_records(old)['records']:
            if r['kind']=='FEEDBACK_ACCEPTED':seen=max(seen,r['sample']['tick'])
            if r['kind']=='FEEDBACK_DIGEST':known[r['sample_id']]=r['sample_sha256']
            if r['kind']=='RECOVERY_LATCHED':latched=True
    log.append('RECONSTRUCTION',seen=seen,recovery_latched=latched)
    ep.send(ipc/'p.sock',dict(kind='REGISTER_WATCHDOG',generation=generation,pid=os.getpid(),path=ep.path));ep.send(ipc/'m.sock',dict(kind='READY',role='watchdog',generation=generation,pid=os.getpid()))
    status=None;last_obs=None;last_obs_host=None;heart=0;heart_gen=-1;ready=False;seq=0;last_request=0;delay=0;previous_backup=None;deadline_reported=False;backup_request_tick=None
    start=time.monotonic_ns();clock_failed=False
    def live_clock(path):
        if clock_failed:raise OSError('synthetic clock-reader failure')
        return contract.read_beacon(path)
    def safe_tick():
        try:return live_clock(root)['tick']
        except Exception:return None
    def latch(reason):
        nonlocal latched,seq,backup_request_tick
        if not latched:
            latched=True;seq+=1;backup_request_tick=safe_tick();log.append('RECOVERY_LATCHED',tick=backup_request_tick,reason=reason)
            ep.send(ipc/'p.sock',dict(kind='REVOKE',generation=generation,seq=seq))
    while True:
        samples=[]
        for m in ep.drain():
            kind=m['kind']
            if kind=='STOP':log.append('FINISHED',recovery_latched=latched);ep.close();return
            if kind=='INJECT_COMPUTE_DELAY':delay=m['seconds'];log.append('COMPUTE_DELAY_ENABLED',seconds=delay)
            if kind=='INJECT_CLOCK_FAILURE':clock_failed=True;log.append('CLOCK_READER_FAILURE_ENABLED')
            if kind=='HEARTBEAT':heart=time.monotonic_ns();heart_gen=m['generation'];ready=m['ready'];log.append('HEARTBEAT_RECEIVED',heartbeat=m)
            if kind=='STATUS':status=m;log.append('STATUS_RECEIVED',status=m)
            if kind=='OBS':samples.append(m)
        if status is not None and status['backup_requested']:latch('PLANT_REPORTED_RECOVERY')
        selection=contract.select_samples(samples,seen=seen,known=known,public=public)
        for item in selection['events']:log.append(item['kind'],**{k:v for k,v in item.items() if k!='kind'})
        known.update(selection['digest_updates'])
        if selection['critical'] is not None:latch(selection['critical'])
        samples=[] if selection['selected'] is None else [selection['selected']]
        for sample in samples:
            if sample['tick']<=seen:log.append('REPLAY_IGNORED',tick=sample['tick'],sample_id=sample['id']);continue
            seen=sample['tick'];last_obs=sample;last_obs_host=time.monotonic_ns();log.append('FEEDBACK_ACCEPTED',sample=sample)
            if latched:
                check=backup_observation(previous_backup,sample) if status is not None and status['backup_engaged'] else dict(status='ENGAGEMENT_NOT_OBSERVED',operational_authorization=False)
                log.append('BACKUP_OBSERVATION',sample=sample,status=status,check=check);previous_backup=sample;continue
            if status is None:continue
            healthy=(heart_gen==status['controller_generation'] and ready and time.monotonic_ns()-heart<100000000) or sample['tick']<4
            relative=boot+'/assessments/'+f'{sample["tick"]:08d}'
            try:
                basis=contract.assess_frame(root,relative,sample,public,boot,primary_healthy=healthy,controller_generation=status['controller_generation'],delay_seconds=delay,clock=live_clock);delay=0
                log.append('ASSESSMENT',tick=sample['tick'],basis_path=relative+'/result.json',basis_sha256=sha(basis),reason=basis['reason'])
                if basis['reason'] is None and basis['result']['development_action']=='CONTINUE':
                    beacon=contract.read_beacon(root);issue_host=time.monotonic_ns()
                    try:lease=contract.make_lease(basis,relative,public,generation=generation,seq=seq+1,issue_host_ns=issue_host,issue_beacon=beacon)
                    except ValueError as exc:log.append('REASSESSMENT_REQUIRED',tick=sample['tick'],reason=str(exc));continue
                    seq+=1;log.append('LEASE_ISSUED',tick=basis['beacon_after']['tick'],lease=lease,issue_beacon=beacon);ep.send(ipc/'p.sock',dict(kind='LEASE',lease=lease))
                elif basis['reason'] in ('PLANT_CLOCK_ADVANCED_OR_RESET','NATIVE_COMPUTATION_BUDGET_EXCEEDED') or (basis['result'] is not None and basis['result'].get('reason')=='TIME_ADVANCED_FRESH_ASSESSMENT_REQUIRED'):log.append('REASSESSMENT_REQUIRED',tick=sample['tick'],reason=basis['reason'])
                else:latch(basis['reason'] or 'MODEL_REQUESTED_HANDOFF')
            except Exception as exc:log.append('ASSESSMENT_ERROR',error_type=type(exc).__name__,error=str(exc));latch('ASSESSMENT_ERROR')
        now=time.monotonic_ns()
        if not latched and now-start>200000000 and (last_obs_host is None or now-last_obs_host>public['max_observation_host_ns']):latch('OBSERVATION_SILENCE')
        if not latched and status is not None and status['tick']>=4 and now-heart>100000000:latch('CONTROLLER_HEARTBEAT_SILENCE')
        if latched and now-last_request>80000000:
            name=f'watchdog-{generation}-backup';log.append('BACKUP_REQUEST_SENT',tick=safe_tick(),command_id=name);ep.send(ipc/'p.sock',dict(kind='BACKUP',command_id=name));last_request=now
        if latched and status is not None and not deadline_reported and backup_request_tick is not None and status['tick']>backup_request_tick+4 and not status['backup_engaged']:
            log.append('BACKUP_DEADLINE_MISSED',tick=status['tick'],request_tick=backup_request_tick);deadline_reported=True
        time.sleep(.001)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('role',choices=('plant','controller','watchdog'));p.add_argument('public',type=Path);p.add_argument('ipc',type=Path);p.add_argument('root',type=Path);p.add_argument('--generation',type=int,default=0);p.add_argument('--fault',type=Path);a=p.parse_args();public=json.loads(a.public.read_bytes())
    if a.role=='plant':plant(public,json.loads(a.fault.read_bytes()),a.ipc,a.root)
    elif a.role=='controller':controller(public,a.ipc,a.root,a.generation)
    else:watchdog(public,a.ipc,a.root,a.generation)
