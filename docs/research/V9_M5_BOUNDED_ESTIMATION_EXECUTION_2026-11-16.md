# V9-M5 bounded-estimation development execution — 2026-11-16

**Scope:** exploratory simulation/control engineering. **Governance: `GATE_B_NOT_AUTHORIZED`.** This work does not close V9-M4 release blockers, certify a robot, approve statistical rules or create a Final Release Commit. Branch: `codex/research-hardening`; parent: `74b0bfab8e57cd450293e49de881207074df3141`. Source hashes identify the actual uncommitted files, rather than implying that the parent commit contains these additions.

## Outcome and appropriate claim

Implemented and executed a separately identified estimate-only braking diagnostic with explicit measurement error balls, acquisition times, frame/source labels, monotone delivery sequence, age propagation and finite-duration command checks. Completed **54 trajectories × 80 physics steps = 4,320 physics steps**, with all 54 assignments retained and completed. The 27 point/bounded comparisons have matching initial states, runtime records and synthetic noise innovations. The selected regression suite passed **102 tests in 23.05 s**.

The implemented component checks a **conditional command property**: under the asserted velocity error ball and ideal constant-force model, the chosen force must oppose every admissible velocity and must not increase kinetic energy during the supplied command interval. It is **not a stopping, arrival, obstacle-avoidance, recoverability, calibrated uncertainty or self-authenticating safety result**. Command refusal can leave substantial residual motion. Undeclared faults can defeat the check.

This is an extension of existing work, not the first estimate-only implementation: `scripts/research/no_oracle_control.py` already supplied an estimate-only command generator, and `scripts/research/study_estimated_braking_v3.py` already applied its force directly. Those files remain unchanged. The previous integrated execution register's “not yet implemented” status referred to the planned uncertainty-aware interface, and should not be read as denying those earlier micro-studies.

## Changes and source boundaries

| New component | Implementation and evidence |
|---|---|
| Bounded state interface | `src/aegis/development/bounded_braking.py:42` packet and `:69` gate. Position/velocity share an asserted frame, source and acquisition time. Bounds are Euclidean absolute errors, not covariance or confidence intervals. Accepted mutable lists are copied to immutable tuples. |
| Input/age contract | Same module `:87`. Rejects malformed/nonfinite values, bool/nonnumeric scalars, absent bounds/basis, unexpected frame/source, future/stale packets, nonincreasing sequence and clock regression. A rejection latches the session; no automatic reset/retry. Source/basis strings are labels, not authentication. |
| Braking proposal | Same module `:129`. Uses the accepted velocity and its radius only. No environment, simulator, CBF, true velocity, true position or true range parameter enters the command function. |
| Fixed development study | `scripts/research/bounded_estimation_study.py:43` declares the 54 assignments; `:53` selects a command; `:63` scores it using simulator truth afterward; `:93` executes physics. |
| Evidence writer and reader | Same runner `:171` uses the existing exclusive, fsynced development ledger. `:195` reconstructs command/scoring/geometry/impulse/phase; `:259` checks paired reset/runtime/noise. `ERROR`, unstarted and interrupted work remain unevaluable. |
| Regression tests | `tests/test_bounded_braking.py` and `tests/test_bounded_estimation_study.py`. Adjacent older estimate-control, freshness, ledger and reader tests are included in the selected suite. |

No old benchmark, controller, evaluator, preregistration, frozen artifact or existing report was edited. The pre-existing tracked benchmark's SHA-256 still matches the earlier integrated-execution receipt (`04bc31bf74423806200e39a44334e1dd0cf4063dde08797ef79dacb491b4323f`). The historical tracked diff remains 46 insertions and 2 deletions in that file. No commit, push, merge or publication occurred.

## Mathematical contract and limits

Let acquisition error bounds be `||p_true-p_m|| <= e_p`, `||v_true-v_m|| <= e_v`, age `t >= 0`, and a caller-asserted acceleration norm bound `A` over that age. The propagated center and radii are:

```
p_center = p_m + v_m*t
position_radius = e_p + e_v*t + A*t*t/2
v_center = v_m
velocity_radius = e_v + A*t
```

These follow by integrating bounded initial velocity error and acceleration. The implementation does not estimate or validate `A`, `e_p` or `e_v` against an independent physical sensor. Ordinary floating-point arithmetic has explicit numeric-range refusals and analytical tests; it is not outward-rounded interval arithmetic or a formal machine proof.

For a proposed force `f` and velocity ball `B(v_center,r_v)`, the support function gives:

