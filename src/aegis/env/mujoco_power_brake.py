"""DEVELOPMENT force-driven translational plant with explicit power domains.

Brake motor force is commanded from a measured-feedback controller, not true
velocity. Separate gravity compensation can be removed on total power loss.
No physical battery or brake hardware is calibrated by this model.
"""
import hashlib
import numpy as np
import mujoco
from .mujoco_lease_brake import ForceLimitedBrakeEnvironment
from aegis.development.bounded_braking import vector,scalar


class PowerBrakeEnvironment(ForceLimitedBrakeEnvironment):
    ENVIRONMENT_ID='AEGIS_POWER_FORCE_BRAKE_V1_DEVELOPMENT'

    def _build_mujoco_model(self):
        c=self.config
        obstacles=''.join(f'<geom name="obs_{i}" type="sphere" size="{o.radius}" pos="{o.center[0]} {o.center[1]} {o.center[2]}"/>' for i,o in enumerate(self.obstacles))
        joints=''.join(f'<joint name="robot_{a}" type="slide" axis="{axis}"/>' for a,axis in zip('xyz',('1 0 0','0 1 0','0 0 1')))
        motors=''.join(f'<motor name="brake_{a}" joint="robot_{a}" gear="1" ctrllimited="true" ctrlrange="{-self.brake_cap} {self.brake_cap}" forcelimited="true" forcerange="{-self.brake_cap} {self.brake_cap}"/>' for a in 'xyz')
        self.xml=f'<mujoco model="nexvia_power_brake_dev"><option timestep="{c.timestep}" gravity="0 0 -9.81" integrator="Euler"/><worldbody><geom name="floor" type="plane" size="3 3 .1"/>{obstacles}<body name="robot">{joints}<geom name="robot_geom" type="sphere" size="{c.robot_radius}" mass="{self.actual_mass}"/></body></worldbody><actuator>{motors}</actuator></mujoco>'
        return mujoco.MjModel.from_xml_string(self.xml)

    def set_brake_gain(self,gain):
        if scalar(gain,'gain')!=0:raise ValueError('force plant has no velocity servo')
        self.model.actuator_gainprm[:,0]=1.;self.model.actuator_biasprm[:,2]=0.;self.data.ctrl[:]=0.

    def prepare_forces(self,command,disturbance,*,brake_gain):
        raise NotImplementedError('use prepare_powered_force with explicit domains')

    def prepare_powered_force(self,force,*,brake_powered,gravity_powered,disturbance):
        if type(brake_powered) is not bool or type(gravity_powered) is not bool:raise ValueError('explicit power domains required')
        force=np.array(vector(force));disturbance=np.array(vector(disturbance))
        if np.any(abs(force)>self.brake_cap+1e-12):raise ValueError('motor cap exceeded')
        applied=disturbance.copy();applied[2]+=9.81 if gravity_powered else 0.
        self.data.ctrl[:]=force if brake_powered else 0.
        self.data.xfrc_applied[self.robot_body_id,:3]=applied
        mujoco.mj_forward(self.model,self.data);self._prepared=True
        return {'actuator_force_pre_n':self.data.actuator_force.tolist(),'generalized_force_pre_n':self.data.qfrc_actuator.tolist(),
          'applied_body_force_n':applied.tolist(),'brake_powered':brake_powered,'gravity_powered':gravity_powered,
          'ctrl':self.data.ctrl.tolist(),'phase':'PRE_INTEGRATION_NATIVE_MOTOR_FORCE',
          'contact_floor_pre':bool(self.get_state()['contact_floor']),'contact_obstacle_pre':bool(self.get_state()['contact_obstacle'])}

    def runtime_record(self):
        r=super().runtime_record();r.update(actuator_kind='DIRECT_FORCE_MOTORS_NO_VELOCITY_SERVO',
          native_gain=self.model.actuator_gainprm[:,0].tolist(),native_velocity_bias=self.model.actuator_biasprm[:,2].tolist(),
          gravity_compensation='NOMINAL_1_KG_POWER_DOMAIN_DEPENDENT',actual_power_source='SYNTHETIC_FLAGS_NOT_BATTERY_EVIDENCE')
        return r
