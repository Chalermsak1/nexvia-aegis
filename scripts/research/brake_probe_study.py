#!/usr/bin/env python3
"""Separate, short development brake-observability experiment.

Motivated by passive low-speed ambiguity; not an extension/reclassification of
those trajectories. Finite sampled-window feasibility is NOT operational or
post-window authorization. All residual motion and force-budget failures remain.
"""
from dataclasses import asdict
import argparse,hashlib,json,math,platform,subprocess,sys
from pathlib import Path
import numpy as np
import mujoco
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src'))
from scripts.research import physical_reference_study as passive
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError,inspect
from aegis.development.physical_reference import KinematicReference,IntervalReading,brake_feedback_reference,force_acceleration_reference
from aegis.development.probe_window import brake_probe_window
from aegis.env.mujoco_lease_brake import ForceLimitedBrakeEnvironment

STUDY='V9-M5 finite-window brake diagnostic v1'
CASES=('nominal','brake_absent','force_feedback_spoof','coherent_spoof','wrong_sign','force_over_budget','near_wall_design')
FILES=tuple(dict.fromkeys(passive.FILES+('src/aegis/development/probe_window.py','scripts/research/brake_probe_study.py')))


def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

def plan():return [{'id':f'v{i}:{case}','initial_index':i,'initial_speed_m_s':v,'case':case,'rng_key':[20261116,5,i],
 'position':[-2.79 if case=='near_wall_design' else -2.,-2.,1.3],'delay_ticks':3,'pulse_ticks':2,'feedback_ticks':1,'cap_n':1.}
 for i,v in enumerate((.4,.5,.6)) for case in CASES]


def setup(a):
 env=ForceLimitedBrakeEnvironment();env.reset_development(a['initial_speed_m_s']);env.data.qpos[:]=a['position'];mujoco.mj_forward(env.model,env.data)
 rng=np.random.default_rng(a['rng_key']);p=np.array(a['position'])+passive.uniform_ball(rng,.005);v=np.array([a['initial_speed_m_s'],0.,0.])+passive.uniform_ball(rng,.01)
 ref=KinematicReference(p.tolist(),v.tolist(),position_error_m=.005,velocity_error_m_s=.01)
 design=brake_probe_window(ref.snapshot(),env.runtime_record(),delay_ticks=a['delay_ticks'],pulse_ticks=a['pulse_ticks'],feedback_ticks=a['feedback_ticks'])
 return env,rng,ref,design


