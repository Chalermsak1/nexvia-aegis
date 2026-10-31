# V9-M5 exploratory anchor arrival guard

**Status:** simulation development, not a registered confirmatory study or real-robot validation. Gate B remains `GATE_B_NOT_AUTHORIZED`. No Holdout outcomes or reserved seeds were used.

## Problem and investigation

In the prior range-bias run, three strict-range episodes with heavy vector bias were classified as false arrivals. The development traces `trace_biased_2236003.json`, `trace_biased_2236005.json`, and `trace_biased_2236009.json` reconstruct the same cases. At the STOP decision, respectively, the true distance was 0.25493, 0.25075, and 0.25463 m; the navigation-vector norm was 0.23337, 0.23248, and 0.21931 m; the calculated range-window upper value was 0.24174, 0.24213, and 0.22997 m. All three thus passed the 0.25 m strict check despite being outside the target. Their speeds were approximately 0.698, 0.255, and 0.348 m/s. Sensor noise, injected range bias and calibration uncertainty interact; these traces do not isolate a single statistical cause.

The benchmark scores true distance at the STOP decision. It does not establish that a moving robot physically stops inside the radius. Speed and post-STOP trajectory are a separate unresolved endpoint.

## Prototype

`src/aegis/v9/anchor_arrival_candidate.py` wraps the existing strict-range development controller. A proposed STOP becomes `VERIFY` with braking and an anchor request. On the next update, a valid queried finite 3D anchor and fresh valid non-anomalous range are required. The prototype stops only if `norm(anchor) + 1.645 × anchor sigma <= success radius`; otherwise it abstains. Missing or invalid evidence abstains and a terminal outcome is latched. The original controller and its default margin are not replaced.

**Limitations:** The scalar 1.645 multiplier applied to a 3D norm is an exploratory heuristic, not a validated confidence bound. The anchor is sampled from the simulator's ground-truth relative position with added noise and optional bias; independence, calibration, timestamp validity, integrity, and availability are assumptions, not established real sensor properties. Range validity is supplied by the harness, with nonzero latency rejected conservatively. The wrapper does not independently verify timestamps or make a post-stop guarantee. A candidate STOP is checked one step later than the baseline, so matching seed does not imply identical state at scoring.

## Development experiment

The script `scripts/research/compare_anchor_guard.py` used previously unused development seeds 2237000–2237019, 300 steps maximum, two vector-bias cases, strict baseline and anchor guard, across four sensor fault settings. There are 320 assigned episodes; all completed without execution exceptions. Anchor noise is generated independently of vector/range noise; anchor dropout uses a separate random stream. Identical seed and fault setting provide paired initial conditions and random streams, but trajectories diverge after different decisions.

Cells are **true success / false arrival / abstain / timeout**, each out of 20:

| Range and anchor condition | Vector bias | Strict baseline | Anchor guard |
|---|---|---|---|
| Nominal range, nominal anchor | nominal | 15 / 0 / 1 / 4 | 11 / 0 / 5 / 4 |
| Nominal range, nominal anchor | heavy | 16 / 0 / 0 / 4 | 8 / 0 / 8 / 4 |
| Range bias −0.08 m, nominal anchor | nominal | 15 / 1 / 1 / 3 | 6 / 0 / 11 / 3 |
| Range bias −0.08 m, nominal anchor | heavy | 14 / 4 / 0 / 2 | 4 / 0 / 13 / 3 |
| Range bias −0.08 m, anchor dropout 30% | nominal | 15 / 1 / 1 / 3 | 4 / 0 / 13 / 3 |
| Range bias −0.08 m, anchor dropout 30% | heavy | 16 / 1 / 0 / 3 | 2 / 0 / 15 / 3 |
| Range bias −0.08 m, anchor bias `[0.08, 0, 0]` m | nominal | 15 / 1 / 1 / 3 | 3 / 0 / 14 / 3 |
| Range bias −0.08 m, anchor bias `[0.08, 0, 0]` m | heavy | 12 / 4 / 0 / 4 | 4 / 0 / 12 / 4 |

For heavy vector bias and negative range bias with nominal anchor, the four baseline false-arrival cases paired with three guard abstentions and one guard timeout. Ten baseline true successes paired with guard abstentions. Anchor guard made 217 total anchor queries in those 20 episodes versus 200 for the strict baseline; these counts include calibration queries, not just arrival checks. Counts of zero false arrivals are not evidence of zero risk. Scenarios reuse seeds and selected fault levels; 20 episodes per cell cannot substantiate a general safety or efficacy claim. A fixed anchor bias in one direction is not a comprehensive common-mode fault test.

Raw evidence: `results/research_development/dev/anchor_guard_development_v1.json`, SHA-256 `6583ce866259e9e0ada770910d92efc49e267b5e1dd7405c8c54d3fb006d3ccc`. It contains assigned outcomes, exception records, fault settings, runtime versions and source hashes. Source hashes identify selected files, not the full dependency tree or an externally attested environment. The empty output file is reserved before execution, so an interrupted run can leave an incomplete file; do not treat one as complete. Preserve outputs and use a fresh path for each run.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/compare_anchor_guard.py \
  --seed-start 2237000 --n-seeds 20 --max-steps 300 --output NEW_OUTPUT.json
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_anchor_arrival_candidate.py tests/test_3d_strict_range_development.py \
  tests/test_3d_aware_controller.py tests/test_3d_ablation_reproducibility.py \
  tests/test_mujoco_3d_benchmark_integrity.py tests/test_3d_development_summary.py
```

## Interpretation and next work

The candidate is useful for studying a safety/availability trade-off but is not ready to replace the baseline: in this sample it converts many successes to abstentions, and its observed absence of false arrivals is conditional on a narrow simulated anchor model. Next investigate anchor failure correlation and biases toward the target, the cause of rejected true successes, and whether bounded repeated confirmation can improve utility without implicitly reusing samples as independent. Design and separately score braking and stable final position; instrument confirmation-only queries and operating cost. Define freshness at the real interface rather than assuming simulator timing. Before any confirmatory claim, fix the scientific design in advance and obtain appropriate independent statistical and security review. V9-M4 release blockers and owner authorization remain separate prerequisites.
