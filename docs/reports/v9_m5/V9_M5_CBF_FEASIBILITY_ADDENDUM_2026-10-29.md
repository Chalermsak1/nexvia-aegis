# V9-M5 CBF feasibility and final development matrix — 2026-10-29

**Historical snapshot:** exploratory v18 3D MuJoCo development, following [the fault and CBF report](V9_M5_3D_FAULT_AND_CBF_FOLLOWUP_2026-10-29.md). The [current v19 status](V9_M5_DEVELOPMENT_CURRENT_STATUS_2026-10-29.md) supersedes this snapshot after the braking path was brought through CBF feasibility checks. It does not change V9-M4 frozen artifacts, Gate B, or release status. No physical robot was available.

## What changed after the v17 matrix

The fast iterative halfspace projection occasionally returned a control that violated a CBF inequality after actuator clipping. `ControlBarrierFilter3D` now checks its residual and, if nonzero, enumerates feasible intersections of up to three active planes in the 3D control space, including the actuator box. This solves the small convex projection problem when a feasible point exists. A cheap single-halfspace/box check rejects a physically impossible constraint before enumeration. The filter exposes `cbf_qp_feasible`, `cbf_projection_method`, and residual in the step state. `UNCHECKED_BRAKING` remains explicit because the braking branch does not run the constraint projection.

The independent numerical regression test compares 12 randomly generated feasible 3D polytopes against SciPy SLSQP. Synthetic tests also cover an actuator-infeasible wall state. The full repository suite passed:

```text
.venv/bin/python -m pytest -q
326 passed in 29.51s
```

The v18 matrix used the same six condition definitions and six arms as the v17 matrix, producing 360 episode rows per file. Every v18 file records source and runtime identities, scenario/bias settings, per-episode outcomes, fallback counts, infeasible counts, and unchecked braking counts. The test script independently reconciled summary counts to every episode row and source SHA-256 to the current source bytes.

## Main CBF feasibility results

| Condition | CBF_ONLY: residual episodes / exact fallback steps / infeasible steps | AEGIS+CBF: residual episodes / exact fallback steps / infeasible steps / unchecked braking steps |
|---|---|---|
| Nominal seeds 120000 | 4 / 807 / 54 | 0 / 345 / 0 / 29 |
| Nominal seeds 130000 | 7 / 1384 / 101 | 0 / 743 / 0 / 26 |
| Range dropout 20% | 4 / 807 / 54 | 0 / 362 / 0 / 39 |
| Range latency 3 steps | 4 / 807 / 54 | 0 / 353 / 0 / 30 |
| Range bias −0.20 m | 4 / 807 / 54 | 0 / 207 / 0 / 36 |
| Vertical vector bias +0.60 m | 22 / 0 / 321 | 0 / 0 / 0 / 60 |

The exact fallback eliminated observed CBF residuals in the AEGIS arms of this matrix; it did **not** make physically infeasible states feasible. CBF_ONLY still entered such states. Zero residual on checked steps does **not** prove forward invariance: the braking path is unchecked, sampled trajectories can miss between-step events, the world model is approximate, and no real-time deadline analysis has been completed. The fallback also increased the nominal 120000 benchmark wall-clock time from roughly 7 seconds to 22 seconds; a 50 Hz controller claim needs per-step latency measurement on target hardware.

## Final observed policy outcomes

Cells show `true success / false arrival / accepted` out of 60 for the three AEGIS variants most relevant to the next design decision. Simulated collision count was 0/60 for these arms in every listed condition.

| Condition | Planar V9 + CBF | Four-sample range window | Four-sample range + 3D veto |
|---|---|---|---|
| Nominal 120000 | 15 / 13 / 28 | 10 / **1** / 11 | 6 / 0 / 6 |
| Nominal 130000 | 12 / 11 / 23 | 11 / 0 / 11 | 6 / 0 / 6 |
| Range dropout 20% | 16 / 12 / 28 | 6 / **1** / 7 | 4 / 0 / 4 |
| Range latency 3 steps | 16 / 14 / 30 | 0 / 0 / 0 | 0 / 0 / 0 |
| Range bias −0.20 m | 0 / **21** / 21 | 6 / **6** / 12 | 2 / 0 / 2 |
| Vertical vector bias +0.60 m | 1 / 0 / 1 | 1 / 0 / 1 | 0 / 0 / 0 |

The 3D veto removed false arrivals **observed in these development runs** but has poor utility and fails closed under latency and vertical bias. The range window is more useful but still has observed false arrivals, especially when the range sensor underreads. Neither is ready for a confirmatory or physical safety claim. Further threshold tuning on these same seed sets would only overfit development data.

## Final v18 evidence integrity

| Evidence file under `results/v9_m5/dev/` | SHA-256 |
|---|---|
| `v18_nominal120.json` | `719b2402bcab9837e73754b4819b43267d2e26d92e7673ea2135e9ddca941c7e` |
| `v18_nominal130.json` | `583f07643c5eea08ddcd9b76d74b95d6c74d582f2930fada7eebf9163aeead13` |
| `v18_dropout20.json` | `71d28ec6377f8afeed406388c683879205a667fd1dee302b28502ba8ad5a6194` |
| `v18_latency3.json` | `c6ac500537f6e557daa43d3ccc9b31ae9fc99994ddbf6642695539d1136f28bc` |
| `v18_rangebiasminus20.json` | `3e08ed6bf63297e73776ba21e2029fc95f2d483220e02e2eb5093fd82bc3b5ba` |
| `v18_verticalbiasplus60.json` | `a0c44de6eee6fa0acdc4400b8c6afbac5631a995506884780d5efddeb863d66d` |

All six files record Python `3.12.14`, NumPy `2.5.3`, MuJoCo `3.14.0`, benchmark source SHA-256 `1583f490e363f105168e3aec053a84ec54e9f7a6b5401c1ba2daccec72257c2d`, and world source SHA-256 `cc63352bd93ee60945fa7bb71c9198d6eae0d01b50c607ded7d2c9373fbd6c41`. The files are exclusively created, not overwritten. Earlier v15–v17 and initial JSON artifacts remain in `results/v9_m5/dev/` as historical development evidence.

## What remains before further claims

1. **Safety control:** redesign the braking path to meet the same feasibility/accounting contract; define behavior when the control polytope is empty; verify obstacle, boundary, contact, and between-step safety under a model with actuator limits; measure solver worst-case latency against a real control deadline.
2. **3D arrival and utility:** replace the planar STOP handoff with a specified 3D estimation and verification architecture, using sensor timestamps and explicit treatment of correlated faults. Select it on development data, then freeze before any new final set. Do not label abstention-heavy zero-error runs safe-and-useful.
3. **Research governance:** independently approve V9-M5 estimands, thresholds, sample size, multiplicity, missing-evidence and failure rules, and custody of fresh confirmatory scenarios. Existing development data cannot be repurposed as a Holdout.
4. **Physical stage:** blocked by absent hardware. A platform, ground-truth system, containment, emergency stop, hazard review, and operator protocol are necessary before HIL or robot trials.

**Disposition:** source defects corrected and testable, failure modes exposed, development remains exploratory. No V9-M5 release candidate or real-robot validation is established.