def execute(a,emit):
 env,rng,ref,design=setup(a);emit({'type':'DESIGN','design':design,'reference_anchor':ref.snapshot(),'runtime':env.runtime_record()})
 if design['design_status']!='WITHIN_ASSERTED_SAMPLED_WINDOW':
  return {'classification':'NO_PROBE_WINDOW_DECLINED','physics_steps':0,'residual_speed_m_s':None,'design':design}
 ghost_p,ghost_v=np.array(a['position']),np.array([a['initial_speed_m_s'],0.,0.]);events=[]
 for tick in range(design['window_ticks']):
  before=env.get_state();pos,vel=before['robot_pos'].tolist(),before['robot_velocity'].tolist();start_ref=ref.snapshot()
  requested=2. if a['delay_ticks']<=tick<a['delay_ticks']+a['pulse_ticks'] else 0.
  actual=requested if a['case']=='nominal' else 0.
  rogue=[(1. if a['case']=='wrong_sign' else 3.) if requested and a['case'] in ('wrong_sign','force_over_budget') else 0.,0.,0.]
  pre=env.prepare_forces([0.,0.,0.],rogue,brake_gain=actual)
  total=np.array(pre['actuator_force_pre_n'])+rogue
  e={'type':'TICK','tick':tick,'requested_gain':requested,'actual_gain':actual,'rogue_force_n':rogue,
     'position_before':pos,'velocity_before':vel,'reference_before':start_ref,'plant':pre,'total_actual_probe_force_n':total.tolist()};emit(e);events.append(e)
  physical=env.advance_prepared();e=dict(physical,type='PHYSICS',tick=tick);emit(e);events.append(e)
  fn,an=passive.uniform_ball(rng,.005),passive.uniform_ball(rng,.04)
  true_acc=(np.array(physical['velocity'])-vel)/.02
  reported_force,reported_acc=total.copy(),true_acc.copy()
  expected=np.clip(-requested*np.array(vel),-1.,1.)
  if a['case']=='force_feedback_spoof':reported_force=expected
  if a['case']=='coherent_spoof':
   reported_force=np.clip(-requested*ghost_v,-1.,1.);reported_acc=reported_force.copy()
   ghost_v=ghost_v+.02*reported_acc;ghost_p=ghost_p+.02*ghost_v
  force=IntervalReading('BRAKE_FORCE',tick,tick+1,(reported_force+fn).tolist(),.005)
  accel=IntervalReading('ACCELERATION',tick,tick+1,(reported_acc+an).tolist(),.04)
  b=brake_feedback_reference(start_ref,force,tick=tick,requested_gain=requested,cap_per_axis_n=1.)
  c=force_acceleration_reference([0.,0.,0.],force,accel,tick=tick,mass_lower_kg=1.,mass_upper_kg=1.5,disturbance_upper_n=0.)
  after=ref.advance(accel)
  e={'type':'OBSERVATION','tick':tick,'force':asdict(force),'acceleration':asdict(accel),'force_noise':fn,'acceleration_noise':an,
     'brake_check':b,'force_acceleration_check':c,'reference_after':after,
     'force_bound_violated_for_scoring':bool(math.hypot(*total)>design['force_norm_budget_n']+1e-10),
     'force_error_for_scoring_n':float(np.linalg.norm(np.array(force.value)-total)),
     'acceleration_error_for_scoring_m_s2':float(np.linalg.norm(np.array(accel.value)-true_acc)),
     'reference_velocity_error_for_scoring_m_s':float(np.linalg.norm(np.array(after['velocity'])-physical['velocity']))};emit(e);events.append(e)
 physics=[e for e in events if e['type']=='PHYSICS'];ticks=[e for e in events if e['type']=='TICK'];obs=[e for e in events if e['type']=='OBSERVATION']
 violation=any(e['force_bound_violated_for_scoring'] for e in obs)
 contact=any(e['contact_floor'] or e['contact_obstacle'] for e in physics)
 path=sum(float(np.linalg.norm(np.array(p['position'])-t['position_before'])) for p,t in zip(physics,ticks))
 return {'classification':'FINITE_DIAGNOSTIC_WINDOW_COMPLETED_NOT_REST','physics_steps':len(physics),'design':design,
  'brake_inconsistent_pulse_samples':sum(e['brake_check']['status']=='INCONSISTENT' for e in obs),
  'cross_inconsistent_samples':sum(e['force_acceleration_check']['status']=='INCONSISTENT' for e in obs),
  'uninformative_pulse_samples':sum(e['brake_check']['status']=='UNINFORMATIVE_NEAR_ZERO' for e in obs),
  'force_sensor_bound_violations':sum(e['force_error_for_scoring_n']>.005+1e-10 for e in obs),
  'acceleration_sensor_bound_violations':sum(e['acceleration_error_for_scoring_m_s2']>.04+1e-10 for e in obs),
  'force_budget_violated':violation,'window_bound_evaluation':'UNEVALUABLE_FORCE_BUDGET' if violation else 'UNEVALUABLE_CONTACT' if contact else 'CONDITIONAL_SAMPLED_CHECK',
  'sampled_path_m':path,'path_exceeds_design_bound':None if violation or contact else path>design['sampled_path_upper_m']+1e-10,
  'residual_speed_m_s':float(np.linalg.norm(physics[-1]['velocity'])),'operational_authorization':False}


def run(path):
 sources=hashes();meta={'sources':sources,'parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  'versions':{'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__},'gate_b':'GATE_B_NOT_AUTHORIZED'}
 assignments=[dict(a,metadata=meta) for a in plan()]
 with DevelopmentLedger.create(path,study=STUDY,assignments=assignments,record_events=True) as w:
  for a in assignments:
   w.start(a['id'])
   try:
    result=execute(a,lambda e:w.event(a['id'],details=e));after=hashes()
    if after!=sources:raise ValueError('sources changed')
    w.complete(a['id'],status='COMPLETED',details={'summary':result,'sources_after':after})
   except (LedgerError,LedgerWriteError):raise
   except Exception as exc:w.complete(a['id'],status='ERROR',details={'error_type':type(exc).__name__,'error':str(exc)});raise
  w.finalize()
 return audit(path)


