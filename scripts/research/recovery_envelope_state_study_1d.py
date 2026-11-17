"""State-aware 1D development analysis; no online/production admission."""
import argparse,copy,gzip,hashlib,json,os,platform,subprocess
from collections import deque
from fractions import Fraction as Q
from pathlib import Path
import numpy as np
import mujoco
from aegis.development.recovery_envelope_state_1d import assess_state,remaining_cut_window
from aegis.development.recovery_envelope_1d import assess
from aegis.development.dynamic_braking import DelayedSlewBrake
from aegis.env.mujoco_power_brake import PowerBrakeEnvironment
from scripts.research import recovery_envelope_study_1d as previous
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError
from scripts.research.streaming_ledger import LedgerStream
ROOT=Path(__file__).resolve().parents[2]
STUDY='V9-M5 state-aware 1D recovery development v1'
FILES=previous.FILES+('src/aegis/development/recovery_envelope_state_1d.py','scripts/research/recovery_envelope_state_study_1d.py')
FLAGS={'evidence_status':'COMPATIBLE_UNDER_ASSERTED_BOUNDS','measurement_bounds_asserted':True,'actuator_model_asserted':True,'power_bounds_asserted':True,'actuator_state_bounds_asserted':True}


def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
def base():
 return {'dt':'.02','position':['0','0'],'velocity':['.5','.5'],'mass':['1','1'],'gain':['2','2'],'cap':['1','1'],'slew':['4','4'],
  'disturbance':'0','measurement_error':'0','delay_ticks':[3,3],'power_cut_ticks':[160,160],'horizon':140,
  'safe_position':['-.5','.32'],'terminal_velocity':['-.05','.05'],'terminal_samples':25}
def state(force='0',queue=None):
 return {'mode':'EXPLICIT_INTERVALS','assessment_tick':50,'state_bounds_tick':50,'actuator_bounds_tick':50,
  'force':[force,force],'pending_by_delay':{'3':[[x,x] for x in (['0']*3 if queue is None else queue)]}}
def plan():
 out=[]
 def add(name,s=None,native=False):out.append({'id':name,'model':base(),'snapshot':state() if s is None else s,'flags':dict(FLAGS),'native':native,'absolute_cut_window':None})
 add('zero_actuator_state',native=True)
 add('pending_acceleration',state('.8',['.8']*3),True)
 add('pending_braking',state('-.8',['-.8']*3),True)
 add('mixed_pending_order',state('.4',['.8','-.8','.4']),True)
 add('full_cap_unknown_values');out[-1]['snapshot'].update(mode='FULL_CAP_UNCERTAINTY',force=None,pending_by_delay=None)
 add('power_already_absent',state('.8',['.8']*3),True);out[-1]['model']['power_cut_ticks']=[0,0]
 add('power_cut_window',state('-.8',['-.8']*3));out[-1]['model']['power_cut_ticks']=[20,22]
 add('stale_state_bounds');out[-1]['snapshot']['state_bounds_tick']=49
 add('stale_actuator_bounds');out[-1]['snapshot']['actuator_bounds_tick']=49
 add('unasserted_actuator_state');out[-1]['flags']['actuator_state_bounds_asserted']=False
 add('unknown_measurement_evidence');out[-1]['flags']['evidence_status']='UNKNOWN'
 add('missing_pending_records');out[-1]['snapshot']['pending_by_delay']={}
 add('expired_absolute_power_window',native=True)
 out[-1]['snapshot'].update(assessment_tick=100,state_bounds_tick=100,actuator_bounds_tick=100)
 out[-1]['absolute_cut_window']=[80,85];out[-1]['model']['power_cut_ticks']=remaining_cut_window([80,85],100)
 out[-1]['model']['safe_position']=['-.5','.5']
 return out


def exact_point(a):
 m=a['model'];s=a['snapshot'];p,v=Q(m['position'][0]),Q(m['velocity'][0]);mass,gain,cap,rate=[Q(m[k][0]) for k in ('mass','gain','cap','slew')]
 delay,cut=m['delay_ticks'][0],m['power_cut_ticks'][0];dt=Q(m['dt']);force=Q(s['force'][0]);queue=[Q(x[0]) for x in s['pending_by_delay'][str(delay)]];rows=[]
 for k in range(m['horizon']):
  if k<cut:
   queue.append(max(-cap,min(cap,-gain*v)));due=queue.pop(0);force+=max(-rate*dt,min(rate*dt,due-force))
  else:force=Q(0);queue=[Q(0)]*delay
  v+=dt*force/mass;p+=dt*v;rows.append({'tick':k,'position':str(p),'velocity':str(v),'force':str(force),'pending_targets':[str(x) for x in queue]})
 return rows


