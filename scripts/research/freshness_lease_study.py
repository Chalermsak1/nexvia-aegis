#!/usr/bin/env python3
"""Exploratory assurance faults in a NEW three-slide-joint MuJoCo plant.

Separately scheduled capture/lease checks are simulation assumptions, not real
hardware independence or authenticated clocks. Preserves physics when command
production, monitoring or fallback scheduling fails. Never a V9-M4 evaluation.
"""
from dataclasses import asdict, replace
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'src'))
from aegis.development.assurance_gateway import CaptureWitness, FreshnessGateway, CommandLease, LeaseWatchdog
from aegis.development.bounded_braking import BoundedStatePacket
from aegis.development.dual_source_braking import SourceBrakeSupervisor, SimulatedDamperSwitch
from aegis.development.sampled_motion_reference import sampled_motion_reference
from aegis.env.mujoco_lease_brake import ForceLimitedBrakeEnvironment
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect

STUDY = 'V9-M5 capture freshness, command lease and capped brake diagnostic v1'
CASES = ('nominal', 'retimed_cache', 'payload_substitution', 'controller_stall', 'long_lease',
         'shared_reverse', 'compromised_witness', 'shared_scheduler_stall', 'brake_unavailable',
         'limited_brake_disturbance', 'persistent_disturbance', 'mass_gravity_offset', 'watchdog_clock_freeze')
ARMS = ('DUAL_HOLD', 'LEASE', 'WITNESS_LEASE')
STEPS = 80
FILES = ('src/aegis/development/__init__.py', 'src/aegis/development/bounded_braking.py',
         'src/aegis/development/dual_source_braking.py', 'src/aegis/development/assurance_gateway.py',
         'src/aegis/development/sampled_motion_reference.py', 'src/aegis/env/mujoco_3d_cbf.py',
         'src/aegis/env/mujoco_lease_brake.py', 'scripts/research/development_ledger.py',
         'scripts/research/freshness_lease_study.py')


def hashes(): return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}


def plan():
    return [{'id': f'v{i}:{case}:{arm}', 'initial_index': i, 'initial_speed_m_s': speed, 'case': case,
             'arm': arm, 'steps': STEPS, 'sensor_rng_keys': [[20261116, 3, i, 0], [20261116, 3, i, 1]],
             'actual_mass_kg': 1.5 if case == 'mass_gravity_offset' else 1.,
             'brake_cap_per_axis_n': .05 if case == 'limited_brake_disturbance' else 1.,
             'disturbance_n': [.2, 0., 0.] if case in ('limited_brake_disturbance', 'persistent_disturbance') else [0., 0., 0.],
             'design_disturbance_upper_n': 5. if case == 'mass_gravity_offset' else .2 if case in ('limited_brake_disturbance', 'persistent_disturbance') else 0.}
            for i, speed in enumerate((.4, .5, .6)) for case in CASES for arm in ARMS]


def noise_sample(rngs):
    return [{'position': rng.uniform(-ep / math.sqrt(3), ep / math.sqrt(3), 3).tolist(),
             'velocity': rng.uniform(-ev / math.sqrt(3), ev / math.sqrt(3), 3).tolist()}
            for rng, ep, ev in zip(rngs, (.01, .015), (.02, .03))]


