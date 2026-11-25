# Standalone Research Benchmark: Tri-Sensor Self-Verification & Fault Isolation

> **Status — Run #1 (`tri_sensor_maze_v1`):** Standalone exploratory simulation benchmark (**simulation-only**; decoupled from core runtime / LIVE01; no real-hardware validation or Gate B claim).

## Overview

This standalone research module evaluates a three-sensor self-verification layer (`TriSensorVerifier`) operating inside the 3D subterranean maze environment (`aegis.navigation.frontier_exploration.FrontierExplorationEngine`) with **zero ground-truth leakage**. Three heterogeneous simulated localization channels (`S1_VIO`, `S2_LIDAR`, `S3_UWB`) cross-check one another to:

1. Reject physically invalid readings (`NaN` / `Inf` / out-of-bounds) in `0` steps (`SENSOR_BLACKOUT`).
2. Detect **retimestamped-freeze** faults (fresh metadata with static physical readings) via cross-channel motion consistency within `1` step.
3. Isolate gradual drift, heavy drift, sudden bias, and outlier bursts using pairwise normalized parity residuals ($z_{ij}$) combined with deterministic **Page CUSUM** ($k = 1.65$, $h = 4.0$). *(Note: Page CUSUM reflects at zero and is **not** a nonnegative supermartingale or Ville-anytime-valid.)*
4. Strictly exclude quarantined sensor readings from both `display_pos` and `control_pos` (logging excluded values separately in `audit_quarantine_events.jsonl`), fuse healthy sensors via inverse-variance weighting, and **fail closed** (`ABSTAIN_SAFE_STOP`) under simultaneous dual-sensor failure.

## Run #1 Summary (`20 Scenarios x 3 Arms = 60 Maze Episodes`)

| Arm | Mean RMSE | Max RMSE | Worst Single-Tick | Fault-Window RMSE | Maze Collisions | Mean Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `NAIVE_AVG` | `0.6037 m` | `1.7375 m` | `3.0365 m` | `0.8045 m` | `111` | `57.7%` |
| `TWO_SENSOR_MIN_SIGMA` | `0.7039 m` | `4.4080 m` | `7.3839 m` | `0.9232 m` | `65` | `59.4%` |
| `TRI_SENSOR_VERIFIER` | **`0.0413 m`** | **`0.0540 m`** | **`0.1131 m`** | **`0.0462 m`** | **`0`** | **`61.7%`** |

* Mean fault isolation accuracy: **`96.1%`** (`557` faulty readings excluded; `626` separated audit events; `32` fail-closed safe-stop steps on `DUAL_S1_DRIFT_S2_FREEZE`).
* Recorded Run #1 evidence: [`logs/tri_sensor_maze_v1/RUN_01_SUMMARY.txt`](logs/tri_sensor_maze_v1/RUN_01_SUMMARY.txt), [`logs/tri_sensor_maze_v1/summary_table.csv`](logs/tri_sensor_maze_v1/summary_table.csv), [`logs/tri_sensor_maze_v1/audit_quarantine_events.jsonl`](logs/tri_sensor_maze_v1/audit_quarantine_events.jsonl), [`logs/tri_sensor_maze_v1/figures/`](logs/tri_sensor_maze_v1/figures/), and [`logs/tri_sensor_maze_v1/dashboard.html`](logs/tri_sensor_maze_v1/dashboard.html).

## Known Limitations & Retained Counterexamples (Run #1)

1. **CUSUM Spike-Poisoning on `OUTLIER_BURSTS`:** False alarm rate reached `50.0%–69.2%` on `OUTLIER_BURSTS` (vs. `0.0%` on all other 17 scenarios) because large `2.4 m` single-tick spikes saturate Page CUSUM near its cap (`40.0`). Planned fix in Run #2: decouple spike gating from the CUSUM drift accumulator via Winsorized clipping.
2. **Gradual Drift Onset Latency:** Slow linear drift (`0.030 m/step`) required `5–6` steps to cross `h = 4.0` (`81.8%` fault-window isolation; max error `<= 0.113 m`).
3. **Common-Mode Failure & Simulation Scope:** Simultaneous correlated drift across 2+ sensors in the same direction is not mitigated in Run #1; all experiments use deterministic synthetic noise and fault injection.

## Reproduction Steps (from Repository Root)

```bash
# 1. Run standalone unit tests (14 tests)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run pytest -v -p no:cacheprovider \
  research/tri_sensor_verification/tests/test_tri_sensor_verifier.py

# 2. Re-run the full 20-scenario x 3-arm 3D maze benchmark (~45s)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run python -m research.tri_sensor_verification.maze_experiment_runner

# 3. Regenerate 300-DPI figures and 5-tab HTML dashboard
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run python -m research.tri_sensor_verification.plot_results
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run python -m research.tri_sensor_verification.build_dashboard
```
