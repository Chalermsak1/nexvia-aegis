"""New DEVELOPMENT plant: three translational slide joints, capped velocity servos.

Different dynamics from the historical free-joint or joint-damping arms. Zero
velocity targets and native per-axis actuator force caps model hypothetical
powered brakes. Their hardware availability/effectiveness is not established.
"""
import hashlib
import mujoco
import numpy as np
from .mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from aegis.development.bounded_braking import scalar, vector


class ForceLimitedBrakeEnvironment(AegisMuJoCo3DEnvironment):
    ENVIRONMENT_ID = 'AEGIS_SLIDING_MASS_CAPPED_BRAKE_V1_DEVELOPMENT'

    def __init__(self, *, actual_mass_kg=1., brake_cap_per_axis_n=1.):
        self.actual_mass = scalar(actual_mass_kg, 'actual mass', positive=True)
        self.brake_cap = scalar(brake_cap_per_axis_n, 'brake cap', positive=True)
        super().__init__()
        if self.model.nq != 3 or self.model.nv != 3 or self.model.nu != 3: raise ValueError('unexpected plant dimensions')
        self._prepared = False
        self.set_brake_gain(0.)

    def _build_mujoco_model(self):
        c = self.config
        obstacles = ''.join(f'<geom name="obs_{i}" type="sphere" size="{o.radius}" pos="{o.center[0]} {o.center[1]} {o.center[2]}"/>' for i, o in enumerate(self.obstacles))
        joints = ''.join(f'<joint name="robot_{axis}" type="slide" axis="{direction}"/>' for axis, direction in zip('xyz', ('1 0 0', '0 1 0', '0 0 1')))
        actuators = ''.join(f'<velocity name="brake_{axis}" joint="robot_{axis}" kv="2" forcelimited="true" forcerange="{-self.brake_cap} {self.brake_cap}"/>' for axis in 'xyz')
        self.xml = f'''<mujoco model="nexvia_lease_brake_dev"><option timestep="{c.timestep}" gravity="0 0 -9.81" integrator="Euler"/>
        <worldbody><geom name="floor" type="plane" size="3 3 .1"/>{obstacles}
        <body name="robot">{joints}<geom name="robot_geom" type="sphere" size="{c.robot_radius}" mass="{self.actual_mass}"/></body>
        </worldbody><actuator>{actuators}</actuator></mujoco>'''
        return mujoco.MjModel.from_xml_string(self.xml)

    def reset(self, rng):
        raise NotImplementedError('This versioned plant requires reset_development(speed).')

    def reset_development(self, speed):
        speed = scalar(speed, 'initial speed')
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:] = [-2., -2., 1.3]
        self.data.qvel[:] = [speed, 0., 0.]
        self.step_count = 0; self._prepared = False
        self.set_brake_gain(0.)
        mujoco.mj_forward(self.model, self.data)
        return self.get_state()

    def set_brake_gain(self, gain):
        gain = scalar(gain, 'brake gain')
        self.model.actuator_gainprm[:, 0] = gain
        self.model.actuator_biasprm[:, 2] = -gain
        self.data.ctrl[:] = 0.

    def prepare_forces(self, command, disturbance, *, brake_gain):
        command, disturbance = np.array(vector(command)), np.array(vector(disturbance))
        if np.linalg.norm(command) > 2. + 1e-10: raise ValueError('command force limit')
        self.set_brake_gain(brake_gain)
        applied = command + disturbance
        applied[2] += 9.81  # Nominal 1 kg compensation, including in mass-mismatch cases.
        self.data.xfrc_applied[self.robot_body_id, :3] = applied
        mujoco.mj_forward(self.model, self.data)
        self._prepared = True
        return {'actuator_force_pre_n': self.data.actuator_force.tolist(),
                'generalized_brake_force_pre_n': self.data.qfrc_actuator.tolist(),
                'applied_body_force_n': applied.tolist(), 'brake_gain': brake_gain,
                'phase': 'PRE_INTEGRATION_NATIVE_ACTUATOR_FORCE',
                'native_gain': self.model.actuator_gainprm[:, 0].tolist(),
                'native_velocity_bias': self.model.actuator_biasprm[:, 2].tolist(),
                'native_target_velocity': self.data.ctrl.tolist()}

    def advance_prepared(self):
        if not self._prepared: raise ValueError('prepare and persist tick intent before advance')
        self._prepared = False
        mujoco.mj_step(self.model, self.data); self.step_count += 1
        mujoco.mj_forward(self.model, self.data)
        state = self.get_state()
        return {'position': state['robot_pos'].tolist(), 'velocity': state['robot_velocity'].tolist(),
                'time': float(self.data.time), 'integrated_qpos': self.data.qpos.tolist(),
                'contact_floor': bool(state['contact_floor']), 'contact_obstacle': bool(state['contact_obstacle']),
                'geometric_or_contact_violation': bool(state['safety_violation']),
                'boundary_clearance': state['boundary_clearance'], 'min_obstacle_distance': state['min_obstacle_distance']}

    def runtime_record(self):
        return {'environment_id': self.ENVIRONMENT_ID, 'xml_sha256': hashlib.sha256(self.xml.encode()).hexdigest(),
                'dt': float(self.model.opt.timestep), 'mass_kg': float(self.model.body_mass[self.robot_body_id]),
                'gravity': self.model.opt.gravity.tolist(), 'integrator': int(self.model.opt.integrator),
                'nq': self.model.nq, 'nv': self.model.nv, 'nu': self.model.nu,
                'actuator_forcelimited': self.model.actuator_forcelimited.tolist(),
                'actuator_forcerange': self.model.actuator_forcerange.tolist(),
                'robot_radius': self.config.robot_radius, 'arena_limit': self.config.arena_limit,
                'obstacles': [{'center': o.center.tolist(), 'radius': o.radius} for o in self.obstacles],
                'geometry_positions': self.model.geom_pos.tolist(), 'geometry_sizes': self.model.geom_size.tolist(),
                'cbf_used': False, 'nominal_gravity_compensation_n': 9.81}
