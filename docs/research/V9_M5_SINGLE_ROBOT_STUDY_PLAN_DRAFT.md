# V9-M5 single-robot study plan — draft for decision and preregistration

**Status:** exploratory design; not approved, registered, or confirmatory. Prepared from the `codex/research-hardening` work at base `3acff8ff42fcc2784e210ff8608158b549c4cbe0`. The numbers in the existing development smoke result were observed during development and cannot serve as a fresh confirmatory set. This plan does not change V9-M4 H1–H5, frozen artifacts, or Gate B.

## Research question and contribution

When a single simulated aerial robot's vector and range sensors are biased, delayed, or intermittently unavailable, can AEGIS reduce false arrival while retaining a prespecified useful level of accepted decisions and true mission success? Secondary questions concern which sensor checks, active verification, and control barriers contribute to those outcomes and at what cost in abstention or time.

This is a proposed contribution, not a claim of novelty or proven safety. Compare it against published runtime-assurance and selective-risk work, including SOTER and existing ROS safety tools, and document what remains new after that review.

## Experimental units and stages

1. **D0 — engineering development:** existing smoke and development results; tune, debug, and inspect failures freely while recording versions. No formal hypothesis verdict.
2. **D1 — independent development check:** new scenario realizations selected before the run, not reused from D0. Explore transport faults and parameter boundaries. Revisions after observing D1 remain exploratory.
3. **D2 — prospective simulation confirmation:** after owner/statistician approval and timestamped registration, freeze code, configuration, analysis, scenarios, assignment manifest, sample size and evidence custody. Use a fresh isolated test set. Do not substitute a run after inspecting outcomes.
4. **D3 — SITL/HIL and physical research:** separately approved protocol and platform safety case. Hardware is not currently available; no real-robot claim is made here.

An episode is one policy operating from a declared reset to exactly one terminal outcome. The same world/bias realization can be paired across arms, but repeated biases, policies, and episodes within the same seed/world are dependent. The statistician must specify the independent sampling unit, clustering, and how uncertainty is estimated. No sample size is fixed here.

## Arms and interface parity

| Arm | Existing starting point | Evidence or work still needed |
|---|---|---|
| A: AEGIS 3D-aware + CBF | `AEGIS_3D_AWARE_CBF` in `experiments/benchmark_physical_3d_cbf.py` | Freeze controller, sensor configuration, anchor behavior, CBF and version |
| B: CBF only | `CBF_ONLY` in the same benchmark | Verify same plant, obstacle knowledge, action limits, observations and success definition |
| C: unshielded baseline | `UNSHIELDED` in the same benchmark | Simulation-only by default; audit input parity and intentional safety differences |
| D: AEGIS without active probing | `AEGIS_3D_NO_ACTIVE_PROBE` in the development benchmark | It retains the same monitors and ordinary range checks, but abstains when probing or anchor acquisition is requested. Review this as an ablation of probing, not of every form of verification. |

The anchor in the current simulation is generated from simulator truth plus noise when queried; it is a **simulated independent measurement**, not proof that such a sensor exists on a physical robot. Record which arms receive an anchor and its query costs. Do not claim fair comparisons until differences in sensing, observation timing, controller tuning, and allowed actions are documented. A simulated crash, invalid telemetry, or unavailable ground truth must never be silently counted as success.

## Scenario matrix — development proposals

| Factor | Examples to develop | What must be frozen for D2 |
|---|---|---|
| Vector sensing | nominal, individual bias, common-mode bias, vertical bias, drift, dropout | ranges, distributions, correlation, timing, assignment probability |
| Range sensing | negative/positive bias, intermittent dropout, delayed/stale data, combined vector and range faults | sensor independence assumptions, timing/age, measurement distributions |
| Environment | start/target geometry, vertical separation, obstacles, simulator parameters | scenario weights, model version, world-generation procedure |
| Control | force saturation, infeasible CBF constraints, sensor loss at arrival, watchdog events | failure codes and whether an episode is safe to attempt |

Test individual faults first, then selected interactions. Preserve fault settings per episode; use separate environment, sensor, and fault random streams. The existing 3D benchmark has options for range bias/dropout/latency and vector bias; drift, vector dropout and validated sensor-age data are not established by those options and require additional implementation. Exhaustive coverage of every real-world condition is not claimed.

## Endpoint dictionary — proposals requiring approval

| Endpoint | Proposed numerator | Denominator | Important distinction |
|---|---|---|---|
| Coverage | accepted STOP decisions | all assigned episodes | Count failures and timeouts in the assignment ledger |
| Selective false-arrival risk | false STOP decisions | accepted STOP decisions | `UNDEFINED` at zero accepted; report M and K |
| Unconditional false-arrival incidence | false STOP decisions | all assigned episodes | A low value may reflect abstention |
| True-success rate | correct STOP decisions | all assigned episodes | Ground truth used for scoring only |
| Collision/boundary breach | episodes with recorded event | all assigned episodes | Event can overlap another terminal outcome |
| Abstain, timeout, exception | one terminal status per assigned episode | all assigned episodes | Instrument failure and missing outcome must remain visible |
| CBF feasibility | episodes/steps with reported infeasibility and residual | all assigned episodes / checked steps | Report unchecked control paths separately |

