"""LIVE01 conditional simulation evidence and lifecycle guards. No authority.

Logical clock beacons and manifests are explicit common-host assumptions.
Finite conformance checks do not authenticate sources or future physical facts.
"""
from copy import deepcopy
from fractions import Fraction as Q
from pathlib import Path,PurePosixPath
import hashlib,json,time,re
from . import evidence_recovery as adapter
from . import physical_time_recovery as physical
from .recovery_evidence import EvidenceJournal,PREMISE_NAMES
from .durable_feedback_session import canonical,sha
from .independent_clock_mapping import IndependentClockMap,tick
from .recovery_feedback_state_1d import _bounds
from .restart_process_experiment import BACKUP,FAMILY,DT

ASSUMED=('backup_timing_asserted','independent_handoff_asserted','power_independent_backup_asserted','no_impulse_handoff_asserted')
LEASE_FIELDS={'schema','id','seq','watchdog_generation','controller_generation','source_epoch','sample_id','issued_tick','expires_tick','issued_host_ns','expires_host_ns','basis_path','basis_sha256','public_sha256','assurance'}


def save(path,value):
    import os
    path=Path(path);pending=path.with_name('pending_'+path.name)
    with pending.open('xb') as f:f.write(canonical(value)+b'\n');f.flush();os.fsync(f.fileno())
    os.link(pending,path);fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    pending.unlink()


def model_contract():
    return dict(backup=deepcopy(BACKUP),family=deepcopy(FAMILY),active_force_cap='1',backup_delay_bound_seconds='.08',dynamics_id=physical.DYNAMICS_ID,power_domains=dict(primary_power='SIM_PRIMARY_RAIL',backup_power='SIM_BACKUP_RAIL'),measurement_source='SYNTHETIC_MEASURED_CHANNEL',measurement_error='0.00000002',clock_rate='1',authority='CONDITIONAL_SIMULATION_CONTRACT_ONLY')


def policy():return adapter.policy(source_ids={k:'LIVE01_'+k for k in PREMISE_NAMES},max_age_ticks=160)


def read_beacon(root):
    path=Path(root)/'clock.json'
    if path.is_symlink():raise ValueError('clock beacon symlink')
    raw=json.loads(path.read_bytes())
    if set(raw)!={'payload','sha256'} or sha(raw['payload'])!=raw['sha256']:raise ValueError('clock beacon identity mismatch')
    b=raw['payload']
    if set(b)!={'tick','sensor_epoch','plant_pid','host_ns','public_sha256'}:raise ValueError('clock beacon fields')
    tick(b['tick']);tick(b['host_ns'])
    return b


def input_bundle(sample,beacon,public,boot,*,primary_healthy):
    if sample['source_id']!=public['model']['measurement_source'] or sample['remote_epoch']!=beacon['sensor_epoch']:raise ValueError('measurement source/epoch mismatch')
    if type(sample['tick']) is not int or sample['tick']>beacon['tick']:raise ValueError('future sample')
    local=boot;remote=sample['remote_epoch'];offset=sample['clock_offset_ms'];tube=public.get('assessment_mode')=='STATE_TUBE_WINDOW_V1'
    if type(offset) is not int:raise ValueError('explicit synthetic clock offset')
    clock=IndependentClockMap(local_epoch=local,remote_epoch=remote,rate_bounds=['1','1'],max_extrapolation=100000)
    if tube:
        if beacon['tick']-sample['tick']>3:raise ValueError('source age outside declared virtual limit')
        clock.add(dict(id=remote+':'+local,local_epoch=local,remote_epoch=remote,local_send=0,remote_receive=0,remote_send=0,local_receive=0))
    else:clock.add(dict(id=remote+':'+local,local_epoch=local,remote_epoch=remote,local_send=0,remote_receive=offset,remote_send=offset,local_receive=0))
    p,v=_bounds(sample['position']),_bounds(sample['velocity']);model=public['model'];mass=_bounds(model['family']['mass'])
    acc=(Q(model['active_force_cap'])+Q(model['backup']['disturbance']))/mass.lo
    horizon=DT*(beacon['tick']-sample['tick']+2) if tube else DT;p,v=physical.transport(p,v,acc,Q(0),horizon)
    packet=dict(remote_time=0 if tube else sample['remote_time'],local_epoch=local,remote_epoch=remote,frame=sample['frame'],source_id=('LIVE_TUBE:'+sha(dict(sample=sample,beacon=beacon,horizon=str(horizon)))) if tube else sample['source_id'],position=p.wire(),velocity=v.wire())
    return dict(backup=model['backup'],parameter_bounds=model['family'],packet=packet,clock_map=clock,now_local=0 if tube else 20*beacon['tick'],units_per_second='1000',max_state_age_seconds='0' if tube else '.06',local_epoch=local,boot_id=boot,active_force_cap=model['active_force_cap'],handoff_delay_seconds=['0',model['backup_delay_bound_seconds']],monitor_seconds='.10',primary_healthy=primary_healthy,dynamics_id=model['dynamics_id'])


