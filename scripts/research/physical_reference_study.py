#!/usr/bin/env python3
"""Development-only measured reference/actuator feedback integration.

The initial anchor, mean-acceleration sensor, brake force sensor and their frame,
clock/error bounds are MODELED assumptions. Faults explicitly defeat them. No
hardware, authenticated trust anchor, Holdout or scientific release decision.
"""
from dataclasses import asdict
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np
import mujoco

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'src'))
from aegis.development.physical_reference import KinematicReference, IntervalReading, state_consistency, command_energy_reference, brake_feedback_reference, force_acceleration_reference
from aegis.development.dual_source_braking import SourceBrakeSupervisor
from aegis.env.mujoco_lease_brake import ForceLimitedBrakeEnvironment
from scripts.research import freshness_lease_study as previous
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect

STUDY = 'V9-M5 measured physical reference and brake feedback diagnostic v1'
CASES = ('nominal', 'shared_reverse', 'cached_capture', 'initial_frame_flip', 'joint_frame_model_spoof',
         'brake_loss', 'force_feedback_spoof', 'imu_force_spoof', 'all_feedback_ghost',
         'persistent_disturbance', 'limited_brake_disturbance', 'mass_gravity_offset', 'reference_dropout', 'reference_bias')
ARMS = ('WITNESS_BASELINE', 'REFERENCE_GUARD', 'REFERENCE_FEEDBACK')
STEPS = 60
FILES = tuple(dict.fromkeys(previous.FILES + ('src/aegis/development/physical_reference.py', 'scripts/research/physical_reference_study.py')))


def hashes(): return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}


def plan():
    out = []
    for i, speed in enumerate((.4, .5, .6)):
        for case in CASES:
            for arm in ARMS:
                out.append({'id': f'v{i}:{case}:{arm}', 'initial_index': i, 'initial_speed_m_s': speed, 'case': case, 'arm': arm, 'steps': STEPS,
                    'sensor_rng_keys': [[20261116, 4, i, 0], [20261116, 4, i, 1]], 'reference_rng_key': [20261116, 4, i, 2],
                    'actual_mass_kg': 1.5 if case == 'mass_gravity_offset' else 1., 'brake_cap_per_axis_n': .05 if case == 'limited_brake_disturbance' else 1.,
                    'disturbance_n': [.2, 0., 0.] if case in ('persistent_disturbance', 'limited_brake_disturbance') else [0., 0., 0.],
                    'design_disturbance_upper_n': 5. if case == 'mass_gravity_offset' else .2 if case in ('persistent_disturbance', 'limited_brake_disturbance') else 0.})
    return out


def uniform_ball(rng, bound): return rng.uniform(-bound / math.sqrt(3), bound / math.sqrt(3), 3).tolist()


