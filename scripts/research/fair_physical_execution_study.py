"""Matched ideal ZOH development comparison and durable synthetic marker study.

All arms share dynamics, backup, actuator delay/slew, evidence and fault schedule.
Engineering policies, NOT reproduced published baselines or confirmatory trials.
"""
from pathlib import Path
import argparse,gzip,hashlib,json,os,platform,subprocess
from fractions import Fraction as Q
from copy import deepcopy
from aegis.development import physical_time_recovery as physical
from aegis.development.durable_simulation_executor import DurableSimulationExecutor
from aegis.development.durable_feedback_session import canonical,sha
from aegis.development.independent_clock_mapping import IndependentClockMap
from aegis.development.dynamic_braking import DelayedSlewBrake
from scripts.research import family_recovery_composition_study as prior
from scripts.research import recovery_supervisor_study_1d as old
from scripts.research.backup_parameter_uncertainty_study import family
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError,inspect

ROOT=Path(__file__).resolve().parents[2]
STUDY='V9-M5 matched ideal physical-time policies with synthetic durable effects v1'
FILES=prior.FILES+('src/aegis/development/durable_simulation_executor.py','src/aegis/development/physical_time_recovery.py',
 'scripts/research/fair_physical_execution_study.py','tests/test_durable_simulation_executor.py','tests/test_physical_time_recovery.py','tests/test_fair_physical_execution_study.py')
ARMS=('ALWAYS_BACKUP','FIXED_POSITION_TRIGGER','PHYSICAL_RESERVE','PHYSICAL_RESERVE_DEGRADED')
FAULTS=('nominal','primary_power_loss','backup_absent','late_handoff')


def hashes():return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FILES}
def common_contract():return dict(dt='.02',spring='4',damping='3',backup_cap='4',primary_cap='1',delay_ticks=3,slew_n_s='4',disturbance='.01',safe_position=['-.5','.32'])

def plan():
    return [dict(id=f'm{m}_v{v}_{f}_{arm}',mass=m,initial_velocity=v,fault=f,arm=arm,steps=200,
                 common_contract=common_contract())
            for m in ('.9','1.1') for v in ('.3','.8') for f in FAULTS for arm in ARMS]

def clock_map():
    c=IndependentClockMap(local_epoch='local-A',remote_epoch='sensor-A',rate_bounds=['1','1'],max_extrapolation=100000)
    c.add(dict(id='exchange',local_epoch='local-A',remote_epoch='sensor-A',local_send=98,remote_receive=1100,remote_send=1100,local_receive=100))
    return c

def baseline_plan(arm):return dict(status='DEVELOPMENT_BASELINE_ACTION',policy=arm,dispatch=False,operational_authorization=False,hardware_validation=False,gate_b='GATE_B_NOT_AUTHORIZED')


