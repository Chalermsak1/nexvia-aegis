import json
import os
import subprocess
import sys
import pytest
from scripts.research import development_ledger as ledger


def create(path):
    return ledger.DevelopmentLedger.create(path, study="synthetic", assignments=[
        {"id": "case-a", "fault": "none"}, {"id": "case-b", "fault": "dropout"}])


def test_success_and_error_are_distinct_and_finalized_explicitly(tmp_path):
    path = tmp_path / "runs.jsonl"
    with create(path) as writer:
        writer.start("case-a")
        writer.complete("case-a", status="COMPLETED", details={"score": 0})
        writer.start("case-b")
        writer.complete("case-b", status="ERROR", details={"type": "synthetic exception"})
        assert ledger.inspect(path)["state"] == "INCOMPLETE"
        writer.finalize()
    result = ledger.inspect(path)
    assert result["state"] == "FINALIZED_WITH_ERRORS"
    assert result["counts"] == {"ASSIGNED": 0, "STARTED": 0, "COMPLETED": 1, "ERROR": 1}


def test_interruption_leaves_assigned_and_started_visible_and_no_implicit_resume(tmp_path):
    path = tmp_path / "interrupted.jsonl"
    with create(path) as writer:
        writer.start("case-a")
        with pytest.raises(ledger.LedgerError):
            writer.finalize()
    result = ledger.inspect(path)
    assert result["state"] == "INCOMPLETE"
    assert result["assignments"] == {"case-a": "STARTED", "case-b": "ASSIGNED"}
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        create(path)
    assert path.read_bytes() == before


def test_process_exit_after_fsynced_start_keeps_incomplete_assignment(tmp_path):
    path = tmp_path / "killed.jsonl"
    code = '''import os,sys
from scripts.research.development_ledger import DevelopmentLedger
w=DevelopmentLedger.create(sys.argv[1],study="synthetic",assignments=[{"id":"a"}])
w.start("a")
os._exit(73)
'''
    result = subprocess.run([sys.executable, "-c", code, str(path)], check=False)
    assert result.returncode == 73
    assert ledger.inspect(path)["assignments"] == {"a": "STARTED"}


def test_duplicate_transitions_and_unplanned_ids_rejected(tmp_path):
    with create(tmp_path / "duplicates.jsonl") as writer:
        with pytest.raises(ledger.LedgerError): writer.start("unknown")
        with pytest.raises(ledger.LedgerError): writer.start([])
        with pytest.raises(ledger.LedgerError): writer.complete("case-a", status="COMPLETED", details={})
        writer.start("case-a")
        with pytest.raises(ledger.LedgerError): writer.start("case-a")
        writer.complete("case-a", status="ERROR", details={})
        with pytest.raises(ledger.LedgerError): writer.complete("case-a", status="ERROR", details={})


def test_partial_line_and_tampering_never_silently_recovered(tmp_path):
    path = tmp_path / "damaged.jsonl"
    with create(path) as writer: writer.start("case-a")
    with path.open("ab") as f: f.write(b'{"incomplete":')
    before = path.read_bytes()
    with pytest.raises(ledger.LedgerError): ledger.inspect(path)
    assert path.read_bytes() == before
    other = tmp_path / "tampered.jsonl"
    with create(other) as writer: writer.start("case-a")
    content = other.read_bytes().replace(b'"case-a"', b'"case-z"', 1)
    other.write_bytes(content)
    with pytest.raises(ledger.LedgerError): ledger.inspect(other)


def test_fsync_failure_poison_writer_and_preserve_file(tmp_path, monkeypatch):
    path = tmp_path / "failed.jsonl"
    writer = create(path)
    def fail(_fd): raise OSError("injected fsync failure")
    monkeypatch.setattr(ledger.os, "fsync", fail)
    with pytest.raises(ledger.LedgerWriteError): writer.start("case-a")
    with pytest.raises(ledger.LedgerError): writer.start("case-b")
    writer.close()
    assert path.exists()


def test_creation_directory_fsync_failure_does_not_remove_or_reuse_path(tmp_path, monkeypatch):
    path = tmp_path / "creation_failed.jsonl"
    def fail(_directory): raise OSError("injected directory fsync failure")
    monkeypatch.setattr(ledger, "_fsync_directory", fail)
    with pytest.raises(OSError): create(path)
    assert path.exists()
    assert path.read_bytes() == b""
    with pytest.raises(FileExistsError): create(path)
    with pytest.raises(ledger.LedgerError): ledger.inspect(path)


