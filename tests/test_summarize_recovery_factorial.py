import pytest
from scripts.research.development_ledger import DevelopmentLedger
from scripts.research.summarize_recovery_factorial import compare, post_stop_summary
from scripts.research import summarize_recovery_factorial as factorial


FORCES = ('AXIS_CLIP', 'DIRECTION_PRESERVING_PEAK')


def create_cell(path, force, budget, *, metadata=None, states=('COMPLETED', 'COMPLETED')):
    metadata = metadata or {}
    assignments = [dict(id=str(i), seed=2256000, bias_xyz=[0., 0., 0.], controller=arm,
        case={'name': 'nominal', 'range_bias_m': 0., 'range_dropout_probability': 0.},
        max_steps=1, post_stop_steps=2, runtime={'python': 'fixture'}, source_sha256={'fixture': 'a'*64},
        navigation_force_method=force, recovery_steps_limit=budget)
        for i, arm in enumerate(('AEGIS_3D_ANCHOR_RECOVERY', 'AEGIS_3D_RECOVERY_MONITOR'))]
    for assignment in assignments:
        assignment.update(metadata)
    with DevelopmentLedger.create(path, study='V9-M5 exploratory recovery monitor', assignments=assignments, record_events=True) as ledger:
        for a, status in zip(assignments, states):
            if status == 'INCOMPLETE':
                continue
            ledger.start(a['id'])
            if status == 'ERROR':
                ledger.complete(a['id'], status='ERROR', details={'error': 'synthetic'})
                continue
            event = dict(step=0, navigation_force_method=force, navigation_force_transformed=False,
                phase_before='ANCHOR', phase_after='TERMINAL', mode='NOMINAL', decision='STOP', effective_decision='STOP',
                action=[0., 0., 0.], original_action=[0., 0., 0.], nav_vector=[0., 0., 0.],
                recovery_steps=0, stabilization_wait_steps=1, missing_velocity_count=0, terminal_reason='FIXTURE_STOP')
            ledger.event(a['id'], details={'type': 'PRE_PHYSICS_DECISION', 'record': event})
            episode = dict(controller=a['controller'], seed=a['seed'], steps=1, true_success=1, false_arrival=0,
                abstained=0, timeout=0, collision_occurred=0, range_bias_m=0., range_dropout_probability=0.,
                postproposal_monitor_steps=0, navigation_force_method=force, recovery_steps_limit=budget,
                post_stop={'decision_distance': .1, 'decision_speed': .2, 'steps': [
                    {'distance': .3, 'speed': .4, 'collision': False}, {'distance': .5, 'speed': .6, 'collision': True}]})
            ledger.complete(a['id'], status='COMPLETED', details={'episode': episode, 'last_events': [event], 'source_sha256_after': a['source_sha256']})
        if 'INCOMPLETE' not in states:
            ledger.finalize()


def grid(tmp_path, **kwargs):
    paths = []
    for force in FORCES:
        for budget in (100, 400):
            path = tmp_path / f'{force}_{budget}.jsonl'
            create_cell(path, force, budget, **kwargs)
            paths.append(path)
    return paths


def test_full_grid_keeps_post_stop_and_decision_state_distinct(tmp_path):
    result = compare(grid(tmp_path))
    assert len(result['cells']) == 4 and result['matched_assignments_per_cell'] == 2
    post = result['cells'][0]['assignments'][0]['post_stop']
    assert post['decision_speed'] == .2 and post['post_speed_min'] == .4 and post['post_speed_max'] == .6
    assert post['decision_distance'] == .1 and post['post_distance_max'] == .5
    assert post['post_collision_observed'] is True
    assert result['cells'][0]['outcome_counts']['true_success'] == 2
    assert all(row['recorded_decision_states_actions_equal'] is True
        for pair in result['decision_trace_comparisons'] for row in pair['assignments'])


def test_errors_and_incomplete_remain_in_assigned_denominator(tmp_path):
    result = compare(grid(tmp_path, states=('ERROR', 'INCOMPLETE')))
    for cell in result['cells']:
        assert cell['assigned'] == 2
        assert cell['execution_counts'] == {'ERROR': 1, 'INCOMPLETE': 1}
        assert sum(cell['outcome_counts'].values()) == 0
        assert all(row['post_stop'] is None and row['outcome'] is None for row in cell['assignments'])
    assert post_stop_summary(None) is None
    assert all(row['recorded_decision_states_actions_equal'] is None
        for pair in result['decision_trace_comparisons'] for row in pair['assignments'])


@pytest.mark.parametrize('defect', ['runtime', 'source', 'horizon', 'identity'])
def test_unequal_metadata_rejected(tmp_path, defect):
    paths = grid(tmp_path)
    extra = tmp_path / 'extra.jsonl'
    metadata = {
        'runtime': {'runtime': {'python': 'different'}},
        'source': {'source_sha256': {'fixture': 'b'*64}},
        'horizon': {'max_steps': 2},
        'identity': {'tag': 'unmatched'},
    }[defect]
    # Every nonfactor field must match, including unrecognized metadata.
    create_cell(extra, 'DIRECTION_PRESERVING_PEAK', 400, metadata=metadata)
    with pytest.raises(ValueError, match='unmatched'):
        compare(paths[:3] + [extra])


def test_missing_or_duplicate_factorial_cells_rejected(tmp_path):
    paths = grid(tmp_path)
    with pytest.raises(ValueError):
        compare(paths[:3])
    with pytest.raises(ValueError, match='duplicate'):
        compare(paths[:3] + [paths[0]])


def test_changed_validation_snapshot_rejected(tmp_path, monkeypatch):
    paths = grid(tmp_path)
    monkeypatch.setattr(factorial, 'analyze', lambda path: {'input_sha256': '0'*64})
    with pytest.raises(ValueError, match='changed'):
        compare(paths)
