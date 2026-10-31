# Recovery progress diagnosis

Exploratory simulation only. Gate B remains `GATE_B_NOT_AUTHORIZED`. No confirmatory endpoint or frozen policy was changed.

## Evidence and interpretation

The new `scripts/research/diagnose_recovery_progress.py` validates the development ledger and reports distance changes and mode/decision occupancy from incremental pre-physics observations. It retains assignment and execution status, distinguishes the last pre-physics observation from terminal plant state, and makes no invented progress/safety threshold or causal classification. Output creation is exclusive. Missing event evidence is shown as unavailable; ERROR and INCOMPLETE executions retain their status.

Across the existing 32 development assignments (seeds 2252000–2252001), observed total distance reduction was 2.01619–4.10136 m. In the last 50 observations, reduction was -0.19905 to 0.00002318 m. Sixteen episodes remained NOMINAL; sixteen included ACTIVE_PROBING and CALIBRATED_APPROACH. These are correlated development trajectories, not 32 independent trials of progress probability.

A deliberately selected diagnostic repeat used seed 2252000, nominal range, both vector biases and both arms, extending the horizon from 350 to 1,200 steps. The manifest explicitly declares this four-assignment subset. All four completed execution but timed out scientifically; all ended at approximately 3.4454503 m from target, with zero distance reduction in the final 50 observations. The 4,800 recorded decision events pass analyzer validation. Longer duration did not resolve this specific stall. This is a repeated diagnostic seed, not a fresh independent experiment.

Raw extended-horizon ledger: `results/research_development/dev/recovery_progress_horizon_diagnostic_v1.jsonl`, SHA-256 `c73446f1d111546145d532d34ca998731615a98b30e5a6925acf771586f0618b`. Diagnostic outputs are in `results/research_development/analysis/`, named `recovery_monitor_step_ledger_v2_progress.json`, `recovery_monitor_step_trigger_diagnostic_v2_progress.json`, and `recovery_progress_horizon_diagnostic_v1_progress.json`. Historical inputs were preserved.

## Isolated mechanism

For the nominal-bias final decision, position is approximately [-0.55565277, -0.55565277, 0.35]. Recomputing the current CBF from that recorded state with its existing static obstacle geometry and desired action minus velocity damping gives desired force [2, 2, 0.0419378], projected force approximately [-2.22e-16, -2.22e-16, 6.73e-16], active barrier, feasible constraints and residual 3.52e-17. Clearance from the central obstacle surface after robot radius is 0.15000000000000113 m, the configured margin.

Relevant source: `src/aegis/v9/controller_3d.py:372` onward constructs proportional navigation and clips each axis at the force limit (line 375). `src/aegis/env/mujoco_3d_cbf.py:309` defines the obstacle geometry and line 423 onward applies the CBF. `experiments/benchmark_physical_3d_cbf.py:535` onward applies velocity damping before filtering. The exact source maps for executed runs are embedded in their ledgers; current files may subsequently evolve.

The reproduced feasible near-zero projection explains this trajectory's local stall. Axis saturation makes the requested horizontal components identical despite an unequal target direction. It is a plausible contributor to head-on symmetry; a controlled saturation ablation is still required to establish causality. This does not explain every timeout, including seed 2252001 with a different endpoint. A barrier feasibility result does not ensure navigation progress.

## Next development experiment

1. Preserve current baseline and add a separately named exploratory navigation candidate that chooses a route around static obstacles, retaining the existing CBF.
2. Test direction-preserving force scaling independently of routing, because changing both simultaneously would confound attribution.
3. Specify a development grid before execution: baseline, force-scaling only, routing only, combined; matched worlds, horizons, noise and fault settings. Keep all timeouts, abstentions and failures in denominators.
4. Verify route clearance, unreachable goals, oscillation, planner failure, missing observations and stale observations synthetically before simulation. A planner's use of simulator-known geometry must remain explicit; it is not perception validation.
5. Include progress, actual post-action force, CBF feasibility and residuals, collision/contact, and physical post-decision behavior. Current pre-physics events do not demonstrate actuation completion. Independently review safety assumptions before external claims.

The current work adds diagnosis and case-subset selection only. It does not alter navigation gains, CBF constraints, the recovery monitor or V9-M4 statistical rules. Owner authorization and scientific/security release blockers remain outstanding.
