"""Independent DEVELOPMENT plant/controller/watchdog actors over local datagrams.

Ideal 1D ZOH plant, synthetic clocks/sensors and simulation-only permissions.
Not a robot interface, hard real-time scheduler, production authority or trust root.
"""
from pathlib import Path
from fractions import Fraction as Q
import argparse,hashlib,json,os,socket,time,errno
from .durable_feedback_session import canonical,sha
from .independent_clock_mapping import IndependentClockMap
from . import physical_time_recovery as physical

DT=Q('.02')
BACKUP=dict(dt='.02',mass='1',spring='4',damping='3',position_scale='1',velocity_scale='1',anchor='0',level='5',force_cap='4',disturbance='.01',safe_position=['-.5','.32'])
FAMILY=dict(mass=['.9','1.1'],spring=['3.6','4.4'],damping=['2.7','3.3'])
ZERO='0'*64


class Records:
    """Atomic committed files. Pending bytes survive a killed writer untouched."""
    def __init__(self,directory,header):
        self.directory=Path(directory);self.directory.mkdir(exist_ok=False);self.seq=0;self.previous=ZERO
        self.append('HEADER',**header)
    def append(self,kind,**data):
        payload=dict(kind=kind,pid=os.getpid(),wall_ns=time.monotonic_ns(),**data)
        body=dict(seq=self.seq,previous=self.previous,payload=payload);record=dict(body,sha256=sha(body));raw=canonical(record)+b'\n'
        pending=self.directory/('pending_%08d.json'%self.seq);final=self.directory/('%08d.json'%self.seq)
        with pending.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.link(pending,final);fd=os.open(self.directory,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        pending.unlink();self.previous=record['sha256'];self.seq+=1;return payload


def read_records(directory):
    d=Path(directory);rows=[];previous=ZERO
    for n,p in enumerate(sorted(d.glob('[0-9]'*8+'.json'))):
        if p.is_symlink():raise ValueError('record symlink')
        r=json.loads(p.read_bytes());body={k:r[k] for k in ('seq','previous','payload')}
        if r['seq']!=n or p.name!='%08d.json'%n or r['previous']!=previous or sha(body)!=r['sha256'] or canonical(r)+b'\n'!=p.read_bytes():raise ValueError('committed record mismatch')
        previous=r['sha256'];rows.append(r['payload'])
    if not rows or rows[0]['kind']!='HEADER':raise ValueError('missing role header')
    pending=[dict(name=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,committed_alias=(d/p.name.removeprefix('pending_')).exists() and (d/p.name.removeprefix('pending_')).read_bytes()==p.read_bytes()) for p in sorted(d.glob('pending_*'))]
    return dict(records=rows,pending=pending,head_sha256=previous)


class Endpoint:
    def __init__(self,path):
        self.path=str(path);self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);self.sock.bind(self.path);self.sock.setblocking(False)
    def send(self,path,message):
        raw=canonical(message)
        if len(raw)>1800:raise ValueError('bounded datagram contract')
        try:self.sock.sendto(raw,str(path));return True
        except OSError as e:
            if e.errno in (errno.EAGAIN,errno.ENOBUFS,errno.ENOENT,errno.ECONNREFUSED):return False
            raise
    def drain(self):
        rows=[]
        while True:
            try:raw=self.sock.recv(8192)
            except BlockingIOError:break
            rows.append(json.loads(raw))
        return rows
    def close(self):self.sock.close()


def obs(p,v):
    def bounds(x):
        q=Q(format(float(x),'.8f'));return [str(q-Q('0.00000002')),str(q+Q('0.00000002'))]
    return dict(position=bounds(p),velocity=bounds(v))


def assessment(packet,now_ms,clock,local_epoch,boot,healthy,delay='.08'):
    return physical.assess(BACKUP,FAMILY,packet,clock,now_local=now_ms,units_per_second='1000',max_state_age_seconds='.06',
        local_epoch=local_epoch,boot_id=boot,active_force_cap='1',handoff_delay_seconds=['0',delay],monitor_seconds='.06',
        premises={k:True for k in physical.PREMISES.split()},primary_healthy=healthy,dynamics_id=physical.DYNAMICS_ID)


