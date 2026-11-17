"""Synthetic end-to-end runtime-core study; no native actuation or Holdout."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

from aegis.development.durable_feedback_session import DurableFeedbackSession as Store,canonical,sha,runtime_identity
from aegis.development.independent_clock_mapping import IndependentClockMap
from aegis.development.runtime_readiness import DeadlineGuard,restart_check,calibration_check,select_response
from scripts.research import temporal_feedback_study_1d as temporal
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError,inspect

ROOT=Path(__file__).resolve().parents[2]
STUDY='V9-M5 runtime core foundations synthetic integration v1'
FILES=temporal.FILES+('src/aegis/development/durable_feedback_session.py','src/aegis/development/independent_clock_mapping.py',
    'src/aegis/development/runtime_readiness.py','scripts/research/runtime_core_study.py',
    'tests/test_durable_feedback_session.py','tests/test_independent_clock_mapping.py','tests/test_runtime_readiness.py','tests/test_runtime_core_study.py')


def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
def plan():
    names=('nominal_candidate','restart_replay','checkpoint_mismatch','checkpoint_absent','asymmetric_clock',
        'clock_epoch_reset','stale_restart_state','deadline_before_compute','deadline_after_compute',
        'calibration_missing','calibration_point_error','unsafe_recovery_prefix','missing_state','hardware_mode')
    return [dict(id=name,classification='EXPLICIT_SYNTHETIC_DEVELOPMENT_DESIGN') for name in names]


def case_inputs(name):
    base=temporal.plan()[0]
    config={k:deepcopy(base[k]) for k in ('model','session_id','clock_id','start_tick','limits','assumptions')}
    reaction=0
    if name=='unsafe_recovery_prefix':config['model'].update(horizon=10,terminal_samples=2,terminal_velocity=['-1','1']);reaction=3
    mapper=IndependentClockMap(local_epoch='clock-A',remote_epoch='sensor-boot',rate_bounds=['1','1'],max_extrapolation=0)
    exchange=dict(id='exchange-1',local_epoch='clock-A',remote_epoch='sensor-boot',local_send=100,remote_receive=1000,remote_send=1000,local_receive=100)
    if name=='asymmetric_clock':exchange.update(local_send=90,local_receive=110)
    mapper.add(exchange)
    mapping=mapper.map_event(1000,local_epoch='new-clock' if name=='clock_epoch_reset' else 'clock-A',remote_epoch='sensor-boot')
    operations=deepcopy(base['operations'][:-1]);state_op=operations[0]
    if name=='unsafe_recovery_prefix':state_op['packet']['payload'].update(position=['.33','.33'],velocity=['-.5','-.5'])
    if not mapping.get('exact_integer_tick') or name=='missing_state':operations=operations[1:]
    else:state_op['packet']['event_tick']=int(mapping['local_interval'][0])
    return config,reaction,mapping,exchange,operations


def calibration_inputs(name):
    profile=dict(classification='SYNTHETIC_ONLY',device_id='synthetic-device',reference_id='synthetic-reference',frame='WORLD_X_SI',velocity_error_bound='.01',force_error_bound='.02')
    samples=[dict(id='sample-1',device_id='synthetic-device',reference_id='synthetic-reference',frame='WORLD_X_SI',sample_ns=1005,
        velocity=['.5','.5'],force=['0','0'],reference_velocity=['.5','.5'],reference_force=['0','0'])]
    if name=='calibration_missing':samples=[]
    if name=='calibration_point_error':samples[0]['velocity']=['.52','.52']
    return profile,samples


def deadline_inputs(name):
    return [2000,2010] if name=='deadline_before_compute' else [2000,2001,2010] if name=='deadline_after_compute' else [2000,2001,2002]


def restart_inputs(name,checkpoint,mapping):
    fresh={key:dict(boot_id='runtime-boot',observed_ns=1005,received_ns=1006,evidence_asserted=True) for key in ('STATE','ACTUATOR','POWER','CLOCK_MAP')}
    fresh['CLOCK_MAP']['evidence_asserted']=mapping.get('exact_integer_tick') is True
    fresh['STATE']['evidence_asserted']=mapping.get('exact_integer_tick') is True and name!='missing_state'
    if name=='stale_restart_state':fresh['STATE']['observed_ns']=999
    args=dict(actual_checkpoint=checkpoint,expected_checkpoint=deepcopy(checkpoint),actual_runtime=runtime_identity(),
        expected_runtime=runtime_identity(),boot_id='runtime-boot',boot_start_ns=1000,now_ns=1010,freshness_limit_ns=10,fresh_observations=fresh)
    if name=='checkpoint_mismatch':args['expected_checkpoint']['head_sha256']='0'*64
    if name=='checkpoint_absent':args['expected_checkpoint']=None
    return args


def run_case(a,directory,emit=None):
    directory=Path(directory);directory.mkdir(exist_ok=False);name=a['id']
    config,reaction,mapping,exchange,operations=case_inputs(name)
    store=Store.create(directory/'store',config,store_id='synthetic-'+name);counter=0
    def apply(op):
        nonlocal counter
        if emit:emit(dict(phase='DURABLE_OPERATION_INTENT',index=counter,operation=op))
        value=store.apply(op)
        if emit:emit(dict(phase='DURABLE_OPERATION_RESULT',index=counter,result_sha256=sha(value['result']),checkpoint=value['checkpoint']))
        counter+=1;return value['result']
    replay=None
    try:
        for op in operations:apply(op)
        if name=='restart_replay':
            pin=store.checkpoint;store.close();store=Store.open(directory/'store',expected_checkpoint=pin)
            replay=apply(operations[0])['status']
        checkpoint_before=store.checkpoint
        restart_args=restart_inputs(name,checkpoint_before,mapping)
        restarted=restart_check(**restart_args)
        profile,samples=calibration_inputs(name)
        calibration=calibration_check(profile,samples)
        ticks=deadline_inputs(name)
        iterator=iter(ticks);guard=DeadlineGuard(boot_id='runtime-boot',clock=lambda:next(iterator));budget=guard.begin(10);saved=[]
        assessment_op=temporal.assess(100,reaction)
        def compute():
            r=apply(assessment_op);saved.append(r);return r
        if emit:emit(dict(phase='COMPUTATION_BUDGET_INTENT',ticks=ticks,budget_ns=10))
        deadline=guard.evaluate(budget,compute);assessed=saved[0] if saved else None
        response=select_response(assessed or {},deadline=deadline,restart=restarted,calibration=calibration,
                                 boot_id='runtime-boot',mode='HARDWARE' if name=='hardware_mode' else 'DEVELOPMENT_SIMULATION')
        checkpoint=store.checkpoint
    finally:store.close()
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((directory/'store').iterdir()) if p.is_file()}
    return dict(id=name,config=config,mapping=mapping,exchange=exchange,restart_args=restart_args,restart=restarted,
        calibration_profile=profile,calibration_samples=samples,calibration=calibration,deadline_ticks=ticks,deadline=deadline,
        assessment_operation=assessment_op,temporal=assessed,response=response,restart_replay_status=replay,
        final_checkpoint=checkpoint,closed_store_files=files,durable_operation_count=counter,
        physics_steps=0,hardware_validation=False,operational_authorization=False,gate_b='GATE_B_NOT_AUTHORIZED')


def summary(r):
    return dict(response=r['response']['status'],reason=r['response']['reason'],restart=r['restart']['status'],
        clock_mapping=r['mapping']['status'],clock_exact=r['mapping'].get('exact_integer_tick',False),deadline=r['deadline']['status'],
        calibration=r['calibration']['status'],replay_status=r['restart_replay_status'],durable_operations=r['durable_operation_count'],
        combined_containment=None if r['temporal'] is None else r['temporal']['combined_finite_horizon_containment'],
        hardware_validation=False,dispatch=False,operational_authorization=False)


def audit_case(a,raw,source_dir,workdir):
    """Never open original SQLite for mutation; audit a fresh copy only."""
    if raw['id']!=a['id'] or raw['gate_b']!='GATE_B_NOT_AUTHORIZED':raise ValueError('case identity mismatch')
    config,reaction,mapping,exchange,ops=case_inputs(a['id'])
    expected_assessment=temporal.assess(100,reaction)
    if (raw['config'],raw['mapping'],raw['exchange'],raw['assessment_operation'])!=(config,mapping,exchange,expected_assessment):raise ValueError('fixed case inputs changed')
    if (raw['calibration_profile'],raw['calibration_samples'])!=calibration_inputs(a['id']) or raw['deadline_ticks']!=deadline_inputs(a['id']):raise ValueError('fixed calibration/deadline inputs changed')
    if any(p.is_symlink() for p in (source_dir/'store').iterdir()):raise ValueError('symlinked store evidence rejected')
    actual={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((source_dir/'store').iterdir()) if p.is_file()}
    if actual!=raw['closed_store_files']:raise ValueError('closed store hash mismatch')
    workdir.mkdir(exist_ok=False);shutil.copytree(source_dir/'store',workdir/'store')
    with Store.open(workdir/'store',expected_checkpoint=raw['final_checkpoint']) as store:
        events=store._con.execute('SELECT operation,result,digest FROM events ORDER BY seq').fetchall()
        expected_ops=list(ops)
        if a['id']=='restart_replay':expected_ops.append(ops[0])
        if a['id']!='deadline_before_compute':expected_ops.append(expected_assessment)
        if [json.loads(op) for op,_,_ in events]!=expected_ops:raise ValueError('durable operations differ from fixed plan')
        if json.loads(store._con.execute('SELECT header FROM metadata').fetchone()[0])['config']!=config:raise ValueError('store configuration differs from plan')
        assessments=[digest for op,digest,_ in events if json.loads(op)['type']=='ASSESS']
        if raw['temporal'] is None:
            if assessments:raise ValueError('withheld pre-computation case unexpectedly assessed')
        elif assessments!=[sha(raw['temporal'])]:raise ValueError('temporal result not bound to reconstructed durable operation')
        before=raw['restart_args']['actual_checkpoint'];n=before['seq']
        row=store._con.execute('SELECT digest FROM events WHERE seq=?',(n,)).fetchone() if n else None
        expected=dict(raw['final_checkpoint'],seq=n,head_sha256=row[0] if row else raw['final_checkpoint']['header_sha256'])
        if before!=expected:raise ValueError('restart checkpoint not a recorded prefix')
        if raw['restart_args']!=restart_inputs(a['id'],before,mapping):raise ValueError('fixed restart premises changed')
        expected_events=[];budget_logged=False
        for index,(op,digest,chain) in enumerate(events):
            op=json.loads(op)
            if op['type']=='ASSESS':
                expected_events.append(dict(phase='COMPUTATION_BUDGET_INTENT',ticks=raw['deadline_ticks'],budget_ns=10));budget_logged=True
            expected_events.append(dict(phase='DURABLE_OPERATION_INTENT',index=index,operation=op))
            expected_events.append(dict(phase='DURABLE_OPERATION_RESULT',index=index,result_sha256=digest,
                checkpoint=dict(raw['final_checkpoint'],seq=index+1,head_sha256=chain)))
        if not budget_logged:expected_events.append(dict(phase='COMPUTATION_BUDGET_INTENT',ticks=raw['deadline_ticks'],budget_ns=10))
    mapper=IndependentClockMap(local_epoch='clock-A',remote_epoch='sensor-boot',rate_bounds=['1','1'],max_extrapolation=0)
    mapper.add(raw['exchange']);mapping=mapper.map_event(1000,local_epoch='new-clock' if a['id']=='clock_epoch_reset' else 'clock-A',remote_epoch='sensor-boot')
    if mapping!=raw['mapping']:raise ValueError('clock mapping reconstruction mismatch')
    restarted=restart_check(**raw['restart_args']);calibration=calibration_check(raw['calibration_profile'],raw['calibration_samples'])
    iterator=iter(raw['deadline_ticks']);guard=DeadlineGuard(boot_id='runtime-boot',clock=lambda:next(iterator));budget=guard.begin(10)
    deadline=guard.evaluate(budget,lambda:raw['temporal'])
    response=select_response(raw['temporal'] or {},deadline=deadline,restart=restarted,calibration=calibration,
        boot_id='runtime-boot',mode='HARDWARE' if a['id']=='hardware_mode' else 'DEVELOPMENT_SIMULATION')
    if (restarted,calibration,deadline,response)!=(raw['restart'],raw['calibration'],raw['deadline'],raw['response']):raise ValueError('runtime component reconstruction mismatch')
    if actual!={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((source_dir/'store').iterdir()) if p.is_file()}:raise ValueError('original store changed during audit')
    return expected_events


def run(directory):
    directory=Path(directory);directory.mkdir(exist_ok=False);sources=hashes()
    metadata=dict(source_sha256=sources,runtime=runtime_identity(),parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),gate_b='GATE_B_NOT_AUTHORIZED')
    assignments=[dict(a,metadata=metadata) for a in plan()]
    with DevelopmentLedger.create(directory/'assignments.jsonl',study=STUDY,assignments=assignments,record_events=True) as log:
        for a in assignments:
            log.start(a['id'])
            try:
                r=run_case(a,directory/a['id'],emit=lambda e:log.event(a['id'],details=e));data=canonical(r)
                with (directory/(a['id']+'.json')).open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
                if hashes()!=sources:raise ValueError('sources changed during study')
                log.complete(a['id'],status='COMPLETED',details=dict(output_sha256=hashlib.sha256(data).hexdigest(),summary=summary(r),sources_after=sources))
            except (LedgerError,LedgerWriteError):raise
            except Exception as exc:log.complete(a['id'],status='ERROR',details=dict(error_type=type(exc).__name__,error=str(exc)));raise
        log.finalize()
    return dict(study=STUDY,counts=inspect(directory/'assignments.jsonl')['counts'],metadata=metadata,gate_b='GATE_B_NOT_AUTHORIZED')


def audit(directory,workdir):
    directory=Path(directory);workdir=Path(workdir);workdir.mkdir(exist_ok=False)
    log=inspect(directory/'assignments.jsonl');header=log['records'][0];assignments=header['assignments'];meta=assignments[0]['metadata']
    if header['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan():raise ValueError('study/plan mismatch')
    if any(a['metadata']!=meta for a in assignments) or meta['source_sha256']!=hashes() or meta['runtime']!=runtime_identity():raise ValueError('source/runtime mismatch')
    rows={};active=None;events=[]
    for record in log['records']:
        if record['kind']=='START':
            if active is not None:raise ValueError('nonsequential runtime study')
            active=record['id'];events=[]
        elif record['kind']=='EVENT':
            if record['id']!=active:raise ValueError('runtime event order')
            events.append(record['details'])
        if record['kind']=='TERMINAL' and record['status']=='COMPLETED':
            name=record['id'];path=directory/(name+'.json');data=path.read_bytes();r=json.loads(data);details=record['details']
            if name!=active or path.is_symlink():raise ValueError('terminal order or unsafe result')
            if hashlib.sha256(data).hexdigest()!=details['output_sha256'] or details['sources_after']!=meta['source_sha256']:raise ValueError('raw/source hash mismatch')
            a=next(x for x in assignments if x['id']==name);expected_events=audit_case(a,r,directory/name,workdir/name)
            if expected_events!=events:raise ValueError('durable intent/result log mismatch')
            if summary(r)!=details['summary']:raise ValueError('derived summary mismatch')
            rows[name]=summary(r);active=None
        elif record['kind']=='TERMINAL' and record['status']=='ERROR':active=None
    return dict(study=STUDY,ledger_state=log['state'],counts=log['counts'],metadata=meta,
        assignments=[dict(id=a['id'],state=log['assignments'][a['id']],summary=rows.get(a['id'])) for a in assignments],
        physics_steps=0,hardware_validation=False,operational_authorization=False,gate_b='GATE_B_NOT_AUTHORIZED')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--workdir',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    if a.mode=='audit' and a.workdir is None:p.error('audit requires a new --workdir')
    r=run(a.directory) if a.mode=='run' else audit(a.directory,a.workdir)
    with a.output.open('xb') as f:f.write(canonical(r));f.write(b'\n')
    print(json.dumps(dict(counts=r['counts'],gate_b=r['gate_b'])))


if __name__=='__main__':main()
