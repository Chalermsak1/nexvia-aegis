"""Fixed synthetic feedback-interface study. No simulator or Holdout access."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

from aegis.development.recovery_feedback_state_1d import assess_feedback
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect

ROOT = Path(__file__).resolve().parents[2]
STUDY = 'V9-M5 measured-feedback preparation synthetic fixtures v1'
FILES = (
    'src/aegis/development/recovery_envelope_1d.py',
    'src/aegis/development/recovery_envelope_state_1d.py',
    'src/aegis/development/recovery_feedback_state_1d.py',
    'scripts/research/recovery_feedback_study_1d.py',
    'scripts/research/development_ledger.py',
    'tests/test_recovery_feedback_state_1d.py',
    'tests/test_recovery_feedback_study_1d.py',
)
FLAGS = dict(evidence_status='COMPATIBLE_UNDER_ASSERTED_BOUNDS',
             measurement_bounds_asserted=True, actuator_model_asserted=True,
             power_bounds_asserted=True, command_records_asserted=True,
             clock_bounds_asserted=True)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def hashes():
    return {name: sha((ROOT / name).read_bytes()) for name in FILES}


def plan():
    model = dict(dt='.02', position=['0','0'], velocity=['.5','.5'],
                 mass=['1','1'], gain=['2','2'], cap=['1','1'], slew=['4','4'],
                 disturbance='0', measurement_error='0', delay_ticks=[3,3],
                 power_cut_ticks=[160,160], horizon=140, safe_position=['-.5','.32'],
                 terminal_velocity=['-.05','.05'], terminal_samples=25)
    common = dict(sample_tick=100, received_tick=100, clock_id='fixture-clock',
                  frame='WORLD_X_SI', source_id='synthetic-feedback')
    evidence = dict(assessment_tick=100, clock_id='fixture-clock', max_state_age_ticks=8,
                    state_observations=[dict(common, position=['0','0'], velocity=['.5','.5'])],
                    force_observations=[dict(common, force=['0','0'])],
                    commands=[dict(enqueue_tick=t, received_tick=100, clock_id='fixture-clock',
                                   frame='WORLD_X_SI', source_id='synthetic-enqueue-ack',
                                   effective_target=['0','0']) for t in (97,98,99)],
                    power=dict(absolute_cut_ticks=[260,260], received_tick=100,
                               clock_id='fixture-clock', source_id='synthetic-power-bound'))
    result = []
    def add(name):
        row = dict(id=name, model=copy.deepcopy(model), evidence=copy.deepcopy(evidence), flags=dict(FLAGS))
        result.append(row)
        return row
    add('fresh_reset_feedback')
    a = add('acknowledged_pending_acceleration')
    a['evidence']['force_observations'][0]['force'] = ['.8','.8']
    for command in a['evidence']['commands']:
        command['effective_target'] = ['.8','.8']
    a = add('missing_all_acknowledgements'); a['evidence']['commands'] = []
    a = add('missing_current_force'); a['evidence']['force_observations'] = []
    a = add('aged_state_transport'); a['evidence']['state_observations'][0]['sample_tick'] = 96
    a = add('aged_force_not_current'); a['evidence']['force_observations'][0].update(sample_tick=99, force=['-.8','-.8'])
    a = add('expired_power_deadline'); a['evidence']['power']['absolute_cut_ticks'] = [80,85]
    a = add('conflicting_state_packets')
    a['evidence']['state_observations'].append(dict(common, position=['1','1'], velocity=['.5','.5']))
    a = add('conflicting_command_ack'); other=copy.deepcopy(a['evidence']['commands'][0]);other['effective_target']=['1','1'];a['evidence']['commands'].append(other)
    a = add('conflicting_old_force_packets')
    a['evidence']['force_observations']=[dict(common,sample_tick=99,force=['-.8','-.8']),dict(common,sample_tick=99,force=['.8','.8'])]
    a = add('missing_state_observation'); a['evidence']['state_observations'] = []
    a = add('missing_power_evidence'); a['evidence']['power'] = None
    a = add('incompatible_clock'); a['evidence']['state_observations'][0]['clock_id'] = 'other-clock'
    a = add('future_receipt'); a['evidence']['commands'][0]['received_tick'] = 101
    a = add('unasserted_ack_semantics'); a['flags']['command_records_asserted'] = False
    a = add('unknown_evidence'); a['flags']['evidence_status'] = 'UNKNOWN'
    a = add('force_conflicts_with_expired_power')
    a['evidence']['power']['absolute_cut_ticks']=[80,85]
    a['evidence']['force_observations'][0]['force']=['.8','.8']
    a = add('possible_prior_power_flush')
    a['evidence']['power']['absolute_cut_ticks']=[99,102]
    for command in a['evidence']['commands']:
        command['effective_target']=['.8','.8']
    return result


def run_case(assignment):
    return assess_feedback(assignment['model'], assignment['evidence'], **assignment['flags'])


def summarize(result):
    p, a = result['preparation'], result['assessment']
    return dict(preparation_status=p['status'], conclusion=result['conclusion'],
                finite_horizon_containment=None if a is None else a['finite_horizon_containment'],
                terminal_sample_condition=None if a is None else a['terminal_sample_condition'],
                recovery_analysis_branches=0 if a is None else len(a['branches']),
                operational_authorization=False, action=None,
                future_position_containment='NOT_ESTABLISHED')


def run(directory):
    directory = Path(directory)
    directory.mkdir(exist_ok=False)
    sources = hashes()
    metadata = dict(source_sha256=sources, python=platform.python_version(),
                    parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    gate_b='GATE_B_NOT_AUTHORIZED',
                    classification='SYNTHETIC_ANALYSIS_NOT_INDEPENDENT_TRIALS_NO_PHYSICS_STEPS')
    assignments = [dict(a, metadata=metadata) for a in plan()]
    with DevelopmentLedger.create(directory/'assignments.jsonl', study=STUDY, assignments=assignments) as ledger:
        for a in assignments:
            ledger.start(a['id'])
            try:
                result = run_case(a)
                raw = canonical(result)
                with (directory/(a['id']+'.json')).open('xb') as output:
                    output.write(raw); output.flush(); os.fsync(output.fileno())
                if hashes() != sources:
                    raise ValueError('sources changed during analysis')
                ledger.complete(a['id'], status='COMPLETED', details=dict(
                    output_sha256=sha(raw), summary=summarize(result), sources_after=sources))
            except (LedgerError, LedgerWriteError):
                raise
            except Exception as exc:
                ledger.complete(a['id'], status='ERROR', details=dict(error_type=type(exc).__name__, error=str(exc)))
                raise
        ledger.finalize()
    return audit(directory)


def audit(directory):
    """Reconstruct exact outputs under pinned local sources; no authenticity claim."""
    directory = Path(directory)
    log = inspect(directory/'assignments.jsonl')
    header = log['records'][0]
    assignments = header['assignments']
    metadata = assignments[0]['metadata']
    if header['study'] != STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments] != plan():
        raise ValueError('unexpected study or assignment plan')
    if any(a['metadata'] != metadata for a in assignments) or metadata['gate_b'] != 'GATE_B_NOT_AUTHORIZED':
        raise ValueError('metadata mismatch')
    if hashes() != metadata['source_sha256'] or platform.python_version() != metadata['python']:
        raise ValueError('audit source/runtime mismatch; use original source snapshot')
    by_id = {a['id']:a for a in assignments}
    rows = {}
    active = None
    for record in log['records'][1:]:
        if record['kind'] == 'START':
            if active is not None:
                raise ValueError('nonsequential analysis')
            active = record['id']
        elif record['kind'] == 'TERMINAL':
            name = record['id']
            if active != name:
                raise ValueError('terminal analysis order mismatch')
            active = None
            if record['status'] == 'COMPLETED':
                path = directory/(name+'.json')
                if path.is_symlink():
                    raise ValueError('symlinked result unsupported')
                raw = path.read_bytes()
                details = record['details']
                rebuilt = run_case(by_id[name])
                if details['sources_after'] != metadata['source_sha256'] or sha(raw) != details['output_sha256']:
                    raise ValueError('source/output hash mismatch')
                if raw != canonical(rebuilt) or details['summary'] != summarize(rebuilt):
                    raise ValueError('reconstructed output/summary mismatch')
                rows[name] = details['summary']
    return dict(study=STUDY, ledger_state=log['state'], counts=log['counts'], metadata=metadata,
                assignments=[dict(id=a['id'], state=log['assignments'][a['id']], summary=rows.get(a['id'])) for a in assignments],
                unreferenced_result_files=[a['id']+'.json' for a in assignments if a['id'] not in rows and (directory/(a['id']+'.json')).exists()],
                physics_steps=0, gate_b='GATE_B_NOT_AUTHORIZED', operational_authorization=False,
                limitations=['Caller-asserted packet coverage, clock and enqueue semantics; not authentication.',
                             'Exact discrete 1D model; no hardware calibration, invariant terminal set or online action policy.',
                             'Design fixtures are dependent analyses, not statistical trials.',
                             'Self-reported hash chain and same-runtime reconstruction are not independent provenance.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run','audit'))
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists')
    result = run(args.directory) if args.mode == 'run' else audit(args.directory)
    with args.output.open('xb') as output:
        output.write(canonical(result));output.flush();os.fsync(output.fileno())
    print(json.dumps(dict(state=result['ledger_state'],counts=result['counts'])))


if __name__ == '__main__':
    main()
