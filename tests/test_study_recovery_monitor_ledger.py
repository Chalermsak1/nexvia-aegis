"""Synthetic runner integration: every assignment is recorded once."""
import sys
import pytest
from scripts.research import study_recovery_monitor_ledger as study
from scripts.research.development_ledger import inspect
from scripts.research.analyze_recovery_monitor_ledger import analyze
from scripts.research.diagnose_recovery_progress import diagnose


def test_runner_records_success_and_error_without_silent_retry(tmp_path, monkeypatch):
    target = tmp_path / "run.jsonl"
    monkeypatch.setattr(sys, "argv", ["study", "--seed-start", "12345", "--n-seeds", "1", "--output", str(target)])
    monkeypatch.setattr(study, "hashes", lambda: {"fixture.py": "a" * 64})
    monkeypatch.setattr(study, "AegisMuJoCo3DEnvironment", lambda: object())
    calls = []

    def fake_run(env, arm, seed, bias, max_steps, **kwargs):
        calls.append((arm, seed, tuple(bias)))
        if len(calls) == 1:
            raise RuntimeError("synthetic failure")
        return {"controller": arm, "seed": seed}

    monkeypatch.setattr(study, "run_3d_episode", fake_run)
    study.main()
    evidence = inspect(target)
    assert len(calls) == 12
    assert evidence["state"] == "FINALIZED_WITH_ERRORS"
    assert evidence["counts"] == {"ASSIGNED": 0, "STARTED": 0, "COMPLETED": 11, "ERROR": 1}
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        study.main()
    assert target.read_bytes() == before and len(calls) == 12


def test_real_development_simulation_persists_ordered_decisions(tmp_path, monkeypatch):
    target = tmp_path / "steps.jsonl"
    monkeypatch.setattr(sys, "argv", ["study", "--seed-start", "2252000", "--n-seeds", "1",
        "--max-steps", "5", "--post-stop-steps", "1", "--incremental-events", "--output", str(target)])
    study.main()
    evidence = inspect(target)
    assert evidence["schema"].endswith("/2")
    assert evidence["state"] == "FINALIZED"
    assert sum(evidence["event_counts"].values()) == 60
    assert analyze(target)["ledger_state"] == "FINALIZED"
    progress = diagnose(target)
    assert len(progress["episodes"]) == 12
    assert all(row["observations"]["decision_observations"] == 5 for row in progress["episodes"])


def test_explicit_case_subset_preserves_matched_assignment_grid(tmp_path, monkeypatch):
    target = tmp_path / "subset.jsonl"
    monkeypatch.setattr(sys, "argv", ["study", "--seed-start", "2252000", "--n-seeds", "1",
        "--max-steps", "2", "--post-stop-steps", "1", "--case", "nominal", "--incremental-events", "--output", str(target)])
    study.main()
    assert len(diagnose(target)["episodes"]) == 4


def test_incremental_events_survive_simulated_episode_failure(tmp_path, monkeypatch):
    target = tmp_path / "failed.jsonl"
    monkeypatch.setattr(sys, "argv", ["study", "--seed-start", "12345", "--n-seeds", "1",
        "--incremental-events", "--output", str(target)])
    monkeypatch.setattr(study, "hashes", lambda: {"fixture.py": "a" * 64})
    monkeypatch.setattr(study, "AegisMuJoCo3DEnvironment", lambda: object())

    def fake_run(env, arm, seed, bias, max_steps, **kwargs):
        kwargs["on_trace"]({"step": 0})
        raise RuntimeError("synthetic failure after decision")

    monkeypatch.setattr(study, "run_3d_episode", fake_run)
    study.main()
    evidence = inspect(target)
    assert evidence["state"] == "FINALIZED_WITH_ERRORS"
    assert evidence["counts"]["ERROR"] == 12
    assert sum(evidence["event_counts"].values()) == 12
