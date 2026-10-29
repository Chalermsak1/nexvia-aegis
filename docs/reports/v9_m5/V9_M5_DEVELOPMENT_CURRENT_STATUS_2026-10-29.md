# V9-M5 3D simulation development — current status, 2026-10-29

**Current evidence version:** v19. Earlier [initial benchmark](V9_M5_3D_DEVELOPMENT_TEST_REPORT_2026-10-29.md), [fault investigation](V9_M5_3D_FAULT_AND_CBF_FOLLOWUP_2026-10-29.md), and [v18 CBF addendum](V9_M5_CBF_FEASIBILITY_ADDENDUM_2026-10-29.md) document the progression and preserve prior observations. This document is the current summary. All work is exploratory; no V9-M4 Holdout, Gate B ticket, reserved seed manifest, or physical robot was used.

## Implementation now present

- Corrected post-step collision/contact accounting and benchmark terminal accounting; removed the hardcoded zero-error conclusion.
- Added separate engineering arms for one-sample range guard, fixed four-sample range window, and range-window plus two 3D vector vetoes. They do not modify the frozen V9-M4 policy. All decision inputs in these arms are simulated observations; ground truth is used only after decisions for scoring.
- Added explicit range dropout, delay, and bias injection, vertical vector-bias testing, and separate random streams for world, sensors, and fault draws.
- Added wall/floor/ceiling braking-distance constraints, an exact active-set projection fallback when fast CBF projection leaves a residual, and explicit reporting of infeasible actuator-limited states. Braking now passes through the same feasibility check instead of bypassing it.
- Added episode-level JSON evidence with exclusive creation, runtime and source hashes, and tests for physical limits, sensor faults, output retention, and numerical projection against an independent SciPy solver.

## Final tests and evidence

```text
.venv/bin/python -m pytest -q
326 passed in 26.85s
```

Six v19 simulation conditions each produced 360 episode rows: six arms × 60 episodes. Nominal, range dropout, range latency, and range-bias conditions use three vector-bias settings × 20 seeds per arm; the vertical-only condition uses one setting × 60 seeds. Seeds repeat across arms and settings. These are **development data**, so no confirmatory test or confidence claim is made.

Cells show `true success / false arrival / accepted` out of 60.

| Condition | Planar V9 + CBF | Four-sample range window | Range window + 3D veto |
|---|---|---|---|
| Nominal seeds 120000 | 15 / **13** / 28 | 10 / **1** / 11 | 6 / 0 / 6 |
| Nominal seeds 130000 | 12 / **11** / 23 | 11 / 0 / 11 | 6 / 0 / 6 |
| Range dropout 20% | 16 / **12** / 28 | 6 / **1** / 7 | 4 / 0 / 4 |
| Range latency 3 steps | 16 / **14** / 30 | 0 / 0 / 0 | 0 / 0 / 0 |
| Range bias −0.20 m | 0 / **21** / 21 | 6 / **6** / 12 | 2 / 0 / 2 |
| Vertical vector bias +0.60 m | 1 / 0 / 1 | 1 / 0 / 1 | 0 / 0 / 0 |

The 3D veto had zero **observed** false arrivals in this limited matrix but accepted very few episodes. The range window accepted more, yet still produced false arrivals. Neither demonstrates a useful and safe operating point. All three AEGIS arms had 0/60 **recorded** simulated collisions per condition; this does not establish a physical or continuous-time guarantee.

### CBF feasibility

| Condition | AEGIS+CBF: residual episodes / exact fallback steps / infeasible steps / unchecked braking steps | CBF_ONLY: residual episodes / infeasible steps |
|---|---|---|
| Nominal 120000 | 0 / 345 / 0 / 0 | 4 / 54 |
| Nominal 130000 | 0 / 743 / 0 / 0 | 7 / 101 |
| Range dropout 20% | 0 / 362 / 0 / 0 | 4 / 54 |
| Range latency 3 steps | 0 / 353 / 0 / 0 | 4 / 54 |
| Range bias −0.20 m | 0 / 207 / 0 / 0 | 4 / 54 |
| Vertical vector bias +0.60 m | 0 / 0 / 0 / 0 | 22 / 321 |

The fallback removes observed residuals in the AEGIS arms for these trajectories. It cannot make an empty actuator-feasible set nonempty; CBF_ONLY enters such states. The benchmark does not assess between-step collision tunneling, model mismatch, or a real-time worst-case deadline. Zero residual in this model is therefore **not** a proof of forward invariance or deployment safety.

## v19 artifact register

| File under `results/v9_m5/dev/` | SHA-256 |
|---|---|
| `v19_nominal120.json` | `cbc92eecb6a18a787a101fa6c3e483fb4ec9863311f2c8e731f52f5284ad3723` |
| `v19_nominal130.json` | `9fd48811ed7a47f1e18d758bf380ed96c63be1cb53076aedc1d765dd4457e15c` |
| `v19_dropout20.json` | `44e7c9216a567852ffd78adf3d5c03f0a9dab4dc781dd38c228f2f471eabff7b` |
| `v19_latency3.json` | `718dc899ff62b116d9ece07c5d730ffaf6d42d4b61edf1db5f58eb10b1bc0a6c` |
| `v19_rangebiasminus20.json` | `9fa19368113bbb6b30a7ae9367531d13e4f36df94242bdf4ab99125074570f7c` |
| `v19_verticalbiasplus60.json` | `65bab1d8e9b0188ec78dd8e9f38fd8226b727264ef473a55b9ac0f86f871da5f` |

All six JSON files record Python `3.12.14`, NumPy `2.5.3`, MuJoCo `3.14.0`, benchmark source SHA-256 `be9ce84d9fa7a0261878e42fb02433e4fbb607b8db64cadc6f9fbbc3c46d36a1`, and world source SHA-256 `184e1dd623fab0128dc5bc4b3219b009534e3c541dbbd707bb55d0ad88a42ac6`. We independently reconciled each summary count to episode rows and confirmed the embedded source hashes match the working tree. Earlier JSON versions remain preserved as development history.

## Open blockers and next admissible work

1. **3D decision design:** the planar V9 STOP handoff has observed false arrivals. The 3D veto avoids those observed errors by abstaining often. A new 3D-aware estimation and arrival rule must be developed on separate development scenarios, with explicit treatment of common-mode corruption and sensor age; it cannot be certified from these reused seeds.
2. **Actuator and timing safety:** empty feasible sets still occur in CBF_ONLY. Specify an emergency controller and safety case for those states, validate the dynamics/model assumptions, and measure worst-case solver latency. This cannot be inferred from test pass counts.
3. **Statistical protocol:** owner and independent statistician must approve the V9-M5 estimands, safety/utility conjuncts, sample size, multiplicity, scenario weights, missingness, and final-data custody **before** a new confirmatory run. No numeric acceptance threshold is invented here.
4. **Physical trials:** blocked by absent hardware. Hardware-in-loop and robot tests need a named platform, ground truth, containment, E-stop, hazard review, and trained operator.
5. **V9-M4 release claim:** independent post-execution source/provenance/statistical discrepancies remain a separate blocker; this development work does not resolve or reauthorize Gate B.

**Disposition:** substantial simulation development and reproducible tests completed. V9-M5 remains **exploratory and release-blocked**. No real-robot validation or V9-M4 certification is claimed.
