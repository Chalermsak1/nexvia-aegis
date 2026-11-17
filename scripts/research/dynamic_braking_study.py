"""Development-only delayed/ramped force braking with measured-feedback monitoring.

All power/error/delay settings are synthetic. No Holdout, real robot, trusted
hardware feedback, operational admission or newly approved scientific rule.
"""
from dataclasses import asdict
import argparse,hashlib,json,math,platform,subprocess
from pathlib import Path
import numpy as np
import mujoco
from aegis.development.dynamic_braking import DelayedSlewBrake,MeasuredRecoveryMonitor
from aegis.development.bounded_braking import BoundedStatePacket
from aegis.development.physical_reference import IntervalReading
from aegis.env.mujoco_power_brake import PowerBrakeEnvironment
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError
from scripts.research.streaming_ledger import LedgerStream
ROOT=Path(__file__).resolve().parents[2]
STUDY='V9-M5 delayed ramped powered braking measured feedback v1'
CASES=('nominal','delay_mismatch','ramp_mismatch','brake_bus_loss','backup_exhaustion','total_actuation_loss',
 'sensor_loss','force_dropout','stale_state','force_spoof','force_acc_spoof','all_feedback_ghost','late_bus_loss')
ARMS=('FAST_REFERENCE','DELAYED_RAMPED')
FILES=('src/aegis/development/__init__.py','src/aegis/development/bounded_braking.py','src/aegis/development/physical_reference.py',
 'src/aegis/development/recovery_contract.py','src/aegis/development/dynamic_braking.py','src/aegis/env/mujoco_3d_cbf.py',
 'src/aegis/env/mujoco_lease_brake.py','src/aegis/env/mujoco_power_brake.py','scripts/research/development_ledger.py',
 'scripts/research/streaming_ledger.py','scripts/research/dynamic_braking_study.py')

def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
def plan():
 return [{'id':f'h{i}:{case}:{arm}','heading':list(h),'case':case,'arm':arm,'steps':160,'rng_key':[20261116,7,i],
  'speed_m_s':.5,'position':[-2.,-2.,1.3],'cut_tick':100 if case=='late_bus_loss' else 12,
  'backup_ticks':40 if case=='backup_exhaustion' else 0}
  for i,h in enumerate(([1.,0.,0.],[1/math.sqrt(3)]*3)) for case in CASES for arm in ARMS]

def profile_config(a):
 return {'delay_ticks':3 if a['arm']=='DELAYED_RAMPED' else 0,'slew_n_s':4. if a['arm']=='DELAYED_RAMPED' else 1000.,'cap_n':1.,'dt_seconds':.02}
def actual_config(a):
 c=profile_config(a)
 if a['case']=='delay_mismatch':c['delay_ticks']+=5
 if a['case']=='ramp_mismatch':c['slew_n_s']/=4
 return c

def domains(a,k):
 cut=k>=a['cut_tick'];silent=a['case'] in ('force_spoof','force_acc_spoof','all_feedback_ghost')
 lost=cut and a['case'] in ('brake_bus_loss','backup_exhaustion','total_actuation_loss','late_bus_loss')
 brake=not silent and (not lost or (a['case']=='backup_exhaustion' and k<a['cut_tick']+a['backup_ticks']))
 gravity=not (cut and a['case']=='total_actuation_loss')
 return brake,gravity


def packet(p,v,k):return BoundedStatePacket(np.asarray(p,dtype=float).tolist(),np.asarray(v,dtype=float).tolist(),.005,.01,k,k*.02,'WORLD','SIM_DYNAMIC_STATE_V1','ASSERTED_SYNTHETIC_ERROR_BALL')
def noise(rng,r):return rng.uniform(-r/math.sqrt(3),r/math.sqrt(3),3)
def serialize(s):return None if s is None else asdict(s)
def state_from(s):return None if s is None else BoundedStatePacket(**s)
def interval_from(s):return None if s is None else IntervalReading(**s)


