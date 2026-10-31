import pytest
from scripts.research.diagnose_recovery_progress import summarize_events


def events(distances):
    return [dict(step=i, true_distance=d, mode='NOMINAL', effective_decision='NAVIGATE') for i, d in enumerate(distances)]


def test_progress_and_tail_can_disagree_without_inventing_stall_threshold():
    result = summarize_events(events([5., 3., 1., 2., 3.]), tail_steps=3)
    assert result['observed_distance_reduction_m'] == 2.
    assert result['tail_distance_reduction_m'] == -2.
    assert result['minimum_observed_distance_m'] == 1.
    assert result['effective_decision_counts'] == {'NAVIGATE': 5}


@pytest.mark.parametrize('distances', [[float('nan')], [float('inf')], [-1.], [True]])
def test_invalid_distance_rejected(distances):
    with pytest.raises(ValueError):
        summarize_events(events(distances))


def test_short_and_single_observation_are_not_final_state_claims():
    result = summarize_events(events([3.]))
    assert result['tail_observations'] == 1
    assert result['tail_distance_reduction_m'] == 0.
    assert result['interpretation'] == 'DESCRIPTIVE_ONLY_NO_CAUSAL_OR_SAFETY_CLASSIFICATION'


def test_missing_or_reordered_events_rejected():
    rows = events([2., 1.])
    rows[1]['step'] = 3
    with pytest.raises(ValueError):
        summarize_events(rows)
    with pytest.raises(ValueError):
        summarize_events([])
    with pytest.raises(ValueError):
        summarize_events(events([2., 1.]), tail_steps=1)
