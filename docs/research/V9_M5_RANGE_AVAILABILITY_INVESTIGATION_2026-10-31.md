# Post-proposal range availability investigation

**Development evidence only. Gate B remains `GATE_B_NOT_AUTHORIZED`.** No Holdout outcomes, reserved seeds, frozen artifacts or scientific decision rules were accessed or modified. This investigation creates only this document.

## Finding

All three `POSTPROPOSAL_RANGE_UNAVAILABLE` episodes in the two team nominal-force smoke ledgers were triggered by a **negative range value with transport-valid and fresh flags both true**. They were not caused by configured dropout, range latency, or an anchor request scheduling failure. The observed validation failure is consistent with the benchmark's additive Gaussian range model near zero distance. The generic terminal reason conflates semantic invalidity with missing/unavailable transport data.

The fail-closed behavior is not demonstrated to be a code defect: the validator deliberately requires nonnegative physical distance. What is demonstrated is a diagnostic ambiguity in the reason/trace field names. Clamping the negative value to zero, resampling until positive, ignoring this observation, or relaxing the validator would change the sensor distribution or controller policy and is not justified as a mere engineering fix.

## Evidence identity and counts

Both inputs were inspected using the development ledger integrity reader; each was FINALIZED with8 completed assignments, no execution errors or incomplete assignments. They share the declared nominal range case, zero range bias/dropout, default latency0, seeds2252000/2254000, two vector biases and two recovery controllers. This is a correlated development grid, not16 independent worlds.

| Input | SHA-256 | Decision events | Negative range events | Transport-invalid/fresh-false events | Range-unavailable terminal episodes |
|---|---|---:|---:|---:|---:|
| `results/research_development/dev/team_force_axis_smoke_v1.jsonl` | `a8a96233912157c48d4cf35f54d1fb0dcaa94f025867f53239fae4121aa51ad6` |3402|3|0|1/8 assignments,1/4 monitor assignments|
| `results/research_development/dev/team_force_direction_smoke_v1.jsonl` | `34cf9601f56d7be643f6960f4016acdf6e01243f27dc04c40f15f490999afe2e` |2343|5|0|2/8 assignments,2/4 monitor assignments|

Every negative event in these ledgers occurred with phase_before BRAKING, ANCHOR or RECOVERY. Counts include baseline-controller observations that did not immediately terminate. Raw traces record `range_valid` and `range_fresh`; these fields represented transport/dropout/freshness, not the full `valid_range` semantic predicate.

Exact terminal cases (zero-based step; observed pre-physics decision state):

| Force method | Seed | Vector bias | Controller | Step | Recorded range m | True diagnostic distance m | Transition |
|---|---:|---|---|---:|---:|---:|---|
| AXIS_CLIP |2254000|[0.8,0.8,-0.3]|AEGIS_3D_RECOVERY_MONITOR|110|-0.006723520402780472|0.06952878150486434|BRAKING → TERMINAL / ABSTAIN|
| DIRECTION_PRESERVING_PEAK |2254000|[0,0,0]|AEGIS_3D_RECOVERY_MONITOR|110|-0.044279249913393326|0.03197305199425149|BRAKING → TERMINAL / ABSTAIN|
| DIRECTION_PRESERVING_PEAK |2254000|[0.8,0.8,-0.3]|AEGIS_3D_RECOVERY_MONITOR|113|-0.08485794085698328|0.04401567506653146|BRAKING → TERMINAL / ABSTAIN|

In all three, `range_valid=True`, `range_fresh=True`, `anchor_requested=False`, `anchor_valid=None`; the preceding event had monitor reason OBSERVED and BRAKING → BRAKING / VERIFY. No anchor observation was expected yet: stabilized confirmation requests it only after low measured speed. Monitor checks range before the stabilized wrapper advances. The monitor abort is therefore earlier than any anchor scheduling requirement.

The generic terminal-reason totals are: axis ACTIVE4 (all timeouts), RECOVERY_TIMEOUT3, POSTPROPOSAL_RANGE_UNAVAILABLE1; direction RECOVERY_TIMEOUT5, POSTPROPOSAL_RANGE_UNAVAILABLE2, POSTPROPOSAL_MONITOR_ALARM1. ACTIVE is the retained controller reason on a timeout, not completed navigation. All range-unavailable cases are abstentions, not passes.

Negative observations by controller: axis seed2254000/heavy bias anchor recovery2 and monitor1; direction seed2254000/nominal bias anchor recovery2 and monitor1, heavy bias anchor recovery1 and monitor1. Every other assignment had0. The original anchor-recovery wrapper does not validate range while BRAKING solely for a high-speed VERIFY step, whereas the monitor checks every monitored phase; this explains why baseline negative events can be retained without the same immediate terminal reason. It does not establish that either behavior is preferable scientifically.

## Source path and interpretation

