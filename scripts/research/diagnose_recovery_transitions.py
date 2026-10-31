#!/usr/bin/env python3
"""Read-only transition diagnostics; no thresholds, safety or success inference."""
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


def summarize(events):
    transitions, reasons, modes = [], [], []
    availability = {name: Counter() for name in ('range_valid', 'range_fresh', 'range_semantically_valid',
        'range_raw_transport_valid', 'anchor_requested', 'anchor_valid', 'next_query_anchor')}
    low_speed = []
    recovery = []
    last_reason = last_mode = object()
    for index, event in enumerate(events):
        if type(event.get('step')) is not int or event['step'] != index:
            raise ValueError('decision events must start at zero and be consecutive')
        for field in ('phase_before', 'phase_after', 'mode', 'terminal_reason'):
            if not isinstance(event.get(field), str) or not event[field]:
                raise ValueError('missing transition evidence: ' + field)
        if event['phase_before'] != event['phase_after']:
            transitions.append({'step': index, 'before': event['phase_before'], 'after': event['phase_after'],
                                'decision': event.get('effective_decision'), 'reason': event['terminal_reason']})
        if event['terminal_reason'] != last_reason:
            reasons.append({'step': index, 'reason': event['terminal_reason']})
            last_reason = event['terminal_reason']
        if event['mode'] != last_mode:
            modes.append({'step': index, 'mode': event['mode']})
            last_mode = event['mode']
        for name, counts in availability.items():
            value = event.get(name)
            if value is not None and type(value) is not bool:
                raise ValueError('invalid availability flag: ' + name)
            counts['unrecorded_or_not_applicable' if value is None else str(value).lower()] += 1
        value = event.get('low_speed_samples')
        for name in ('recovery_steps', 'stabilization_wait_steps', 'missing_velocity_count'):
            count = event.get(name)
            if count is not None and (type(count) is not int or count < 0):
                raise ValueError('invalid internal counter: ' + name)
        if value is not None:
            if type(value) is not int or value < 0:
                raise ValueError('invalid low-speed sample count')
            low_speed.append({'step': index, 'count': value})
        if event['phase_before'] == 'RECOVERY':
            recovery.append(event)

    def snapshot(event):
        output = {name: event.get(name) for name in ('step', 'phase_before', 'phase_after', 'true_distance',
            'range', 'range_valid', 'range_fresh', 'range_semantically_valid', 'range_raw_sample',
            'range_raw_transport_valid', 'range_validation_status',
            'recovery_steps', 'stabilization_wait_steps', 'missing_velocity_count',
            'anchor_requested', 'anchor_valid', 'effective_decision', 'terminal_reason')}
        for name in ('anchor', 'velocity_observation', 'action'):
            vector = event.get(name)
            if vector is None:
                output[name + '_norm'] = None
            else:
                if not isinstance(vector, list) or len(vector) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
                    raise ValueError('invalid recorded vector: ' + name)
                output[name + '_norm'] = math.sqrt(sum(v*v for v in vector))
        return output

    return {'decision_events': len(events), 'phase_transitions': transitions, 'mode_changes': modes,
            'reason_changes': reasons, 'phase_before_counts': dict(Counter(e['phase_before'] for e in events)),
            'phase_after_counts': dict(Counter(e['phase_after'] for e in events)),
            'availability_counts': {name: dict(counts) for name, counts in availability.items()},
            'recovery_update_observations': len(recovery),
            'recovery_guidance_observations': sum(e.get('effective_decision') == 'NAVIGATE' for e in recovery),
            'recovery_availability_counts': {name: dict(Counter('unrecorded_or_not_applicable' if e.get(name) is None else str(e[name]).lower() for e in recovery)) for name in availability},
            'first_recovery_update': snapshot(recovery[0]) if recovery else None,
            'last_recovery_update': snapshot(recovery[-1]) if recovery else None,
            'low_speed_samples_recorded': low_speed,
            'low_speed_samples_unavailable_count': len(events) - len(low_speed),
            'last_recorded_reason': events[-1]['terminal_reason'] if events else None,
            'internal_counters': {name: {'recorded_observations': sum(e.get(name) is not None for e in events),
                'last_recorded_value': next((e[name] for e in reversed(events) if e.get(name) is not None), None)}
                for name in ('recovery_steps', 'stabilization_wait_steps', 'missing_velocity_count')},
            'interpretation': 'Recovery update count is observed phase occupancy, not the unrecorded internal recovery_steps variable. Missing low_speed_samples does not mean zero.'}


def diagnose(path):
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    valid = analyze(path)
    if valid['input_sha256'] != digest:
        raise ValueError('input changed between diagnostic and validation reads')
    ledger = inspect_bytes(raw)
    if ledger['schema'] != 'nexvia-development-ledger/2':
        raise ValueError('incremental decision events required')
    assignments = ledger['records'][0]['assignments']
    events = {a['id']: [] for a in assignments}
    terminals = {}
    for record in ledger['records']:
        if record['kind'] == 'EVENT':
            events[record['id']].append(record['details']['record'])
        elif record['kind'] == 'TERMINAL':
            terminals[record['id']] = record
    rows = []
    for a in assignments:
        terminal = terminals.get(a['id'])
        episode = terminal['details'].get('episode') if terminal else None
        rows.append({'id': a['id'], 'controller': a['controller'], 'seed': a['seed'], 'bias_xyz': a['bias_xyz'],
            'navigation_force_method': a.get('navigation_force_method'),
            'execution_status': terminal['status'] if terminal else 'INCOMPLETE',
            'terminal_reason': episode.get('terminal_reason') if episode else None,
            'diagnostic': summarize(events[a['id']]),
            'limitation': 'Pre-physics controller observations only. Last recorded reason is not an execution-completion verdict.'})
    return {'classification': 'EXPLORATORY_RECOVERY_TRANSITION_DIAGNOSTIC', 'input_sha256': digest,
            'ledger_state': ledger['state'], 'episodes': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = diagnose(args.input)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write('\n')


if __name__ == '__main__':
    main()