def make_map(message):
    c=IndependentClockMap(local_epoch=message['local_epoch'],remote_epoch=message['remote_epoch'],rate_bounds=['1','1'],max_extrapolation=100000)
    c.add(message['exchange']);return c


def extrema(p,v,a):
    ts=[Q(0),DT]
    if a and 0<-v/a<DT:ts.append(-v/a)
    vals=[p+t*v+t*t*a/2 for t in ts]
    return [str(min(vals)),str(max(vals))]


def backup_observation(before,after):
    """Necessary bounded ideal ZOH consistency; not a new actuation permission."""
    out=dict(status='UNKNOWN_BACKUP_OBSERVATION',operational_authorization=False)
    try:
        if before is None or after['tick']!=before['tick']+1 or after['remote_epoch']!=before['remote_epoch']:return out
        from .recovery_feedback_state_1d import _bounds
        from .recovery_envelope_1d import internal,point
        p,v=_bounds(before['position']),_bounds(before['velocity'])
        force=-(_bounds(FAMILY['spring'])*p+_bounds(FAMILY['damping'])*v)
        force=internal(max(Q(-4),min(Q(4),force.lo)),max(Q(-4),min(Q(4),force.hi)))
        a=(force+internal(Q('-.01'),Q('.01'))).divide_positive(_bounds(FAMILY['mass']))
        pn=p+point(DT)*v+point(DT*DT/2)*a;vn=v+point(DT)*a
        ok=all(max(x.lo,y.lo)<=min(x.hi,y.hi) for x,y in ((pn,_bounds(after['position'])),(vn,_bounds(after['velocity']))))
        return dict(out,status='COMPATIBLE_IDEAL_BACKUP_STEP' if ok else 'BACKUP_MODEL_OR_FEEDBACK_CONTRADICTION',predicted_position=pn.wire(),predicted_velocity=vn.wire())
    except (ValueError,TypeError,KeyError,ZeroDivisionError):return out


