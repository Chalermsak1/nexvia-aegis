# Development investigation: timeout and range faults

This is exploratory simulation, not V9-M4 Holdout or robot validation. Gate B remains unauthorized. Existing evidence was retained, including intermediate `*_development.json` runs produced before the final freshness fix; use only the `_v2` files below for this study.

## What was changed

The 3D simulation harness previously passed delayed range values to the 3D controller as valid, even though the measurement described an earlier position. It now marks a range invalid whenever the simulated fixed latency is nonzero. This conservative rule applies only to the harness; `RangeReading` does not encode timestamp or freshness, and this is not a production transport solution. Zero-latency behavior is unchanged. Traces now distinguish delivered validity from freshness. This may reduce availability; it does not correct bias or make the controller safe.

The comparison script now accepts range bias, dropout and latency and records them with each episode and in the run configuration. It refuses to overwrite an existing output. Synthetic regression checks verify that only fresh range is passed as valid, and that an at-target fixed world with delayed range cannot generate a STOP. Selected suite: 43 tests passed (see command below).

## Timeout diagnosis

For development seed 2235000, heavy vector bias and strict range, the 100-step trace timed out at distance 1.9343 m; it contained 90 NAVIGATE and 10 PROBE decisions. The same simulation with 300 steps reached a true success at step 226, distance 0.2165 m. Another seed, 2235001, succeeded in 77 steps under both time budgets. This illustrates that 100 steps can truncate an otherwise successful trajectory; it does not establish the cause of every timeout. The four trace files are retained as `trace_timeout_<seed>_<max-steps>.json` under `results/research_development/dev/`.

## New comparison

Each run used development seeds 2236000–2236019, nominal and `[0.8, 0.8, -0.3]` vector bias, both arms, and a 300-step budget: 80 records per run. Seed and noise streams are paired between arms; physics trajectories need not remain paired after decisions diverge. The three fault settings use the same development seeds, so they are not independent studies. Each cell below is **true successes / false arrivals / abstentions / timeouts**, out of 20 episodes per arm and scenario.

| Range setting | Vector bias | Original | Strict |
|---|---|---|---|
| No injected range fault | nominal | 16 / 0 / 2 / 2 | 16 / 0 / 2 / 2 |
| No injected range fault | heavy | 19 / 0 / 0 / 1 | 19 / 0 / 0 / 1 |
| Two-step latency, rejected as stale | nominal | 0 / 0 / 5 / 15 | 0 / 0 / 5 / 15 |
| Two-step latency, rejected as stale | heavy | 0 / 0 / 5 / 15 | 0 / 0 / 5 / 15 |
| Range bias −0.08 m | nominal | 16 / 0 / 2 / 2 | 16 / 0 / 2 / 2 |
| Range bias −0.08 m | heavy | 16 / 3 / 0 / 1 | 16 / 3 / 0 / 1 |

No collisions, CBF violations or unchecked CBF steps were observed in these runs. This small sample does not imply zero risk. In the biased heavy scenario, strict-range false-arrival seeds were 2236003, 2236005 and 2236009, at recorded distances 0.2549, 0.2508 and 0.2546 m. The margin change alone is insufficient under correlated vector bias and negative range bias. The runs do not establish how often this happens in deployment, nor independently validate the simulated fault model.

| Output, under `results/research_development/dev/` | SHA-256 |
|---|---|
| `strict_range_long_v2.json` | `ff254a095f0a9f1d32fae2898921d3841667b089837186704d3915295085d2dd` |
| `strict_range_latency_v2.json` | `4c464ab1658aa119542e6a1c0a83a89fb90c4e7001aae7289fae2a7fc3dd1f6b` |
| `strict_range_biased_v2.json` | `b81e7133eb8ceebacf57966db2129d0de75661a38858565490b11db3c0b62c7b` |

Each output records source hashes and episode-level outcomes. Re-run with a new path, selecting the desired fault setting:

```bash
PYTHONPATH=src .venv/bin/python scripts/research/compare_strict_range.py \
  --seed-start 2236000 --n-seeds 20 --max-steps 300 \
  --range-bias-m -0.08 --output NEW_OUTPUT.json
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_3d_strict_range_development.py tests/test_3d_aware_controller.py \
  tests/test_3d_ablation_reproducibility.py tests/test_mujoco_3d_benchmark_integrity.py \
  tests/test_3d_development_summary.py
```

## Priorities and unresolved questions

1. Establish a threat model for biased/correlated range and vector sensors. A range bound based only on nominal Gaussian noise cannot cover an unmodeled systematic bias; investigate independent calibration or an explicitly justified bias bound before evaluating another candidate. Do not claim a guarantee without its assumptions and independent review.
2. Add timestamps and freshness provenance at actual sensor interfaces, with explicit clock, replay and motion-compensation assumptions. The simulation-only rejection rule is not sufficient for real sensors.
3. Diagnose remaining long-budget timeouts and abstentions individually, using traces and predeclared development scenarios. Specify an operational time budget rather than choosing one solely to improve results.
4. Explore asymmetric noise, dropout, moving-target and obstacle conditions with separate development seeds, retaining every assigned outcome and failures. A future independent study must fix design and statistical rules before looking at its outcomes.
5. Preserve existing data and resolve V9-M4 scientific, security and release blockers before any owner decision on Gate B. No production authorization or confirmatory execution was performed.