```
max f·v = f·v_center + ||f||*r_v = P_upper
```

The bounded arm requires `P_upper < 0`. If the ball includes zero or an opposing direction, it returns `NO_COMMAND` rather than choosing a direction and calling it safe. The point baseline deliberately ignores the radius but uses the same input/freshness contract, so this experiment isolates the command checks; it is not a comparison with every existing NEXVIA controller.

Initial dissipation alone is insufficient over a sampled control interval. For known mass `m`, constant force held for `h`, and **no unmodeled force or contact during that interval**:

```
max ΔK = h*P_upper + h*h*||f||²/(2*m)
```

The bounded arm also requires this value to be strictly negative when `h>0`. An analytic counterexample is `v=.01 m/s`, `f=-2 N`, `m=1 kg`, `h=.02 s`: initial power is negative, but final velocity is `-.03 m/s`, so kinetic energy increases. Tests explicitly preserve this distinction. Zero hold time requests only the instantaneous check; the study explicitly supplies `.02 s`.

This force rule neither certifies the maximum travel before rest nor maintains obstacle constraints. Position bounds are transported and scored, but **are not used for collision avoidance in this diagnostic**. The separate 1D braking-envelope reference remains unintegrated; inserting it without a feasible, persistent fallback would overstate recoverability. Platform mass, friction, disturbance, actuation delay, contact, gravity compensation and force availability require independent justification before transferring any result.

## Experiment design and exclusions

- Three explicitly designated development RNG roots `[20261116, world]`, `world=0,1,2`; append `0` for the initial-world stream and `1` for noise. No reserved seed file is read. Initial position `[-2,-2,1.3] m`; initial velocity `[.4+.2*U,0,0] m/s`.
- Nine cases, each in point and bounded arms: nominal; reversed velocity with an error radius expanded to cover reversal; reversed velocity without declaring that error; undeclared velocity scaling to `.25`; delayed packets; stale packets; exact replay; missing packet; missing velocity bound.
- Position noise components are independent uniform draws in `[-.01/√3,.01/√3] m`; velocity components use `[-.02/√3,.02/√3] m/s`. Thus the specified synthetic Euclidean noise balls are bounded by `.01 m` and `.02 m/s`. This bounded-noise construction is not a calibration result for real sensors.
- Faults begin at decision 6. Latency increases by one physics tick per decision to three ticks (delayed) or six ticks (stale); the maximum accepted age is `.08 s`. Acquisition time can stay equal while latency ramps, with a new delivery sequence and newly drawn synthetic measurement noise at the recorded older state. This is an artificial delayed-measurement fixture, not a realistic transport/queue implementation. The replay case instead repeats the exact previous packet/sequence.
- Maximum 80 decisions per trajectory, actual timestep `.02 s`, mass `1 kg`, ideal gravity compensation, force norm limit `2 N`, asserted age-transport acceleration bound `2 m/s²`.
- Physics directly receives the proposed force. `env.step()` is not called: no truth-state CBF, true-velocity damping or hidden safety projection is used. The constructed environment still provides known geometry and truth for sensor generation and scoring. Sensors are not hardware or an implemented estimator.
- On `NO_COMMAND`, physics continues for every remaining step with **zero incremental force plus ideal gravity compensation**. This diagnostic choice exposes coasting; it is not an independently available fallback, safe hover or a real-robot shutdown procedure.
- Ground-truth errors, membership in the declared balls, contact/geometry, true power and speed are evaluated after command selection and never returned to it. Full-horizon sampled states are retained. No V9-M4 evaluator or confirmatory test is invoked.

The 54 trajectories share three worlds and paired innovations. Counts of steps, test repetitions and trajectory arms are dependent. No population reliability estimate, p-value, confidence interval, TRL upgrade or confirmatory claim is derived.

## Actual observations

Each row aggregates **three development trajectories per arm**, 240 sampled control intervals. “Positive power” means `f·v_true > 1e-10`; “energy increases” means `||v_after||²-||v_before||² > 1e-10`. These are numerical diagnostic tolerances, not approved scientific acceptance thresholds. Final speeds are the range across the three worlds, not confidence intervals.

