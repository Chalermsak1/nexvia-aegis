# V9-M5: sampled dwell and anchor-guided recovery

**Exploratory simulation only.** Gate B remains `GATE_B_NOT_AUTHORIZED`. No V9-M4 Holdout episodes or reserved seeds were accessed, and no production ticket was created. These are not real-robot, safety certification or confirmatory results.

## What the rejection traces show

For the retained `velocity_retry_development_v1.json` run, anchor-margin rejections were not all cases of a noisy anchor near a robot already inside the target. In the nominal range and nominal vector-bias condition, 3 of 7 rejected cases were within 0.25 m at the confirmation step; the other 4 were outside, with distances up to 0.919 m. Under nominal range and heavy vector bias, 3 of 8 were within the radius. Ground truth here is for retrospective analysis, not a controller input. These 12-episode conditions and reused seeds do not establish population proportions. They suggest investigating both recovery from overshoot and confirmation uncertainty, rather than assuming every rejection can be fixed by repeating an anchor check.

## Sampled continuous dwell diagnostic

The new `scripts/research/dwell_diagnostics.py` separately classifies each STOP using truth observed at STOP and the next 50 simulator steps. The exploratory setting is radius 0.25 m, speed at most 0.05 m/s at **every sample**, no previously observed or post-STOP collision, and one second (50 intervals at 0.02 s). It therefore checks 51 sampled positions/speeds, including the decision instant. Missing or invalid samples and incomplete post-STOP horizons are `UNEVALUABLE`; episodes with no STOP are `NO_STOP`. This is a sampled diagnostic, not evidence of continuous behavior between samples or an approved research acceptance rule.

Applying it to the prior 216-record bounded-retry study: **none of its STOP episodes met this sampled dwell condition**. This differs from the earlier one-second proxy, which required low speed only at the last sample. Outputs are retained in `results/research_development/analysis/velocity_retry_dwell_v1.json`. The threshold and one-second duration are development choices requiring prospective justification for any later claim.

## Recovery candidate

`AnchorRecoveryCandidate` is a separate exploratory arm: after the first anchor confirmation is rejected, it may enter one bounded recovery attempt. While recovering, it requests a new anchor each step, checks both vector observations, range and velocity availability, rejects large anchor/range disagreement, and uses the latest simulated anchor to guide a bounded action toward the target. Once the anchor appears sufficiently near the target, it brakes and repeats the stabilized confirmation. Missing or invalid required evidence, a conflict, recovery timeout, or a second rejected confirmation produces abstention. The existing arms retain their previous defaults.

This is not ready for live operation. The base controller's monitor does not update during recovery; the simple range/anchor agreement threshold does not detect all common-mode faults; anchor freshness is assumed from the simulator; repeated anchor readings create sequential selection; the model uses idealized anchor noise and a fixed force/CBF model; and the action path in the simulation harness uses simulated velocity for damping. The candidate has not been validated against an actual robot or safety system. In particular, no confidence, low-risk or certification claim follows from its anchor margin.

## New paired development study

The study assigned seeds 2241000–2241011, nominal/heavy vector bias, strict baseline, stabilized retry, and recovery across four range/anchor/velocity conditions: **288 assigned episodes**, all recorded completed. The recovery arm was tested for at most 500 decision steps and the existing post-STOP brake ran for 50 steps. Anchor noise was independent of vector/range noise in this particular simulation; 30% anchor and 10% velocity dropouts were independent per measurement, not burst failures. Source hashes for selected files matched before and after. Seeds are reused across conditions and the sample is small; per-cell numbers are descriptive only.

Cells show **decision-time true success / false arrival / abstain / timeout; sampled dwell met**, each out of 12:

