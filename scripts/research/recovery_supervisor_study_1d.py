"""Native sampled-force architecture ablation for a proposed mechanical backup.

The native plant's true state is used only by physical force-law simulation,
sensor generation and scoring. The supervisor receives bounded sensor packets.
The two arms differ in backup architecture; this is NOT an algorithm-only or
confirmatory comparison. Gravity support remains powered; no airborne claim.
"""
import argparse
from collections import deque
from copy import deepcopy
from fractions import Fraction as Q
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import numpy as np
import mujoco

from aegis.development.passive_backup_supervisor_1d import assess_supervisor,certificate,model,energy_box,check_backup_step
from aegis.development.recovery_envelope_1d import point
from aegis.development.dynamic_braking import DelayedSlewBrake
from aegis.env.mujoco_power_brake import PowerBrakeEnvironment
from aegis.development.temporal_feedback_1d import TemporalFeedbackSession
from aegis.development.runtime_readiness import DeadlineGuard,restart_check,calibration_check
from aegis.development.durable_feedback_session import runtime_identity,canonical,sha
from scripts.research import runtime_core_study as previous
from scripts.research import dynamic_braking_study as dynamic
from scripts.research import temporal_feedback_study_1d as temporal
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError,inspect

ROOT=Path(__file__).resolve().parents[2]
STUDY='V9-M5 proposed passive backup reserve supervisor architecture ablation v1'
FILES=tuple(dict.fromkeys(previous.FILES+dynamic.FILES+('src/aegis/development/passive_backup_supervisor_1d.py',
    'scripts/research/recovery_supervisor_study_1d.py','tests/test_passive_backup_supervisor_1d.py','tests/test_recovery_supervisor_study_1d.py')))
CASES=('nominal','primary_loss','power_loss','backup_missing_hidden','handoff_late_hidden','unestablished_backup','outside_backup_region','conservative_reserve')
ARMS=('NO_BACKUP_ABLATION','SUPERVISED_PROPOSED_BACKUP')


def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
def backup_model():return dict(dt='.02',mass='1',spring='4',damping='3',position_scale='1',velocity_scale='1',anchor='0',level='5',force_cap='4',disturbance='.01',safe_position=['-.5','.32'])
def premises():return dict(state_bounds_asserted=True,active_cap_asserted=True,backup_model_asserted=True,independent_handoff_asserted=True,power_independent_backup_asserted=True,no_impulse_handoff_asserted=True)
def plan():return [dict(id=case+'__'+arm,case=case,arm=arm,steps=400,monitor_ticks=5 if case=='conservative_reserve' else 3,
    actual_handoff_delay=40 if case=='handoff_late_hidden' else 3,initial_velocity='1.5' if case=='outside_backup_region' else '.5',
    initial_force='.8' if case=='primary_loss' else '0',backup=backup_model(),criteria_origin='SYNTHETIC_DEVELOPMENT_ONLY') for case in CASES for arm in ARMS]
def bounds(value,error=2e-8,cap=None):
    middle=round(float(value),8);lo=middle-error;hi=middle+error
    if cap is not None:lo=max(-cap,lo);hi=min(cap,hi)
    # Packet contract forbids exponent notation, including near-zero values.
    return [format(x,'.15f').rstrip('0').rstrip('.') if x else '0' for x in (lo,hi)]
def observation(p,v):return dict(position=bounds(p),velocity=bounds(v))
def unavailable(a):return a['case'] not in ('nominal','conservative_reserve')
def power(a):return a['case'] in ('nominal','conservative_reserve','primary_loss')


