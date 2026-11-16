from dataclasses import replace
import math
import random
import pytest
from aegis.development.bounded_braking import BoundedStatePacket
from aegis.development.physical_reference import KinematicReference,IntervalReading,state_consistency,command_energy_reference,brake_feedback_reference,force_acceleration_reference


def ref(v=.5,ev=.01):return KinematicReference([0.,0.,1.],[v,0.,0.],position_error_m=.005,velocity_error_m_s=ev)
def reading(kind='ACCELERATION',tick=0,value=(0.,0.,0.),error=.04):return IntervalReading(kind,tick,tick+1,list(value),error)
def packet(**kw):
 d=dict(position=[0.,0.,1.],velocity=[.5,0.,0.],position_error_m=.01,velocity_error_m_s=.02,sequence=0,acquired_seconds=0.,frame='WORLD',source='SIM_PRIMARY',bound_basis='TEST_ASSERTION');d.update(kw);return BoundedStatePacket(**d)


def test_semiimplicit_reference_and_exact_extreme_error_transport():
 r=ref();s=r.advance(reading(value=[2.,0.,0.]))
 assert s['velocity']==pytest.approx([.54,0.,0.]);assert s['position']==pytest.approx([.0108,0.,1.])
 assert s['velocity_error_m_s']==pytest.approx(.0108);assert s['position_error_m']==pytest.approx(.005216)
 actual_v=.51+2.04*.02;actual_p=.005+actual_v*.02
 assert abs(actual_v-s['velocity'][0])<=s['velocity_error_m_s']+1e-14
 assert abs(actual_p-s['position'][0])<=s['position_error_m']+1e-14


@pytest.mark.parametrize('sample',[None,reading(tick=1),reading(kind='BRAKE_FORCE'),replace(reading(),frame='BODY'),reading(value=[float('nan'),0.,0.]),reading(error=-1.)])
def test_reference_bad_or_missing_interval_latches_unsupported(sample):
 r=ref();assert r.advance(sample)['status']=='UNSUPPORTED'
 assert r.advance(reading())['status']=='UNSUPPORTED'


def test_reference_snapshot_no_mutable_alias():
 r=ref();s=r.snapshot();s['velocity'][0]=900.;assert r.snapshot()['velocity'][0]==.5


@pytest.mark.parametrize('kw',[dict(velocity=[-.5,0.,0.]),dict(position=[.4,0.,1.])])
def test_disjoint_state_bounds_reject(kw):
 assert state_consistency(packet(**kw),ref().snapshot(),tick=0)['status']=='INCONSISTENT'


@pytest.mark.parametrize('kw',[dict(frame='BODY'),dict(sequence=1),dict(acquired_seconds=.02),dict(velocity_error_m_s=None)])
def test_misaligned_state_evidence_unknown(kw):
 assert state_consistency(packet(**kw),ref().snapshot(),tick=0)['status']=='UNSUPPORTED'


def test_shared_wrong_anchor_is_not_identifiable_by_agreement():
 r=ref(v=-.5)
 assert state_consistency(packet(velocity=[-.5,0.,0.]),r.snapshot(),tick=0)['status']=='COMPATIBLE_UNDER_ASSERTED_BOUNDS'


def test_energy_zero_disturbance_matches_extreme_ball_state():
 r=ref();f=[-2.,0.,0.];c=command_energy_reference(f,r.snapshot(),hold_seconds=.02,mass_lower_kg=1.,disturbance_upper_n=0.)
 actual=.5*((.49-.04)**2-.49**2)
 assert c['hold_energy_upper_j']==pytest.approx(actual) and actual<0


def test_disturbance_can_make_braking_direction_unsupported():
 c=command_energy_reference([-2.,0.,0.],ref().snapshot(),hold_seconds=.02,mass_lower_kg=1.,disturbance_upper_n=5.)
 assert c['status']=='UNSUPPORTED_ENERGY_DIRECTION' and c['hold_energy_upper_j']>0


