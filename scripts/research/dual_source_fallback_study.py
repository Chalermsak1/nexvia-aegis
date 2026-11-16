#!/usr/bin/env python3
"""Fixed exploratory two-source and hypothetical passive-fallback diagnostic.

No Holdout, registered evaluator, safety certification or hardware execution.
All packet-generation truth and physical damping belong to the simulation plant,
not the controller. Raw records preserve command refusals and subsequent motion.
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
import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'src'))
from aegis.development.bounded_braking import BoundedStatePacket
from aegis.development.dual_source_braking import SourceBrakeSupervisor, SimulatedDamperSwitch
from aegis.development.passive_motion_reference import passive_path_reference
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect

STUDY = 'V9-M5 dual-source union and passive-damper diagnostic v1'
CASES = ('nominal', 'primary_reverse', 'secondary_reverse', 'shared_reverse',
         'primary_reported_reverse', 'shared_retimestamped_stale', 'primary_replay',
         'secondary_missing', 'primary_position_bias', 'secondary_position_bias',
         'shared_position_bias', 'damper_unavailable')
ARMS = ('SINGLE_COAST', 'DUAL_COAST', 'DUAL_DAMPER')
STEPS = 100
FILES = ('src/aegis/development/__init__.py', 'src/aegis/development/bounded_braking.py',
         'src/aegis/development/dual_source_braking.py', 'src/aegis/development/passive_motion_reference.py',
         'src/aegis/env/mujoco_3d_cbf.py',
         'scripts/research/development_ledger.py', 'scripts/research/dual_source_fallback_study.py')


def hashes():
    return {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in FILES}


def plan():
    return [{'id': f'w{w}:{case}:{arm}', 'world': w, 'case': case, 'arm': arm, 'steps': STEPS,
             'world_rng_key': [20261116, w, 0], 'sensor_rng_keys': [[20261116, 2, w, 0], [20261116, 2, w, 1]]}
            for w in range(3) for case in CASES for arm in ARMS]


def components(a):
    return (SourceBrakeSupervisor(require_secondary=a['arm'] != 'SINGLE_COAST'),
            SimulatedDamperSwitch(enabled=a['arm'] == 'DUAL_DAMPER'))


def sample_noise(rngs):
    result = []
    for rng, ep, ev in zip(rngs, (.01, .015), (.02, .03)):
        result.append({'position': rng.uniform(-ep / math.sqrt(3), ep / math.sqrt(3), 3).tolist(),
                       'velocity': rng.uniform(-ev / math.sqrt(3), ev / math.sqrt(3), 3).tolist()})
    return result


def packets(history, step, case, noise, previous):
    """Declared synthetic fault generation; all returned metadata is scoring only."""
    delayed_index = max(0, step - 3) if step >= 6 and case == 'shared_retimestamped_stale' else step
    physical = history[delayed_index]
    now = history[-1]['time']
    out, scoring = [], []
    for source, ep, ev, innovation in zip(('SIM_PRIMARY', 'SIM_SECONDARY'), (.01, .015), (.02, .03), noise):
        p = np.array(physical['position']) + innovation['position']
        v = np.array(physical['velocity']) + innovation['velocity']
        radius = ev
        if step >= 6:
            reverse = (case == 'shared_reverse' or (source == 'SIM_PRIMARY' and case in ('primary_reverse', 'primary_reported_reverse'))
                       or (source == 'SIM_SECONDARY' and case == 'secondary_reverse'))
            if reverse:
                v = -np.array(physical['velocity']) + innovation['velocity']
                if case == 'primary_reported_reverse': radius += 2 * float(np.linalg.norm(physical['velocity']))
            if case == 'shared_position_bias' or (source == 'SIM_PRIMARY' and case == 'primary_position_bias') or (source == 'SIM_SECONDARY' and case == 'secondary_position_bias'):
                p[0] += .4
        packet = BoundedStatePacket(p.tolist(), v.tolist(), ep, radius, step, now, 'WORLD', source, 'SYNTHETIC_DECLARED_BALL_V1')
        if step >= 6 and case == 'primary_replay' and source == 'SIM_PRIMARY': packet = previous[0]
        if step >= 6 and case == 'secondary_missing' and source == 'SIM_SECONDARY': packet = None
        out.append(packet)
        if packet is None:
            scoring.append({'contains_current_truth': None, 'velocity_error_m_s': None, 'position_error_m': None})
        else:
            # Compare to CURRENT truth, deliberately revealing relabeled stale data.
            pe = float(np.linalg.norm(np.array(packet.position) - history[-1]['position']))
            ve = float(np.linalg.norm(np.array(packet.velocity) - history[-1]['velocity']))
            scoring.append({'contains_current_truth': bool(pe <= packet.position_error_m + 1e-10 and ve <= packet.velocity_error_m_s + 1e-10),
                            'velocity_error_m_s': ve, 'position_error_m': pe})
    return out, {'generated_from_physical_step': delayed_index, 'raw_packet_errors_for_scoring': scoring}


def retrospective_path_check(controls, physics):
    first = next((c for c in controls if c['selection']['status'] == 'NO_COMMAND'), None)
    if first is None:
        return {'classification': 'NOT_REQUESTED', 'reference': None, 'observed_post_refusal_path_m': None, 'exceeds_conditional_bound': None}
    start = first['step']
    travel = sum(float(np.linalg.norm(np.array(p['position']) - c['position_before']))
                 for c, p in zip(controls[start:], physics[start:]))
    result = {'classification': None, 'reference': None, 'observed_post_refusal_path_m': travel, 'exceeds_conditional_bound': None}
    if first['switch']['state'] == 'DISABLED_COAST_BASELINE':
        result['classification'] = 'NO_PASSIVE_FALLBACK_BASELINE'
        return result
    states = (first['selection']['primary'], first['selection']['secondary'])
    if any(state is None for state in states):
        result['classification'] = 'UNSUPPORTED_MISSING_ACCEPTED_STATE_BALL'
        return result
    upper = max(math.hypot(*state['velocity']) + state['velocity_error_m_s'] for state in states)
    available = any(c['switch']['state'] == 'ACTIVE_ASSUMED' for c in controls) and not any(c['switch']['state'] == 'FAILED_UNAVAILABLE' for c in controls)
    reference = passive_path_reference(speed_upper_m_s=upper, delay_upper_seconds=.06, mass_kg=1.,
                                       damping_lower_kg_s=2., persistent_force_upper_n=0., available=available)
    result.update(classification='RETROSPECTIVE_CONDITIONAL_MODEL_CHECK', reference=reference)
    if reference['additional_path_upper_m'] is not None:
        result['exceeds_conditional_bound'] = travel > reference['additional_path_upper_m'] + 1e-10
    return result


def summarize(events):
    controls, physics = [e for e in events if e['type'] == 'CONTROL'], [e for e in events if e['type'] == 'PHYSICS']
    refusals = [e for e in controls if e['selection']['status'] == 'NO_COMMAND']
    return {'control_steps': len(controls), 'physics_steps': len(physics),
            'first_refusal_step': refusals[0]['step'] if refusals else None,
            'first_refusal_reason': refusals[0]['selection']['reason'] if refusals else None,
            'command_steps': len(controls) - len(refusals),
            'positive_command_power_samples': sum(e['command_power_for_scoring_w'] > 1e-10 for e in controls),
            'kinetic_energy_increase_samples': sum(bool(np.dot(p['velocity'], p['velocity']) - np.dot(c['velocity_before'], c['velocity_before']) > 1e-10) for c, p in zip(controls, physics)),
            'primary_raw_bound_violations': sum(e['sensor_scoring']['raw_packet_errors_for_scoring'][0]['contains_current_truth'] is False for e in controls),
            'secondary_raw_bound_violations': sum(e['sensor_scoring']['raw_packet_errors_for_scoring'][1]['contains_current_truth'] is False for e in controls),
            'damper_active_steps': sum(e['switch']['state'] == 'ACTIVE_ASSUMED' for e in controls),
            'damper_failed_steps': sum(e['switch']['state'] == 'FAILED_UNAVAILABLE' for e in controls),
            'collision_samples': sum(e['collision'] for e in physics),
            'final_sampled_speed_m_s': float(np.linalg.norm(physics[-1]['velocity'])) if physics else None,
            'path_length_m': sum(float(np.linalg.norm(np.array(p['position']) - c['position_before'])) for c, p in zip(controls, physics)),
            'retrospective_path_check': retrospective_path_check(controls, physics),
            'classification': 'DEVELOPMENT_DIAGNOSTIC_NOT_A_RECOVERY_OR_SAFETY_PASS'}


def runtime_record(env):
    return {'dt': float(env.model.opt.timestep), 'mass': float(env.model.body_mass[env.robot_body_id]),
            'gravity': env.model.opt.gravity.tolist(), 'integrator': int(env.model.opt.integrator),
            'initial_dof_damping': env.model.dof_damping.tolist(),
            'robot_radius': env.config.robot_radius, 'arena_limit': env.config.arena_limit,
            'obstacles': [{'center': o.center.tolist(), 'radius': o.radius} for o in env.obstacles],
            'cbf_used': False, 'damper_model': 'HYPOTHETICAL_TRANSLATIONAL_JOINT_DAMPING',
            'damper_delay_steps': 3, 'active_damping_kg_s': 2., 'gravity_compensation': 'IDEAL'}


def run_episode(a, emit):
    env = AegisMuJoCo3DEnvironment()
    rng = np.random.default_rng(a['world_rng_key'])
    rngs = [np.random.default_rng(k) for k in a['sensor_rng_keys']]
    env.reset(rng); env.data.qpos[:3] = [-2., -2., 1.3]; env.data.qvel[:3] = [.4 + .2 * rng.random(), 0., 0.]
    mujoco.mj_forward(env.model, env.data)
    runtime = runtime_record(env)
    if runtime['dt'] != .02 or runtime['mass'] != 1. or runtime['integrator'] != 0 or runtime['gravity'] != [0., 0., -9.81] or any(runtime['initial_dof_damping']):
        raise ValueError('unsupported development model')
    initial = env.get_state()
    emit({'type': 'RESET', 'runtime': runtime, 'position': initial['robot_pos'].tolist(), 'velocity': initial['robot_velocity'].tolist(),
          'collision': bool(initial['safety_violation'])})
    supervisor, switch = components(a)
    history, events, previous = [], [], [None, None]
    for step in range(a['steps']):
        mujoco.mj_forward(env.model, env.data)
        state = env.get_state()
        now, pos, vel = float(env.data.time), state['robot_pos'].tolist(), state['robot_velocity'].tolist()
        history.append({'time': now, 'position': pos, 'velocity': vel})
        noise = sample_noise(rngs)
        measured, diagnostic = packets(history, step, a['case'], noise, previous)
        selection = supervisor.choose(*measured, now_seconds=now)
        request = selection['status'] == 'NO_COMMAND'
        switched = switch.advance(step=step, request=request, available=a['case'] != 'damper_unavailable')
        force = selection['force_n'] or [0., 0., 0.]
        event = {'type': 'CONTROL', 'step': step, 'time': now, 'position_before': pos, 'velocity_before': vel,
                 'noise': noise, 'packets': [asdict(p) if p else None for p in measured], 'selection': selection,
                 'switch': switched, 'force_n': force, 'sensor_scoring': diagnostic,
                 'command_power_for_scoring_w': float(np.dot(force, vel))}
        emit(event); events.append(event)  # Command and switch intent durable BEFORE mutation.
        env.model.dof_damping[:3] = switched['requested_damping_kg_s']
        applied = np.array(force, dtype=float); applied[2] += 9.81
        env.data.xfrc_applied[env.robot_body_id, :3] = applied
        mujoco.mj_step(env.model, env.data); env.step_count += 1
        mujoco.mj_forward(env.model, env.data)
        after = env.get_state()
        event = {'type': 'PHYSICS', 'step': step, 'time': float(env.data.time),
                 'position': after['robot_pos'].tolist(), 'velocity': after['robot_velocity'].tolist(),
                 'runtime_dof_damping': env.model.dof_damping[:3].tolist(),
                 'collision': bool(after['safety_violation']), 'contact_floor': bool(after['contact_floor']),
                 'contact_obstacle': bool(after['contact_obstacle']), 'boundary_clearance': after['boundary_clearance'],
                 'min_obstacle_distance': after['min_obstacle_distance']}
        emit(event); events.append(event)
        previous = measured
    return summarize(events)


def audit_episode(a, events, terminal, metadata):
    if len(events) != 1 + 2 * a['steps'] or events[0]['type'] != 'RESET':
        raise ValueError('incomplete control/physics horizon')
    r = events[0]['runtime']
    expected_runtime = {'dt': .02, 'mass': 1., 'gravity': [0., 0., -9.81], 'integrator': 0,
                        'initial_dof_damping': [0.] * 6, 'cbf_used': False,
                        'damper_model': 'HYPOTHETICAL_TRANSLATIONAL_JOINT_DAMPING', 'damper_delay_steps': 3,
                        'active_damping_kg_s': 2., 'gravity_compensation': 'IDEAL'}
    if any(r[k] != v for k, v in expected_runtime.items()): raise ValueError('unsupported runtime')
    if terminal['sources_after'] != metadata['sources']: raise ValueError('sources changed')
    supervisor, switch = components(a)
    rngs = [np.random.default_rng(k) for k in a['sensor_rng_keys']]
    last_pos, last_vel, history, previous = events[0]['position'], events[0]['velocity'], [], [None, None]
    for step in range(a['steps']):
        c, p = events[1 + 2 * step:3 + 2 * step]
        if c['type'] != 'CONTROL' or p['type'] != 'PHYSICS' or c['step'] != step or p['step'] != step:
            raise ValueError('control/physics ordering mismatch')
        if c['position_before'] != last_pos or c['velocity_before'] != last_vel: raise ValueError('state continuity mismatch')
        if abs(c['time'] - step * .02) > 1e-10 or abs(p['time'] - (step + 1) * .02) > 1e-10: raise ValueError('time mismatch')
        noise = sample_noise(rngs)
        if noise != c['noise']: raise ValueError('noise stream mismatch')
        history.append({'time': c['time'], 'position': last_pos, 'velocity': last_vel})
        measured, scoring = packets(history, step, a['case'], noise, previous)
        if [asdict(v) if v else None for v in measured] != c['packets'] or scoring != c['sensor_scoring']: raise ValueError('measurement/scoring provenance mismatch')
        selection = supervisor.choose(*measured, now_seconds=c['time'])
        switched = switch.advance(step=step, request=selection['status'] == 'NO_COMMAND', available=a['case'] != 'damper_unavailable')
        if selection != c['selection'] or switched != c['switch']: raise ValueError('supervisor/switch reconstruction mismatch')
        force, damping = selection['force_n'] or [0., 0., 0.], switched['requested_damping_kg_s']
        if c['force_n'] != force or c['command_power_for_scoring_w'] != float(np.dot(force, last_vel)): raise ValueError('force/power mismatch')
        if p['runtime_dof_damping'] != [damping] * 3: raise ValueError('missing/mismatched damper acknowledgement')
        # Native MuJoCo Euler integrates joint damping implicitly for this free mass.
        if not p['contact_floor'] and not p['contact_obstacle']:
            velocity = (np.array(last_vel) + np.array(force) * .02) / (1. + .02 * damping)
            if not np.allclose(p['velocity'], velocity, rtol=0., atol=1e-10): raise ValueError('passive dynamics mismatch')
            if not np.allclose(p['position'], np.array(last_pos) + velocity * .02, rtol=0., atol=1e-10): raise ValueError('integration phase mismatch')
        pos = np.array(p['position']); limit = r['arena_limit'] - r['robot_radius']
        boundary = min(pos[2] - r['robot_radius'], limit - pos[2], limit - abs(pos[0]), limit - abs(pos[1]))
        clearance = min(float(np.linalg.norm(pos - o['center']) - r['robot_radius'] - o['radius']) for o in r['obstacles'])
        if abs(p['boundary_clearance'] - boundary) > 1e-10 or abs(p['min_obstacle_distance'] - clearance) > 1e-10: raise ValueError('geometry mismatch')
        if p['collision'] != bool(boundary < 0 or clearance < 0 or p['contact_floor'] or p['contact_obstacle']): raise ValueError('collision contradiction')
        last_pos, last_vel, previous = p['position'], p['velocity'], measured
    calculated = summarize(events)
    if calculated != terminal['summary']: raise ValueError('summary contradiction')
    return calculated


def run(path):
    sources = hashes()
    metadata = {'sources': sources, 'parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'mujoco': mujoco.__version__},
                'gate_b': 'GATE_B_NOT_AUTHORIZED', 'not_confirmatory': True}
    assignments = [dict(a, metadata=metadata) for a in plan()]
    with DevelopmentLedger.create(path, study=STUDY, assignments=assignments, record_events=True) as ledger:
        for a in assignments:
            ledger.start(a['id'])
            try:
                result = run_episode(a, lambda e: ledger.event(a['id'], details=e))
                after = hashes()
                if after != sources: raise ValueError('sources changed during execution')
                ledger.complete(a['id'], status='COMPLETED', details={'summary': result, 'sources_after': after})
            except (LedgerError, LedgerWriteError): raise
            except Exception as exc:
                ledger.complete(a['id'], status='ERROR', details={'error_type': type(exc).__name__, 'error': str(exc)})
                raise
        ledger.finalize()
    return audit(path)


def audit(path):
    log = inspect(path); records = log['records']; assignments = records[0]['assignments']
    if records[0]['study'] != STUDY or [{k: v for k, v in a.items() if k != 'metadata'} for a in assignments] != plan(): raise ValueError('wrong study or assignments')
    meta = assignments[0]['metadata']
    if any(a['metadata'] != meta for a in assignments): raise ValueError('inconsistent source/runtime identities')
    grouped, terminals = {}, {}
    for r in records:
        if r['kind'] == 'EVENT': grouped.setdefault(r['id'], []).append(r['details'])
        elif r['kind'] == 'TERMINAL': terminals[r['id']] = r
    rows, complete = [], {}
    for a in assignments:
        if log['assignments'][a['id']] != 'COMPLETED':
            rows.append({'id': a['id'], 'state': log['assignments'][a['id']], 'summary': None}); continue
        result = audit_episode(a, grouped[a['id']], terminals[a['id']]['details'], meta)
        rows.append({'id': a['id'], 'state': 'COMPLETED', 'summary': result}); complete[a['id']] = grouped[a['id']]
    triples = []
    for world in range(3):
        for case in CASES:
            ids = [f'w{world}:{case}:{arm}' for arm in ARMS]
            if any(k not in complete for k in ids):
                triples.append({'world': world, 'case': case, 'status': 'UNEVALUABLE_INCOMPLETE'}); continue
            first, second, third = (complete[k] for k in ids)
            if first[0] != second[0] or first[0] != third[0]: raise ValueError('reset/runtime mismatch across arms')
            # Each source stream is separately reconstructed above; this also checks paired delivery/noise.
            for cs in zip(first[1::2], second[1::2], third[1::2]):
                if cs[0]['noise'] != cs[1]['noise'] or cs[0]['noise'] != cs[2]['noise']: raise ValueError('cross-arm noise mismatch')
            triples.append({'world': world, 'case': case, 'status': 'MATCHED_RESET_RUNTIME_NOISE_ONLY'})
    return {'study': STUDY, 'ledger_state': log['state'], 'counts': log['counts'], 'metadata': meta,
            'assignments': rows, 'matched_triples': triples, 'gate_b': 'GATE_B_NOT_AUTHORIZED',
            'classification': 'SIMULATION_DIAGNOSTIC_NOT_CONFIRMATORY_OR_HARDWARE_VALIDATION',
            'limitations': ['Sensor error bounds and at-least-one-valid-source condition are assumptions.',
                            'Compatibility cannot authenticate truth or exclude common-mode faults.',
                            'Hypothetical switchable damping and ideal gravity compensation are not available robot hardware.',
                            'Command decisions stop examining sensors after latched refusal; raw packets remain recorded/scored.',
                            'Three inspected development worlds, dependent trajectories, no reliability inference.',
                            'No collision-avoidance controller or certified recoverability envelope.',
                            'Hash chains/reconstructed arithmetic do not authenticate an independent runtime.']}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('mode', choices=('run', 'audit')); p.add_argument('ledger', type=Path); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists(): p.error('output already exists')
    result = run(args.ledger) if args.mode == 'run' else audit(args.ledger)
    with args.output.open('x') as f: json.dump(result, f, indent=2, allow_nan=False); f.write('\n')
    print(json.dumps({'state': result['ledger_state'], 'counts': result['counts']}))


if __name__ == '__main__': main()