def native_point(a,saved=None,emit=None):
 model=a['model'];initial=a['snapshot'];epoch=initial['assessment_tick']
 # Only declared point cases, 1 kg, zero disturbance/error, powered support.
 assert all(model[k][0]==model[k][1] for k in ('position','velocity','mass','gain','cap','slew'))
 assert Q(model['mass'][0])==1 and Q(model['disturbance'])==0 and Q(model['measurement_error'])==0
 delay=model['delay_ticks'][0];cut=model['power_cut_ticks'][0];dt=float(Q(model['dt']));gain=float(Q(model['gain'][0]));cap=float(Q(model['cap'][0]));rate=float(Q(model['slew'][0]))
 env=PowerBrakeEnvironment(brake_cap_per_axis_n=cap);env.reset_development(float(Q(model['velocity'][0])))
 actuator=DelayedSlewBrake(delay_ticks=delay,slew_n_s=rate,cap_n=cap,dt_seconds=dt)
 actuator.force=(float(Q(initial['force'][0])),0.,0.)
 actuator.pending=deque([(float(Q(x[0])),0.,0.) for x in initial['pending_by_delay'][str(delay)]])
 actuator.tick=epoch
 runtime=env.runtime_record();frames=[];exact=exact_point(a);maxp=maxv=maxf=0.
 if runtime['dt']!=dt:raise ValueError('native fixture timestep mismatch')
 if saved is not None and (not isinstance(saved,dict) or saved.get('runtime')!=runtime or not isinstance(saved.get('frames'),list) or len(saved['frames'])!=model['horizon']):raise ValueError('native runtime/frame mismatch')
 pos=np.array([-2.,-2.,1.3]);vel=np.array([float(Q(model['velocity'][0])),0.,0.])
 for k in range(model['horizon']):
  measurement={'velocity_m_s':float(vel[0]),'error_m_s':0.,'source':'IDEAL_SYNTHETIC_VELOCITY_SENSOR'}
  force=actuator.step([-gain*measurement['velocity_m_s'],0.,0.],tick=epoch+k,powered=k<cut)
  if saved is not None:
   env.data.qpos[:]=pos;env.data.qvel[:]=vel
  pre=env.prepare_powered_force(force,brake_powered=k<cut,gravity_powered=True,disturbance=[0.,0.,0.])
  if saved is None:
   if emit:emit({'phase':'NATIVE_TICK_INTENT','tick':k,'position_before':pos.tolist(),'velocity_before':vel.tolist(),'measurement':measurement,'plant':pre})
   physical=env.advance_prepared()
   if emit:emit({'phase':'NATIVE_PHYSICS','tick':k,'physical':physical})
  else:
   row=saved['frames'][k]
   if row['tick']!=k or row['plant']!=pre or row['measurement']!=measurement:raise ValueError('native force/measurement intent mismatch')
   physical=row['physical']
   vn=vel+dt*np.array(pre['actuator_force_pre_n']);pn=pos+dt*vn
   if not np.allclose(physical['position'],pn,atol=1e-10,rtol=0) or not np.allclose(physical['velocity'],vn,atol=1e-10,rtol=0):raise ValueError('native free-motion mismatch')
   env.data.qpos[:]=physical['position'];env.data.qvel[:]=physical['velocity'];mujoco.mj_forward(env.model,env.data);state=env.get_state()
   for key in ('contact_floor','contact_obstacle'):
    if physical[key]!=bool(state[key]):raise ValueError('native contact-state mismatch')
   if physical['geometric_or_contact_violation']!=bool(state['safety_violation']):raise ValueError('native geometry-state mismatch')
   for key in ('boundary_clearance','min_obstacle_distance'):
    if abs(physical[key]-state[key])>1e-10:raise ValueError('native clearance mismatch')
  if physical['contact_floor'] or physical['contact_obstacle'] or physical['geometric_or_contact_violation']:raise ValueError('unexpected contact invalidates this 1D corroboration')
  if physical['integrated_qpos']!=physical['position'] or abs(physical['time']-(k+1)*dt)>1e-10:raise ValueError('native phase/time mismatch')
  frame={'tick':k,'plant':pre,'measurement':measurement,'physical':physical};frames.append(frame)
  maxp=max(maxp,abs((physical['position'][0]+2)-float(Q(exact[k]['position']))))
  maxv=max(maxv,abs(physical['velocity'][0]-float(Q(exact[k]['velocity']))))
  maxf=max(maxf,abs(pre['actuator_force_pre_n'][0]-float(Q(exact[k]['force']))))
  pos,vel=np.array(physical['position']),np.array(physical['velocity'])
 if max(maxp,maxv,maxf)>1e-10:raise ValueError('native/rational discrepancy exceeds descriptive comparison tolerance')
 result={'runtime':runtime,'frames':frames,'max_absolute_position_error_m':maxp,'max_absolute_velocity_error_m_s':maxv,'max_absolute_force_error_n':maxf,
  'comparison_tolerance':'1e-10_NUMERICAL_CHECK_NOT_PHYSICAL_ERROR_BUDGET','classification':'SYNTHETIC_STATE_SEEDED_NATIVE_CORROBORATION_NOT_CERTIFICATE','state_seed':initial}
 if saved is not None and result!=saved:raise ValueError('native comparison summary mismatch')
 return result