The current development analyzer defines selective risk as `false_arrival / accepted` for its schema. This is a **descriptive engineering definition**, not a change to the V9-M4 protocol, whose crash accounting requires independent reconciliation. For D2 the owner and statistician must approve the exact classification of controller exceptions, physical contacts, incomplete runs, and missing ground truth.

## Proposed hypotheses and analysis decisions

| Proposal | Estimand | Decision needed before D2 |
|---|---|---|
| P1: safety and utility | False-arrival risk among accepted decisions and coverage in the target scenario mixture | Risk ceiling, coverage floor, minimum accepted count, confidence procedure, conjunction and exception treatment |
| P2: baseline comparison | Paired difference in unconditional false-arrival incidence vs the chosen baseline | Primary baseline, direction, effect size, paired test/interval and dependence assumptions |
| P3: mission utility | True-success rate or paired difference against baseline | Absolute floor or noninferiority margin, interval and clinical/operational rationale |
| P4: component effect | Difference between full and no-active-probing ablation | Exact ablation and resource cost, hypothesis family and multiplicity |

No numerical thresholds, alpha, CI procedure, sample size, scenario weight, or formal pass status are approved here. Recommend one joint safety-and-utility primary claim with a defined hierarchy for secondary claims; an independent statistician must decide whether the sampling design supports the intended error control. Do not use an exact binomial interval as if repeated seed/scenario rows were independent. Document how the cluster-aware method behaves when no decisions are accepted.

## Missing and contradictory evidence — proposed engineering behavior

- A required baseline, planned episode, fault setting, ground-truth score, or source identity that is absent or inconsistent blocks the affected comparison; no implicit substitution.
- Duplicate or unplanned `(controller, seed, bias)` and inconsistent terminal outcomes are rejected. Exceptions must be recorded separately and assessed under the approved rule.
- `accepted=0` produces undefined selective risk, never zero risk. The raw numerator and denominator are always shown.
- Failed runs retain partial logs and assignment status; no silent rerun or removal. A retry policy must be registered before D2.
- If the assignment manifest is absent, validating records against self-declared JSON metadata cannot prove completeness. A separately controlled manifest and provenance check are necessary.

## Evidence package and tests

Store a candidate commit and working-tree state, config, independent scenario/assignment manifest, software/runtime lock, source and input hashes, policy and comparator identity, raw episode events, diagnostics, failures, analyzer version, and immutable outputs. Keep development and confirmation paths distinct. Compare summaries to raw records with a second implementation or independent reviewer before any scientific claim.

Regression tests should cover: empty acceptance, missing and duplicate episodes, incorrect bias/seed/fault, contradictory outcome flags, invalid summary, unavailable baseline, crashes, source hash mismatch, altered schema, scenario identity mismatch, and existing output path. The current analyzer covers a subset and is limited to the 3D development JSON schema; it does not parse raw ROS logs, confirm an independent manifest, or determine statistical significance.

## Owner and independent review decisions

1. Choose the intended robot/task, environment, intended operating domain, and primary comparison.
2. Approve endpoint definitions, feasible effect size, required safety/coverage criteria, error handling, and claim hierarchy.
3. Ask an independent statistician to review the independent unit, cluster/pairing structure, power, intervals, multiplicity, and missingness.
4. Approve custody and registration of a fresh D2 set; no observation or tuning on it before freeze.
5. Address separately the H2 scenario-name/index discrepancy and historical V9-M4 provenance findings. This new study cannot retroactively resolve them.

## Development smoke test

The first separately seeded D0 smoke run used 5 development seeds, three vector-bias settings, 100 maximum steps and eight arms: **120 episode records**. The 3D-aware arm recorded 6 true successes, 2 false arrivals, 2 abstentions and 5 timeouts out of 15; the no-active-probing arm recorded 3 true successes, 0 false arrivals, 11 abstentions and 1 timeout. These are small, dependent development observations and support neither a formal comparison nor a safety claim. Anchor noise now uses a separate random stream so conditional anchor queries do not advance the vector/range sensor-noise stream. Simulation targets and noise models remain shared assumptions, not real-world evidence.

The current raw input is `results/research_development/dev/3d_probe_ablation_v2.json` (SHA-256 `198c29e9e6bbf3315ede26bae2581bd47608dc6f1795ced821e28bd29b2b6eb7`). The previous `3d_probe_ablation_smoke.json` remains preserved as intermediate evidence. Version 2 scores baseline STOP before advancing physics, aligning the decision time and outcome state; version 1 had applied a step before scoring against the prior state. The accompanying analyzer report includes input and analyzer hashes. The 3D-aware controller source hash is embedded in the benchmark output; the study's approved candidate has not yet been frozen. A stricter parity audit, fault-injection suite, exception accounting, and larger independently designed study are still required.

**Current status:** D0 engineering work is available. D1 has not been executed; D2 requires protocol approval and a fresh set. No hardware is available for D3. No V9-M5 safety certification or physical validation has been established.
