from copy import deepcopy
import pytest
from scripts.research import bounded_estimation_study as study
from scripts.research.development_ledger import DevelopmentLedger, LedgerWriteError, inspect


@pytest.fixture(scope='module')
def study_log(tmp_path_factory):
    path = tmp_path_factory.mktemp('bounded_study') / 'study.jsonl'
    result = study.run(path)
    return path, result


def test_full_study_continues_physics_after_no_command(study_log):
    path, r = study_log
    assert r['ledger_state'] == 'FINALIZED'
    assert r['assignment_counts']['COMPLETED'] == 54
    assert len(r['pair_checks']) == 27
    assert all(p['status'] == 'MATCHED_RESET_RUNTIME_INNOVATIONS_ONLY' for p in r['pair_checks'])
    assert all(a['summary']['physics_steps'] == 80 for a in r['assignments'])
    assert any(a['summary']['no_command'] for a in r['assignments'])
    assert sum(a['summary']['collision_samples'] for a in r['assignments']) == 0
    assert study.audit(path) == r


def test_honest_and_undeclared_reversal_are_distinguished(study_log):
    rows = study_log[1]['assignments']
    honest = [a for a in rows if ':reversal_reported:BOUNDED' in a['id']]
    dishonest = [a for a in rows if ':reversal_unreported:BOUNDED' in a['id']]
    assert all(a['summary']['positive_power_samples_for_scoring'] == 0 and a['summary']['no_command'] >= 74 for a in honest)
    assert all(a['summary']['declared_bound_violations_for_scoring'] > 0 and a['summary']['positive_power_samples_for_scoring'] > 0 for a in dishonest)
    delayed = [a for a in rows if ':delayed:' in a['id']]
    assert all(a['summary']['declared_bound_violations_for_scoring'] == 0 for a in delayed)


def test_exclusive_output_preserves_previous_bytes(study_log):
    path = study_log[0]; before = path.read_bytes()
    with pytest.raises(FileExistsError): study.run(path)
    assert path.read_bytes() == before


def rewrite(path, records):
    with DevelopmentLedger.create(path, study=study.STUDY, assignments=records[0]['assignments'], record_events=True) as w:
        for r in records[1:]:
            if r['kind'] == 'START': w.start(r['id'])
            elif r['kind'] == 'EVENT': w.event(r['id'], details=r['details'])
            elif r['kind'] == 'TERMINAL': w.complete(r['id'], status=r['status'], details=r['details'])
            else: w.finalize()


@pytest.mark.parametrize('defect', ['force', 'score', 'geometry', 'missing_physics', 'summary', 'identity', 'paired_noise', 'impulse'])
def test_rehashed_contradictions_are_rejected(study_log, tmp_path, defect):
    records = deepcopy(inspect(study_log[0])['records'])
    control = next(r['details'] for r in records if r['kind'] == 'EVENT' and r['details']['type'] == 'CONTROL')
    physics = next(r['details'] for r in records if r['kind'] == 'EVENT' and r['details']['type'] == 'PHYSICS')
    terminal = next(r for r in records if r['kind'] == 'TERMINAL')
    if defect == 'force': control['applied_incremental_force_n'][0] += 1
    elif defect == 'score': control['scoring']['force_dot_true_velocity_before_w'] += 1
    elif defect == 'geometry': physics['boundary_clearance'] += 1
    elif defect == 'missing_physics': records.remove(next(r for r in records if r['kind'] == 'EVENT' and r['details']['type'] == 'PHYSICS'))
    elif defect == 'paired_noise': control['noise_velocity'][0] += 1
    elif defect == 'impulse': physics['velocity_after'][0] += 1
    elif defect == 'summary': terminal['details']['summary']['no_command'] += 1
    else: terminal['details']['sources_after']['src/aegis/development/bounded_braking.py'] = '0' * 64
    path = tmp_path / 'bad.jsonl'; rewrite(path, records)
    with pytest.raises(ValueError): study.audit(path)


def test_sink_failure_does_not_silently_apply_unrecorded_force(tmp_path, monkeypatch):
    path = tmp_path / 'partial.jsonl'
    original = DevelopmentLedger.event
    def fail(self, identifier, *, details):
        if details['type'] == 'CONTROL': raise LedgerWriteError('synthetic sink failure')
        return original(self, identifier, details=details)
    monkeypatch.setattr(DevelopmentLedger, 'event', fail)
    with pytest.raises(LedgerWriteError): study.run(path)
    r = study.audit(path)
    assert r['ledger_state'] == 'INCOMPLETE'
    assert r['assignment_counts']['STARTED'] == 1 and r['assignment_counts']['ASSIGNED'] == 53
    assert r['assignments'][0]['summary'] is None
    ev = [r['details']['type'] for r in inspect(path)['records'] if r['kind'] == 'EVENT']
    assert ev == ['RESET']


def test_runtime_failure_retains_error_and_unstarted_assignments(tmp_path, monkeypatch):
    path = tmp_path / 'runtime_error.jsonl'
    def fail(a, emit):
        raise RuntimeError('synthetic unavailable simulator')
    monkeypatch.setattr(study, 'run_assignment', fail)
    with pytest.raises(RuntimeError): study.run(path)
    r = study.audit(path)
    assert r['ledger_state'] == 'INCOMPLETE'
    assert r['assignment_counts'] == {'ASSIGNED': 53, 'STARTED': 0, 'COMPLETED': 0, 'ERROR': 1}
    assert r['assignments'][0]['summary'] is None
    assert all(p['status'] == 'UNEVALUABLE_INCOMPLETE_PAIR' for p in r['pair_checks'])
