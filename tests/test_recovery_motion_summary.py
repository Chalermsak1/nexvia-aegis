"""Synthetic retained-sample diagnostics, without inventing a stopping threshold."""
import math
import sys
import pytest
from scripts.research import summarize_recovery_motion as motion
from scripts.research.development_ledger import DevelopmentLedger


def fixture(tmp_path, *, label='STOP', samples=2, requested=3, target_change=False, bad_anchor=False):
    path = tmp_path / 'motion.jsonl'
    assignment = {'id': 'case', 'post_stop_steps': requested, 'post_abstain_steps': requested if label == 'ABSTAIN' else 0}
    version = 'v2' if label == 'ABSTAIN' else 'v1'
    with DevelopmentLedger.create(path, study=f'V9-M5 recovery physical evidence {version}',
                                  assignments=[assignment], record_events=True) as ledger:
        ledger.start('case')
        decision = {'step': 0, 'effective_decision': label, 'position': [1., 0., 0.],
                    'target': [0., 0., 0.], 'true_distance': 1., 'velocity': [2., 0., 0.]}
        if bad_anchor:
            decision['position'] = [True, 0., 0.]
        ledger.event('case', details={'type': 'DECISION', 'record': decision})
        count = samples + (label == 'ABSTAIN')
        for i in range(count):
            position = [1. + .1 * (i + 1), 0., 0.]
            target = [0., 1., 0.] if target_change and i == count - 1 else [0., 0., 0.]
            stage = ('ABSTAIN_BRAKE' if i == 0 else 'POST_ABSTAIN_BRAKE') if label == 'ABSTAIN' else 'POST_STOP_BRAKE'
            record = {'physics_step': i + 1, 'decision_step': 0, 'stage': stage,
                      'position': position, 'target': target, 'distance': math.dist(position, target),
                      'velocity': [1. / (i + 1), 0., 0.], 'projected_force': [0., 0., 0.],
                      'collision': i == 1, 'cbf_residual': None}
            ledger.event('case', details={'type': 'PHYSICS', 'record': record})
    return path


def test_partial_stop_is_not_a_completed_or_safe_interval(tmp_path):
    result = motion.summarize(fixture(tmp_path))
    row = result['assignments'][0]
    w = row['windows']['STOP']
    assert row['execution_status'] == 'INCOMPLETE'
    assert w['window_status'] == 'PARTIAL'
    assert w['observed_samples'] == 2 and w['requested_samples'] == 3
    assert w['collision_observed'] is True
    assert w['last_speed_m_s'] == .5 and w['anchor_speed_m_s'] == 2
    assert w['distance_change_from_anchor_m'] == pytest.approx(.2)
    assert w['sampled_polyline_from_anchor_m'] == pytest.approx(.2)
    assert w['min_observed_cbf_residual'] is None
    assert w['cbf_residual_observed_samples'] == 0
    assert w['elapsed_seconds'] is None
    assert w['physical_rest_classification'] == 'NOT_EVALUATED_NO_APPROVED_CRITERION'
    assert row['windows']['ABSTAIN']['window_status'] == 'NOT_REACHED'
    assert row['windows']['ABSTAIN']['collision_observed'] is None


def test_complete_samples_do_not_complete_an_interrupted_episode(tmp_path):
    row = motion.summarize(fixture(tmp_path, requested=2))['assignments'][0]
    assert row['execution_status'] == 'INCOMPLETE'
    assert row['windows']['STOP']['window_status'] == 'COMPLETE_OBSERVATION_WINDOW'


def test_abstain_anchor_is_original_brake_not_decision_time(tmp_path):
    row = motion.summarize(fixture(tmp_path, label='ABSTAIN'))['assignments'][0]
    w = row['windows']['ABSTAIN']
    assert w['anchor_speed_m_s'] == 1
    assert w['anchor_distance_m'] == 1.1
    assert w['observed_samples'] == 2
    assert w['last_speed_m_s'] == pytest.approx(1 / 3)
    assert w['distance_change_from_anchor_m'] == pytest.approx(.2)
    assert w['sampled_polyline_from_anchor_m'] == pytest.approx(.2)


@pytest.mark.parametrize('requested,status', [(3, 'MISSING'), (0, 'NOT_REQUESTED')])
def test_no_samples_produce_null_observations(tmp_path, requested, status):
    w = motion.summarize(fixture(tmp_path, samples=0, requested=requested))['assignments'][0]['windows']['STOP']
    assert w['window_status'] == status
    assert w['collision_observed'] is None
    assert w['last_speed_m_s'] is None
    assert w['sampled_polyline_from_anchor_m'] is None


def test_untouched_assignment_does_not_imply_collision_free(tmp_path):
    path = tmp_path / 'unstarted.jsonl'
    with DevelopmentLedger.create(path, study='V9-M5 recovery physical evidence v1',
                                  assignments=[{'id': 'case'}], record_events=True):
        pass
    row = motion.summarize(path)['assignments'][0]
    assert row['execution_status'] == 'INCOMPLETE'
    assert all(w['collision_observed'] is None and w['window_status'] == 'NOT_REACHED' for w in row['windows'].values())


@pytest.mark.parametrize('kwargs,error', [({'target_change': True}, 'target changes'),
                                         ({'bad_anchor': True}, 'anchor vector'),
                                         ({'requested': 1}, 'horizon overrun')])
def test_valid_hash_chain_does_not_mask_bad_motion_evidence(tmp_path, kwargs, error):
    with pytest.raises(ValueError, match=error):
        motion.summarize(fixture(tmp_path, **kwargs))


def test_input_replacement_is_detected(tmp_path, monkeypatch):
    path = fixture(tmp_path)
    monkeypatch.setattr(motion, 'analyze', lambda _: {'input_sha256': '0' * 64})
    with pytest.raises(ValueError, match='input changed'):
        motion.summarize(path)


def test_cli_never_overwrites_an_existing_report(tmp_path, monkeypatch):
    path = fixture(tmp_path)
    output = tmp_path / 'prior.json'
    output.write_text('keep historical bytes')
    monkeypatch.setattr(sys, 'argv', ['summary', str(path), '--output', str(output)])
    with pytest.raises(FileExistsError):
        motion.main()
    assert output.read_text() == 'keep historical bytes'


def test_path_length_does_not_collapse_out_and_back_motion():
    anchor = {'position': [1., 0., 0.], 'target': [0., 0., 0.],
              'velocity': [1., 0., 0.], 'distance': 1.}
    samples = [dict(position=[x, 0., 0.], target=[0., 0., 0.], distance=x,
                    velocity=[v, 0., 0.], collision=False, cbf_residual=r)
               for x, v, r in [(2., .2, None), (1., .8, -.1)]]
    w = motion._window(reached=True, requested=2, anchor=anchor, samples=samples)
    assert w['distance_change_from_anchor_m'] == 0
    assert w['sampled_polyline_from_anchor_m'] == 2
    assert w['last_speed_m_s'] == .8
    assert w['min_sample_speed_m_s'] == .2 and w['max_sample_speed_m_s'] == .8
    assert w['cbf_residual_observed_samples'] == 1
    assert w['min_observed_cbf_residual'] == -.1
    assert w['collision_observed'] is False
    assert w['physical_rest_classification'] == 'NOT_EVALUATED_NO_APPROVED_CRITERION'
