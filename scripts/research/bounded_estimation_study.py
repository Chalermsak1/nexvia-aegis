#!/usr/bin/env python3
"""Fixed DEVELOPMENT-only sensor-bound braking diagnostic, not task validation.

Direct force application bypasses the truth-state CBF. On NO_COMMAND this
simulation deliberately applies zero incremental force plus ideal gravity
compensation and CONTINUES physics. That is a recorded diagnostic choice, NOT
an operational fallback, safe hover, collision avoidance, or stopping claim.
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from aegis.development.bounded_braking import BoundedStatePacket, BoundedStateGate, braking_command
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect

STUDY = 'V9-M5 bounded estimation braking diagnostic v1'
CASES = ('nominal', 'reversal_reported', 'reversal_unreported', 'underreported',
         'delayed', 'stale', 'replay', 'missing', 'bounds_missing')
ARMS = ('POINT_ESTIMATE', 'BOUNDED_ESTIMATE')
STEPS = 80
FILES = ('src/aegis/development/__init__.py', 'src/aegis/development/bounded_braking.py',
         'scripts/research/bounded_estimation_study.py', 'src/aegis/env/mujoco_3d_cbf.py',
         'scripts/research/development_ledger.py')


def source_hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in FILES}


def plan():
    # These are explicit new development RNG stream keys, not reserved seed files.
    return [{'id': f'w{world}:{case}:{arm}', 'world': world, 'rng_key': [20261116, world],
             'case': case, 'arm': arm, 'steps': STEPS} for world in range(3) for case in CASES for arm in ARMS]


def gate():
    return BoundedStateGate(max_age_seconds=.08, acceleration_norm_upper_m_s2=2.)


def choose(g, packet, now, arm):
    estimate, reason = g.accept(packet, now_seconds=now)
    command = braking_command(estimate, force_norm_limit_n=2., use_uncertainty=arm == 'BOUNDED_ESTIMATE', hold_seconds=.02, mass_kg=1.)
    snapshot = asdict(estimate) if estimate else None
    if snapshot is not None:
        snapshot['position'] = list(snapshot['position'])
        snapshot['velocity'] = list(snapshot['velocity'])
    return {'input_reason': reason, 'estimate': snapshot, 'command': command}


def score(estimate, pos, vel, force):
    # Simulator truth is used ONLY after choose(). No feedback to gate/command.
    pos, vel, force = np.array(pos), np.array(vel), np.array(force)
    if estimate is None:
        pe = ve = contains = None
    else:
        pe = float(np.linalg.norm(pos - estimate['position']))
        ve = float(np.linalg.norm(vel - estimate['velocity']))
        contains = bool(pe <= estimate['position_error_m'] + 1e-10 and ve <= estimate['velocity_error_m_s'] + 1e-10)
    return {'position_error_for_scoring_m': pe, 'velocity_error_for_scoring_m_s': ve,
            'declared_ball_contains_truth_for_scoring': contains,
            'force_dot_true_velocity_before_w': float(np.dot(force, vel))}


def summary(events):
    controls = [e for e in events if e['type'] == 'CONTROL']
    physics = [e for e in events if e['type'] == 'PHYSICS']
    return {'controls': len(controls), 'physics_steps': len(physics),
            'commands_proposed': sum(e['selection']['command']['status'] == 'COMMAND_PROPOSED' for e in controls),
            'no_command': sum(e['selection']['command']['status'] == 'NO_COMMAND' for e in controls),
            'declared_bound_violations_for_scoring': sum(e['scoring']['declared_ball_contains_truth_for_scoring'] is False for e in controls),
            'positive_power_samples_for_scoring': sum(e['scoring']['force_dot_true_velocity_before_w'] > 1e-10 for e in controls),
            'collision_samples': sum(e['collision'] for e in physics),
            'positive_kinetic_energy_increments_for_scoring': sum(
                float(np.dot(p['velocity_after'], p['velocity_after'])) - float(np.dot(c['velocity_before'], c['velocity_before'])) > 1e-10
                for c, p in zip(controls, physics)),
            'final_sampled_speed_m_s': float(np.linalg.norm(physics[-1]['velocity_after'])) if physics else None,
            'classification': 'DEVELOPMENT_DIAGNOSTIC_NO_SAFETY_PASS'}


def run_assignment(a, emit):
    env = AegisMuJoCo3DEnvironment()
    world_rng = np.random.default_rng(np.random.SeedSequence(a['rng_key'] + [0]))
    noise_rng = np.random.default_rng(np.random.SeedSequence(a['rng_key'] + [1]))
    env.reset(world_rng)
    env.data.qpos[:3] = [-2., -2., 1.3]
    env.data.qvel[:3] = [.4 + .2 * world_rng.random(), 0., 0.]
    mujoco.mj_forward(env.model, env.data)
    runtime = {'dt': float(env.model.opt.timestep), 'mass': float(env.model.body_mass[env.robot_body_id]),
               'gravity': env.model.opt.gravity.tolist(), 'integrator': int(env.model.opt.integrator),
               'robot_radius': env.config.robot_radius, 'arena_limit': env.config.arena_limit,
               'obstacles': [{'center': o.center.tolist(), 'radius': o.radius} for o in env.obstacles],
               'cbf_used': False, 'no_command_simulation_action': 'ZERO_INCREMENTAL_FORCE_IDEAL_GRAVITY_COMPENSATION'}
    if runtime['dt'] != .02 or runtime['mass'] != 1. or runtime['gravity'] != [0., 0., -9.81]:
        raise ValueError('unsupported development runtime')
    s = env.get_state()
    emit({'type': 'RESET', 'runtime': runtime, 'position': s['robot_pos'].tolist(),
          'velocity': s['robot_velocity'].tolist(), 'collision': bool(s['safety_violation'])})
    history, events, previous_packet = [], [], None
    g = gate()
    for step in range(a['steps']):
        mujoco.mj_forward(env.model, env.data)
        s = env.get_state()
        now = float(env.data.time)
        pos, vel = s['robot_pos'].copy(), s['robot_velocity'].copy()
        history.append((now, pos, vel))
        lag = min(3 if a['case'] == 'delayed' else 6 if a['case'] == 'stale' else 0, max(0, step - 5))
        acquired, mp, mv = history[max(0, step - lag)]
        pn = noise_rng.uniform(-.01 / math.sqrt(3), .01 / math.sqrt(3), 3)
        vn = noise_rng.uniform(-.02 / math.sqrt(3), .02 / math.sqrt(3), 3)
        pv, vv, radius = mp + pn, mv + vn, .02
        if step >= 6:
            if a['case'] in ('reversal_reported', 'reversal_unreported'):
                vv = -mv + vn
                if a['case'] == 'reversal_reported':
                    radius += 2 * float(np.linalg.norm(mv))
            elif a['case'] == 'underreported':
                vv = .25 * mv + vn  # Deliberately undeclared fault.
        packet = BoundedStatePacket(pv.tolist(), vv.tolist(), .01, radius, step, acquired,
                                    'WORLD', 'SIM_STATE_SENSOR_V1', 'SYNTHETIC_BOUNDED_UNIFORM_PLUS_DECLARED_FAULT')
        if step >= 6:
            if a['case'] == 'replay':
                packet = previous_packet  # Exact replay, not freshly relabeled data.
            elif a['case'] == 'missing':
                packet = None
            elif a['case'] == 'bounds_missing':
                packet = BoundedStatePacket(pv.tolist(), vv.tolist(), .01, None, step, acquired,
                                            'WORLD', 'SIM_STATE_SENSOR_V1', 'MISSING_VELOCITY_BOUND')
        selection = choose(g, packet, now, a['arm'])
        previous_packet = packet
        force = selection['command']['force_n'] or [0., 0., 0.]
        e = {'type': 'CONTROL', 'step': step, 'now_seconds': now,
             'packet': asdict(packet) if packet else None, 'selection': selection,
             'noise_position': pn.tolist(), 'noise_velocity': vn.tolist(),
             'position_before': pos.tolist(), 'velocity_before': vel.tolist(),
             'applied_incremental_force_n': force,
             'scoring': score(selection['estimate'], pos, vel, force)}
        emit(e); events.append(e)  # Durable decision BEFORE physics; sink failure stops.
        applied = np.array(force, dtype=float)
        if np.linalg.norm(applied) > 2. + 1e-10:
            raise ValueError('force exceeds declared acceleration model')
        applied[2] += 9.81
        env.data.xfrc_applied[env.robot_body_id, :3] = applied
        # Deliberately no env.step(), no truth-state CBF or true-velocity damping.
        mujoco.mj_step(env.model, env.data)
        env.step_count += 1
        mujoco.mj_forward(env.model, env.data)
        after = env.get_state()
        e = {'type': 'PHYSICS', 'step': step, 'time_after_seconds': float(env.data.time),
             'position_after': after['robot_pos'].tolist(), 'velocity_after': after['robot_velocity'].tolist(),
             'collision': bool(after['safety_violation']), 'contact_floor': bool(after['contact_floor']),
             'contact_obstacle': bool(after['contact_obstacle']),
             'boundary_clearance': after['boundary_clearance'],
             'min_obstacle_distance': after['min_obstacle_distance']}
        emit(e); events.append(e)
    return summary(events)


def run(path):
    sources = source_hashes()
    metadata = {'sources': sources, 'parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'mujoco': mujoco.__version__},
                'not_confirmatory': True, 'gate_b': 'GATE_B_NOT_AUTHORIZED'}
    assignments = [dict(a, metadata=metadata) for a in plan()]
    with DevelopmentLedger.create(path, study=STUDY, assignments=assignments, record_events=True) as ledger:
        for a in assignments:
            ledger.start(a['id'])
            try:
                result = run_assignment(a, lambda event: ledger.event(a['id'], details=event))
                after = source_hashes()
                if after != sources:
                    raise ValueError('executed sources changed')
                ledger.complete(a['id'], status='COMPLETED', details={'summary': result, 'sources_after': after})
            except (LedgerError, LedgerWriteError):
                raise
            except Exception as exc:
                ledger.complete(a['id'], status='ERROR', details={'error_type': type(exc).__name__, 'error': str(exc)})
                raise  # Retain ERROR and all remaining ASSIGNED; no implicit retry.
        ledger.finalize()
    return audit(path)


def audit(path):
    log = inspect(path)
    records = log['records']
    if records[0]['study'] != STUDY:
        raise ValueError('wrong study')
    assignments = records[0]['assignments']
    if [{k: v for k, v in a.items() if k != 'metadata'} for a in assignments] != plan():
        raise ValueError('assignment plan mismatch')
    metadata = assignments[0]['metadata']
    if any(a['metadata'] != metadata for a in assignments):
        raise ValueError('source/runtime metadata mismatch')
    results, evidence = [], {}
    for a in assignments:
        ev = [r['details'] for r in records if r['kind'] == 'EVENT' and r['id'] == a['id']]
        terminal = [r for r in records if r['kind'] == 'TERMINAL' and r['id'] == a['id']]
        if log['assignments'][a['id']] != 'COMPLETED':
            results.append({'id': a['id'], 'state': log['assignments'][a['id']], 'summary': None})
            continue
        if len(ev) != 1 + 2 * a['steps'] or ev[0]['type'] != 'RESET' or len(terminal) != 1:
            raise ValueError('missing physics or reset evidence')
        if terminal[0]['details']['sources_after'] != metadata['sources']:
            raise ValueError('source identity changed')
        runtime = ev[0]['runtime']
        if runtime['dt'] != .02 or runtime['mass'] != 1. or runtime['gravity'] != [0., 0., -9.81] or runtime['cbf_used'] is not False:
            raise ValueError('unsupported runtime')
        g = gate()
        last_pos, last_vel = ev[0]['position'], ev[0]['velocity']
        for step in range(a['steps']):
            c, p = ev[1 + 2 * step:3 + 2 * step]
            if c['type'] != 'CONTROL' or p['type'] != 'PHYSICS' or c['step'] != step or p['step'] != step:
                raise ValueError('control/physics ordering mismatch')
            if c['position_before'] != last_pos or c['velocity_before'] != last_vel:
                raise ValueError('state continuity mismatch')
            if abs(c['now_seconds'] - step * runtime['dt']) > 1e-10 or abs(p['time_after_seconds'] - (step + 1) * runtime['dt']) > 1e-10:
                raise ValueError('time mismatch')
            packet = BoundedStatePacket(**c['packet']) if c['packet'] else None
            selection = choose(g, packet, c['now_seconds'], a['arm'])
            # Normalize tuples through JSON so raw reader types match dataclasses.
            if json.loads(json.dumps(selection)) != c['selection']:
                raise ValueError('decision reconstruction mismatch')
            force = selection['command']['force_n'] or [0., 0., 0.]
            if force != c['applied_incremental_force_n'] or score(selection['estimate'], c['position_before'], c['velocity_before'], force) != c['scoring']:
                raise ValueError('force or scoring mismatch')
            pos = np.array(p['position_after'])
            boundary = min(pos[2] - runtime['robot_radius'], runtime['arena_limit'] - runtime['robot_radius'] - pos[2],
                           runtime['arena_limit'] - runtime['robot_radius'] - abs(pos[0]), runtime['arena_limit'] - runtime['robot_radius'] - abs(pos[1]))
            obstacle = min(float(np.linalg.norm(pos - o['center']) - runtime['robot_radius'] - o['radius']) for o in runtime['obstacles'])
            if abs(boundary - p['boundary_clearance']) > 1e-10 or abs(obstacle - p['min_obstacle_distance']) > 1e-10:
                raise ValueError('geometry mismatch')
            if p['collision'] != bool(boundary < 0 or obstacle < 0 or p['contact_floor'] or p['contact_obstacle']):
                raise ValueError('collision evidence mismatch')
            if not p['contact_floor'] and not p['contact_obstacle']:
                expected_velocity = np.array(c['velocity_before']) + np.array(force) * runtime['dt'] / runtime['mass']
                if not np.allclose(p['velocity_after'], expected_velocity, rtol=0., atol=1e-10):
                    raise ValueError('force/velocity impulse mismatch')
                expected_position = np.array(c['position_before']) + expected_velocity * runtime['dt']
                if runtime['integrator'] != 0 or not np.allclose(pos, expected_position, rtol=0., atol=1e-10):
                    raise ValueError('integration phase mismatch')
            last_pos, last_vel = p['position_after'], p['velocity_after']
        evidence[a['id']] = ev
        calculated = summary(ev)
        if terminal[0]['details']['summary'] != calculated:
            raise ValueError('summary mismatch')
        results.append({'id': a['id'], 'state': 'COMPLETED', 'summary': calculated})
    pair_checks = []
    for world in range(3):
        for case in CASES:
            ids = [f'w{world}:{case}:{arm}' for arm in ARMS]
            if any(identifier not in evidence for identifier in ids):
                pair_checks.append({'world': world, 'case': case, 'status': 'UNEVALUABLE_INCOMPLETE_PAIR'})
                continue
            first, second = (evidence[identifier] for identifier in ids)
            if first[0] != second[0]:
                raise ValueError('paired reset/runtime mismatch')
            for c1, c2 in zip(first[1::2], second[1::2]):
                if any(c1[key] != c2[key] for key in ('step', 'now_seconds', 'noise_position', 'noise_velocity')):
                    raise ValueError('paired innovation/timing mismatch')
            pair_checks.append({'world': world, 'case': case, 'status': 'MATCHED_RESET_RUNTIME_INNOVATIONS_ONLY'})
    return {'study': STUDY, 'ledger_state': log['state'], 'assignment_counts': log['counts'],
            'source_metadata': metadata, 'assignments': results, 'pair_checks': pair_checks,
            'classification': 'DEVELOPMENT_ONLY_NOT_A_SAFETY_OR_CONFIRMATORY_PASS',
            'limitations': ['Caller bounds are assumptions, not authenticated truth.',
                            'Zero force plus ideal gravity compensation is a diagnostic, not a physical fallback.',
                            'No obstacle-avoidance filter or recovery/stopping guarantee.',
                            'Dependent trajectories: three development worlds, shared innovations.',
                            'Hash chains and replayed arithmetic are not independent simulator authentication.'],
            'gate_b': 'GATE_B_NOT_AUTHORIZED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'audit'))
    parser.add_argument('path', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists')
    result = run(args.path) if args.mode == 'run' else audit(args.path)
    with args.output.open('x') as out:
        json.dump(result, out, indent=2, allow_nan=False); out.write('\n')
    print(json.dumps({'ledger_state': result['ledger_state'], 'counts': result['assignment_counts']}))


if __name__ == '__main__':
    main()