class Logic:
    """No environment parameter; receives only noisy measured state upstream.

    The study's capture producer below is deliberately outside the controller.
    Truth is supplied only to that measurement producer and to scoring/physics.
    """
    def __init__(self, a):
        self.a = a
        self.witness, self.gateway = CaptureWitness(), FreshnessGateway()
        self.controller, self.guard = SourceBrakeSupervisor(), LeaseWatchdog()
        self.switch = SimulatedDamperSwitch(enabled=True)
        self.captured, self.held_force, self.last_output = [], [0., 0., 0.], None
        self.last_lease = None

    def tick(self, step, capture_input):
        a = self.a; now = step * .02
        if a['case'] == 'shared_scheduler_stall' and step >= 6:
            # Whole shared scheduler stops; plant continues its zero-order hold.
            return dict(self.last_output, scheduled=False, controller_scheduled=False,
                        capture_packets=[], capture_receipts=[], deliveries=[], witness_verdicts=[],
                        lease_submitted=None, monitor_scheduled=False)
        receipts, captured = [], []
        for source, ep, ev, measurement in zip(('SIM_PRIMARY', 'SIM_SECONDARY'), (.01, .015), (.02, .03), capture_input):
            p, v = measurement['position'], measurement['velocity']
            if step >= 6 and a['case'] == 'shared_reverse': v = [-x for x in v]
            if step >= 6 and a['case'] == 'compromised_witness':
                old = self.captured[step - 3][0 if source == 'SIM_PRIMARY' else 1]
                p, v = old.position, old.velocity  # Trusted layer itself falsely certifies old values as new.
            packet = BoundedStatePacket(list(p), list(v), ep, ev, step, now, 'WORLD', source, 'SIMULATED_BOUNDED_STATE_CAPTURE')
            captured.append(packet); receipts.append(self.witness.capture(packet, tick=step))
        self.captured.append(captured)
        delivered, ids = list(captured), [r['id'] for r in receipts]
        if step >= 6 and a['case'] in ('retimed_cache', 'payload_substitution'):
            delivered = [replace(p, sequence=step, acquired_seconds=now) for p in self.captured[step - 3]]
            if a['case'] == 'retimed_cache': ids = [f'{p.source}:{step - 3}' for p in delivered]
        verdicts = [self.gateway.check(p, rid, tick=step, witness=self.witness) for p, rid in zip(delivered, ids)] if a['arm'] == 'WITNESS_LEASE' else []
        fresh = all(v['accepted'] for v in verdicts) if verdicts else None
        controller_scheduled = not (a['case'] == 'controller_stall' and step >= 6)
        selection = self.controller.choose(*delivered, now_seconds=now) if controller_scheduled and fresh is not False else None
        refusal = (selection is not None and selection['status'] == 'NO_COMMAND') or fresh is False
        lease = None
        if selection is not None and selection['status'] == 'COMMAND_PROPOSED':
            lease = CommandLease(step, step, step + (20 if a['case'] == 'long_lease' and step >= 6 else 1), selection['force_n'])
        guard_tick = 5 if a['case'] == 'watchdog_clock_freeze' and step >= 6 else step
        if a['arm'] == 'DUAL_HOLD':
            if refusal: self.held_force = [0., 0., 0.]
            elif lease is not None: self.held_force = list(lease.force_n)
            guarded = None; request = refusal
        else:
            guarded = self.guard.advance(tick=guard_tick, command=lease, refusal=refusal, freshness_ok=fresh)
            self.held_force = list(guarded['force_n']); request = guarded['fallback_requested']
        if lease is not None: self.last_lease = lease
        switched = self.switch.advance(step=step, request=request, available=a['case'] != 'brake_unavailable')
        result = {'scheduled': True, 'controller_scheduled': controller_scheduled,
                  'capture_packets': [asdict(p) for p in captured], 'capture_receipts': receipts,
                  'deliveries': [{'packet': asdict(p), 'receipt_id': rid} for p, rid in zip(delivered, ids)],
                  'witness_verdicts': verdicts, 'selection': selection, 'lease_submitted': asdict(lease) if lease else None,
                  'monitor_scheduled': a['arm'] != 'DUAL_HOLD', 'monitor_tick': guard_tick if a['arm'] != 'DUAL_HOLD' else None,
                  'watchdog': guarded, 'switch': switched, 'force_n': list(self.held_force),
                  'last_lease_expires_tick': self.last_lease.expires_tick if self.last_lease else None,
                  'brake_gain': switched['requested_damping_kg_s']}
        self.last_output = result
        return result


def measured_inputs(pos, vel, noise):
    return [{'position': (np.array(pos) + n['position']).tolist(), 'velocity': (np.array(vel) + n['velocity']).tolist()} for n in noise]


def scoring(pos, vel, logic):
    errors = []
    for delivered in logic['deliveries']:
        p = delivered['packet']
        pe, ve = float(np.linalg.norm(np.array(p['position']) - pos)), float(np.linalg.norm(np.array(p['velocity']) - vel))
        errors.append({'position_error_m': pe, 'velocity_error_m_s': ve,
                       'declared_ball_contains_current_truth': bool(pe <= p['position_error_m'] + 1e-10 and ve <= p['velocity_error_m_s'] + 1e-10)})
    return {'raw_delivery_errors': errors, 'command_power_w': float(np.dot(logic['force_n'], vel))}