class SensorModel:
    """Fault generator, NOT a control or monitoring component. Reads plant truth."""
    def __init__(self, a):
        self.a, self.ghost = a, None
        self.rng = np.random.default_rng(a['reference_rng_key'])

    def frame(self, pos, vel):
        p, v = np.array(pos, dtype=float).copy(), np.array(vel, dtype=float).copy()
        if self.a['case'] in ('initial_frame_flip', 'joint_frame_model_spoof'):
            p[0] = -4. - p[0]; v[0] = -v[0]
        return p, v

    def anchor(self, pos, vel):
        p, v = self.frame(pos, vel)
        noise = {'position': uniform_ball(self.rng, .005), 'velocity': uniform_ball(self.rng, .01)}
        return {'position': (p + noise['position']).tolist(), 'velocity': (v + noise['velocity']).tolist(),
                'position_error_m': .005, 'velocity_error_m_s': .01, 'noise': noise}

    def capture_input(self, pos, vel, noise):
        p, v = (np.array(self.ghost['position']), np.array(self.ghost['velocity'])) if self.ghost else self.frame(pos, vel)
        return previous.measured_inputs(p, v, noise)

    def prepare_ghost(self, pos, vel, requested_gain):
        if self.a['case'] == 'all_feedback_ghost' and requested_gain > 0 and self.ghost is None:
            self.ghost = {'position': list(pos), 'velocity': list(vel)}

    def post_sensors(self, step, pos_before, vel_before, physical_after, native_brake, requested_gain, command):
        force_noise, acc_noise = uniform_ball(self.rng, .005), uniform_ball(self.rng, .04)
        true_acc = (np.array(physical_after['velocity']) - vel_before) / .02
        sensed_force, sensed_acc = np.array(native_brake), true_acc.copy()
        case, cap = self.a['case'], self.a['brake_cap_per_axis_n']
        if case in ('force_feedback_spoof', 'imu_force_spoof') and requested_gain > 0:
            expected = np.clip(-requested_gain * np.array(vel_before), -cap, cap)
            sensed_force = expected
            if case == 'imu_force_spoof': sensed_acc = np.array(command) + expected
        if self.ghost is not None:
            old_v = np.array(self.ghost['velocity']); old_p = np.array(self.ghost['position'])
            expected = np.clip(-requested_gain * old_v, -cap, cap)
            sensed_acc = np.array(command) + expected
            new_v = old_v + .02 * sensed_acc; new_p = old_p + .02 * new_v
            self.ghost = {'position': new_p.tolist(), 'velocity': new_v.tolist()}
            sensed_force = expected
        if case in ('initial_frame_flip', 'joint_frame_model_spoof'):
            sensed_acc[0] = -sensed_acc[0]; sensed_force[0] = -sensed_force[0]
        if case == 'reference_bias' and step >= 6: sensed_acc[0] += .3
        force = IntervalReading('BRAKE_FORCE', step, step + 1, (sensed_force + force_noise).tolist(), .005)
        acc = None if case == 'reference_dropout' and step >= 6 else IntervalReading('ACCELERATION', step, step + 1, (sensed_acc + acc_noise).tolist(), .04)
        reported_command = list(command)
        if case == 'joint_frame_model_spoof': reported_command[0] = -reported_command[0]
        return {'force': asdict(force), 'acceleration': asdict(acc) if acc else None, 'force_noise': force_noise, 'acceleration_noise': acc_noise,
                'reported_command_for_monitor': reported_command, 'ghost_after': self.ghost,
                'true_acceleration_for_scoring': true_acc.tolist(),
                'force_error_for_scoring_n': float(np.linalg.norm(np.array(force.value) - native_brake)),
                'acceleration_error_for_scoring_m_s2': float(np.linalg.norm(np.array(acc.value) - true_acc)) if acc else None}


class ReferenceController:
    """Control/monitor path: only supplied measurements and asserted model bounds."""
    def __init__(self, a, anchor):
        self.a, self.base = a, SourceBrakeSupervisor()
        self.reference = KinematicReference(anchor['position'], anchor['velocity'], position_error_m=anchor['position_error_m'], velocity_error_m_s=anchor['velocity_error_m_s'])
        self.first_state_failure = self.first_feedback_failure = None
        self.last_feedback = None

    def choose(self, primary, secondary, *, now_seconds):
        tick = round(now_seconds / .02); ref = self.reference.snapshot()
        checks = [state_consistency(p, ref, tick=tick) for p in (primary, secondary)]
        if any(v['status'] in ('INCONSISTENT', 'UNSUPPORTED') for v in checks) and self.first_state_failure is None:
            self.first_state_failure = {'tick': tick, 'reason': 'STATE_REFERENCE_INCONSISTENT_OR_UNSUPPORTED'}
        result = self.base.choose(primary, secondary, now_seconds=now_seconds)
        energy = command_energy_reference(result['force_n'], ref, hold_seconds=.02, mass_lower_kg=1., disturbance_upper_n=self.a['design_disturbance_upper_n']) if result['status'] == 'COMMAND_PROPOSED' else None
        reason = None
        if self.a['arm'] != 'WITNESS_BASELINE':
            if self.first_state_failure: reason = self.first_state_failure['reason']
            elif energy and energy['status'] != 'SUPPORTED_UNDER_ASSERTED_MODEL': reason = 'REFERENCE_ENERGY_UNSUPPORTED'
            if self.a['arm'] == 'REFERENCE_FEEDBACK' and self.first_feedback_failure: reason = self.first_feedback_failure['reason']
        result['reference_checks'] = {'reference': ref, 'state_consistency': checks, 'command_energy': energy,
            'first_state_failure': self.first_state_failure, 'first_feedback_failure': self.first_feedback_failure,
            'last_feedback_status': {k: v['status'] for k, v in self.last_feedback.items()} if self.last_feedback else None,
            'intervention_reason': reason}
        if reason: result.update(status='NO_COMMAND', reason=reason, force_n=None)
        return result

    def post(self, sensors, *, start_reference, tick, requested_gain):
        f = IntervalReading(**sensors['force']) if sensors['force'] else None
        acc = IntervalReading(**sensors['acceleration']) if sensors['acceleration'] else None
        brake = brake_feedback_reference(start_reference, f, tick=tick, requested_gain=requested_gain, cap_per_axis_n=self.a['brake_cap_per_axis_n'])
        cross = force_acceleration_reference(sensors['reported_command_for_monitor'], f, acc, tick=tick,
            mass_lower_kg=1., mass_upper_kg=1.5, disturbance_upper_n=self.a['design_disturbance_upper_n'])
        self.last_feedback = {'brake_force': brake, 'force_acceleration': cross}
        if any(v['status'] in ('INCONSISTENT', 'UNSUPPORTED') for v in self.last_feedback.values()) and self.first_feedback_failure is None:
            self.first_feedback_failure = {'tick': tick + 1, 'reason': 'FORCE_OR_MODEL_FEEDBACK_INCONSISTENT_OR_UNSUPPORTED'}
        after = self.reference.advance(acc)
        return {'feedback': self.last_feedback, 'first_feedback_failure': self.first_feedback_failure, 'reference_after': after,
                'fallback_authority': 'NO_GUARANTEED_REST_MARGIN' if self.a['design_disturbance_upper_n'] >= self.a['brake_cap_per_axis_n'] else 'CAP_EXCEEDS_ASSERTED_DISTURBANCE_ONLY'}


