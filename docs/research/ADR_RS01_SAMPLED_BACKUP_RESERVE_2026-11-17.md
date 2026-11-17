# RS01 — Sampled backup reserve for a supported 1D development plant

Prepared 2026-11-17, Asia/Bangkok. **Implemented as an exploratory prototype; proposed for architecture review. No operational approval. Gate B remains `GATE_B_NOT_AUTHORIZED`. Release remains BLOCKED.**

## Problem and connection to existing research

The temporal/replay/restart/deadline work determines when evidence supports a bounded recovery calculation. It cannot create a physical response when the primary evidence or active power fails. A finite braking calculation and a small endpoint velocity also do not establish future containment under persistent disturbance.

This increment addresses that gap without changing previous models or scientific rules. It combines the existing temporal/feedback/readiness prototype with a separately specified, hypothetical backup mechanism. See the implementation and results report (workspace record `V9_M5_BACKUP_RESERVE_SUPERVISOR_RESULTS_2026-11-17.md`; not included in this lightweight upload) and prior runtime foundations (workspace record `V9_M5_RUNTIME_CORE_FOUNDATIONS_RESULTS_2026-11-17.md`; not included in this lightweight upload).

## Scope and operating envelope

The development plant is a supported translational stage with one controlled axis. A proposed independent mechanism applies a sampled, capped spring/damper force about an anchor. Its force supply is assumed available despite loss of the primary brake's electrical power. This is an architecture hypothesis implemented through simulated external body force, not a claim that NEXVIA already contains such hardware.

Only a static point mass, fixed step, fixed stiffness/damping, bounded additive force, position/velocity bounds, no-contact motion and no-impulse handoff are covered. The backup invariant result is at sampled instants. Inter-sample motion, continuous physical springs, contact/impacts, full 3D dynamics, payload uncertainty, wear, temperature, binding, finite energy, actuator failure and indefinite mechanical lifetime are not established. Gravity compensation stays powered in the native fixture; no aircraft or complete power-blackout claim follows.

## Options considered

| Option | Consequence | Disposition |
|---|---|---|
| Send zero when primary evidence is UNKNOWN | Old force/FIFO, momentum and disturbance can continue motion; zero is not a safety argument. | Reject as a universal fallback. Retain as an explicit negative-control request. |
| Continue using only a finite active-brake calculation | Does not cover unavailable active power, lost evidence or post-horizon disturbance. | Retain previous finite scope; do not extend its claim. |
| Add a proposed independent backup and require reserve before continuing | Provides an explicit physical premise and a conditional sampled invariant argument; exposes handoff and availability failures. | Selected for this development prototype only. |
| Assert a universal stop or stationary park | No justified mechanism or invariant argument for all platforms/faults. | Unsupported. |

The selected option changes the physical architecture between experimental arms. It therefore cannot support an algorithm-only superiority claim under identical hardware. There is no assertion of novelty relative to all published control methods.

## Architecture decision and interfaces

The new offline supervisor has two distinct inputs: a primary temporal/readiness result and a bounded backup-state packet with its own explicit physical premises. A missing primary result may request backup only if the backup state, invariant model and bounded independent handoff are supported. Missing or contradictory backup evidence yields an unresolved response, not a safe default.

The supervisor propagates state age and bridges the monitoring-plus-handoff interval using any active force within the declared cap. It does not assume an empty queue, zero previous force or healthy primary controller. A primary candidate must share the assessment epoch and compatible physical bounds. Continued operation is allowed as a development plan only while reserve for the next monitoring opportunity plus all admitted handoff delays remains inside the backup set and safe region. Otherwise a currently supported handoff is proposed.

An independent watchdog is an asserted mechanism, not this Python process. The bound must include missed-heartbeat detection, scheduling, assessment, transport, handoff and any physical engagement delay. Calling the supervisor late cannot restore consumed reserve. The implementation is stateless/offline, does not preempt computations and does not dispatch hardware. It is not yet a durable supervisor/executor integrated with the persistent temporal session.

After expected engagement, a bounded one-step observation check can identify disagreement with the backup model. It latches disagreement in the study record, without pretending software can repair a missing mechanical mechanism. Agreement is necessary consistency only; it does not authenticate sensors, eliminate common-mode error or prove future availability.

## Evidence and acceptance for this development increment

The increment requires exact rational model checks, negative boundary fixtures, source-bound native reconstruction without physics advancement, explicit failed-run retention, and a report that separates conditional plans from actual sampled violations. The selected regression and scripted simulation are engineering evidence, not independent safety trials or registered confirmatory acceptance criteria.

Every output denies physical dispatch and operational authorization. No V9-M4 frozen criterion, evaluator, ticket, seed, outcome, release manifesto or historical artifact is changed. All production trust, hardware and independent-review decisions remain open.

## Review gates before extending the claim

1. Owner selects a concrete supported platform and decides whether an independent backup mechanism is feasible. A different architecture requires its own model and new evidence.
2. A control/verification reviewer checks the discrete invariant and bridge arguments, conservatism, parameter uncertainty and any proposed inter-sample extension.
3. A security/runtime reviewer checks evidence authentication, isolated trigger authority, restart/checkpoint custody and deadline coverage across process failure.
4. Hardware and an independent calibrated reference must measure actual delay, force, power-loss behavior, clock error and payload-dependent dynamics. Current evidence is simulation only.
5. Future confirmatory endpoints, independent units, missingness, baselines and multiplicity need separate protocol preparation and qualified statistical review. This architecture study cannot supply that approval.

**Owner operational decision: UNAPPROVED. Independent control/security/statistical approvals: NOT PROVIDED. Gate B: `GATE_B_NOT_AUTHORIZED`.**

## Publication scope note

Historical results and full evidence remain unchanged in the original workspace. This publication copy preserves the development criteria and identifies unavailable workspace records explicitly. The [current NEXVIA team handoff](NEXVIA_AEGIS_RECOVERY_HANDOFF_2026-11-17.md) provides source entry points, review summaries and remaining blockers. Publication does not approve a criterion or authorize Gate B.
