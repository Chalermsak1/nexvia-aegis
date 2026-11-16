"""Retained phase/runtime contract and interrupted development-fixture evidence."""
from copy import deepcopy
import sys
import subprocess
import os
from pathlib import Path
import pytest
from scripts.research import synchronized_fixture_ledger as study
from scripts.research.development_ledger import DevelopmentLedger, LedgerWriteError, inspect
from scripts.research.analyze_recovery_physics_evidence import analyze as legacy_analyze


def completed(tmp_path):
    path = tmp_path / 'fixtures.jsonl'; study.run(path)
    return path


def rewrite(source, target, mutate):
    content = inspect(source); header = deepcopy(content['records'][0])
    records = deepcopy(content['records'][1:]); mutate(header, records)
    with DevelopmentLedger.create(target, study=header['study'], assignments=header['assignments'], record_events=True) as w:
        for r in records:
            if r['kind'] == 'START': w.start(r['id'])
            elif r['kind'] == 'EVENT': w.event(r['id'], details=r['details'])
            elif r['kind'] == 'TERMINAL': w.complete(r['id'], status=r['status'], details=r['details'])
            else: w.finalize()


def test_complete_fixtures_have_predeclared_metadata_and_incremental_steps(tmp_path):
    path = completed(tmp_path); result = study.analyze(path)
    assert result['ledger_state'] == 'FINALIZED'
    assert len(result['assignments']) == 6
    assert sum(r['persisted_steps'] for r in result['assignments']) == 14
    assert all(r['execution_status'] == 'COMPLETED' for r in result['assignments'])
    assert {r['id'] for r in result['assignments'] if r['collision_observed']} == {'floor_crossing','obstacle_crossing','boundary_crossing'}
    header = inspect(path)['records'][0]
    assert all(a['runtime']['environment_id'] == study.Environment.ENVIRONMENT_ID for a in header['assignments'])
    assert header['assignments'][0]['runtime']['runtime_timestep_seconds'] == .01
    assert result['assignments'][0]['persisted_step_seconds'] == pytest.approx(.03)
    with pytest.raises(ValueError, match='unexpected'):
        legacy_analyze(path)


@pytest.mark.parametrize('defect', ['identity','dt','phase','time','position','reset','terminal_count','runtime','source','collision','clearance','runtime_omission','source_omission'])
def test_valid_chain_does_not_hide_wrong_phase_or_incomplete_evidence(tmp_path, defect):
    path = completed(tmp_path); target = tmp_path / 'bad.jsonl'
    def mutate(header, records):
        step = next(r['details']['observation'] for r in records if r['kind'] == 'EVENT' and r['details']['type'] == 'STEP')
        reset = next(r['details']['observation'] for r in records if r['kind'] == 'EVENT' and r['details']['type'] == 'RESET')
        terminal = next(r['details'] for r in records if r['kind'] == 'TERMINAL')
        if defect == 'identity': header['assignments'][0]['runtime']['environment_id'] = 'LEGACY'
        elif defect == 'dt': header['assignments'][0]['runtime']['runtime_timestep_seconds'] = .02
        elif defect == 'phase': step['state_phase'] = 'PRE_INTEGRATION'
        elif defect == 'time': step['simulation_time_seconds'] += .01
        elif defect == 'position': step['integrated_translation_qpos'][0] += .1
        elif defect == 'reset': reset['velocity'][0] = 8
        elif defect == 'terminal_count': terminal['observed_steps'] -= 1
        elif defect == 'runtime': terminal['runtime_after']['runtime_timestep_seconds'] = .1
        elif defect == 'source': terminal['source_sha256_after'][study.FILES[0]] = '0' * 64
        elif defect == 'collision': step['contact_floor'] = True; step['collision'] = False
        elif defect == 'clearance': step['min_obstacle_distance'] += 1
        elif defect == 'runtime_omission':
            for value in (header['assignments'][0]['runtime'], terminal['runtime_after']): value.pop('integrator')
        elif defect == 'source_omission':
            for value in (header['assignments'][0]['source_sha256'], terminal['source_sha256_after']): value.pop(study.FILES[-1])
    rewrite(path, target, mutate)
    with pytest.raises(ValueError): study.analyze(target)


