#!/usr/bin/env python3
"""Read-only matched recovery-budget comparison. No scientific pass criteria."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.analyze_recovery_monitor_ledger import analyze
from scripts.research.development_ledger import inspect_bytes


def load(path):
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if analyze(path)['input_sha256'] != digest:
        raise ValueError('input changed during validation')
    return inspect_bytes(raw), digest


def compare(left, right):
    first, sha_first = load(left)
    second, sha_second = load(right)
    aa = {a['id']: a for a in first['records'][0]['assignments']}
    bb = {a['id']: a for a in second['records'][0]['assignments']}
    if aa.keys() != bb.keys():
        raise ValueError('unmatched assignments')
    budgets = []
    for assignments in (aa, bb):
        values = {a.get('recovery_steps_limit') for a in assignments.values()}
        if len(values) != 1 or any(type(v) is not int or v <= 0 for v in values):
            raise ValueError('explicit uniform positive recovery budget required')
        budgets.append(values.pop())
    if budgets[0] == budgets[1]:
        raise ValueError('budgets must differ')
    for identifier, a in aa.items():
        if {k:v for k,v in a.items() if k != 'recovery_steps_limit'} != {k:v for k,v in bb[identifier].items() if k != 'recovery_steps_limit'}:
            raise ValueError('settings differ beyond recovery budget')
    terminals = [{r['id']: r for r in ledger['records'] if r['kind'] == 'TERMINAL'} for ledger in (first,second)]
    rows = []
    for identifier in aa:
        row = {'id': identifier, 'conditions': {k:aa[identifier][k] for k in ('seed','controller','bias_xyz','case')}, 'observations': []}
        for budget, records in zip(budgets, terminals):
            record = records.get(identifier)
            item = {'recovery_steps_limit': budget, 'execution_status': record['status'] if record else 'INCOMPLETE'}
            if record and record['status'] == 'COMPLETED':
                episode = record['details']['episode']
                item['episode'] = episode
                tail = record['details'].get('last_events', [])
                item['last_observed_reason'] = tail[-1].get('terminal_reason') if tail else None
            row['observations'].append(item)
        rows.append(row)
    return {'classification': 'EXPLORATORY_MATCHED_BUDGET_COMPARISON', 'input_sha256': [sha_first,sha_second],
            'ledger_states': [first['state'],second['state']], 'budgets': budgets, 'assignments': rows,
            'limitation': 'Repeated worlds, unchanged STOP rules; no risk probability, safety guarantee or confirmatory pass inferred.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('left', type=Path)
    parser.add_argument('right', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.left,args.right)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(result,out,indent=2,allow_nan=False)
        out.write('\n')


if __name__ == '__main__':
    main()