def run_case(a,saved_native=None,*,audit_mode=False,emit=None):
 if audit_mode and a['native'] and saved_native is None:raise ValueError('native evidence unavailable; audit never integrates')
 analysis=assess_state(a['model'],a['snapshot'],**a['flags'])
 flags={k:v for k,v in a['flags'].items() if k!='actuator_state_bounds_asserted'}
 reset_reference=assess(a['model'],**flags)
 witness=exact_point(a) if a['native'] else None
 native=native_point(a,saved_native,emit) if a['native'] else None
 wrong_budget=None
 if a['absolute_cut_window'] is not None:
  wrong=copy.deepcopy(a['model']);wrong['power_cut_ticks']=a['absolute_cut_window']
  wrong_budget=assess(wrong,**flags)
 return {'analysis':analysis,'reset_reference':reset_reference,'misused_absolute_budget_reference':wrong_budget,
  'point_witness':witness,'native':native,'allowed_position':a['model']['safe_position'],
  'assessment_epoch':a['snapshot']['assessment_tick'],'criteria_origin':'SYNTHETIC_DEVELOPMENT_NOT_OPERATIONAL_REQUIREMENTS'}


def summary(result):
 r=result['analysis'];reference=result['reset_reference'];w=result['point_witness']
 return {'model_status':r['model_status'],'conclusion':r['conclusion'],'finite_horizon_containment':r['finite_horizon_containment'],
  'terminal_sample_condition':r['terminal_sample_condition'],'stateful_analysis_branches':len(r['branches']),
  'reset_reference_containment':reference['finite_horizon_containment'],'reset_reference_terminal_samples':reference['terminal_sample_condition'],
  'point_witness_crosses_bound':None if w is None else any(not Q(result['allowed_position'][0])<=Q(x['position'])<=Q(result['allowed_position'][1]) for x in w),
  'native_physics_steps':len(result['native']['frames']) if result['native'] is not None else 0,
  'misused_absolute_budget_containment':None if result['misused_absolute_budget_reference'] is None else result['misused_absolute_budget_reference']['finite_horizon_containment'],
  'misused_absolute_budget_terminal':None if result['misused_absolute_budget_reference'] is None else result['misused_absolute_budget_reference']['terminal_sample_condition'],
  'future_position_containment':'NOT_ESTABLISHED','operational_authorization':False}


def chunks(result):
 for text in json.JSONEncoder(sort_keys=True,separators=(',',':'),allow_nan=False).iterencode(result):yield text.encode('ascii')
def digest(result):
 h=hashlib.sha256()
 for b in chunks(result):h.update(b)
 return h.hexdigest()
def write_output(path,result):
 h=hashlib.sha256()
 with path.open('xb') as f:
  with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as g:
   for b in chunks(result):g.write(b);h.update(b)
  f.flush();os.fsync(f.fileno())
 return h.hexdigest()


