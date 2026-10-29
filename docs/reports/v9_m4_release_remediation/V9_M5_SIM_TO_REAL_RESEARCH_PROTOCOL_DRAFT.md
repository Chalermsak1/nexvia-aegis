# V9-M5 prospective research protocol draft: safety and utility transfer from planar simulation to 3D and physical robots

**Version:** draft 0.1, 2026-10-29

**Status:** decision preparation only; **not preregistered, approved, or executed**. No thresholds, sample size, hardware configuration, or analysis choices in this draft are binding until dated approval and registration before new confirmatory data access.

**Primary research question:** *When the frozen AEGIS policy is transferred from the V9 planar simulation to a defined 3D task and then a physical platform, does it retain bounded false-success risk while delivering a prespecified minimum level of useful task completion under realistic sensor faults?*

## 1. Why this is the next study

The visible V9 preregistration concerns an extended 12-scenario simulated task and defines selective risk, accepted-count, and coverage criteria for H1; H2 is a gatekept core-10 selective-risk claim ([protocol, lines 15–39](https://github.com/Chalermsak1/nexvia-aegis/blob/5055526f83846d1ce7a0e76058fc27407e2ff06f/docs/v9_experiment_protocol.md#L15-L39)). Its [outcome rules](https://github.com/Chalermsak1/nexvia-aegis/blob/5055526f83846d1ce7a0e76058fc27407e2ff06f/docs/v9_experiment_protocol.md#L60-L69) count controller exceptions conservatively. The reported V9-M4 Holdout follows a [two-coordinate world](https://github.com/Chalermsak1/nexvia-aegis/blob/5055526f83846d1ce7a0e76058fc27407e2ff06f/src/aegis/v3/env/world.py#L55-L78), while separate [3D CBF](https://github.com/Chalermsak1/nexvia-aegis/blob/5055526f83846d1ce7a0e76058fc27407e2ff06f/experiments/benchmark_physical_3d_cbf.py#L1-L38) and [3D swarm](https://github.com/Chalermsak1/nexvia-aegis/blob/5055526f83846d1ce7a0e76058fc27407e2ff06f/experiments/benchmark_mujoco_swarm_3d.py#L1-L40) development benchmarks have been added. The 3D benchmark [projects 3D measurements into a planar V9 core](https://github.com/Chalermsak1/nexvia-aegis/blob/5055526f83846d1ce7a0e76058fc27407e2ff06f/experiments/benchmark_physical_3d_cbf.py#L52-L60); equivalence of the 2D and 3D safety claim is not established by that projection. The current [post-execution source audit](V9_M4_POSTEXECUTION_SOURCE_AUDIT_2026-10-29.md) also lists unresolved V9-M4 claim and provenance issues. V9-M5 must be a **new** study, with fresh development and confirmatory sets. Its analysis cannot retroactively repair V9-M4.

## 2. Decision boundary and study objectives

### 2.1 Primary objective

Estimate and test, in each preselected target domain, the risk of a false success among accepted decisions and the fraction of episodes in which a decision is accepted. Safety and usefulness are a joint requirement. A policy that merely abstains on everything is not successful.

### 2.2 Secondary objectives

1. Estimate unconditional false-success incidence, true-success rate, collision rate, near-miss rate, timeout/abstention rate, controller exception rate, and intervention rate.
2. Quantify the *simulation-to-physical gap* for each metric using the same scenario taxonomy and, where possible, matched scenario settings. Do **not** treat random simulator seed and physical trial as literally identical units.
3. Isolate contributions of runtime assurance, 3D CBF shield, sensor cross-check, and multiagent consensus with prespecified ablations.
4. Characterize the operating envelope as fault severity, environment shift, and latency rise. Report negative results and guardrail tradeoffs.
5. Measure calibration or decision drift after transfer without tuning on final evaluation episodes.

### 2.3 What the study cannot claim automatically

Passing a planar simulation, 3D simulator, or single laboratory platform does not imply general safety across unseen hardware, environments, fault families, or autonomous deployment. A physical pilot is feasibility evidence until a separately powered, registered physical confirmatory cohort is completed. V9-M4's published `GATE_B_CONFIRMED` claim is under source-level reconciliation and must not be used as proof of 3D or physical validation.

## 3. Study populations and experimental units

| Domain | Unit and hierarchy | Purpose | Claim boundary |
|---|---|---|---|
| D0: planar reference | One policy × scenario × independent simulator seed episode; seeds nested in scenario | Reproduce interface behavior and detect transfer regressions with **new** seeds | Engineering benchmark, not new physical evidence |
| D1: 3D simulator | One policy × scenario × independent 3D world realization; several episodes may share world/obstacle layout | Develop and evaluate transfer behavior, including vertical motion and shield | Simulation evidence only |
| D2: hardware-in-loop | One closed-loop trial with real sensor/control timing and a simulated or constrained plant | Latency, communication, watchdog, and interface validation | Engineering readiness |
| D3: supervised physical pilot | One reset-to-reset physical trial on fixed named robot and site; trials nested in day/operator/robot | Feasibility, failure discovery, safety envelope | Exploratory unless independently preregistered |
| D4: physical confirmatory | One independent physical trial after final freeze; blocked by prior safety gates | Confirmatory physical claim if design/power/approval support it | Only specified platform, site, scenarios, and conditions |

**Experimental unit:** the full attempt from standardized reset through termination, including aborted attempts, exceptions, and watchdog stops. Repeated episodes on one robot/day are clustered; naive independent Bernoulli intervals may be anticonservative. The independent statistician must specify the cluster-aware inferential unit or hierarchical model before confirmatory data. All policy comparisons should use matched scenario configurations and randomize policy order, with washout/reset rules that prevent carryover.

## 4. Policy and comparator definition

| Arm | Role | Frozen identity required |
|---|---|---|
| A: AEGIS V9 core + 3D CBF integration | Primary candidate | Commit/tree, policy parameters, weights, 2D-to-3D interface, sensor transformation, controller and CBF settings, firmware and configuration hashes |
| B: CBF-only | Safety mechanism ablation | Same plant, sensor feed, mission, and hardware limits; no runtime risk monitor |
| C: AEGIS V9 without 3D shield | Risk monitor ablation | Safety review may restrict to simulation only; never run unsafe physical ablation without approved safeguards |
| D: existing V8.1 or another documented baseline | Continuity comparator | Exact implementation, sensor parity, tuning provenance, and permitted physical safety envelope |
| E: unshielded naive controller | Mechanism benchmark | Simulation-only unless independent physical safety approval explicitly permits it |

The primary comparison must be chosen **before** confirmatory episodes. Every arm must use equal observation availability, task definition, action limits, stopping time, and fault injection where technically possible. If parity is impossible, list the asymmetry and limit the claim. The present 3D benchmark's controller labels ([source, lines 1–38](https://github.com/Chalermsak1/nexvia-aegis/blob/5055526f83846d1ce7a0e76058fc27407e2ff06f/experiments/benchmark_physical_3d_cbf.py#L1-L38)) are development examples, not a registered comparator set.

## 5. Outcome dictionary and denominator rules — proposed

Define each endpoint on a complete episode, preserving raw sensor, controller, shield, and ground-truth channels separately. Ground truth may determine outcomes after the episode but must not enter the controller. The V9 source protocol uses `A`, `TS`, `FS`, `AB`, `TO`, and `crashed` ([lines 60–68](https://github.com/Chalermsak1/nexvia-aegis/blob/5055526f83846d1ce7a0e76058fc27407e2ff06f/docs/v9_experiment_protocol.md#L60-L68)). V9-M5 needs new physical definitions rather than importing the V9 distance thresholds without validation.

| Endpoint | Proposed operational definition | Denominator | Ambiguity to settle |
|---|---|---|---|
| Accepted decision `A` | Controller declares mission arrival/STOP before timeout with no disqualifying exception | All assigned episodes | Does a shield-enforced stop count as acceptance or intervention? |
| True success `TS` | Accepted and independent ground truth meets 3D position/orientation/time/safety tolerances | All assigned episodes for TSR; accepted episodes for precision | Physical ground-truth accuracy and tolerance must be approved |
| False success `FS` | Accepted but ground truth violates success tolerance, **or** a prespecified unsafe exception class | All assigned episodes for incidence; accepted episodes for selective risk only under a predeclared exception rule | Whether a crash with `A=0` enters selective-risk numerator requires a formal definition |
| Selective risk `R_sel` | False accepted decisions divided by accepted decisions; handling of exceptions separately defined | `M=sum(A)`, undefined at `M=0` | Avoid mixing fail-unsafe exception penalty with a denominator that excludes crashes |
| Coverage `C` | Accepted decisions / all assigned episodes | All assigned episodes | Minimum useful coverage by domain and scenario |
| Unconditional incidence `R_inc` | FS / all assigned episodes, with all exceptions/abortions retained | All assigned episodes | Exception classification and instrument failures |
| Collision / breach | Any physical contact or crossing of the preregistered minimum clearance or geofence | All assigned episodes | Sensor accuracy, near-miss margin, severity |
| Other states | Abstain, timeout, watchdog stop, emergency stop, human intervention, invalid instrumentation | All assigned episodes | Mutually exclusive terminal-state hierarchy and censoring |

**Required algebraic checks:** every assigned trial has exactly one terminal state; accepted true and false outcomes are disjoint; all counts and denominators reconcile to the assignment log; crashes and emergency stops are never silently dropped. Publish a confusion matrix and reason-coded exception ledger. Failed ground-truth instrumentation makes the outcome **unevaluable**, not a success. Preserve the physical trial and log the missingness; the confirmatory decision cannot pass if the required evidence is incomplete under the approved rule.

## 6. Prospective hypotheses and estimands — choices for approval

The following are **proposed questions**, not registered pass criteria. The owner and independent statistician must fix direction, threshold, alpha allocation, and complete decision rule before seeing D1/D4 confirmatory outcomes.

| ID | Proposed estimand and population | Candidate test/interval approach | Decision still required |
|---|---|---|---|
| M5-H1: 3D simulated selective safety | `P(FS=1 | A=1)` over frozen 3D scenario mixture, with `M` and `C` guards | Exact one-sided binomial bound if independent units; cluster-aware alternative if shared worlds | Risk cap, coverage floor, sample size, accepted-count floor, cluster treatment |
| M5-H2: 3D physical-envelope safety | Collision/breach probability and false-success incidence over a frozen fault envelope | Exact or cluster-adjusted upper bounds; both conjuncts if both essential | Whether both outcomes are co-primary; allocation of familywise error |
| M5-H3: useful completion | Difference in true-success probability vs approved baseline in matched scenarios | Paired risk-difference CI; noninferiority or superiority chosen prospectively | Baseline, margin, direction, minimum absolute TSR, policy order |
| M5-H4: transfer gap | `metric_physical − metric_3D` in matched scenario strata | Stratified/cluster-aware paired or hierarchical interval, with calibration validation | What gap is scientifically acceptable; cross-domain comparability |
| M5-H5: physical confirmatory safety and utility | Joint selective risk/coverage/collision/TSR on the named physical platform | Predeclared intersection–union or hierarchical gatekeeping with simultaneous bounds as needed | Whether feasible to power; primary population, sample size, alpha, multiplicity, stopping |

**Recommendation:** make safe accepted decisions and useful completion a *joint* primary objective; retain unconditional collision/incident reporting as a separate safety guardrail. Use a fixed hierarchy or explicit familywise adjustment, rather than declaring five independent unadjusted passes. The exact procedure is an independent statistical-review decision. If a physical confirmatory cohort is infeasible, label D3 as a pilot and report interval estimates without a physical certification claim. Do not carry over V9's `M≥59`, `C≥0.35`, or `R≤0.05` automatically; those values belong to the V9 registered mixture and may be scientifically inappropriate for the new platform.

## 7. Scenario suite and transfer stressors

Freeze a scenario taxonomy with severity levels and deployment frequencies. Separate *naturalistic mixture* from *stratified stress testing* because equal weighting of faults does not estimate field incidence. Suggested factors to define and measure:

1. Geometry: obstacle density, narrow passages, vertical clearance, target elevation, occlusion, dynamic objects, start/target separation.
2. Dynamics: mass/inertia variation, actuation saturation, motor lag, drag, wind or ground effect, friction/contact, battery state.
3. Sensing: independent bias, common-mode bias, drift, dropout, latency, outliers, spoofed anchors, calibration loss, time synchronization error.
4. Computation/network: frame drops, stale messages, clock skew, CPU load, delayed shield decisions, controller restarts, communication partitions.
5. Multiagent, **only if included in scope**: malicious/Byzantine messages, collision avoidance interaction, consensus isolation, formation failures. The [3D swarm benchmark](https://github.com/Chalermsak1/nexvia-aegis/blob/5055526f83846d1ce7a0e76058fc27407e2ff06f/experiments/benchmark_mujoco_swarm_3d.py#L1-L40) does not by itself validate a multiagent physical claim.
6. Domain shift: lighting, surface, reflectivity, motion-capture dropout, room layout, payload, operator, robot serial number, and day.

For each scenario record: origin, parameter range, expected occurrence, severity rationale, safety constraints, assignment probability, and whether it belongs to development or final evaluation. Randomize settings via a preregistered generator, retain seeds and manifest under controlled custody, and prevent model/policy tuning on final outcomes. Physical fault injection must be hazard reviewed; unsafe faults remain simulation/HIL only.

## 8. Sampling, power, and randomization plan

1. Define the smallest effect or risk bound that would change a deployment decision. This must be justified from safety requirements and task utility, not selected after seeing data.
2. For each proposed primary claim, calculate required **independent** unit count under plausible risk and coverage. Account for the fact that selective-risk precision depends on accepted count, not total assignments. Include uncertainty in coverage and cluster intraclass correlation.
3. Simulate operating characteristics of the complete decision algorithm under null, boundary, and alternative cases: Type-I error, power, expected physical trial count, probability of `M=0`, missingness, and optional safety stopping. Keep simulation code/results with the preregistration.
4. Block randomization by scenario/day/robot; randomize policy order within safe blocks; predefine washout, restart, and carryover checks. Keep allocation concealed from the outcome assessor where feasible. A safety operator may need to know the condition; document limits of blinding.
5. Define development/final split before evaluation. Keep a fresh, isolated final 3D set and, if approved, a separate physical confirmatory cohort. No sample-size increase or extra looks after outcomes without a registered sequential design.

**Unresolved numeric fields:** `N_3D`, `N_physical`, minimum accepted count, target risk, coverage floor, utility margin, alpha, cluster design effect, stopping boundary, and every scenario weight. No values are inferred in this draft.

## 9. Analysis plan and missing-evidence rules — proposed

**Primary set:** all assigned episodes according to frozen manifests, including crashes, emergency stops, and aborted trials. Report by arm, domain, scenario, day/robot, and severity. Keep descriptive point estimates, intervals, and formal decisions separate.

**Preferred analysis sequence:** validate manifest and outcome algebra → verify frozen candidate and environment → classify all assigned trials → compute denominators → inspect missingness → compute estimates and intervals → apply prespecified hierarchy/multiplicity → assess guardrails → generate machine-readable verdict with evidence links. An implementation exception never means statistical acceptance.

**Missing/incomplete evidence:** no baseline means comparison hypothesis `UNEVALUABLE`; absent or mismatched paired trial means pair-level discrepancy reported and a preapproved incomplete-pair rule applied; no ground truth means that trial cannot be a verified success; failed safety telemetry blocks a safety claim unless a conservative prespecified rule makes it a failure. A missing artifact, truncated log, hash mismatch, version mismatch, or unverifiable physical trial blocks the corresponding confirmatory claim. `M=0` makes selective risk undefined; coverage is zero. Contradictory evidence requires an independent reconciliation record and precludes automatic pass. Engineering retry of a failed *development* run is allowed with provenance; confirmatory retries need a preregistered failure/restart rule and may not cherry-pick episodes.

**Multiplicity:** the independent statistician must choose a coherent family and method for all formal claims, including primary safety/utility conjunctions, per-scenario envelopes, and any interim stopping. Report unadjusted exploratory estimates without relabeling them confirmatory. Predefine whether a failed upstream gate causes downstream `NOT_TESTED`, `BLOCKED_BY_GATE`, or descriptive reporting.

**Sensitivity analyses:** intention-to-evaluate versus strict instrument-valid set; all technical failures counted unsafe; site/day leave-one-out; alternate sensor calibration within frozen tolerances; cluster-adjusted intervals; scenario reweighting to plausible deployment frequencies. Mark all sensitivity results as supportive, not substitutes for the registered primary decision.

## 10. Safety case and physical execution stages

| Stage | Work and gate | Evidence to retain | Approval |
|---|---|---|---|
| S0: source correction | Reconcile V9-M4 H2/status/dimensionality and provenance; freeze a corrected claim map | Independent statistical/security opinions, dated errata, original evidence | Owner + independent reviewers |
| S1: interface contract | Specify 3D coordinate frames, units, transforms, timestamping, controller observation parity, Z behavior, CBF invariants | Interface spec, code review, unit/property tests | Engineering lead + safety reviewer |
| S2: simulator development | Validate 3D physics realism and sensor models; tune only on development worlds | Model parameters, calibration logs, seeds, failure log, negative cases | Research lead |
| S3: frozen 3D evaluation | Register design, freeze candidate/baselines, execute fresh 3D final set once | Signed manifest, hashes, raw data, environment lock, analysis code | Owner + statistician before execution |
| S4: hardware-in-loop | Exercise watchdogs, timing, network faults, emergency stop, data logging | Timing traces, fault-injection reports, independent E-stop tests | Safety lead |
| S5: physical pilot | Supervised low-energy trials inside containment with operator stop authority | Trial-by-trial logs, incident/near-miss records, calibration and site photos | Institutional/operational safety approval |
| S6: physical confirmatory | If powered and approved, run fresh preregistered physical cohort | Immutable raw data, randomization, full accounting, independent analysis | Owner + statistician + safety reviewer |

**Physical stop rules to specify before S5:** emergency-stop triggers, speed/force/geofence limits, minimum clearance, loss-of-localization action, stale command timeout, network-loss behavior, battery and thermal limits, human proximity, maximum incident count, who can stop trials, restart authorization, and incident escalation. Avoid testing an unsafe comparator on hardware merely for a balanced experiment. A safety stop is recorded as an outcome and remains in the assignment ledger.

**External method references:** [NIST's robot performance assessment framework](https://www.nist.gov/programs-projects/performance-assessment-framework-robotic-systems) supports measuring perception, mobility, and safety as system-level capabilities; this motivates the staged, multi-endpoint testing above. [ISO's robotics standards inventory](https://www.iso.org/cms/live/live/en/sites/isoorg/home/sectors/engineering/robotics.html) lists different standards for industrial, collaborative, and personal-care robots. The safety reviewer must identify which standard actually applies to the selected platform and use case; this draft does not claim compliance with any standard.

## 11. Engineering and statistical verification matrix

| Level | Synthetic or controlled test | Pass evidence |
|---|---|---|
| Unit | Coordinate transform round trips, frame handedness, 2D-to-3D projection, units, timestamp monotonicity, sensor parity, geometric clearance | Exact fixtures and property bounds; no silent Z loss |
| Unit | Outcome algebra for accepted true/false, abstain, timeout, controller exception, shield stop, watchdog stop, missing ground truth, `M=0` | Deterministic counts; impossible states rejected |
| Unit | Confidence-bound boundary cases at `k=0`, `M=0`, exactly-at-threshold, one episode either side; cluster-aware estimator checks | Values independently calculated; defined `UNEVALUABLE` cases |
| Unit | Missing baseline, duplicate pair, altered scenario, changed policy hash, incomplete partition, conflicting summary/record | Fail closed; never `CONFIRMATORY_PASS` |
| Integration | Simulator ↔ controller ↔ CBF ↔ sensors with injected bias, dropout, delay, obstacles, vertical motion | Logged state/action/ground-truth separation and invariant monitoring |
| Integration | HIL stale packet, CPU stall, clock skew, E-stop, communication loss, logging disk full | Safe actuator state and complete fault event record |
| End-to-end | Rebuild from frozen commit/environment; execute **synthetic** fixture evaluation; compare independent implementation | Reproducible machine-readable verdict and artifact inventory |
| Security/provenance | Signed manifest verification, artifact hash mismatch, wrong executable/runtime, rollback/replay attempt, custody chain, durable evidence root | Rejection with explicit reason; originals preserved |
| Physical readiness | Containment, supervised E-stop drill, calibration check, emergency response rehearsal, known-safe trajectory | Signed safety checklist and operator training record |

Testing alone does not validate a scientific hypothesis. Final inference requires the approved design and real measurements from the relevant domain.

## 12. Evidence, reproducibility, and reporting contract

Before every formal run record UTC/local timestamps, candidate commit/tree, branch/tag, container or environment digest, Python and dependency provenance, firmware and robot serial, sensor calibration, scenario manifest, randomization manifest, protocol version, analysis script hash, owner/reviewer approvals, operator identity, and site. During execution preserve synchronized raw observations, ground truth, actions, shield decisions, interventions, event codes, stderr/stdout, process exit, hashes, and immutable assignment ledger. At close produce an artifact index with SHA-256 for each file, independent checksum verification, discrepancies, and access log. Raw data must be retained even when a run fails. Publish aggregate and per-scenario results, uncertainty intervals, exclusions/missingness, deviations, safety events, and limitations. Do not use the term “real-robot validated” until a physical study meeting the registered criteria has completed and been independently reviewed.

## 13. Owner and independent-review decision register

| Decision | Recommendation and rationale | Who must approve | Blocking evidence/analysis |
|---|---|---|---|
| D1 — V9-M4 claim correction | Reconcile H2 and dimensionality as dated addenda before using V9 as a baseline; preserve original report | Owner + independent statistician; security reviewer for provenance | Audit A1–A7 and original candidate/execution evidence |
| D2 — physical platform and environment | Name one robot, sensors, site, operating envelope, and ground-truth instrument; narrow claims to that setting | Owner + safety lead | Hardware datasheets, hazard analysis, calibration plan |
| D3 — primary endpoints/thresholds | Joint safety-and-utility rule, with collision guardrail; justify each numeric criterion | Owner + independent statistician + safety reviewer | Risk/utility justification and operating-characteristic study |
| D4 — baselines/ablations | Approve primary comparator and simulation-only unsafe arms; enforce interface parity | Owner + independent reviewer | Comparator implementation and parity audit |
| D5 — sampling/analysis | Predefine independent unit, clusters, power, randomization, missingness, multiplicity, and stopping | Independent statistician + owner | Written statistical analysis plan and simulation-based power report |
| D6 — final-set custody | Fresh 3D and physical confirmatory data isolated from development | Owner + independent custodian | Access control, manifest, immutable storage, audit trail |
| D7 — physical safety gate | Require HIL/E-stop/containment before pilot; incident-stop authority remains independent of research goals | Safety reviewer + owner | Signed safety case, drills, training, insurance/institutional requirements as applicable |
| D8 — claim language | Separate planar Holdout, 3D benchmark, physical pilot, physical confirmatory; disclose uncertainty and unresolved V9-M4 disputes | Owner + independent statistician | Claim/evidence map and approved abstract |

## 14. Immediate next actions and deliverables

1. **Now:** complete V9-M4 independent post-execution audit and preserve original raw evidence under controlled access; publish a dated claim correction if indicated. Do not rerun the consumed Holdout.
2. **Then:** write the V9-M5 platform/interface specification, scenario catalog, outcome codebook, hazard analysis, and statistical analysis plan; independent statistician reviews estimands, unit of analysis, power, missingness, and multiplicity.
3. **Before final data:** freeze code, baselines, thresholds, manifests, environment, safety stops, and analysis; register the protocol with a timestamped public or controlled registry. Distinguish every amendment from the original registration.
4. **Engineering:** implement and verify 3D interface and safety controls using synthetic fixtures and development worlds; retain all negative results.
5. **Evaluation:** progress through simulator, HIL, supervised pilot, and only then a separately approved physical confirmatory cohort. At each stage, issue a go/no-go decision with evidence.

**Open blockers:** V9-M4 source contradictions, no approved V9-M5 estimands/thresholds/sample size, no named physical platform or independent safety case, no frozen new test sets, and no independent statistical sign-off. This draft neither changes Gate B nor certifies V9-M4 or V9-M5.

[OSF's registration guidance](https://help.osf.io/article/330-welcome-to-registrations) describes preregistration as a timestamped, read-only plan made before data collection or analysis. It is an available mechanism for the proposed V9-M5 freeze; the owner may choose another credible registry with equivalent versioning and access controls.
