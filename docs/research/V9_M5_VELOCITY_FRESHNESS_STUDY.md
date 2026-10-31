# V9-M5 exploratory velocity freshness contract

**Simulation-only development. Gate B remains `GATE_B_NOT_AUTHORIZED`.** No reserved V9-M4 Holdout seeds or outcomes were accessed, no Holdout episodes were run, and no production ticket was created. This is not a real-robot validation, certified safety control, or confirmatory study.

## Change

The separate `AEGIS_3D_FRESH_VELOCITY` arm wraps the sustained-stop candidate with a velocity metadata gate. In this simulation-only contract an observation has a 3-vector, nonnegative integer sequence number and acquisition time, and the caller provides current time on the same clock. The gate rejects absent, malformed, nonfinite, future, stale, duplicated, reordered or non-monotonic-clock evidence. Accepted samples must advance both sequence and acquisition time. Rejected samples are passed as missing to the existing bounded-retry logic; they cannot advance the sustained-speed count. The exploratory maximum age is 0.01 s; simulator update period is 0.02 s, so a one-step delay exceeds it. This threshold is a development parameter, not a hardware or protocol requirement.

Only velocity is covered by this prototype. The caller's clock and metadata are assumed truthful, synchronized, and associated with the value; the gate cannot detect a forged fresh timestamp/sequence or a plausible biased value. It has no authenticated source identity, clock synchronization, reset/epoch handshake, transport integrity, cross-process persistence, or detection of a sensor republishing old values with new metadata. It should not be integrated as a real safety function. The sustained-stop arm's existing anchor, range, recovery, model and monitor limitations remain.

The simulation harness now separately injects fixed velocity latency and replay. The original sequence and acquisition time travel with a delayed/replayed sample; the unguarded comparator receives the same delayed/replayed vector but no metadata check. The replay generator sometimes republishes the previous delivered measurement, including the possibility that it was itself already a replay. Range bias is fixed at −0.08 m in every condition. This is a controlled development fault injection, not a real network or adversary model.

## Results

Ten development seeds 2243000–2243009, two vector biases, two arms and five fault conditions produced **200 assigned episodes**, all recorded complete. Maximum episode length was 650 steps, plus 50 post-STOP brake steps. Selected source hashes were unchanged before/after the run. Common seeds pair initial conditions and random streams; actions can diverge. Seeds repeat across conditions, and each table cell has only 10 episodes.

Cells show **decision-time true success / false arrival / abstain / timeout; sampled one-second dwell met**, out of 10. Dwell requires all samples at and after STOP to meet the exploratory 0.25 m radius and 0.05 m/s speed limits and no recorded collision. It does not prove behavior between samples and is not an approved endpoint.

| Velocity condition | Vector bias | Sustained, no metadata gate | With freshness gate |
|---|---|---|---|
| Fresh | nominal | 2 / 0 / 8 / 0; **2** | 2 / 0 / 8 / 0; **2** |
| Fresh | heavy | 2 / 0 / 7 / 1; **2** | 2 / 0 / 7 / 1; **2** |
| Two-step delay | nominal | 1 / 0 / 9 / 0; **1** | 0 / 0 / 10 / 0; **0** |
| Two-step delay | heavy | 1 / 0 / 8 / 1; **1** | 0 / 0 / 10 / 0; **0** |
| Replay probability 20% per step | nominal | 2 / 0 / 8 / 0; **2** | 0 / 0 / 10 / 0; **0** |
| Replay probability 20% per step | heavy | 5 / 0 / 5 / 0; **5** | 0 / 0 / 10 / 0; **0** |
| Dropout probability 10% per step | nominal | 0 / 0 / 10 / 0; **0** | 0 / 0 / 10 / 0; **0** |
| Dropout probability 10% per step | heavy | 0 / 0 / 10 / 0; **0** | 0 / 0 / 10 / 0; **0** |
| Velocity scale 0.25 | nominal | 4 / 0 / 6 / 0; **4** | 4 / 0 / 6 / 0; **4** |
| Velocity scale 0.25 | heavy | 3 / 0 / 6 / 1; **3** | 3 / 0 / 6 / 1; **3** |

Under fresh, underreported, and dropout conditions, the two arms matched on step count, final distance, decision-time outcomes, collision count and anchor queries in all 20 seed/bias pairs per condition. This checks that an accepted fresh value is observationally equivalent in this sample; it does not validate all code paths. During the fixed-delay condition, the freshness arm recorded 1,138 rejected velocity observations in the nominal-vector group and 1,531 in the heavy group. These include all episode steps, including navigation and calibration, not only the arrival gate. Stale/duplicate metadata detection does not establish that the values are physically correct, as the underreport arm illustrates. No observed false arrivals in the tested cells imply neither zero risk nor superiority.

The guarded arm had zero sampled-dwell successes with two-step delay or 20% replay; failure to obtain fresh evidence is being traded for availability. A single fixed delay and independent replay/dropout model does not characterize real networks. Investigate timestamped buffers, trusted source identity, outage recovery, observation rate and time-bounded estimation before selecting a practical policy; do not count stale data as independent fresh evidence.

## Evidence and tests

Raw file `results/research_development/dev/velocity_freshness_development_v1.json`, SHA-256 `d96be636f594f7c96077729937831933db6d06efa34aea1e819a34cb669027b1`; sampled-dwell output `results/research_development/analysis/velocity_freshness_dwell_v1.json`. Raw rows contain outcomes, the last four events and aggregate gate reasons, not full per-step traces. Selected source hashes do not attest the full runtime. Assignment and diagnostic validation depend on the self-declared design. Existing earlier simulation evidence remains preserved; because the benchmark was extended, its current hash differs from prior runs.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_velocity_freshness.py \
  --seed-start 2243000 --n-seeds 10 --max-steps 650 --post-stop-steps 50 --output NEW_RAW.json
PYTHONPATH=src .venv/bin/python scripts/research/dwell_diagnostics.py NEW_RAW.json \
  --success-radius 0.25 --speed-limit 0.05 --dwell-seconds 1 \
  --arms AEGIS_3D_SUSTAINED_STOP AEGIS_3D_FRESH_VELOCITY --output NEW_DWELL.json
```

Use fresh output paths; output creation is exclusive and a failed run can leave a partial file. Synthetic tests cover sequence replay and reorder, stale/future timestamps, invalid observations, clock rollback, reset, replay breaking a sustained-speed count, and simulated two-step latency retaining its original acquisition timestamp. The selected adjacent regression suite passed **116 tests**; the full repository suite was not run.

## Next steps

1. Specify an explicit freshness and outage contract for actual sensor sources, including clock domain, maximum clock error, unique identity, sequence reset/epoch, age threshold and behavior when provenance is unavailable; validate against hardware logs before use.
2. Prototype a separately labelled bounded-gap estimator that propagates uncertainty across missing readings without calling old samples fresh. Compare it against the strict gate using burst loss, variable latency, held values, realistic timestamps and matched development scenarios. Keep unevaluable conditions explicit.
3. Model sensor bias and correlated faults, actuator and braking uncertainty, and keep checks active during anchor recovery. Continue to measure sampled dwell, task success, false arrival, abstention, timeout and resource costs together.
4. Seek independent statistical and control review before any claim about confidence or safety; follow existing V9-M4 governance and explicit authorization requirements before any confirmatory stage.