class SensorFixture:
 """Only this fault generator and the scorer receive simulator truth."""
 def __init__(self,a):
  self.a=a;self.rng=np.random.default_rng(a['rng_key']);self.ghost_p=np.array(a['position']);self.ghost_v=np.array(a['heading'])*a['speed_m_s'];self.last=None
 def capture(self,p,v,k):
  pn,vn=noise(self.rng,.005),noise(self.rng,.01)
  reading=packet(np.array(p)+pn,np.array(v)+vn,k)
  if k>=self.a['cut_tick'] and self.a['case']=='sensor_loss':return None
  if k>=self.a['cut_tick'] and self.a['case']=='stale_state':return self.last
  self.last=reading;return reading
 def initial(self):return self.capture(self.ghost_p,self.ghost_v,0)
 def after(self,k,expected_force,actual_force,before_velocity,physical):
  fn,an=noise(self.rng,.005),noise(self.rng,.04)
  true_acc=(np.array(physical['velocity'])-before_velocity)/.02
  f,a=np.array(actual_force),true_acc.copy()
  if self.a['case'] in ('force_spoof','force_acc_spoof','all_feedback_ghost'):f=np.array(expected_force)
  if self.a['case'] in ('force_acc_spoof','all_feedback_ghost'):a=np.array(expected_force)
  self.ghost_v=self.ghost_v+.02*np.array(expected_force);self.ghost_p=self.ghost_p+.02*self.ghost_v
  p,v=(self.ghost_p,self.ghost_v) if self.a['case']=='all_feedback_ghost' else (physical['position'],physical['velocity'])
  state=self.capture(p,v,k+1)
  force=IntervalReading('BRAKE_FORCE',k,k+1,(f+fn).tolist(),.005)
  accel=IntervalReading('ACCELERATION',k,k+1,(a+an).tolist(),.04)
  if k>=self.a['cut_tick'] and self.a['case'] in ('sensor_loss','force_dropout'):force=None
  if k>=self.a['cut_tick'] and self.a['case']=='sensor_loss':accel=None
  # Truth used for scoring only; never supplied to the measured monitor.
  violations={'state_position':None if state is None else math.dist(state.position,physical['position'])>.005+1e-10,
   'state_velocity':None if state is None else math.dist(state.velocity,physical['velocity'])>.01+1e-10,
   'force':None if force is None else math.dist(force.value,actual_force)>.005+1e-10,
   'acceleration':None if accel is None else math.dist(accel.value,true_acc)>.04+1e-10}
  return {'state':serialize(state),'force':serialize(force),'acceleration':serialize(accel),'truth_channel_bound_violations':violations}


def setup(a):
 env=PowerBrakeEnvironment();env.reset_development(a['speed_m_s']);env.data.qpos[:]=a['position'];env.data.qvel[:]=np.array(a['heading'])*a['speed_m_s'];mujoco.mj_forward(env.model,env.data)
 sensors=SensorFixture(a);anchor=sensors.initial();cfg=dict(profile_config(a),gain=2.,position_error_m=.005,velocity_error_m_s=.01,force_error_n=.005,
  acceleration_error_m_s2=.04,mass_lower_kg=1.,mass_upper_kg=1.,disturbance_upper_n=0.,terminal_speed_m_s=.05,dwell_ticks=25,minimum_clearance_m=.02)
 monitor=MeasuredRecoveryMonitor(anchor,env.runtime_record(),**cfg);actuator=DelayedSlewBrake(**actual_config(a))
 first={'type':'RESET','runtime':env.runtime_record(),'anchor':serialize(anchor),'monitor_config':cfg,'actual_actuator_config':actual_config(a),
  'measurement_supply':'INDEPENDENT_BACKUP_ASSUMED_FOR_LOGGING_EXCEPT_DECLARED_CHANNEL_LOSS','criteria_origin':'SYNTHETIC_DEVELOPMENT_ONLY'}
 return env,sensors,monitor,actuator,anchor,first


