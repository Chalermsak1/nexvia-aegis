# V9-M5: post-STOP and anchor rejection diagnostics

**Status:** exploratory simulation only. Gate B remains `GATE_B_NOT_AUTHORIZED`; V9-M4 Holdout has not been executed. Do not interpret these observations as a validated physical stopping guarantee.

## Why this matters

The previous score labeled arrival from ground-truth distance at the instant the controller emits STOP, without simulating the subsequent stop. The new opt-in diagnostic advances the simulated plant for 50 steps after a 3D controller STOP, applies the existing CBF-filtered braking command, and records distance, speed, collision and CBF residual after each step. At the configured 0.02 s timestep this is one second. It does not alter the existing decision-time classification or incorporate post-STOP measurements into the controller. Episodes without STOP have `post_stop: null`. This diagnostic currently supports only the 3D-aware arms.

The candidate anchor guard now distinguishes unavailable evidence from a valid anchor outside its confirmation margin, and reports its pending state. This makes abstention causes inspectable without changing its confirmation rule. These reason labels are diagnostic, not independent truth.

## Study design and integrity

`scripts/research/study_post_stop.py` assigned 20 development seeds (2238000–2238019), two vector biases, two arms, three fault conditions and a maximum of 300 steps: **240 assigned episode records**. There were no recorded execution errors and source hashes before and after matched. Seed pairing aligns initial randomness; different actions lead to different trajectories. Fault cases reuse seeds, so case results are not independent. The range was fixed at 0.25 m in the simulation configuration; the 0.05 m/s speed cutoff below is a diagnostic indicator chosen for exploration, not an approved stopped criterion.

Raw file `results/research_development/dev/post_stop_development_v1.json` has SHA-256 `b9a4b53af0bf0255c000363bacfe0e83e7fade537d5363abf5366a0d89fde6a2`. It preserves each outcome, the last four controller events, and all post-STOP observations. Source hashes cover selected files, not the full environment. The summarizer checks declared episode completeness, unique assignment, outcome consistency, and post-STOP length, and counts execution errors separately; its checks rely on the self-declared design and supplied radius. It does not prove data provenance or validate physics.

## Decision-time outcome versus post-STOP movement

Each cell is out of 20 assigned episodes. The last two columns use only the subset that was inside the radius at the instant of STOP. “Leaves” means at least one recorded post-STOP step exceeds 0.25 m; “outside at 1 s” means the final recorded step exceeds it.

| Range / anchor condition | Vector bias | Arm | True / false / abstain / timeout | Leaves / decision-time true | Outside at 1 s / decision-time true |
|---|---|---|---|---|---|
| Nominal | nominal | strict | 12 / 0 / 2 / 6 | 6 / 12 | 6 / 12 |
| Nominal | nominal | guard | 7 / 0 / 7 / 6 | 5 / 7 | 5 / 7 |
| Nominal | heavy | strict | 13 / 0 / 0 / 7 | 7 / 13 | 7 / 13 |
| Nominal | heavy | guard | 7 / 0 / 6 / 7 | 4 / 7 | 4 / 7 |
| Range bias −0.08 m | nominal | strict | 12 / 0 / 2 / 6 | 7 / 12 | 7 / 12 |
| Range bias −0.08 m | nominal | guard | 6 / 0 / 8 / 6 | 4 / 6 | 4 / 6 |
| Range bias −0.08 m | heavy | strict | 14 / 0 / 0 / 6 | 9 / 14 | 9 / 14 |
| Range bias −0.08 m | heavy | guard | 6 / 0 / 8 / 6 | 4 / 6 | 4 / 6 |
| Range bias −0.08 m, anchor dropout 30% | nominal | strict | 11 / 0 / 3 / 6 | 6 / 11 | 6 / 11 |
| Range bias −0.08 m, anchor dropout 30% | nominal | guard | 3 / 0 / 11 / 6 | 2 / 3 | 2 / 3 |
| Range bias −0.08 m, anchor dropout 30% | heavy | strict | 12 / 2 / 0 / 6 | 5 / 12 | 5 / 12 |
| Range bias −0.08 m, anchor dropout 30% | heavy | guard | 5 / 0 / 9 / 6 | 2 / 5 | 2 / 5 |

For nominal range and nominal vector bias, all 12 strict true arrivals and all 7 guard true arrivals still exceeded 0.05 m/s at one second. Across all STOPs in this sample, no post-STOP collision, missing CBF residual, or residual above 1e-8 was observed. These are descriptive observations under the simulated CBF and braking model, not evidence of no collision risk, and collision status before STOP remains separately recorded.

The anchor confirmation margin rejected five nominal-vector and six heavy-vector cases in the nominal-range condition; in every such rejection the simulated true distance at confirmation was inside 0.25 m. This does **not** show that accepting them would be safe: the readings were noisy, and post-STOP motion matters. In the range-bias/dropout/heavy-vector condition, seven anchor-margin rejections included five inside-radius cases; two additional guard abstentions had unavailable range or anchor evidence. These counts locate the availability cost and motivate further analysis; they do not justify weakening the margin by themselves.

## Reproduction and tests

Use fresh output paths; existing files are never overwritten. A crash can leave a partial output file, which must not be treated as a complete study.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_post_stop.py \
  --seed-start 2238000 --n-seeds 20 --max-steps 300 --post-stop-steps 50 --output NEW_RAW.json
PYTHONPATH=src .venv/bin/python scripts/research/summarize_post_stop.py NEW_RAW.json \
  --success-radius 0.25 --output NEW_SUMMARY.json
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_summarize_post_stop.py tests/test_post_stop_diagnostic.py \
  tests/test_anchor_arrival_candidate.py tests/test_3d_strict_range_development.py \
  tests/test_3d_aware_controller.py tests/test_3d_ablation_reproducibility.py \
  tests/test_mujoco_3d_benchmark_integrity.py tests/test_3d_development_summary.py
```

The retained summary is `results/research_development/analysis/post_stop_development_v1_summary.json`. Synthetic tests cover leaving the radius during post-STOP braking while preserving the original outcome, invalid horizons, incomplete or duplicate assignment, inconsistent outcomes and error accounting. The selected suite passed 67 tests; this is not a full suite.

## Next steps

1. Define a prospective *stabilized arrival* endpoint: observation horizon, speed tolerance, dwell duration, sampling rate, position and collision requirements, and missing-data treatment. The present 1 s and 0.05 m/s are diagnostic choices, not accepted success criteria.
2. Investigate controller designs that consider velocity and braking distance before arrival confirmation. Specify trustworthy velocity and timing inputs and handle sensor failures; do not use simulator truth as a controller input. Preserve the current arms as baselines.
3. Study anchor confirmation under correlated bias, latency and repeated queries, with a statistically justified 3D uncertainty treatment. Independent statistical review is needed before claiming a confidence or risk guarantee.
4. Validate the braking, force, drag, contact and sensor models against an eventual hardware platform; none is available now. A future study needs independent design and fresh data, and V9-M4 remains blocked pending its established owner and reviewer requirements.
