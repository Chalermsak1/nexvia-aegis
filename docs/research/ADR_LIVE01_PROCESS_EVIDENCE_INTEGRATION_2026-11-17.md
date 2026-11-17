# ADR-LIVE01: live evidence, issue/consumption checks and process failures

**Status:** Selected for exploratory implementation under the owner's instruction; no production or scientific-rule approval.
**Date:** 2026-11-17, Asia/Bangkok.
**Authority:** Owner restrictions remain controlling. This record is not an independent review.

## Context and decision

EA01 is an offline evidence adapter. RP01 has autonomous plant/controller/watchdog processes but boolean proof premises and no complete issue-to-consumption evidence binding. Preserve both versions and add a separate LIVE01 arm implementing all four requested parts: live collection; issue/consumption guards; integrated failure experiments; and reproducible evidence.

Reuse the EA01 adapter and journals unchanged. Each live assessment gets an exclusive frame journal and a source-bound result. A durable outer actor journal retains replay watermarks, observations, revocations and recovery latch across frames and process restart. Per-frame creation cannot clear a fault: a rejected/contradictory live frame triggers a persistent recovery latch, never automatic return to nominal.

## Alternatives and trade-offs

| Option | Advantage | Risk/consequence |
| --- | --- | --- |
| Freeze time while computing | Easy reuse of the offline adapter | Hides plant progress; rejected |
| Modify historical adapter or relax clock checks | Smaller live patch | Changes pinned evidence semantics; rejected |
| Read advancing process clock, retain conservative quantized checks and native budgets | Preserves old source; detects stale computations and validates both lifecycle points | Conservative availability loss; shared-clock and simulation assumptions remain; selected |

## Timing and evidence semantics

Plant/controller/watchdog are distinct OS processes. The plant owns a no-catch-up wall-paced loop, exact ideal 0.02-second ZOH dynamics, FIFO, force and simulated actuator registry. Neither controller nor orchestrator grants ticks. A new-run mutable clock beacon exposes only tick, sensor epoch, host timestamp and identity, never position, velocity or actuator truth. It is a declared common-host simulation clock channel, not an independently calibrated oscillator. Operational communication partitions do not remove this clock channel; separate clock-read failures are tested as guard failures.

The watchdog reads the beacon before and after EA01 evaluation; an advancing cursor withholds. Its own monotonic host clock measures communication silence and computation budget. Source intervals are conservatively enlarged over one ideal sample to include within-sample motion under the declared primary-force bound. State age, proof horizon, virtual lease expiry and native host expiry remain distinct. The plant checks the lease against its own advancing cursor and monotonic time at issue/acceptance and actual consumption. This supplies simulation software checks, not physical hard-real-time guarantees.

New-run scratch beacon updates are explicitly mutable; all experimental journals and result artifacts are exclusively committed and immutable. Scratch does not overwrite any preexisting project file.

Two arms expose the evidence limitation. STRICT_OBSERVATIONS retains unmeasured future timing/independence/no-impulse properties as ASSERTED and must withhold nominal control. SIMULATION_CONTRACT_CHECKS checks supplied synthetic observations and declared manifest conformance using EA01 finite predicates. Its permissions are explicitly CONDITIONAL_SIMULATION_CONTRACT_ONLY; model calibration, future backup reliability and physical independence remain assumptions. Source IDs/hashes and different process/power names do not authenticate physical evidence. Neither arm has operational authority or hardware validation.

Raw sensor centers come from the same synthetic measurement channel as intervals, not a ground-truth policy input. Clock consistency is derived from the declared virtual mapping, not independently measured synchronization. Physical truth and hidden fault schedules are available to post-run auditing only. Controller/watchdog receive a public model contract without future fault schedules; plant/orchestrator inject faults separately.

## Command and recovery contract

Commands reference the exact committed lease/result, current controller/watchdog generations and sensor epoch. Older leases cannot be extended by later favorable assessments. Revocation sequence, local evidence/power changes, boot changes, virtual/native expiry and the recovery latch are checked again at consumption. New commands use a fresh ID; replay/conflict cannot cause another consumption. Queueing is not effect confirmation. Read-only queries reconcile unknown effects; delayed QUEUED acknowledgements cannot downgrade terminal beliefs. Contradictory terminal reports remain uncertain.

The plant's modeled local lease-expiry guard requests backup when the watchdog is unavailable. Requested, accepted and actually engaged backup states are separate records. Backup is one-way latched; no nominal return is implemented. A missing brake cannot be replaced by withdrawing permission. Actuator queue flushing/removal of force on primary power loss remains an explicit uncalibrated simulation behavior. Plant/host death and durable physical exactly-once execution are outside LIVE01.

## Predeclared acceptance criteria

### L1: live collection

Every used observation, heartbeat, epoch, model declaration and assessment must be identified in committed source/config-bound records. Replay/staleness, malformed/mismatched sources, old generations and asserted future properties cannot silently become fresh observed support. Strict arm nominal candidates must remain withheld. All simulation-contract candidates must retain their assumption/scope labels.

### L2: lifecycle enforcement

Recompute guards at controller issue, plant acceptance and plant consumption. Expired, revoked, wrong-generation, wrong-epoch or unsupported leases cannot produce new nominal effects. No repeated command consumption or backup engagement; carried force is separately measured. Actual queued negative braking targets must be exposed for queued-power/delay/revocation cases, otherwise classify injection as unqualified. Evidence rejection cannot reset plant state/force or improve containment by definition.

### L3: integrated process campaign

Inject before/after-consumption controller death, watchdog death/restart, lost acknowledgements, duplicate/conflicting requests, replay/staleness, clock/session resets, malformed/source faults, permanent operational partition, queue delay/revocation, compute delay, queued primary power loss and delayed/unavailable backup. Qualifying restart contains at least eight uninterrupted plant updates between termination and restarted readiness. Preserve unqualified, failed and incomplete cases. Record the six outcomes separately, including phase-specific virtual and host latency, unknown effects and availability. No aggregate PASS/FAIL.

### L4: iteration and reproducibility

Run targeted unit/process tests after changes, retain source revisions and failures, perform an additional boundary/falsification campaign, and run the full relevant prior selection plus new tests after implementation stabilizes. Read-only replay must verify role/assignment/source identity, guards, EA01 evaluation, model dynamics, full intersample extrema, effect causality, claims and separate metrics. Save raw outputs, errors/pending bytes and manifest hashes at exclusive paths; reproduce from detached source and evidence. Prior pinned artifacts, Git index, branch and HEAD must remain unchanged.

## Advancement and limitations

These are engineering development criteria, not a scientific preregistration or V9-M4 change. General independent clock mapping, true physical timing, plant/watchdog actuator durability, permanent loss of all time sources, source authentication, recovery-to-nominal authority transfer, matched external baselines, actual expert review and hardware tests remain separate workstreams. Do not mark them complete from LIVE01 tests. **Release BLOCKED; GATE_B_NOT_AUTHORIZED.**