def test_short_write_loop_and_zero_write_failure(tmp_path, monkeypatch):
    path = tmp_path / "short.jsonl"
    writer = create(path)
    original = os.write
    monkeypatch.setattr(ledger.os, "write", lambda fd, data: original(fd, data[:7]))
    writer.start("case-a")
    assert ledger.inspect(path)["assignments"]["case-a"] == "STARTED"
    monkeypatch.setattr(ledger.os, "write", lambda fd, data: 0)
    with pytest.raises(ledger.LedgerWriteError): writer.start("case-b")
    writer.close()


def test_validates_manifest_finite_json_and_terminal_detail(tmp_path):
    with pytest.raises(ledger.LedgerError):
        ledger.DevelopmentLedger.create(tmp_path / "dup.jsonl", study="synthetic", assignments=[{"id": "a"}, {"id": "a"}])
    with create(tmp_path / "finite.jsonl") as writer:
        writer.start("case-a")
        with pytest.raises(ledger.LedgerError): writer.complete("case-a", status="COMPLETED", details={"v": float("nan")})
        writer.complete("case-a", status="COMPLETED", details={"v": 1})


def test_inspector_rejects_duplicate_json_keys_and_rehashed_duplicate_event(tmp_path):
    path = tmp_path / "duplicate_keys.jsonl"
    with create(path): pass
    path.write_bytes(path.read_bytes().replace(b'{"index":0', b'{"index":0,"index":0', 1))
    with pytest.raises(ledger.LedgerError): ledger.inspect(path)
    path = tmp_path / "duplicate_event.jsonl"
    with create(path) as writer: writer.start("case-a")
    lines = path.read_bytes().splitlines()
    last = json.loads(lines[-1])
    event = ledger._entry(2, last["sha256"], {"kind": "START", "id": "case-a"})
    with path.open("ab") as f: f.write(ledger._encode(event) + b"\n")
    with pytest.raises(ledger.LedgerError): ledger.inspect(path)


def test_v2_events_are_ordered_and_retain_incomplete_work(tmp_path):
    path = tmp_path / "events.jsonl"
    with ledger.DevelopmentLedger.create(path, study="synthetic", assignments=[{"id": "a"}], record_events=True) as writer:
        with pytest.raises(ledger.LedgerError): writer.event("a", details={"step": 0})
        writer.start("a")
        writer.event("a", details={"step": 0})
        writer.event("a", details={"step": 1})
    result = ledger.inspect(path)
    assert result["state"] == "INCOMPLETE" and result["event_counts"] == {"a": 2}
    assert [r["details"]["step"] for r in result["records"] if r["kind"] == "EVENT"] == [0, 1]


def test_v2_fsynced_event_survives_process_exit_in_test_filesystem(tmp_path):
    path = tmp_path / "killed_events.jsonl"
    code = '''import os,sys
from scripts.research.development_ledger import DevelopmentLedger
w=DevelopmentLedger.create(sys.argv[1],study="synthetic",assignments=[{"id":"a"}],record_events=True)
w.start("a")
w.event("a",details={"step":0})
os._exit(73)
'''
    result = subprocess.run([sys.executable, "-c", code, str(path)], check=False)
    assert result.returncode == 73
    assert ledger.inspect(path)["event_counts"] == {"a": 1}


def test_v2_rejects_out_of_order_rehashed_event_and_v1_rejects_events(tmp_path):
    path = tmp_path / "bad_events.jsonl"
    with ledger.DevelopmentLedger.create(path, study="synthetic", assignments=[{"id": "a"}], record_events=True) as writer:
        writer.start("a")
    last = json.loads(path.read_bytes().splitlines()[-1])
    event = ledger._entry(2, last["sha256"], {"kind": "EVENT", "id": "a", "event_index": 1, "details": {}})
    with path.open("ab") as f: f.write(ledger._encode(event) + b"\n")
    with pytest.raises(ledger.LedgerError): ledger.inspect(path)
    with create(tmp_path / "v1.jsonl") as writer:
        writer.start("case-a")
        with pytest.raises(ledger.LedgerError): writer.event("case-a", details={})


def test_v2_event_fsync_failure_poisoning_does_not_prove_durability(tmp_path, monkeypatch):
    path = tmp_path / "event_fsync_failure.jsonl"
    writer = ledger.DevelopmentLedger.create(path, study="synthetic", assignments=[{"id": "a"}], record_events=True)
    writer.start("a")
    def fail(_fd): raise OSError("injected fsync failure")
    monkeypatch.setattr(ledger.os, "fsync", fail)
    with pytest.raises(ledger.LedgerWriteError): writer.event("a", details={"step": 0})
    with pytest.raises(ledger.LedgerError): writer.complete("a", status="COMPLETED", details={})
    writer.close()
    # A visible entry after a failed fsync is not evidence that it is durable.
    assert ledger.inspect(path)["state"] == "INCOMPLETE"
