# LIVE01 atomic frame persistence and consumption timing

Declared before the final campaign using this backend, 2026-11-17. Exploratory engineering change, not a V9-M4 rule or production authorization. GATE_B_NOT_AUTHORIZED.

## Evidence and motivation

Per-record fsync of all nine frame witnesses and evaluations sometimes exceeds the unchanged native budget and preempts a planned fault with safe recovery. Preserve those failures/unqualified exposures. A second observed race let preliminary consumption validation outlive the permission during journal persistence.

## Atomic bundle backend

Add ATOMIC_BUNDLE_V1 alongside the retained per-record backend. Apply the unchanged EA01 transition/evaluation semantics to a bounded private frame transaction. Atomically fsync and commit the complete chained witness/evaluation bundle before any lease can be published or returned to the live actor. No durable claim is made from the internal uncommitted math result. Failure before commit preserves pending bytes and withholds publication. Exclusive frame-directory creation supplies the one-shot writer boundary; no resume/append or silent eviction is allowed.

The same checkpoints, predicate statuses and replay result must match the per-record implementation for identical inputs. Read-only replay validates every chain link and semantic transition. This reduces durable transaction count; it does not lengthen the native budget, freshness limit, lease or safety boundary.

## Consumption linearization

Validate before recording the consumption check and again after that record commits. Parse the candidate target before the final check. Timestamp the simulated target assignment immediately before a physics step can observe it. If expiry is observed during finalization, restore the old target before integration and retire the request. Record application time separately from the later evidence-record timestamp. A slow-commit regression must retire the expired request.

This is a simulated software lifecycle contract, not physical hard-real-time or physical exactly-once execution. Plant integrator and actuator guard share one process; a storage stall delays ideal integration, so it cannot establish real plant behavior through a host I/O stall. Physical independent actuation, storage/hardware guarantees and expert review remain unresolved.
