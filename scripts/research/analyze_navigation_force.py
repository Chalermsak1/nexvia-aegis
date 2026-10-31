#!/usr/bin/env python3
"""Validate the exploratory ideal-state force-ablation ledger."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.development_ledger import inspect_bytes
from scripts.research.evidence_integrity import validate_source_maps


def finite_number(value, *, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (nonnegative and value < 0):
        raise ValueError('invalid finite numeric evidence')
    return value


def close(left, right):
    return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-10)


def analyze(path):
    raw = Path(path).read_bytes()
    ledger = inspect_bytes(raw)
    header = ledger['records'][0]
    if header['study'] != 'V9-M5 ideal-state navigation force ablation v1' or ledger['schema'] != 'nexvia-development-ledger/2':
        raise ValueError('unexpected study')
    assignments = header['assignments']
    paired_metadata = {}
    for assignment in assignments:
        if type(assignment.get('seed')) is not int or assignment['seed'] < 0 or type(assignment.get('steps')) is not int or assignment['steps'] <= 0:
            raise ValueError('invalid assignment identity or horizon')
        if assignment.get('state_source') != 'SIMULATOR_TRUTH':
            raise ValueError('unexpected state source')
        metadata = {key: assignment.get(key) for key in ('steps', 'runtime', 'source_sha256', 'state_source')}
        seed = assignment['seed']
        if seed in paired_metadata and paired_metadata[seed] != metadata:
            raise ValueError('paired assignment metadata differs')
        paired_metadata[seed] = metadata
    keys = [(a['seed'], a['arm']) for a in assignments]
    expected = {(seed, arm) for seed, _ in keys for arm in ('AXIS_CLIP', 'DIRECTION_PRESERVING_PEAK')}
    if len(set(keys)) != len(keys) or set(keys) != expected:
        raise ValueError('unpaired grid')
    events = {a['id']: [] for a in assignments}
    terminals = {}
    for record in ledger['records']:
        if record['kind'] == 'EVENT':
            events[record['id']].append(record['details'])
        if record['kind'] == 'TERMINAL':
            terminals[record['id']] = record
    rows = []
    paired_worlds = {}
    for a in assignments:
        terminal = terminals.get(a['id'])
        row = {'id': a['id'], 'seed': a['seed'], 'arm': a['arm'], 'execution_status': terminal['status'] if terminal else 'INCOMPLETE', 'event_count': len(events[a['id']])}
        if terminal and terminal['status'] == 'COMPLETED':
            validate_source_maps(a['source_sha256'], terminal['details']['source_sha256_after'])
            episode = terminal['details']['episode']
            samples = events[a['id']]
            if len(samples) != a['steps'] or type(episode['steps']) is not int or episode['steps'] != a['steps'] or type(episode['seed']) is not int or (episode['seed'], episode['arm']) != (a['seed'], a['arm']):
                raise ValueError('identity or step mismatch')
            for name in ('initial_distance', 'final_distance', 'minimum_distance'):
                finite_number(episode.get(name), nonnegative=True)
            if type(episode.get('safety_violation_observed')) is not bool or type(episode.get('constraint_violation_steps')) is not int:
                raise ValueError('invalid terminal evidence types')
            distances, violations, collision = [], 0, False
            def vector(sample, name):
                value = sample.get(name)
                if not isinstance(value, list) or len(value) != 3 or any(type(v) not in (float, int) or not math.isfinite(v) for v in value):
                    raise ValueError('invalid vector')
                return value
            for index, event in enumerate(samples):
                if type(event['step']) is not int or event['step'] != index or event['type'] != 'POST_PHYSICS':
                    raise ValueError('bad event order or type')
                position, target = vector(event, 'position_after'), vector(event, 'target')
                for name in ('position_before', 'velocity_before', 'velocity_after', 'desired_force', 'projected_force'):
                    vector(event, name)
                if index:
                    previous = samples[index - 1]
                    for before, after in (('position_before', 'position_after'), ('velocity_before', 'velocity_after')):
                        if any(not close(x, y) for x, y in zip(event[before], previous[after])):
                            raise ValueError('discontinuous physics evidence')
                    if target != samples[0]['target']:
                        raise ValueError('target changed during episode')
                distance = math.sqrt(sum((p-t)**2 for p,t in zip(position,target)))
                finite_number(event.get('distance_after'), nonnegative=True)
                if not close(distance, event['distance_after']):
                    raise ValueError('distance mismatch')
                distances.append(distance)
                if type(event['safety_violation']) is not bool or type(event['cbf_feasible']) is not bool:
                    raise ValueError('invalid physics flags')
                residual = event['cbf_residual']
                if type(residual) not in (int, float) or not math.isfinite(residual):
                    raise ValueError('missing residual')
                violations += int(residual > 1e-8)
                collision |= event['safety_violation']
            for key, value in [('final_distance', distances[-1]), ('minimum_distance', min(episode['initial_distance'], *distances))]:
                if not close(episode[key], value):
                    raise ValueError('terminal distance contradiction')
            if collision != episode['safety_violation_observed'] or violations != episode['constraint_violation_steps']:
                raise ValueError('terminal safety evidence contradiction')
            initial = math.sqrt(sum((p-t)**2 for p, t in zip(samples[0]['position_before'], samples[0]['target'])))
            if not close(initial, episode['initial_distance']):
                raise ValueError('initial distance contradiction')
            world = {key: samples[0][key] for key in ('position_before', 'velocity_before', 'target')}
            if a['seed'] in paired_worlds and world != paired_worlds[a['seed']]:
                raise ValueError('paired initial world differs')
            paired_worlds[a['seed']] = world
            row['episode'] = episode
        rows.append(row)
    return {'classification': 'EXPLORATORY_IDEAL_STATE_ABLATION', 'ledger_state': ledger['state'],
            'input_sha256': hashlib.sha256(raw).hexdigest(), 'episodes': rows,
            'limitations': 'Simulator truth, static known geometry; no arrival or safety pass; selected diagnostic seed is not independent replication.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = analyze(args.input)
    with args.output.open('x') as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write('\n')


if __name__ == '__main__':
    main()