def primary_inputs(obs,force,queue,k):
    a=temporal.plan()[0];m=a['model'];m.update(position=obs['position'],velocity=obs['velocity'],disturbance='.01',measurement_error='.00000002')
    cfg=dict(model=m,session_id='boot-A',clock_id='clock-A',start_tick=max(0,k-4),limits=a['limits'],assumptions=a['assumptions'])
    cfg['limits']['max_transport_ticks']=8
    session=TemporalFeedbackSession(**cfg)
    rows=[temporal.packet('STATE',k,position=obs['position'],velocity=obs['velocity']),temporal.packet('FORCE',k,force=bounds(force,cap=1.)),
          temporal.packet('POWER',k,absolute_cut_ticks=[k+200,k+200])]
    # Pre-zero FIFO slots remain unknown, rather than inventing reset evidence.
    for i,target in enumerate(queue):
        t=k-3+i
        if t>=0:rows.append(temporal.packet('COMMAND_ENQUEUED',t,sequence=i,command_id='target-'+str(t),effective_target=bounds(target,cap=1.)))
    for row in rows:session.ingest(row,received_tick=k)
    result=session.assess_at(k,reaction_delay_ticks=0)
    clock=iter((1000,1001,1002));guard=DeadlineGuard(boot_id='runtime-boot',clock=lambda:next(clock));budget=guard.begin(10)
    pin=dict(store_id='synthetic-primary',header_sha256='a'*64,seq=1,head_sha256='b'*64)
    restarted=restart_check(actual_checkpoint=pin,expected_checkpoint=pin,actual_runtime=runtime_identity(),expected_runtime=runtime_identity(),
        boot_id='runtime-boot',boot_start_ns=1000,now_ns=1010,freshness_limit_ns=10,fresh_observations={key:dict(boot_id='runtime-boot',observed_ns=1005,received_ns=1006,evidence_asserted=True) for key in ('STATE','ACTUATOR','POWER','CLOCK_MAP')})
    profile,samples=previous.calibration_inputs('nominal_candidate')
    return dict(temporal=result,deadline=guard.evaluate(budget,lambda:result),restart=restarted,calibration=calibration_check(profile,samples))