def audit(path):
 log=inspect(path);records=log['records'];assignments=records[0]['assignments']
 if records[0]['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan():raise ValueError('wrong study/plan')
 meta=assignments[0]['metadata']
 if any(a['metadata']!=meta for a in assignments):raise ValueError('metadata mismatch')
 rows=[]
 for a in assignments:
  state=log['assignments'][a['id']]
  if state!='COMPLETED':rows.append({'id':a['id'],'state':state,'summary':None});continue
  ev=[r['details'] for r in records if r['kind']=='EVENT' and r['id']==a['id']]
  terminal=next(r['details'] for r in records if r['kind']=='TERMINAL' and r['id']==a['id'])
  if terminal['sources_after']!=meta['sources']:raise ValueError('source mismatch')
  env,rng,ref,design=setup(a)  # Compile/check initial model only; no integration.
  if not ev or ev[0]!={'type':'DESIGN','design':design,'reference_anchor':ref.snapshot(),'runtime':env.runtime_record()}:raise ValueError('probe design/runtime mismatch')
  if design['design_status']!='WITHIN_ASSERTED_SAMPLED_WINDOW':
   expected={'classification':'NO_PROBE_WINDOW_DECLINED','physics_steps':0,'residual_speed_m_s':None,'design':design}
   if len(ev)!=1 or terminal['summary']!=expected:raise ValueError('declined window contains execution evidence')
   rows.append({'id':a['id'],'state':state,'summary':expected});continue
  if len(ev)!=1+3*design['window_ticks']:raise ValueError('missing probe evidence')
  pos=np.array(a['position']);vel=np.array([a['initial_speed_m_s'],0.,0.]);ghost_p=pos.copy();ghost_v=vel.copy()
  for tick in range(design['window_ticks']):
   t,p,o=ev[1+3*tick:4+3*tick]
   if [v['type'] for v in (t,p,o)]!=['TICK','PHYSICS','OBSERVATION'] or any(v['tick']!=tick for v in (t,p,o)):raise ValueError('probe event order')
   if t['position_before']!=pos.tolist() or t['velocity_before']!=vel.tolist() or t['reference_before']!=ref.snapshot():raise ValueError('probe continuity/reference')
   requested=2. if a['delay_ticks']<=tick<a['delay_ticks']+a['pulse_ticks'] else 0.;actual=requested if a['case']=='nominal' else 0.
   rogue=np.array([(1. if a['case']=='wrong_sign' else 3.) if requested and a['case'] in ('wrong_sign','force_over_budget') else 0.,0.,0.])
   brake=np.clip(-actual*vel,-1.,1.);total=brake+rogue;applied=rogue.copy();applied[2]+=9.81
   if (t['requested_gain']!=requested or t['actual_gain']!=actual or t['rogue_force_n']!=rogue.tolist() or
       not np.allclose(t['total_actual_probe_force_n'],total,rtol=0.,atol=1e-12)):raise ValueError('probe force intent')
   plant=t['plant']
   if (not np.allclose(plant['actuator_force_pre_n'],brake,rtol=0.,atol=1e-12) or not np.allclose(plant['generalized_brake_force_pre_n'],brake,rtol=0.,atol=1e-12) or
       plant['applied_body_force_n']!=applied.tolist() or plant['native_gain']!=[actual]*3 or plant['native_velocity_bias']!=[-actual]*3 or
       plant['native_target_velocity']!=[0.]*3 or plant['brake_gain']!=actual or plant['phase']!='PRE_INTEGRATION_NATIVE_ACTUATOR_FORCE'):raise ValueError('native probe actuator mismatch')
   vn=vel+.02*total;pn=pos+.02*vn
   if not np.allclose(p['velocity'],vn,rtol=0.,atol=1e-10) or not np.allclose(p['position'],pn,rtol=0.,atol=1e-10) or p['integrated_qpos']!=p['position'] or abs(p['time']-(tick+1)*.02)>1e-10:raise ValueError('probe integration mismatch')
   runtime=ev[0]['runtime'];point=np.array(p['position']);limit=runtime['arena_limit']-runtime['robot_radius']
   boundary=min(point[2]-runtime['robot_radius'],limit-point[2],limit-abs(point[0]),limit-abs(point[1]))
   clearance=min(float(np.linalg.norm(point-b['center'])-runtime['robot_radius']-b['radius']) for b in runtime['obstacles'])
   if p['contact_floor'] or p['contact_obstacle'] or p['geometric_or_contact_violation'] or abs(p['boundary_clearance']-boundary)>1e-10 or abs(p['min_obstacle_distance']-clearance)>1e-10:raise ValueError('probe contact/geometry inconsistency')
   fn,an=passive.uniform_ball(rng,.005),passive.uniform_ball(rng,.04);true_acc=(np.array(p['velocity'])-vel)/.02
   sensed_force,sensed_acc=total.copy(),true_acc.copy();expected_force=np.clip(-requested*vel,-1.,1.)
   if a['case']=='force_feedback_spoof':sensed_force=expected_force
   if a['case']=='coherent_spoof':
    sensed_force=np.clip(-requested*ghost_v,-1.,1.);sensed_acc=sensed_force.copy();ghost_v=ghost_v+.02*sensed_acc;ghost_p=ghost_p+.02*ghost_v
   force=IntervalReading('BRAKE_FORCE',tick,tick+1,(sensed_force+fn).tolist(),.005);accel=IntervalReading('ACCELERATION',tick,tick+1,(sensed_acc+an).tolist(),.04)
   b=brake_feedback_reference(ref.snapshot(),force,tick=tick,requested_gain=requested,cap_per_axis_n=1.)
   c=force_acceleration_reference([0.,0.,0.],force,accel,tick=tick,mass_lower_kg=1.,mass_upper_kg=1.5,disturbance_upper_n=0.)
   expected_observation={'type':'OBSERVATION','tick':tick,'force':asdict(force),'acceleration':asdict(accel),'force_noise':fn,'acceleration_noise':an,
      'brake_check':b,'force_acceleration_check':c,'reference_after':ref.advance(accel),'force_bound_violated_for_scoring':bool(math.hypot(*total)>design['force_norm_budget_n']+1e-10)}
   expected_observation.update(force_error_for_scoring_n=float(np.linalg.norm(np.array(force.value)-total)),
     acceleration_error_for_scoring_m_s2=float(np.linalg.norm(np.array(accel.value)-true_acc)),
     reference_velocity_error_for_scoring_m_s=float(np.linalg.norm(np.array(ref.snapshot()['velocity'])-p['velocity'])))
   if o!=expected_observation:raise ValueError('probe observation mismatch')
   pos,vel=np.array(p['position']),np.array(p['velocity'])
  physics=[e for e in ev if e['type']=='PHYSICS'];ticks=[e for e in ev if e['type']=='TICK'];obs=[e for e in ev if e['type']=='OBSERVATION']
  violation=any(e['force_bound_violated_for_scoring'] for e in obs);contact=any(e['contact_floor'] or e['contact_obstacle'] for e in physics)
  path=sum(float(np.linalg.norm(np.array(p['position'])-t['position_before'])) for p,t in zip(physics,ticks))
  expected={'classification':'FINITE_DIAGNOSTIC_WINDOW_COMPLETED_NOT_REST','physics_steps':len(physics),'design':design,
   'brake_inconsistent_pulse_samples':sum(e['brake_check']['status']=='INCONSISTENT' for e in obs),'cross_inconsistent_samples':sum(e['force_acceleration_check']['status']=='INCONSISTENT' for e in obs),
   'uninformative_pulse_samples':sum(e['brake_check']['status']=='UNINFORMATIVE_NEAR_ZERO' for e in obs),
   'force_sensor_bound_violations':sum(e['force_error_for_scoring_n']>.005+1e-10 for e in obs),
   'acceleration_sensor_bound_violations':sum(e['acceleration_error_for_scoring_m_s2']>.04+1e-10 for e in obs),'force_budget_violated':violation,
   'window_bound_evaluation':'UNEVALUABLE_FORCE_BUDGET' if violation else 'UNEVALUABLE_CONTACT' if contact else 'CONDITIONAL_SAMPLED_CHECK',
   'sampled_path_m':path,'path_exceeds_design_bound':None if violation or contact else path>design['sampled_path_upper_m']+1e-10,
   'residual_speed_m_s':float(np.linalg.norm(physics[-1]['velocity'])),'operational_authorization':False}
  if terminal['summary']!=expected:raise ValueError('probe summary mismatch')
  rows.append({'id':a['id'],'state':state,'summary':expected})
 return {'study':STUDY,'ledger_state':log['state'],'counts':log['counts'],'metadata':meta,'assignments':rows,
  'audit_method':'READ_ONLY_ARITHMETIC_AND_RECORD_RECONSTRUCTION','classification':'DEVELOPMENT_PROBE_NOT_OPERATIONAL_OR_CONFIRMATORY_AUTHORIZATION',
  'gate_b':'GATE_B_NOT_AUTHORIZED','limitations':['Only a short sampled design window; no post-window recoverability or rest guarantee.',
   'Sensor, geometry, initial-state and force bounds are unverified model assertions.','Reader compiles the initial model but never advances physics.']}


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('ledger',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('output exists')
 r=run(a.ledger) if a.mode=='run' else audit(a.ledger)
 with a.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'state':r['ledger_state'],'counts':r['counts']}))
if __name__=='__main__':main()
