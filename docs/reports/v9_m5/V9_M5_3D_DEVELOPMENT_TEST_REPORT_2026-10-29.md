# V9-M5 3D development implementation and test report — 2026-10-29

**Classification:** exploratory MuJoCo development result. No V9-M4 Holdout data, reserved seed manifest, production ticket, or physical robot was used. No safety certification is claimed.

**Base:** `origin/main` at `5055526f83846d1ce7a0e76058fc27407e2ff06f`, developed on local branch `codex/v9-m5-development`. This report describes uncommitted working-tree changes; the final code commit is not yet designated. The V9-M4 frozen evaluator, policy files, production results, and release documents were not edited.

## Implemented changes

1. `src/aegis/env/mujoco_3d_cbf.py`: observe post-step obstacle clearance, arena/floor clearance, and MuJoCo robot–obstacle/floor contacts. Previously, `step()` reported obstacle distance from the **pre-step** position, so a contact on the current step could be missed. The `safety_violation` output now reflects the returned state plus contacts.
2. `experiments/benchmark_physical_3d_cbf.py`: count collision events before any terminal branch exits and return the actual final-state distance. Remove the unconditional printed claim of zero false arrivals. Use configured mass, force limit, and success radius instead of hardcoded physical values.
3. Add a **separate exploratory arm**, `AEGIS_V9_CBF_RANGE_GUARD`. It accepts a planar V9 `STOP` only when the independent measured 3D range plus a fixed `1.645 × 0.05 m` measurement margin fits within the configured success radius; otherwise it brakes and abstains. This is a one-observation engineering veto, **not** a valid sequential confidence bound, certified risk control, or change to the frozen V9-M4 candidate. Ground truth is used to score outcomes only, not to decide STOP.
4. Add a reproducible CLI with seed range, step cap, and exclusive-create JSON output. Each evidence file stores all episode rows, summary counts, Python/NumPy/MuJoCo versions, and source SHA-256. Existing evidence files cannot be overwritten by the CLI.
5. `tests/test_mujoco_3d_benchmark_integrity.py`: regression tests for post-step contact, last-step collision accounting/final distance, fail-closed range veto, evidence completeness, and no overwrite.

## Executed tests

```text
.venv/bin/python -m pytest -q
318 passed in 29.80s
```

Both final development cohorts used the same three prespecified bias vectors in the script (`[0,0,0]`, `[0.5,-0.4,0.2]`, `[0.8,0.8,-0.3]`) and four policy arms. Each arm had 20 seeds per bias = 60 episode records. Seeds repeat across arms and biases for comparison; **60 records are not necessarily 60 independent statistical units**. The second seed range was run after the guard was developed, so it is additional exploratory validation, **not** a preregistered Holdout. All 480 final episode records were preserved in JSON.

```text
PYTHONPATH=src .venv/bin/python experiments/benchmark_physical_3d_cbf.py \
  --seed-start 88000 --n-seeds 20 \
  --output results/v9_m5/dev/benchmark_3d_88000_final.json

PYTHONPATH=src .venv/bin/python experiments/benchmark_physical_3d_cbf.py \
  --seed-start 99000 --n-seeds 20 \
  --output results/v9_m5/dev/benchmark_3d_99000_final.json
```

### Cohort A: seeds 88000–88019, 60 episodes per arm

| Arm | True success | False arrival | Simulated collision | Accepted | Abstained | Timeout |
|---|---:|---:|---:|---:|---:|---:|
| UNSHIELDED | 9 | 30 | 29 | 39 | 0 | 21 |
| CBF_ONLY | 10 | 30 | 0 | 40 | 0 | 20 |
| AEGIS_V9_CBF | 15 | 13 | 0 | 28 | 21 | 11 |
| AEGIS_V9_CBF_RANGE_GUARD | 4 | 0 | 0 | 4 | 45 | 11 |

### Cohort B: seeds 99000–99019, 60 episodes per arm

| Arm | True success | False arrival | Simulated collision | Accepted | Abstained | Timeout |
|---|---:|---:|---:|---:|---:|---:|
| UNSHIELDED | 8 | 24 | 41 | 32 | 0 | 28 |
| CBF_ONLY | 7 | 29 | 0 | 36 | 0 | 24 |
| AEGIS_V9_CBF | 12 | 12 | 0 | 24 | 19 | 17 |
| AEGIS_V9_CBF_RANGE_GUARD | 6 | 0 | 0 | 6 | 37 | 17 |

The guard reduced observed false arrivals in both development cohorts, but accepted only **4/60** and **6/60** episodes. Its apparent safety comes with a severe utility loss. The unguarded 3D integration produced **13/60** and **12/60** false arrivals, contradicting the benchmark's former unconditional zero-error conclusion. No statistical pass criterion has been applied or inferred from these observations. Collision counts are based on recorded post-step state and MuJoCo contacts; continuous trajectories between solver steps and physical-world contacts are outside this measurement.

## Evidence integrity

| Final evidence | SHA-256 |
|---|---|
| `results/v9_m5/dev/benchmark_3d_88000_final.json` | `dc635d476a1e050eccbcd405aff820dc921ff6601881edbacc0c1a32d064665f` |
| `results/v9_m5/dev/benchmark_3d_99000_final.json` | `9e81d92c5efb794ba185841faabd3cbae7b791819b61083b7d98cb693a277bc9` |

Both JSON files record Python `3.12.14`, NumPy `2.5.3`, MuJoCo `3.14.0`, benchmark source SHA-256 `0ced4fb07591c299464e88e5810529081632363e91e82b4bf2e6b18498d683e9`, and world source SHA-256 `b386ffb38cf733b6539c2835d833c083204c7c7354211eecd0dc7bd5be863f17`. Earlier development JSON versions (`benchmark_3d_88000.json`, `benchmark_3d_99000.json`, and their `contact_v2` versions) are retained as historical intermediate measurements; the `*_final.json` files are the report basis.

## Interpretation and remaining work

- **Engineering finding:** the 3D benchmark had a real measurement defect and a false hardcoded conclusion. The corrected instrumentation and tests now expose nonzero false arrivals in the original 3D arm.
- **Scientific finding:** the range guard is an exploratory risk/coverage tradeoff, not an acceptable final policy by default. Its very low acceptance requires redesign and a prospective joint safety-and-utility criterion before any confirmatory claim.
- **Next development:** investigate why the planar STOP core fires near the 3D success boundary; develop a 3D-aware arrival/verification interface; test sensor bias, vertical error, latency, dropout, and contact detection with new development fixtures. Freeze the policy only after independent statistical and safety review of the V9-M5 protocol.
- **Physical testing:** not performed. A named robot, controller interface, ground-truth system, containment and emergency stop, hazard review, operator, and approved trial protocol are required before hardware-in-loop or supervised physical trials.
- **Governance:** these changes do not alter or re-authorize V9-M4 Gate B, do not rerun its Holdout, and do not resolve its independent post-execution audit questions.
