# V9-M5 — Conditional recovery assessment and efficient evidence auditing

Date: 2026-11-16, Asia/Bangkok. Development implementation and evidence record. **Overall release remains BLOCKED; Gate B remains `GATE_B_NOT_AUTHORIZED`.**

This increment implements and tests a post-diagnostic recovery reference and a streaming reader for existing development evidence. It establishes conditional behavior for explicit synthetic model inputs. Operational requirements, physically calibrated bounds, independent scientific/security review, and V9-M4 authorization remain outstanding. No Holdout data or reserved seeds were accessed, confirmatory evaluation executed, production ticket created/signed, frozen artifact changed, or release commit created. There is no real-robot validation.

## 1. Source identity and scope

Repository: `/Users/chalermsak/Documents/ChatGPT/New project/nexvia-aegis`. Branch: `codex/research-hardening`; parent HEAD: `74b0bfab8e57cd450293e49de881207074df3141`. These new files remain local/uncommitted. The parent commit alone does not identify this dirty source tree; the verification receipt and each run record the executed source SHA-256 map.

The [research-team charter](AI_RESEARCH_TEAM_CHARTER_2026-10-31.md) and [preceding reference/probe report](V9_M5_PHYSICAL_REFERENCE_AND_PROBE_EXECUTION_2026-11-16.md) govern this development scope. Existing user changes, reports, historical Calibration/Validation artifacts and prior development evidence were preserved. The pre-existing tracked benchmark has its original 46-insertion/2-deletion diff and SHA-256 `04bc31bf74423806200e39a44334e1dd0cf4063dde08797ef79dacb491b4323f`. The preceding reference/probe source map still matches all its files.

New source locations:

| File / entry point | Purpose |
|---|---|
| `src/aegis/development/recovery_contract.py:54` | Explicit conditional recovery assessment; no operational authorization |
| `scripts/research/recovery_contract_study.py:25` | Versioned 39-assignment development plan |
| `scripts/research/recovery_contract_study.py:57` | Descriptive outcome and premise-violation accounting |
| `scripts/research/recovery_contract_study.py:85` | Persist intent, then integrate native physics for the fixed horizon |
| `scripts/research/recovery_contract_study.py:99` | Read-only model/arithmetic reconstruction |
| `scripts/research/streaming_ledger.py:12` | Generic streaming ledger state machine |
| `scripts/research/audit_reference_stream.py:23` | One-episode adapter using the existing reference-study reconstruction |
| `scripts/research/benchmark_reference_readers.py` | Separate-process read-only time/RSS measurement |
| `tests/test_recovery_contract.py`, `tests/test_recovery_contract_study.py`, `tests/test_streaming_ledger.py` | Synthetic boundaries, native integration, interruption and evidence tests |

These are separate development modules. Existing controllers, registered evaluators, scientific thresholds, release files and original readers were not changed. The new runner does not automatically admit or deploy actions into the operational controller.

## 2. Research question and explicit synthetic settings

The previous six-tick diagnostic bounded only the test window. In its nominal `.5 m/s` example, residual speed was `.4608 m/s`; finishing the diagnostic was not recovery. This increment asks whether a bounded diagnostic can be composed with a declared braking interval and finite speed/dwell condition, and which failures invalidate that reasoning.

All criteria below are **synthetic fixture inputs, not preregistered thresholds or owner-approved operational requirements**:

| Input | Fixture value / meaning |
|---|---|
| Initial modeled speed | `.5 m/s`, three headings: X, Y, positive 3D diagonal |
| Initial position | `[-2,-2,1.3] m`; near-wall design uses X = `-2.69 m` |
| Asserted anchor radii | `.005 m` position, `.01 m/s` velocity |
| Diagnostic prefix | 6 ticks: delay 3, pulse 2, feedback 1 |
| Tick duration | `.02 s` |
| Prefix force norm budget | `sqrt(3) N`; separate disturbance norm bound |
| Model mass bounds | `[1,1.5] kg`; actual fixture plant is `1 kg` |
| Brake | Native clipped velocity servo, gain `2 kg/s`, per-axis cap `1 N` |
| Terminal speed band | `<= .05 m/s`; no finite exact-rest claim |
| Dwell | 25 subsequent ticks (`.5 s`); terminal sample plus 25 dwell samples are scored |
| Maximum total horizon | 300 ticks (`6 s`); horizon-decline fixture deliberately uses 5 |
| Kinetic energy increase budget | `.2 J`; energy-decline fixture deliberately uses `.001 J` |
| Disturbance | 0 nominally; `.02 N` finite-disturbance fixture; `.2 N` authority counterexamples |
| Infinite sampled position containment | Required in zero-disturbance fixtures; explicitly unsupported for a persistent disturbance with this velocity damper alone |