def test_energy_bound_covers_sampled_adversarial_states_masses_and_forces():
 rng=random.Random(20261116);r=ref().snapshot();f=[-2.,0.,0.]
 c=command_energy_reference(f,r,hold_seconds=.02,mass_lower_kg=1.,disturbance_upper_n=.2)
 for _ in range(300):
  unit=[rng.uniform(-1,1) for _ in range(3)];norm=math.hypot(*unit);v=[x+.01*y/norm for x,y in zip(r['velocity'],unit)]
  unit=[rng.uniform(-1,1) for _ in range(3)];norm=math.hypot(*unit);d=[.2*y/norm for y in unit]
  m=rng.uniform(1.,1.5);after=[x+.02*(u+w)/m for x,u,w in zip(v,f,d)]
  delta=.5*m*(sum(x*x for x in after)-sum(x*x for x in v))
  assert delta<=c['hold_energy_upper_j']+1e-12


def test_native_force_interval_missing_and_near_zero_distinguished():
 s=ref().snapshot()
 good=brake_feedback_reference(s,reading('BRAKE_FORCE',value=[-.99,0.,0.],error=.005),tick=0,requested_gain=2.,cap_per_axis_n=1.)
 bad=brake_feedback_reference(s,reading('BRAKE_FORCE',error=.005),tick=0,requested_gain=2.,cap_per_axis_n=1.)
 assert good['status']=='MODEL_CONSISTENT_FORCE' and bad['status']=='INCONSISTENT'
 near=brake_feedback_reference(ref(v=0.).snapshot(),reading('BRAKE_FORCE',error=.005),tick=0,requested_gain=2.,cap_per_axis_n=1.)
 assert near['status']=='UNINFORMATIVE_NEAR_ZERO'
 assert brake_feedback_reference(s,None,tick=0,requested_gain=2.,cap_per_axis_n=1.)['status']=='UNSUPPORTED'
 assert brake_feedback_reference(s,reading('BRAKE_FORCE'),tick=0,requested_gain=0.,cap_per_axis_n=1.)['status']=='NOT_REQUESTED'


def force_cross(f,a,**kw):
 params=dict(tick=0,mass_lower_kg=1.,mass_upper_kg=1.5,disturbance_upper_n=0.);params.update(kw)
 return force_acceleration_reference([0.,0.,0.],reading('BRAKE_FORCE',value=f,error=.005),reading(value=a),**params)


def test_forged_force_is_caught_by_honest_acceleration_but_joint_spoof_can_pass():
 assert force_cross([-.5,0.,0.],[0.,0.,0.])['status']=='INCONSISTENT'
 assert force_cross([-.5,0.,0.],[-.5,0.,0.])['status']=='COMPATIBLE_UNDER_ASSERTED_MODEL'


def test_inverse_mass_segment_projection_and_uncertainty():
 c=force_cross([-.6,0.,0.],[-.4,0.,0.])
 assert c['minimum_residual_m_s2']==pytest.approx(0.) and c['best_inverse_mass_kg_inv']==pytest.approx(2/3)
 assert force_cross([-.6,0.,0.],[-.3,0.,0.])['status']=='INCONSISTENT'
 assert force_cross([-.6,0.,0.],[-.3,0.,0.],disturbance_upper_n=.2)['status']=='COMPATIBLE_UNDER_ASSERTED_MODEL'


@pytest.mark.parametrize('kw',[dict(mass_lower_kg=0.),dict(mass_upper_kg=.5),dict(disturbance_upper_n=-1.),dict(tick=1)])
def test_bad_model_or_misaligned_reading_is_unsupported(kw):
 assert force_cross([0.,0.,0.],[0.,0.,0.],**kw)['status']=='UNSUPPORTED'


def test_numeric_ranges_are_not_favorable_decisions():
 c=command_energy_reference([-1e308,0.,0.],ref().snapshot(),hold_seconds=1e308,mass_lower_kg=1.,disturbance_upper_n=1e308)
 assert c['status']=='UNSUPPORTED' and c['hold_energy_upper_j'] is None
 r=KinematicReference([1e308,0.,0.],[1e308,0.,0.],position_error_m=.01,velocity_error_m_s=.01,dt_seconds=1e308)
 assert r.advance(reading(value=[1e308,0.,0.]))['status']=='UNSUPPORTED'


@pytest.mark.parametrize('tick',[False,True,-1,.0])
def test_reading_tick_must_be_a_nonnegative_integer(tick):
 result=force_acceleration_reference([0.,0.,0.],reading('BRAKE_FORCE'),reading(),tick=tick,mass_lower_kg=1.,mass_upper_kg=1.5,disturbance_upper_n=0.)
 assert result['status']=='UNSUPPORTED'
