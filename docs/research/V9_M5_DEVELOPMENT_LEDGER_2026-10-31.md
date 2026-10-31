# V9-M5 exploratory development assignment ledger

**Status:** exploratory development prototype, subsequently integrated into separate development-only runners. This is not an authorization ledger, controlled manifest, production retention system, statistical decision rule, evidence of a complete experiment, or a safety guarantee. Gate B remains `GATE_B_NOT_AUTHORIZED`; this work did not run V9-M4 Holdout, inspect reserved seed contents, or alter frozen artifacts.

## Problem and mechanism

Some development runners collect outcomes in memory and serialize them at the end. Interruption can lose the assignment history or leave an unusable final file. `scripts/research/development_ledger.py` provides a separate, single-writer building block:

1. Create a **new** JSON Lines file exclusively with `O_CREAT | O_EXCL`; an existing file is never opened for append or overwritten. The initial header includes a caller-provided, nonempty, uniquely identified assignment list and the `EXPLORATORY_SIMULATION` label.
2. Write and `fsync` a `START` event **before** an assigned episode begins. The caller must not execute the episode until `start()` returns.
3. Append and `fsync` one terminal event for the same assignment: `COMPLETED` or `ERROR`, with caller-supplied details. Duplicate starts, terminal records, unknown assignments and nonfinite JSON are rejected.
4. Explicitly finalize only when every assignment has a terminal event. `FINALIZED_WITH_ERRORS` remains different from `FINALIZED`. Without a final record, even a file containing terminal records for every assignment remains `INCOMPLETE`.
5. Inspect the visible file with `inspect()`. It checks canonical JSON, a sequential unkeyed SHA-256 chain, assignment transitions, terminal statuses and final counts. It reports `ASSIGNED`, `STARTED`, `COMPLETED` and `ERROR` separately. An empty, corrupt or partial record raises `LedgerError`; no trailing data is silently dropped or repaired.

The API never resumes or retries an existing ledger. A `STARTED` assignment after interruption means the prior run's outcome is unknown; it is not automatically restarted or treated as failure or success. A new investigation or retry needs a separate, explicitly documented policy and a new evidence path.

An opt-in schema `/2` additionally appends ordered per-assignment `EVENT` records for a started assignment, syncing each write. Schema `/1` remains readable and is still the default. `inspect()` checks the event sequence and reports per-assignment event counts, but rejects a partial/corrupt trailing line rather than recovering a prefix. This does not prove successful durability after an fsync failure, authenticate the hash chain, solve concurrent writers or guarantee behavior under power loss. A development runner and process-interruption test exercise these records; see `V9_M5_INCREMENTAL_STEP_LEDGER_2026-10-31.md`.

## Minimal synthetic example

```python
from scripts.research.development_ledger import DevelopmentLedger, inspect

with DevelopmentLedger.create("NEW_LEDGER.jsonl", study="synthetic-demo", assignments=[
    {"id": "case-a", "case": "nominal"},
    {"id": "case-b", "case": "dropout"},
]) as ledger:
    ledger.start("case-a")  # durable START returns before running the assignment
    ledger.complete("case-a", status="COMPLETED", details={"result": "synthetic"})
    ledger.start("case-b")
    ledger.complete("case-b", status="ERROR", details={"reason": "synthetic fixture"})
    ledger.finalize()

print(inspect("NEW_LEDGER.jsonl")["state"])  # FINALIZED_WITH_ERRORS
```

## Durability and integrity limits

- File creation is exclusive, the parent directory is fsynced after creation, and every record is written with a short-write loop and file `fsync`. If a write or file `fsync` fails, the writer is poisoned and cannot append more records. A creation failure can leave an empty file; a record failure can leave a partial or fully visible line whose persistence is uncertain. These files must be preserved and investigated, never overwritten or automatically repaired.
- `fsync` failure or sudden power/storage failure cannot be proven absent merely by reading visible bytes. The synthetic test terminates a child process with `os._exit` after a returned `start()`, not a power-cut or hardware durability test. Actual guarantees depend on OS, filesystem, storage device and mount configuration.
- Hash chaining detects accidental alteration or deletion relative to the self-contained chain, but is unkeyed: an attacker can replace the file and recompute every hash. There is no authenticated signature, trusted external checkpoint, secure clock, independent manifest, schema-level scientific validation, automatic archival, filesystem locking, concurrent-writer support, access control beyond local permissions, or review of what the caller writes into `details`. Use one owning thread and prevent external mutation. The inspector reads the entire file into memory, so this prototype is unsuitable for unbounded streams.
- The header's assignments are self-declared. `COMPLETED` only means the caller recorded that status; the ledger does not infer scientific success, validate outcome truth, approve a protocol, or make time-step observations independent. Recording external source hashes or raw evidence remains the caller's responsibility, and those hashes require independent provenance to support stronger claims.
- Interrupted or failed records must remain explicitly incomplete/invalid, never relabeled as accepted. The code does not decide whether to retry, create a new ledger, or use partial evidence for analysis.

## Verification and integration work

`PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_development_ledger.py` exercises exclusive creation, assignment and terminal-state rules, preserved incomplete work after process exit, partial-line rejection, tampering and duplicate JSON keys, short writes, directory and file `fsync` failure, error accounting and invalid input. These are synthetic tests; no Holdout, production tickets or historical files are accessed.

Before using this for a real development experiment, integrate it into one **new** runner with an independently reviewed assignment plan; capture code/config/runtime and raw per-assignment outputs separately; ensure explicit start before execution and failure records on exceptions; test interruption at every event and output step on the actual target filesystem; and document data retention, review, retry and external checkpoint policies. Do not alter old runner outputs or replace historical evidence with a reconstructed ledger.