def case(a,*,executor=None,emit=None,saved=None):
    if a['common_contract']!=common_contract():raise ValueError('unsupported/mismatched physical contract')
    c=clock_map();backup=old.backup_model();bounds=family('.1');pos=Q(0);vel=Q(a['initial_velocity']);m=Q(a['mass']);h=Q('.02')
    actuator=DelayedSlewBrake(delay_ticks=3,slew_n_s=4.,cap_n=1.,dt_seconds=.02);rows=[];request_tick=None;effect=None
    if saved is not None and len(saved['frames'])!=a['steps']:raise ValueError('frame count')
    for tick in range(a['steps']):
        now_ms=100+20*tick;obs=old.observation(float(pos),float(vel));packet=dict(remote_time=now_ms+1000,local_epoch='local-A',remote_epoch='sensor-A',frame='WORLD_X_SI',source_id='SYNTHETIC_SENSOR',**obs)
        primary_power=a['fault']!='primary_power_loss'
        result=physical.assess(backup,bounds,packet,c,now_local=now_ms,units_per_second='1000',max_state_age_seconds='.05',local_epoch='local-A',boot_id='boot-A',
            active_force_cap='1',handoff_delay_seconds=['0','.06'],monitor_seconds='.06',premises={k:True for k in physical.PREMISES.split()},primary_healthy=primary_power,dynamics_id=physical.DYNAMICS_ID)
        trigger=False
        if request_tick is None:
            if a['arm']=='ALWAYS_BACKUP':trigger=True
            elif a['arm']=='FIXED_POSITION_TRIGGER':trigger=(Q(obs['position'][1])>=Q('.1') or not primary_power)
            elif a['arm']=='PHYSICAL_RESERVE':trigger=result['development_action']=='HANDOFF'
            else:trigger=result['development_action']=='HANDOFF' or result['status']!='CONDITIONAL_PHYSICAL_TIME_PLAN'
            # Identical watchdog loss-of-primary rule for every arm. It is a
            # physical hypothesis, not a supported plan when reserve is unknown.
            if not primary_power:trigger=True
            if trigger:
                request_tick=tick;recorded_plan=result if a['arm'] in ('PHYSICAL_RESERVE','PHYSICAL_RESERVE_DEGRADED') and result['status']=='CONDITIONAL_PHYSICAL_TIME_PLAN' else baseline_plan(a['arm'])
                if executor is not None:
                    executor._clock.value=now_ms*1000000
                    executor.record('handoff',recorded_plan,expires_ns=(now_ms+100)*1000000)
                    claim=executor.claim('handoff');effect=executor.simulate_effect('handoff',token=claim['token'])
        actual_delay=15 if a['fault']=='late_handoff' else 3
        engaged=request_tick is not None and tick>=request_tick+actual_delay and a['fault']!='backup_absent'
        active=actuator.step([-2.*float(Q(obs['velocity'][0])+Q(obs['velocity'][1]))/2.,0.,0.],tick=tick,powered=primary_power and not engaged)[0]
        backup_force=max(Q(-4),min(Q(4),-4*pos-3*vel)) if engaged else Q(0)
        # Float actuator outputs are encoded explicitly before exact scalar integration.
        force=Q(str(active))+backup_force+Q('.01');acc=force/m
        candidates=[Q(0),h]
        if acc:
            t=-vel/acc
            if 0<t<h:candidates.append(t)
        extrema=[pos+t*vel+t*t*acc/2 for t in candidates];vn=vel+h*acc;pn=pos+h*vel+h*h*acc/2
        record=dict(tick=tick,packet=packet,assessment=result,request_tick=request_tick,backup_engaged=engaged,
                    primary_power=primary_power,active_force=str(Q(str(active))),backup_force=str(backup_force),
                    request_supported=(request_tick is not None and rows[request_tick]['assessment']['status']=='CONDITIONAL_PHYSICAL_TIME_PLAN') if request_tick is not None and request_tick<len(rows) else (result['status']=='CONDITIONAL_PHYSICAL_TIME_PLAN' if request_tick==tick else None),
                    position_before=str(pos),velocity_before=str(vel),position_after=str(pn),velocity_after=str(vn),
                    continuous_position=[str(min(extrema)),str(max(extrema))],premise_fault=a['fault'] in ('backup_absent','late_handoff'))
        if saved is not None and record!=saved['frames'][tick]:raise ValueError('saved dynamics/policy/clock/force mismatch')
        if emit:emit(dict(phase='IDEAL_ZOH_RESULT',record=record))
        rows.append(record);pos,vel=pn,vn
        # Restrict exact denominator growth while enclosing simulation arithmetic:
        # no rounding state is performed; this is an ideal rational plant.
    low,high=Q('-.5'),Q('.32');violation=any(Q(f['continuous_position'][0])<low or Q(f['continuous_position'][1])>high for f in rows)
    result=dict(frames=rows,summary=dict(continuous_position_violation=violation,peak_position=str(max(Q(f['continuous_position'][1]) for f in rows)),
        final_position=str(pos),final_velocity=str(vel),request_tick=request_tick,
        primary_active_ticks=sum(f['primary_power'] and not f['backup_engaged'] for f in rows),
        premise_fault_injected=a['fault'] in ('backup_absent','late_handoff'),
        initial_state_supported=(rows[0]['assessment']['status']=='CONDITIONAL_PHYSICAL_TIME_PLAN'),
        unsupported_assessment_ticks=sum(f['assessment']['status']!='CONDITIONAL_PHYSICAL_TIME_PLAN' for f in rows),
        physical_hardware_validated=False,operational_authorization=False))
    if saved is not None and result!=saved:raise ValueError('summary mismatch')
    return result


class Clock:
    def __init__(self,value=100000000):self.value=value
    def __call__(self):return self.value


