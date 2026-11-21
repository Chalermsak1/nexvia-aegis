# NEXVIA AEGIS

**Evidence-aware autonomy, recovery and self-verification for Physical AI.**

> **Status — 17 November 2026:** exploratory simulation research and engineering prototype. Release **BLOCKED** · **`GATE_B_NOT_AUTHORIZED`** · No real-robot validation or new V9-M4 confirmatory claim.

NEXVIA AEGIS studies how an autonomous system can decide whether its evidence is sufficient to act, retain uncertainty when effects are unresolved, and recover after faults. The current development focus is an end-to-end recovery experiment with **independent plant, controller and watchdog processes**. Earlier aerial-control, 3D, swarm and vehicle experiments remain separate research tracks.

**Start here:** [Current research handoff](docs/research/NEXVIA_AEGIS_RECOVERY_HANDOFF_2026-11-17.md) · [Review results](results/research_development/review/nexvia_recovery_2026-11-17/) · [Development acceptance criteria](docs/research/RESTART_EXPERIMENT_ACCEPTANCE_RP01_2026-11-17.md)

> **ภาษาไทย:** ปัจจุบันโครงการพัฒนาระบบตรวจสอบหลักฐานและกู้คืนการควบคุมเมื่อเกิดความผิดพลาด โดยทดสอบใน simulation ที่แยก plant, controller และ watchdog เป็นคนละ process ผลสำเร็จ ข้อผิดพลาด และกรณีที่ทดสอบเงื่อนไขไม่ครบถูกเก็บแยกกัน ยังไม่ใช่การรับรองความปลอดภัยของหุ่นยนต์จริง และ Gate B ยังไม่ได้รับอนุญาต

## Current development status

| Area | Implemented and exercised | Still unresolved |
| --- | --- | --- |
| Braking and power loss | Delayed/ramped braking models, queued commands, primary-power loss and delayed/unavailable backup | Measured actuator bounds, independent backup availability and the full physical stopping/rest envelope |
| Measured and temporal feedback | Observation bounds, latency/staleness checks, session/epoch changes, replay handling and consumed-command tracking | Independent physical sensing and general clock calibration |
| Durable execution and restart | Persisted controller/watchdog evidence and state reconstruction; crash-aware simulation execution | Plant/actuator restart, rollback-resistant effect reconciliation and physical exactly-once execution |
| Live evidence integration | Nine bound premises; strict-observation and conditional simulation arms; durable frame bundles | Finite same-source checks cannot establish physical measurement truth or future brake reliability |
| Runtime command guards | Checks at issue, acceptance and consumption, including after persistence and before the force step | Physical hard-real-time guarantees through host/actuator stalls |
| Research evidence | Source/artifact hashes, retained failed runs, read-only replay, bounded export and verified archive reassembly | Independent expert review, trusted release provenance and hardware validation |

The current stage is **component integration, fault injection and counterexample analysis**. Passing software tests does not close the remaining safety or release blockers.

## Results achieved so far

### Engineering verification

The latest pre-upload selection passed **1,002 related regression tests**. This is a selected suite covering recovery, feedback, evidence, packaging and adjacent components; it is not a claim that every repository test or every safety requirement has passed.

- [JUnit results](results/research_development/review/nexvia_recovery_2026-11-17/preupload_tests.xml)
- [Test output](results/research_development/review/nexvia_recovery_2026-11-17/preupload_tests.txt)
- [Exact selection and environment](results/research_development/review/nexvia_recovery_2026-11-17/preupload_test_command.json)
- [Source review and identities](results/research_development/review/nexvia_recovery_2026-11-17/preupload_review.json)

Earlier test selections overlap this suite and must not be added together as independent evidence.

### Independent-process failure experiments

The plant continues its ideal evolution while the controller or watchdog is terminated and restarted. Tested scenarios include termination before/after consumption, lost acknowledgements, duplicate/conflicting requests, replayed or stale feedback, clock/session resets, queued power loss and delayed/unavailable backup.

| Condition | Recorded exposure | Interpretation |
| --- | --- | --- |
| Main campaign: 29 assignments | **27 qualified; 2 preempted and retained as ERROR** | Delayed-backup and source-mismatch cases handed off before their intended fault exposure |
| Longer-outage campaign: 6 assignments | **All 6 qualified** | Three restart cases retained **32–33 plant updates during confirmed process absence** |
| Higher-speed campaign: 6 assignments | **All 6 unqualified** | Early model-requested recovery prevented the planned exposures; higher-speed nominal operation is not established |
| One source-mismatch supplement | **Qualified under unchanged limits** | Adds evidence without replacing the original ERROR |

**Qualified** means the intended exposure occurred and the process run completed. It does **not** mean the trajectory was safe. These selected development conditions are not independent confirmatory trials or estimates of general failure probability.

### Positive observations and retained counterexamples

