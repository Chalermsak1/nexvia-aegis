# V9-M5 exploratory false-arrival investigation

Status: development only; Gate B remains unauthorized. No V9-M4 confirmatory Holdout was run. These simulations do not establish robot safety or real-world validation.

## Evidence and diagnosis

The original development output `results/research_development/dev/3d_probe_ablation_v2.json` recorded two false arrivals for the 3D-aware controller with bias `[0.8, 0.8, -0.3]`. Re-execution with the same development seeds reproduced the episode summaries and captured step-level traces in `trace_false_arrival_2234001.json` and `trace_false_arrival_2234002.json` in that directory. Tracing records truth after the controller update for evaluation; controller inputs are simulated observations only. The traces record the source hashes at their creation; the benchmark and controller were subsequently changed to add the strict candidate, so those hashes do not identify the current files.

At the STOP decision, respectively: true distance was 0.2548 and 0.2809 m, calibrated-vector norms were approximately 0.2351 and 0.2198 m, and range-window calculated upper values were 0.260126 and 0.262856 m. The controller compared these with 0.25 + 0.03 = 0.28 m. Both stops therefore depended on the extra margin: with all other inputs and prior states held fixed, comparing those same upper values with 0.25 m would reject the STOP. This does not prove the margin is the sole root cause; measurement noise, calibration error, selection of consecutive samples and dynamics also matter. The computed bound is a heuristic applied sequentially to samples at changing positions, not a validated anytime confidence sequence.

## Candidate and experimental results

The original default remains a 0.03 m margin. The separate `AEGIS_3D_STRICT_RANGE` development arm sets it to zero; this is an exploratory engineering alternative, not a change to any registered V9-M4 decision rule. Re-running the two original cases with the strict arm produced two timeouts at 100 steps, not successful arrivals. Raw traces are `trace_strict_2234001.json` and `trace_strict_2234002.json`.

An additional disjoint development seed range (2235000–2235019), two bias scenarios, two paired arms, 100 steps maximum, produced 80 episode records in `results/research_development/dev/strict_range_fresh_development.json` (SHA-256 `4d4e762aa8bf632a0c3b6e55612b03076cf7b91607000127867d9cf15bbf2128`). Each row below is out of 20 episodes:

| Bias | Arm | True success | False arrival | Abstention | Timeout |
|---|---|---:|---:|---:|---:|
| nominal | original | 6 | 0 | 1 | 13 |
| nominal | strict | 6 | 0 | 1 | 13 |
| heavy correlated | original | 5 | 0 | 0 | 15 |
| heavy correlated | strict | 5 | 0 | 0 | 15 |

All arms had zero observed collisions, CBF constraint violations and unchecked CBF steps in this sample. Observed zeros do not show zero risk. The range was selected for development, not independently registered, and repeated bias scenarios share seeds; no confirmatory interpretation or general safety claim follows. The raw file includes each assigned episode, source hashes and setup. Reproduction requires a fresh output filename:

```bash
PYTHONPATH=src .venv/bin/python scripts/research/compare_strict_range.py \
  --seed-start 2235000 --n-seeds 20 --max-steps 100 --output NEW_OUTPUT.json
```

To investigate one development episode, run `scripts/research/trace_3d_development.py` with explicit seed, bias, controller and a fresh output path. Both scripts refuse to overwrite an existing output; partial files may remain if execution fails and must not be mistaken for completed evidence. Do not use reserved Holdout seeds.

## Next engineering and research steps

1. Study repeated sampling, sensor latency and calibration uncertainty; model motion during braking and avoid treating correlated or stale range samples as independent. Design fault scenarios before interpreting another comparison.
2. Investigate high timeout frequency and the speed/accuracy trade-off; log verification interruptions and separate controller and physics failures. Do not tune against a confirmatory dataset.
3. Validate sensor noise and simulator assumptions; add independent evaluation of sequential decision rules, sampling, denominators and multiplicity before proposing a confirmatory study.
4. Preserve development outputs, dependencies and runtime versions for reproducibility; test interrupted evidence writes and isolation under failures before using any workflow for controlled research.
5. Before any V9-M4 Holdout, resolve the existing release and scientific blockers and obtain the previously required explicit owner authorization. No such authorization is given here.
