from fractions import Fraction
import math,random
import pytest
from aegis.development.recovery_contract import assess_recovery
from aegis.development.probe_window import brake_probe_window


def reference():return {'status':'CONDITIONAL_REFERENCE','position':[-2.,-2.,1.3],'velocity':[.5,0.,0.],'position_error_m':.005,'velocity_error_m_s':.01}
def geometry():return {'robot_radius':.2,'arena_limit':3.,'obstacles':[{'center':[0.,0.,.5],'radius':.45}]}
def config():return dict(pre_steps=6,dt_seconds=.02,probe_force_norm_upper_n=math.sqrt(3),mass_lower_kg=1.,mass_upper_kg=1.5,
 brake_gain_lower_kg_s=2.,brake_gain_upper_kg_s=2.,cap_lower_n=1.,disturbance_upper_n=0.,brake_available_asserted=True,
 terminal_speed_m_s=.05,dwell_steps=25,max_total_steps=300,max_energy_increase_j=.2,require_infinite_sampled_containment=True)
def assess(**kw):c=config();c.update(kw);return assess_recovery(reference(),geometry(),**c)


def test_composed_reference_requires_recovery_and_is_not_authorization():
 r=assess();assert r['design_status']=='WITHIN_ASSERTED_RECOVERY_DESIGN'
 assert r['required_total_steps']>6+25 and r['terminal_speed_bound_m_s']<=.05
 assert r['infinite_sampled_path_upper_m']<r['clearance_lower_m']
 assert r['operational_authorization'] is False and r['registered_criterion'] is False


def test_exact_rational_discrete_linear_case_and_infinite_tail():
 ref=reference();ref.update(velocity=[.5,0.,0.],velocity_error_m_s=0.)
 c=config();c.update(pre_steps=0,probe_force_norm_upper_n=0.,dwell_steps=0,max_energy_increase_j=0.)
 r=assess_recovery(ref,geometry(),**c)
 v=Fraction(1,2);q=Fraction(73,75);n=0;path=Fraction(0)
 while v>Fraction(1,20):v*=q;path+=Fraction(1,50)*v;n+=1
 assert r['recovery_steps']==n
 assert r['terminal_speed_bound_m_s']==pytest.approx(float(v),abs=1e-14)
 assert r['finite_sampled_path_upper_m']==pytest.approx(float(path),abs=1e-13)
 assert r['infinite_sampled_path_upper_m']==pytest.approx(.365)


def test_saturation_region_matches_exact_recurrence():
 ref=reference();ref.update(velocity=[1.2,0.,0.],velocity_error_m_s=0.)
 c=config();c.update(pre_steps=0,probe_force_norm_upper_n=0.,cap_lower_n=.5,dwell_steps=0,require_infinite_sampled_containment=False)
 r=assess_recovery(ref,geometry(),**c)
 v=1.2;n=0;path=0.
 while v>.05:
  v-=.02*min(2*v,.5)/1.5;path+=.02*v;n+=1
 assert r['recovery_steps']==n and r['finite_sampled_path_upper_m']==pytest.approx(path)


def test_short_window_can_fit_while_composed_recovery_does_not():
 ref=reference();ref['position'][0]=-2.69
 assert brake_probe_window(ref,geometry())['design_status']=='WITHIN_ASSERTED_SAMPLED_WINDOW'
 assert assess_recovery(ref,geometry(),**config())['design_status']=='DECLINED_COMPOSED_CLEARANCE'


@pytest.mark.parametrize('kw,status',[(dict(brake_available_asserted=False),'UNSUPPORTED_BRAKE_AVAILABILITY'),
 (dict(disturbance_upper_n=.1),'UNSUPPORTED_TERMINAL_AUTHORITY'),(dict(cap_lower_n=.05,disturbance_upper_n=.2),'UNSUPPORTED_TERMINAL_AUTHORITY'),
 (dict(disturbance_upper_n=.02),'UNSUPPORTED_INFINITE_CONTAINMENT_WITH_DISTURBANCE'),
 (dict(max_total_steps=5),'DECLINED_HORIZON_BUDGET'),(dict(max_energy_increase_j=.001),'DECLINED_ENERGY_BUDGET')])