def test_sink_failure_preserves_unfinished_assignment_and_no_retry(tmp_path, monkeypatch):
    path = tmp_path / 'sink.jsonl'; calls = []
    original = DevelopmentLedger.event
    def fail(self, identifier, *, details):
        if details['type'] == 'STEP':
            calls.append(identifier)
            raise LedgerWriteError('synthetic persistence failure')
        return original(self, identifier, details=details)
    monkeypatch.setattr(DevelopmentLedger, 'event', fail)
    with pytest.raises(LedgerWriteError): study.run(path)
    assert len(calls) == 1
    result = study.analyze(path)
    assert result['ledger_state'] == 'INCOMPLETE'
    assert result['assignments'][0]['execution_status'] == 'STARTED'
    assert result['assignments'][0]['reset_observed'] is True
    assert result['assignments'][0]['collision_observed'] is None
    assert all(r['execution_status'] == 'ASSIGNED' for r in result['assignments'][1:])


def test_execution_error_is_retained_and_not_retried(tmp_path, monkeypatch):
    path = tmp_path / 'error.jsonl'; calls = []
    original = study.Environment.step
    def fail_first(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1: raise RuntimeError('synthetic execution error')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(study.Environment, 'step', fail_first)
    study.run(path)
    result = study.analyze(path)
    assert result['ledger_state'] == 'FINALIZED_WITH_ERRORS'
    assert result['assignments'][0]['execution_status'] == 'ERROR'
    assert result['assignments'][0]['persisted_steps'] == 0
    assert all(r['execution_status'] == 'COMPLETED' for r in result['assignments'][1:])
    assert len(calls) == 12  # one failed call plus 11 requested steps in other cases


def test_child_exit_after_first_persisted_step_stays_incomplete(tmp_path):
    path = tmp_path / 'interrupted.jsonl'
    script = '''
import os,sys
from scripts.research import synchronized_fixture_ledger as study
from scripts.research.development_ledger import DevelopmentLedger
original=DevelopmentLedger.event
def stop(self,identifier,*,details):
 original(self,identifier,details=details)
 if details['type']=='STEP':os._exit(43)
DevelopmentLedger.event=stop
study.run(sys.argv[1])
'''
    env = dict(os.environ, PYTHONPATH='src:.', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-c', script, str(path)], env=env, capture_output=True, text=True)
    assert result.returncode == 43, result.stderr
    row = study.analyze(path)['assignments'][0]
    assert row['execution_status'] == 'STARTED' and row['persisted_steps'] == 1
    assert row['persisted_step_seconds'] == pytest.approx(.01)


def test_existing_output_is_never_overwritten(tmp_path):
    path = tmp_path / 'keep.jsonl'; path.write_bytes(b'previous evidence')
    with pytest.raises(FileExistsError): study.run(path)
    assert path.read_bytes() == b'previous evidence'


def test_source_drift_during_execution_error_leaves_other_assignments_unrun(tmp_path, monkeypatch):
    path = tmp_path / 'drift.jsonl'
    original_hashes = study.hashes; calls = []
    def changing_hashes():
        calls.append(1); value = original_hashes()
        if len(calls) >= 3: value[study.FILES[0]] = '0' * 64
        return value
    def fail(*args, **kwargs): raise RuntimeError('synthetic execution error')
    monkeypatch.setattr(study, 'hashes', changing_hashes)
    monkeypatch.setattr(study.Environment, 'step', fail)
    with pytest.raises(RuntimeError, match='source changed during failed assignment'):
        study.run(path)
    states = inspect(path)['assignments']
    assert states['drift_10ms'] == 'ERROR'
    assert sum(v == 'ASSIGNED' for v in states.values()) == 5


def test_missing_declared_fixtures_cannot_appear_complete(tmp_path):
    path = completed(tmp_path); target = tmp_path / 'subset.jsonl'
    def mutate(header, records):
        header['assignments'] = header['assignments'][:1]
        records[:] = [r for r in records if r['kind'] == 'FINAL' or r.get('id') == 'drift_10ms']
    rewrite(path, target, mutate)
    with pytest.raises(ValueError, match='fixture coverage mismatch'):
        study.analyze(target)
