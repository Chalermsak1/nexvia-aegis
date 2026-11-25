# Standalone Research Benchmark: Tri-Sensor Self-Verification & Fault Isolation

> **Status — Run #1 (`tri_sensor_maze_v1`):** Standalone exploratory simulation benchmark (**simulation-only**; decoupled from core runtime / LIVE01; no real-hardware validation or Gate B claim).

## Overview

This standalone research module evaluates a three-sensor self-verification layer (`TriSensorVerifier`) operating inside the 3D subterranean maze environment (`aegis.navigation.frontier_exploration.FrontierExplorationEngine`) with **zero ground-truth leakage**. Three heterogeneous simulated localization channels (`S1_VIO`, `S2_LIDAR`, `S3_UWB`) cross-check one another to:

1. Reject physically invalid readings (`NaN` / `Inf` / out-of-bounds) in `0` steps (`SENSOR_BLACKOUT`).
2. Detect **retimestamped-freeze** faults (fresh metadata with static physical readings) via cross-channel motion consistency within `1` step.
3. Isolate gradual drift, heavy drift, sudden bias, and outlier bursts using pairwise normalized parity residuals ($z_{ij}$) combined with deterministic **Page CUSUM** ($k = 1.65$, $h = 4.0$). *(Note: Page CUSUM reflects at zero and is **not** a nonnegative supermartingale or Ville-anytime-valid.)*
4. Strictly exclude quarantined sensor readings from both `display_pos` and `control_pos` (logging excluded values separately in `audit_quarantine_events.jsonl`), fuse healthy sensors via inverse-variance weighting, and **fail closed** (`ABSTAIN_SAFE_STOP`) under simultaneous dual-sensor failure.

## Run #1 Summary (`20 Scenarios x 3 Arms = 60 Maze Episodes`, 45 steps/episode = 900 total ticks/arm)

| Arm | Mean RMSE | Max RMSE | Worst Single-Tick | Fault-Window RMSE | Estimates / Abstentions | Simulation Collision Ticks | Mean Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `NAIVE_AVG` | `0.6037 m` | `1.7375 m` | `3.0365 m` | `0.8045 m` | `900 / 0` | `111` | `57.7%` |
| `TWO_SENSOR_MIN_SIGMA` | `0.7039 m` | `4.4080 m` | `7.3839 m` | `0.9232 m` | `900 / 0` | `65` | `59.4%` |
| `TRI_SENSOR_VERIFIER` | **`0.0413 m`** | **`0.0540 m`** | **`0.1131 m`** | **`0.0462 m`** | **`868 / 32`** | **`0`** | **`61.7%`** |

* **RMSE Reliability Accounting:** Each summary row explicitly records `estimate_count` (estimates included in RMSE) and `abstain_steps` (fail-closed abstentions excluded from RMSE, e.g., `13` estimates / `32` abstentions on `19_DUAL_S1_DRIFT_S2_FREEZE`). Whenever `estimate_count == 0`, RMSE and max display error are reported explicitly as `"Unavailable"` rather than `0.0`.
* **Collision Metric Semantics:** Collision counts are reported as **`simulation_collision_ticks`** (per-step simulated obstacle/wall boundary overlap ticks across the 45-step episode, not distinct physical crash events).
* **Mean Fault Isolation Accuracy:** `96.1%` (`557` faulty readings excluded; `626` separated audit events; `32` fail-closed safe-stop ticks on `DUAL_S1_DRIFT_S2_FREEZE`).
* **Preserved Run #1 Evidence:** [`logs/tri_sensor_maze_v1/`](logs/tri_sensor_maze_v1/) is preserved as the original Run #1 baseline record. All repeat runs default to a new unique timestamped folder and refuse to overwrite existing run directories (`FileExistsError`), recording `planner_provenance` (git commit & SHA-256 of `frontier_exploration.py`), `dependencies` versions, and per-scenario `scenario_seeds` in `experiment_config.json`.

## Known Limitations & Retained Counterexamples (Run #1)

1. **CUSUM Spike-Poisoning on `OUTLIER_BURSTS`:** False alarm rate reached `50.0%–69.2%` on `OUTLIER_BURSTS` (vs. `0.0%` on all other 17 scenarios) because large `2.4 m` single-tick spikes saturate Page CUSUM near its cap (`40.0`). Planned fix in Run #2: decouple spike gating from the CUSUM drift accumulator via Winsorized clipping.
2. **Gradual Drift Onset Latency:** Slow linear drift (`0.030 m/step`) required `5–6` steps to cross `h = 4.0` (`81.8%` fault-window isolation; max error `<= 0.113 m`).
3. **Common-Mode Failure & Simulation Scope:** Simultaneous correlated drift across 2+ sensors in the same direction is not mitigated in Run #1; all experiments use deterministic synthetic noise and fault injection.

## Reproduction Steps (from Repository Root)

```bash
# 1. Run standalone unit tests (20 tests: fault isolation, recovery probation, unavailable RMSE, no-overwrite provenance)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run pytest -v -p no:cacheprovider \
  research/tri_sensor_verification/tests/test_tri_sensor_verifier.py

# 2. Re-run the full 20-scenario x 3-arm 3D maze benchmark into a NEW timestamped folder (~45s; never overwrites Run #1)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run python -m research.tri_sensor_verification.maze_experiment_runner

# 3. Regenerate 300-DPI figures and 5-tab HTML dashboard for the latest run
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run python -m research.tri_sensor_verification.plot_results
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. uv run python -m research.tri_sensor_verification.build_dashboard
```
