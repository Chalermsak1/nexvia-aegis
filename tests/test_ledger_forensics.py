import pytest
from scripts.research.development_ledger import DevelopmentLedger, LedgerError
from scripts.research.ledger_forensics import diagnose


def create(path):
    with DevelopmentLedger.create(path, study="synthetic", assignments=[{"id": "a"}], record_events=True) as w:
        w.start("a")
        w.event("a", details={"step": 0})


def test_valid_prefix_and_truncated_tail_are_reported_without_repair(tmp_path):
    path = tmp_path / "ledger.jsonl"
    create(path)
    original = path.read_bytes()
    damaged = original + b'{"index":'
    path.write_bytes(damaged)
    result = diagnose(path.read_bytes())
    assert result["inspection"] == "TRUNCATED_FINAL_LINE"
    assert result["prefix_state"] == "INCOMPLETE" and result["prefix_event_counts"] == {"a": 1}
    assert result["valid_prefix_bytes"] == len(original) and not result["claim_complete"]
    assert path.read_bytes() == damaged


def test_corrupt_complete_line_is_not_skipped(tmp_path):
    path = tmp_path / "ledger.jsonl"
    create(path)
    raw = path.read_bytes().replace(b'"event_index":0', b'"event_index":1') + b'{"partial":'
    with pytest.raises(LedgerError): diagnose(raw)


def test_finalized_prefix_plus_suffix_is_never_claimed_complete(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with DevelopmentLedger.create(path, study="synthetic", assignments=[{"id": "a"}], record_events=True) as w:
        w.start("a"); w.complete("a", status="COMPLETED", details={}); w.finalize()
    result = diagnose(path.read_bytes() + b'{"unexpected":')
    assert result["prefix_state"] == "FINALIZED" and result["inspection"] == "TRUNCATED_FINAL_LINE"
    assert not result["claim_complete"]


def test_no_complete_header_and_empty_evidence_are_rejected():
    with pytest.raises(LedgerError): diagnose(b'{"partial"')
    with pytest.raises(LedgerError): diagnose(b'')
