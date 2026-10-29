# V9-M5 3D simulation development follow-up — 2026-10-29

**Status:** exploratory engineering evidence, not preregistered or confirmatory. No physical robot is available. This report supplements the earlier [development test report](V9_M5_3D_DEVELOPMENT_TEST_REPORT_2026-10-29.md); its earlier JSON files remain preserved. V9-M4 frozen evaluation code, results, tickets, and Gate B state were not changed.

**Base repository:** `origin/main` at `5055526f83846d1ce7a0e76058fc27407e2ff06f`; work is on local `codex/v9-m5-development` with uncommitted changes. Final code identity must be assigned if this development work is later published.

## Development implemented

1. Added a fixed four-observation range confirmation window after the planar V9 core requests `STOP`. The robot brakes during confirmation. This uses only simulated sensor observations for its decision; ground truth scores the terminal result afterward. It is an engineering heuristic, not a statistical guarantee.
2. Added a separate 3D vector veto arm. It combines the four range observations with the two 3D vector-sensor histories. A gross disagreement blocks acceptance. The margin is a heuristic and cannot defend against arbitrary coordinated sensor corruption.
3. Added range dropout, fixed range latency, range bias, and explicit 3D vector-bias options to the CLI. World initialization, sensor noise, and fault injection now use separate `SeedSequence` random streams, avoiding a fault draw changing the world sample. The same seed and bias are used across arms; each JSON file records the exact settings and source hashes.
4. Added CBF residual and unchecked-braking diagnostics. The current filter is an iterative halfspace projection followed by actuator clipping, **not an exact QP solver**. Its braking path bypasses CBF checking. Added a wall/floor/ceiling stopping-distance envelope and monitored upper Z boundary. If no actuator-limited action meets a constraint, the residual is reported; the code does not claim to restore feasibility.
5. Added synthetic regression tests for STOP veto, missing/stale range, contradictory range/vector evidence, output completeness/no-overwrite, post-step contact, a recoverable wall approach, and an actuator-infeasible state.

## Final executed verification

```text
.venv/bin/python -m pytest -q
324 passed in 31.19s
```

The final matrix used six arms × 60 episodes per condition = **360 episode rows per JSON file**, six conditions = **2,160 episode rows**. The nominal/dropout/latency/range-bias conditions used three vector-bias scenarios × 20 seeds (`120000–120019`). A second nominal cohort used `130000–130019`. The vertical-only condition used one `[0,0,+0.6]` m bias × 60 seeds (`120000–120059`). These are development seeds; no V9-M4 reserved seeds or Holdout outcomes were accessed. Reused seeds and scenario blocks make naive independent-binomial inference inappropriate.

For each condition below, cells show `true success / false arrival / accepted / CBF-residual episodes` out of 60. Simulated collisions were 0/60 for all four AEGIS arms in these conditions; that observation does not establish continuous-time or physical safety.

| Condition | Planar V9 + CBF | One-sample range guard | Four-sample range window | Four-sample range + 3D veto |
|---|---|---|---|---|
| Nominal 120000 | 15 / 13 / 28 / 6 | 2 / 0 / 2 / 6 | 10 / **1** / 11 / 6 | 6 / 0 / 6 / 6 |
| Nominal 130000 | 13 / 10 / 23 / 10 | 4 / 0 / 4 / 10 | 12 / 0 / 12 / 10 | 6 / 0 / 6 / 10 |
| Range dropout 20% | 16 / 12 / 28 / 7 | 4 / 0 / 4 / 7 | 6 / **1** / 7 / 7 | 4 / 0 / 4 / 7 |
| Range latency 3 steps | 16 / 14 / 30 / 7 | 0 / 0 / 0 / 7 | 0 / 0 / 0 / 7 | 0 / 0 / 0 / 7 |
| Range bias −0.20 m | 0 / 21 / 21 / 3 | 0 / **8** / 8 / 3 | 6 / **6** / 12 / 3 | 2 / 0 / 2 / 3 |
| Vertical vector bias +0.60 m | 1 / 0 / 1 / 0 | 1 / 0 / 1 / 0 | 1 / 0 / 1 / 0 | 0 / 0 / 0 / 0 |