def summarize(a,ev):
 ticks=[e for e in ev if e['type']=='TICK'];physics=[e for e in ev if e['type']=='PHYSICS'];obs=[e for e in ev if e['type']=='OBSERVATION']
 contacts=any(e['contact_floor'] or e['contact_obstacle'] or e['geometric_or_contact_violation'] for e in physics)
 true_dwell=0;max_true=0
 for p in physics:
  okay=math.hypot(*p['velocity'])<=.05 and min(p['boundary_clearance'],p['min_obstacle_distance'])>=.02
  true_dwell=true_dwell+1 if okay else 0;max_true=max(max_true,true_dwell)
 channel_counts={key:sum(o['measurements']['truth_channel_bound_violations'][key] is True for o in obs) for key in ('state_position','state_velocity','force','acceleration')}
 contact_steps=sum(t['plant']['contact_floor_pre'] or t['plant']['contact_obstacle_pre'] or p['contact_floor'] or p['contact_obstacle'] for t,p in zip(ticks,physics))
 return {'classification':'SIMULATION_DEVELOPMENT_ONLY','physics_steps':len(physics),'sampled_path_m':sum(math.dist(t['position_before'],p['position']) for t,p in zip(ticks,physics)),
  'contact_or_geometry_violation':contacts,'contact_dynamics_steps_not_reconstructed':contact_steps,
  'residual_speed_m_s':math.hypot(*physics[-1]['velocity']),
  'first_force_inconsistency_tick':next((o['tick'] for o in obs if o['monitor']['force_check']['status']=='INCONSISTENT'),None),
  'first_any_inconsistency_tick':next((o['tick'] for o in obs if o['monitor']['assessment']=='INCONSISTENCY_OBSERVED'),None),
  'unknown_evidence_samples':sum(o['monitor']['assessment']=='UNKNOWN_EVIDENCE' for o in obs),
  'maximum_supported_measured_samples':max(o['monitor']['consecutive_supported_samples'] for o in obs),
  'final_measured_dwell_under_asserted_channels':obs[-1]['monitor']['measured_dwell_under_asserted_channels'],
  'final_truth_speed_clearance_dwell':true_dwell>=25 and not contacts,
  'maximum_truth_speed_clearance_samples':max_true,'truth_channel_bound_violations':channel_counts,
  'false_measured_dwell_for_scoring':bool(obs[-1]['monitor']['measured_dwell_under_asserted_channels'] and not (true_dwell>=25 and not contacts)),
  'future_position_containment':'NOT_ESTABLISHED','operational_authorization':False}


def execute(a,emit):
 env,sensors,monitor,actuator,current,first=setup(a);emit(first);events=[]
 for k in range(a['steps']):
  before=env.get_state();command=monitor.command(current,tick=k);brake,gravity=domains(a,k)
  force=actuator.step(command['request_n'],tick=k,powered=brake)
  pre=env.prepare_powered_force(force,brake_powered=brake,gravity_powered=gravity,disturbance=[0.,0.,0.])
  t={'type':'TICK','tick':k,'state_packet':serialize(current),'command':command,'position_before':before['robot_pos'].tolist(),
   'velocity_before':before['robot_velocity'].tolist(),'actuator_force_request_n':force,'plant':pre};emit(t);events.append(t)
  p=dict(env.advance_prepared(),type='PHYSICS',tick=k);emit(p);events.append(p)
  measurements=sensors.after(k,command['expected_force_n'],pre['actuator_force_pre_n'],before['robot_velocity'],p)
  current=state_from(measurements['state'])
  result=monitor.observe(interval_from(measurements['force']),interval_from(measurements['acceleration']),current,tick=k)
  o={'type':'OBSERVATION','tick':k,'measurements':measurements,'monitor':result};emit(o);events.append(o)
 return summarize(a,events)


def audit_episode(a,ev,terminal,meta):
 env,sensors,monitor,actuator,current,first=setup(a)  # Compiles/checks, never integrates.
 if not ev or ev[0]!=first or len(ev)!=1+3*a['steps']:raise ValueError('reset/runtime/event count mismatch')
 if terminal['sources_after']!=meta['sources']:raise ValueError('source map mismatch')
 pos=np.array(a['position']);vel=np.array(a['heading'])*a['speed_m_s']
 for k in range(a['steps']):
  t,p,o=ev[1+3*k:4+3*k]
  if [e['type'] for e in (t,p,o)]!=['TICK','PHYSICS','OBSERVATION'] or any(e['tick']!=k for e in (t,p,o)):raise ValueError('event order')
  if t['position_before']!=pos.tolist() or t['velocity_before']!=vel.tolist() or t['state_packet']!=serialize(current):raise ValueError('continuity/state packet')
  command=monitor.command(current,tick=k);brake,gravity=domains(a,k);force=actuator.step(command['request_n'],tick=k,powered=brake)
  env.data.qpos[:]=pos;env.data.qvel[:]=vel
  pre=env.prepare_powered_force(force,brake_powered=brake,gravity_powered=gravity,disturbance=[0.,0.,0.])
  if t['command']!=command or t['actuator_force_request_n']!=force or t['plant']!=pre:raise ValueError('force/power/command mismatch')
  if p['integrated_qpos']!=p['position'] or abs(p['time']-(k+1)*.02)>1e-10:raise ValueError('phase/time mismatch')
  env.data.qpos[:]=p['position'];env.data.qvel[:]=p['velocity'];mujoco.mj_forward(env.model,env.data);state=env.get_state()
  for key in ('contact_floor','contact_obstacle'):
   if p[key]!=bool(state[key]):raise ValueError('native contact state mismatch')
  if p['geometric_or_contact_violation']!=bool(state['safety_violation']):raise ValueError('geometry violation mismatch')
  if abs(p['boundary_clearance']-state['boundary_clearance'])>1e-10 or abs(p['min_obstacle_distance']-state['min_obstacle_distance'])>1e-10:raise ValueError('clearance mismatch')
  contact=pre['contact_floor_pre'] or pre['contact_obstacle_pre'] or p['contact_floor'] or p['contact_obstacle']
  if not contact:
   acc=np.array(pre['actuator_force_pre_n'])+np.array(pre['applied_body_force_n'])+np.array(first['runtime']['gravity'])
   vn=vel+.02*acc;pn=pos+.02*vn
   if not np.allclose(p['velocity'],vn,rtol=0,atol=1e-10) or not np.allclose(p['position'],pn,rtol=0,atol=1e-10):raise ValueError('free-flight integration mismatch')
  measurements=sensors.after(k,command['expected_force_n'],pre['actuator_force_pre_n'],vel,p)
  current=state_from(measurements['state']);result=monitor.observe(interval_from(measurements['force']),interval_from(measurements['acceleration']),current,tick=k)
  if o['measurements']!=measurements or o['monitor']!=result:raise ValueError('measurement/monitor mismatch')
  pos,vel=np.array(p['position']),np.array(p['velocity'])
 expected=summarize(a,ev[1:])
 if terminal['summary']!=expected:raise ValueError('summary mismatch')
 return expected


