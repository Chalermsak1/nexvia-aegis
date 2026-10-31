# Targeted vector-sensor loss after a STOP proposal

**Exploratory development simulation only. Gate B remains `GATE_B_NOT_AUTHORIZED`.** No V9-M4 Holdout outcomes or reserved seed contents were accessed, no production ticket was created, and no frozen artifact or registered statistical rule was changed. These findings are not real-robot validation or a safety certificate.

## Objective and design

A prior synthetic fixture showed the exploratory anchor-recovery candidate could issue STOP after both vector sensors were absent during confirmation. The benchmark now provides an **opt-in, separately named development fault**: once either recovery arm enters BRAKING, ANCHOR or RECOVERY after a STOP proposal, both 3D vector readings are marked invalid/dropped. The simulator still generates underlying measurements, but the observations presented to the candidates are marked unavailable; the injected-step count is recorded. The fault is not injected into unrelated controllers. Other range, anchor, noise, physics and CBF behavior are unchanged for the selected setting. This is not a real sensor failure model, and it does not measure partial loss, intermittency, delayed messages, or fault detection latency.

The study runner uses an exclusive development ledger and records assignments before execution. Development seeds 2251000–2251002, two vector biases, two arms and four cases (the prior three plus targeted vector loss) produced **48 assigned/completed episodes** with no recorded execution errors. Targeted fault injection occurs only when an arm actually reaches a post-proposal phase; an untriggered assignment is not evidence of resilience or detection. Seed/world realizations are paired across arms until trajectories diverge; three seeds and repeated conditions are insufficient for risk or statistical conclusions.

## Targeted-fault observations

Cells are per vector bias and arm; each has three assigned episodes. STOP refers to decision time, not stable physical arrival.

| Vector bias | Arm | Fault triggered | STOP after fault | Abstain after fault | Assigned outcomes: true / false / abstain / timeout |
|---|---|---:|---:|---:|---|
| nominal | anchor recovery | 2 | 1 | 1 | 1 / 0 / 2 / 0 |
| nominal | recovery monitor | 2 | 0 | 2 | 0 / 0 / 3 / 0 |
| heavy | anchor recovery | 2 | 0 | 2 | 0 / 0 / 2 / 1 |
| heavy | recovery monitor | 2 | 0 | 2 | 0 / 0 / 2 / 1 |

Thus the previously observed synthetic state-machine gap was also seen in one development MuJoCo episode: the baseline anchor-recovery arm issued a decision-time true STOP after the injected vector loss. The post-proposal monitor abstained in its triggered counterpart. This is a comparison of exploratory policies and does not establish an alarm probability, a false-alarm rate, or that either arm is safe. The monitor starts a fresh e-process after the STOP proposal and can react to raw residuals under bias; its assumptions and false alarms remain unvalidated. The simulator still uses truth-state information in its existing damping/CBF path.

## Evidence and tests

Raw `results/research_development/dev/recovery_monitor_vector_loss_v2.jsonl` SHA-256 `aed0dc58956f63f675a45dec755f70942bb13d54ff7bb2ea02167b123995b458`; summary `results/research_development/analysis/recovery_monitor_vector_loss_v2_summary.json`. The analyzer checks self-declared assignments, identities, outcomes, fault counts and source map consistency, but the manifest and unkeyed chain are not independently authenticated. Last-four-event trace storage is not a full trace; interrupted episode steps may still be lost in memory. The older recovery-monitor ledger and summary remain unchanged. The runner and analyzer changed since the older run, so current source hashes do not match it.

Synthetic integration tests verify loss starts only after the simulated proposal, reaches both paired arms with invalid/dropped flags, and is rejected for unrelated arms. Dedicated monitor tests cover invalid readings separately; they do not validate real-world sensor or plant safety.

```bash
PYTHONPATH=src .venv/bin/python scripts/research/study_recovery_monitor_ledger.py \
  --seed-start 2251000 --n-seeds 3 --max-steps 400 --post-stop-steps 50 --include-vector-loss --output NEW_LEDGER.jsonl
PYTHONPATH=src .venv/bin/python scripts/research/analyze_recovery_monitor_ledger.py NEW_LEDGER.jsonl --output NEW_SUMMARY.json
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_recovery_vector_fault_injection.py \
  tests/test_analyze_recovery_monitor_ledger.py tests/test_study_recovery_monitor_ledger.py \
  tests/test_recovery_monitor_candidate.py tests/test_development_ledger.py
```

Use new output paths; no automatic retry or repair. Next examine transition-specific intermittent and correlated faults, retain step-level observations for selected diagnostic cases, define monitoring treatment across calibration and recovery, and repeat with estimated-state control instead of truth-state damping. Any confirmatory endpoint or safety claim requires an independently reviewed protocol and appropriate evidence.
