"""Predeclared synthetic evidence-gating and first-stop capability development.

Finite synthetic witnesses are test inputs, not independent sensor observations.
The stopping grid is a separate force model, not a new RP01 controller arm.
"""
from pathlib import Path
from copy import deepcopy
import argparse,hashlib,json
from aegis.development import physical_time_recovery as physical
from aegis.development import evidence_recovery as adapter
from aegis.development.recovery_evidence import EvidenceJournal,EvidenceReplay,PREMISE_NAMES,inspect as inspect_evidence
from aegis.development.durable_feedback_session import canonical,sha
from aegis.development.stopping_capability_1d import analyze as stopping
from scripts.research.fair_physical_execution_study import clock_map
from scripts.research.recovery_supervisor_study_1d import backup_model
from scripts.research.backup_parameter_uncertainty_study import family
from scripts.research.development_ledger import DevelopmentLedger,inspect

ROOT=Path(__file__).resolve().parents[2]
FILES=('src/aegis/development/recovery_evidence.py','src/aegis/development/evidence_recovery.py','src/aegis/development/stopping_capability_1d.py','scripts/research/evidence_recovery_study.py','tests/test_recovery_evidence.py','tests/test_evidence_recovery.py','tests/test_stopping_capability_1d.py','tests/test_evidence_recovery_study.py','docs/research/ADR_EA01_EVIDENCE_AWARE_RECOVERY_2026-11-17.md')
MODES=('MISSING','ASSERTED','UNKNOWN','EXPIRED','CONTRADICTED','WRONG_BINDING','WRONG_SOURCE','WRONG_BOOT','WRONG_DOMAIN','MALFORMED','ID_CONFLICT')


def hashes():
    from scripts.research.restart_failure_study import FILES as prior
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(prior+FILES))}


def inputs():
    return dict(backup=backup_model(),parameter_bounds=family('.1'),packet=dict(remote_time=1100,local_epoch='local-A',remote_epoch='sensor-A',frame='WORLD_X_SI',position=['0','0'],velocity=['.3','.3'],source_id='SYNTHETIC_FIXTURE'),clock_map=clock_map(),now_local=100,units_per_second='1000',max_state_age_seconds='.06',local_epoch='local-A',boot_id='boot-A',active_force_cap='1',handoff_delay_seconds=['0','.08'],monitor_seconds='.06',primary_healthy=True,dynamics_id=physical.DYNAMICS_ID)


def policy():return adapter.policy(source_ids={k:'SYNTHETIC_'+k for k in PREMISE_NAMES},max_age_ticks=4)


def witnesses(a):
    return [['0','.3'],['1','4','3'],['100'],['1'],dict(backup=deepcopy(a['backup']),dynamics_id=a['dynamics_id']),['.06'],dict(controller='pid-11',watchdog='pid-12',plant='pid-13'),dict(primary_power='sim-primary',backup_power='sim-backup'),['0','0']]


def artifacts(a=None,*,expires=105):
    a=inputs() if a is None else a;s=adapter.statement_for(a);p=policy()
    return [dict(id='fixture-'+str(n),premise=k,source_id=p[k]['source_id'],scope='DEVELOPMENT_SIMULATION',statement_sha256=sha(s),boot_id=a['boot_id'],clock_domain=a['local_epoch'],observed_tick=100,expires_tick=expires,kind='OBSERVATION',observations=v) for n,(k,v) in enumerate(zip(PREMISE_NAMES,witnesses(a)))]


def contradiction(row):
    row=deepcopy(row);key=row['premise']
    if key=='backup_model_asserted':row['observations']['dynamics_id']='WRONG_MODEL'
    elif key=='independent_handoff_asserted':row['observations']['plant']=row['observations']['controller']
    elif key=='power_independent_backup_asserted':row['observations']['backup_power']=row['observations']['primary_power']
    else:row['observations'][0]='999'
    return row


def evidence_plan():
    return [dict(id='evidence_nominal',kind='EVIDENCE',mode='NOMINAL',premise=None)]+[dict(id=f'evidence_{n}_{mode}',kind='EVIDENCE',mode=mode,premise=k) for n,k in enumerate(PREMISE_NAMES) for mode in MODES]


def stopping_plan():
    return [dict(id=f'stop_v{v}_f{force}_d{delay}_r{ramp}',kind='STOPPING',velocity=v,brake_force=force,delay=delay,ramp=ramp) for v in ('.3','.8') for force in ('0','.01','1','4') for delay in ('0','.08','.3') for ramp in ('1','4')]


def plan():return evidence_plan()+stopping_plan()


def save(path,value):
    with path.open('xb') as f:f.write(canonical(value)+b'\n')


def evidence_case(a,d):
    values=artifacts();target=next((x for x in values if x['premise']==a['premise']),None)
    if target is not None:
        mode=a['mode']
        if mode=='MISSING':values.remove(target)
        elif mode in ('ASSERTED','UNKNOWN'):target.update(kind=mode,observations=None)
        elif mode=='EXPIRED':target.update(observed_tick=90,expires_tick=100)
        elif mode=='CONTRADICTED':values[values.index(target)]=contradiction(target)
        elif mode=='WRONG_BINDING':target['statement_sha256']='0'*64
        elif mode=='WRONG_SOURCE':target['source_id']='UNREGISTERED_SOURCE'
        elif mode=='WRONG_BOOT':target['boot_id']='old-boot'
        elif mode=='WRONG_DOMAIN':target['clock_domain']='old-clock'
        elif mode=='MALFORMED':target['observations']={'malformed':'not a predicate witness'}
    save(d/'submitted_artifacts.json',values)
    with EvidenceJournal.create(d/'evidence',policy=policy(),boot_id='boot-A',clock_domain='local-A',now=100) as j:
        for row in values:j.submit(row,now=100)
        if a['mode']=='ID_CONFLICT':j.submit(dict(target,expires_tick=106),now=100)
        result=adapter.assess(j,inputs(),finish_clock=lambda:100)
    return dict(assignment=a,result=result,checkpoint=inspect_evidence(d/'evidence')['checkpoint'],physical_trajectory='NOT_EXECUTED_EVIDENCE_PREDICATE_FIXTURE',uncertain_effects='NO_ACTUATOR_EFFECT_REQUESTED',duplicate_effects='NO_ACTUATOR_EFFECT_REQUESTED',latency='FIXED_VIRTUAL_ASSESSMENT_TICK_NOT_A_RUNTIME_MEASUREMENT',nominal_control_availability='OFFLINE_CANDIDATE_ONLY',gate_b='GATE_B_NOT_AUTHORIZED')


