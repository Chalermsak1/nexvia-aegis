"""Fixed synthetic study of family reserve, discrete time uncertainty and model mismatch."""
import argparse
from copy import deepcopy
import hashlib,json,os,platform,re,subprocess
from pathlib import Path
from aegis.development import family_backup_supervisor_1d as core
from aegis.development.held_force_motion_1d import segment, DYNAMICS_ID as ZOH
from aegis.development.durable_feedback_session import canonical,sha
from scripts.research import backup_parameter_uncertainty_study as prior
from scripts.research import recovery_supervisor_study_1d as old
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError,inspect

ROOT=Path(__file__).resolve().parents[2]
STUDY='V9-M5 family recovery composition and held-force diagnostic development v1'
FILES=prior.FILES+('src/aegis/development/family_backup_supervisor_1d.py','src/aegis/development/held_force_motion_1d.py',
    'scripts/research/family_recovery_composition_study.py','tests/test_family_backup_supervisor_1d.py',
    'tests/test_held_force_motion_1d.py','tests/test_family_recovery_composition_study.py')


def hashes():return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FILES}
def inputs():
    return dict(backup=old.backup_model(),parameter_bounds=prior.family('.15'),
        state=dict(boot_id='runtime-boot',clock_id='clock-A',frame='WORLD_X_SI',epoch_tick_bounds=[100,100],
                   position=['0','0'],velocity=['.5','.5'],source_id='SYNTHETIC_BACKUP_CHANNEL',evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS'),
        assessment_tick=100,boot_id='runtime-boot',clock_id='clock-A',active_force_cap='1',environment_force='.01',
        handoff_delay_ticks=[0,3],monitor_ticks=3,max_state_age_ticks=8,
        premises={k:True for k in core.PREMISES.split()},primary=None,dynamics_id=core.DYNAMICS_ID)


def primary_inputs(obs,force,queue,k,mass_bounds):
    a=old.temporal.plan()[0];m=a['model']
    m.update(position=obs['position'],velocity=obs['velocity'],mass=mass_bounds,disturbance='.01',measurement_error='.00000002')
    cfg=dict(model=m,session_id='boot-A',clock_id='clock-A',start_tick=max(0,k-4),limits=a['limits'],assumptions=a['assumptions'])
    cfg['limits']['max_transport_ticks']=8;session=old.TemporalFeedbackSession(**cfg)
    rows=[old.temporal.packet('STATE',k,position=obs['position'],velocity=obs['velocity']),old.temporal.packet('FORCE',k,force=old.bounds(force,cap=1.)),old.temporal.packet('POWER',k,absolute_cut_ticks=[k+200,k+200])]
    for i,target in enumerate(queue):
        t=k-3+i
        if t>=0:rows.append(old.temporal.packet('COMMAND_ENQUEUED',t,sequence=i,command_id='target-'+str(t),effective_target=old.bounds(target,cap=1.)))
    for row in rows:session.ingest(row,received_tick=k)
    result=session.assess_at(k,reaction_delay_ticks=0)
    clock=iter((1000,1001,1002));guard=old.DeadlineGuard(boot_id='runtime-boot',clock=lambda:next(clock));budget=guard.begin(10)
    pin=dict(store_id='synthetic-primary',header_sha256='a'*64,seq=1,head_sha256='b'*64)
    restarted=old.restart_check(actual_checkpoint=pin,expected_checkpoint=pin,actual_runtime=old.runtime_identity(),expected_runtime=old.runtime_identity(),boot_id='runtime-boot',boot_start_ns=1000,now_ns=1010,freshness_limit_ns=10,fresh_observations={key:dict(boot_id='runtime-boot',observed_ns=1005,received_ns=1006,evidence_asserted=True) for key in ('STATE','ACTUATOR','POWER','CLOCK_MAP')})
    profile,samples=old.previous.calibration_inputs('nominal_candidate')
    return dict(temporal=result,deadline=guard.evaluate(budget,lambda:result),restart=restarted,calibration=old.calibration_check(profile,samples))


def plan():
    names=('family_unknown_primary','family_primary','family_primary_long_monitor','family_deadline_withheld','singleton_primary','insufficient_primary_mass','uncertain_epoch','stale_epoch','future_epoch',
        'clock_reset','boot_reset','wrong_frame','unsupported_model','family_not_certified','parameter_premise_missing',
        'clock_premise_missing','no_independent_trigger','unknown_state','outside_region','long_handoff','long_monitor',
        'nonzero_state_age','uncertain_epoch_outside_budget','contradictory_primary','wide_state','zero_environment',
        'held_force_interior_escape','held_force_safe','held_force_model_mismatch','held_force_discretization_defect')
    return [dict(id=n) for n in names]


def run_case(a):
    name=a['id']
    if name.startswith('held_force_'):
        args=dict(position=['0','0'],velocity=['2','2'],force=['-4','-4'],mass=['1','1'],dt='1',disturbance='0',safe_position=['-.1','.4'],dynamics_id=ZOH)
        if name=='held_force_safe':args.update(velocity=['.1','.1'],force=['0','0'])
        if name=='held_force_model_mismatch':args['dynamics_id']=core.DYNAMICS_ID
        if name=='held_force_discretization_defect':args.update(velocity=['0','0'],force=['1','1'],dt='.02',safe_position=['-1','1'])
        return dict(kind='SEPARATE_PHYSICAL_SEGMENT_DIAGNOSTIC',inputs=args,result=segment(**args))
    args=inputs()
    if name in ('singleton_primary','insufficient_primary_mass','contradictory_primary'):
        if name!='insufficient_primary_mass':args['parameter_bounds']=prior.family('0')
        args['primary']=old.primary_inputs(dict(position=['0','0'],velocity=['.5','.5']),0.,[0.,0.,0.],100)
    if name in ('family_primary','family_primary_long_monitor','family_deadline_withheld'):
        args['state']['velocity']=['.3','.3']
        args['primary']=primary_inputs(dict(position=['0','0'],velocity=['.3','.3']),0.,[0.,0.,0.],100,args['parameter_bounds']['mass'])
        if name=='family_primary_long_monitor':args['monitor_ticks']=16
        if name=='family_deadline_withheld':args['primary']['deadline']['status']='RESULT_WITHHELD'
    if name=='contradictory_primary':args['state']['position']=['.01','.01']
    if name=='uncertain_epoch':args['state']['epoch_tick_bounds']=[99,100]
    if name=='stale_epoch':args['state']['epoch_tick_bounds']=[90,91]
    if name=='future_epoch':args['state']['epoch_tick_bounds']=[100,101]
    if name=='clock_reset':args['state']['clock_id']='clock-B'
    if name=='boot_reset':args['state']['boot_id']='old-boot'
    if name=='wrong_frame':args['state']['frame']='BODY_X'
    if name=='unsupported_model':args['dynamics_id']=ZOH
    if name=='family_not_certified':args['parameter_bounds']=prior.family('.2')
    if name=='parameter_premise_missing':args['premises']['parameter_bounds_asserted']=False
    if name=='clock_premise_missing':args['premises']['clock_grid_asserted']=False
    if name=='no_independent_trigger':args['premises']['independent_handoff_asserted']=False
    if name=='unknown_state':args['state']['evidence_status']='UNKNOWN'
    if name=='outside_region':args['state']['velocity']=['1.5','1.5']
    if name=='long_handoff':args['handoff_delay_ticks']=[0,12]
    if name=='long_monitor':args['monitor_ticks']=10
    if name=='nonzero_state_age':args['state']['epoch_tick_bounds']=[99,99]
    if name=='uncertain_epoch_outside_budget':args['state']['epoch_tick_bounds']=[91,100]
    if name=='wide_state':args['state'].update(position=['-.1','.1'],velocity=['.3','.7'])
    if name=='zero_environment':args['backup']['disturbance']='0';args['environment_force']='0'
    return dict(kind='SAMPLED_FAMILY_SUPERVISOR',inputs=args,result=core.assess(**args))


def run(directory):
    directory=Path(directory);directory.mkdir(exist_ok=False);pins=hashes()
    metadata=dict(source_sha256=pins,python=platform.python_version(),parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),gate_b='GATE_B_NOT_AUTHORIZED',study_native_steps=0)
    assignments=[dict(a,metadata=metadata) for a in plan()]
    with DevelopmentLedger.create(directory/'assignments.jsonl',study=STUDY,assignments=assignments) as log:
        for a in assignments:
            log.start(a['id'])
            try:
                r=run_case(a)
                with (directory/(a['id']+'.json')).open('xb') as f:f.write(canonical(r)+b'\n');f.flush();os.fsync(f.fileno())
                fd=os.open(directory,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
                if hashes()!=pins:raise ValueError('source changed during study')
                log.complete(a['id'],status='COMPLETED',details=dict(result_sha256=sha(r),sources_after=pins))
            except (LedgerError,LedgerWriteError):raise
            except Exception as exc:
                log.complete(a['id'],status='ERROR',details=dict(error_type=type(exc).__name__,error=str(exc)));raise
        log.finalize()
    return audit(directory)


def audit(directory):
    directory=Path(directory);ledger=inspect(directory/'assignments.jsonl');header=ledger['records'][0];assignments=header['assignments'];meta=assignments[0]['metadata']
    if (set(meta)!={'source_sha256','python','parent_commit','gate_b','study_native_steps'} or meta['gate_b']!='GATE_B_NOT_AUTHORIZED'
        or type(meta['study_native_steps']) is not int or meta['study_native_steps']!=0
        or type(meta['parent_commit']) is not str or not re.fullmatch('[0-9a-f]{40}',meta['parent_commit'])):raise ValueError('provenance contract mismatch')
    if header['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan():raise ValueError('fixed plan mismatch')
    if any(a['metadata']!=meta for a in assignments) or meta['source_sha256']!=hashes() or meta['python']!=platform.python_version():raise ValueError('source/runtime mismatch')
    results={}
    for row in ledger['records']:
        if row['kind']=='TERMINAL' and row['status']=='COMPLETED':
            a=next(x for x in assignments if x['id']==row['id']);r=run_case(a)
            if (directory/(a['id']+'.json')).read_bytes()!=canonical(r)+b'\n':raise ValueError('saved input/result mismatch')
            if row['details']!=dict(result_sha256=sha(r),sources_after=meta['source_sha256']):raise ValueError('terminal evidence mismatch')
            results[a['id']]=r
    categories={}
    for r in results.values():
        key=r['result'].get('development_action') or r['result']['status'];categories[key]=categories.get(key,0)+1
    return dict(study=STUDY,metadata=meta,counts=ledger['counts'],ledger_state=ledger['state'],categories=categories,
                assignments=[dict(id=a['id'],state=ledger['assignments'][a['id']],details=results.get(a['id'])) for a in assignments],
                study_native_steps=0,operational_authorization=False,gate_b='GATE_B_NOT_AUTHORIZED')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    r=run(a.directory) if a.mode=='run' else audit(a.directory)
    with a.output.open('xb') as f:f.write(canonical(r)+b'\n')
    print(json.dumps(dict(counts=r['counts'],categories=r['categories'],gate_b=r['gate_b'])))


if __name__=='__main__':main()