def summarize(a, events):
    ticks, physics = [e for e in events if e['type'] == 'TICK'], [e for e in events if e['type'] == 'PHYSICS']
    contact = any(p['contact_floor'] or p['contact_obstacle'] for p in physics)
    first_request = next((t['step'] for t in ticks if t['logic']['switch']['request_step'] is not None), None)
    path = sum(float(np.linalg.norm(np.array(p['position']) - t['position_before'])) for t, p in zip(ticks, physics))
    ref = sampled_motion_reference(initial_speed_upper_m_s=.65, steps=a['steps'], dt_seconds=.02,
            mass_lower_kg=1., command_force_upper_n=2., disturbance_force_upper_n=a['design_disturbance_upper_n'], damping_gain_upper_kg_s=2.)
    return {'tick_events': len(ticks), 'physics_steps': len(physics), 'first_fallback_request_step': first_request,
            'freshness_rejected_ticks': sum(bool(t['logic']['witness_verdicts']) and not all(v['accepted'] for v in t['logic']['witness_verdicts']) for t in ticks),
            'watchdog_fallback_ticks': sum(t['logic']['watchdog'] is not None and t['logic']['watchdog']['fallback_requested'] for t in ticks),
            'expired_lease_force_ticks': sum(bool(t['logic']['last_lease_expires_tick'] is not None and t['step'] >= t['logic']['last_lease_expires_tick'] and np.linalg.norm(t['logic']['force_n']) > 0) for t in ticks),
            'positive_command_power_ticks': sum(t['scoring']['command_power_w'] > 1e-10 for t in ticks),
            'brake_saturation_ticks': sum(any(abs(f) >= a['brake_cap_per_axis_n'] - 1e-12 for f in t['plant']['actuator_force_pre_n']) for t in ticks),
            'unavailable_brake_ticks': sum(t['logic']['switch']['state'] == 'FAILED_UNAVAILABLE' for t in ticks),
            'geometric_or_contact_violation_samples': sum(p['geometric_or_contact_violation'] for p in physics),
            'contact_samples': sum(p['contact_floor'] or p['contact_obstacle'] for p in physics),
            'final_sampled_speed_m_s': float(np.linalg.norm(physics[-1]['velocity'])), 'sampled_path_m': path,
            'design_motion_reference': ref, 'design_reference_evaluation': 'UNEVALUABLE_CONTACT' if contact else 'CONDITIONAL_SAMPLED_CHECK',
            'path_exceeds_design_bound': None if contact or ref['sampled_path_upper_m'] is None else path > ref['sampled_path_upper_m'] + 1e-10,
            'classification': 'EXPLORATORY_ASSURANCE_DIAGNOSTIC_NOT_A_SAFETY_PASS'}


def run_episode(a, emit):
    env = ForceLimitedBrakeEnvironment(actual_mass_kg=a['actual_mass_kg'], brake_cap_per_axis_n=a['brake_cap_per_axis_n'])
    initial = env.reset_development(a['initial_speed_m_s'])
    emit({'type': 'RESET', 'runtime': env.runtime_record(), 'position': initial['robot_pos'].tolist(), 'velocity': initial['robot_velocity'].tolist()})
    rngs = [np.random.default_rng(k) for k in a['sensor_rng_keys']]; logic = Logic(a); events = []
    for step in range(a['steps']):
        state = env.get_state(); pos, vel = state['robot_pos'].tolist(), state['robot_velocity'].tolist()
        noise = noise_sample(rngs)
        decisions = logic.tick(step, measured_inputs(pos, vel, noise))
        plant = env.prepare_forces(decisions['force_n'], a['disturbance_n'], brake_gain=decisions['brake_gain'])
        e = {'type': 'TICK', 'step': step, 'position_before': pos, 'velocity_before': vel, 'noise': noise,
             'logic': decisions, 'plant': plant, 'scoring': scoring(pos, vel, decisions),
             'contact_before_floor': bool(state['contact_floor']), 'contact_before_obstacle': bool(state['contact_obstacle'])}
        emit(e); events.append(e)  # Persist force/switch/lease intent BEFORE integrating.
        e = dict(env.advance_prepared(), type='PHYSICS', step=step)
        emit(e); events.append(e)
    return summarize(a, events)


