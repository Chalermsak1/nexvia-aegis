#!/usr/bin/env python3
"""Descriptive post-action motion from development ledgers; no stopping criterion.

Never treats an absent observation as a collision-free interval, infers elapsed
seconds from an unrecorded timestep, or classifies STOP/ABSTAIN as physical rest.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.analyze_recovery_physics_evidence import analyze
from scripts.research.development_ledger import inspect_bytes


def _anchor(record):
    if record is None:
        return None
    result = {}
    for name in ('position', 'velocity', 'target'):
        value = record.get(name)
        if (not isinstance(value, list) or len(value) != 3 or
                any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
            raise ValueError('invalid motion anchor vector')
        result[name] = value
    distance = record.get('true_distance', record.get('distance'))
    if (type(distance) not in (int, float) or not math.isfinite(distance) or
            not math.isclose(distance, math.dist(result['position'], result['target']), abs_tol=1e-10)):
        raise ValueError('invalid motion anchor distance')
    result['distance'] = distance
    return result


def _window(*, reached, requested, anchor, samples):
    if type(requested) is not int or requested < 0:
        raise ValueError('invalid assigned diagnostic horizon')
    if not reached:
        state = 'NOT_REACHED'
    elif requested == 0:
        state = 'NOT_REQUESTED'
    elif len(samples) == requested:
        state = 'COMPLETE_OBSERVATION_WINDOW'
    else:
        state = 'PARTIAL' if samples else 'MISSING'
    # No positive physical evidence can be supplied by a missing window.
    output = {
        'window_status': state, 'requested_samples': requested,
        'observed_samples': len(samples),
        'collision_observed': any(s['collision'] for s in samples) if samples else None,
        'anchor_available': anchor is not None,
        'anchor_speed_m_s': math.hypot(*anchor['velocity']) if anchor else None,
        'anchor_distance_m': anchor['distance'] if anchor else None,
        'last_speed_m_s': None, 'last_distance_m': None,
        'min_sample_speed_m_s': None, 'max_sample_speed_m_s': None,
        'distance_change_from_anchor_m': None,
        'sampled_polyline_from_anchor_m': None,
        'cbf_residual_observed_samples': 0, 'min_observed_cbf_residual': None,
        'elapsed_seconds': None,
        'elapsed_seconds_reason': 'timestep not recorded in assignment; no inference from current source',
        'physical_rest_classification': 'NOT_EVALUATED_NO_APPROVED_CRITERION',
    }
    if not samples:
        return output
    speeds = [math.hypot(*s['velocity']) for s in samples]
    residuals = [s['cbf_residual'] for s in samples if s['cbf_residual'] is not None]
    output.update(last_speed_m_s=speeds[-1], last_distance_m=samples[-1]['distance'],
                  min_sample_speed_m_s=min(speeds), max_sample_speed_m_s=max(speeds),
                  cbf_residual_observed_samples=len(residuals),
                  min_observed_cbf_residual=min(residuals) if residuals else None)
    if anchor:
        if any(s['target'] != anchor['target'] for s in samples):
            raise ValueError('target changes within post-action window')
        points = [anchor['position']] + [s['position'] for s in samples]
        output['sampled_polyline_from_anchor_m'] = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
        output['distance_change_from_anchor_m'] = samples[-1]['distance'] - anchor['distance']
    return output


def summarize(path):
    raw = Path(path).read_bytes()
    validated = analyze(path)
    digest = hashlib.sha256(raw).hexdigest()
    if validated['input_sha256'] != digest:
        raise ValueError('input changed during analysis')
    ledger = inspect_bytes(raw)
    events = {a['id']: [] for a in ledger['records'][0]['assignments']}
    for record in ledger['records']:
        if record['kind'] == 'EVENT':
            events[record['id']].append(record['details'])
    statuses = {r['id']: r['execution_status'] for r in validated['assignments']}
    output = []
    for assignment in ledger['records'][0]['assignments']:
        records = events[assignment['id']]
        decisions = [r['record'] for r in records if r['type'] == 'DECISION']
        physics = [r['record'] for r in records if r['type'] == 'PHYSICS']
        last = decisions[-1] if decisions else None
        decision = last['effective_decision'] if last else None
        windows = {}
        for label, field, stage in [('STOP', 'post_stop_steps', 'POST_STOP_BRAKE'),
                                     ('ABSTAIN', 'post_abstain_steps', 'POST_ABSTAIN_BRAKE')]:
            reached = decision == label
            anchor = last if reached and label == 'STOP' else next(
                (r for r in physics if r['stage'] == 'ABSTAIN_BRAKE'), None) if reached else None
            windows[label] = _window(reached=reached, requested=assignment.get(field, 0),
                                     anchor=_anchor(anchor), samples=[r for r in physics if r['stage'] == stage])
        output.append({'id': assignment['id'], 'execution_status': statuses[assignment['id']],
                       'last_decision': decision, 'windows': windows})
    return {'classification': 'EXPLORATORY_POST_ACTION_MOTION', 'input_sha256': digest,
            'ledger_state': validated['ledger_state'], 'assignments': output,
            'limitations': ['Simulation observations, not real-robot validation or a safe-stop claim.',
                            'STOP anchor is decision time; ABSTAIN anchor is after its original brake.',
                            'Sampled polyline is a discrete chord sum, not exact continuous travel.',
                            'Collision absence applies only to persisted samples; partial windows remain partial.',
                            'Window completeness does not establish episode completion, dwell, stability, or authenticated provenance.'],
            'governance': 'GATE_B_NOT_AUTHORIZED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = summarize(args.input)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
