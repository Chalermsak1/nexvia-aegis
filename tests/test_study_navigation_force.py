import sys
import pytest
from scripts.research import study_navigation_force as study
from scripts.research.analyze_navigation_force import analyze
from scripts.research.development_ledger import DevelopmentLedger


def test_mujoco_runner_writes_valid_paired_evidence(tmp_path, monkeypatch):
    path = tmp_path / 'study.jsonl'
    monkeypatch.setattr(sys, 'argv', ['study', '--seeds', '2253002', '--steps', '3', '--output', str(path)])
    study.main()
    result = analyze(path)
    assert result['ledger_state'] == 'FINALIZED'
    assert len(result['episodes']) == 2
    assert all(row['event_count'] == 3 and row['execution_status'] == 'COMPLETED' for row in result['episodes'])


@pytest.mark.parametrize('defect', ['distance', 'safety', 'residual'])
def test_analyzer_rejects_contradictory_synthetic_evidence(tmp_path, monkeypatch, defect):
    path = tmp_path / 'bad.jsonl'
    monkeypatch.setattr(sys, 'argv', ['study', '--seeds', '2253002', '--steps', '3', '--output', str(path)])
    original = study.run

    def corrupt(seed, arm, steps, emit):
        def capture(event):
            if defect == 'residual':
                event['cbf_residual'] = None
            emit(event)
        result = original(seed, arm, steps, capture)
        if defect == 'distance':
            result['final_distance'] += 1.
        if defect == 'safety':
            result['safety_violation_observed'] = not result['safety_violation_observed']
        return result

    monkeypatch.setattr(study, 'run', corrupt)
    study.main()
    with pytest.raises(ValueError):
        analyze(path)


def synthetic_ledger(path, defect=None, status='COMPLETED'):
    assignments, evidence = [], []
    for arm in study.ARMS:
        events = []
        episode = study.run(2253002, arm, 3, events.append)
        assignment = {'id': arm, 'seed': 2253002, 'arm': arm, 'steps': 3,
                      'source_sha256': {'fixture': 'a' * 64}, 'runtime': {'fixture': 'v1'},
                      'state_source': 'SIMULATOR_TRUTH'}
        assignments.append(assignment)
        evidence.append((events, episode))
    events, episode = evidence[0]
    if defect == 'bool_step': events[0]['step'] = False
    if defect == 'bool_terminal_steps': episode['steps'] = True
    if defect == 'bool_collision': episode['safety_violation_observed'] = 0
    if defect == 'bool_count': episode['constraint_violation_steps'] = False
    if defect == 'bad_initial': episode['initial_distance'] += 1.
    if defect == 'continuity': events[1]['position_before'][0] += .1
    if defect == 'changing_target': events[1]['target'][0] += .1
    if defect == 'horizon': assignments[1]['steps'] = 4
    if defect == 'runtime': assignments[1]['runtime'] = {'fixture': 'v2'}
    if defect == 'source': assignments[1]['source_sha256'] = {'fixture': 'b' * 64}
    if defect == 'paired_world':
        # Rigid translation leaves all per-episode distances unchanged, but
        # makes the declared pair different worlds.
        for event in evidence[1][0]:
            for key in ('position_before', 'position_after', 'target'):
                event[key][0] += 1.
    with DevelopmentLedger.create(path, study='V9-M5 ideal-state navigation force ablation v1', assignments=assignments, record_events=True) as ledger:
        for a, (events, episode) in zip(assignments, evidence):
            ledger.start(a['id'])
            for event in events:
                ledger.event(a['id'], details=event)
            if status != 'INCOMPLETE':
                ledger.complete(a['id'], status=status, details={'episode': episode, 'source_sha256_after': a['source_sha256']})
        if status != 'INCOMPLETE':
            ledger.finalize()


@pytest.mark.parametrize('defect', ['bool_step', 'bool_terminal_steps', 'bool_collision', 'bool_count',
    'bad_initial', 'continuity', 'changing_target', 'horizon', 'runtime', 'source', 'paired_world'])
def test_analyzer_rejects_pairing_and_physics_contradictions(tmp_path, defect):
    path = tmp_path / 'bad.jsonl'
    synthetic_ledger(path, defect)
    with pytest.raises(ValueError):
        analyze(path)


@pytest.mark.parametrize('status', ['ERROR', 'INCOMPLETE'])
def test_partial_or_failed_execution_never_counted_completed(tmp_path, status):
    path = tmp_path / 'partial.jsonl'
    synthetic_ledger(path, status=status)
    result = analyze(path)
    assert all(row['execution_status'] == status for row in result['episodes'])
    assert all('episode' not in row for row in result['episodes'])