def collect(sample,beacon,public,boot,*,primary_healthy):
    a=input_bundle(sample,beacon,public,boot,primary_healthy=primary_healthy);statement=adapter.statement_for(a);m=public['model'];tube=public.get('assessment_mode')=='STATE_TUBE_WINDOW_V1';source_tick=0 if tube else 20*sample['tick']
    observations=[
        [sample['position_center'],sample['velocity_center']],
        [m['backup']['mass'],m['backup']['spring'],m['backup']['damping']],
        ['0' if tube else str(Q(sample['remote_time'])-sample['clock_offset_ms'])],
        [m['active_force_cap']],
        dict(backup=m['backup'],dynamics_id=sample['reported_dynamics_id']),
        [m['backup_delay_bound_seconds']],
        {k:str(sample['topology'][k]) for k in ('controller','watchdog','plant')},
        m['power_domains'],
        ['0','0'],
    ]
    rows=[];provenance=[];p=policy()
    for n,(key,value) in enumerate(zip(PREMISE_NAMES,observations)):
        assumed=key in ASSUMED;kind='ASSERTED' if public['arm']=='STRICT_OBSERVATIONS' and assumed else 'OBSERVATION'
        if key=='active_cap_asserted' and not sample['support_valid']:kind='UNKNOWN'
        row=dict(id=f'{boot}:{sample["id"]}:{n}',premise=key,source_id=p[key]['source_id'],scope='DEVELOPMENT_SIMULATION',statement_sha256=sha(statement),boot_id=boot,clock_domain=boot,observed_tick=source_tick,expires_tick=source_tick+160,kind=kind,observations=value if kind=='OBSERVATION' else None)
        rows.append(row);provenance.append(dict(premise=key,kind=kind,basis='DECLARED_MODEL_ASSUMPTION' if assumed else 'SYNTHETIC_CHANNEL_OR_MANIFEST_CONSISTENCY',basis_sample_sha256=sha(sample),independent_physical_evidence=False))
    return a,rows,provenance


def assess_frame(root,relative,sample,public,boot,*,primary_healthy,controller_generation,delay_seconds=0,clock=read_beacon,host_clock=time.monotonic_ns):
    start_host=host_clock();before=None;directory=Path(root)/relative;directory.mkdir(exist_ok=False,parents=True)
    backend=public.get('evidence_backend','PER_RECORD_JOURNAL_V1')
    out=dict(result=None,reason=None,beacon_before=before,beacon_after=None,adapter_finish_beacon=None,start_host_ns=start_host,finish_host_ns=None,public_sha256=sha(public),sample=deepcopy(sample),boot=boot,controller_generation=controller_generation,primary_healthy=primary_healthy,provenance=[],time_basis=None,evidence_backend=backend,operational_authorization=False,hardware_validation=False,independent_attestation=False,future_physical_assumptions=list(ASSUMED),evidence_semantics='FINITE_SYNTHETIC_PREDICATES_NOT_PHYSICAL_AUTHENTICATION')
    try:
        before=clock(root);out['beacon_before']=before
        if before['public_sha256']!=sha(public):raise ValueError('beacon/public mismatch')
        if sample['emitted_host_ns']>start_host or start_host-sample['emitted_host_ns']>public['max_observation_host_ns']:raise ValueError('future or host-stale observation')
        inputs,rows,provenance=collect(sample,before,public,boot,primary_healthy=primary_healthy);out['provenance']=provenance
        tube=public.get('assessment_mode')=='STATE_TUBE_WINDOW_V1'
        out['time_basis']=dict(kind='STATE_TUBE_WINDOW_V1' if tube else 'SNAPSHOT_SAME_TICK',source_tick=sample['tick'],source_host_ns=sample['emitted_host_ns'],reference_tick=0 if tube else 20*before['tick'],max_cursor_advance=1 if tube else 0,state_transport_horizon_seconds=str(DT*(before['tick']-sample['tick']+2) if tube else DT))
        save(directory/'artifacts.json',rows)
        if backend=='ATOMIC_BUNDLE_V1':
            from .live_evidence_bundle import FrameTransaction
            writer=FrameTransaction(policy=policy(),boot_id=boot,clock_domain=boot,now=inputs['now_local'])
        elif backend=='PER_RECORD_JOURNAL_V1':writer=EvidenceJournal.create(directory/'evidence',policy=policy(),boot_id=boot,clock_domain=boot,now=inputs['now_local'])
        else:raise ValueError('unknown evidence persistence backend')
        with writer as journal:
            for row in rows:journal.submit(row,now=inputs['now_local'])
            if delay_seconds:time.sleep(delay_seconds)
            def completion_clock():
                out['adapter_finish_beacon']=clock(root);return 0 if tube else 20*out['adapter_finish_beacon']['tick']
            out['result']=adapter.assess(journal,inputs,finish_clock=completion_clock)
            if backend=='ATOMIC_BUNDLE_V1':journal.persist(directory/'evidence_bundle.json')
        out['beacon_after']=clock(root);out['finish_host_ns']=host_clock()
        out['reason']=completion_reason(out,public)
    except Exception as exc:
        out['reason']='COLLECTOR_OR_ASSESSMENT_FAILURE';out['error_type']=type(exc).__name__;out['error']=str(exc);out['finish_host_ns']=host_clock()
    save(directory/'result.json',out);return out


