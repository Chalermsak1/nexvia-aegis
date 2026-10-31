# V9-M5 exploratory sustained-speed stop

**Status: simulation development only.** Gate B remains `GATE_B_NOT_AUTHORIZED`. No V9-M4 Holdout or reserved seed contents were accessed, and no production ticket was created. These observations are not real-robot validation or a safety certificate.

## Candidate

`SustainedStopCandidate` builds on the exploratory anchor-recovery arm. After a base STOP proposal it brakes and requires 20 consecutive valid simulated velocity observations of norm ≤0.05 m/s before requesting an anchor. At the 0.02 s simulated update interval, 20 readings span 19 intervals (0.38 s); the subsequent anchor confirmation is another update. The speed must also be below the limit on the anchor step. Higher speed or missing velocity resets the count; missing velocity is subject to the inherited bounded retry policy. The per-attempt wait limit is 220 updates. If confirmation rejects the anchor, the inherited bounded recovery may be attempted once. The speed rule monitors velocity before STOP; position at each pre-STOP sample is not independently verified.

This is a **heuristic**, not a confidence statement: sensor noise, bias, stale or repeated readings, clock errors, and correlated faults can defeat it. The harness assumes one fresh velocity observation per step and simulates it as `velocity_scale × true velocity + fixed bias + Gaussian noise`, standard deviation 0.02 m/s per axis. The controller receives the simulated observation, not truth; the environment's existing brake/CBF and damping use simulated plant state. The anchor is separately simulated from truth plus noise, an assumption that does not establish real sensor independence. Recovery's base controller monitor is not updated while recovering. None of these parameters is an approved V9-M4 rule.

## Development experiment

The retained run assigned 12 fresh development seeds 2242000–2242011, two vector-bias settings, three arms and five fault conditions: **360 episodes**, with no recorded execution errors. Each episode had up to 650 steps, followed by 50 simulated braking steps after STOP. The velocity underreport condition sets `velocity_scale=0.25`, so observed velocity, before noise, is one quarter of true velocity; it is one artificial fault model, not a claim about a real sensor. Seeds recur across fault cases, so pooled totals are descriptive, not independent samples. Actions can diverge across arms despite matched initial streams. Selected source hashes match before and after the run, but do not cover all dependencies.

The independent-of-controller post-STOP diagnostic uses simulated truth: at the decision and all 50 subsequent samples, true distance ≤0.25 m and true speed ≤0.05 m/s, with no prior or post-STOP collision. This sampled one-second criterion was selected for exploration, is not a registered success criterion, and does not prove behavior between samples. No STOP is reported separately; missing evidence is unevaluable.

Each cell below shows **decision-time true success / false arrival / abstain / timeout; sampled dwell met**, out of 12:

| Condition | Vector bias | Strict | Anchor recovery | Sustained stop |
|---|---|---|---|---|
| nominal | nominal | 10 / 0 / 2 / 0; **0** | 4 / 0 / 8 / 0; **0** | 5 / 0 / 7 / 0; **5** |
| nominal | heavy | 11 / 0 / 0 / 1; **0** | 4 / 0 / 7 / 1; **0** | 3 / 0 / 8 / 1; **3** |
| range bias −0.08 m | nominal | 9 / 1 / 2 / 0; **0** | 3 / 0 / 9 / 0; **0** | 5 / 0 / 7 / 0; **5** |
| range bias −0.08 m | heavy | 11 / 0 / 0 / 1; **0** | 4 / 0 / 7 / 1; **0** | 2 / 0 / 9 / 1; **2** |
| range bias, velocity dropout 10% | nominal | 9 / 1 / 2 / 0; **0** | 2 / 0 / 10 / 0; **0** | 0 / 0 / 11 / 1; **0** |
| range bias, velocity dropout 10% | heavy | 11 / 0 / 0 / 1; **0** | 5 / 0 / 6 / 1; **1** | 0 / 0 / 10 / 2; **0** |
| range bias, anchor dropout 30% | nominal | 9 / 1 / 2 / 0; **0** | 0 / 0 / 12 / 0; **0** | 2 / 0 / 10 / 0; **2** |
| range bias, anchor dropout 30% | heavy | 10 / 1 / 0 / 1; **0** | 4 / 0 / 7 / 1; **0** | 2 / 0 / 9 / 1; **2** |
| range bias, velocity scale 0.25 | nominal | 9 / 1 / 2 / 0; **0** | 4 / 0 / 8 / 0; **0** | 5 / 0 / 7 / 0; **5** |
| range bias, velocity scale 0.25 | heavy | 11 / 0 / 0 / 1; **0** | 3 / 0 / 8 / 1; **0** | 2 / 0 / 9 / 1; **2** |