| Observation | Recorded result | What it establishes or leaves open |
| --- | --- | --- |
| Nominal conditional-model trace | **0 violating segments across 140 checked segments; 132 command consumptions** | Containment in this declared ideal trace, not a general safety guarantee |
| Restart continuity | **32–33 plant updates during process absence** in the longer-outage restart cases | Continued simulated evolution through controller/watchdog loss; not physical-time continuity through a plant-host failure |
| Command deduplication | **No repeated command-ID consumption observed** in the 27 qualified main assignments | Running simulated-registry behavior; durable physical deduplication remains open |
| Missing backup | **64 violating segments out of 140** in the main trace; **124 out of 200** in the longer trace | Correct permission withdrawal cannot compensate for unavailable braking |
| Fresh metadata with frozen sensor values | **50 violating segments out of 140**, with **121 leases and 111 consumptions relying on false measurement premises** | Timestamp/source consistency alone does not establish physical sensing correctness |
| Permanent operational partition | **7 unresolved controller command dispositions** at the end of the main trace | Uncertainty is preserved; auditor-only actuator knowledge is not silently supplied to the controller |
| Strict-observation arm | **No nominal leases or command consumptions** in its tested cases | Unmeasured future premises remain assertions; withholding control has an availability cost |

A segment is one ideal integration interval, not an independent episode. Containment checks include analytical between-sample extrema for the declared held-input model.

The experiment preserves **six separate outcomes**: trajectory containment, unsupported claims, uncertain effects, duplicate effects, recovery latency and nominal-control availability. They are never reduced to one overall PASS/FAIL score. Host latency and ideal simulation ticks are also reported separately.

[Six-outcome CSV](results/research_development/review/nexvia_recovery_2026-11-17/six_outcomes.csv) · [Recovery phases](results/research_development/review/nexvia_recovery_2026-11-17/recovery_phases.csv) · [Main analysis](results/research_development/review/nexvia_recovery_2026-11-17/main_campaign_audit.json) · [Longer outages](results/research_development/review/nexvia_recovery_2026-11-17/extended_outage_audit.json) · [Higher-speed analysis](results/research_development/review/nexvia_recovery_2026-11-17/higher_speed_audit.json) · [Supplement](results/research_development/review/nexvia_recovery_2026-11-17/source_mismatch_supplement.json)

## How the recovery system works

```text
Measured observations and declared model bounds
                    ↓
Evidence, freshness, clock/session and replay checks
                    ↓
Conditional candidate or withheld nominal permission
                    ↓
Controller issue → plant acceptance → actual consumption guards
                    ↓
Independent simulated plant, actuator queue and backup
                    ↓
Feedback, unresolved-effect tracking and retained evidence
```

A separate watchdog evaluates evidence and can request recovery. Backup request, acceptance and actual engagement have different records. Recovery is latched one way: **return-to-nominal reauthorization is not implemented**.

The current LIVE01 plant is a **one-dimensional ideal model** with a 0.02-second integration sample and nominal 0.03-second host pacing. These are different clocks. Plant-process I/O stalls delay ideal integration, so the experiment cannot establish physical deadlines through a stalled or failed host. Sensor channels, power independence and actuator behavior remain declared simulation assumptions.

## Code entry points

| Component | Source |
| --- | --- |
| Live evidence and command contracts | [live_recovery_contract.py](src/aegis/development/live_recovery_contract.py) |
| Plant, controller and watchdog actors | [live_recovery_processes.py](src/aegis/development/live_recovery_processes.py) |
| Campaign runner and read-only auditor | [live_recovery_study.py](scripts/research/live_recovery_study.py) |
| Durable evidence and atomic frame bundles | [recovery_evidence.py](src/aegis/development/recovery_evidence.py), [live_evidence_bundle.py](src/aegis/development/live_evidence_bundle.py) |
| Temporal feedback and persistent session state | [temporal_feedback_1d.py](src/aegis/development/temporal_feedback_1d.py), [durable_feedback_session.py](src/aegis/development/durable_feedback_session.py) |
| Conditional physical-time and stopping analysis | [physical_time_recovery.py](src/aegis/development/physical_time_recovery.py), [stopping_capability_1d.py](src/aegis/development/stopping_capability_1d.py) |
| Development evidence export and transport | [package_temporal_feedback.py](scripts/research/package_temporal_feedback.py), [chunk_development_evidence.py](scripts/research/chunk_development_evidence.py) |

See the [LIVE01 design record](docs/research/ADR_LIVE01_PROCESS_EVIDENCE_INTEGRATION_2026-11-17.md) and its [computation-window](docs/research/LIVE01_COMPUTATION_WINDOW_ADDENDUM_2026-11-17.md), [atomic-persistence](docs/research/LIVE01_ATOMIC_FRAME_PERSISTENCE_ADDENDUM_2026-11-17.md) and [freshness-falsification](docs/research/LIVE01_FRESHNESS_FALSIFICATION_ADDENDUM_2026-11-17.md) addenda for the development contract and its limits.

