# Standalone development monitor reference

This directory is a research reference, not an approved replacement for any NEXVIA statistical monitor/evaluator. No repository files were modified. Gate B remains `GATE_B_NOT_AUTHORIZED`.

`development_eprocess.py` implements the upper-only score and unfloored log-wealth process specified in `/private/tmp/nexvia-monitor-proof-review-20261116.md`. Conditional validity requires nonnegative observations and a positive predictable envelope satisfying **E[Z_t | past] <= tau_t** at every supported step. That is an unverified caller assumption, not an assertion about aerodynamic residuals. The API cannot authenticate predictability, the observation model, calibration or runtime integrity.

The public bet/cap/alpha parameters are read-only after construction. No reset or wealth-replenishment API is supplied. Invalid observations/order reject before updating state. Missingness is not automatically modeled or silently skipped. Source code is an ordinary Python reference, not tamper-resistant software or certified floating-point verification.

Tests check exact rational null expectations and two counterexamples, agreement of log wealth with ordinary products, threshold arithmetic, extreme finite ratios, invalid inputs/order and read-only public configuration. Initial 25 passed; final 26 passed after adding the configuration-access check. No unexpected test failures. The first attempted tool launch used a not-yet-created work directory and did not execute; the directory was created before the successful test runs.

Reproduce with the project's Python environment:

```
PYTHONDONTWRITEBYTECODE=1 /Users/chalermsak/Documents/ChatGPT/New\ project/nexvia-aegis/.venv/bin/python -m pytest -p no:cacheprovider -q test_development_eprocess.py
```

The selected final source/test/XML hashes are in `verification.json`. Further calibration/dependence, missingness, resets/multiplicity and independent statistical review remain required before a physical-system anytime-valid claim. A monitor-error guarantee would still not constitute a collision-risk guarantee.