No customer specification, physical calibration, external certificate or new statistical acceptance threshold is inferred from these inputs. Energy means modeled kinetic-energy increase relative to the initial state; it does not measure electrical consumption, thermal load, total injected work, or hardware capacity.

## 3. Conditional mathematical construction

Let `s0 = norm(v_anchor) + velocity_error_radius`, `h = dt`, `N = prefix ticks`, `U = prefix force norm bound`, `D = disturbance norm bound`, and `m_lo`, `m_hi`, `c_lo`, `c_hi`, `cap_lo` be asserted positive model bounds. The model is translational explicit-Euler velocity with semi-implicit position integration, static spherical obstacles and a spherical robot. The damping-step restriction is `c_hi*h/m_lo <= 1`.

The diagnostic prefix gives:

```text
A       = (U + D) / m_lo
s_pre   = s0 + N*h*A
L_pre   = N*h*s0 + A*h^2*N*(N+1)/2
```

During recovery, a conservative scalar comparison above the positive terminal speed goal is:

```text
s_next <= s - h/m_hi * (min(c_lo*s, cap_lo) - D)
D < min(c_lo*goal, cap_lo)
```

For a fixed admissible mass and gain, the component damping map has nonnegative shrinkage under the step restriction. Each component's shrinkage ratio is bounded by the ratio at the vector norm, giving the radial contraction bound. Adding a disturbance ball gives the displayed comparison. Above the goal, using the maximum mass minimizes the guaranteed decrement. The comparison map is monotone. At/below the goal, applying the same step restriction and strict authority inequality separately establishes invariance of the speed ball under the asserted model. This argument does not establish an invariant position set under persistent disturbance.

The saturated region is summed as an arithmetic series with decrement `h*(cap_lo-D)/m_hi`. The unsaturated region is a geometric series around `D/c_lo`, with ratio `q=1-h*c_lo/m_hi`. Closed-form logarithms determine a candidate integer recovery horizon, followed by an explicit rounding check. Dwell travel is conservatively bounded by `goal*h*dwell_steps`. This avoids iterating over the prospective recovery horizon just to decide a design.

For `D=0`, continuing the same brake indefinitely gives a finite sampled path tail, `h*s*q/(1-q)` after saturation. A conditional infinite sampled containment label requires that complete tail plus prefix fit strictly inside the clearance lower bound. It also assumes the brake remains available and the model stays valid indefinitely. Finite recorded motion cannot establish those future premises.

For `D>0`, the damper can settle to a nonzero velocity. The module permits a finite speed-band/dwell assessment when sufficient authority and finite clearance exist, but declines an infinite position-containment request. No position-holding controller, mechanical latch or independently powered brake is silently assumed.

The prefix kinetic-energy increase reference is `T*(U+D)*s0 + (T*(U+D))^2/(2*m_lo)`. Recovery above the goal cannot increase speed under the stated premises. With disturbance, the energy reference also covers the terminal speed ball using `m_hi*goal^2/2`. This is deliberately a sufficient bound, not an optimal energy design.

Initial uncertainty reduces the nearest arena/floor/obstacle clearance after accounting for robot radius. Finite path must fit strictly; if infinite containment is required, its tail must also fit strictly. A declined horizon, energy, clearance or authority check never becomes a favorable scientific outcome.

**Numerical limitation:** results are labeled `FLOATING_POINT_REFERENCE_NOT_INTERVAL_VERIFIED`. Exact rational and adversarial fixtures check particular boundaries, but floating-point arithmetic is not outward-rounded certification. These formulas and tests do not establish continuous-time contact/rotation safety, hardware braking, calibrated uncertainties or an authenticated reference frame.

## 4. Actual development batch

Final batch: `results/research_development/dev/recovery_contract_v2_2026-11-16/assignments.jsonl`. It has 39 planned/terminal COMPLETED assignments, zero execution ERROR and FINAL present. Here COMPLETED means the assignment's computation finished; it does not mean a research hypothesis passed or even that physics ran.