def completion_reason(basis,public):
    result=basis['result'];before=basis['beacon_before'];after=basis['beacon_after']
    evidence=result.get('evidence') or {}
    # Material contradictions must not disappear behind a transient timing miss.
    if any(x['status'] in ('CONTRADICTED','INVALID_EVIDENCE','LEDGER_FAULT') for x in evidence.get('premises',{}).values()):return 'CONTRADICTORY_OR_INVALID_EVIDENCE'
    limit=1 if public.get('assessment_mode')=='STATE_TUBE_WINDOW_V1' else 0
    if after['sensor_epoch']!=before['sensor_epoch'] or not 0<=after['tick']-before['tick']<=limit:return 'PLANT_CLOCK_ADVANCED_OR_RESET'
    if basis['finish_host_ns']-basis['start_host_ns']>=public['computation_budget_ns']:return 'NATIVE_COMPUTATION_BUDGET_EXCEEDED'
    if basis['sample']['emitted_host_ns']>basis['finish_host_ns'] or basis['finish_host_ns']-basis['sample']['emitted_host_ns']>public['max_observation_host_ns']:return 'OBSERVATION_EXPIRED_DURING_COMPUTATION'
    if result['development_action'] is None:return result['reason'] or 'NO_SUPPORTED_MODEL_PLAN'
    return None


def make_lease(basis,relative,public,*,generation,seq,issue_host_ns=None,issue_beacon=None):
    if basis['reason'] is not None or basis['result']['development_action']!='CONTINUE':raise ValueError('no live conditional candidate')
    issued=basis['beacon_after']['tick'];now=basis['finish_host_ns'] if issue_host_ns is None else issue_host_ns
    tick(now)
    if now<basis['finish_host_ns']:raise ValueError('publication time precedes assessment completion')
    if basis['boot']!=f'watchdog-{generation}':raise ValueError('publication watchdog generation differs')
    if issue_beacon is not None and (issue_beacon['tick']!=issued or issue_beacon['sensor_epoch']!=basis['beacon_after']['sensor_epoch']):raise ValueError('plant clock changed before lease issue')
    if now-basis['start_host_ns']>=public['computation_budget_ns']:raise ValueError('computation/publication budget exceeded')
    return dict(schema='LIVE01_LEASE',id=f'w{generation}:{seq}',seq=seq,watchdog_generation=generation,controller_generation=basis['controller_generation'],source_epoch=basis['sample']['remote_epoch'],sample_id=basis['sample']['id'],issued_tick=issued,expires_tick=issued+6,issued_host_ns=now,expires_host_ns=now+public['lease_host_ns'],basis_path=relative+'/result.json',basis_sha256=sha(basis),public_sha256=sha(public),assurance='CONDITIONAL_SIMULATION_CONTRACT_ONLY')


