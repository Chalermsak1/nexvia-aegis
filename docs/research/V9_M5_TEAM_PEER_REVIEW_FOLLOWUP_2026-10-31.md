# Team peer review and evidence hardening

**Development-only and simulation-only.** Gate B remains `GATE_B_NOT_AUTHORIZED`; no V9-M4 Holdout or reserved seed contents were accessed. AI role review is not independent human statistical, control, safety or security approval.

## Findings addressed

- Both ledger analyzers now check nonempty well-formed self-reported SHA-256 maps, consistent case configuration and the complete paired Cartesian grid **implied by the manifest**. This cannot establish that the manifest is the right or independently registered design.
- The recovery ledger analyzer rejects inconsistent identities, fault settings, counts, timeouts before the assigned horizon, and missing/malformed post-STOP samples. Its `true_success` remains the original decision-time outcome, not dwell or a physical safety claim.
- The braking ledger analyzer requires a nonempty `NO_COMMAND` reason, distinguishes errors/incomplete assignments, and validates event sequence and source metadata. `NO_COMMAND` remains an interrupted simulation path with no physical fallback, not a successful safe stop.
- A separate v2 braking data schema records estimated position/velocity, measurement sequence/time, desired and projected control force, true velocity before/after (evaluation only), and estimated-state CBF feasibility/residual. The v2 analyzer checks vector/score consistency and projected-force equality; it cannot prove the logged measurements are physically truthful or independently sourced.

The original `estimated_braking_ledger_v1.jsonl` and monitor ledger remain unchanged and pass the strengthened corresponding analyzers. The new v2 runner records episode events in memory and writes them with the terminal record; a crash **within** an episode can still lose its partial trace. A `START` record without a terminal record remains incomplete and must not be silently rerun. If file fsync fails after bytes are written, an inspector may still see a structurally FINALIZED file: the reader's state describes visible bytes, not independently proven durability. Hash chains are unkeyed and self-reported.

## New braking micro-study v2

Development seeds 2249000–2249002, four cases, two arms, 80 steps: 24 assignments recorded complete, no recorded execution errors. Raw `results/research_development/dev/estimated_braking_ledger_v2.jsonl` SHA-256 `7ab994c817f374458317d00c8e0f518e86a2ead705f67febf2ad032a4dc8bb87`; summary `results/research_development/analysis/estimated_braking_ledger_v2_summary.json`. Source maps were recorded before and after each completed episode; they cover selected files only.

In three reversed-velocity estimated-arm episodes, force dotted with true pre-step velocity was positive in all 240 recorded steps; final true speeds were 3.2518–3.2597 m/s. In the three underreported episodes, final speeds were 0.1775–0.1803 m/s; missing velocity produced `NO_COMMAND` before any physics step in all three. The oracle-state arm is a reference that does not receive those sensor faults, not a matched sensor-fault ablation. The dot product covers the control force only, not total net energy; CBF residual for the estimated arm is evaluated against estimated state, not true state. These tiny runs have a fixed starting pose and initial speed and cannot estimate field risk or demonstrate a real robot behavior.

Obstacle geometry, world parameters, gravity compensation and physics are simulator-known. The estimated-state arm is therefore not a full no-oracle implementation. Current sensor models are generated from simulator truth, timestamps are idealized, and no independent fallback for missing input exists. The monitor benchmark does not inject vector loss or anomaly during recovery; unit tests of such cases do not establish detection coverage in the simulator. Its post-proposal monitor is newly initialized and its raw residuals under correlated bias require further study.

## Reproduce using new paths

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_estimated_braking.py \
  --seed-start 2249000 --n-seeds 3 --max-steps 80 --output NEW_BRAKE_V2.jsonl
PYTHONPATH=src .venv/bin/python scripts/research/analyze_estimated_braking_ledger_v2.py NEW_BRAKE_V2.jsonl --output NEW_SUMMARY.json
```

Never overwrite prior evidence or silently resume. The V2 analyzer does not read the V1 schema; use the V1 analyzer for that file. Future work should implement explicit per-step interruption evidence, a trustworthy external manifest/provenance process, independently sourced sensor inputs, continuous recovery monitoring with fault injection, and physical fallback behavior before an applied pilot. No single result here establishes safety.
