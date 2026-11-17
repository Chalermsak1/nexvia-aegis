# LIVE01 additional falsification: fresh metadata with frozen measurement values

Declared on 2026-11-17 before running these additional cases. Exploratory simulation only; no V9-M4 change or production authorization. GATE_B_NOT_AUTHORIZED.

## Question

Can a same-source consistency check distinguish a physically current measurement from frozen values carried in newly identified and timestamped packets? Packet freshness, source labels and internal consistency do not independently establish physical calibration or value freshness.

## Additional cases and expected interpretation

Add retimestamped_freeze to SIMULATION_CONTRACT_CHECKS and STRICT_OBSERVATIONS. At the existing fault tick, the plant's fault injector replaces reported position and velocity centers/intervals with zero while retaining fresh sequence IDs, metadata and transport timestamps. Actual plant evolution is unchanged. Controller/watchdog must not receive ground-truth state or the future fault schedule. Only the read-only auditor compares reported intervals with the saved exact trajectory.

Preserve any continued conditional permissions, effects based on false measurement premises and trajectory violations. Do not classify successful finite predicate comparisons as independently validated physical state. The strict arm must continue withholding nominal permission. These cases intentionally falsify the measurement-bound assumption; containment is not an acceptance requirement under that false assumption. Report the limitation explicitly rather than weakening the boundary, adding simulator truth to the policy or changing old results.

## Closure evidence

Require actual injected samples with violated physical bounds, source-bound collection records, exact post-run comparison, and separate counts for conditional leases/effects whose measurement premise was false. Preserve all six outcomes, including any counterexample. This exercise cannot close the external requirement for an independently justified/calibrated observation source. No new physical assurance or release readiness follows from preparing or running this addendum.
