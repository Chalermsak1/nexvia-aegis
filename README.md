# Nexvia Aegis

### A self-verifying decision layer for Physical AI

Nexvia Aegis is a research prototype for risk-aware decision making in uncertain physical environments.

The system combines:

- Uncertainty estimation
- Active sensing
- Cross-sensor verification
- Sensor arbitration
- Risk-aware decision making
- Abstention under insufficient evidence

## Research Thesis

> A Physical AI agent should not only know what to do — it should know when it has enough evidence to do it.

## Decision Loop

```text
Perceive
   ↓
Estimate
   ↓
Predict
   ↓
Evaluate Evidence
   ↓
Inspect / Verify
   ↓
Sensor Arbitration
   ↓
Risk-Aware Decision
   ↓
ACT / STOP / ABSTAIN
   ↓
Verify Again
Experimental Setup

The current prototype uses a custom 2D uncertain-target environment.

Policies:

Always Act
Inspect Once
Nexvia Aegis v1.0

Scenarios:

NORMAL
BIASED
HEAVY_TAIL
OUTLIER
DRIFT
CORRELATED_BIAS

Final benchmark:

1,000 episodes per policy per scenario
Key Results

Aegis showed substantially lower false-stop rates under several uncertain and anomalous conditions.

Scenario	Aegis Success	Aegis False Stop	Aegis Abstain
NORMAL	74.00%	3.27%	23.50%
BIASED	1.00%	85.07%	93.30%
HEAVY_TAIL	65.80%	1.35%	33.30%
OUTLIER	23.70%	3.27%	75.50%
DRIFT	12.00%	49.37%	76.30%
CORRELATED_BIAS	0.00%	100.00%	24.10%

These results indicate a clear safety-efficiency trade-off. Aegis can reduce unsafe stopping decisions by verifying evidence and abstaining, but remains vulnerable to systematic and correlated sensor failures.

Limitations

This is a research prototype rather than a production robotic system.

Current limitations include:

2D simulated environment
Simplified sensor models
Synthetic distribution-shift scenarios
No physical robot evaluation
Limited sensor modalities
Correlated sensor failures remain difficult to detect
Future Work
MuJoCo
   ↓
Robot Manipulation
   ↓
Vision / Sensor Observations
   ↓
Aegis Decision Layer
   ↓
Act / Verify / Recover

Future research directions include multimodal perception, learned uncertainty estimation, counterfactual action evaluation, adaptive sensor selection, recovery policies, and sim-to-real transfer.

Reproducibility

Install dependencies:

uv sync

Run the final benchmark:

PYTHONPATH=src uv run python experiments/final_benchmark.py
Version

Nexvia Aegis v1.0.0

Frozen research prototype.

Author

Chalermsak Sinsok

Nexvia Core — Physical AI Research