References are to working files inspected in this investigation. Source hashes embedded in the historical smoke ledgers control their actual executed versions; current diagnostic additions must not be retroactively attributed to those runs.

1. `experiments/benchmark_physical_3d_cbf.py:220`–224 generates vector noise and scalar `raw_range = true_dist + range_bias_m + Normal(0,0.05)`. The additive scalar distribution is unbounded below; no clamp is present.
2. At lines225–234, `raw_valid` is determined by configured dropout only, delayed history is selected, and freshness is `range_valid and range_latency_steps == 0`. A negative numerical range alone does not clear these flags.
3. At lines406–413, the delivered `RangeReading` uses the current range if fresh, sigma0.05, valid=fresh, dropped=not fresh. `RangeReading` itself is a dataclass with no distance validation (`src/aegis/v3/sensors/cross_modal.py:8`).
4. `src/aegis/v9/exploratory_sensor_validation.py:10`–13 rejects nonfinite/negative physical real values. Its `valid_range` predicate at lines20–25 additionally requires correct flags, nonnegative distance and positive sigma.
5. `src/aegis/v9/recovery_monitor_candidate.py:56`–61 checks vectors first, then `valid_range`, mapping any failed range predicate to `POSTPROPOSAL_RANGE_UNAVAILABLE`. At lines93–103 it applies this before delegating whenever phase is BRAKING/ANCHOR/RECOVERY; failure invokes `_abstain`.
6. `src/aegis/v9/stabilized_arrival_candidate.py:81`–88 keeps BRAKING for high velocity, requests an anchor only after low velocity, and validates range with the anchor at lines90–94. Thus `anchor_requested=False` in the observed failure is consistent with the phase sequence.
7. `src/aegis/v9/anchor_recovery_candidate.py:24`–29 separately requires valid range in RECOVERY. Negative BRAKING observations in the original wrapper do not necessarily traverse this guard.

## Safe engineering proposal

Add additive diagnostic fields that distinguish raw transport validity/freshness from semantic range validity, and expose a reason such as NEGATIVE_DISTANCE, NONFINITE_DISTANCE, DROPPED_OR_NOT_VALID, ANOMALY, or INVALID_SIGMA. Record the raw sample and delivered controller distance separately, including delay context. Keep existing action, monitor, phase transition, terminal reason and sensor draw schedule unchanged for backward comparability. A semantic invalidity reason may be an auxiliary report field; do not silently rewrite historical terminal reasons or evidence.

Synthetic regression should show that a negative fresh transport-valid sample retains its raw value, is semantically invalid and still abstains in the monitor; zero remains semantically valid under the existing validator; dropout and latency remain distinguishable; no extra RNG draws are made; the diagnostics do not alter traces/terminal behavior apart from added fields. Inject nonfinite/sigma/anomaly defects in fixtures only, not these historical runs.

Any change to range generation (censoring, truncated noise, hardware nonnegative output), permissive monitor handling, or retry/braking policy needs its own explicitly named development candidate and declared comparison. Sensor specifications or empirical calibration would be needed to choose a realistic near-zero model; this investigation provides neither. New diagnostic traces can explain this issue but do not resolve scientific or authorization blockers.

## Implemented telemetry follow-up and declared fault batch

During this investigation root implemented additive trace telemetry in `experiments/benchmark_physical_3d_cbf.py:493` onward: raw sample, raw transport-valid flag, delivered controller distance, semantic validity, NEGATIVE_DISTANCE versus INVALID_OR_UNAVAILABLE validation status, plus recovery/wait/missing-velocity counters. The known negative-range case is covered by `tests/test_recovery_range_telemetry.py`, preserving ABSTAIN and the original monitor reason. This records the observed distinction without clamping/resampling, relaxing validation, changing the monitor criterion, or rewriting old ledgers. Detailed invalid-sigma/anomaly/nonfinite statuses remain a possible later diagnostic extension; current telemetry intentionally uses a generic remainder status.

Before inspecting any follow-on results, the team declares the vector-loss-only batch: seeds2252000 (selected historical stall repeat) and2254000 (now a nominal-smoke development repeat), biases[0,0,0]/[0.8,0.8,-0.3], both recovery controllers, both force methods, max600/post-STOP50. Set case=`vector_loss_after_proposal` and use two new exclusive ledgers, one per method:8 assignments each,16 total. All inputs except that declared fault case and additive telemetry match the nominal smoke. Seed2254000 must no longer be described as fresh independent replication after its nominal outcome was inspected. No seed selection changes are made based on the range findings.

Retain the full assignment denominator and separately count actual injected-loss triggers. Episodes never reaching a monitored post-proposal phase do not test vector-loss resilience. The fault batch is a development stress diagnostic, not a new statistical endpoint or confirmatory evaluation. Gate B remains `GATE_B_NOT_AUTHORIZED`.
