# V9-M5 team development: monitor, evidence ledger and estimated braking

**Status: exploratory simulation and synthetic tests only.** Gate B remains `GATE_B_NOT_AUTHORIZED`. No V9-M4 Holdout outcomes or reserved seed contents were accessed, no production ticket created, and no registered V9-M4 evaluation logic or frozen artifact changed. These results do not validate a robot or certify safety.

## Monitor and incremental ledger

The separate `RecoveryMonitorCandidate` inspects vector/range observations and updates a newly initialized development monitor during BRAKING, ANCHOR and RECOVERY, returning abstention on unavailable evidence or monitor alarm. Its monitor begins after the underlying STOP proposal; it does not inherit prior e-process state or authenticate sensors. See `V9_M5_RECOVERY_MONITOR_2026-10-31.md` for assumptions and synthetic tests. It is now integrated as the separately named `AEGIS_3D_RECOVERY_MONITOR` benchmark arm; baseline arms and their old results remain separate.

The new `DevelopmentLedger` stores a self-declared assignment list before execution, records START before each run, writes terminal `COMPLETED` or `ERROR` records as they occur, and checks a hash chain when inspecting. It uses exclusive new-file creation, file fsync per record and directory fsync on creation; it never silently resumes or reruns an interrupted assignment. A hash chain is not a signature, independent assignment registration or guarantee of power-loss durability. Interrupted writes can produce a partial record that requires explicit investigation, and fsync behavior depends on the filesystem. See `V9_M5_DEVELOPMENT_LEDGER_2026-10-31.md`.

`study_recovery_monitor_ledger.py` connects the two for a small development study. Three seeds 2247000–2247002, two vector biases, two arms and three range-fault conditions produced 36 assigned/completed episodes; the ledger validates as FINALIZED with zero recorded execution errors. Rows below combine the two bias settings, each uses the same three seeds, so they are not six independent world draws. Each cell is **true success / false arrival / abstain / timeout**, out of six:

| Range condition | Original anchor recovery | Post-proposal monitor |
|---|---|---|
| nominal | 2 / 0 / 2 / 2 | 1 / 0 / 4 / 1 |
| bias −0.08 m | 3 / 0 / 2 / 1 | 1 / 0 / 4 / 1 |
| independent dropout 10% | 1 / 0 / 3 / 2 | 0 / 0 / 6 / 0 |

In this tiny sample the monitor arm recorded three monitor-alarm episodes in each of the first two conditions; dropout also caused unavailable range. An unavailable range can occur from invalid simulated numeric readings even if the configured dropout rate is zero. The monitor can therefore reduce availability, and these results do not estimate false-alarm or detection rates. Sensor models, CBF damping/braking and obstacle geometry still use simulation assumptions, including plant truth in the existing benchmark.

Raw `results/research_development/dev/recovery_monitor_ledger_v1.jsonl` SHA-256 `a676c1f0a6213f29757f2b0b01d0398f31ea8d0f6f998ace528d87e70e09ff98`; self-reported-chain and outcome summary `results/research_development/analysis/recovery_monitor_ledger_v1_summary.json`. The assignment grid and selected file hashes are declared by the runner rather than independently authenticated. The ledger records last four events, not every event. Source maps are checked before/after each completed episode; later source changes invalidate exact reproduction with current files. Synthetic tests cover interruption, invalid lines, duplicates, no overwrite, source mismatches, incomplete assignments and a runner exception recorded without a retry.

## Estimated-state braking micro-study

The isolated `EstimateOnlyControl` proposal computes damping, braking and CBF projection from supplied estimated position/velocity. `NO_COMMAND` explicitly does not mean the robot has stopped. See `V9_M5_NO_ORACLE_CONTROL_2026-10-31.md` for synthetic examples and limitations.

