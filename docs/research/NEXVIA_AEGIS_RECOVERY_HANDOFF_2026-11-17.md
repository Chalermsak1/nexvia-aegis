# NEXVIA AEGIS recovery research: team handoff

**Development simulation only. Release BLOCKED. GATE_B_NOT_AUTHORIZED.** No hardware validation, owner release authorization or new confirmatory result is supplied by this upload.

## What this branch contains

This branch publishes the pending recovery implementation and tests under the NEXVIA AEGIS project name. It includes delayed/ramped braking, power-loss behavior, measured and temporal feedback, durable simulation execution, bounded clock mapping, uncertainty-aware recovery, evidence-aware decisions and independent-process recovery experiments. It also includes the previously developed owner-register reconciliation documents; publication does not approve any unresolved scientific or security decision.

The current LIVE01 implementation has four components:

| Component | Entry points | Scope |
| --- | --- | --- |
| Live evidence | `src/aegis/development/live_recovery_contract.py` | Nine source/configuration-bound premises; strict and conditional simulation arms; replay/staleness handling |
| Command lifecycle | `src/aegis/development/live_recovery_processes.py` | Controller issue, plant acceptance, post-persistence consumption, refreshed force-step checks, uncertain effects and one-way recovery latch |
| Independent process experiments | `scripts/research/live_recovery_study.py` | Separate autonomous plant, controller and watchdog processes; injected failure scenarios; read-only analysis |
| Evidence preservation | `live_evidence_bundle.py`, `package_temporal_feedback.py`, `chunk_development_evidence.py` | Durable frame bundles, bounded integrity exports, exclusive hash-verified archive transport and reassembly |

The 76 LIVE01 source/criterion identities match the tested workspace byte for byte. Optional earlier design records retain their criteria and add publication-scope notes for unavailable workspace evidence. The [review provenance](../../results/research_development/review/nexvia_recovery_2026-11-17/provenance.json) records source origins and raw-archive hashes. Historical records keep their original branch/path identities. One legacy packaging generator now obtains its historical branch from the recorded receipt and checks the parent identity instead of embedding a tool-specific label. Its original source remains in the parent commit and the original workspace.

## Results available for review

The completed workspace regression selection reported **981 passing tests**. A subsequent evidence-transport selection reported **68 passing tests**, including 21 new chunk tests and 47 overlapping packager tests. These are engineering checks, not independent experimental episodes. A separate pre-upload run checks this actual publication tree; its precise selection and results are recorded in the publication review receipt.

| Experiment condition | Recorded exposure | Finding |
| --- | --- | --- |
| Main campaign, 29 assignments | 27 qualified; delayed-backup and source-mismatch exposures preempted and retained as ERROR | Do not treat process completion as a successful fault exposure |
| Higher initial speed, six assignments | Six unqualified; model-requested handoff before planned faults | No supported claim of nominal higher-speed operation |
| Longer outage, six assignments | All six qualified; restart cases contain 32–33 observed plant updates during confirmed process absence | Continued ideal evolution through controller/watchdog loss, with explicit timing assumptions |
| One source-mismatch supplement | Qualified under unchanged limits | Additional evidence only; the original ERROR is not replaced |

The six outcomes remain distinct: trajectory containment, unsupported claims, uncertain effects, duplicate effects, recovery latency and nominal-control availability. Review the [six-outcome CSV](../../results/research_development/review/nexvia_recovery_2026-11-17/six_outcomes.csv), [latency phases](../../results/research_development/review/nexvia_recovery_2026-11-17/recovery_phases.csv), [main analysis](../../results/research_development/review/nexvia_recovery_2026-11-17/main_campaign_audit.json), [longer outage analysis](../../results/research_development/review/nexvia_recovery_2026-11-17/extended_outage_audit.json), [higher-speed analysis](../../results/research_development/review/nexvia_recovery_2026-11-17/higher_speed_audit.json) and [supplement](../../results/research_development/review/nexvia_recovery_2026-11-17/source_mismatch_supplement.json).

Unavailable backup produces 64 violating continuous segments in the main trace and 124 in the longer trace. Fresh metadata over frozen sensor values produces 50 violating segments, with 121 leases and 111 consumptions relying on a false measurement premise in the main trace. The permanent operational partition retains seven unresolved controller dispositions. These counterexamples are preserved. Zero lifecycle-integrity defects does not establish physically justified safety.

## Run safe development checks

Use the repository's Python environment with Python 3.12 or newer and the recorded dependencies. These commands run only synthetic/development checks and use new temporary paths:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m pytest -q -p no:cacheprovider \
  tests/test_live_recovery_contract.py tests/test_live_recovery_processes.py \
  tests/test_live_recovery_study.py tests/test_chunk_development_evidence.py \
  tests/test_package_temporal_feedback.py
```

Process tests require local UNIX-domain sockets. Host scheduling and storage latency can preempt an intended exposure. Preserve such runs as unqualified rather than extending budgets until they pass. The full related pre-upload selection is retained with its JUnit output in the review directory.

For a new development campaign, choose previously unused output paths:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m scripts.research.live_recovery_study \
  run /tmp/nexvia-new-development-run --output /tmp/nexvia-new-development-run.json
```

This is one-dimensional ideal simulation, not physical validation. Its 0.02-second ideal integration and nominal 0.03-second host pacing use different clocks. A plant-process I/O stall delays ideal integration. The experiment therefore does not prove physical deadlines through a host stall or loss of the plant process.

## Evidence distribution

This upload adds runnable code, tests, development criteria and lightweight review summaries. The new immutable raw/fixture archives, full exports and original research reports remain preserved in the owner's workspace; they are not represented as newly uploaded raw evidence. Previously published repository evidence remains unchanged. Some exceed ordinary repository-file limits. Their SHA-256 identities are recorded in the review provenance for later controlled distribution.

The complete local export was independently copied within the same environment, verified for 159 files, five Markdown documents and 24 local links, and used to rebuild the 285,714,527-byte raw ZIP from three parts. Its pinned SHA-256 is `ba6929ba188b11733991594773b0e1ea4023d57e14abae15273e80928987705c`. Read-only reconstruction checked 107,456 raw files and reproduced the saved analyses, including unqualified cases. This is internal reproducibility, not independent expert attestation. The lightweight summaries alone cannot replace the raw evidence for a complete audit.

## Review priorities and remaining work

1. Independent measurement assurance: same-source finite predicates cannot establish that fresh metadata contains fresh physical values.
2. Joint capability and admissible-state analysis: delayed engagement, unavailable backup, residual force, queue retirement, initial state and rest behavior must be composed without selecting favorable traces.
3. Durable actuator recovery: the plant registry is in memory; controller/watchdog journal recovery does not prove actuator exactly-once effects across plant loss or rollback.
4. Independent clocks and physical deadlines: the same-host simulation beacon is not an independently calibrated oscillator or real-time actuator monitor.
5. Nominal return: the recovery latch is one way; evidence-bound reauthorization and authority handoff remain undeveloped.
6. Fair baselines, qualified independent review and hardware calibration/validation remain required before broader claims.

Do not access reserved V9-M4 data, run Holdout episodes, modify frozen scientific rules, sign production tickets or infer Gate B authorization from publication. No merge into the main branch or Final Release Commit is performed by this handoff. **GATE_B_NOT_AUTHORIZED.**
