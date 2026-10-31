# V9-M5 velocity-gated arrival: development report

**Status: exploratory simulation, not a safety guarantee or real-robot validation. Gate B remains `GATE_B_NOT_AUTHORIZED`; no V9-M4 Holdout or reserved seeds were used.**

## Question and candidate

The previous investigation showed that decision-time arrival and remaining in the target after braking are different outcomes. The new `AEGIS_3D_STABILIZED` exploratory arm wraps the strict 3D controller. When that controller proposes STOP, it commands VERIFY/braking, waits until a simulated velocity observation has norm at most 0.08 m/s, requests a fresh anchor, checks velocity again, then requires a valid range and an anchor whose norm plus `1.645 × sigma` is within 0.25 m. Invalid velocity, unavailable anchor/range, anchor outside the margin, or waiting more than 120 updates causes abstention. If measured speed rises while awaiting the anchor, the anchor is discarded and braking resumes.

The candidate uses a simulated velocity sensor (true simulated velocity plus Gaussian noise with standard deviation 0.02 m/s per axis and optional injected bias/dropout); it does not receive ground truth directly. The simulation environment's existing CBF braking model itself has access to simulated plant state. **0.08 m/s, 120 updates, and the anchor margin are development heuristics, not approved criteria or proven confidence bounds.** A single noisy low-speed sample does not prove the robot is stopped; the anchor check may be affected by bias, missing data, timing, and selection effects. There is no hardware or real sensor validation.

## Experiment and endpoints

Twelve new development seeds 2239000–2239011 were assigned to two vector-bias settings, three arms and five fault settings: 360 assigned episodes, all recorded as completed. Maximum episode length was 400 steps. Following a STOP, the simulated plant was braked for another 50 steps (1 s at 0.02 s timestep). Initial random streams are paired, but actions and subsequent states can differ. Cases reuse seeds and are not independent replications. Source hashes before and after the run match for the recorded subset of files; this is not full environment attestation.

To complement the original decision-time outcome, this report uses an **exploratory stabilized proxy**: at STOP the true distance is within 0.25 m, every recorded post-STOP distance stays within 0.25 m, no post-STOP collision occurs, and final true speed is at most 0.05 m/s. This is an evaluation-only simulator-truth measure. It is not an approved dwell criterion; the speed threshold is checked at the final sample only, not throughout the full second. Execution errors would be counted separately, not treated as successes.

## Results

Cells below show **decision-time true success / false arrival / abstain / timeout; stabilized proxy count**, out of 12 assigned per arm. Vector bias `heavy` is `[0.8, 0.8, -0.3]` m. Velocity bias `[0.08, 0, 0]` m/s and velocity dropout apply to the new candidate's velocity observation; other arms do not use that observation.

| Condition | Vector bias | Strict baseline | Anchor guard | Velocity-gated candidate |
|---|---|---|---|---|
| nominal | nominal | 10 / 0 / 0 / 2; **2** | 5 / 0 / 5 / 2; **1** | 3 / 0 / 6 / 3; **3** |
| nominal | heavy | 10 / 0 / 0 / 2; **4** | 2 / 0 / 8 / 2; **1** | 2 / 0 / 8 / 2; **2** |
| range bias −0.08 m | nominal | 10 / 0 / 0 / 2; **2** | 4 / 0 / 6 / 2; **1** | 2 / 0 / 7 / 3; **2** |
| range bias −0.08 m | heavy | 9 / 1 / 0 / 2; **3** | 1 / 0 / 9 / 2; **0** | 1 / 0 / 9 / 2; **1** |
| range bias and anchor dropout 30% | nominal | 10 / 0 / 0 / 2; **2** | 4 / 0 / 6 / 2; **1** | 1 / 0 / 8 / 3; **1** |
| range bias and anchor dropout 30% | heavy | 8 / 2 / 0 / 2; **2** | 2 / 0 / 8 / 2; **0** | 2 / 0 / 8 / 2; **2** |
| range bias and velocity bias | nominal | 10 / 0 / 0 / 2; **2** | 4 / 0 / 6 / 2; **1** | 2 / 0 / 6 / 4; **2** |
| range bias and velocity bias | heavy | 9 / 1 / 0 / 2; **3** | 1 / 0 / 9 / 2; **0** | 2 / 0 / 6 / 4; **2** |
| range bias and velocity dropout 10% | nominal | 10 / 0 / 0 / 2; **2** | 4 / 0 / 6 / 2; **1** | 0 / 0 / 10 / 2; **0** |
| range bias and velocity dropout 10% | heavy | 9 / 1 / 0 / 2; **3** | 1 / 0 / 9 / 2; **0** | 0 / 0 / 10 / 2; **0** |

