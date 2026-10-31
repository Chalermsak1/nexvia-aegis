import pytest
from scripts.research.diagnose_recovery_transitions import summarize, diagnose
from scripts.research.development_ledger import DevelopmentLedger


def event(step, before, after, reason, decision='VERIFY'):
    return dict(step=step, phase_before=before, phase_after=after, mode='NOMINAL', terminal_reason=reason,
                effective_decision=decision, range_valid=True, range_fresh=True, anchor_requested=False,
                anchor_valid=None, next_query_anchor=False, low_speed_samples=None,
                velocity_observation=[0., 0., 0.], anchor=None, action=[0., 0., 0.])


def test_recovery_timeout_counts_attempted_update_and_preserves_missing_fields():
    rows = [event(0, 'BASE', 'RECOVERY', 'RECOVERY_ANCHOR_REQUESTED'),
            event(1, 'RECOVERY', 'RECOVERY', 'ANCHOR_GUIDED_RECOVERY', 'NAVIGATE'),
            event(2, 'RECOVERY', 'TERMINAL', 'RECOVERY_TIMEOUT', 'ABSTAIN')]
    result = summarize(rows)
    assert result['recovery_update_observations'] == 2
    assert result['recovery_guidance_observations'] == 1
    assert result['last_recorded_reason'] == 'RECOVERY_TIMEOUT'
    assert len(result['phase_transitions']) == 2
    assert result['low_speed_samples_recorded'] == []
    assert result['low_speed_samples_unavailable_count'] == 3
    assert result['availability_counts']['anchor_valid'] == {'unrecorded_or_not_applicable': 3}


def test_empty_unstarted_assignment_has_no_invented_terminal_reason():
    result = summarize([])
    assert result['last_recorded_reason'] is None
    assert result['recovery_update_observations'] == 0


@pytest.mark.parametrize('defect', ['order', 'missing_phase', 'flag', 'low_speed', 'vector'])
def test_invalid_or_ambiguous_transition_evidence_rejected(defect):
    row = event(0, 'RECOVERY', 'RECOVERY', 'ANCHOR_GUIDED_RECOVERY', 'NAVIGATE')
    if defect == 'order': row['step'] = 1
    if defect == 'missing_phase': del row['phase_before']
    if defect == 'flag': row['anchor_valid'] = 1
    if defect == 'low_speed': row['low_speed_samples'] = True
    if defect == 'vector': row['action'] = [float('nan'), 0., 0.]
    with pytest.raises(ValueError):
        summarize([row])


def test_error_and_incomplete_assignments_preserved(tmp_path):
    path = tmp_path / 'partial.jsonl'
    assignments = [dict(id=str(i), seed=2254000, bias_xyz=[0., 0., 0.], controller=arm,
        navigation_force_method='AXIS_CLIP',
        case={'name': 'nominal', 'range_bias_m': 0., 'range_dropout_probability': 0.},
        max_steps=10, post_stop_steps=1) for i, arm in enumerate(('AEGIS_3D_ANCHOR_RECOVERY', 'AEGIS_3D_RECOVERY_MONITOR'))]
    with DevelopmentLedger.create(path, study='V9-M5 exploratory recovery monitor', assignments=assignments, record_events=True) as ledger:
        ledger.start('0')
        row = event(0, 'BASE', 'BASE', 'ACTIVE', 'NAVIGATE')
        row.update(navigation_force_method='AXIS_CLIP', navigation_force_transformed=False,
                   original_action=[0., 0., 0.], nav_vector=[0., 0., 0.], decision='NAVIGATE')
        ledger.event('0', details={'type': 'PRE_PHYSICS_DECISION', 'record': row})
        ledger.complete('0', status='ERROR', details={'error': 'synthetic'})
    result = diagnose(path)
    assert result['ledger_state'] == 'INCOMPLETE'
    assert [row['execution_status'] for row in result['episodes']] == ['ERROR', 'INCOMPLETE']
    assert result['episodes'][0]['diagnostic']['decision_events'] == 1
    assert result['episodes'][1]['diagnostic']['last_recorded_reason'] is None
