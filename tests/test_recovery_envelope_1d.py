from fractions import Fraction as Q
from itertools import product
import copy,random
import pytest
from aegis.development.recovery_envelope_1d import Interval,assess,spec,branch,linked_velocity,internal,point


def config():
 return {'dt':'0.02','position':['0','0'],'velocity':['0.49','0.51'],'mass':['1','1.5'],'gain':['2','2'],
  'cap':['1','1'],'slew':['3','5'],'disturbance':'0.01','measurement_error':'0.005','delay_ticks':[2,4],
  'power_cut_ticks':[160,160],'horizon':140,'safe_position':['-0.5','1.5'],'terminal_velocity':['-0.05','0.05'],'terminal_samples':25}
def run(raw=None,**flags):
 args=dict(evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS',measurement_bounds_asserted=True,actuator_model_asserted=True,power_bounds_asserted=True)
 args.update(flags);return assess(config() if raw is None else raw,**args)
def exact_trajectory(raw,*,mass,gain,cap,rate,delay,cut,p,v,errors,disturbances):
 h=Q(raw['dt']);f=Q(0);queue=[Q(0)]*delay;records=[(p,v,f)]
 for k in range(raw['horizon']):
  if k<cut:
   request=max(-cap,min(cap,-gain*(v+errors[k])));queue.append(request);due=queue.pop(0)
   f+=max(-rate*h,min(rate*h,due-f))
  else:f=Q(0);queue=[Q(0)]*delay
  v+=h*(f+disturbances[k])/mass;p+=h*v;records.append((p,v,f))
 return records


def test_fixed_point_model_equals_independent_exact_trajectory():
 c=config();c.update(velocity=['0.5','0.5'],mass=['1','1'],slew=['4','4'],disturbance='0',measurement_error='0',delay_ticks=[3,3],power_cut_ticks=[70,70],horizon=90)
 r=run(c);assert r['model_status']!='UNSUPPORTED_INPUT_OR_MODEL'
 truth=exact_trajectory(c,mass=Q(1),gain=Q(2),cap=Q(1),rate=Q(4),delay=3,cut=70,p=Q(0),v=Q('0.5'),errors=[Q(0)]*90,disturbances=[Q(0)]*90)
 for row,(p,v,f) in zip(r['branches'][0]['history'],truth):
  assert list(map(Q,row['position']))==[p,p]
  assert list(map(Q,row['velocity']))==[v,v]
  assert list(map(Q,row['force']))==[f,f]
 assert r['operational_authorization'] is False and r['future_position_containment']=='NOT_ESTABLISHED'


def test_zero_delay_known_gain_retains_feedback_contraction():
 c=config();c.update(delay_ticks=[0,0],mass=['1','1'],slew=['1000','1000'],disturbance='0',measurement_error='0',horizon=40)
 s=spec(c);linked=branch(s,0,40,linked=True);naive=branch(s,0,40,linked=False)
 lo,hi=map(Q,linked['history'][-1]['velocity']);nlo,nhi=map(Q,naive['history'][-1]['velocity'])
 assert hi-lo<Q('0.02') and nhi-nlo>Q('0.02')
 # Exact unconstrained P trajectory from each endpoint lies in the linked tube.
 for v in (Q('.49'),Q('.51')):
  for row in linked['history']:
   low,high=map(Q,row['velocity']);assert low<=v<=high
   v+=Q('.02')*max(-Q(1),min(Q(1),-2*v))


def test_enumerates_delay_and_cut_static_uncertainty_once_per_branch():
 c=config();c.update(delay_ticks=[1,3],power_cut_ticks=[20,22],horizon=30)
 r=run(c);assert {(b['delay'],b['power_cut']) for b in r['branches']}==set(product(range(1,4),range(20,23)))
 assert all(len(b['history'])==31 for b in r['branches'])


def test_random_exact_rational_parameter_and_error_trajectories_are_enclosed():
 c=config();c.update(horizon=70,power_cut_ticks=[40,42],terminal_samples=10,gain=['1.5','2.5'],cap=['0.8','1.2'])
 r=run(c);assert r['model_status']!='UNSUPPORTED_INPUT_OR_MODEL';by={(b['delay'],b['power_cut']):b for b in r['branches']}
 rng=random.Random(20261116)
 for _ in range(60):
  d=rng.randint(2,4);cut=rng.randint(40,42)
  mass=Q(rng.randint(100,150),100);gain=Q(rng.randint(150,250),100);cap=Q(rng.randint(80,120),100);rate=Q(rng.randint(300,500),100)
  errors=[Q(rng.randint(-5,5),1000) for k in range(70)];disturbances=[Q(rng.randint(-10,10),1000) for k in range(70)]
  true=exact_trajectory(c,mass=mass,gain=gain,cap=cap,rate=rate,delay=d,cut=cut,p=Q(0),v=Q(rng.randint(490,510),1000),errors=errors,disturbances=disturbances)
  for row,values in zip(by[(d,cut)]['history'],true):
   for key,value in zip(('position','velocity','force'),values):
    lo,hi=map(Q,row[key]);assert lo<=value<=hi,(key,d,cut,row['tick'])


def test_linked_update_contains_dense_corners_including_velocity_sign_changes():
 rng=random.Random(77);dt=Q('.02')
 for _ in range(60):
  vlo=Q(rng.randint(-80,40),100);v=internal(vlo,vlo+Q('.3'));f=internal(Q('-.8'),Q('.9'));lag=internal(Q('-.2'),Q('.2'))
  e=Q('.01');gain=internal(Q(1),Q(3));rate=internal(Q(1),Q(8));cap=internal(Q('.5'),Q('1.2'));mass=internal(Q('.8'),Q('1.5'));due=internal(Q(-1),Q(1));dist=Q('.03')
  out=linked_velocity(v,f,due,lag,e,gain,rate,cap,mass,dist,dt)
  for j in range(40):
   frac=lambda lo,hi:lo+(hi-lo)*Q(rng.randint(0,10),10)
   vv=frac(v.lo,v.hi);ff=frac(f.lo,f.hi);ll=frac(lag.lo,lag.hi);ee=frac(-e,e);g=frac(gain.lo,gain.hi);rr=frac(rate.lo,rate.hi);cc=frac(cap.lo,cap.hi);mm=frac(mass.lo,mass.hi);dd=frac(-dist,dist)
   target=max(due.lo,min(due.hi,max(-cc,min(cc,-g*(vv-ll+ee)))))
   force=ff+max(-rr*dt,min(rr*dt,target-ff));next_v=vv+dt*(force+dd)/mm
   assert out.lo<=next_v<=out.hi


@pytest.mark.parametrize('kw,expected',[(dict(evidence_status='UNKNOWN'),'UNKNOWN_EVIDENCE'),(dict(evidence_status='CONTRADICTORY'),'CONTRADICTORY_EVIDENCE'),(dict(measurement_bounds_asserted=False),'UNKNOWN_PHYSICAL_PREMISES'),(dict(power_bounds_asserted=False),'UNKNOWN_PHYSICAL_PREMISES')])
def test_evidence_and_model_feasibility_remain_separate(kw,expected):
 c=config();c.update(horizon=30,terminal_samples=1)
 r=run(c,**kw);assert r['conclusion']==expected and r['operational_authorization'] is False
 assert r['finite_horizon_containment'] is not None


@pytest.mark.parametrize('kw',[{'dt':.02},{'delay_ticks':[True,3]},{'delay_ticks':[0,17]},{'power_cut_ticks':[40,20]},
 {'horizon':0},{'terminal_samples':141},{'mass':['0','1']},{'gain':['2','100']},{'position':['1','0']},
 {'measurement_error':'-1'},{'delay_ticks':[0,16],'power_cut_ticks':[0,20]}])
def test_unsupported_input_cannot_produce_a_positive_statement(kw):
 c=config();c.update(kw);r=run(c)
 assert r['conclusion']=='UNKNOWN_INPUT' and r['model_status']=='UNSUPPORTED_INPUT_OR_MODEL'
 assert r['operational_authorization'] is False


def test_failed_enclosure_is_not_labeled_physical_impossibility():
 c=config();c.update(safe_position=['-0.01','0.01'],horizon=20,terminal_samples=1)
 r=run(c);assert not r['finite_horizon_containment']
 assert r['conclusion']=='NOT_ESTABLISHED_BY_THIS_ENCLOSURE' and 'IMPOSSIBLE' not in r['model_status']


def test_zero_power_and_nonzero_velocity_cannot_claim_future_rest():
 c=config();c.update(delay_ticks=[0,0],power_cut_ticks=[0,0],velocity=['.5','.5'],mass=['1','1'],disturbance='0',measurement_error='0',horizon=50,terminal_samples=5)
 r=run(c);assert r['finite_horizon_containment'] is True and r['terminal_sample_condition'] is False
 assert r['branches'][0]['history'][-1]['position']==['1/2','1/2']
 assert r['future_position_containment']=='NOT_ESTABLISHED'


def test_parameter_partition_covers_whole_input_box_and_keeps_failed_cells():
 from aegis.development.recovery_envelope_1d import assess_partitioned
 c=config();c.update(horizon=50,terminal_samples=5)
 flags=dict(evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS',measurement_bounds_asserted=True,actuator_model_asserted=True,power_bounds_asserted=True)
 r=assess_partitioned(c,partitions={'mass':2,'slew':2},**flags)
 assert len(r['models'])==4 and r['analysis_branch_count']==12
 assert {tuple(x['parameter_box']['mass']) for x in r['models']}=={('1','5/4'),('5/4','3/2')}
 assert {tuple(x['parameter_box']['slew']) for x in r['models']}=={('3','4'),('4','5')}
 assert r['terminal_sample_condition']==all(x['assessment']['terminal_sample_condition'] for x in r['models'])
 assert r['cells_with_terminal_condition']<4  # No selecting only favorable cells.
 assert r['conclusion']!='SUPPORTED_FINITE_MODEL_STATEMENT_ONLY'
 assert r['operational_authorization'] is False


@pytest.mark.parametrize('parts,budget',[({'mass':0},256),({'mass':True},256),({'velocity':2},256),({'mass':16,'slew':16},128),({'mass':2},False)])
def test_invalid_or_over_budget_partition_cannot_grant_support(parts,budget):
 from aegis.development.recovery_envelope_1d import assess_partitioned
 flags=dict(evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS',measurement_bounds_asserted=True,actuator_model_asserted=True,power_bounds_asserted=True)
 r=assess_partitioned(config(),partitions=parts,max_total_branches=budget,**flags)
 assert r['model_status']=='UNSUPPORTED_INPUT_OR_MODEL' and r['conclusion']=='UNKNOWN_INPUT'
 assert r['operational_authorization'] is False
