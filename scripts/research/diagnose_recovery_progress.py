#!/usr/bin/env python3
"""Read-only descriptive diagnostics of development decision traces; no safety verdict."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.development_ledger import inspect_bytes
from scripts.research.analyze_recovery_monitor_ledger import analyze


def summarize_events(events, *, tail_steps=50):
    if type(tail_steps) is not int or tail_steps < 2:
        raise ValueError('tail_steps must be an integer >= 2')
    if not events:
        raise ValueError('no decision events available')
    for index, event in enumerate(events):
        if type(event.get('step')) is not int or event['step'] != index:
            raise ValueError('nonconsecutive decision steps')
        distance = event.get('true_distance')
        if type(distance) not in (int, float) or not math.isfinite(distance) or distance < 0:
            raise ValueError('invalid diagnostic distance')
        for name in ('mode', 'effective_decision'):
            if not isinstance(event.get(name), str) or not event[name]:
                raise ValueError('missing decision label')
    distances = [event['true_distance'] for event in events]
    tail = distances[-tail_steps:]
    return {
        'decision_observations': len(events),
        'initial_observed_distance_m': distances[0],
        'last_prephysics_distance_m': distances[-1],
        'minimum_observed_distance_m': min(distances),
        'observed_distance_reduction_m': distances[0] - distances[-1],
        'tail_observations': len(tail),
        'tail_distance_reduction_m': tail[0] - tail[-1],
        'mode_counts': dict(Counter(e['mode'] for e in events)),
        'effective_decision_counts': dict(Counter(e['effective_decision'] for e in events)),
        'tail_mode_counts': dict(Counter(e['mode'] for e in events[-tail_steps:])),
        'interpretation': 'DESCRIPTIVE_ONLY_NO_CAUSAL_OR_SAFETY_CLASSIFICATION',
    }


def diagnose(path, *, tail_steps=50):
    path = Path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    validated = analyze(path)
    if validated['input_sha256'] != digest:
        raise ValueError('input changed between reads')
    ledger = inspect_bytes(raw)
    if ledger['schema'] != 'nexvia-development-ledger/2':
        raise ValueError('incremental decision evidence required')
    assignments = ledger['records'][0]['assignments']
    events = {a['id']: [] for a in assignments}
    terminals = {}
    for row in ledger['records']:
        if row['kind'] == 'EVENT':
            events[row['id']].append(row['details']['record'])
        elif row['kind'] == 'TERMINAL':
            terminals[row['id']] = row
    rows = []
    for assignment in assignments:
        identifier = assignment['id']
        terminal = terminals.get(identifier)
        record = {'id': identifier, 'assignment': assignment,
                  'execution_status': terminal['status'] if terminal else 'INCOMPLETE',
                  'observations': summarize_events(events[identifier], tail_steps=tail_steps) if events[identifier] else None,
                  'episode': terminal['details'].get('episode') if terminal else None}
        rows.append(record)
    return {'classification': 'EXPLORATORY_SIMULATION_DIAGNOSTIC', 'input_sha256': digest,
            'ledger_state': ledger['state'], 'tail_steps': tail_steps,
            'measurement_scope': 'Controller observations before physics; last observation is not final plant state. No success threshold inferred.',
            'episodes': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--tail-steps', type=int, default=50)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.input, tail_steps=args.tail_steps)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write('\n')


if __name__ == '__main__':
    main()