| Case | Positive power, point / bounded | Energy increases, point / bounded | NO_COMMAND, point / bounded | Final speed range point (m/s) | Final speed range bounded (m/s) |
|---|---:|---:|---:|---:|---:|
| Nominal | 0 / 0 | 101 / 0 | 0 / 205 | .01828–.03597 | .00698–.02298 |
| Reversal, declared radius | 222 / 0 | 222 / 0 | 0 / 222 | 3.14032–3.23571 | .18061–.27589 |
| Reversal, undeclared | 222 / 222 | 222 / 222 | 0 / 0 | 3.14032–3.23571 | 3.14032–3.23571 |
| Underreported velocity, undeclared | 27 / 0 | 104 / 0 | 0 / 211 | .01309–.03504 | .08136–.10486 |
| Delayed | 22 / 0 | 108 / 0 | 0 / 206 | .08760–.09481 | .00613–.03625 |
| Stale | 0 / 0 | 0 / 0 | 210 / 210 | .02170–.11600 | .02170–.11600 |
| Replay | 0 / 0 | 0 / 0 | 222 / 222 | .18061–.27589 | .18061–.27589 |
| Missing packet | 0 / 0 | 0 / 0 | 222 / 222 | .18061–.27589 | .18061–.27589 |
| Missing velocity bound | 0 / 0 | 0 / 0 | 222 / 222 | .18061–.27589 | .18061–.27589 |

No collision flag appears in the recorded samples of this deliberately open braking setup. That does not test general navigation or imply collision-free operation. The bounded arm trades command availability for avoiding unsupported directional actions. Its higher residual speed in the underreported case illustrates why fewer adverse power samples cannot be equated with successful stopping or task utility.

The hidden reversal is a direct limitation of self-verification: both arms reach approximately `3.1–3.2 m/s`. The bounded arm reports a negative conditional power bound while true power is positive because the true velocity is outside its asserted ball. All 222 post-fault intervals per arm violate the declared ball in that case. Those contradictory observations remain in the raw ledger and are not reclassified as a pass. A realistic next method needs independent evidence for error bounds and executable fallback dynamics, including shared failures of any secondary source.

## Tests, failed attempts and retention

Final selected command (run with bytecode/cache disabled and a unique temporary directory):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q -x -p no:cacheprovider \
  tests/test_bounded_braking.py tests/test_bounded_estimation_study.py \
  tests/test_no_oracle_control.py tests/test_velocity_freshness_candidate.py \
  tests/test_development_ledger.py tests/test_study_estimated_braking.py \
  tests/test_analyze_estimated_braking_ledger_v3.py \
  --basetemp=/private/tmp/nexvia-bounded-release-tests-20261116 \
  --junitxml=/private/tmp/nexvia-bounded-release-tests-20261116.xml
```

**102 passed in 23.05 s**, including 46 bounded-contract tests and 13 new study/integrity tests, plus 43 adjacent tests. This is a selected suite, not the entire repository. Earlier successful suites overlap and must not be added as independent test counts.

Coverage includes stale-age boundaries, malformed input/bounds, replay/clock/source/frame issues, rejection latching, immutable snapshots, numerical range, exact extremal transport/dissipation/finite-hold examples, full-horizon simulation, declared versus undeclared faults, exclusive outputs, reconstructed decisions, paired noise/runtime, rehashed force/scoring/geometry/summary/source/impulse contradictions, missing physics, sink failure and simulator failure. A failed sink stops execution without claiming an unrecorded command; a simulator failure preserves one ERROR and 53 unstarted assignments. These are deliberate synthetic failures.

The initial integration attempt had **1 passed, 9 setup errors** because dataclass tuple vectors were rejected by the strict JSON ledger. That failure occurred before any physics step. The partial ledger and original five-file source snapshot are retained. After normalizing vectors to JSON lists, 10 integration tests passed. Subsequent improvements added finite-hold checks, impulse/pair checks, numeric handling and runtime-failure coverage; overlapping selected suites of 96 and 101 tests passed before the final 102-test suite. Original unit tests also passed 41 cases. Failed/partial evidence is preserved separately from the completed actual study; there is no invisible replacement or retry of an existing output file.

Actual execution and read-only audit:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python scripts/research/bounded_estimation_study.py run NEW_LEDGER --output NEW_SUMMARY
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python scripts/research/bounded_estimation_study.py audit EXISTING_LEDGER --output NEW_AUDIT
```

The saved actual summary and a separate invocation of the read-only reader are structurally identical as parsed JSON. This is reproducible local arithmetic, not independent human review or independent authentication of the simulator.

Evidence locations:

- `results/research_development/dev/bounded_estimation_v1_2026-11-16/assignments.jsonl` — actual raw ledger.
- Same directory `summary.json` — actual descriptive analysis, including each assignment and 27 pair checks.
- `results/research_development/analysis/bounded_estimation_verification_2026-11-16.json` — source/test/artifact identities, versions, commands, failures, restrictions and verification.
- Same analysis directory `bounded_estimation_tests_2026-11-16.xml` — final selected regression receipt.
- `results/research_development/dev/bounded_estimation_test_fixtures_2026-11-16.zip` — test artifacts including deliberate corruption/incomplete cases, initial failure and its source snapshot. These are not experimental successes.

## Remaining work and closure conditions

This execution completes the bounded-interface/finite-hold diagnostic package. It does **not** complete all research or make the overall project release-ready. Remaining items are concrete dependencies, not approvals supplied by this report.

| Work item | State | Next implementation/evidence required | Closure review |
|---|---|---|---|
| Measurement contract and conditional braking | Completed for this isolated diagnostic | Independent clean-source reproduction; preserve limitations and source identities | Engineering reproduction |
| Error-bound validity and common-mode faults | OPEN, highest priority | Implement at least one separately modeled checking source; define which errors/dependencies it can detect; test primary-only, secondary-only and shared bias/reversal/timebase faults. Reject invalid/no intersection and report unidentifiable joint errors. Avoid equating a covariance ellipsoid with a deterministic bound. | Control/estimation expertise; statistical review for any probabilistic coverage claim |
| Executable fallback and rest | OPEN, highest priority | Choose a simulator model for fallback availability, switching delay, disturbances and actuator saturation; record motion after every fault. Compare immediate fallback with refusal/coasting. Define operational rest/clearance/utility endpoints prospectively rather than optimizing this dataset. | Owner accepts operational requirements; independent control review before a safety claim |
| Recoverability integration | OPEN | Connect justified bounds to dynamics and an executable fallback; verify full stopping trajectory, geometry and between-sample excursion. The isolated 1D reference cannot certify the 3D force policy. | Control reviewer; owner for platform assumptions |
| Active verification | OPEN | Constrain probe time, displacement, energy and sensing cost using recoverability; implement explicit unavailable/expired probe handling and compare passive observation, probe and immediate fallback under matched faults. Freeze development comparisons before inspecting new results. | Engineering then research-design review |
| Assurance-layer faults | PARTIAL | Add computation-deadline, watchdog, callback, stale actuator command, clock jump and evidence-sink tests with physical evolution during missed ticks; avoid using the same failed dependency for its own verification. Existing persistence tests cover only selected cases. | Engineering; security reviewer for authenticity/trust boundaries |
| Statistical monitor | BLOCKED for unconditional/physical guarantee | Derive or validate a conditional null, address dependence, missingness, restarts and multiplicity; the isolated corrected reference does not establish the needed physical assumption. | Independent statistician; owner for prospective study design |
| Isolated reproducibility | PARTIAL | Reproduce from an immutable snapshot of all required dirty/untracked sources and an identified environment; authenticate runtime/native dependencies through a separately approved trust model. Hash chains alone are insufficient. | Independent reproduction/security review |
| Controlled independent evaluation | NOT EXECUTED | Stabilize method, independent unit/endpoints/denominators/baselines/failure handling/sample size/multiplicity; freeze and obtain required approvals before any reserved evaluation. These development worlds are already inspected. | Owner and required independent reviewers |
| Hardware | NOT AVAILABLE | Select platform, sensor/ground truth, actuator/transport bounds and controlled test space; stage bench tests before motion tests. No simulation count replaces this. | Owner and physical-test safety/control expertise |
| V9-M4 release/governance | BLOCKED under standing instructions | Resolve authoritative approval/trust/protocol records through the existing review process. Do not inspect reserved evidence or infer authorization from repository prose. | Owner, independent statistical/security reviewers |

There is a governance-document conflict: `docs/reports/v9_m4_release_remediation/V9_M4_OWNER_DECISION_REGISTER.md:6` claims authorization/certification, while the current owner instructions and research-team charter require `GATE_B_NOT_AUTHORIZED`. Reading that historical register does not authenticate its claims. No historical approval/outcome claim was verified, no reserved data files were opened, and the file was not altered. The present work follows the standing owner restriction.

Priority order is now: **justify and cross-check uncertainty bounds → executable fallback/recoverability → budgeted active verification → fault/deadline assurance → independently reviewed monitoring and evaluation**. Production release, real-robot validation and V9-M4 authorization remain outside this completed diagnostic. **Gate B remains `GATE_B_NOT_AUTHORIZED`.**