def components(a, initial_pos, initial_vel):
    sensor = SensorModel(a); anchor = sensor.anchor(initial_pos, initial_vel)
    parent_case = 'shared_reverse' if a['case'] == 'shared_reverse' else 'compromised_witness' if a['case'] == 'cached_capture' else 'nominal'
    logic = previous.Logic(dict(a, case=parent_case, arm='WITNESS_LEASE'))
    controller = ReferenceController(a, anchor); logic.controller = controller
    return sensor, anchor, logic, controller


def actual_gain(a, step, requested):
    return 0. if step >= 6 and a['case'] in ('brake_loss', 'force_feedback_spoof', 'imu_force_spoof', 'all_feedback_ghost') else requested


def summary(a, events):
    ticks, physics, sensors = ([v for v in events if v['type'] == kind] for kind in ('TICK', 'PHYSICS', 'SENSORS'))
    state_ticks = [t['step'] for t in ticks if t['logic']['selection']['reference_checks']['first_state_failure'] is not None]
    feedback_ticks = [s['monitor']['first_feedback_failure']['tick'] for s in sensors if s['monitor']['first_feedback_failure'] is not None]
    req = next((t['logic']['switch']['request_step'] for t in ticks if t['logic']['switch']['request_step'] is not None), None)
    contact = any(p['contact_floor'] or p['contact_obstacle'] for p in physics)
    return {'physics_steps': len(physics), 'first_fallback_request_tick': req, 'first_state_failure_tick': min(state_ticks) if state_ticks else None,
            'first_feedback_failure_tick': min(feedback_ticks) if feedback_ticks else None,
            'positive_command_power_ticks': sum(t['true_command_power_w'] > 1e-10 for t in ticks),
            'brake_force_inconsistent_intervals': sum(s['monitor']['feedback']['brake_force']['status'] == 'INCONSISTENT' for s in sensors),
            'force_acceleration_inconsistent_intervals': sum(s['monitor']['feedback']['force_acceleration']['status'] == 'INCONSISTENT' for s in sensors),
            'uninformative_brake_intervals': sum(s['monitor']['feedback']['brake_force']['status'] == 'UNINFORMATIVE_NEAR_ZERO' for s in sensors),
            'force_sensor_bound_violations': sum(s['measurements']['force_error_for_scoring_n'] > .005 + 1e-10 for s in sensors),
            'acceleration_sensor_bound_violations': sum(s['measurements']['acceleration_error_for_scoring_m_s2'] is not None and s['measurements']['acceleration_error_for_scoring_m_s2'] > .04 + 1e-10 for s in sensors),
            'reference_velocity_ball_violations': sum(s['monitor']['reference_after']['status'] == 'CONDITIONAL_REFERENCE' and s['reference_truth_scoring']['velocity_error_m_s'] > s['monitor']['reference_after']['velocity_error_m_s'] + 1e-10 for s in sensors),
            'reference_evaluable_intervals': sum(s['monitor']['reference_after']['status'] == 'CONDITIONAL_REFERENCE' for s in sensors),
            'reference_unevaluable_intervals': sum(s['monitor']['reference_after']['status'] != 'CONDITIONAL_REFERENCE' for s in sensors),
            'acceleration_sensor_missing_intervals': sum(s['measurements']['acceleration'] is None for s in sensors),
            'unsupported_feedback_intervals': sum(any(v['status'] == 'UNSUPPORTED' for v in s['monitor']['feedback'].values()) for s in sensors),
            'geometric_or_contact_violation_samples': sum(p['geometric_or_contact_violation'] for p in physics),
            'contact_samples': sum(p['contact_floor'] or p['contact_obstacle'] for p in physics),
            'free_motion_evaluation': 'UNEVALUABLE_CONTACT' if contact else 'DEVELOPMENT_DIAGNOSTIC_ONLY',
            'final_sampled_speed_m_s': float(np.linalg.norm(physics[-1]['velocity'])),
            'classification': 'MEASURED_REFERENCE_DIAGNOSTIC_NOT_SAFETY_OR_REST_CERTIFICATION'}


