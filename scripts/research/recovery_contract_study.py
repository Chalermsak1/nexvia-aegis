"""Compact development fixtures for a conditional post-probe recovery reference.

Native MuJoCo execution uses a fixed design horizon, never a truth-based early
stop. Truth is only logged/scored. Synthetic limits are not registered rules.
The auditor compiles the declared model but never advances physics.
"""
import argparse,hashlib,json,math,platform,subprocess
from pathlib import Path
import numpy as np
import mujoco
from aegis.development.recovery_contract import assess_recovery
from aegis.env.mujoco_lease_brake import ForceLimitedBrakeEnvironment
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError
from scripts.research.streaming_ledger import LedgerStream
from scripts.research import physical_reference_study as reference
ROOT=Path(__file__).resolve().parents[2]
STUDY='V9-M5 conditional recovery contract synthetic fixtures v1'
CASES=('nominal','finite_disturbance','infinite_disturbance_declined','terminal_authority_declined',
 'cap_authority_declined','availability_declined','near_wall_declined','energy_declined','horizon_declined',
 'wrong_sign_probe','over_budget_probe','brake_loss','late_brake_loss')
FILES=tuple(dict.fromkeys(reference.FILES+('src/aegis/development/recovery_contract.py','scripts/research/streaming_ledger.py','scripts/research/recovery_contract_study.py')))

def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}

def plan():
 headings=([1.,0.,0.],[0.,1.,0.],[1/math.sqrt(3)]*3)
 return [{'id':f'h{i}:{case}','heading':list(h),'case':case,'initial_speed_m_s':.5,
          'position':[-2.69 if case=='near_wall_declined' else -2.,-2.,1.3]}
         for i,h in enumerate(headings) for case in CASES]

def setup(a):
 env=ForceLimitedBrakeEnvironment();env.reset_development(a['initial_speed_m_s'])
 env.data.qpos[:]=a['position'];env.data.qvel[:]=np.array(a['heading'])*a['initial_speed_m_s'];mujoco.mj_forward(env.model,env.data)
 anchor={'status':'CONDITIONAL_REFERENCE','position':a['position'],'velocity':env.data.qvel.tolist(),
         'position_error_m':.005,'velocity_error_m_s':.01}
 case=a['case'];d=.02 if case in ('finite_disturbance','infinite_disturbance_declined') else .2 if case in ('terminal_authority_declined','cap_authority_declined') else 0.
 cfg=dict(pre_steps=6,dt_seconds=.02,probe_force_norm_upper_n=math.sqrt(3),mass_lower_kg=1.,mass_upper_kg=1.5,
   brake_gain_lower_kg_s=2.,brake_gain_upper_kg_s=2.,cap_lower_n=.05 if case=='cap_authority_declined' else 1.,
   disturbance_upper_n=d,brake_available_asserted=case!='availability_declined',terminal_speed_m_s=.05,dwell_steps=25,
   max_total_steps=5 if case=='horizon_declined' else 300,max_energy_increase_j=.001 if case=='energy_declined' else .2,
   require_infinite_sampled_containment=case!='finite_disturbance')
 design=assess_recovery(anchor,env.runtime_record(),**cfg)
 first={'type':'DESIGN','runtime':env.runtime_record(),'reference_anchor':anchor,'config':cfg,'design':design,
        'criteria_origin':'EXPLICIT_SYNTHETIC_FIXTURE_NOT_REGISTERED_OR_OWNER_APPROVED'}
 return env,first

def intent(a,first,tick):
 c=first['config'];design=first['design'];pre=tick<c['pre_steps'];pulse=3<=tick<5
 requested=2. if not pre or pulse else 0.;actual=requested
 if a['case'] in ('wrong_sign_probe','over_budget_probe') and pre:actual=0.
 if a['case']=='brake_loss' and not pre:actual=0.
 if a['case']=='late_brake_loss' and tick>=c['pre_steps']+design['recovery_steps']:actual=0.
 rogue=np.array(a['heading'])*(3. if a['case']=='over_budget_probe' else .8) if pulse and a['case'] in ('wrong_sign_probe','over_budget_probe') else np.zeros(3)
 disturbance=np.array(a['heading'])*c['disturbance_upper_n']
 return requested,actual,rogue,disturbance

