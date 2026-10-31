# V9-M5 bounded-gap development and falsification

**Result: the proposed bound is falsified in the tested simulator. The bounded-gap arm is an exploratory research fixture, not a deployment candidate.** Gate B remains `GATE_B_NOT_AUTHORIZED`. No reserved V9-M4 Holdout seed contents or outcomes were accessed, no Holdout episodes were run, and no production ticket was created.

## Candidate and assumptions

The separate `AEGIS_3D_BOUNDED_GAP` arm extends the freshness-gated sustained-stop prototype. It allows a missing velocity update to preserve, but **not increment**, the existing count of fresh low-speed samples when the time since the last fresh sample is at most 0.04 s and the following assumed bound remains ≤0.05 m/s:

`norm(last fresh velocity) + 0.01 m/s assumed measurement error + 0.1 m/s² assumed acceleration × elapsed seconds`.

This assumption is not independently measured. In particular, simulator velocity observations include Gaussian noise with 0.02 m/s standard deviation per axis, which has unbounded tails and therefore does not satisfy an absolute 0.01 m/s error bound. This alone prevents the expression from being a deterministic safety bound. It is explicitly used to test an idea, not to state statistical coverage. The candidate does not bridge replay, stale, bad clock, malformed velocity, or gaps beyond 0.04 s; such events go to the existing missing-data logic. During a bridged gap it commands VERIFY/braking, and still requires 20 fresh low-speed readings before requesting anchor confirmation. Fresh metadata itself is neither authenticated nor evidence of sensor correctness.

The fault simulation injects −0.08 m range bias in all cases; independent per-step velocity dropout, replay and a velocity scaling fault are evaluated separately. `velocity_scale=0.25` means the velocity component is underreported before adding noise. Other sensor and actuator assumptions remain idealized. The simulator's braking and damping have access to plant state. No hardware was used.

## Development results

Ten fresh development seeds 2244000–2244009, two vector-bias conditions, two arms and five fault cases produced **200 assigned episodes**; all were recorded complete and selected source hashes matched before/after. Seeds repeat across fault conditions. Maximum length was 650 steps plus 50 post-STOP brake steps. The post-STOP sampled dwell measure requires simulator-truth position ≤0.25 m and speed ≤0.05 m/s at the STOP instant and 50 subsequent samples, with no recorded collision. It is exploratory and not an approved scientific endpoint.

Cells show **decision-time true success / false arrival / abstain / timeout; sampled dwell met** out of 10. The gap and violation counts are numbers of *bridged steps*, not independent episodes.

| Velocity condition | Vector bias | Freshness only | Bounded gap | Bridged steps / actual speed exceeds assumed bound |
|---|---|---|---|---|
| no injected fault | nominal | 2 / 0 / 6 / 2; **2** | 2 / 0 / 6 / 2; **2** | 0 / 0 |
| no injected fault | heavy | 5 / 0 / 4 / 1; **5** | 5 / 0 / 4 / 1; **5** | 0 / 0 |
| 10% dropout | nominal | 0 / 0 / 9 / 1; **0** | 1 / 0 / 8 / 1; **1** | 73 / 1 |
| 10% dropout | heavy | 0 / 0 / 9 / 1; **0** | 2 / 0 / 8 / 0; **2** | 92 / 2 |
| 30% dropout | nominal | 0 / 0 / 10 / 0; **0** | 1 / 0 / 9 / 0; **1** | 22 / 2 |
| 30% dropout | heavy | 0 / 0 / 10 / 0; **0** | 0 / 0 / 10 / 0; **0** | 32 / 3 |
| 10% dropout and velocity scale 0.25 | nominal | 0 / 0 / 9 / 1; **0** | 1 / 0 / 8 / 1; **1** | 91 / 21 |
| 10% dropout and velocity scale 0.25 | heavy | 0 / 0 / 9 / 1; **0** | 3 / 0 / 7 / 0; **3** | 106 / 28 |
| 20% replay | nominal | 0 / 0 / 10 / 0; **0** | 0 / 0 / 10 / 0; **0** | 0 / 0 |
| 20% replay | heavy | 0 / 0 / 10 / 0; **0** | 0 / 0 / 10 / 0; **0** | 0 / 0 |

Under velocity underreporting, actual speed exceeded the assumed bound on **49 of 197 bridged steps**, including **40 steps above the exploratory 0.05 m/s limit**. These steps are clustered within episodes and the rate is not a population estimate. One concrete counterexample is seed 2244000, heavy vector bias, step 177: true speed was approximately 0.154862 m/s while the candidate bound was 0.043089 m/s, with no velocity observation at that step. The candidate therefore continued VERIFY while incorrectly treating the carried sequence as satisfying its assumed speed bound. It cannot observe this contradiction from its own missing measurement.

Some dropout cases show more sampled-dwell successes than the strict freshness arm, but the falsified assumption is a decisive limitation: later observed successful stops do not retroactively validate the bound. Zero decision-time false arrivals in this small sample is not evidence of zero risk. The system has no runtime detector for arbitrary velocity underreporting, unauthenticated metadata or incorrect acceleration bounds.

## Evidence, validation and reproduction

Raw file `results/research_development/dev/bounded_gap_development_v1.json` SHA-256 `afec1fa2efefdcff93eff8c891865b726012d2ecc70592919c2e53a9f9cd5db9`; analysis outputs `results/research_development/analysis/bounded_gap_bounds_v1.json` and `results/research_development/analysis/bounded_gap_dwell_v1.json`. Each bridged event retains simulator velocity, bound, timestamp/sequence metadata and controller state. The bound analyzer validates the self-declared assignment grid, event counts and finite values; it does not independently authenticate simulation source, full dependency set or experimental design. Metadata hashes matched for the selected source files before/after the run.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_bounded_gap.py \
  --seed-start 2244000 --n-seeds 10 --max-steps 650 --post-stop-steps 50 --output NEW_RAW.json
PYTHONPATH=src .venv/bin/python scripts/research/analyze_gap_bounds.py NEW_RAW.json --output NEW_BOUNDS.json
PYTHONPATH=src .venv/bin/python scripts/research/dwell_diagnostics.py NEW_RAW.json \
  --success-radius 0.25 --speed-limit 0.05 --dwell-seconds 1 \
  --arms AEGIS_3D_FRESH_VELOCITY AEGIS_3D_BOUNDED_GAP --output NEW_DWELL.json
```

Outputs must use fresh paths; interrupted execution may leave a partial file. Synthetic tests verify gaps do not count as new observations, finite gap duration, reset of evidence, replay rejection, bounds-analyzer consistency, duplicate detection and explicit bound violations. The selected adjacent regression suite passed **126 tests**; the full repository suite was not run.

## Next steps

1. Keep the strict freshness arm as comparator and do not promote the falsified bounded-gap policy. Obtain evidence for sensor error, clock quality and acceleration bounds before proposing any bounded estimator; if those assumptions cannot be supported, represent uncertainty as unresolved and avoid confirmation.
2. Model independent velocity sources and physically plausible correlated faults. Test whether independent observations actually detect underreporting; avoid assuming independence without evidence. Add burst dropout, clock faults and actuator mismatch to the development design.
3. Define and review a practical stability endpoint and full missing-evidence semantics before future confirmatory research. The existing V9-M4 scientific and release blockers and explicit owner authorization remain prerequisites for any V9-M4 Holdout.
