# V9-M5 research and tool development handoff

**State:** exploratory development on `codex/research-hardening`, based on `3acff8ff42fcc2784e210ff8608158b549c4cbe0`. No V9-M4 Holdout was run, no reserved Holdout seed contents or raw outcomes were accessed, and no production ticket or scientific decision rule was changed. The new study remains a proposal awaiting independent statistical and owner approval for a confirmatory stage.

## Deliverables

- [Single-robot study plan](V9_M5_SINGLE_ROBOT_STUDY_PLAN_DRAFT.md): proposed hypotheses, comparator arms, fault matrix, endpoint definitions, missing-evidence handling, and explicit unresolved owner/statistician decisions.
- [Research-tool product brief](AEGIS_RESEARCH_TOOL_PRODUCT_BRIEF_DRAFT.md): user hypotheses, MVP, customer interview and pilot plans, and distinction between existing functionality and future features.
- `experiments/benchmark_physical_3d_cbf.py`: development-only no-active-probing ablation, separately seeded anchor randomness, corrected STOP timing for baseline arms, and source hashes including the 3D controller.
- `scripts/research/summarize_3d_development.py`: offline validation and descriptive reports by arm, bias scenario and optionally matched seed/bias against an explicit baseline.
- `tests/test_3d_ablation_reproducibility.py` and `tests/test_3d_development_summary.py`: synthetic regressions for the ablation, sensor-stream pairing, terminal timing, input integrity, missing baselines, and output preservation.

## Development run and interpretation

The retained v2 run used 5 development seeds × 3 vector biases × 8 controller arms = **120 episode records**, each with at most 100 steps. The 3D-aware arm produced 6 true successes, 2 false arrivals, 2 abstentions and 5 timeouts; the no-active-probing ablation produced 3 true successes, 0 false arrivals, 11 abstentions and 1 timeout, each out of 15. The matched descriptive counts show three pairs where both succeeded, three where only the 3D-aware arm succeeded, and two where only the 3D-aware arm had false arrivals. This is a small development sample with repeated seeds; it does not establish treatment effects or safety.

```bash
PYTHONPATH=src .venv/bin/python experiments/benchmark_physical_3d_cbf.py \
  --seed-start 2234000 --n-seeds 5 --max-steps 100 --include-3d-no-probe \
  --output results/research_development/dev/3d_probe_ablation_v2.json

.venv/bin/python scripts/research/summarize_3d_development.py \
  results/research_development/dev/3d_probe_ablation_v2.json \
  --baseline AEGIS_3D_NO_ACTIVE_PROBE \
  --output-dir results/research_development/analysis/3d_probe_ablation_paired
```

Both output locations must be new for reruns; these exact paths already exist and are evidence. Choose fresh paths to reproduce without overwriting. A prior `3d_probe_ablation_smoke.json` is retained as intermediate evidence, before baseline STOP timing was corrected.

| File | SHA-256 |
|---|---|
| `results/research_development/dev/3d_probe_ablation_v2.json` | `198c29e9e6bbf3315ede26bae2581bd47608dc6f1795ced821e28bd29b2b6eb7` |
| `results/research_development/dev/3d_probe_ablation_v2.log` | `0fa9386909d052d9a939b242f2de683231221e5e047a8baa4eb1a4be17965787` |
| `experiments/benchmark_physical_3d_cbf.py` | `042dfff39936612a99c7fdf4d3cac03e330e4cefb961c353b081e5a2718c256b` |

The paired report records the input and analyzer hashes. It validates completeness against the **self-declared** design, which cannot substitute for an independently controlled assignment manifest or verify every controller dependency. The generated CSV/JSON/Markdown do not contain a pass/fail claim or confidence interval.

## Verification and remaining work

The selected regression suite passed **84 tests**, covering the new analyzer and ablation plus adjacent 3D, watchdog, swarm, simulation and control components. A full suite remains unavailable in the current environment because `torch` is not installed. The new ablation retains ordinary range confirmation and abstains rather than initiating active probing or anchor acquisition; it is not an ablation of every verification behavior.

Further work: review sensor and action parity, record failures and exceptions as assigned outcomes, add event-level diagnostics, obtain independent statistical approval of the prospective test design and H2 identity rule, and interview potential users before claiming demand. Live ROS transport remains disabled; no hardware is available for physical validation.