def lease_check(lease,*,now_tick,now_host_ns,controller_generation,watchdog_generation,source_epoch,public_sha256,revoked_seq,primary_power,recovery_latched):
    out=dict(allowed=False,reason=None,operational_authorization=False)
    try:
        if type(lease) is not dict or set(lease)!=LEASE_FIELDS or lease['schema']!='LIVE01_LEASE' or lease['assurance']!='CONDITIONAL_SIMULATION_CONTRACT_ONLY':raise ValueError('invalid lease contract')
        for k in ('seq','watchdog_generation','controller_generation','issued_tick','expires_tick','issued_host_ns','expires_host_ns'):tick(lease[k])
        tick(now_tick);tick(now_host_ns);tick(controller_generation);tick(watchdog_generation)
        if type(revoked_seq) is not int or revoked_seq<-1:raise ValueError('revocation sequence required')
        if type(primary_power) is not bool or type(recovery_latched) is not bool:raise ValueError('explicit local state required')
        if not primary_power:return dict(out,reason='PRIMARY_POWER_UNAVAILABLE')
        if recovery_latched:return dict(out,reason='RECOVERY_LATCHED')
        if lease['public_sha256']!=public_sha256:return dict(out,reason='PUBLIC_CONTRACT_MISMATCH')
        if lease['controller_generation']!=controller_generation or lease['watchdog_generation']!=watchdog_generation:return dict(out,reason='GENERATION_MISMATCH')
        if lease['source_epoch']!=source_epoch:return dict(out,reason='SOURCE_EPOCH_MISMATCH')
        if lease['seq']<=revoked_seq:return dict(out,reason='REVOKED_SEQUENCE')
        if not lease['issued_tick']<=now_tick<lease['expires_tick'] or lease['expires_tick']>lease['issued_tick']+6:return dict(out,reason='VIRTUAL_LEASE_EXPIRED_OR_FUTURE')
        if not lease['issued_host_ns']<=now_host_ns<lease['expires_host_ns'] or lease['expires_host_ns']>lease['issued_host_ns']+160000000:return dict(out,reason='NATIVE_LEASE_EXPIRED_OR_FUTURE')
        return dict(out,allowed=True)
    except (ValueError,TypeError,KeyError,OverflowError):return dict(out,reason='MALFORMED_LEASE')


def load_basis(root,lease):
    relative=PurePosixPath(lease['basis_path'])
    if relative.is_absolute() or '..' in relative.parts or len(relative.parts)!=4 or relative.parts[1]!='assessments' or relative.name!='result.json':raise ValueError('unsafe basis path')
    path=Path(root)
    for component in relative.parts:
        path=path/component
        if path.is_symlink():raise ValueError('basis symlink')
    raw=json.loads(path.read_bytes());r=raw['result']
    if any(raw.get(k) is not False for k in ('operational_authorization','hardware_validation','independent_attestation')) or raw.get('future_physical_assumptions')!=list(ASSUMED):raise ValueError('outer authority/scope mismatch')
    if relative.parts[0]!=f'watchdog-{lease["watchdog_generation"]}' or raw['boot']!=relative.parts[0]:raise ValueError('basis watchdog generation mismatch')
    if sha(raw)!=lease['basis_sha256'] or raw['reason'] is not None or raw['public_sha256']!=lease['public_sha256'] or raw['controller_generation']!=lease['controller_generation']:raise ValueError('basis binding mismatch')
    limit=1 if raw.get('time_basis',{}).get('kind')=='STATE_TUBE_WINDOW_V1' else 0
    if not 0<=lease['issued_tick']-raw['beacon_before']['tick']<=limit or raw['beacon_after']['tick']!=lease['issued_tick'] or raw['sample']['id']!=lease['sample_id'] or raw['sample']['remote_epoch']!=lease['source_epoch']:raise ValueError('basis clock/sample mismatch')
    if r['status']!='DEVELOPMENT_EVIDENCE_BACKED_CONDITIONAL_PLAN' or r['development_action']!='CONTINUE' or not r['conditional_continuous_containment'] or any(r.get(k) is not False for k in ('dispatch','operational_authorization','hardware_validation','independent_attestation')):raise ValueError('unsupported authority/basis')
    if set(r['evidence']['premises'])!=set(PREMISE_NAMES) or any(x['status']!='SUPPORTED_SIMULATION_PREDICATE' for x in r['evidence']['premises'].values()):raise ValueError('incomplete premise vector')
    return raw


def command_check(message,*,expected_reply):
    """Reject malformed arithmetic before queueing, without touching the plant."""
    try:
        if type(message) is not dict or set(message)!={'kind','command_id','generation','lease_id','basis_sha256','target','reply'} or message['kind']!='COMMAND':raise ValueError('command fields')
        tick(message['generation'])
        if type(message['command_id']) is not str or re.fullmatch(r'c[0-9]{1,10}:[0-9]{1,20}',message['command_id']) is None:raise ValueError('command identity')
        if not message['command_id'].startswith(f'c{message["generation"]}:'):raise ValueError('command boot prefix')
        if type(message['lease_id']) is not str or not 0<len(message['lease_id'])<=128:raise ValueError('lease identity')
        if type(message['basis_sha256']) is not str or re.fullmatch('[0-9a-f]{64}',message['basis_sha256']) is None:raise ValueError('basis hash')
        if message['reply']!=expected_reply:raise ValueError('reply endpoint')
        value=message['target']
        if type(value) is not str or re.fullmatch(r'[+-]?[0-9]{1,40}(?:\.[0-9]{1,40}|/[0-9]{1,40})?',value) is None:raise ValueError('bounded rational target')
        Q(value)
        return dict(valid=True,reason=None)
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError):return dict(valid=False,reason='MALFORMED_COMMAND')