`study_estimated_braking.py` now exercises a separate **MuJoCo braking micro-study**, not the arrival benchmark: the estimated arm sends the proposal's already-filtered force directly to the plant without recomputing a truth-state CBF. Position/velocity truth is used to generate noisy measurements and later score the physics. The environment's obstacle geometry and arena remain simulator-known; gravity compensation and the physics model are also idealized. The logged CBF residual is computed for the state presented to the filter: for the estimated arm it is an estimated-state residual, not evidence that the true-state constraint held. This is therefore a position/velocity-estimated comparison, **not a complete no-oracle robot system**. An unavailable measurement terminates as `NO_COMMAND`, without a simulated fallback.

Three seeds 2248000–2248002, four velocity cases, two arms and 80 steps produced 24 assigned/completed micro-episodes, with no execution errors. The same initial velocity was 0.4 m/s in every case. Sample ranges of final true speed, in m/s:

| Sensor case | Oracle-state CBF brake | Estimated-state CBF brake |
|---|---:|---:|
| nominal | 0.0153–0.0153 | 0.0098–0.0197 |
| underreported to 25% | 0.0153–0.0153 | 0.1728–0.1844 |
| reversed direction | 0.0153–0.0153 | 3.2631–3.2780 |
| missing velocity | 0.0153–0.0153 | `NO_COMMAND` in all three; no plant steps |

In the reversed case, force dot true pre-step velocity was positive in all 240 recorded estimated-arm steps: a counterexample showing the candidate's requested brake accelerated along the motion in this model. Force-dot sign is an observation, not a complete energy or safety analysis. No safety violation was recorded in these short episodes; this does not establish zero risk. Three seeds and a single fixed start do not support a general performance or safety conclusion.

Raw `results/research_development/dev/estimated_braking_ledger_v1.jsonl` SHA-256 `b882b77e51fe92041048aed198f9e5ea65b6f30770214518a9a20c9c46a0b888`; summary `results/research_development/analysis/estimated_braking_ledger_v1_summary.json`. The analyzer checks the self-reported hash chain, assignments, source maps, event order, finite scores, no-command accounting and missing/duplicate/inconsistent data. The results do not claim that selected hashes are complete provenance.

After this run, the study runner was updated to emit a v2 schema with additional input and force evidence; its source hash is therefore different. The historical v1 cannot be reproduced with the current runner at the same source identity. See `V9_M5_TEAM_PEER_REVIEW_FOLLOWUP_2026-10-31.md` for the later v2 run and analyzer.

## Reproduce with new paths

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_recovery_monitor_ledger.py \
  --seed-start 2247000 --n-seeds 3 --max-steps 400 --post-stop-steps 50 --output NEW_MONITOR.jsonl
PYTHONPATH=src .venv/bin/python scripts/research/analyze_recovery_monitor_ledger.py NEW_MONITOR.jsonl --output NEW_MONITOR_SUMMARY.json
PYTHONPATH=src .venv/bin/python scripts/research/study_estimated_braking.py \
  --seed-start 2248000 --n-seeds 3 --max-steps 80 --output NEW_BRAKE.jsonl
PYTHONPATH=src .venv/bin/python scripts/research/analyze_estimated_braking_ledger_v2.py NEW_BRAKE.jsonl --output NEW_BRAKE_SUMMARY.json
```

Never overwrite historical evidence or silently rerun an interrupted assignment. Each runner creates a new ledger exclusively. Selected synthetic, runner-integration and adjacent tests must be run against the relevant working tree.

## Next work

1. Add separate simulated, delayed/biased position and obstacle observations, sensor provenance and physically justified fallback; the estimated braking arm presently trusts simulator obstacle geometry and applies no command on missing evidence.
2. Retain monitoring across the actual full mission or explicitly assess the implications of restarting it; test missing vector and correlated faults with controlled non-oracle information parity.
3. Expand development scenarios and inspect disagreements/abstentions with complete traces for prespecified diagnostic cases. A larger count alone is not a confirmatory study.
4. Independently review assumptions, sampling, statistical endpoints, release security and hardware safety before making any confidence, product-safety or real-world claim.
