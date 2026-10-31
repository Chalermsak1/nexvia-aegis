# V9-M5: bounded velocity-dropout retry study

**Exploratory simulation only.** Gate B remains `GATE_B_NOT_AUTHORIZED`; no V9-M4 Holdout, production ticket or real robot was used. Results do not certify safety or show that the prototype is ready for deployment.

## Change and decision rule

The first stabilized prototype abstained immediately when a velocity reading was missing during confirmation. The new `AEGIS_3D_STABILIZED_RETRY` arm permits at most two consecutive missing velocity updates while it commands the existing simulated VERIFY brake, still bounded by the 120-update total stabilization wait. A valid reading resets the consecutive-missing counter. A third consecutive missing reading causes abstention; malformed or nonfinite values still cause immediate abstention. Any anchor delivered while velocity is missing is discarded, and a new anchor must be requested after a fresh low-speed reading. The original stabilized arm defaults to zero retries and remains a separate comparison.

The two-update choice is an unapproved development heuristic, not a guaranteed freshness window. The candidate assumes the simulation harness correctly identifies missing readings and supplies fresh readings. It does not model timestamps, correlated/dropout bursts beyond the simple independent dropout test, or hardware failures. Its single-sample speed and 3D anchor checks are heuristics, not validated statistical bounds.

## Evidence

The new simulation used development seeds 2240000–2240011, two vector biases, three arms, three fault conditions, 400-step maximum and 50 post-STOP braking steps. All 216 assigned episodes completed; recorded source hashes matched before and after execution. Identical seeds pair initial conditions and random streams; decisions change later trajectories. Results below are counts per 12 assigned episodes. The post-STOP proxy requires decision-time true arrival, staying inside the 0.25 m radius for all 50 samples, no post-STOP collision, and final speed ≤0.05 m/s. The speed threshold applies only at the final sample and is not an approved dwell requirement.

Cells show **true success / false arrival / abstain / timeout; post-STOP proxy**:

| Range and velocity condition | Vector bias | Strict baseline | Stabilized, no retry | Stabilized, bounded retry |
|---|---|---|---|---|
| nominal | nominal | 12 / 0 / 0 / 0; **3** | 4 / 0 / 8 / 0; **4** | 4 / 0 / 8 / 0; **4** |
| nominal | heavy | 12 / 0 / 0 / 0; **3** | 4 / 0 / 8 / 0; **4** | 4 / 0 / 8 / 0; **4** |
| range bias −0.08 m | nominal | 11 / 1 / 0 / 0; **1** | 3 / 0 / 9 / 0; **3** | 3 / 0 / 9 / 0; **3** |
| range bias −0.08 m | heavy | 11 / 1 / 0 / 0; **3** | 4 / 0 / 8 / 0; **4** | 4 / 0 / 8 / 0; **4** |
| range bias −0.08 m, velocity dropout 10% | nominal | 11 / 1 / 0 / 0; **1** | 0 / 0 / 12 / 0; **0** | 1 / 0 / 11 / 0; **1** |
| range bias −0.08 m, velocity dropout 10% | heavy | 11 / 1 / 0 / 0; **3** | 0 / 0 / 12 / 0; **0** | 3 / 0 / 9 / 0; **3** |

Across the six conditions, abstention reasons in the no-retry arm were 32 anchor margin, 23 invalid velocity and 2 unavailable anchor/range; the retry arm recorded 47 anchor margin, 1 invalid velocity and 5 unavailable anchor/range. This suggests retry avoids some immediate missing-velocity abstentions but exposes other limits; outcomes are at different times and positions and must not be treated as direct counterfactual labels. Small samples, repeated seeds across conditions and a narrow sensor model limit inference. The observed zero false arrivals for candidate arms is not evidence of zero risk.

Raw file `results/research_development/dev/velocity_retry_development_v1.json` SHA-256 `faaca576605100f8d625bee2545e4a269ad684f69b67663992a089472e213ee5`. The companion summary is `results/research_development/analysis/velocity_retry_development_v1_summary.json`. Files capture the self-declared assignments and selected source hashes, not a complete reproducibility or provenance guarantee.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_velocity_retry.py \
  --seed-start 2240000 --n-seeds 12 --max-steps 400 --post-stop-steps 50 --output NEW_RAW.json
PYTHONPATH=src .venv/bin/python scripts/research/summarize_velocity_retry.py NEW_RAW.json \
  --success-radius 0.25 --output NEW_SUMMARY.json
```

Use new paths: output creation is exclusive; interrupted runs may leave partial files. Synthetic tests cover retry limits, counter reset, anchor discard, invalid values, and assignment completeness.

## Remaining work

Availability remains poor. Investigate anchor margin and the robot's braking trajectory before relaxing any condition. Study burst loss, velocity bias toward zero, correlated position/anchor faults, age and timestamp spoofing, acceleration/actuator uncertainty, and a prospective dwell endpoint. A conservative missing-data policy does not make the brake safe if the robot or obstacle model is wrong. Validate a wider collection of independently designed simulation scenarios and seek appropriate statistical, control and security review; no real-world validation can be claimed without a physical platform and independent ground truth.