Across these 120 candidate assignments, 46 abstentions were labelled anchor outside margin, 20 invalid velocity, 8 unavailable anchor/range, and 4 stabilization timeout. In nominal conditions with nominal vector bias, six strict decision-time true successes paired with candidate abstentions and one with candidate timeout; three paired with candidate true successes. These decision-time classifications are made at different times and positions, and must not be interpreted as a counterfactual causal classification. No candidate false arrival was observed, but zero in this small dependent sample does not establish zero risk. The prototype does not yet satisfy a reasonable availability objective and should not replace a baseline.

## Evidence and reproducibility

Raw evidence: `results/research_development/dev/stabilized_arrival_development_v1.json`, SHA-256 `1e956e01a84e441bc252d79e840035e4ffbe13a9de3860f7306e785c4bedc636`. The retained summary is `results/research_development/analysis/stabilized_arrival_development_v1_summary.json`. The summary checks the declared assignment grid, uniqueness, outcomes, source-hash consistency and post-STOP length; the supplied radius and declared design are not independently authenticated. Last four control events and all post-STOP samples are retained for each applicable record; complete step traces are not retained by this study.

The candidate and benchmark files were subsequently changed to add a separate bounded-retry arm. The original arm retains zero retries by default, but the current files no longer match this run's recorded hashes; rerunning the command uses the current sources and is not an exact source-level reproduction of the retained run.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_stabilized_arrival.py \
  --seed-start 2239000 --n-seeds 12 --max-steps 400 --post-stop-steps 50 --output NEW_RAW.json
PYTHONPATH=src .venv/bin/python scripts/research/summarize_stabilized_arrival.py NEW_RAW.json \
  --success-radius 0.25 --output NEW_SUMMARY.json
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_summarize_stabilized_arrival.py tests/test_stabilized_arrival_candidate.py \
  tests/test_summarize_post_stop.py tests/test_post_stop_diagnostic.py \
  tests/test_anchor_arrival_candidate.py tests/test_3d_strict_range_development.py \
  tests/test_3d_aware_controller.py tests/test_3d_ablation_reproducibility.py \
  tests/test_mujoco_3d_benchmark_integrity.py tests/test_3d_development_summary.py
```

Outputs are created exclusively; interrupted runs may leave partial files. Synthetic tests exercise state transitions, missing velocity, dropout, anchor rejection, speed rising while waiting, timeouts, and input summary completeness. The full repository suite has not been established in this environment.

## Next investigations

1. Examine individual anchor rejection and braking traces. Evaluate bounded recovery or a limited fresh-velocity retry policy as a **separate candidate**, with predeclared limits and evidence, while keeping fail-closed behavior for stale and invalid readings. Do not tune on any confirmatory dataset.
2. Add velocity timestamp, delay, clock and calibration fault models; test bias toward low reported speed and correlated faults. `[0.08, 0, 0]` covers only one fixed direction.
3. Define a prospective dwell endpoint including speed over the entire dwell interval, position, collision, missing readings, and timing; the current proxy is not that endpoint. Investigate dynamics across multiple robot models and sensor configurations.
4. Review sequential-selection and 3D uncertainty assumptions with an independent statistician before any confidence or safety claim. Seek hardware and a measured ground truth system before drawing real-world conclusions.
