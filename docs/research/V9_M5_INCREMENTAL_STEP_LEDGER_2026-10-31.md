# Incremental development step ledger

**Status:** exploratory V9-M5 tooling and simulated braking micro-study, not a production/authorization ledger, independent provenance, registered endpoint, safety claim or V9-M4 Holdout. Gate B remains `GATE_B_NOT_AUTHORIZED`.

## Changes

The development ledger now optionally writes schema `nexvia-development-ledger/2` with per-assignment ordered `EVENT` records after `START`, each flushed with `fsync` before the next step. The existing `/1` schema remains the default and remains readable; historical evidence is not rewritten. `inspect()` validates the self-reported unkeyed hash chain, record order and event indexes, rejects partial/corrupt lines, and marks assignments without terminal records incomplete. It does not resume, repair, silently rerun, or infer that a started episode succeeded.

The separate `study_estimated_braking_v3.py` sends each MuJoCo braking event to a `/2` ledger as it occurs and also records the complete episode in its terminal record. `analyze_estimated_braking_ledger_v3.py` checks that the incremental event sequence equals the final episode event list, validates selected source maps and the self-declared paired grid, and applies the v2 vector/score checks. Episode errors and incomplete assignments remain distinct from completed episodes. A process-interruption integration test stops a real short MuJoCo episode immediately after its third event is written and observes three events with the assignment still `STARTED` in the test filesystem.

There is no guarantee that a complete line visible after a failed `fsync` is actually durable. Power loss, device caching, concurrent writers, process termination during a partial write, filesystem semantics, and the absence of independently signed manifests remain unresolved; `inspect()` rejects the full file if a trailing line is corrupt rather than automatically recovering a valid prefix. An unkeyed hash chain can be rewritten and is not authenticity or anti-rollback protection. Selected file hashes and assignments are self-reported, and full environment provenance is not established.

`scripts/research/ledger_forensics.py` adds a **read-only diagnostic** for a truncated final line. It validates every complete line as a prefix, reports separate hashes and sizes for the visible prefix and suffix, and never repairs, resumes, discards, or labels the damaged file complete. A prefix that itself says FINALIZED does not prove that the whole file or its writes are durable. Corruption in any complete line still raises an error. This tool is not an authority to recover or rerun a study. The ledger implementation was later refactored to share byte-level inspection with this diagnostic, so its current source hash differs from the v3 run below; historical v3 bytes and recorded hashes were not changed.

## Development smoke run

The new v3 runner assigned one development seed 2250000, four velocity cases, two arms and at most 40 steps: eight completed micro-episodes and **281 ordered events** (including one `NO_COMMAND`). The ledger's visible structure is FINALIZED with zero recorded execution errors. This is a smoke test, not a reliability estimate.

In the reversed-velocity estimated arm, all 40 control forces had a positive dot product with the true pre-step velocity and final true speed was approximately 1.6705 m/s. Missing velocity yielded `NO_COMMAND` before any physics step; this is not a safe-stop claim. The comparison's oracle arm does not receive the same sensor fault. The simulated known obstacle geometry, mass, gravity compensation and true-state sensor generation remain, so this is not a fully no-oracle physical system.

Raw `results/research_development/dev/estimated_braking_step_ledger_v3.jsonl` SHA-256 `c9e9fc6bb0db0444d9cd1b4c02002dec82f9ac207c2f3971d96175a85b47c3d2`; analysis `results/research_development/analysis/estimated_braking_step_ledger_v3_summary.json`. Earlier v1 and v2 files remain unchanged. Later modifications to a source file would change exact reproducibility even if code behavior is similar.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_estimated_braking_v3.py \
  --seed-start 2250000 --n-seeds 1 --max-steps 40 --output NEW_LEDGER.jsonl
PYTHONPATH=src .venv/bin/python scripts/research/analyze_estimated_braking_ledger_v3.py NEW_LEDGER.jsonl --output NEW_SUMMARY.json
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_development_ledger.py tests/test_analyze_estimated_braking_ledger_v3.py
```

Use fresh paths. Continue work on independently stored manifests and runtime identities, partial-record inspection without repair, no-oracle information parity, safe handling of absent controls, and practical sensor fault models before any prospective study or physical trial.