def plant(config,ipc,out):
    ep=Endpoint(ipc/'p.sock');log=Records(out/'plant',dict(role='plant',configuration_sha256=sha(config),source_sha256=config['sources']))
    def notify(kind,**data):
        r=log.append(kind,**data);ep.send(ipc/'m.sock',dict(kind=kind,role='plant',pid=os.getpid(),wall_ns=r['wall_ns'],**{k:v for k,v in data.items() if k in ('tick','command_id','status','generation')}));return r
    controller=None;controller_offset=0;generation=-1;wd=None;started=False
    p=Q(config.get('initial_position','0'));v=Q(config['initial_velocity']);force=Q('.8') if config['scenario']=='power_loss_queued' else Q(0);target=force
    queue=[];registry={};history=[];permission=None;backup_at=None;backup_id=None;engaged=False;sensor_epoch='sensor-0';sensor_offset=1000;last_power=True
    notify('READY')
    def clock_to(path,epoch,offset,tick):
        local=100+20*tick+offset;remote=100+20*tick+sensor_offset
        ep.send(path,dict(kind='CLOCK',local_epoch=epoch,remote_epoch=sensor_epoch,
            exchange=dict(id=sensor_epoch+':'+epoch,local_epoch=epoch,remote_epoch=sensor_epoch,local_send=local-2,remote_receive=remote,remote_send=remote,local_receive=local)))
    while not started:
        for m in ep.drain():
            if m['kind']=='REGISTER_CONTROLLER':controller=Path(m['path']);controller_offset=m['offset'];generation=m['generation'];clock_to(controller,'ctrl-'+str(generation),controller_offset,0)
            if m['kind']=='REGISTER_WATCHDOG':wd=Path(m['path']);clock_to(wd,'wd-0',0,0)
            if m['kind']=='START':started=True
        time.sleep(.001)
    start=time.monotonic_ns();next_wall=start
    if config['scenario']=='power_loss_queued':
        for n in range(3):queue.append(dict(id='fixture-'+str(n),target='.8',due=n,expires=10000,generation=-1,fixture=True))
    for tick in range(config['steps']):
        next_wall+=int(config['wall_period']*1e9)
        power=not(config['scenario'] in ('power_loss_queued','backup_delayed','backup_unavailable') and tick>=config.get('power_loss_tick',30))
        for m in ep.drain():
            kind=m['kind']
            if kind=='REGISTER_CONTROLLER':
                if m['generation']>generation:
                    generation=m['generation'];controller=Path(m['path']);controller_offset=m['offset'];notify('REGISTERED_CONTROLLER',tick=tick,generation=generation);clock_to(controller,'ctrl-'+str(generation),controller_offset,tick)
            elif kind=='PERMISSION':
                notify('PERMISSION_RECEIVED',tick=tick,message=m)
                if m['issued_tick']<=tick and (permission is None or m['issued_tick']>=permission['issued_tick']):permission=m
            elif kind=='BACKUP':
                if backup_id is None:
                    backup_id=m['command_id'];backup_at=tick+(15 if config['scenario']=='backup_delayed' else 3);notify('BACKUP_ACCEPTED',tick=tick,command_id=backup_id,status=m['basis'])
                else:notify('BACKUP_DUPLICATE_IGNORED',tick=tick,command_id=m['command_id'])
            elif kind=='QUERY':
                answer={x:registry.get(x,dict(status='UNKNOWN'))['status'] for x in m['ids']}
                ep.send(Path(m['reply']),dict(kind='QUERY_RESULT',tick=tick,states=answer));notify('QUERY_ANSWERED',tick=tick,status=answer)
            elif kind=='COMMAND':
                name=m['command_id'];digest=sha({k:x for k,x in m.items() if k!='reply'})
                if name in registry:
                    status='DUPLICATE_IGNORED' if registry[name]['digest']==digest else 'CONFLICT_REJECTED';notify(status,tick=tick,command_id=name)
                else:
                    allowed=permission is not None and permission['allow'] and permission['expires_tick']>=tick and m['generation']==generation and m['expires_tick']>=tick+3 and not engaged
                    status='QUEUED' if allowed else 'REJECTED'
                    registry[name]=dict(status=status,digest=digest,body=m)
                    if allowed:queue.append(dict(id=name,target=m['target'],due=tick+3,expires=m['expires_tick'],generation=generation,fixture=False))
                    notify('COMMAND_ACCEPTED' if allowed else 'COMMAND_REJECTED',tick=tick,command_id=name,generation=m['generation'],status=status,command=m,due_tick=tick+3)
                if config['scenario'] not in ('lost_acknowledgements','restart_lost_ack_replay'):
                    ep.send(Path(m['reply']),dict(kind='ACK',tick=tick,command_id=name,status=registry[name]['status']))
                else:notify('ACK_DROPPED',tick=tick,command_id=name)
        if config['scenario']=='clock_reset' and tick==40:
            sensor_epoch='sensor-1';sensor_offset=-20*tick
            clock_to(controller,'ctrl-'+str(generation),controller_offset,tick);clock_to(wd,'wd-0',0,tick);notify('SENSOR_CLOCK_RESET',tick=tick)
        if not power and last_power:
            notify('POWER_LOSS_FLUSH',tick=tick,queue_before=list(queue),force_before=str(force));
            for q in queue:
                if not q['fixture']:registry[q['id']]['status']='REJECTED_POWER_LOSS'
            queue=[];force=Q(0);target=Q(0)
        last_power=power
        allow=permission is not None and permission['allow'] and permission['expires_tick']>=tick and not engaged and power
        due=[q for q in queue if q['due']<=tick];queue=[q for q in queue if q['due']>tick]
        for q in due:
            usable=power and not engaged and (q['fixture'] or (allow and q['expires']>=tick and q['generation']==generation))
            if usable:
                target=max(Q(-1),min(Q(1),Q(q['target'])))
                if not q['fixture']:registry[q['id']]['status']='CONSUMED'
                notify('COMMAND_CONSUMED',tick=tick,command_id=q['id'],generation=q['generation'],permission_valid=bool(allow),fixture=q['fixture'])
            elif not q['fixture']:registry[q['id']]['status']='REJECTED_AT_CONSUMPTION';notify('COMMAND_RETIRED',tick=tick,command_id=q['id'])
        if not allow and config['scenario']!='power_loss_queued':target=Q(0)
        if power:force+=max(Q('-.08'),min(Q('.08'),target-force))
        else:force=Q(0)
        if not engaged and backup_at is not None and tick>=backup_at and config['scenario']!='backup_unavailable':engaged=True;notify('BACKUP_ENGAGED',tick=tick,command_id=backup_id)
        active=Q(0) if engaged else force
        bf=max(Q(-4),min(Q(4),-4*p-3*v)) if engaged else Q(0);a=active+bf+Q('.01')
        intent=dict(tick=tick,position=str(p),velocity=str(v),force=str(force),target=str(target),queue=list(queue),active_force=str(active),backup_force=str(bf),power=power,backup_engaged=engaged,permission_valid=bool(allow),generation=generation)
        notify('STEP_INTENT',**intent)
        pn=p+DT*v+DT*DT*a/2;vn=v+DT*a
        notify('STEP_RESULT',tick=tick,position=str(pn),velocity=str(vn),continuous_position=extrema(p,v,a),wall_lateness_ns=max(0,time.monotonic_ns()-next_wall))
        p,v=pn,vn
        row=dict(kind='OBS',tick=tick+1,remote_time=100+20*(tick+1)+sensor_offset,remote_epoch=sensor_epoch,frame='WORLD_X_SI',source_id='SYNTHETIC_PLANT_CHANNEL',**obs(p,v));history.append(row)
        tickmsg=dict(kind='TICK',tick=tick+1,virtual_ms=100+20*(tick+1),primary_power=power,backup_engaged=engaged,backup_requested=backup_id is not None)
        ep.send(wd,tickmsg);ep.send(wd,row)
        if controller is not None:
            ep.send(controller,tickmsg)
            sample=row
            if config['scenario']=='progressive_staleness' and tick>=30:sample=history[max(0,len(history)-1-min(40,1+(tick-30)//2))]
            if config['scenario'] in ('replayed_feedback','restart_lost_ack_replay') and tick>=20 and tick%4==0:sample=history[max(0,len(history)-6)];notify('FEEDBACK_REPLAY_INJECTED',tick=tick)
            if config['scenario']=='malformed_feedback' and 30<=tick<45:sample=dict(row,velocity=['bad','bad'])
            ep.send(controller,sample)
        while time.monotonic_ns()<next_wall:time.sleep(min(.001,(next_wall-time.monotonic_ns())/1e9))
    if controller is not None:
        ids=list(registry)
        for chunk in reversed([ids[start:start+8] for start in range(0,len(ids),8)]):ep.send(controller,dict(kind='QUERY_RESULT',tick=config['steps'],states={name:registry[name]['status'] for name in chunk},final_snapshot=True))
    notify('FINISHED',tick=config['steps']);ep.send(wd,dict(kind='STOP'));ep.send(controller,dict(kind='STOP'));ep.close()


def control(config,ipc,out,generation,offset):
    boot='ctrl-'+str(generation);path=ipc/('c'+str(generation)+'.sock');ep=Endpoint(path)
    log=Records(out/boot,dict(role='controller',generation=generation,configuration_sha256=sha(config),source_sha256=config['sources']))
    def event(kind,**kw):return log.append(kind,**kw)
    seen=-1;uncertain={};intent_ticks={};timeout_reported=set()
    for old in sorted(out.glob('ctrl-*')):
        if old==log.directory:continue
        for r in read_records(old)['records']:
            if r['kind']=='FEEDBACK_ACCEPTED':seen=max(seen,r['sample']['tick'])
            if r['kind']=='COMMAND_INTENT':uncertain[r['command']['command_id']]='UNKNOWN';intent_ticks[r['command']['command_id']]=r['tick']
            if r['kind']=='ACK':uncertain[r['command_id']]=r['status']
            if r['kind']=='QUERY_RESULT':uncertain.update(r['states'])
    event('RECONSTRUCTION',last_seen=seen,uncertain=uncertain)
    ep.send(ipc/'p.sock',dict(kind='REGISTER_CONTROLLER',path=str(path),generation=generation,offset=offset));ep.send(ipc/'w.sock',dict(kind='REGISTER_CONTROLLER',generation=generation))
    ep.send(ipc/'m.sock',dict(kind='READY',role='controller',pid=os.getpid(),generation=generation))
    clock=None;now=None;current_tick=-1;last_processed=-1;ready=False;last_query=-10;clock_epoch=None;recovery_latched=False;previous_sample=None
    while True:
        incoming=ep.drain();samples=[]
        for m in incoming:
            if m['kind']=='STOP':event('FINISHED',tick=current_tick);ep.close();return
            if m['kind']=='CLOCK':
                if clock is not None and clock_epoch!=m['remote_epoch']:event('CLOCK_EPOCH_CHANGED',tick=current_tick,old_epoch=clock_epoch,new_epoch=m['remote_epoch'])
                clock=make_map(m);clock_epoch=m['remote_epoch'];event('CLOCK_MAP',message=m)
            if m['kind']=='TICK':
                current_tick=m['tick'];now=m['virtual_ms']+offset;recovery_latched|=m['backup_requested']
            if m['kind']=='OBS':samples.append(m)
            if m['kind']=='ACK':uncertain[m['command_id']]=m['status'];event('ACK',tick=m['tick'],command_id=m['command_id'],status=m['status'])
            if m['kind']=='QUERY_RESULT':uncertain.update(m['states']);event('QUERY_RESULT',tick=m['tick'],states=m['states'])
        for sample in samples:
            if sample['tick']<=seen:event('REPLAY_IGNORED',tick=current_tick,sample_tick=sample['tick']);continue
            if clock is None or now is None:continue
            if recovery_latched:
                event('RECOVERY_LATCHED_OBSERVATION',tick=current_tick,sample=sample,check=backup_observation(previous_sample,sample))
                seen=sample['tick'];previous_sample=sample;ready=False
                ep.send(ipc/'w.sock',dict(kind='HEARTBEAT',generation=generation,tick=current_tick,ready=False))
                continue
            previous_sample=sample
            packet={k:v for k,v in sample.items() if k not in ('kind','tick')};packet['local_epoch']=boot
            result=assessment(packet,now,clock,boot,boot,True);seen=sample['tick'];last_processed=current_tick
            event('FEEDBACK_ACCEPTED',tick=current_tick,sample=sample);event('ASSESSMENT',tick=current_tick,packet=packet,sample=sample,now_local=now,valid_until_tick=current_tick+3,result=result)
            ready=result['development_action']=='CONTINUE';ep.send(ipc/'w.sock',dict(kind='HEARTBEAT',generation=generation,tick=current_tick,ready=ready))
            if ready and current_tick<config['steps']-config.get('quiesce_ticks',4):
                target=-2*(Q(sample['velocity'][0])+Q(sample['velocity'][1]))/2
                cmd=dict(kind='COMMAND',command_id=boot+':'+str(sample['tick']),generation=generation,source_tick=sample['tick'],expires_tick=current_tick+6,target=str(target),reply=str(path),claim_sha256=sha(result))
                event('COMMAND_INTENT',tick=current_tick,command=cmd);uncertain[cmd['command_id']]='UNKNOWN';intent_ticks[cmd['command_id']]=current_tick;ep.send(ipc/'p.sock',cmd)
                if config['scenario'] in ('duplicate_requests','conflicting_duplicate') and current_tick>=20:
                    repeated=dict(cmd)
                    if config['scenario']=='conflicting_duplicate':repeated['target']='.5'
                    ep.send(ipc/'p.sock',repeated);event('DUPLICATE_INJECTED',tick=current_tick,command_id=cmd['command_id'],changed=config['scenario']=='conflicting_duplicate')
        for name,status in list(uncertain.items()):
            if status=='UNKNOWN' and current_tick-intent_ticks.get(name,current_tick)>=4 and name not in timeout_reported:
                event('ACK_TIMEOUT',tick=current_tick,command_id=name);timeout_reported.add(name)
        if current_tick>=0 and current_tick-last_query>=8:
            ids=[k for k,v in uncertain.items() if v in ('UNKNOWN','QUEUED')][:8]
            if ids:ep.send(ipc/'p.sock',dict(kind='QUERY',ids=ids,reply=str(path)));event('QUERY_SENT',tick=current_tick,ids=ids)
            last_query=current_tick
        time.sleep(.001)


def watchdog(config,ipc,out):
    ep=Endpoint(ipc/'w.sock');log=Records(out/'watchdog',dict(role='watchdog',configuration_sha256=sha(config),source_sha256=config['sources']))
    ep.send(ipc/'p.sock',dict(kind='REGISTER_WATCHDOG',path=str(ipc/'w.sock')));ep.send(ipc/'m.sock',dict(kind='READY',role='watchdog',pid=os.getpid()))
    clock=None;now=None;tick=-1;heart=-100;generation=-1;ready=False;last_sample=-1;requested=False;grace_until=4;previous_sample=None;request_tick=None;deadline_reported=False
    while True:
        samples=[]
        for m in ep.drain():
            if m['kind']=='STOP':log.append('FINISHED',tick=tick);ep.close();return
            if m['kind']=='CLOCK':
                if clock is not None and clock.remote_epoch!=m['remote_epoch']:log.append('CLOCK_EPOCH_CHANGED',tick=tick,old_epoch=clock.remote_epoch,new_epoch=m['remote_epoch'])
                clock=make_map(m);log.append('CLOCK_MAP',message=m)
            if m['kind']=='REGISTER_CONTROLLER' and m['generation']>generation:generation=m['generation'];ready=False;grace_until=tick+4
            if m['kind']=='HEARTBEAT' and m['generation']==generation:heart=max(heart,m['tick']);ready=m['ready']
            if m['kind']=='TICK':tick=m['tick'];now=m['virtual_ms'];power=m['primary_power'];engaged=m['backup_engaged']
            if m['kind']=='OBS':samples.append(m)
        for sample in samples:
            if clock is None or now is None or sample['tick']<=last_sample:continue
            if requested:
                check=backup_observation(previous_sample,sample) if tick>request_tick+4 else dict(status='HANDOFF_OBSERVATION_PENDING',operational_authorization=False)
                log.append('BACKUP_OBSERVATION',tick=tick,sample=sample,check=check,reported_engaged=engaged)
                if tick>request_tick+4 and not engaged and not deadline_reported:
                    log.append('BACKUP_ENGAGEMENT_UNCONFIRMED',tick=tick,request_tick=request_tick);deadline_reported=True
                previous_sample=sample;last_sample=sample['tick'];continue
            previous_sample=sample
            last_sample=sample['tick'];healthy=((ready and tick-heart<3) or (tick<=grace_until and generation>=0)) and power
            packet={k:v for k,v in sample.items() if k not in ('kind','tick')};packet['local_epoch']='wd-0'
            result=assessment(packet,now,clock,'wd-0','wd-0',healthy);allow=result['development_action']=='CONTINUE' and not requested
            log.append('ASSESSMENT',tick=tick,packet=packet,now_local=now,healthy=healthy,last_heartbeat_tick=heart,sample=sample,valid_until_tick=tick+3,result=result)
            ep.send(ipc/'p.sock',dict(kind='PERMISSION',issued_tick=tick,expires_tick=tick+3,allow=allow,claim_sha256=sha(result)))
            if not allow and not requested:
                basis='CONDITIONAL_MODEL' if result['development_action']=='HANDOFF' else 'UNSUPPORTED_BEST_EFFORT'
                msg=dict(kind='BACKUP',command_id='watchdog-backup',basis=basis)
                log.append('FAILURE_DETECTED',tick=tick,heart_age=tick-heart,basis=basis)
                ep.send(ipc/'p.sock',msg);log.append('BACKUP_SENT',tick=tick,basis=basis);requested=True;request_tick=tick
        time.sleep(.001)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('role',choices=('plant','controller','watchdog'));p.add_argument('config',type=Path);p.add_argument('ipc',type=Path);p.add_argument('output',type=Path);p.add_argument('--generation',type=int,default=0);p.add_argument('--offset',type=int,default=0);a=p.parse_args();config=json.loads(a.config.read_text())
    if a.role=='plant':plant(config,a.ipc,a.output)
    elif a.role=='watchdog':watchdog(config,a.ipc,a.output)
    else:control(config,a.ipc,a.output,a.generation,a.offset)


if __name__=='__main__':main()
