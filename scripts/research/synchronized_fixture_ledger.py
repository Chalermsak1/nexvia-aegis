#!/usr/bin/env python3
"""Versioned, incremental synchronized-physics fixtures; not policy evaluation."""
import argparse
from dataclasses import asdict
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
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from aegis.env.mujoco_3d_cbf import PhysicalWorld3DConfig
from aegis.env.mujoco_3d_synchronized import SynchronizedAegisMuJoCo3DEnvironment as Environment
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect_bytes
from scripts.research.evidence_integrity import validate_source_maps

STUDY = 'V9-M5 synchronized physics fixtures v1'
FILES = ['scripts/research/synchronized_fixture_ledger.py', 'scripts/research/development_ledger.py',
         'src/aegis/env/mujoco_3d_cbf.py', 'src/aegis/env/mujoco_3d_synchronized.py',
         'scripts/research/evidence_integrity.py']


CASES = [('drift_10ms', .01, [-2., -2., .5], [.1, 0., 0.], 3, False),
             ('drift_20ms', .02, [-2., -2., .5], [.5, 0., 0.], 3, False),
             ('active_braking', .02, [-2., -2., .5], [.5, 0., 0.], 5, True),
             ('floor_crossing', .02, [-2., -2., .201], [0., 0., -1.], 1, False),
             ('obstacle_crossing', .02, [-.70, 0., .5], [4., 0., 0.], 1, False),
             ('boundary_crossing', .02, [2.79, -2., .6], [2., 0., 0.], 1, False)]

def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}