def summarize(first,events):
 design=first['design'];c=first['config']
 if design['design_status']!='WITHIN_ASSERTED_RECOVERY_DESIGN':
  return {'classification':'DESIGN_DECLINED_NO_EXECUTION','physics_steps':0,'design_status':design['design_status'],
          'model_evaluation':'UNEVALUABLE_DESIGN','terminal_speed_band_and_dwell_observed':None,'sampled_path_m':None,
          'operational_authorization':False}
 ticks=[e for e in events if e['type']=='TICK'];post=[e for e in events if e['type']=='PHYSICS']
 contacts=any(p['contact_floor'] or p['contact_obstacle'] or p['geometric_or_contact_violation'] for p in post)
 force_bad=any(math.hypot(*e['actual_probe_force_n'])>c['probe_force_norm_upper_n']+1e-10 for e in ticks if e['tick']<c['pre_steps'])
 brake_bad=any(e['actual_gain']<c['brake_gain_lower_kg_s'] for e in ticks if e['tick']>=c['pre_steps'])
 premise_bad=contacts or force_bad or brake_bad
 boundary=c['pre_steps']+design['recovery_steps']
 selected=post[max(0,boundary-1):]  # terminal sample plus every dwell sample
 speeds=[math.hypot(*p['velocity']) for p in selected]
 path=sum(math.dist(t['position_before'],p['position']) for t,p in zip(ticks,post))
 k0=.5*math.hypot(*first['reference_anchor']['velocity'])**2
 energy_increase=max([0.]+[.5*math.hypot(*p['velocity'])**2-k0 for p in post])
 return {'classification':'FINITE_SYNTHETIC_RECOVERY_FIXTURE','physics_steps':len(post),'design_status':design['design_status'],
  'model_evaluation':'UNEVALUABLE_PREMISE_VIOLATION' if premise_bad else 'CONDITIONAL_SAMPLED_COMPARISON',
  'force_budget_violated':force_bad,'brake_availability_violated':brake_bad,'contact_or_geometry_violation':contacts,
  'terminal_speed_band_and_dwell_observed':bool(speeds and max(speeds)<=c['terminal_speed_m_s']+1e-10),
  'maximum_terminal_dwell_speed_m_s':max(speeds) if speeds else None,'terminal_dwell_samples':len(speeds),
  'residual_speed_m_s':math.hypot(*post[-1]['velocity']),'sampled_path_m':path,
  'observed_kinetic_energy_increase_j':energy_increase,
  'path_exceeds_design_bound':None if premise_bad else path>design['finite_sampled_path_upper_m']+1e-10,
  'energy_exceeds_design_bound':None if premise_bad else energy_increase>design['energy_increase_upper_j']+1e-10,
  'empirical_post_horizon_containment':'NOT_ESTABLISHED_BY_FINITE_TRAJECTORY','operational_authorization':False}

def execute(a,emit):
 env,first=setup(a);emit(first);events=[]
 if first['design']['design_status']!='WITHIN_ASSERTED_RECOVERY_DESIGN':return summarize(first,events)
 for tick in range(first['design']['required_total_steps']):
  state=env.get_state();pos=state['robot_pos'].tolist();vel=state['robot_velocity'].tolist()
  requested,actual,rogue,disturbance=intent(a,first,tick)
  pre=env.prepare_forces([0.,0.,0.],(rogue+disturbance).tolist(),brake_gain=actual)
  e={'type':'TICK','tick':tick,'position_before':pos,'velocity_before':vel,'requested_gain':requested,'actual_gain':actual,
     'rogue_force_n':rogue.tolist(),'disturbance_n':disturbance.tolist(),'plant':pre,
     'actual_probe_force_n':(np.array(pre['actuator_force_pre_n'])+rogue).tolist()}
  emit(e);events.append(e)  # persisted before irreversible physics advance
  e=dict(env.advance_prepared(),type='PHYSICS',tick=tick);emit(e);events.append(e)
 return summarize(first,events)