def native_case(a,saved=None,emit=None):
    bm=a['backup'];s=model(bm);env=PowerBrakeEnvironment(brake_cap_per_axis_n=1.)
    env.reset_development(float(Q(a['initial_velocity'])))
    actuator=DelayedSlewBrake(delay_ticks=3,slew_n_s=4.,cap_n=1.,dt_seconds=.02)
    initial=float(Q(a['initial_force']));actuator.force=(initial,0.,0.);actuator.pending=deque([(initial,0.,0.)]*3)
    actuator.tick=100  # explicit synthetic prehistory epoch, not real executions
    pos=np.array([-2.,-2.,1.3]);vel=np.array([float(Q(a['initial_velocity'])),0.,0.])
    runtime=env.runtime_record();rows=[];requested=None;origin=None;ever_contradictory=False
    if runtime['dt']!=.02 or env.actual_mass!=1.:raise ValueError('unsupported native point fixture')
    if saved is not None and (saved['runtime']!=runtime or len(saved['frames'])!=a['steps']):raise ValueError('native runtime/frame count mismatch')
    for k in range(a['steps']):
        obs=observation(pos[0]+2.,vel[0]);supervision=None;primary=None
        if a['arm']=='SUPERVISED_PROPOSED_BACKUP' and requested is None and k%a['monitor_ticks']==0:
            if not unavailable(a):primary=primary_inputs(obs,actuator.force[0],[x[0] for x in actuator.pending],100+k)
            state=dict(boot_id='runtime-boot',epoch_tick=100+k,source_id='SYNTHETIC_SECOND_STATE_CHANNEL',evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS',**obs)
            flags=premises()
            if a['case']=='unestablished_backup':flags['backup_model_asserted']=False
            supervision=assess_supervisor(bm,state,assessment_tick=100+k,boot_id='runtime-boot',active_force_cap='1',environment_force='.01',
                handoff_delay_ticks=[0,3],monitor_ticks=a['monitor_ticks'],max_state_age_ticks=8,premises=flags,primary=primary)
            if supervision['development_action']=='HANDOFF_TO_PASSIVE_BACKUP':requested=k;origin='SUPERVISOR_CANDIDATE'
            elif unavailable(a) and a['case']!='unestablished_backup':
                # Proposed independent watchdog acts even when software cannot
                # establish a safe starting set. That is scored as unresolved.
                requested=k;origin='PROPOSED_INDEPENDENT_WATCHDOG_UNRESOLVED_STATE'
        actual_available=a['arm']=='SUPERVISED_PROPOSED_BACKUP' and a['case'] not in ('backup_missing_hidden','unestablished_backup')
        engaged=actual_available and requested is not None and k>=requested+a['actual_handoff_delay']
        expected_engaged=requested is not None and k>=requested+3
        # Primary-loss ablation makes a zero REQUEST; old force/FIFO persist.
        request=0. if unavailable(a) else -2.*round(float(vel[0]),8)
        active=actuator.step([request,0.,0.],tick=100+k,powered=power(a) and not engaged)
        # A physical sampled spring/damper force law, not a controller oracle.
        relative=float(pos[0])+2.;passive=float(max(-float(s['force_cap']),min(float(s['force_cap']),-float(s['spring'])*(relative-float(s['anchor']))-float(s['damping'])*float(vel[0])))) if engaged else 0.
        exogenous=.01
        if saved is not None:env.data.qpos[:]=pos;env.data.qvel[:]=vel
        pre=env.prepare_powered_force(active,brake_powered=power(a) and not engaged,gravity_powered=True,disturbance=[passive+exogenous,0.,0.])
        intent=dict(phase='NATIVE_INTENT',tick=k,position_before=pos.tolist(),velocity_before=vel.tolist(),state_observation=obs,
            supervision=supervision,primary_sha256=None if primary is None else sha(primary),request_n=request,
            active_force_n=active[0],proposed_backup_force_n=passive,backup_engaged_for_scoring=engaged,
            expected_backup_engaged=expected_engaged,plant=pre)
        if saved is None:
            if emit:emit(intent)
            physical=env.advance_prepared()
            if emit:emit(dict(phase='NATIVE_PHYSICS',tick=k,physical=physical))
        else:
            frame=saved['frames'][k]
            if frame['intent']!=intent:raise ValueError('native decision/force/measurement intent mismatch')
            physical=frame['physical'];vn=vel+.02*np.array([active[0]+passive+exogenous,0.,0.]);pn=pos+.02*vn
            if not np.allclose(physical['velocity'],vn,rtol=0,atol=1e-10) or not np.allclose(physical['position'],pn,rtol=0,atol=1e-10):raise ValueError('native sampled dynamics mismatch')
            env.data.qpos[:]=physical['position'];env.data.qvel[:]=physical['velocity'];mujoco.mj_forward(env.model,env.data);check=env.get_state()
            for key in ('contact_floor','contact_obstacle'):
                if physical[key]!=bool(check[key]):raise ValueError('native contact state mismatch')
            if physical['geometric_or_contact_violation']!=bool(check['safety_violation']):raise ValueError('native geometry-state mismatch')
            for key in ('boundary_clearance','min_obstacle_distance'):
                if abs(physical[key]-check[key])>1e-10:raise ValueError('native clearance mismatch')
        if physical['contact_floor'] or physical['contact_obstacle']:raise ValueError('contact invalidates this declared no-contact 1D corroboration')
        if physical['position']!=physical['integrated_qpos'] or abs(physical['time']-(k+1)*.02)>1e-10:raise ValueError('native sampled phase mismatch')
        after=observation(physical['position'][0]+2.,physical['velocity'][0])
        monitored=check_backup_step(bm,obs,after) if expected_engaged else dict(status='BACKUP_NOT_YET_EXPECTED',operational_authorization=False)
        ever_contradictory|=monitored['status']=='BACKUP_MODEL_OR_EVIDENCE_CONTRADICTION'
        record=dict(intent=intent,physical=physical,backup_observation=monitored,assumption_contradiction_latched=ever_contradictory)
        if saved is not None and record!=saved['frames'][k]:raise ValueError('native post-feedback mismatch')
        if saved is None and emit:emit(dict(phase='BACKUP_OBSERVATION',tick=k,result=monitored,contradiction_latched=ever_contradictory))
        rows.append(record);pos=np.array(physical['position']);vel=np.array(physical['velocity'])
    result=dict(runtime=runtime,frames=rows,handoff_request_tick=requested,handoff_origin=origin,classification='SAMPLED_PHYSICAL_BACKUP_ARCHITECTURE_ABLATION_NOT_REAL_ROBOT')
    if saved is not None and result!=saved:raise ValueError('native episode reconstruction mismatch')
    return result


def summary(a,r):
    values=[(f['physical']['position'][0]+2.,f['physical']['velocity'][0]) for f in r['frames']]
    decisions=[f['intent']['supervision'] for f in r['frames'] if f['intent']['supervision'] is not None]
    low,high=map(float,a['backup']['safe_position'])
    return dict(native_steps=len(values),sampled_position_violation=any(not low<=p<=high for p,v in values),
        maximum_position_m=max(p for p,v in values),final_position_m=values[-1][0],final_velocity_m_s=values[-1][1],
        handoff_request_tick=r['handoff_request_tick'],actual_first_backup_tick=next((i for i,f in enumerate(r['frames']) if f['intent']['backup_engaged_for_scoring']),None),
        first_model_contradiction_tick=next((i for i,f in enumerate(r['frames']) if f['assumption_contradiction_latched']),None),
        conditional_plan_count=sum(d['status']=='CONDITIONAL_DEVELOPMENT_PLAN' for d in decisions),
        unresolved_plan_count=sum(d['development_action'] is None for d in decisions),
        observed_backup_model_supported=not any(f['assumption_contradiction_latched'] for f in r['frames']) and r['handoff_request_tick'] is not None,
        architecture_differs_between_arms=True,independent_hardware_validated=False,operational_authorization=False)


def run(directory):
    directory=Path(directory);directory.mkdir(exist_ok=False);sources=hashes()
    metadata=dict(source_sha256=sources,python=platform.python_version(),numpy=np.__version__,mujoco=mujoco.__version__,
        parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),gate_b='GATE_B_NOT_AUTHORIZED')
    assignments=[dict(a,metadata=metadata) for a in plan()]
    with DevelopmentLedger.create(directory/'assignments.jsonl',study=STUDY,assignments=assignments,record_events=True) as log:
        for a in assignments:
            log.start(a['id'])
            try:
                result=native_case(a,emit=lambda e:log.event(a['id'],details=e));data=canonical(result)
                with (directory/(a['id']+'.json.gz')).open('xb') as f:
                    with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as z:z.write(data)
                    f.flush();os.fsync(f.fileno())
                if sources!=hashes():raise ValueError('study sources changed')
                log.complete(a['id'],status='COMPLETED',details=dict(raw_sha256=hashlib.sha256(data).hexdigest(),compressed_sha256=hashlib.sha256((directory/(a['id']+'.json.gz')).read_bytes()).hexdigest(),sources_after=sources,summary=summary(a,result)))
            except (LedgerError,LedgerWriteError):raise
            except Exception as exc:log.complete(a['id'],status='ERROR',details=dict(error_type=type(exc).__name__,error=str(exc)));raise
        log.finalize()
    return dict(counts=inspect(directory/'assignments.jsonl')['counts'],gate_b='GATE_B_NOT_AUTHORIZED')