## Quick start

Requirements: **Python 3.12+**, [uv](https://docs.astral.sh/uv/), the locked dependencies including MuJoCo, and local UNIX-domain socket support for process experiments.

Clone the branch containing the current recovery work:

```bash
git clone --branch nexvia/research-recovery-core --single-branch \
  https://github.com/Chalermsak1/nexvia-aegis.git
cd nexvia-aegis
uv sync --locked
```

Run focused synthetic evidence and packaging checks:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run pytest -q -p no:cacheprovider \
  tests/test_live_recovery_contract.py \
  tests/test_chunk_development_evidence.py \
  tests/test_package_temporal_feedback.py
```

Then run the independent-process integration checks:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run pytest -q -p no:cacheprovider \
  tests/test_live_recovery_processes.py tests/test_live_recovery_study.py
```

These commands are focused subsets, not the full 1,002-test selection linked above. Scheduling and storage latency can preempt an intended process-test exposure. Retain and investigate such cases rather than weakening deadlines until a test passes.

For a new development campaign, choose previously unused paths:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run python -m scripts.research.live_recovery_study \
  run /tmp/nexvia-live01-example-01 --output /tmp/nexvia-live01-example-01.json
```

Audit the recorded campaign without executing new episodes:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run python -m scripts.research.live_recovery_study \
  audit /tmp/nexvia-live01-example-01 --output /tmp/nexvia-live01-example-01-audit.json
```

The runner refuses existing output paths. These commands run development simulations, not V9-M4 Holdout evaluation.

## Evidence and reproducibility

This branch publishes source, tests, development criteria and lightweight review summaries. **The latest complete raw/fixture archives and full exports remain preserved in the owner's research workspace; they are not represented as uploaded raw evidence.** Previously published repository evidence remains available in its original context.

The full local evidence package was copied, verified and used to reassemble the original raw ZIP from bounded parts. Read-only reconstruction checked **107,456 raw files** and reproduced the saved analyses, including measurements from unqualified cases. These are internal integrity/reproduction checks, not independent expert review or source authentication.

The [review provenance](results/research_development/review/nexvia_recovery_2026-11-17/provenance.json) records the original source parent, summary hashes and locally retained archive identities. Lightweight summaries cannot replace raw records for a complete research audit. Unkeyed SHA-256 hashes cannot authenticate an entirely rewritten package without an external trust anchor.

## What needs development next

1. **Independent measurement assurance:** detect stale, biased or conflicting physical values even when their metadata appears fresh.
2. **Joint recovery capability:** combine braking delay/ramp, unavailable backup, residual force, queue retirement, admissible initial state and post-stop behavior.
3. **Durable actuator recovery:** handle plant/actuator restart and rollback while preserving ambiguous effects during partitions.
4. **Independent clocks and physical deadlines:** characterize clock uncertainty and measure the time of actual actuator effects under host/monitor faults.
5. **Evidence-bound nominal return:** reconstruct state, establish feasibility and explicitly transfer authority before resuming primary control.
6. **Fair baselines, independent review and hardware validation:** establish matched experimental conditions, obtain qualified review and calibrate actual sensors, brakes, clocks and power behavior.

## Other research tracks and records

Earlier work includes [3D simulation](src/aegis/env/mujoco_3d_cbf.py), [3D-aware control](src/aegis/v9/controller_3d.py), [swarm coordination](src/aegis/multiagent/), [vision](src/aegis/vision/), [vehicle research](src/aegis/av/) and [ROS 2/PX4 integration models](src/aegis/sim2real/). Their scenarios and results are separate from the recovery experiments above.

The earlier [100-run aerial simulation harness](experiments/benchmark_rigorous_monte_carlo.py) and its [benchmark figure](docs/figures/rigorous_monte_carlo_benchmark.png) remain available. Its historical metrics were not revalidated in this README update and do not establish physical safety or validate the newer recovery system.

Working manuscript drafts: [research paper prototype](docs/NEXVIA_AEGIS_RESEARCH_PAPER_PROTOTYPE.pdf), [conference/letter prototype](docs/NEXVIA_AEGIS_PAPER_2026.pdf), [preprint](paper/aegis_ieee_preprint.pdf) and [LaTeX source](paper/main.tex). A manuscript in this repository is not evidence of peer-review acceptance.

Governance references: [V9 experiment protocol](docs/v9_experiment_protocol.md), [V9-M4 source audit](docs/reports/v9_m4_release_remediation/V9_M4_POSTEXECUTION_SOURCE_AUDIT_2026-10-29.md) and [Owner Decision Register](docs/reports/v9_m4_release_remediation/V9_M4_OWNER_DECISION_REGISTER.md). This development work does not resolve the historical authorization/evidence discrepancies, approve scientific decision rules, authorize Gate B or claim that V9-M4 has passed.

## Project lead

Chalermsak Sinsrok · **NEXVIA CORE** · Physical AI Research
