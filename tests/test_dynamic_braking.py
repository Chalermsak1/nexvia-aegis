import math
from dataclasses import replace
import pytest
from aegis.development.dynamic_braking import DelayedSlewBrake,MeasuredRecoveryMonitor
from aegis.development.bounded_braking import BoundedStatePacket
from aegis.development.physical_reference import IntervalReading


def packet(tick,v=(.5,0.,0.),p=(-2.,-2.,1.3)):
 return BoundedStatePacket(list(p),list(v),.005,.01,tick,tick*.02,'WORLD','SIM_DYNAMIC_STATE_V1','ASSERTED_SYNTHETIC_ERROR_BALL')
def monitor():
 return MeasuredRecoveryMonitor(packet(0),{'robot_radius':.2,'arena_limit':3.,'obstacles':[]},delay_ticks=2,slew_n_s=4.,cap_n=1.,dt_seconds=.02,gain=2.,position_error_m=.005,velocity_error_m_s=.01,force_error_n=.005,acceleration_error_m_s2=.04,mass_lower_kg=1.,mass_upper_kg=1.,disturbance_upper_n=0.,terminal_speed_m_s=.05,dwell_ticks=3,minimum_clearance_m=.02)
def force(k,v):return IntervalReading('BRAKE_FORCE',k,k+1,list(v),.005)
def acc(k,v):return IntervalReading('ACCELERATION',k,k+1,list(v),.04)


def test_delay_boundary_and_per_axis_force_slew():
 b=DelayedSlewBrake(delay_ticks=3,slew_n_s=4.,cap_n=1.,dt_seconds=.02)
 fs=[b.step([-4.,4.,0.],tick=k,powered=True) for k in range(20)]
 assert fs[:3]==[[0.,0.,0.]]*3
 assert fs[3]==pytest.approx([-.08,.08,0.]);assert fs[-1]==[-1.,1.,0.]
 for old,new in zip([[0.,0.,0.]]+fs,fs):assert max(abs(x-y) for x,y in zip(old,new))<=.08+1e-12


def test_power_cut_is_immediate_and_restart_flushes_pending_commands():
 b=DelayedSlewBrake(delay_ticks=2,slew_n_s=100.,cap_n=1.,dt_seconds=.02)
 assert [b.step([-1.,0.,0.],tick=k,powered=True)[0] for k in range(3)]==[0.,0.,-1.]
 assert b.step([1.,0.,0.],tick=3,powered=False)==[0.,0.,0.]
 assert [b.step([1.,0.,0.],tick=k,powered=True)[0] for k in range(4,7)]==[0.,0.,1.]


@pytest.mark.parametrize('kw',[{'delay_ticks':True},{'delay_ticks':-1},{'delay_ticks':10001},{'slew_n_s':0.},{'slew_n_s':float('nan')},{'cap_n':False},{'dt_seconds':0.},{'dt_seconds':1e-320,'slew_n_s':1e-320}])
def test_invalid_actuator_model_rejected(kw):
 c=dict(delay_ticks=2,slew_n_s=4.,cap_n=1.,dt_seconds=.02);c.update(kw)
 with pytest.raises(ValueError):DelayedSlewBrake(**c)


@pytest.mark.parametrize('p',[None,replace(packet(0),sequence=True),replace(packet(0),acquired_seconds=True),replace(packet(0),position_error_m=1.),replace(packet(0),source='OTHER'),replace(packet(0),velocity=[float('nan'),0.,0.]),replace(packet(0),velocity=[1e308,0.,0.])])
def test_unavailable_malformed_or_overflowing_state_cannot_command_braking(p):
 m=monitor();c=m.command(p,tick=0)
 assert c['status']!='MEASURED_BRAKE_REQUEST' and c['request_n']==[0.,0.,0.]
 assert c['operational_authorization'] is False


def test_missing_force_preserves_independent_acceleration_reference_but_dwell_unknown():
 m=monitor();m.command(packet(0),tick=0)
 r=m.observe(None,acc(0,[0.,0.,0.]),packet(1,p=(-1.99,-2.,1.3)),tick=0)
 assert r['reference_after']['status']=='CONDITIONAL_REFERENCE'
 assert r['assessment']=='UNKNOWN_EVIDENCE' and r['consecutive_supported_samples']==0


def test_missing_acceleration_breaks_propagated_reference():
 m=monitor();m.command(packet(0),tick=0)
 r=m.observe(force(0,[0.,0.,0.]),None,packet(1,p=(-1.99,-2.,1.3)),tick=0)
 assert r['reference_after']['status']=='UNSUPPORTED' and r['assessment']=='UNKNOWN_EVIDENCE'
 assert m.command(packet(1),tick=1)['status']=='ABSTAIN_REFERENCE_CONTRADICTION'


def test_observation_sequence_is_enforced():
 m=monitor()
 with pytest.raises(ValueError):m.observe(None,None,None,tick=0)
 m.command(packet(0),tick=0)
 with pytest.raises(ValueError):m.command(packet(0),tick=0)
 m.observe(None,None,None,tick=0)
 with pytest.raises(ValueError):m.command(packet(0),tick=0)


def test_force_loss_after_delay_is_detected_from_measurements():
 m=monitor();v=.5;p=-2.
 for k in range(3):
  c=m.command(packet(k,v=(v,0.,0.),p=(p,-2.,1.3)),tick=k);p+=.02*v
  r=m.observe(force(k,[0.,0.,0.]),acc(k,[0.,0.,0.]),packet(k+1,v=(v,0.,0.),p=(p,-2.,1.3)),tick=k)
 assert c['expected_force_n'][0]<-.005 and r['force_check']['status']=='INCONSISTENT'
 assert r['assessment']=='INCONSISTENCY_OBSERVED' and r['operational_authorization'] is False


def test_realized_force_changes_with_reported_velocity_without_any_plant_input():
 first=monitor();second=monitor()
 c1=first.command(packet(0),tick=0)
 # Alternate anchor is legitimate independently specified input; no truth access.
 second.reference.velocity=(.1,0.,0.)
 c2=second.command(packet(0,v=(.1,0.,0.)),tick=0)
 assert c1['request_n']==[-1.,0.,0.] and c2['request_n']==[-.2,0.,0.]
