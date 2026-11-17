from fractions import Fraction as Q
import copy,random
import pytest
from aegis.development.recovery_envelope_1d import assess
from aegis.development.recovery_envelope_state_1d import assess_state


def model():
 return {'dt':'.02','position':['0','0'],'velocity':['.5','.5'],'mass':['1','1'],'gain':['2','2'],'cap':['1','1'],'slew':['4','4'],
  'disturbance':'0','measurement_error':'0','delay_ticks':[3,3],'power_cut_ticks':[160,160],'horizon':140,
  'safe_position':['-.5','.32'],'terminal_velocity':['-.05','.05'],'terminal_samples':25}
def state(force=('0','0'),pending=None):
 return {'mode':'EXPLICIT_INTERVALS','assessment_tick':50,'state_bounds_tick':50,'actuator_bounds_tick':50,
  'force':list(force),'pending_by_delay':{'3':pending if pending is not None else [['0','0']]*3}}
def flags():return dict(evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS',measurement_bounds_asserted=True,actuator_model_asserted=True,power_bounds_asserted=True,actuator_state_bounds_asserted=True)
def run(m=None,s=None,**kw):f=flags();f.update(kw);return assess_state(model() if m is None else m,state() if s is None else s,**f)
def trajectory(m,force,pending,*,delay=3,cut=160,v=Q('.5'),p=Q(0),mass=Q(1),rate=Q(4),errors=None,disturbances=None):
 dt=Q(m['dt']);g=Q(m['gain'][0]);cap=Q(m['cap'][0]);q=list(pending);rows=[(p,v,force,list(q))]
 for k in range(m['horizon']):
  if k<cut:
   e=Q(0) if errors is None else errors[k];q.append(max(-cap,min(cap,-g*(v+e))));due=q.pop(0)
   force+=max(-rate*dt,min(rate*dt,due-force))
  else:force=Q(0);q=[Q(0)]*delay
  w=Q(0) if disturbances is None else disturbances[k]
  v+=dt*(force+w)/mass;p+=dt*v;rows.append((p,v,force,list(q)))
 return rows


def test_zero_state_preserves_original_reset_enclosure():
 m=model();old_flags=flags();old_flags.pop('actuator_state_bounds_asserted');old=assess(m,**old_flags);new=run(m)
 assert new['model_status']==old['model_status']
 for a,b in zip(old['branches'][0]['history'],new['branches'][0]['history']):
  assert all(a[k]==b[k] for k in ('position','velocity','force'))


def test_nonzero_force_and_pending_acceleration_cannot_be_reset_to_zero():
 s=state(('.8','.8'),[['.8','.8']]*3);r=run(s=s);reset=run()
 assert reset['finite_horizon_containment'] and reset['terminal_sample_condition']
 assert r['finite_horizon_containment'] is False
 truth=trajectory(model(),Q('.8'),[Q('.8')]*3)
 assert truth[-1][0]>Q('.32')
 for row,(p,v,f,pending) in zip(r['branches'][0]['history'],truth):
  assert list(map(Q,row['position']))==[p,p] and list(map(Q,row['velocity']))==[v,v]
  assert list(map(Q,row['force']))==[f,f]
  assert row['pending_targets']==[[str(x),str(x)] for x in pending]
 assert r['operational_authorization'] is False


def test_initial_pending_request_is_not_linked_to_current_velocity():
 s=state(('0','0'),[['1','1'],['-1','-1'],['.4','.4']]);m=model();m.update(horizon=15,terminal_samples=2)
 r=run(m,s);truth=trajectory(m,Q(0),[Q(1),Q(-1),Q('.4')])
 for row,values in zip(r['branches'][0]['history'],truth):
  for key,value in zip(('position','velocity','force'),values):assert list(map(Q,row[key]))==[value,value]


@pytest.mark.parametrize('field,value',[('state_bounds_tick',49),('actuator_bounds_tick',49),('assessment_tick',True)])
def test_misaligned_or_invalid_epochs_are_unknown(field,value):
 s=state();s[field]=value;r=run(s=s)
 assert r['conclusion']=='UNKNOWN_INPUT' and not r['operational_authorization']
 assert r['finite_horizon_containment'] is None


@pytest.mark.parametrize('change',['missing_delay','extra_delay','wrong_length','outside_force','outside_pending','wrong_mode','implicit_unknown'])
def test_bad_state_does_not_get_implicit_zero_defaults(change):
 s=state()
 if change=='missing_delay':s['pending_by_delay']={}
 if change=='extra_delay':s['pending_by_delay']['2']=[['0','0']]*2
 if change=='wrong_length':s['pending_by_delay']['3']=[]
 if change=='outside_force':s['force']=['-2','2']
 if change=='outside_pending':s['pending_by_delay']['3'][0]=['2','2']
 if change=='wrong_mode':s['mode']='RESET_ASSUMED'
 if change=='implicit_unknown':s['force']=None
 r=run(s=s);assert r['conclusion']=='UNKNOWN_INPUT'


def test_full_cap_uncertainty_is_explicit_and_contains_pending_force_witnesses():
 m=model();m.update(horizon=30,terminal_samples=5,delay_ticks=[1,3],safe_position=['-2','2'])
 s=state();s.update(mode='FULL_CAP_UNCERTAINTY',force=None,pending_by_delay=None)
 r=run(m,s);assert len(r['branches'])==3
 rng=random.Random(20261116)
 for branch in r['branches']:
  d=branch['delay']
  for _ in range(12):
   f=Q(rng.randint(-10,10),10);q=[Q(rng.randint(-10,10),10) for _ in range(d)]
   truth=trajectory(m,f,q,delay=d)
   for row,values in zip(branch['history'],truth):
    for key,value in zip(('position','velocity','force'),values):
     lo,hi=map(Q,row[key]);assert lo<=value<=hi
 assert r['snapshot_mode']=='FULL_CAP_UNCERTAINTY'
 assert not r['operational_authorization']


def test_unknown_state_assertion_blocks_positive_combined_conclusion():
 r=run(actuator_state_bounds_asserted=False)
 assert r['finite_horizon_containment'] is True and r['conclusion']=='UNKNOWN_PHYSICAL_PREMISES'
 assert r['future_position_containment']=='NOT_ESTABLISHED'


def test_power_cut_bounds_are_remaining_ticks_from_assessment_epoch():
 m=model();m.update(power_cut_ticks=[0,0]);s=state(('.8','.8'),[['.8','.8']]*3)
 r=run(m,s);hist=r['branches'][0]['history']
 assert hist[0]['force']==['4/5','4/5'] and hist[1]['force']==['0','0']
 assert hist[1]['pending_targets']==[['0','0']]*3
 assert r['power_timing']=='CUT_TICKS_RELATIVE_TO_ASSESSMENT_EPOCH'
 assert r['terminal_sample_condition'] is False


def test_interval_uncertainties_with_nonzero_state_enclose_exact_rational_samples():
 m=model();m.update(mass=['1','1.3'],slew=['3','5'],velocity=['.49','.51'],measurement_error='.005',disturbance='.01',horizon=45,terminal_samples=5,power_cut_ticks=[25,27])
 s=state(('.4','.8'),[['.5','.9'],['-.3','.2'],['-.8','-.2']]);r=run(m,s);rng=random.Random(41)
 for b in r['branches']:
  for _ in range(15):
   mass=Q(rng.randint(100,130),100);rate=Q(rng.randint(300,500),100);f=Q(rng.randint(40,80),100)
   q=[Q(rng.randint(50,90),100),Q(rng.randint(-30,20),100),Q(rng.randint(-80,-20),100)]
   errors=[Q(rng.randint(-5,5),1000) for k in range(45)];w=[Q(rng.randint(-10,10),1000) for k in range(45)]
   truth=trajectory(m,f,q,cut=b['remaining_power_cut_tick'],mass=mass,rate=rate,v=Q(rng.randint(490,510),1000),errors=errors,disturbances=w)
   for row,values in zip(b['history'],truth):
    for key,value in zip(('position','velocity','force'),values):
     lo,hi=map(Q,row[key]);assert lo<=value<=hi


def test_remaining_power_translation_does_not_restart_an_expired_budget():
 from aegis.development.recovery_envelope_state_1d import remaining_cut_window
 assert remaining_cut_window([80,85],100)==[0,0]
 assert remaining_cut_window([80,85],50)==[30,35]
 assert remaining_cut_window([80,85],82)==[0,3]


@pytest.mark.parametrize('window,epoch',[([80,85],True),([85,80],50),([-1,85],50),([80],50),([80,False],50)])
def test_bad_deadline_translation_is_rejected(window,epoch):
 from aegis.development.recovery_envelope_state_1d import remaining_cut_window
 with pytest.raises(ValueError):remaining_cut_window(window,epoch)