def audit(path):
 active=None;events=[];summaries={};peak=0
 with LedgerStream(path) as reader:
  for r in reader:
   if r['kind']=='HEADER':
    assignments=r['assignments'];meta=assignments[0]['metadata'];by_id={a['id']:a for a in assignments}
    if r['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan() or any(a['metadata']!=meta for a in assignments):raise ValueError('study/plan/metadata')
   elif r['kind']=='START':
    if active is not None:raise ValueError('sequential adapter required')
    active=r['id'];events=[]
   elif r['kind']=='EVENT':
    if r['id']!=active:raise ValueError('interleaved event')
    events.append(r['details']);peak=max(peak,len(events))
   elif r['kind']=='TERMINAL':
    if r['id']!=active:raise ValueError('interleaved terminal')
    if r['status']=='COMPLETED':summaries[active]=audit_episode(by_id[active],events,r['details'],meta)
    active=None;events=[]
  log=reader.summary()
 return {'study':STUDY,'ledger_state':log['state'],'counts':log['counts'],'metadata':meta,
  'assignments':[{'id':a['id'],'state':log['assignments'][a['id']],'summary':summaries.get(a['id'])} for a in assignments],
  'peak_buffered_episode_events':peak,'gate_b':'GATE_B_NOT_AUTHORIZED','limitations':[
   'Synthetic packets/error budgets and exact delay/ramp models lack independent physical calibration.',
   'Shared-channel ghost deception is an explicit negative control; consistency does not authenticate truth.',
   'Finite backup duration is assumed, not an electrical battery energy model.',
   'Contact states/geometry checked with native forward calculation; contact impulses/trajectories not independently reconstructed.',
   'Measured finite dwell is not an invariant terminal set or operational authorization.']}


def run(path):
 sources=hashes();meta={'sources':sources,'parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  'versions':{'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__},'gate_b':'GATE_B_NOT_AUTHORIZED'}
 assignments=[dict(a,metadata=meta) for a in plan()]
 with DevelopmentLedger.create(path,study=STUDY,assignments=assignments,record_events=True) as w:
  for a in assignments:
   w.start(a['id'])
   try:
    result=execute(a,lambda e:w.event(a['id'],details=e));after=hashes()
    if sources!=after:raise ValueError('sources changed')
    w.complete(a['id'],status='COMPLETED',details={'summary':result,'sources_after':after})
   except (LedgerError,LedgerWriteError):raise
   except Exception as exc:w.complete(a['id'],status='ERROR',details={'error_type':type(exc).__name__,'error':str(exc)});raise
  w.finalize()
 return audit(path)


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('ledger',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 if a.output.exists():p.error('output exists')
 result=run(a.ledger) if a.mode=='run' else audit(a.ledger)
 with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'state':result['ledger_state'],'counts':result['counts']}))
if __name__=='__main__':main()