def run_episode(a, emit):
    env = ForceLimitedBrakeEnvironment(actual_mass_kg=a['actual_mass_kg'], brake_cap_per_axis_n=a['brake_cap_per_axis_n'])
    initial = env.reset_development(a['initial_speed_m_s']); pos, vel = initial['robot_pos'].tolist(), initial['robot_velocity'].tolist()
    sensor, anchor, logic, controller = components(a, pos, vel)
    emit({'type': 'RESET', 'runtime': env.runtime_record(), 'position': pos, 'velocity': vel, 'reference_anchor': anchor})
    rngs = [np.random.default_rng(k) for k in a['sensor_rng_keys']]; events = []
    for step in range(a['steps']):
        state = env.get_state(); pos, vel = state['robot_pos'].tolist(), state['robot_velocity'].tolist()
        noise = previous.noise_sample(rngs); ref_start = controller.reference.snapshot()
        decisions = logic.tick(step, sensor.capture_input(pos, vel, noise)); requested = decisions['brake_gain']
        gain = actual_gain(a, step, requested); sensor.prepare_ghost(pos, vel, requested)
        plant = env.prepare_forces(decisions['force_n'], a['disturbance_n'], brake_gain=gain)
        e = {'type': 'TICK', 'step': step, 'position_before': pos, 'velocity_before': vel, 'noise': noise,
             'logic': decisions, 'plant': plant, 'actual_brake_gain': gain,
             'contact_before_floor': bool(state['contact_floor']), 'contact_before_obstacle': bool(state['contact_obstacle']),
             'true_command_power_w': float(np.dot(decisions['force_n'], vel)), 'reference_at_interval_start': ref_start}
        emit(e); events.append(e)
        after = env.advance_prepared(); e = dict(after, type='PHYSICS', step=step); emit(e); events.append(e)
        measured = sensor.post_sensors(step, pos, vel, after, plant['actuator_force_pre_n'], requested, decisions['force_n'])
        checked = controller.post(measured, start_reference=ref_start, tick=step, requested_gain=requested)
        ref_after = checked['reference_after']
        e = {'type': 'SENSORS', 'step': step, 'measurements': measured, 'monitor': checked,
             'reference_truth_scoring': {'velocity_error_m_s': float(np.linalg.norm(np.array(ref_after['velocity']) - after['velocity'])),
                                         'position_error_m': float(np.linalg.norm(np.array(ref_after['position']) - after['position']))}}
        emit(e); events.append(e)
    return summary(a, events)