| Family | Assignments | Physics / evaluation |
|---|---:|---|
| Nominal | 3 | Fixed-horizon execution; conditional sampled comparison |
| Persistent `.02 N`, finite horizon only | 3 | Fixed-horizon execution; conditional sampled comparison; no infinite containment |
| Wrong-sign prefix within force budget | 3 | Fixed-horizon execution; conditional sampled comparison |
| Over-budget prefix | 3 | Executed and retained; `UNEVALUABLE_PREMISE_VIOLATION` |
| Brake loss immediately after the diagnostic | 3 | Executed and retained; `UNEVALUABLE_PREMISE_VIOLATION`; observed speed/dwell criterion false |
| Brake loss after reaching the planned terminal sample | 3 | Executed and retained; observed speed/dwell criterion true, premise violated |
| Infinite containment requested with disturbance | 3 | Design unsupported; no physics |
| Insufficient terminal authority / insufficient cap | 6 | Design unsupported; no physics |
| Brake availability explicitly unavailable | 3 | Design unsupported; no physics |
| Near-wall composed clearance | 3 | Design declined; no physics |
| Insufficient energy / horizon budgets | 6 | Design declined; no physics |

Totals: **18 executed windows, 2,418 native simulated steps; 21 designs declined/unsupported before execution.** Nine executed cases supported conditional sampled comparisons and nine violated a premise. All nine conditional comparisons stayed within their path/kinetic-energy references and met the declared speed/dwell condition. These are deterministic development fixtures with common initial/model structure, not 39 independent reliability trials or a success-rate estimate.

Selected X-heading descriptive outputs:

| Case | Steps | Sampled path (m) | Largest terminal/dwell speed (m/s) | Interpretation |
|---|---:|---:|---:|---|
| Nominal | 133 | .277976632 | .007164374 | Within asserted finite reference |
| Finite disturbance | 141 | .301823523 | .015082346 | Finite speed/dwell only |
| Wrong-sign prefix | 133 | .316404145 | .008300197 | Prefix force stayed within the deliberately conservative budget |
| Over-budget prefix | 133 | .370281971 | .009931352 | Speed observed below goal; model comparison unevaluable |
| Brake loss | 133 | 1.228464000 | .460800000 | Recovery not observed; model comparison unevaluable |
| Late brake loss | 133 | .279359287 | .007164374 | Speed/dwell observed; future containment not established |

The late-loss counterexample matters: a small nonzero coasting velocity can satisfy a finite speed/dwell check while eventually leaving a bounded position region. A slow-motion endpoint alone does not establish a safe terminal position set. The fault is labeled using simulator truth (`actual_gain`) for evaluation. This runner does **not** demonstrate an onboard, independent detector of brake loss, nor derive trusted brake availability from the short diagnostic. The plan supplies that availability assertion explicitly; the negative fixtures deliberately violate it.

The planner fixes the full horizon before execution. The runner never stops early when simulator truth first reaches a target. Intent is durably written before each native physics step. Contacts or geometry violations invalidate the free-motion auditor; their raw records would remain preserved rather than receive a fabricated successful comparison. These versioned fixtures remained contact-free. The plan does not validate contact dynamics, realistic gravity compensation, non-1 kg native plants, rotations or sensor/actuator latency distributions.

## 5. Streaming audit and measured efficiency

The original generic reader remains unchanged. The new generic reader verifies canonical bytes, unique JSON keys, finite serialization, hash chain, integer indices, schemas, assignment transitions, event order and FINAL counts. A summary is available only after exhausting the complete visible stream. A valid prefix, abandoned iterator, FINAL followed by corrupt/trailing bytes, or partially written last record cannot receive complete-ledger acceptance.

Generic state memory scales with assignments plus the largest input line. The physical-reference adapter additionally retains one episode, compact summaries and cross-arm fingerprints. It reuses the original episode reconstruction and compares canonical SHA-256 fingerprints of reset/runtime and matched noise streams. Fingerprints have the usual collision assumption and supply no authentication. The adapter explicitly requires sequential assignments; the generic reader accepts valid interleaving. There is no adversarial record-size cap or constant-memory guarantee for an unbounded line/header/episode. Reading to EOF does not authenticate filesystem immutability or concurrent mutation protection.

The retained reference input was read without executing physics:

- 65,272,478 bytes; 126 completed development episodes.
- SHA-256 `ffd27fea2278806bc8dfe25ef25c8ffeec9fda4b710f0f5966b271c261cc477d`.
- Both readers produced identical canonical hashes for all six shared output fields: study, ledger state, counts, metadata, per-assignment summaries and matched triples.
- Normalized summary SHA-256: `310da4a8747901d3581a3b4ceebd515930e3fa0b99c25b6bef752f1b59e58c6e`.
- Streaming adapter peak: 181 episode events.

