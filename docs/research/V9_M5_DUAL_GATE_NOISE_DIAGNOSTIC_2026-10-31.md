# Dual velocity gate: analytical noise diagnostic

**Exploratory mathematical toy model only; not a simulator episode success probability, confidence guarantee, confirmatory result, or real-robot validation.** Gate B remains `GATE_B_NOT_AUTHORIZED`.

## Question and assumptions

The exploratory dual-source candidate applies a 0.05 m/s norm limit to the larger of two velocity readings and the sustained gate requests 20 consecutive low-speed samples. To investigate whether noise alone might contribute to timeout, `scripts/research/dual_gate_noise_diagnostic.py` calculates an idealized lower-level event: both sensors pass this norm limit for 20 successive samples at least once within 220 samples.

Assume the robot is exactly stationary throughout, each axis of each source is independent Gaussian noise with standard deviation 0.02 m/s, both sources are independent, samples are independent over time, and no other gate, recovery, braking, anchor, collision, clock, latency or control logic applies. These assumptions are deliberately stronger and simpler than physical reality; common faults and temporal correlations break them. The formula for a single 3D Gaussian norm and a dynamic program for runs of Bernoulli successes avoid treating overlapping windows as independent. Dropout, where included, is independent per source per step and independent of noise. The model does **not** use or adjust a registered threshold and does not imply the 220-sample wait alone determines episode outcome.

| Independent per-source dropout | Single-source speed check on an available reading | Both sources pass and are available in one step | One specified 20-sample window passes | At least one 20-sample run within 220 samples |
|---|---:|---:|---:|---:|
| 0% | 89.994% | 80.989% | 1.474% | 45.643% |
| 10% | 89.994% | 65.601% | 0.0218% | 1.511% |

The per-source dropout model is not the same as the previous study's secondary-only dropout, so the numerical values must not be presented as predictions of that study. Even when true velocity is zero, the toy calculation indicates that requiring both noisy sensors to pass at every step can contribute to a long wait. It cannot establish the real cause of a specific timeout; inspect instrumented development traces and consider sensor dependence, measurement age, controller state, recovery and action constraints before choosing a candidate. Do not loosen the condition or reuse development results as confirmatory evidence based on this model.

As an implementation sanity check, 30,000 independent Bernoulli sequences per condition generated with NumPy seed 5918274 gave 0.45710 and 0.01620 for the 0% and 10% dropout cases, compared with the dynamic-program outputs 0.45643 and 0.01511. This is a check of the simplified calculation, not evidence that the model matches simulator dynamics or a safety probability.

## Evidence and verification

`results/research_development/analysis/dual_gate_noise_theory_v1.json` has SHA-256 `f6f4df67b2f602d33107a21cca3f9eb07335714d315f67238d9bd016c705998f` and includes the analytical script hash and all assumptions. Synthetic unit tests cover the 3D Gaussian probability, short-run cases, zero and one probability, dropout effects and invalid inputs. Use a fresh output path; no previous result is overwritten.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/dual_gate_noise_diagnostic.py --output NEW_OUTPUT.json
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_dual_gate_noise_diagnostic.py
```

## Next development decision

Instrument the exploratory dual gate to retain fixed, preselected development traces and distinguish noise-driven resets from source loss, disagreement, motion and recovery. Compare candidate evidence-handling policies on separate development scenarios, including common-mode faults and burst loss. Any interval/uncertainty interpretation needs stated assumptions and independent statistical review before use in a prospective study. No V9-M4 data or decision logic is involved.