def audit(directory):
    directory=Path(directory);log=inspect(directory/'assignments.jsonl');header=log['records'][0];assignments=header['assignments'];meta=assignments[0]['metadata']
    if header['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan():raise ValueError('study plan mismatch')
    if any(a['metadata']!=meta for a in assignments) or meta['source_sha256']!=hashes() or (meta['python'],meta['numpy'],meta['mujoco'])!=(platform.python_version(),np.__version__,mujoco.__version__):raise ValueError('source/runtime mismatch')
    rows={};active=None;events=[]
    for record in log['records']:
        if record['kind']=='START':active=record['id'];events=[]
        elif record['kind']=='EVENT':
            if record['id']!=active:raise ValueError('native event order mismatch')
            events.append(record['details'])
        elif record['kind']=='TERMINAL':
            if record['id']!=active:raise ValueError('native terminal order mismatch')
            if record['status']=='COMPLETED':
                name=record['id'];a=next(x for x in assignments if x['id']==name);p=directory/(name+'.json.gz');data=gzip.decompress(p.read_bytes());saved=json.loads(data);details=record['details']
                if hashlib.sha256(data).hexdigest()!=details['raw_sha256'] or hashlib.sha256(p.read_bytes()).hexdigest()!=details['compressed_sha256'] or details['sources_after']!=meta['source_sha256']:raise ValueError('source/raw artifact mismatch')
                rebuilt=native_case(a,saved=saved)
                expected=[]
                for k,f in enumerate(rebuilt['frames']):expected.extend([f['intent'],dict(phase='NATIVE_PHYSICS',tick=k,physical=f['physical']),dict(phase='BACKUP_OBSERVATION',tick=k,result=f['backup_observation'],contradiction_latched=f['assumption_contradiction_latched'])])
                if expected!=events or hashlib.sha256(canonical(rebuilt)).hexdigest()!=details['raw_sha256'] or summary(a,rebuilt)!=details['summary']:raise ValueError('durable native/summary reconstruction mismatch')
                rows[name]=summary(a,rebuilt)
            active=None
    return dict(study=STUDY,ledger_state=log['state'],counts=log['counts'],metadata=meta,
        assignments=[dict(id=a['id'],state=log['assignments'][a['id']],summary=rows.get(a['id'])) for a in assignments],
        classification='DEPENDENT_ARCHITECTURE_ABLATION_NOT_ALGORITHM_ONLY_COMPARISON',gate_b='GATE_B_NOT_AUTHORIZED')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    result=run(a.directory) if a.mode=='run' else audit(a.directory)
    with a.output.open('xb') as f:f.write(canonical(result));f.write(b'\n')
    print(json.dumps(dict(counts=result['counts'],gate_b=result['gate_b'])))


if __name__=='__main__':main()