def audit_episode(a, events, terminal, meta):
    if len(events) != 1 + 3 * a['steps'] or events[0]['type'] != 'RESET': raise ValueError('missing measured reference evidence')
    r = events[0]['runtime']; expected = ForceLimitedBrakeEnvironment(actual_mass_kg=a['actual_mass_kg'], brake_cap_per_axis_n=a['brake_cap_per_axis_n']).runtime_record()
    if r != expected or terminal['sources_after'] != meta['sources']: raise ValueError('runtime/source mismatch')
    pos, vel = events[0]['position'], events[0]['velocity']
    if pos != [-2., -2., 1.3] or vel != [a['initial_speed_m_s'], 0., 0.]: raise ValueError('reset mismatch')
    sensor, anchor, logic, controller = components(a, pos, vel)
    if anchor != events[0]['reference_anchor']: raise ValueError('anchor stream mismatch')
    rngs = [np.random.default_rng(k) for k in a['sensor_rng_keys']]; old_floor = old_obstacle = False
    for step in range(a['steps']):
        t, p, s = events[1 + 3*step:4 + 3*step]
        if [v['type'] for v in (t,p,s)] != ['TICK','PHYSICS','SENSORS'] or any(v['step'] != step for v in (t,p,s)): raise ValueError('event order mismatch')
        if t['position_before'] != pos or t['velocity_before'] != vel: raise ValueError('state continuity mismatch')
        noise = previous.noise_sample(rngs); ref_start = controller.reference.snapshot()
        decisions = logic.tick(step, sensor.capture_input(pos, vel, noise)); requested = decisions['brake_gain']; gain = actual_gain(a,step,requested)
        sensor.prepare_ghost(pos,vel,requested)
        if noise != t['noise'] or ref_start != t['reference_at_interval_start'] or decisions != t['logic'] or t['actual_brake_gain'] != gain: raise ValueError('reference/control reconstruction mismatch')
        if t['true_command_power_w'] != float(np.dot(decisions['force_n'],vel)): raise ValueError('power mismatch')
        brake = np.clip(-gain*np.array(vel),-a['brake_cap_per_axis_n'],a['brake_cap_per_axis_n'])
        if not np.allclose(t['plant']['actuator_force_pre_n'],brake,rtol=0.,atol=1e-12) or not np.allclose(t['plant']['generalized_brake_force_pre_n'],brake,rtol=0.,atol=1e-12): raise ValueError('actual brake force mismatch')
        if t['plant']['native_gain'] != [gain]*3 or t['plant']['native_velocity_bias'] != [-gain]*3 or t['plant']['native_target_velocity'] != [0.]*3 or t['plant']['brake_gain'] != gain or t['plant']['phase'] != 'PRE_INTEGRATION_NATIVE_ACTUATOR_FORCE': raise ValueError('native parameter/phase mismatch')
        applied = np.array(decisions['force_n'])+a['disturbance_n'];applied[2]+=9.81
        if t['plant']['applied_body_force_n'] != applied.tolist(): raise ValueError('applied force mismatch')
        if t['contact_before_floor'] != old_floor or t['contact_before_obstacle'] != old_obstacle: raise ValueError('contact continuity mismatch')
        if not(old_floor or old_obstacle or p['contact_floor'] or p['contact_obstacle']):
            vn = np.array(vel)+.02*((applied+brake)/a['actual_mass_kg']+np.array(r['gravity']))
            if not np.allclose(vn,p['velocity'],rtol=0.,atol=1e-10) or not np.allclose(np.array(pos)+.02*vn,p['position'],rtol=0.,atol=1e-10): raise ValueError('native integration mismatch')
        if p['integrated_qpos'] != p['position'] or abs(p['time']-(step+1)*.02)>1e-10: raise ValueError('time/phase mismatch')
        point=np.array(p['position']);limit=r['arena_limit']-r['robot_radius']
        boundary=min(point[2]-r['robot_radius'],limit-point[2],limit-abs(point[0]),limit-abs(point[1]))
        clearance=min(float(np.linalg.norm(point-o['center'])-r['robot_radius']-o['radius']) for o in r['obstacles'])
        if abs(boundary-p['boundary_clearance'])>1e-10 or abs(clearance-p['min_obstacle_distance'])>1e-10 or p['geometric_or_contact_violation']!=bool(boundary<0 or clearance<0 or p['contact_floor'] or p['contact_obstacle']): raise ValueError('geometry/violation mismatch')
        measured = sensor.post_sensors(step,pos,vel,p,t['plant']['actuator_force_pre_n'],requested,decisions['force_n'])
        checked = controller.post(measured,start_reference=ref_start,tick=step,requested_gain=requested)
        truth={'velocity_error_m_s':float(np.linalg.norm(np.array(checked['reference_after']['velocity'])-p['velocity'])),
               'position_error_m':float(np.linalg.norm(np.array(checked['reference_after']['position'])-p['position']))}
        if measured!=s['measurements'] or checked!=s['monitor'] or truth!=s['reference_truth_scoring']: raise ValueError('sensor/feedback reconstruction mismatch')
        pos,vel=p['position'],p['velocity'];old_floor,old_obstacle=p['contact_floor'],p['contact_obstacle']
    result=summary(a,events)
    if result!=terminal['summary']:raise ValueError('summary contradiction')
    return result