**Interpretation:** the one-sample guard has very poor utility. The four-sample window improves acceptance in nominal simulation but still made one false arrival in one nominal cohort and one in the dropout condition; it fails badly under negative range bias. The 3D veto removed observed false arrivals in this matrix, including the biased-range condition, but accepted only 2–6 of 60 episodes per condition and none under latency or vertical-only bias. **No tested arm meets a demonstrated joint safety-and-utility target.** A target has not yet been approved, so no formal pass/fail hypothesis verdict is issued.

### CBF diagnostic finding

The CBF residual exceeded `1e-8` in multiple episodes despite zero recorded collisions; the nominal AEGIS arms had 6/60 and 10/60 residual episodes. The `CBF_ONLY` arm had 14/60 residual episodes in the 120000 nominal cohort. In a synthetic actuator-limited state near a wall, no command within ±2 N can satisfy the displayed HOCBF inequality. This shows that zero observed contact is not proof of constraint feasibility or forward invariance. The AEGIS arms also had numerous **unchecked braking steps** (for example 141 steps for the fixed-window arm in nominal 120000). These paths require a control and safety-case redesign before a guarantee is claimed.

## Evidence files and hashes

| Condition | JSON evidence | SHA-256 |
|---|---|---|
| Nominal 120000 | `results/v9_m5/dev/v17_nominal120.json` | `963794c490b43a45f7bc520a607034ce805e9b77a8345763bdbe68479475ec04` |
| Nominal 130000 | `results/v9_m5/dev/v17_nominal130.json` | `dd4eba6b6c247c558a11b52db54c812069e8bb3a70d19f6f738322dd9de68aee` |
| Dropout 20% | `results/v9_m5/dev/v17_dropout20.json` | `3894b5f3c089b73615a510afd157a82d255c63a85f3b01b66bb91b9a5e4bd881` |
| Latency 3 steps | `results/v9_m5/dev/v17_latency3.json` | `a1575c65c176a768aa20527d5fdade58f4b7eed39bfb0ff656dad540f16820c6` |
| Range bias −0.20 m | `results/v9_m5/dev/v17_rangebiasminus20.json` | `f5fa66e64084da6e3d3462a711ca970a7e711db87f7eece7173403ebf93dd68d` |
| Vertical bias +0.60 m | `results/v9_m5/dev/v17_verticalbiasplus60.json` | `8751564284239bdc4dc8a2dfffb9bff60aaf3be0e10c9f407e9a6c1d51ca3a86` |

Each v17 JSON records Python `3.12.14`, NumPy `2.5.3`, MuJoCo `3.14.0`, benchmark source SHA-256 `7e26d62b975e17dd08366db9294ee2867ca0c38db3c01bc34e46a742d43a6395`, and world source SHA-256 `c4bb9eec5a80f7f51d499071727451561db828f10dab3ee0bca91b2d0f7d9936`. Evidence files use exclusive creation and have not been overwritten. Earlier versions in `results/v9_m5/dev/` are retained as intermediate development evidence, not substituted for v17.

## Remaining blockers and concrete next development

1. **3D-aware arrival decision:** replace the planar `STOP` handoff with a separately specified 3D estimation/verification interface. It must handle common-mode vector bias, biased/absent range, vertical error, and explicit sensor-age metadata. Select the policy using development data, then freeze it before any fresh confirmatory set.
2. **Useful coverage:** specify a joint safety-and-utility target with an independent statistician. The current veto's near-zero acceptance makes a zero-error observation uninformative for useful deployment.
3. **CBF feasibility:** design an actuator-aware control law and exact feasibility handling, including braking and obstacle constraints; independently verify continuous-time and discrete-step assumptions. Until then, the code reports residuals rather than claiming invariance.
4. **Hardware-in-loop and robot trials:** unavailable because no physical robot is currently provided. A named platform, sensor timestamps, ground truth, containment, E-stop, hazard review, and approved protocol are required before those stages.
5. **Scientific governance:** complete the V9-M4 source/provenance audit separately. Register a fresh V9-M5 protocol, frozen code, scenario weights, sample size, missing-evidence rules, and acceptance criteria before a confirmatory claim. Development observations here must not be relabeled as Holdout.

**Disposition:** engineering progress and failure modes documented; **release readiness remains blocked**. This work does not authorize Gate B, certify V9-M4, or validate a real robot.