def run(directory):
    d=Path(directory);d.mkdir(exist_ok=False);pins=hashes();metadata=dict(source_sha256=pins,python=platform.python_version(),parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),gate_b='GATE_B_NOT_AUTHORIZED')
    assignments=[dict(a,metadata=metadata) for a in plan()]
    with DevelopmentLedger.create(d/'assignments.jsonl',study=STUDY,assignments=assignments,record_events=True) as log:
        for a in assignments:
            log.start(a['id']);executor=None
            try:
                executor=DurableSimulationExecutor.create(d/(a['id']+'_executor'),store_id=a['id'],boot_id='boot-A',clock=Clock())
                r=case(a,executor=executor,emit=lambda e:log.event(a['id'],details=e));pin=executor.checkpoint;executor.close();executor=None
                raw=canonical(r)
                with (d/(a['id']+'.json.gz')).open('xb') as f:
                    with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as z:z.write(raw)
                    f.flush();os.fsync(f.fileno())
                files={str(p.relative_to(d/(a['id']+'_executor'))):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((d/(a['id']+'_executor')).rglob('*')) if p.is_file()}
                if hashes()!=pins:raise ValueError('source changed')
                log.complete(a['id'],status='COMPLETED',details=dict(raw_sha256=hashlib.sha256(raw).hexdigest(),checkpoint=pin,executor_files=files,summary=r['summary'],sources_after=pins))
            except (LedgerError,LedgerWriteError):raise
            except Exception as e:
                log.complete(a['id'],status='ERROR',details=dict(error_type=type(e).__name__,error=str(e)));raise
            finally:
                if executor is not None:executor.close()
        log.finalize()
    return audit(d)


def audit(directory):
    d=Path(directory);ledger=inspect(d/'assignments.jsonl');header=ledger['records'][0];assignments=header['assignments'];meta=assignments[0]['metadata']
    if header['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan():raise ValueError('matched plan mismatch')
    if any(a['metadata']!=meta for a in assignments) or meta['source_sha256']!=hashes() or meta['python']!=platform.python_version() or meta['gate_b']!='GATE_B_NOT_AUTHORIZED':raise ValueError('source/runtime/governance mismatch')
    results={};events=[]
    for row in ledger['records']:
        if row['kind']=='START':events=[]
        elif row['kind']=='EVENT':events.append(row['details'])
        elif row['kind']=='TERMINAL' and row['status']=='COMPLETED':
            a=next(x for x in assignments if x['id']==row['id']);data=gzip.decompress((d/(a['id']+'.json.gz')).read_bytes());r=json.loads(data);details=row['details']
            if hashlib.sha256(data).hexdigest()!=details['raw_sha256'] or details['sources_after']!=meta['source_sha256']:raise ValueError('raw/source digest mismatch')
            rebuilt=case(a,saved=r)
            if events!=[dict(phase='IDEAL_ZOH_RESULT',record=f) for f in rebuilt['frames']] or details['summary']!=rebuilt['summary']:raise ValueError('event/summary mismatch')
            base=d/(a['id']+'_executor');files={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob('*')) if p.is_file()}
            if files!=details['executor_files']:raise ValueError('closed executor evidence changed')
            journal=DurableSimulationExecutor.audit_closed(base,expected_checkpoint=details['checkpoint'])
            request=rebuilt['summary']['request_tick']
            if request is None:
                if journal['state']['commands']:raise ValueError('unexpected durable effect')
            else:
                f=rebuilt['frames'][request];rplan=f['assessment'] if a['arm'] in ('PHYSICAL_RESERVE','PHYSICAL_RESERVE_DEGRADED') and f['assessment']['status']=='CONDITIONAL_PHYSICAL_TIME_PLAN' else baseline_plan(a['arm'])
                row=journal['state']['commands'].get('handoff')
                if row is None or row['status']!='SYNTHETIC_EFFECT_OBSERVED' or row['plan_sha256']!=sha(rplan):raise ValueError('durable policy/effect binding mismatch')
            results[a['id']]=rebuilt['summary']
    return dict(study=STUDY,metadata=meta,counts=ledger['counts'],ledger_state=ledger['state'],
                assignments=[dict(id=a['id'],state=ledger['assignments'][a['id']],summary=results.get(a['id'])) for a in assignments],
                classification='MATCHED_ENGINEERING_POLICIES_NOT_PUBLISHED_BASELINE_REPLICATION',native_physics_steps=0,gate_b='GATE_B_NOT_AUTHORIZED',operational_authorization=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    r=run(a.directory) if a.mode=='run' else audit(a.directory)
    with a.output.open('xb') as f:f.write(canonical(r)+b'\n')
    print(json.dumps(dict(counts=r['counts'],gate_b=r['gate_b'])))


if __name__=='__main__':main()