| Invocation order | Reader | Wall seconds | Peak process RSS (bytes) |
|---:|---|---:|---:|
| 1 | Original retained reader | 3.017287 | 468,008,960 |
| 2 | Streaming reader | 2.895541 | 61,210,624 |
| 3 | Streaming reader | 2.869109 | 60,964,864 |
| 4 | Original retained reader | 2.991506 | 486,735,872 |

Each invocation used a fresh subprocess and the same imports/runtime. Imports preceded the timed audit, while process peak RSS includes them. Measurements used macOS `ru_maxrss` bytes. Cache state was uncontrolled; this is a two-observation descriptive check per method on one local artifact. Peak RSS was about **87% lower** here, with similar read time. There is no claim of a general speedup, statistical benchmark significance or another experiment's scientific replication.

## 6. Tests, review correction and reproduction

Final selected regression suite: **342 passed in 39.46 seconds**, including 85 new tests and adjacent development modules. Earlier overlapping invocations (37, 47, then 341 tests) passed and are retained; they must not be added to the final count. This is not the full repository suite.

Coverage includes exact rational geometric decay, saturated-region sums, a short window that fits while composed recovery does not, insufficient disturbance/cap authority, unsupported availability, numerical/malformed criteria, 100 fixed-seed adversarial scalar/vector model fixtures, native X/Y/diagonal trajectories, full dwell accounting, source/runtime/force/position/summary contradictions, missing events, incomplete assignments, intentional simulator interruption and exclusive new paths. Readers are prevented from advancing physics in tests. Rehashed semantic contradictions remain rejected despite a valid ledger chain.

Code review after the first passing 341-test suite found a containment-label edge case: when a finite-only request fitted, a zero-disturbance infinite tail outside clearance could still carry a conditional containment label. The label now explicitly says `NOT_ESTABLISHED_ZERO_DISTURBANCE_PATH_EXCEEDS_CLEARANCE`. The new boundary test has finite path < clearance < infinite tail, then verifies rejection when infinite containment is requested. No threshold, model trajectory, registered rule or existing source file was changed to correct it.

The initial batch/source-path reproduction and before-fix code are retained as superseded development evidence (`recovery_contract_v1_2026-11-16`, `recovery_contract_source_reproduction_pre_label_fix_2026-11-16.zip`, and the test archive). Final results use v2 source identities. No unsuccessful test invocation occurred in this increment; intentional ERROR/corruption/interruption fixtures are expected negative tests. A passing earlier suite did not establish the absence of the subsequently found label defect.

A separate source directory verifies all declared source hashes, import origins and runtime versions, then reexecutes v2 through exclusive ledgers and checks raw-byte and full-summary equality. It deliberately reuses the original run's parent metadata; it is same-interpreter/source-path reproduction, not an independently rebuilt runtime, clean release checkout, new independent experiment or human review. Its raw ledger SHA-256 is `6e5383a30bededb14923625a7cad49e8d06909320a822fb2e848efa729c5e16d`; the final receipt identifies all retained artifacts.

Runtime: Python 3.12.14, NumPy 2.5.3, MuJoCo 3.14.0. Native package provenance is not independently authenticated by this work.

## 7. Evidence and usage

New retained evidence:

- `results/research_development/analysis/recovery_streaming_verification_2026-11-16.json`: source/test/artifact identities, run status, superseded work and limitations.
- `results/research_development/analysis/recovery_streaming_tests_v2_2026-11-16.xml`: final 342-test result; earlier XML remains separately retained.
- `results/research_development/dev/recovery_contract_v2_2026-11-16/`: final raw ledger, reconstructed summary and execution log.
- `results/research_development/dev/recovery_contract_v1_2026-11-16/`: superseded pre-label-fix raw ledger/summary/log, not the final source identity.
- `results/research_development/analysis/reference_reader_benchmark_2026-11-16/`: four separate-process measurements and retained second-order logs.
- `results/research_development/dev/recovery_streaming_test_fixtures_2026-11-16.zip`: content-addressed raw test bytes, intentional interruptions/corruptions, all overlapping XML and before-fix source revision; logical-path manifest and verified restore utility.
- `results/research_development/dev/recovery_contract_source_reproduction_2026-11-16.zip`: final source snapshot, explicit reproduction driver, reproduced ledger/summary and verification.
- `results/research_development/analysis/recovery_packaging_2026-11-16/`: packaging/reproduction tooling. Paths record this execution environment.