def runtime_snapshot(env):
    return {'environment_id': env.ENVIRONMENT_ID, 'configuration': asdict(env.config),
            'runtime_timestep_seconds': float(env.model.opt.timestep),
            'gravity': env.model.opt.gravity.tolist(), 'integrator': int(env.model.opt.integrator),
            'robot_body_mass': float(env.model.body_mass[env.robot_body_id]),
            'robot_geom_size': env.model.geom_size[env.robot_geom_id].tolist(),
            'obstacles': [{'center': o.center.tolist(), 'radius': o.radius} for o in env.obstacles],
            'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'mujoco': mujoco.__version__}}


def assignments():
    source = hashes()
    parent = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()

    return [{'id': name, 'steps': steps, 'initial_position': pos, 'initial_velocity': vel,
             'target': [2., 2., .5], 'command': [0., 0., 0.], 'force_braking': brake,
             'development_reset_seed': 9201001, 'git_parent': parent, 'source_sha256': source,
             'runtime': runtime_snapshot(Environment(PhysicalWorld3DConfig(timestep=dt)))}
            for name, dt, pos, vel, steps, brake in CASES]


def observation(env, state, reset=False):
    return {'environment_id': env.ENVIRONMENT_ID,
            'state_phase': 'FORWARD_REFRESH_RESET' if reset else state['state_phase'],
            'control_diagnostics_phase': None if reset else state['control_diagnostics_phase'],
            'step': env.step_count, 'simulation_time_seconds': float(env.data.time),
            'control_interval_start_seconds': None if reset else state['control_interval_start_seconds'],
            'runtime_timestep_seconds': float(env.model.opt.timestep),
            'position': state['robot_pos'].tolist(), 'integrated_translation_qpos': env.data.qpos[:3].tolist(),
            'velocity': state['robot_velocity'].tolist(), 'target': state['target_pos'].tolist(),
            'distance': float(state['distance']), 'collision': bool(state['safety_violation']),
            'contact_floor': bool(state['contact_floor']), 'contact_obstacle': bool(state['contact_obstacle']),
            'boundary_clearance': float(state['boundary_clearance']),
            'min_obstacle_distance': float(state['min_obstacle_distance']),
            'safe_action': None if reset else state['safe_action'].tolist(),
            'cbf_residual': None if reset else state['cbf_constraint_residual']}


def run(output):
    plan = assignments()
    with DevelopmentLedger.create(output, study=STUDY, assignments=plan, record_events=True) as ledger:
        for a in plan:
            if hashes() != a['source_sha256']:
                raise RuntimeError('source changed before assignment; preserve unexecuted work')
            ledger.start(a['id'])
            env = None
            try:
                env = Environment(PhysicalWorld3DConfig(**a['runtime']['configuration']))
                if runtime_snapshot(env) != a['runtime']:
                    raise ValueError('runtime differs from assignment')
                env.reset(np.random.default_rng(a['development_reset_seed']))
                env.data.qpos[:3] = a['initial_position']; env.data.qvel[:3] = a['initial_velocity']
                env.target_pos = np.array(a['target']); mujoco.mj_forward(env.model, env.data)
                ledger.event(a['id'], details={'type': 'RESET', 'observation': observation(env, env.get_state(), True)})
                for _ in range(a['steps']):
                    state = env.step(np.array(a['command']), force_braking=a['force_braking'])
                    ledger.event(a['id'], details={'type': 'STEP', 'observation': observation(env, state)})
            except (LedgerError, LedgerWriteError):
                raise  # Never retry or synthesize a terminal record after a persistence failure.
            except Exception as exc:
                ledger.complete(a['id'], status='ERROR', details={'error_type': type(exc).__name__, 'error': str(exc),
                                'source_sha256_after': hashes(), 'runtime_after': runtime_snapshot(env) if env else None})
                if hashes() != a['source_sha256']:
                    raise RuntimeError('source changed during failed assignment') from exc
                continue
            after = hashes(); runtime = runtime_snapshot(env)
            if after != a['source_sha256'] or runtime != a['runtime']:
                ledger.complete(a['id'], status='ERROR', details={'error': 'source/runtime drift',
                                'source_sha256_after': after, 'runtime_after': runtime})
                raise RuntimeError('source/runtime changed; remaining assignments stay unexecuted')
            ledger.complete(a['id'], status='COMPLETED', details={'observed_steps': env.step_count,
                            'source_sha256_after': after, 'runtime_after': runtime})
        ledger.finalize()


def _number(x):
    return type(x) in (int, float) and math.isfinite(x)


def _vector(v):
    return isinstance(v, list) and len(v) == 3 and all(_number(x) for x in v)


def _validate_runtime(runtime):
    required = {'environment_id', 'configuration', 'runtime_timestep_seconds', 'gravity',
                'integrator', 'robot_body_mass', 'robot_geom_size', 'obstacles', 'versions'}
    if not isinstance(runtime, dict) or set(runtime) != required:
        raise ValueError('missing or unsupported runtime metadata')
    config = runtime['configuration']
    if not isinstance(config, dict) or set(config) != set(asdict(PhysicalWorld3DConfig())) or not all(_number(v) for v in config.values()):
        raise ValueError('missing or invalid configuration metadata')
    if (not isinstance(runtime['versions'], dict) or set(runtime['versions']) != {'python', 'numpy', 'mujoco'} or
            any(not isinstance(v, str) or not v for v in runtime['versions'].values()) or
            not _vector(runtime['gravity']) or type(runtime['integrator']) is not int or runtime['integrator'] < 0 or
            not _number(runtime['robot_body_mass']) or runtime['robot_body_mass'] <= 0 or
            runtime['robot_body_mass'] != config['robot_mass'] or
            not _vector(runtime['robot_geom_size']) or any(v < 0 for v in runtime['robot_geom_size']) or
            runtime['robot_geom_size'][0] != config['robot_radius']):
        raise ValueError('invalid model/runtime metadata')
    obstacles = runtime['obstacles']
    if not isinstance(obstacles, list) or not obstacles:
        raise ValueError('missing model obstacles')
    for obstacle in obstacles:
        if (not isinstance(obstacle, dict) or set(obstacle) != {'center', 'radius'} or
                not _vector(obstacle['center']) or not _number(obstacle['radius']) or obstacle['radius'] <= 0):
            raise ValueError('invalid model obstacle')


def analyze(path):
    raw = Path(path).read_bytes(); ledger = inspect_bytes(raw); header = ledger['records'][0]
    if header['study'] != STUDY or ledger['schema'] != 'nexvia-development-ledger/2':
        raise ValueError('unexpected synchronized fixture study/schema')
    expected_cases = {case[0]: case for case in CASES}
    if {a['id'] for a in header['assignments']} != set(expected_cases):
        raise ValueError('declared fixture coverage mismatch')
    events = {a['id']: [] for a in header['assignments']}; terminals = {}
    for r in ledger['records']:
        if r['kind'] == 'EVENT': events[r['id']].append(r['details'])
        elif r['kind'] == 'TERMINAL': terminals[r['id']] = r
    rows = []
    for a in header['assignments']:
        runtime = a['runtime']; _validate_runtime(runtime); dt = runtime['runtime_timestep_seconds']
        _, expected_dt, pos, vel, count, brake = expected_cases[a['id']]
        if (a['initial_position'] != pos or a['initial_velocity'] != vel or a['steps'] != count or
                a['force_braking'] != brake or a['target'] != [2., 2., .5] or a['command'] != [0., 0., 0.] or
                a['development_reset_seed'] != 9201001 or dt != expected_dt or
                runtime['configuration'] != asdict(PhysicalWorld3DConfig(timestep=expected_dt))):
            raise ValueError('assignment differs from versioned fixture plan')
        validate_source_maps(a['source_sha256'], a['source_sha256'])
        if set(a['source_sha256']) != set(FILES):
            raise ValueError('source manifest coverage mismatch')
        if (runtime['environment_id'] != Environment.ENVIRONMENT_ID or not _number(dt) or dt <= 0 or
                runtime['configuration']['timestep'] != dt or type(a['steps']) is not int or a['steps'] <= 0):
            raise ValueError('invalid assigned environment/timestep/count')
        for name in ('initial_position', 'initial_velocity', 'target', 'command'):
            if not _vector(a[name]): raise ValueError('invalid assigned vector')
        if type(a['force_braking']) is not bool: raise ValueError('invalid assigned brake mode')
        steps = []; reset_seen = False
        for event in events[a['id']]:
            o = event['observation']; reset = event['type'] == 'RESET'
            if event['type'] not in ('RESET', 'STEP') or (reset and (reset_seen or steps)) or (not reset and not reset_seen):
                raise ValueError('invalid reset/step chronology')
            expected = 0 if reset else len(steps) + 1
            phase = 'FORWARD_REFRESH_RESET' if reset else 'POST_INTEGRATION_FORWARD_REFRESH'
            if (o['environment_id'] != runtime['environment_id'] or o['state_phase'] != phase or
                    o['control_diagnostics_phase'] != (None if reset else 'PRE_INTEGRATION_CBF') or
                    type(o['step']) is not int or o['step'] != expected or expected > a['steps']):
                raise ValueError('invalid phase/step identity')
            if (not _number(o['runtime_timestep_seconds']) or o['runtime_timestep_seconds'] != dt or
                    not _number(o['simulation_time_seconds']) or
                    not math.isclose(o['simulation_time_seconds'], expected * dt, rel_tol=0, abs_tol=1e-10)):
                raise ValueError('invalid observation time/timestep')
            start = o['control_interval_start_seconds']
            if (reset and start is not None) or (not reset and (not _number(start) or
                    not math.isclose(start, (expected - 1) * dt, rel_tol=0, abs_tol=1e-10))):
                raise ValueError('invalid transition start time')
            for name in ('position', 'integrated_translation_qpos', 'velocity', 'target'):
                if not _vector(o[name]): raise ValueError('invalid physical vector')
            if o['position'] != o['integrated_translation_qpos'] or o['target'] != a['target']:
                raise ValueError('position phase/target mismatch')
            if not _number(o['distance']) or not math.isclose(o['distance'], math.dist(o['position'], o['target']), rel_tol=0, abs_tol=1e-10):
                raise ValueError('invalid distance')
            if any(type(o[k]) is not bool for k in ('collision', 'contact_floor', 'contact_obstacle')):
                raise ValueError('invalid contact/collision flags')
            if not _number(o['boundary_clearance']) or not _number(o['min_obstacle_distance']):
                raise ValueError('invalid clearance')
            config = runtime['configuration']; position = o['position']
            limit = config['arena_limit'] - config['robot_radius']
            boundary = min(position[2] - config['robot_radius'], limit - position[2],
                           limit - abs(position[0]), limit - abs(position[1]))
            obstacle_distance = min(math.dist(position, v['center']) - config['robot_radius'] - v['radius']
                                    for v in runtime['obstacles'])
            if (not math.isclose(o['boundary_clearance'], boundary, rel_tol=0, abs_tol=1e-10) or
                    not math.isclose(o['min_obstacle_distance'], obstacle_distance, rel_tol=0, abs_tol=1e-10)):
                raise ValueError('clearance contradicts recorded geometry')
            if o['collision'] != (o['contact_floor'] or o['contact_obstacle'] or
                                  o['boundary_clearance'] < 0 or o['min_obstacle_distance'] < 0):
                raise ValueError('collision flag contradicts retained clearance/contact')
            residual = o['cbf_residual']
            if (reset and (o['safe_action'] is not None or residual is not None)) or (not reset and
                    (not _vector(o['safe_action']) or (residual is not None and not _number(residual)))):
                raise ValueError('invalid transition control diagnostics')
            if reset:
                if o['position'] != a['initial_position'] or o['velocity'] != a['initial_velocity']:
                    raise ValueError('reset differs from assignment')
                reset_seen = True
            else: steps.append(o)
        terminal = terminals.get(a['id']); status = ledger['assignments'][a['id']]
        if terminal and terminal['status'] == 'COMPLETED':
            detail = terminal['details']
            if not reset_seen or len(steps) != a['steps'] or type(detail['observed_steps']) is not int or detail['observed_steps'] != len(steps):
                raise ValueError('completed assignment missing observations')
            validate_source_maps(a['source_sha256'], detail['source_sha256_after'])
            if detail['runtime_after'] != runtime: raise ValueError('runtime drift in completed fixture')
        rows.append({'id': a['id'], 'execution_status': status, 'reset_observed': reset_seen,
                     'requested_steps': a['steps'], 'persisted_steps': len(steps),
                     'persisted_step_seconds': len(steps) * dt,
                     'collision_observed': any(o['collision'] for o in steps) if steps else None})
    return {'classification': 'EXPLORATORY_SYNCHRONIZED_FIXTURE_AUDIT',
            'input_sha256': hashlib.sha256(raw).hexdigest(), 'ledger_state': ledger['state'], 'assignments': rows,
            'governance': 'GATE_B_NOT_AUTHORIZED',
            'limitations': ['Synthetic fixtures, including deliberate collisions; not policy performance or real-robot validation.',
                           'Times cover persisted samples only; an interrupted physical step may be unrecorded.',
                           'A self-reported valid chain does not authenticate physical truth, metadata or rollback state.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analyze', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.analyze:
        result = analyze(args.analyze)
        with args.output.open('x') as stream: json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    else: run(args.output)


if __name__ == '__main__': main()