def audit_episode(a,ev,terminal,meta):
 env,first=setup(a)  # initial model compilation only
 if not ev or ev[0]!=first:raise ValueError('design/runtime mismatch')
 if terminal['sources_after']!=meta['sources']:raise ValueError('source identity mismatch')
 design=first['design'];steps=design['required_total_steps'] if design['design_status']=='WITHIN_ASSERTED_RECOVERY_DESIGN' else 0
 if len(ev)!=1+2*steps:raise ValueError('missing/extra recovery evidence')
 pos=np.array(a['position']);vel=np.array(first['reference_anchor']['velocity']);runtime=first['runtime']
 for tick in range(steps):
  t,p=ev[1+2*tick:3+2*tick]
  if t['type']!='TICK' or p['type']!='PHYSICS' or t['tick']!=tick or p['tick']!=tick:raise ValueError('event order')
  if t['position_before']!=pos.tolist() or t['velocity_before']!=vel.tolist():raise ValueError('continuity')
  requested,actual,rogue,disturbance=intent(a,first,tick)
  brake=np.clip(-actual*vel,-1.,1.);applied=rogue+disturbance;applied[2]+=9.81
  expected={'actuator_force_pre_n':brake.tolist(),'generalized_brake_force_pre_n':brake.tolist(),
   'applied_body_force_n':applied.tolist(),'brake_gain':actual,'phase':'PRE_INTEGRATION_NATIVE_ACTUATOR_FORCE',
   'native_gain':[actual]*3,'native_velocity_bias':[-actual]*3,'native_target_velocity':[0.]*3}
  if set(t['plant'])!=set(expected):raise ValueError('native fields')
  for k,v in expected.items():
   if isinstance(v,list):
    if not np.allclose(t['plant'][k],v,atol=1e-12,rtol=0):raise ValueError('native force/configuration')
   elif t['plant'][k]!=v:raise ValueError('native configuration')
  if t['requested_gain']!=requested or t['actual_gain']!=actual or t['rogue_force_n']!=rogue.tolist() or t['disturbance_n']!=disturbance.tolist() or not np.allclose(t['actual_probe_force_n'],brake+rogue,atol=1e-12,rtol=0):raise ValueError('intent mismatch')
  # This versioned plan is contact free. Contact would invalidate free-motion reconstruction;
  # fail audit rather than silently applying a free-motion equation across contact.
  if p['contact_floor'] or p['contact_obstacle'] or p['geometric_or_contact_violation']:raise ValueError('contact requires unsupported dynamics audit; raw evidence retained')
  vn=vel+.02*(brake+rogue+disturbance);pn=pos+.02*vn
  if not np.allclose(p['velocity'],vn,atol=1e-10,rtol=0) or not np.allclose(p['position'],pn,atol=1e-10,rtol=0) or p['integrated_qpos']!=p['position'] or abs(p['time']-(tick+1)*.02)>1e-10:raise ValueError('integration mismatch')
  point=np.array(p['position']);limit=runtime['arena_limit']-runtime['robot_radius']
  boundary=min(point[2]-runtime['robot_radius'],limit-point[2],limit-abs(point[0]),limit-abs(point[1]))
  obstacle=min(float(np.linalg.norm(point-b['center'])-runtime['robot_radius']-b['radius']) for b in runtime['obstacles'])
  if boundary<=0 or obstacle<=0 or abs(p['boundary_clearance']-boundary)>1e-10 or abs(p['min_obstacle_distance']-obstacle)>1e-10:raise ValueError('geometry mismatch')
  pos,vel=np.array(p['position']),np.array(p['velocity'])
 result=summarize(first,ev[1:])
 if terminal['summary']!=result:raise ValueError('summary mismatch')
 return result

def audit(path):
 active=None;events=[];rows={};peak=0
 with LedgerStream(path) as reader:
  for r in reader:
   if r['kind']=='HEADER':
    assignments=r['assignments'];meta=assignments[0]['metadata'];by_id={a['id']:a for a in assignments}
    if r['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan() or any(a['metadata']!=meta for a in assignments):raise ValueError('study/plan/metadata mismatch')
   elif r['kind']=='START':
    if active is not None:raise ValueError('sequential study required')
    active=r['id'];events=[]
   elif r['kind']=='EVENT':
    if r['id']!=active:raise ValueError('nonsequential event')
    events.append(r['details']);peak=max(peak,len(events))
   elif r['kind']=='TERMINAL':
    if r['id']!=active:raise ValueError('nonsequential terminal')
    if r['status']=='COMPLETED':rows[active]=audit_episode(by_id[active],events,r['details'],meta)
    active=None;events=[]
  state=reader.summary()
 return {'study':STUDY,'ledger_state':state['state'],'counts':state['counts'],'metadata':meta,
  'assignments':[{'id':a['id'],'state':state['assignments'][a['id']],'summary':rows.get(a['id'])} for a in assignments],
  'peak_buffered_episode_events':peak,'gate_b':'GATE_B_NOT_AUTHORIZED',
  'classification':'SYNTHETIC_DEVELOPMENT_NOT_CONFIRMATORY_OR_ROBOT_VALIDATION',
  'limitations':['Declared initial-error, geometry and actuator bounds lack physical calibration.',
   'Floating arithmetic is not interval verified. Finite samples do not prove future brake availability.',
   'Nominal 1 kg plant and perfect gravity compensation only; no rotation/contact dynamics validation.',
   'Speed, dwell, energy and horizon settings are synthetic; not approved operational criteria.']}

def run(path):
 sources=hashes();meta={'sources':sources,'parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  'versions':{'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__},'gate_b':'GATE_B_NOT_AUTHORIZED'}
 assignments=[dict(a,metadata=meta) for a in plan()]
 with DevelopmentLedger.create(path,study=STUDY,assignments=assignments,record_events=True) as w:
  for a in assignments:
   w.start(a['id'])
   try:
    summary=execute(a,lambda e:w.event(a['id'],details=e));after=hashes()
    if sources!=after:raise ValueError('sources changed during execution')
    w.complete(a['id'],status='COMPLETED',details={'summary':summary,'sources_after':after})
   except (LedgerError,LedgerWriteError):raise
   except Exception as exc:
    w.complete(a['id'],status='ERROR',details={'error_type':type(exc).__name__,'error':str(exc)});raise
  w.finalize()
 return audit(path)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('ledger',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 if a.output.exists():p.error('output exists')
 r=run(a.ledger) if a.mode=='run' else audit(a.ledger)
 with a.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'state':r['ledger_state'],'counts':r['counts']}))
if __name__=='__main__':main()