Use fresh output paths for every invocation. From the repository root:

```sh
# Read-only audit; compiles the initial model, does not integrate episodes.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python \
  -m scripts.research.recovery_contract_study audit \
  results/research_development/dev/recovery_contract_v2_2026-11-16/assignments.jsonl \
  --output /private/tmp/NEW_recovery_audit.json

# Read-only streaming reconstruction of the previous development study.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python \
  -m scripts.research.audit_reference_stream \
  results/research_development/dev/physical_reference_v1_2026-11-16/assignments.jsonl \
  --output /private/tmp/NEW_reference_audit.json
```

The final receipt records the exact selected pytest command. Source-path reproduction instructions are in the source archive README. Hash agreement establishes byte identity within this self-reported evidence chain; it does not establish an external trust anchor or physically correct sensors/model.

## 8. Remaining work, prioritized by closure evidence

| Priority / task | Status after this increment | Next concrete work and closure evidence |
|---|---|---|
| P0 — Operational terminal requirement | Owner requirements unresolved | Specify intended platform/use case, speed/position/dwell/clearance/energy requirements and disturbance/fault envelope. Trace every future criterion to that decision; synthetic values here grant no approval. |
| P0 — Maintainable fallback authority | Conditional model only | Model ramp, latency, power depletion, brake/bus loss and position holding. Identify a terminal set that stays feasible under the intended failures; test late loss as a mandatory negative control. A finite slow-motion result cannot close it. |
| P0 — Authenticated physical premises | Physical calibration unavailable | Establish independent frame/clock/initial-state, force and motion reference measurements; bound uncertainties and shared failures. Test common spoof and command-port corruption. Model-truth scoring is not an independent monitor. |
| P1 — Numerical assurance | Floating reference only | Independently review the scalar contraction, saturated transition, energy bound and uncertainty transport; use outward-rounded/verified arithmetic before any certificate interpretation. Resolve floating boundary behavior without inventing scientific criteria. |
| P1 — Recovery/control integration | Separate development harness complete | Design and test continuous measured-state feedback and actuator-effectiveness checks through recovery/dwell; demonstrate missing/stale feedback behavior and delay budgets. Preserve fault trajectories after refusal; avoid oracle control inputs. |
| P1 — Efficient evidence tooling | Streaming reference adapter implemented/measured | Add bounded-record/episode resource policies, immutable-input assumptions, interrupted-file/concurrent-mutation handling and schema conformance tests before treating it as a hardened service. Preserve explicit adapter interleaving limits. |
| P1 — Runtime/evidence trust | Same-runtime reproduction complete | Independently authenticate immutable source/native package, wheel/runtime provenance and trusted execution/evidence roots. Existing owner/security decisions remain separate blockers. |
| P1 — Prospective scientific evaluation | Not designed/authorized by this increment | Freeze intended independent unit, endpoints, missingness, baselines, sample size and multiplicity before collecting untouched evaluation data; reviewed development cases cannot become an untouched test set. |
| P2 — Expanded physical realism | No hardware; translation-only nominal plant | After requirements/calibration, add justified mass/gravity/ramp/latency/contact/rotation models and separate non-oracle arms. Bench actuator/sensor/transport behavior before controlled real motion when hardware exists. |
| M4 governance | BLOCKED | Resolve the existing owner decision register and scientific/security review process. No decision or release blocker is marked resolved by this M5 work. |

Specific independent control/numerical-review questions: under which mass/gain/cap/ramp/delay uncertainties does the comparison remain conservative; what position-invariant terminal set survives power/brake loss or persistent force; how should interval arithmetic account for the saturated transition and exponent/log rounding; and how can independent force/motion channels justify the model bounds without common-frame or command-model deception?

Specific independent statistical-review questions: what is the independent unit when headings/scenarios/arms share a model; which endpoint distinguishes insufficient evidence from physical failure; how should refusal, unavailable reference, corrupted evidence and execution ERROR enter denominators; which baselines and multiplicity/gatekeeping rules govern a future prospective claim? No p-values, confidence levels or pass thresholds are introduced here.

The most useful next engineering increment is a **separate delayed/ramped/power-limited fallback model with explicit terminal-set counterexamples**, followed by measured-feedback integration under the approved intended requirements. More repetitions of the current fixtures cannot supply missing physical trust, operational criteria or independent review.

**This implementation increment is complete within its stated development scope. Overall research/release readiness remains incomplete/BLOCKED. Gate B remains `GATE_B_NOT_AUTHORIZED`.**
