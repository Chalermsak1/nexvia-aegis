from copy import deepcopy
import pytest
from scripts.research import dual_source_fallback_study as study
from scripts.research.development_ledger import DevelopmentLedger, LedgerWriteError, inspect


@pytest.fixture(scope='module')
def completed(tmp_path_factory):
    path = tmp_path_factory.mktemp('dual_study') / 'all.jsonl'
    result = study.run(path)
    return path, result


def test_fixed_plan_and_full_physics_after_refusal(completed):
    _, r = completed
    assert len(study.plan()) == 108
    assert r['ledger_state'] == 'FINALIZED' and r['counts']['COMPLETED'] == 108
    assert len(r['matched_triples']) == 36
    assert all(t['status'] == 'MATCHED_RESET_RUNTIME_NOISE_ONLY' for t in r['matched_triples'])
    assert all(a['summary']['physics_steps'] == 100 for a in r['assignments'])
    assert sum(a['summary']['collision_samples'] for a in r['assignments']) == 0


def rows(completed, case, arm):
    return [a['summary'] for a in completed[1]['assignments'] if a['id'].endswith(f':{case}:{arm}')]


def test_individual_fault_refusal_and_damper_motion(completed):
    for case in ('primary_reverse', 'secondary_reverse', 'primary_position_bias', 'secondary_position_bias'):
        coast, damper = rows(completed, case, 'DUAL_COAST'), rows(completed, case, 'DUAL_DAMPER')
        assert all(r['first_refusal_step'] == 6 and r['first_refusal_reason'] == 'CONTRADICTORY_SOURCE_BALLS' for r in coast + damper)
        assert all(r['damper_active_steps'] == 91 for r in damper)
        assert all(d['final_sampled_speed_m_s'] < c['final_sampled_speed_m_s'] for c, d in zip(coast, damper))
        assert all(d['positive_command_power_samples'] == 0 for d in damper)


def test_common_mode_and_retimestamping_remain_visible(completed):
    for arm in ('DUAL_COAST', 'DUAL_DAMPER'):
        reversal = rows(completed, 'shared_reverse', arm)
        assert all(r['positive_command_power_samples'] > 0 and r['damper_active_steps'] == 0 for r in reversal)
        assert all(r['first_refusal_step'] is None for r in reversal)
        position = rows(completed, 'shared_position_bias', arm)
        assert all(r['primary_raw_bound_violations'] > 0 and r['secondary_raw_bound_violations'] > 0 for r in position)
        delayed = rows(completed, 'shared_retimestamped_stale', arm)
        assert all(r['primary_raw_bound_violations'] > 0 and r['secondary_raw_bound_violations'] > 0 for r in delayed)


def test_unavailable_fallback_is_not_classified_as_active(completed):
    r = rows(completed, 'damper_unavailable', 'DUAL_DAMPER')
    assert all(a['damper_failed_steps'] > 0 and a['damper_active_steps'] == 0 for a in r)
    assert all(a['classification'] == 'DEVELOPMENT_DIAGNOSTIC_NOT_A_RECOVERY_OR_SAFETY_PASS' for a in r)


def test_saved_ledger_reanalysis_and_no_overwrite(completed):
    path, result = completed
    assert study.audit(path) == result
    before = path.read_bytes()
    with pytest.raises(FileExistsError): study.run(path)
    assert path.read_bytes() == before


@pytest.fixture(scope='module')
def episode(completed):
    log = inspect(completed[0]); assignment = next(a for a in log['records'][0]['assignments'] if a['id'] == 'w0:primary_reverse:DUAL_DAMPER')
    events = [r['details'] for r in log['records'] if r['kind'] == 'EVENT' and r['id'] == assignment['id']]
    terminal = next(r['details'] for r in log['records'] if r['kind'] == 'TERMINAL' and r['id'] == assignment['id'])
    return assignment, events, terminal