| Condition | Vector bias | Strict | Stabilized retry | Recovery |
|---|---|---|---|---|
| nominal | nominal | 11 / 0 / 1 / 0; **0** | 4 / 0 / 8 / 0; **0** | 7 / 0 / 5 / 0; **1** |
| nominal | heavy | 11 / 0 / 1 / 0; **0** | 2 / 0 / 10 / 0; **0** | 3 / 0 / 9 / 0; **0** |
| range bias −0.08 m | nominal | 10 / 1 / 1 / 0; **0** | 1 / 0 / 11 / 0; **0** | 1 / 0 / 11 / 0; **0** |
| range bias −0.08 m | heavy | 9 / 2 / 1 / 0; **0** | 1 / 0 / 11 / 0; **0** | 3 / 0 / 9 / 0; **0** |
| range bias, velocity dropout 10% | nominal | 10 / 1 / 1 / 0; **0** | 0 / 0 / 12 / 0; **0** | 1 / 0 / 11 / 0; **1** |
| range bias, velocity dropout 10% | heavy | 9 / 2 / 1 / 0; **0** | 1 / 0 / 11 / 0; **0** | 1 / 0 / 11 / 0; **0** |
| range bias, anchor dropout 30% | nominal | 10 / 1 / 1 / 0; **0** | 1 / 0 / 11 / 0; **0** | 1 / 0 / 11 / 0; **0** |
| range bias, anchor dropout 30% | heavy | 9 / 2 / 1 / 0; **0** | 1 / 0 / 11 / 0; **0** | 1 / 0 / 11 / 0; **0** |

In the nominal condition with nominal vector bias, total anchor queries were 1, 35 and 255 respectively across the 12 strict, retry and recovery episodes. This includes calibration as well as confirmation and recovery; these are query counts, not measured cost or latency. The recovery arm sometimes improved decision-time success but retained high abstention, used many more anchors, and met sampled dwell in only 2 of its 96 assignments across the reused conditions. The strict arm recorded nine decision-time false arrivals across those same 96 assignments; these pooled numbers are not independent statistical estimates. No collision was observed in this sample, including post-STOP steps, which does not establish zero collision risk.

## Evidence and reproduction

Raw file `results/research_development/dev/anchor_recovery_development_v1.json` SHA-256 `f8ff8ca778f7b814af857e93323f0c333f466016981848aba16ec7823ff5db1a`. It contains assigned outcomes, selected source hashes and runtime versions, last four events, recovery events, and post-STOP observations. The dwell result is `results/research_development/analysis/anchor_recovery_dwell_v1.json`. The diagnostic validates the declared assignment grid and rejects duplicates; that grid and the configuration remain self-declared and not externally authenticated. Full controller traces are not retained. Output creation is exclusive, and interrupted execution can leave an incomplete file.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_anchor_recovery.py \
  --seed-start 2241000 --n-seeds 12 --max-steps 500 --post-stop-steps 50 --output NEW_RAW.json
PYTHONPATH=src .venv/bin/python scripts/research/dwell_diagnostics.py NEW_RAW.json \
  --success-radius 0.25 --speed-limit 0.05 --dwell-seconds 1.0 \
  --arms AEGIS_3D_STRICT_RANGE AEGIS_3D_STABILIZED_RETRY AEGIS_3D_ANCHOR_RECOVERY \
  --output NEW_DWELL.json
```

## Next steps

1. Develop a separate candidate that monitors a sustained low-speed interval before STOP, with explicit handling of missing or stale readings; validate with the post-STOP sampled dwell diagnostic. Avoid treating pre-STOP dwell as proof of post-STOP safety.
2. Investigate braking distance and approach geometry to reduce overshoot without depending on high-frequency idealized anchor access. Compare recovery attempts with explicit anchor latency, cost, dropout bursts and faults correlated with range and velocity.
3. Improve the input contract to include timestamp, age, clock status and source identity. Ensure monitoring remains active during recovery; use measured hardware dynamics and ground truth when a platform becomes available.
4. Independently review uncertainty bounds, sequential selection and the prospective definition of stable arrival before making confirmatory or statistical safety claims.
