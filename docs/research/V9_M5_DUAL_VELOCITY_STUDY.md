# V9-M5 exploratory dual-velocity cross-check

**Simulation research only. Gate B remains `GATE_B_NOT_AUTHORIZED`.** No reserved V9-M4 Holdout seed contents or outcomes were accessed, no Holdout episodes were run, and no production authorization ticket was created. There is no real-robot or safety certification evidence.

## Objective and design

The preceding bounded-gap study showed that an assumed velocity bound could be wrong under underreporting. This study asks whether a second simulated velocity source can expose a single-source discrepancy and what it costs in availability. The `AEGIS_3D_DUAL_VELOCITY` arm requires a fresh timestamped reading from both sources, rejects differences greater than 0.1 m/s in vector norm, and otherwise uses the vector with the larger norm for the existing sustained-speed gate. A missing, stale, or disagreeing source becomes missing evidence; it cannot increase the low-speed sample count. The 0.1 m/s threshold and maximum-norm selection are exploratory heuristics, not validated detection or risk bounds.

Each simulated source receives the same simulated true velocity but independent Gaussian noise, standard deviation 0.02 m/s per axis, from distinct random streams. Both use the same idealized clock and environment state. Faults are injected as velocity scale and, in one condition, independent 10% dropout for the second source. `scale=0.25` makes a source report one quarter of the true velocity before noise. The simulation does not model actual sensor modality, mounting, clock drift, common power, upstream localization, authenticated source identity, or real fault correlations. The comparator uses only the first velocity source and the existing freshness gate. All cases have −0.08 m range bias and share the existing simulated anchor and control assumptions.

## Development experiment

Eight fresh development seeds 2245000–2245007 × two vector biases × two arms × five cases = **160 assigned episodes**, with no recorded execution errors. Each cell below is out of 8, with a 650-step episode limit and 50 post-STOP brake steps. Seeds are paired between arms and reused across conditions; different controller decisions can change trajectories. Hashes of selected source files matched before and after this run, but they do not attest the complete runtime. The one-second dwell diagnostic uses sampled simulator truth, not controller evidence or an approved endpoint.

Cells show **decision-time true success / false arrival / abstain / timeout; sampled dwell met**:

| Condition | Vector bias | One freshness-gated source | Dual source |
|---|---|---|---|
| both nominal | nominal | 3 / 0 / 5 / 0; **3** | 0 / 0 / 8 / 0; **0** |
| both nominal | heavy | 6 / 0 / 2 / 0; **6** | 0 / 0 / 7 / 1; **0** |
| primary underreports | nominal | 2 / 0 / 6 / 0; **2** | 0 / 0 / 8 / 0; **0** |
| primary underreports | heavy | 5 / 0 / 3 / 0; **5** | 0 / 0 / 8 / 0; **0** |
| secondary underreports | nominal | 3 / 0 / 5 / 0; **3** | 0 / 0 / 8 / 0; **0** |
| secondary underreports | heavy | 6 / 0 / 2 / 0; **6** | 0 / 0 / 8 / 0; **0** |
| both underreport | nominal | 2 / 0 / 6 / 0; **2** | 0 / 0 / 8 / 0; **0** |
| both underreport | heavy | 5 / 0 / 3 / 0; **5** | 0 / 0 / 7 / 1; **0** |
| secondary dropout 10% | nominal | 3 / 0 / 5 / 0; **3** | 0 / 0 / 8 / 0; **0** |
| secondary dropout 10% | heavy | 6 / 0 / 2 / 0; **6** | 0 / 0 / 7 / 1; **0** |

The dual arm made **no sampled-dwell successes in this development sample**, even in nominal conditions. In the 16 dual nominal episodes, ten abstentions were labeled stabilization timeout, two recovery sensor invalid, two calibration timeout, one recovery timeout, and one episode timed out. Thus this prototype is not satisfactory for usability and should not be promoted.

When only the primary underreported, the cross-check flagged 1,612 of 1,636 comparisons in the nominal-vector group and 2,079 of 2,102 in the heavy-vector group. These are correlated time steps across episodes, mostly outside the terminal decision; they are not sensitivity estimates or independent samples. In contrast, when both sources underreported, the sources often agreed despite error. One retained example is seed 2245000, nominal vector bias, step 129: simulator true speed ≈0.1967 m/s, primary observed ≈0.0394 m/s, secondary observed ≈0.0310 m/s, and the cross-check labeled the readings consistent while the controller was in VERIFY. This observation is **not a false STOP**; it demonstrates that agreement alone cannot establish correctness under common-mode error.

For context, the run records 216 nominal-vector and 308 heavy-vector time steps under common underreport where true simulator speed exceeded 0.05 m/s, the primary reported at most 0.05 m/s, and the two sources were labeled consistent. These counters include all controller phases and cannot be interpreted as per-episode failure rates. A consistent label does not necessarily mean the selected larger source was below 0.05 m/s; only the retained example above explicitly establishes that both were below the exploratory threshold. No observed decision-time false arrival or collision in a small sample establishes zero risk.

## Evidence, checks and reproducibility

Raw `results/research_development/dev/dual_velocity_development_v1.json`, SHA-256 `9744ee7c8c7ad640fce39e47a58fd15447d3529a8d2feba513af00ef02281724`; analyzed counts `results/research_development/analysis/dual_velocity_diagnostics_v1.json`; dwell `results/research_development/analysis/dual_velocity_dwell_v1.json`. Raw records retain each outcome, comparison totals, aggregated primary-underreport condition counts, up to five examples per episode, and last four events; they are not complete time-series logs. The analyzer validates the self-declared grid and counts but cannot authenticate inputs, ensure source independence or prove physical accuracy. The benchmark was changed after prior studies to add this arm, so prior source hashes will not match current files.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_dual_velocity.py \
  --seed-start 2245000 --n-seeds 8 --max-steps 650 --post-stop-steps 50 --output NEW_RAW.json
PYTHONPATH=src .venv/bin/python scripts/research/analyze_dual_velocity.py NEW_RAW.json --output NEW_DIAGNOSTICS.json
PYTHONPATH=src .venv/bin/python scripts/research/dwell_diagnostics.py NEW_RAW.json \
  --success-radius 0.25 --speed-limit 0.05 --dwell-seconds 1 \
  --arms AEGIS_3D_FRESH_VELOCITY AEGIS_3D_DUAL_VELOCITY --output NEW_DWELL.json
```

Outputs use exclusive creation; interrupted runs may leave incomplete files. Synthetic tests cover disagreement, missing and replayed source, selection of the larger consistent speed, and agreement under common faulty readings; analyzer tests cover missing/duplicate assignments, contradictory outcomes and malformed evidence. The selected adjacent regression suite passed **139 tests**. The full repository suite was not run.

## Next decisions for development

1. Investigate the availability bottleneck caused by repeated noisy readings and consecutive low-speed samples. Any replacement should model uncertainty, missingness and sensor dependence explicitly; avoid choosing a threshold solely to improve the observed sample.
2. Design a development experiment with genuinely different sensor modalities and a separately measured reference once hardware or realistic public recordings are available. A second simulated copy of truth with independent noise is not evidence of independent physical sources.
3. Model shared upstream errors, clock faults, replay, sensor dropout bursts and calibration drift. Record full events for a small fixed diagnostic subset and preserve all assigned outcomes.
4. Define and independently review a prospective stabilized-arrival endpoint and statistical design before a confirmatory claim. Do not enable the candidate as a safety function or proceed to V9-M4 Holdout without resolving its separate governance blockers and obtaining explicit authorization.