class EffectBeliefs:
    """Terminal beliefs never become QUEUED through a late acknowledgement."""
    def __init__(self):self.states={};self.conflicts=[]
    def merge(self,name,status):
        old=self.states.get(name,'UNKNOWN')
        if type(status) is not str or (status not in ('UNKNOWN','QUEUED','CONSUMED','EFFECT_UNCERTAIN','REJECTED') and not status.startswith('REJECTED_')):
            self.states[name]='EFFECT_UNCERTAIN';self.conflicts.append(dict(command_id=name,old=old,new=status,reason='MALFORMED_STATUS'));return 'EFFECT_UNCERTAIN'
        terminal=lambda s:s=='CONSUMED' or s.startswith('REJECTED')
        if old=='EFFECT_UNCERTAIN':return old
        if status=='EFFECT_UNCERTAIN':self.states[name]=status;self.conflicts.append(dict(command_id=name,old=old,new=status,reason='EXPLICIT_UNCERTAINTY_REPORT'));return status
        if terminal(old):
            if terminal(status) and old!=status:self.states[name]='EFFECT_UNCERTAIN';self.conflicts.append(dict(command_id=name,old=old,new=status))
        elif status!='UNKNOWN' or name not in self.states:self.states[name]=status
        return self.states.get(name,old)


def observation_problem(sample,public):
    try:
        tick(sample['tick']);tick(sample['emitted_host_ns'])
        if sample['source_id']!=public['model']['measurement_source'] or sample['frame']!='WORLD_X_SI':return 'SOURCE_OR_FRAME_MISMATCH'
        if sample['reported_dynamics_id']!=public['model']['dynamics_id']:return 'REPORTED_MODEL_CONTRADICTION'
        if sample['support_valid'] is not True:return 'SUPPORT_REVOKED'
        for field in ('position','velocity'):
            if not _bounds(sample[field]).contains(Q(sample[field+'_center'])):return 'MEASUREMENT_SELF_CONSISTENCY_FAILURE'
        if type(sample['clock_offset_ms']) is not int or sample['remote_time']!=20*sample['tick']+sample['clock_offset_ms']:return 'CLOCK_PACKET_INCONSISTENT'
        topology=sample['topology']
        if set(topology)!=set(('controller','watchdog','plant')) or len(set(topology.values()))!=3 or any(type(v) is not int or v<=0 for v in topology.values()):return 'LOGICAL_TOPOLOGY_INCONSISTENT'
        return None
    except Exception:return 'MALFORMED_OBSERVATION'


def select_samples(samples,*,seen,known,public):
    """Coalesce backlog only after inspecting every packet for material faults."""
    events=[];updates={};candidates=[];critical=None;critical_sample=None
    for sample in samples:
        name=sample.get('id');digest=sha(sample)
        if type(name) is not str:
            critical='MALFORMED_OBSERVATION';events.append(dict(kind='FEEDBACK_INVALID',sample=sample));continue
        previous=updates.get(name,known.get(name))
        if previous is not None and previous!=digest:
            critical='SAMPLE_ID_CONFLICT';events.append(dict(kind='FEEDBACK_ID_CONFLICT',sample=sample,previous_sha256=previous));continue
        if previous is None:updates[name]=digest;events.append(dict(kind='FEEDBACK_DIGEST',sample_id=name,sample_sha256=digest))
        problem=observation_problem(sample,public)
        if problem is not None:
            critical=problem;events.append(dict(kind='FEEDBACK_INVALID',sample=sample,reason=problem))
            if type(sample.get('tick')) is int and sample['tick']>seen:critical_sample=sample
            continue
        if sample['tick']<=seen:events.append(dict(kind='REPLAY_IGNORED',tick=sample['tick'],sample_id=name));continue
        candidates.append(sample)
    selected=critical_sample if critical is not None else max(candidates,key=lambda s:s['tick']) if candidates else None
    for sample in candidates:
        if sample is not selected:events.append(dict(kind='FEEDBACK_SUPERSEDED',tick=sample['tick'],sample_id=sample['id'],reason='CRITICAL_PACKET_PRESENT' if critical else 'NEWER_VALID_PACKET_AVAILABLE'))
    return dict(selected=selected,critical=critical,events=events,digest_updates=updates)