def test_decline_or_unknown_is_explicit(kw,status):assert assess(**kw)['design_status']==status


def test_disturbance_can_allow_finite_band_without_infinite_position_claim():
 r=assess(disturbance_upper_n=.02,require_infinite_sampled_containment=False)
 assert r['design_status']=='WITHIN_ASSERTED_RECOVERY_DESIGN'
 assert r['infinite_sampled_path_upper_m'] is None and r['post_horizon_position_containment']=='UNSUPPORTED_PERSISTENT_DISTURBANCE'


@pytest.mark.parametrize('kw',[dict(terminal_speed_m_s=0.),dict(max_energy_increase_j=None),dict(dwell_steps=True),dict(mass_upper_kg=.5),
 dict(brake_gain_upper_kg_s=1.),dict(brake_gain_upper_kg_s=60.),dict(dt_seconds=1e-320),dict(pre_steps=-1)])
def test_unsupported_criteria_model_or_numeric_range_never_grants(kw):
 r=assess(**kw);assert r['design_status']=='UNSUPPORTED' and r['operational_authorization'] is False


def test_adversarial_sampled_dynamics_stay_below_the_composed_bounds():
 rng=random.Random(20261116)
 c=config();c.update(probe_force_norm_upper_n=.2,disturbance_upper_n=.02,require_infinite_sampled_containment=False,brake_gain_upper_kg_s=2.4)
 bound=assess_recovery(reference(),geometry(),**c);assert bound['design_status']=='WITHIN_ASSERTED_RECOVERY_DESIGN'
 for _ in range(100):
  mass=rng.uniform(1.,1.5);gain=rng.uniform(2.,2.4);cap=rng.uniform(1.,1.2)
  raw=[rng.uniform(-1,1) for _ in range(3)];norm=math.hypot(*raw);v=[.51*x/norm for x in raw];path=0.
  for k in range(bound['required_total_steps']):
   direction=[rng.uniform(-1,1) for _ in range(3)];norm=math.hypot(*direction)
   disturbance=[.02*x/norm for x in direction]
   if k<c['pre_steps']:
    active=[.2*x/norm for x in direction];brake=[0.,0.,0.]
   else:
    active=[0.,0.,0.];brake=[-max(-cap,min(cap,gain*x)) for x in v]
   v=[x+.02*(a+b+d)/mass for x,a,b,d in zip(v,active,brake,disturbance)];path+=.02*math.hypot(*v)
   if k>=c['pre_steps']+bound['recovery_steps']-1:assert math.hypot(*v)<=.05+1e-12
  assert path<=bound['finite_sampled_path_upper_m']+1e-12


def test_gain_step_boundary_is_supported_for_the_discrete_model_only():
 ref=reference();ref['velocity_error_m_s']=0.
 c=config();c.update(pre_steps=0,probe_force_norm_upper_n=0.,dt_seconds=.5,mass_upper_kg=1.,dwell_steps=0)
 r=assess_recovery(ref,geometry(),**c)
 assert r['recovery_steps']==1 and r['terminal_speed_bound_m_s']==0.


def test_finite_horizon_design_cannot_claim_an_uncontained_infinite_tail():
 ref=reference();ref.update(position=[-2.44,-2.,1.3],velocity_error_m_s=0.)
 c=config();c.update(pre_steps=0,probe_force_norm_upper_n=0.,dwell_steps=0,max_energy_increase_j=0.,require_infinite_sampled_containment=False)
 r=assess_recovery(ref,geometry(),**c)
 assert r['design_status']=='WITHIN_ASSERTED_RECOVERY_DESIGN'
 assert r['finite_sampled_path_upper_m']<r['clearance_lower_m']<r['infinite_sampled_path_upper_m']
 assert r['post_horizon_position_containment']=='NOT_ESTABLISHED_ZERO_DISTURBANCE_PATH_EXCEEDS_CLEARANCE'
 c['require_infinite_sampled_containment']=True
 assert assess_recovery(ref,geometry(),**c)['design_status']=='DECLINED_COMPOSED_CLEARANCE'