def run(directory):
 directory=Path(directory);directory.mkdir(exist_ok=False);sources=hashes()
 meta={'sources':sources,'parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  'versions':{'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__},'gate_b':'GATE_B_NOT_AUTHORIZED'}
 assignments=[dict(a,metadata=meta) for a in plan()]
 with DevelopmentLedger.create(directory/'assignments.jsonl',study=STUDY,assignments=assignments,record_events=True) as w:
  for a in assignments:
   w.start(a['id']);w.event(a['id'],details={'phase':'ANALYSIS_INTENT','criteria_origin':'EXPLICIT_SYNTHETIC_DEVELOPMENT_NOT_APPROVED_OPERATIONAL_CRITERIA'})
   try:
    result=run_case(a,emit=lambda e:w.event(a['id'],details=e));path=directory/(a['id']+'.json.gz');raw_sha=write_output(path,result)
    if hashes()!=sources:raise ValueError('sources changed')
    w.complete(a['id'],status='COMPLETED',details={'output_file':path.name,'compressed_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'canonical_raw_sha256':raw_sha,'summary':summary(result),'sources_after':hashes()})
   except (LedgerError,LedgerWriteError):raise
   except Exception as exc:w.complete(a['id'],status='ERROR',details={'error_type':type(exc).__name__,'error':str(exc)});raise
  w.finalize()
 return audit(directory)


def audit(directory):
 directory=Path(directory);rows={};active=None;events=[]
 with LedgerStream(directory/'assignments.jsonl') as reader:
  for r in reader:
   if r['kind']=='HEADER':
    assignments=r['assignments'];meta=assignments[0]['metadata'];by={a['id']:a for a in assignments}
    if r['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan() or any(a['metadata']!=meta for a in assignments):raise ValueError('study/plan mismatch')
    if hashes()!=meta['sources']:raise ValueError('audit source identity differs; use the recorded source snapshot')
    if meta['versions']!={'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__}:raise ValueError('audit runtime versions differ')
   elif r['kind']=='START':
    if active is not None:raise ValueError('sequential analysis assignments required')
    active=r['id'];events=[]
   elif r['kind']=='EVENT':
    if r['id']!=active:raise ValueError('analysis event order')
    if not events and r['details']!={'phase':'ANALYSIS_INTENT','criteria_origin':'EXPLICIT_SYNTHETIC_DEVELOPMENT_NOT_APPROVED_OPERATIONAL_CRITERIA'}:raise ValueError('analysis intent mismatch')
    events.append(r['details'])
   elif r['kind']=='TERMINAL' and r['status']=='ERROR':
    if r['id']!=active:raise ValueError('terminal order')
    active=None
   elif r['kind']=='TERMINAL' and r['status']=='COMPLETED':
    if r['id']!=active or not events:raise ValueError('completed analysis lacks matching intent')
    active=None
    a=by[r['id']];d=r['details'];expected=a['id']+'.json.gz';path=directory/expected
    if d['output_file']!=expected or path.is_symlink() or path.resolve().parent!=directory.resolve():raise ValueError('invalid output path')
    if d['sources_after']!=meta['sources'] or hashlib.sha256(path.read_bytes()).hexdigest()!=d['compressed_sha256']:raise ValueError('source/output mismatch')
    with gzip.open(path,'rb') as f:raw=hashlib.file_digest(f,'sha256').hexdigest()
    if raw!=d['canonical_raw_sha256']:raise ValueError('raw output hash mismatch')
    saved_native=None
    if a['native']:
     with gzip.open(path,'rt') as f:saved_native=json.load(f)['native']
    expected_events=[{'phase':'ANALYSIS_INTENT','criteria_origin':'EXPLICIT_SYNTHETIC_DEVELOPMENT_NOT_APPROVED_OPERATIONAL_CRITERIA'}]
    if a['native']:
     if not isinstance(saved_native,dict):raise ValueError('native evidence unavailable')
     pos=[-2.,-2.,1.3];vel=[float(Q(a['model']['velocity'][0])),0.,0.]
     for frame in saved_native['frames']:
      expected_events.extend([{'phase':'NATIVE_TICK_INTENT','tick':frame['tick'],'position_before':pos,'velocity_before':vel,'measurement':frame['measurement'],'plant':frame['plant']},
       {'phase':'NATIVE_PHYSICS','tick':frame['tick'],'physical':frame['physical']}])
      pos=frame['physical']['position'];vel=frame['physical']['velocity']
    if events!=expected_events:raise ValueError('durable intent/physics events mismatch')
    rebuilt=run_case(a,saved_native,audit_mode=True)
    if digest(rebuilt)!=raw or summary(rebuilt)!=d['summary']:raise ValueError('recomputed output/summary mismatch')
    rows[a['id']]=d['summary']
  log=reader.summary()
 return {'study':STUDY,'ledger_state':log['state'],'counts':log['counts'],'metadata':meta,
  'assignments':[{'id':a['id'],'state':log['assignments'][a['id']],'summary':rows.get(a['id'])} for a in assignments],
  'classification':'STATEFUL_DEVELOPMENT_DESIGNS_NOT_INDEPENDENT_TRIALS','gate_b':'GATE_B_NOT_AUTHORIZED',
  'limitations':['Declared 1D static-parameter model and coherent state/actuator bounds at the assessment epoch only.','No invariant terminal set, continuous-time/hardware or production authorization claim.',
  'Exact rational arithmetic is not formal verification of this implementation.','Native point fixtures use the same existing runtime; no independent wheel or physical calibration.']}


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('output exists')
 r=run(a.directory) if a.mode=='run' else audit(a.directory)
 with a.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'state':r['ledger_state'],'counts':r['counts']}))
if __name__=='__main__':main()