@pytest.mark.parametrize('defect', ['force', 'union_bound', 'packet', 'noise', 'switch', 'ack', 'impulse', 'geometry', 'summary', 'missing_physics', 'source', 'time'])
def test_episode_contradictions_reject(episode, defect):
    a, original, term = episode
    ev, t = deepcopy(original), deepcopy(term)
    c, p = ev[1], ev[2]
    if defect == 'force': c['force_n'][0] += 1
    elif defect == 'union_bound': c['selection']['union_power_upper_w'] -= 1
    elif defect == 'packet': c['packets'][1]['velocity'][0] += 1
    elif defect == 'noise': c['noise'][0]['velocity'][0] += .01
    elif defect == 'switch': ev[1 + 2 * 6]['switch']['activation_due_step'] += 1
    elif defect == 'ack': ev[2 + 2 * 9]['runtime_dof_damping'][0] = 0.
    elif defect == 'impulse': p['velocity'][0] += .01
    elif defect == 'geometry': p['boundary_clearance'] += 1
    elif defect == 'summary': t['summary']['damper_active_steps'] += 1
    elif defect == 'missing_physics': ev.pop(2)
    elif defect == 'source': t['sources_after'] = {}
    else: c['time'] += .01
    with pytest.raises(ValueError): study.audit_episode(a, ev, t, a['metadata'])


def test_valid_hash_chain_with_false_fallback_receipt_rejects(episode, tmp_path):
    a, ev, term = episode; changed = deepcopy(ev)
    changed[2 + 2 * 9]['runtime_dof_damping'] = [0., 0., 0.]
    assignments = [dict(p, metadata=a['metadata']) for p in study.plan()]
    path = tmp_path / 'false_ack.jsonl'
    with DevelopmentLedger.create(path, study=study.STUDY, assignments=assignments, record_events=True) as w:
        w.start(a['id'])
        for e in changed: w.event(a['id'], details=e)
        w.complete(a['id'], status='COMPLETED', details=term)
    with pytest.raises(ValueError): study.audit(path)


def test_sink_failure_preserves_unexecuted_commands(tmp_path, monkeypatch):
    path = tmp_path / 'sink_failure.jsonl'; original = DevelopmentLedger.event
    def fail(self, identifier, *, details):
        if details['type'] == 'CONTROL': raise LedgerWriteError('synthetic sink failure')
        return original(self, identifier, details=details)
    monkeypatch.setattr(DevelopmentLedger, 'event', fail)
    with pytest.raises(LedgerWriteError): study.run(path)
    r = study.audit(path)
    assert r['counts']['STARTED'] == 1 and r['counts']['ASSIGNED'] == 107
    assert r['assignments'][0]['summary'] is None
    assert [x['details']['type'] for x in inspect(path)['records'] if x['kind'] == 'EVENT'] == ['RESET']


def test_simulator_error_retains_error_and_remaining_assignments(tmp_path, monkeypatch):
    path = tmp_path / 'runtime_failure.jsonl'
    def fail(a, emit): raise RuntimeError('synthetic unavailable simulator')
    monkeypatch.setattr(study, 'run_episode', fail)
    with pytest.raises(RuntimeError): study.run(path)
    r = study.audit(path)
    assert r['counts'] == {'ASSIGNED': 107, 'STARTED': 0, 'COMPLETED': 0, 'ERROR': 1}
    assert r['ledger_state'] == 'INCOMPLETE'
    assert all(v['status'] == 'UNEVALUABLE_INCOMPLETE' for v in r['matched_triples'])


def test_relabelled_stale_data_invalidates_conditional_path_bound(completed):
    stale = rows(completed, 'shared_retimestamped_stale', 'DUAL_DAMPER')
    assert all(r['retrospective_path_check']['exceeds_conditional_bound'] is True for r in stale)
    honest = rows(completed, 'primary_reverse', 'DUAL_DAMPER')
    assert all(r['retrospective_path_check']['exceeds_conditional_bound'] is False for r in honest)
    unavailable = rows(completed, 'damper_unavailable', 'DUAL_DAMPER')
    assert all(r['retrospective_path_check']['reference']['additional_path_upper_m'] is None for r in unavailable)