def audit_episode(a, events, terminal, meta):
    if len(events) != 1 + 2 * a['steps'] or events[0]['type'] != 'RESET': raise ValueError('missing tick/physics evidence')
    r = events[0]['runtime']
    expected_runtime = ForceLimitedBrakeEnvironment(actual_mass_kg=a['actual_mass_kg'], brake_cap_per_axis_n=a['brake_cap_per_axis_n']).runtime_record()
    if r != expected_runtime: raise ValueError('compiled runtime/geometry/XML mismatch')
    if (r['environment_id'] != ForceLimitedBrakeEnvironment.ENVIRONMENT_ID or r['dt'] != .02 or r['mass_kg'] != a['actual_mass_kg'] or
        r['gravity'] != [0., 0., -9.81] or r['integrator'] != 0 or (r['nq'], r['nv'], r['nu']) != (3, 3, 3) or
        r['actuator_forcerange'] != [[-a['brake_cap_per_axis_n'], a['brake_cap_per_axis_n']]] * 3 or not all(r['actuator_forcelimited'])): raise ValueError('runtime mismatch')
    if terminal['sources_after'] != meta['sources']: raise ValueError('source identity mismatch')
    if events[0]['position'] != [-2., -2., 1.3] or events[0]['velocity'] != [a['initial_speed_m_s'], 0., 0.]: raise ValueError('reset mismatch')
    logic = Logic(a); rngs = [np.random.default_rng(k) for k in a['sensor_rng_keys']]
    pos, vel = events[0]['position'], events[0]['velocity']
    contact_floor_before = contact_obstacle_before = False
    for step in range(a['steps']):
        t, p = events[1 + 2 * step:3 + 2 * step]
        if t['type'] != 'TICK' or p['type'] != 'PHYSICS' or t['step'] != step or p['step'] != step: raise ValueError('event order mismatch')
        if t['position_before'] != pos or t['velocity_before'] != vel: raise ValueError('state continuity mismatch')
        noise = noise_sample(rngs)
        if t['noise'] != noise: raise ValueError('noise mismatch')
        decisions = logic.tick(step, measured_inputs(pos, vel, noise))
        if decisions != t['logic'] or scoring(pos, vel, decisions) != t['scoring']: raise ValueError('assurance reconstruction mismatch')
        force, gain = decisions['force_n'], decisions['brake_gain']
        if (t['plant']['native_gain'] != [gain] * 3 or t['plant']['native_velocity_bias'] != [-gain] * 3 or
            t['plant']['native_target_velocity'] != [0.] * 3): raise ValueError('native actuator parameter mismatch')
        brake = np.clip(-gain * np.array(vel), -a['brake_cap_per_axis_n'], a['brake_cap_per_axis_n'])
        if not np.allclose(t['plant']['actuator_force_pre_n'], brake, rtol=0., atol=1e-12) or not np.allclose(t['plant']['generalized_brake_force_pre_n'], brake, rtol=0., atol=1e-12): raise ValueError('native brake force/cap mismatch')
        applied = np.array(force) + a['disturbance_n']; applied[2] += 9.81
        if t['plant']['applied_body_force_n'] != applied.tolist() or t['plant']['brake_gain'] != gain or t['plant']['phase'] != 'PRE_INTEGRATION_NATIVE_ACTUATOR_FORCE': raise ValueError('force phase mismatch')
        if abs(p['time'] - (step + 1) * .02) > 1e-10 or p['integrated_qpos'] != p['position']: raise ValueError('phase/time mismatch')
        if t['contact_before_floor'] != contact_floor_before or t['contact_before_obstacle'] != contact_obstacle_before: raise ValueError('contact continuity mismatch')
        if not (p['contact_floor'] or p['contact_obstacle'] or contact_floor_before or contact_obstacle_before):
            velocity = np.array(vel) + .02 * ((applied + brake) / a['actual_mass_kg'] + np.array(r['gravity']))
            if not np.allclose(p['velocity'], velocity, rtol=0., atol=1e-10): raise ValueError('native impulse mismatch')
            if not np.allclose(p['position'], np.array(pos) + .02 * velocity, rtol=0., atol=1e-10): raise ValueError('position integration mismatch')
        point = np.array(p['position']); limit = r['arena_limit'] - r['robot_radius']
        boundary = min(point[2] - r['robot_radius'], limit - point[2], limit - abs(point[0]), limit - abs(point[1]))
        clearance = min(float(np.linalg.norm(point - o['center']) - r['robot_radius'] - o['radius']) for o in r['obstacles'])
        if abs(p['boundary_clearance'] - boundary) > 1e-10 or abs(p['min_obstacle_distance'] - clearance) > 1e-10: raise ValueError('geometry mismatch')
        if p['geometric_or_contact_violation'] != bool(boundary < 0 or clearance < 0 or p['contact_floor'] or p['contact_obstacle']): raise ValueError('violation inconsistency')
        pos, vel = p['position'], p['velocity']
        contact_floor_before, contact_obstacle_before = p['contact_floor'], p['contact_obstacle']
    result = summarize(a, events)
    if terminal['summary'] != result: raise ValueError('summary mismatch')
    return result


