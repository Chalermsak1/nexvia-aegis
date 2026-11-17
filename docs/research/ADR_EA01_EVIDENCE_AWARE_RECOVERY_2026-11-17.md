# ADR-EA01: Evidence-aware recovery development system

**Status:** Accepted for bounded exploratory implementation under the owner's development instruction; no production or scientific-rule approval.
**Date:** 2026-11-17, Asia/Bangkok.
**Deciders:** Research owner retains release and scientific authority. This technical record supplies no independent review.

## Context

RP01 records 29 violating trajectory segments with unavailable backup and 11 backup-model contradictions with delayed backup. Its proof wrapper supplies all premises as true. The plant's in-memory registry survives controller death only. Virtual-time pacing and finite-run reconciliation do not establish physical deadlines or permanent-partition recovery. The published RP01 artifacts and sources must remain unchanged.

## Decision

Build a new development-only assurance pipeline: explicit evidence statements, durable evidence/replay history, evidence-gated adaptation of the existing physical-time assessment, and independently derived bounded stopping-capability analysis. Preserve the mathematical proof separately from evidence sufficiency, physical containment, unknown effects, duplicates, latency and nominal availability. A proof is never an operational authorization.

Evidence is scoped to DEVELOPMENT_SIMULATION. Registered source IDs and caller-held checkpoint pins are development assumptions; they are neither authentication nor independent evidence. Generic artifact comparisons validate their declared finite predicates only. They do not prove sensor accuracy, future reliability or hardware independence. A synthetic source is never relabelled physical or independently authenticated.

## Options considered

| Option | Advantage | Risk and consequence |
| --- | --- | --- |
| Retain boolean premises only | Minimal integration cost | Assumptions and measured support remain indistinguishable |
| Replace the historical proof/experiment | Single apparent interface | Breaks historical hashes and hides before/after evidence |
| Add a separate evidence adapter and durable journal | Explicit support and provenance; preserves old sources | More state, storage and lifecycle semantics to verify; selected option |

## Evidence contract

Each of the nine existing physical premises has a registered source, predicate kind and maximum evidence age, provided explicitly by a development contract. Predicates are exact rational enclosure, exact identity and distinct declared identities. A statement binds those expected values to a specific physical-input digest. The adapter constructs the input digest itself; caller-provided support cannot substitute for another packet, clock-map identity, model or timing argument.

Artifacts identify statement, premise, source, boot, clock domain, observation time, expiration and observations. Time validity is half-open: observed <= now < expires, with age <= the contract's maximum. Replaying an identical ID cannot refresh validity. Changing an old ID poisons the ledger. Missing, assumed, expired, wrong-statement, wrong-epoch or malformed evidence cannot support a development candidate. Contradictions are sticky across restart and cannot be erased by a later favorable artifact. No automatic contradiction-clear API is provided.

A journal commits evidence and evaluation events before returning candidates. It is single-writer, bounded and exclusively created. Restart requires an externally supplied matching checkpoint; committed records are checked against hashes and deterministic semantics. Pending bytes are retained and prevent writable restart. Old boot identities cannot be revived. These guarantees cover the evidence journal only, not atomicity between a database and a physical actuator, whole-disk rollback resistance or power-loss durability on untested hardware.

## Predeclared acceptance criteria for this increment

### EA-A: evidence and claims

All nine premises must have current, correctly bound, predicate-satisfying simulation evidence before the adapter invokes the physical candidate path. Every single-premise omission, assumption, expiry, contradiction, wrong binding/source/domain/boot and ID conflict must withhold a candidate. An exact expiry-boundary case must withhold. Malformed evidence must not escape as a supported result. A new favorable observation cannot erase contradiction. The adapter must continue to deny dispatch, hardware validation, independent attestation and operational authority.

### EA-B: persistence and restart

Evidence and evaluations must reconstruct from committed records. Duplicate/conflicting IDs, faults, consumed boot identities and clock regression must remain effective across close/reopen. A stale checkpoint, concurrent writer, changed record, partial pending record or capacity exhaustion must fail closed and preserve original bytes. A restarted boot starts without reusable prior-boot support. No claim of whole-host or actuator exactly-once semantics follows.

### EA-C: stopping capability

Use exact rational, piecewise constant-force dynamics with full quadratic intersample extrema. Separate prefix delay/ramp containment, stop reachability, stopping-time upper bound and rest-maintenance capability. A zero/insufficient brake must be reported unable to stop under the declared disturbance. A finite contained prefix cannot become an infinite safety conclusion. Support for a brake must depend on explicit force, mass, adverse acceleration, delay, ramp, speed and position bounds. Boundary equality and just-outside cases must be tested. No threshold is imported into frozen V9-M4 rules.

### EA-D: iteration and preservation

Run targeted tests, a declared synthetic study, adversarial/boundary tests after the initial implementation, then the full relevant prior suite plus new tests. Preserve failed attempts and source revisions. Reconstruct the study from a detached source snapshot, check all report links and hashes, and verify prior evidence and Git index remain unchanged. Passing test counts alone do not close the stage.

## Development roadmap and stage gates

| Workstream | Current increment | Required next evidence before widening claims |
| --- | --- | --- |
| Evidence-aware claims | Implement durable evidence contract and physical-proof adapter | Live collector/source provenance, input binding at issue and consumption, independently reviewed trust policy |
| Backup capability | Implement bounded stopping envelope and fault sweeps | Joint envelope with actual backup dynamics; measured availability, delay, ramp and independent power |
| Durable recovery | Implement evidence/replay journal | Plant/actuator registry durability, crash between physical effect and record, plant/watchdog death and rollback tests |
| Clock and deadlines | Explicit boot/domain/age and proof input binding | Independently evolving plant time, variable drift mapping, CPU/IPC/storage stalls, derived deadlines |
| Permanent partition | Preserve expired/unknown outcomes | Live disconnection campaigns without final reconciliation opportunity |
| Return to nominal | Retain existing backup latch | Separately specified state machine, new epochs, reconciled effects, fresh prospective feasibility and acknowledged authority transfer |
| Comparison/review/hardware | Preserve reviewable source and raw records | Matched baselines, independent mathematical/security review, calibrated hardware and physical failure tests |

## Consequences

Unknown evidence reduces availability and may trigger only an uncertified fallback request. Evidence rejection cannot supply missing braking force. A bounded stopping envelope is a different model from the RP01 spring-damper backup, so it is an exploratory capability analysis, not a retrospective recertification or replacement controller. Future collectors must not use simulator truth as a hidden policy input in claimed fair comparisons.

Existing frozen scientific thresholds, artifacts and release manifests are unchanged. No Holdout data, production tickets or release commits are needed. **Gate B remains GATE_B_NOT_AUTHORIZED; release BLOCKED.**