def stopping_case(a):
    values=dict(position=['0','0'],velocity=[a['velocity'],a['velocity']],mass=['.9','1.1'],adverse_force_max='.01',brake_force_min=a['brake_force'],delay_seconds=a['delay'],ramp_rate_min=a['ramp'],sample_seconds='.02',horizon_seconds='5',safe_position=['-.5','.32'])
    return dict(assignment=a,inputs=values,result=stopping(**values),gate_b='GATE_B_NOT_AUTHORIZED')


def run(root):
    root.mkdir(exist_ok=False);sources=hashes();declaration=dict(assignments=plan(),source_sha256=sources,classification='SYNTHETIC_FIXTURES_AND_SEPARATE_FIRST_STOP_CAPABILITY',aggregate_pass_fail=None,gate_b='GATE_B_NOT_AUTHORIZED');save(root/'declared_plan.json',declaration)
    results=[]
    with DevelopmentLedger.create(root/'assignments.jsonl',study='EA01 evidence and capability development',assignments=plan()) as ledger:
        for a in plan():
            ledger.start(a['id']);d=root/a['id'];d.mkdir(exist_ok=False)
            try:
                r=evidence_case(a,d) if a['kind']=='EVIDENCE' else stopping_case(a);save(d/'result.json',r)
                if sources!=hashes():raise ValueError('source changed during study')
                ledger.complete(a['id'],status='COMPLETED',details=dict(result_sha256=sha(r)));results.append(r)
            except Exception as exc:
                error=dict(error_type=type(exc).__name__,error=str(exc));save(d/'error.json',error);ledger.complete(a['id'],status='ERROR',details=error)
        ledger.finalize()
    return dict(source_sha256=sources,results=results,gate_b='GATE_B_NOT_AUTHORIZED',aggregate_pass_fail=None)


def audit(root):
    declaration=json.loads((root/'declared_plan.json').read_bytes());ledger=inspect(root/'assignments.jsonl');sources=hashes()
    if declaration['assignments']!=plan() or declaration['source_sha256']!=sources or ledger['records'][0]['assignments']!=plan() or ledger['records'][0]['study']!='EA01 evidence and capability development':raise ValueError('plan/source/ledger identity mismatch')
    results=[];incomplete=[];terminals={x['id']:x for x in ledger['records'] if x['kind']=='TERMINAL'}
    if {p.name for p in root.iterdir() if p.is_dir()}!={a['id'] for a in plan()}:raise ValueError('case inventory mismatch')
    for a in plan():
        d=root/a['id'];t=terminals.get(a['id'])
        if t is None or t['status']!='COMPLETED':incomplete.append(dict(assignment=a,terminal=t));continue
        r=json.loads((d/'result.json').read_bytes())
        if r['assignment']!=a or t['details']['result_sha256']!=sha(r):raise ValueError('result identity mismatch')
        if a['kind']=='STOPPING':
            if stopping_case(a)!=r:raise ValueError('stopping reconstruction mismatch')
        else:
            j=inspect_evidence(d/'evidence');last=j['records'][-1]['payload']
            if j['checkpoint']!=r['checkpoint'] or last['kind']!='EVALUATE':raise ValueError('evidence terminal mismatch')
            if j['header']['policy']!=policy() or j['header']['boot_id']!='boot-A' or j['header']['clock_domain']!='local-A':raise ValueError('evidence policy/header mismatch')
            submitted=json.loads((d/'submitted_artifacts.json').read_bytes());events=[x['payload'] for x in j['records'][1:] if x['payload']['kind']!='EVALUATE']
            expected=list(submitted)
            if a['mode']=='ID_CONFLICT':expected.append(dict(next(x for x in submitted if x['premise']==a['premise']),expires_tick=106))
            if len(events)!=len(expected):raise ValueError('artifact event inventory mismatch')
            for event,row in zip(events,expected):
                if event['kind']=='ARTIFACT' and event['artifact']!=row:raise ValueError('submitted artifact mismatch')
                if event['kind']=='REJECT' and event['artifact_sha256']!=sha(row):raise ValueError('rejected artifact identity mismatch')
                if event['kind'] not in ('ARTIFACT','REJECT'):raise ValueError('unexpected artifact event')
            replay=EvidenceReplay(d/'evidence');rebuilt=adapter.assess(replay,inputs(),finish_clock=lambda:100)
            if rebuilt!=r['result'] or replay.index!=len(replay.records):raise ValueError('full evidence/physical decision reconstruction mismatch')
        results.append(r)
    return dict(source_sha256=sources,results=results,incomplete=incomplete,ledger_counts=ledger['counts'],gate_b='GATE_B_NOT_AUTHORIZED',aggregate_pass_fail=None)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('run','audit'));p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    save(args.output,run(args.root) if args.mode=='run' else audit(args.root))