def run(path):
    sources=hashes();meta={'sources':sources,'parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
       'versions':{'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__},'gate_b':'GATE_B_NOT_AUTHORIZED'}
    assignments=[dict(a,metadata=meta) for a in plan()]
    with DevelopmentLedger.create(path,study=STUDY,assignments=assignments,record_events=True) as w:
        for a in assignments:
            w.start(a['id'])
            try:
                result=run_episode(a,lambda e:w.event(a['id'],details=e));after=hashes()
                if after!=sources:raise ValueError('sources changed')
                w.complete(a['id'],status='COMPLETED',details={'summary':result,'sources_after':after})
            except (LedgerError,LedgerWriteError):raise
            except Exception as exc:
                w.complete(a['id'],status='ERROR',details={'error_type':type(exc).__name__,'error':str(exc)});raise
        w.finalize()
    return audit(path)


def audit(path):
    log=inspect(path);records=log['records'];assignments=records[0]['assignments']
    if records[0]['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan():raise ValueError('study/plan mismatch')
    meta=assignments[0]['metadata']
    if any(a['metadata']!=meta for a in assignments):raise ValueError('metadata mismatch')
    grouped,terminals={},{}
    for r in records:
        if r['kind']=='EVENT':grouped.setdefault(r['id'],[]).append(r['details'])
        elif r['kind']=='TERMINAL':terminals[r['id']]=r
    rows,complete=[],{}
    for a in assignments:
        state=log['assignments'][a['id']];result=audit_episode(a,grouped[a['id']],terminals[a['id']]['details'],meta) if state=='COMPLETED' else None
        rows.append({'id':a['id'],'state':state,'summary':result})
        if result is not None:complete[a['id']]=grouped[a['id']]
    triples=[]
    for i in range(3):
        for case in CASES:
            ids=[f'v{i}:{case}:{arm}' for arm in ARMS]
            if any(k not in complete for k in ids):triples.append({'initial_index':i,'case':case,'status':'UNEVALUABLE_INCOMPLETE'});continue
            first,second,third=(complete[k] for k in ids)
            if any(first[0][k]!=second[0][k] or first[0][k]!=third[0][k] for k in ('runtime','position','velocity','reference_anchor')):raise ValueError('matched reset/runtime/anchor mismatch')
            if any(x['noise']!=y['noise'] or x['noise']!=z['noise'] for x,y,z in zip(first[1::3],second[1::3],third[1::3])):raise ValueError('matched pose-noise mismatch')
            for xs in zip(first[3::3],second[3::3],third[3::3]):
                if any(xs[0]['measurements'][k]!=xs[1]['measurements'][k] or xs[0]['measurements'][k]!=xs[2]['measurements'][k] for k in ('force_noise','acceleration_noise')):raise ValueError('matched reference-noise mismatch')
            triples.append({'initial_index':i,'case':case,'status':'MATCHED_RESET_RUNTIME_NOISE_ONLY'})
    return {'study':STUDY,'ledger_state':log['state'],'counts':log['counts'],'metadata':meta,'assignments':rows,'matched_triples':triples,
      'classification':'DEVELOPMENT_REFERENCE_DIAGNOSTIC_NOT_CONFIRMATORY_OR_HARDWARE_VALIDATION','gate_b':'GATE_B_NOT_AUTHORIZED',
      'limitations':['Initial anchor/acceleration/force sensors and error/frame/clock bounds are unverified model assumptions.',
        'Virtual acceleration is interval-mean world-frame velocity change, not raw hardware IMU data.',
        'Consistency does not identify the faulty channel or establish rest/fallback sufficiency.',
        'Coherent joint sensor/model spoofing and insufficient brake authority remain possible.',
        'No independent native-runtime provenance, safety certification or population inference.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('ledger',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output already exists')
    result=run(a.ledger) if a.mode=='run' else audit(a.ledger)
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'state':result['ledger_state'],'counts':result['counts']}))


if __name__=='__main__':main()