The sustained arm's 26 decision-time successes all met the sampled dwell diagnostic in this set, with no observed false arrival; its 87 abstentions and 7 timeouts out of 120 assigned rows expose a severe availability cost. Those pooled rows share seeds and conditions and are **not 120 independent observations**. Of the abstentions, 25 were stabilization timeouts and 19 anchor-margin rejections; other reasons include anchor or sensor unavailability, recovery timeout and calibration timeout. The 10% independent velocity dropout condition produced no successes in either vector-bias group. The successful underreport cases do not prove tolerance to velocity spoofing or systematic bias.

No post-STOP collision was observed in the recorded sample; this is not evidence of zero collision risk. The strict and recovery arms often stopped while true velocity exceeded the diagnostic limit, explaining many sampled-dwell failures. The retained older recovery-run source hashes no longer match the current benchmark because this new arm was added subsequently; prior results remain unchanged.

## Evidence and testing

Raw `results/research_development/dev/sustained_stop_development_v1.json` SHA-256 `7169c730ee4de8984eeafe3b4733844ab56c305734f507fb6dc811c0464af002`; diagnostic `results/research_development/analysis/sustained_stop_dwell_v1.json`. The dataset includes last four events and recovery/sustained-speed events, rather than every step of every episode. The diagnostic verifies the self-declared assignment grid and input completeness for STOP dwell. It now marks absent or contradictory episode outcome flags as unevaluable. It does not authenticate the self-declared design or verify the simulation's sensor model.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_sustained_stop.py \
  --seed-start 2242000 --n-seeds 12 --max-steps 650 --post-stop-steps 50 --output NEW_RAW.json
PYTHONPATH=src .venv/bin/python scripts/research/dwell_diagnostics.py NEW_RAW.json \
  --success-radius 0.25 --speed-limit 0.05 --dwell-seconds 1 \
  --arms AEGIS_3D_STRICT_RANGE AEGIS_3D_ANCHOR_RECOVERY AEGIS_3D_SUSTAINED_STOP \
  --output NEW_DWELL.json
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/test_sustained_stop_candidate.py tests/test_dwell_diagnostics.py tests/test_anchor_recovery_candidate.py \
  tests/test_summarize_velocity_retry.py tests/test_summarize_stabilized_arrival.py tests/test_stabilized_arrival_candidate.py \
  tests/test_summarize_post_stop.py tests/test_post_stop_diagnostic.py tests/test_anchor_arrival_candidate.py \
  tests/test_3d_strict_range_development.py tests/test_3d_aware_controller.py \
  tests/test_3d_ablation_reproducibility.py tests/test_mujoco_3d_benchmark_integrity.py tests/test_3d_development_summary.py
```

Selected regression suite: **105 passed**. Existing outputs must not be overwritten; exclusive output files can be partial after interruption. The full repository suite was not run.

## Remaining work

1. Address repeated missing velocity without counting stale or duplicated readings as new evidence; compare candidates under burst dropout, delayed readings, biased low velocity and clock issues. Specify a real timestamp/sequence contract before any hardware use.
2. Diagnose the high stabilization-timeout and anchor-rejection rates, then test a prospective bounded recovery or estimation design on new development scenarios. Do not tune acceptance criteria on confirmatory data.
3. Reduce anchor dependence, retain monitoring during recovery, and evaluate faults correlated across sensors plus actuator mismatch and obstacles. Measure practical cost, latency and real operational utility with a partner.
4. Independently review uncertainty and sequential-selection assumptions and define the actual post-stop dwell requirement before a prospective confirmatory study; real-world and Gate B requirements remain outstanding.
