# ADR-RC01 — Persistent feedback and runtime assurance foundations

**Status:** Proposed for operational use; development prototypes implemented and tested.

**Date:** 2026-11-17, Asia/Bangkok.

**Deciders:** Project owner and independent security/control/runtime reviewers. This document supplies no independent approval or Gate B authorization.

## Context

The existing temporal layer detects replay only during one object's lifetime and assumes a common discrete clock. A credible recovery assessment also depends on committed ingress state, restart identity/freshness, computation time, calibration evidence and a justified response. The owner requested development across all six areas. No physical hardware is available, and production tickets, Holdout data/execution, frozen scientific changes and Gate B authorization remain outside scope.

## Development decision

Implement separate, additive development modules for persistent temporal operations, exact two-clock interval mapping, restart checks, monotonic computation budgets, paired calibration evidence and a non-dispatchable response selector. Connect them in a fixed synthetic study. Preserve the previous components and scientific artifacts.

Use SQLite WAL with FULL synchronization for the bounded development store. Store operations and result digests transactionally, bind them to the source/runtime/configuration identity and an explicit store identity, reconstruct before reuse, and require an exact externally supplied checkpoint. Persist before returning an accepted result. Poison a connection after failure and require explicit reconciliation; do not retry an uncertain commit automatically.

SQLite commit durability depends on filesystem, VFS and storage synchronization behavior. Technical references are retained in the reference record (workspace record `../../results/research_development/analysis/runtime_core_references_2026-11-17.json`; not included in this lightweight upload). Ordinary process-exit tests do not prove physical power-loss durability. The prototype does not provide checkpoint custody outside the restored storage or message-source authentication.

## Options considered

| Option | Complexity and cost | Benefits | Risks and limits |
|---|---|---|---|
| SQLite WAL/FULL, selected for development | Standard-library interface; one transaction protocol; local disk synchronization cost | Atomic sequence/operation/result persistence, locking and explicit stale-writer checks | Filesystem assumptions; synchronous I/O consumes deadline; malicious rollback needs an independent witness |
| Custom append-only fsync log | Small initial format, substantial recovery/locking design work | Transparent raw history and interruption evidence | Torn writes, lock ordering, uncertain commits and rollback still need explicit design; an unkeyed chain is not authentication |
| Hardware monotonic counter or independent witness service | Hardware/service deployment and custody required; currently unavailable | Can anchor freshness outside a restored database | Integration, availability and recovery policy must be reviewed; no such trust anchor is invented here |

## Trade-offs and assurance boundaries

The software store protects committed history across tested ordinary restarts under the declared local-storage model. A newer independently retained checkpoint detects restoration of an older database. Restoring both database and witness defeats local-only detection; this negative control is retained. Caller-provided labels/pins are not authenticated device identities, secure boot or remote attestation.

Independent clock mapping uses `local = rate * remote + offset`, a declared positive rate interval and causal timestamp inequalities. Exact rational polygon clipping preserves asymmetric transport uncertainty. Mapping is conditional on correct timestamp provenance and the fixed-affine model. Uncertain event times are not rounded into the old exact-tick API; those observations are withheld from that path.

Restart checks require configuration/source/runtime agreement, a matching checkpoint and asserted fresh state, actuator, power and clock-map observations for the current boot. The checks are software contracts; freshness labels are not independent proof of physical state. Previously queued commands, spent power and old monotonic deadlines are never assumed reset by restarting software.

Deadline checks prevent starting an already expired computation and withhold results completed at or after the declared deadline. They do not preempt blocking Python code or enforce physical actuator timing. Calibration checks establish only compatibility of paired intervals with caller-declared error bounds. Hardware validation remains false. Response selection returns only a simulation candidate, and selects no action when prerequisites fail.

## Consequences

- Persistent ingress reconstruction and restart evidence become reviewable, but bounded storage and replay costs need real-platform measurement before long-running use.
- Clock uncertainty is visible instead of becoming an exact timestamp; interval-time transport for ambiguous actuator history remains future work.
- A late result cannot become a development candidate, but a physical executor, hard timing argument and sustainable fallback remain absent.
- No physical calibration, independent reference authenticity or real-robot claim follows from synthetic paired samples.
- SQLite/configuration/source changes require explicit compatibility/reconciliation; there is no silent migration or history rewrite.

## Action items

- [x] Implement and test bounded persistent temporal operations, checkpoint mismatch and uncertain-commit handling.
- [x] Implement and test affine clock intervals, epoch rejection and asymmetric-delay counterexamples.
- [x] Add restart freshness, one-shot deadline checks, calibration-evidence checks and a simulation-only selector.
- [x] Run and preserve the fixed integration study and source-bound database-copy audit.
- [ ] Choose and independently review message identity, checkpoint custody, anti-rollback, secure boot and key-custody mechanisms.
- [ ] Establish clock-rate/skew validity and interval-time integration on the actual platform.
- [ ] Measure worst-case scheduling/storage/actuation timing and establish feasible response/fallback behavior.
- [ ] Execute the hardware-validation plan (workspace record `V9_M5_HARDWARE_VALIDATION_READINESS_2026-11-17.md`; not included in this lightweight upload) after hardware and independent measurement facilities exist.

Gate B remains `GATE_B_NOT_AUTHORIZED`. This ADR does not amend registered H1–H5 criteria or approve a release.

## Publication scope note

Historical results and full evidence remain unchanged in the original workspace. This publication copy preserves the development criteria and identifies unavailable workspace records explicitly. The [current NEXVIA team handoff](NEXVIA_AEGIS_RECOVERY_HANDOFF_2026-11-17.md) provides source entry points, review summaries and remaining blockers. Publication does not approve a criterion or authorize Gate B.
