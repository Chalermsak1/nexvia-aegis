# RP01 — Predeclared development-stage criteria for restart experiments

Prepared before the first process experiment on 2026-11-17 (Asia/Bangkok). **Exploratory simulation criteria, not a scientific preregistration, production approval or V9-M4 rule. Gate B remains GATE_B_NOT_AUTHORIZED.**

## Stage A — process and plant continuity

Plant, controller and watchdog must have distinct actual OS process IDs. The plant owns its state, actuator history, command registry and simulation clock. It advances from its own wall-paced loop without waiting for controller responses or parent tick permits. Startup readiness may precede the experiment; there is no per-step barrier afterward. Controller termination/restart must not replace the plant PID, rewind tick/time, reset position/velocity, empty queues or reset force merely because a controller process changed. Power-outage flushing is a separately declared actuator behavior.

A qualifying controller outage must contain at least eight consecutive recorded plant updates before restart readiness. Record host monotonic times and virtual physical time separately; the pacing ratio is synthetic and supplies no hard real-time guarantee. If the intended before/after-consumption ordering does not occur, classify that scenario's injection as unqualified/incomplete, not a successful test.

## Stage B — command, replay and uncertain effects

A consumed command must have a committed controller intent and an accepted plant record. A command ID can cause at most one consumption. Duplicates and changed bodies under an old ID must not cause repeated effects. Previously accepted feedback cannot produce a new claim by being replayed. New boot/sensor epochs cannot silently revive retired identities.

Missing acknowledgements and controller death leave effects uncertain until a read-only query of the still-running simulated plant's registry supplies disposition. Never resend an unresolved old command as if it had not executed. Query/reconstruction records must preserve QUEUED, CONSUMED, REJECTED and UNKNOWN distinctly. Late evidence cannot establish timely actuation retrospectively.

## Stage C — six independent outcomes

Record separately: full continuous trajectory containment; unsupported claims at issue and subsequently contradicted premises; uncertain command/effect counts and reconciliation; repeated effects; detection/reconstruction/assessment/handoff latencies; and nominal-control availability including new commands without a valid simulation permission.

No aggregate PASS/FAIL outcome is allowed. A mathematical conditional claim must recompute from its actual evidence; stale/replayed/wrong-epoch/unsupported evidence must not produce supported claims. Count actual timing/power/backup premise violations separately from a mathematical counterexample inside the declared assumptions. Carried force during handoff is not a newly authorized nominal command.

For admitted initial states with intact declared backup/timing premises, any trajectory violation is a blocking counterexample requiring investigation. Intentionally unavailable or out-of-bound delayed backup cases must preserve their trajectories, premise violations and UNKNOWN/unresolved classifications even if a finite trace happens to remain contained. Unsupported-start cases cannot be labelled certified by a best-effort request.

## Stage D — evidence, falsification and iteration

Every role has an exclusive immutable record sequence with chain and source/configuration identities. A killed process may leave uncommitted pending bytes; retain those bytes and never promote them into committed evidence. Physical/simulated commands are sent only after their intents commit. A failed/incomplete case is preserved under its original path; use a new path for a corrected run.

Read-only reconstruction must verify committed record order, exact plant equations and between-sample extrema, command causality/deduplication, claim recomputation and independent metrics. It must not spawn fresh workers or integrate new native episodes. Targeted tests and the complete relevant prior selection run after implementation stabilizes; later modifications require affected tests and the relevant regression again.

At least one further falsification/boundary campaign and evidence review must follow the initial implementation. Do not conclude on the first successful run or test count. Each stage's criterion evidence and remaining exceptions are documented independently. External physical validation, authenticated hardware independence and actual expert review remain unavailable prerequisites, not synthetic successes.