def run(path):
    sources = hashes(); meta = {'sources': sources, 'parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'mujoco': mujoco.__version__}, 'gate_b': 'GATE_B_NOT_AUTHORIZED'}
    assignments = [dict(a, metadata=meta) for a in plan()]
    with DevelopmentLedger.create(path, study=STUDY, assignments=assignments, record_events=True) as w:
        for a in assignments:
            w.start(a['id'])
            try:
                result = run_episode(a, lambda e: w.event(a['id'], details=e)); after = hashes()
                if after != sources: raise ValueError('sources changed')
                w.complete(a['id'], status='COMPLETED', details={'summary': result, 'sources_after': after})
            except (LedgerError, LedgerWriteError): raise
            except Exception as exc:
                w.complete(a['id'], status='ERROR', details={'error_type': type(exc).__name__, 'error': str(exc)}); raise
        w.finalize()
    return audit(path)


def audit(path):
    log = inspect(path); records = log['records']; assignments = records[0]['assignments']
    if records[0]['study'] != STUDY or [{k: v for k, v in a.items() if k != 'metadata'} for a in assignments] != plan(): raise ValueError('study/assignment mismatch')
    meta = assignments[0]['metadata']
    if any(a['metadata'] != meta for a in assignments): raise ValueError('metadata mismatch')
    grouped, terminal = {}, {}
    for r in records:
        if r['kind'] == 'EVENT': grouped.setdefault(r['id'], []).append(r['details'])
        elif r['kind'] == 'TERMINAL': terminal[r['id']] = r
    rows, completed = [], {}
    for a in assignments:
        state = log['assignments'][a['id']]
        result = audit_episode(a, grouped[a['id']], terminal[a['id']]['details'], meta) if state == 'COMPLETED' else None
        rows.append({'id': a['id'], 'state': state, 'summary': result})
        if result is not None: completed[a['id']] = grouped[a['id']]
    matched = []
    for i in range(3):
        for case in CASES:
            ids = [f'v{i}:{case}:{arm}' for arm in ARMS]
            if any(k not in completed for k in ids):
                matched.append({'initial_index': i, 'case': case, 'status': 'UNEVALUABLE_INCOMPLETE'}); continue
            first, second, third = (completed[k] for k in ids)
            if first[0] != second[0] or first[0] != third[0]: raise ValueError('matched runtime/reset mismatch')
            if any(x['noise'] != y['noise'] or x['noise'] != z['noise'] for x, y, z in zip(first[1::2], second[1::2], third[1::2])): raise ValueError('matched noise mismatch')
            matched.append({'initial_index': i, 'case': case, 'status': 'MATCHED_RESET_RUNTIME_NOISE_ONLY'})
    return {'study': STUDY, 'ledger_state': log['state'], 'counts': log['counts'], 'metadata': meta, 'assignments': rows, 'matched_triples': matched,
            'classification': 'DEVELOPMENT_SIMULATION_NOT_CONFIRMATORY_OR_HARDWARE_VALIDATION', 'gate_b': 'GATE_B_NOT_AUTHORIZED',
            'limitations': ['Capture witness and independent scheduling are unauthed model assumptions.', 'Shared scheduler/witness/semantic failures remain possible.',
                            'New three-slide plant with hypothetical powered capped brakes; do not pool old-arm results.', 'Command energy guard remains conditional on its original zero-unmodeled-force model.',
                            'Sampled envelope is conservative, assumes no contact and takes no braking credit.', 'No real-world safe-stop, sensing accuracy or native-runtime authenticity claim.']}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('mode', choices=('run', 'audit')); p.add_argument('ledger', type=Path); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists(): p.error('output exists')
    result = run(a.ledger) if a.mode == 'run' else audit(a.ledger)
    with a.output.open('x') as f: json.dump(result, f, indent=2, allow_nan=False); f.write('\n')
    print(json.dumps({'state': result['ledger_state'], 'counts': result['counts']}))


if __name__ == '__main__': main()
