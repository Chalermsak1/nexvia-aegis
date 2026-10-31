#!/usr/bin/env python3
"""Compare a declared 2x2 development recovery grid; no acceptance inference."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.analyze_recovery_monitor_ledger import analyze
from scripts.research.development_ledger import inspect_bytes

FACTORS = {'navigation_force_method', 'recovery_steps_limit'}
OUTCOMES = ('true_success', 'false_arrival', 'abstained', 'timeout')


def post_stop_summary(post):
    if not post:
        return None
    samples = post['steps']
    return {'decision_distance': post['decision_distance'], 'decision_speed': post['decision_speed'],
            'post_samples': len(samples),
            'post_distance_min': min((s['distance'] for s in samples), default=None),
            'post_distance_max': max((s['distance'] for s in samples), default=None),
            'post_speed_min': min((s['speed'] for s in samples), default=None),
            'post_speed_max': max((s['speed'] for s in samples), default=None),
            'post_collision_observed': any(s['collision'] for s in samples)}


def compare(paths):
    if len(paths) != 4:
        raise ValueError('exactly four factorial input ledgers required')
    cells, reference, key_reference = {}, None, None
    for path in paths:
        raw = Path(path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        verified = analyze(path)
        if verified['input_sha256'] != digest:
            raise ValueError('input changed between validation reads')
        ledger = inspect_bytes(raw)
        assignments = ledger['records'][0]['assignments']
        # Require explicit factors; legacy assignments cannot identify a cell.
        if not assignments or any(not FACTORS.issubset(a) for a in assignments):
            raise ValueError('explicit force and budget factors required')
        cell_keys = {(a['navigation_force_method'], a['recovery_steps_limit']) for a in assignments}
        if len(cell_keys) != 1:
            raise ValueError('mixed factorial cell')
        cell = next(iter(cell_keys))
        if cell in cells:
            raise ValueError('duplicate factorial cell')
        normalized = {a['id']: {k: v for k, v in a.items() if k not in FACTORS} for a in assignments}
        scientific_keys = {a['id']: (a['seed'], tuple(a['bias_xyz']), a['controller'], json.dumps(a['case'], sort_keys=True)) for a in assignments}
        if reference is None:
            reference, key_reference = normalized, scientific_keys
        elif normalized != reference or scientific_keys != key_reference:
            raise ValueError('unmatched assignment identities, source, runtime, horizons or configuration')
        terminals = {r['id']: r for r in ledger['records'] if r['kind'] == 'TERMINAL'}
        traces = {a['id']: [] for a in assignments}
        for record in ledger['records']:
            if record['kind'] == 'EVENT':
                event = record['details']['record']
                traces[record['id']].append({name: event.get(name) for name in
                    ('step', 'position', 'velocity', 'target', 'action', 'decision', 'effective_decision', 'phase_before', 'phase_after')})
        execution_counts, outcome_counts = Counter(), Counter({name: 0 for name in OUTCOMES})
        rows = []
        for a in assignments:
            terminal = terminals.get(a['id'])
            execution = terminal['status'] if terminal else 'INCOMPLETE'
            execution_counts[execution] += 1
            row = {'id': a['id'], 'execution_status': execution, 'outcome': None, 'post_stop': None}
            trace = traces[a['id']]
            row['decision_state_action_record_count'] = len(trace)
            row['decision_state_action_sha256'] = hashlib.sha256(json.dumps(trace, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() if trace else None
            if execution == 'COMPLETED':
                episode = terminal['details']['episode']
                row['outcome'] = next(name for name in OUTCOMES if episode[name])
                outcome_counts[row['outcome']] += 1
                row['collision_occurred'] = episode['collision_occurred']
                row['post_stop'] = post_stop_summary(episode.get('post_stop'))
                trace = terminal['details'].get('last_events', [])
                row['last_recorded_reason'] = trace[-1].get('terminal_reason') if trace else None
            rows.append(row)
        cells[cell] = {'navigation_force_method': cell[0], 'recovery_steps_limit': cell[1],
            'input_path': str(path), 'input_sha256': digest, 'ledger_state': ledger['state'],
            'assigned': len(assignments), 'execution_counts': dict(execution_counts),
            'outcome_counts': dict(outcome_counts), 'assignments': rows}
    forces = {key[0] for key in cells}
    budgets = {key[1] for key in cells}
    if forces != {'AXIS_CLIP', 'DIRECTION_PRESERVING_PEAK'} or len(budgets) != 2 or set(cells) != {(f, b) for f in forces for b in budgets}:
        raise ValueError('full two-force by two-budget grid required')
    trace_comparisons = []
    ordered = sorted(cells)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            left_rows = {r['id']: r for r in cells[left]['assignments']}
            right_rows = {r['id']: r for r in cells[right]['assignments']}
            trace_comparisons.append({'left': list(left), 'right': list(right), 'assignments': [
                {'id': identifier, 'recorded_decision_states_actions_equal':
                 left_rows[identifier]['decision_state_action_sha256'] == right_rows[identifier]['decision_state_action_sha256']
                 if left_rows[identifier]['decision_state_action_sha256'] is not None and right_rows[identifier]['decision_state_action_sha256'] is not None else None}
                for identifier in sorted(left_rows)]})
    return {'classification': 'EXPLORATORY_MATCHED_RECOVERY_FACTORIAL',
            'interpretation': 'Descriptive counts over all assigned cases. No probability, statistical acceptance or real-robot claim. Decision-time STOP and post-STOP observations remain separate; absent post evidence is null.',
            'matched_assignments_per_cell': len(reference), 'budgets': sorted(budgets),
            'cells': [cells[key] for key in sorted(cells)], 'decision_trace_comparisons': trace_comparisons,
            'trace_comparison_scope': 'Exact equality of recorded pre-physics state/action/decision fields only; excludes force method labels and budget metadata, not a complete physics-trajectory equivalence proof. Equal outcome counts need not imply equal traces.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs=4, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = compare(args.inputs)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write('\n')


if __name__ == '__main__':
    main()
