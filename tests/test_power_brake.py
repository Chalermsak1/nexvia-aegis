import math
import numpy as np
import pytest
from aegis.env.mujoco_power_brake import PowerBrakeEnvironment


def test_force_motor_is_not_a_true_velocity_servo():
 e=PowerBrakeEnvironment();e.reset_development(.5)
 r=e.runtime_record();assert r['native_gain']==[1.]*3 and r['native_velocity_bias']==[0.]*3
 for k in range(3):
  pre=e.prepare_powered_force([-.1,0.,0.],brake_powered=True,gravity_powered=True,disturbance=[0.,0.,0.])
  assert pre['actuator_force_pre_n']==[-.1,0.,0.]
  p=e.advance_prepared();assert p['velocity'][0]==pytest.approx(.5-(k+1)*.002,abs=1e-12)
 assert r['actuator_kind']=='DIRECT_FORCE_MOTORS_NO_VELOCITY_SERVO'


@pytest.mark.parametrize('brake,gravity,expected_acc',[(True,True,[-1.,0.,0.]),(False,True,[0.,0.,0.]),(True,False,[-1.,0.,-9.81]),(False,False,[0.,0.,-9.81])])
def test_brake_and_gravity_power_domains_have_separate_effects(brake,gravity,expected_acc):
 e=PowerBrakeEnvironment();e.reset_development(.5);before=e.get_state()['robot_velocity'].copy()
 pre=e.prepare_powered_force([-1.,0.,0.],brake_powered=brake,gravity_powered=gravity,disturbance=[0.,0.,0.])
 p=e.advance_prepared();actual=(np.array(p['velocity'])-before)/.02
 assert actual==pytest.approx(expected_acc,abs=1e-12)
 assert pre['applied_body_force_n'][2]==(9.81 if gravity else 0.)


def test_total_loss_keeps_integrating_until_floor_contact_and_does_not_freeze():
 e=PowerBrakeEnvironment();e.reset_development(.5);events=[]
 for k in range(60):
  e.prepare_powered_force([0.,0.,0.],brake_powered=False,gravity_powered=False,disturbance=[0.,0.,0.]);events.append(e.advance_prepared())
 assert any(p['contact_floor'] for p in events)
 assert events[-1]['time']==pytest.approx(1.2)
 assert events[-1]['position'][0]>-2. and events[-1]['position'][2]<1.3
 assert max(p['velocity'][0] for p in events)>0.4  # motion continues before floor friction


@pytest.mark.parametrize('kw',[{'brake_powered':1},{'gravity_powered':None},{'force':[2.,0.,0.]},{'disturbance':[float('nan'),0.,0.]}])
def test_invalid_motor_or_domain_input_rejected(kw):
 e=PowerBrakeEnvironment();e.reset_development(.5)
 c=dict(force=[0.,0.,0.],brake_powered=True,gravity_powered=True,disturbance=[0.,0.,0.]);c.update(kw)
 with pytest.raises(ValueError):e.prepare_powered_force(**c)
