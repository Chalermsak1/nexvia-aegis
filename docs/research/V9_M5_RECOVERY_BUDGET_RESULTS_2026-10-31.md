# Recovery budget diagnostic comparison

**Development simulation only; Gate B remains `GATE_B_NOT_AUTHORIZED`.** No confirmatory Holdout, reserved seed contents, production ticket, frozen artifact or V9-M4 decision rule was used or changed.

## Controlled change and evidence

The team added an explicit positive-integer `recovery_steps` benchmark/runner parameter, default100. Alternate budgets are restricted to the two exploratory recovery arms. Both arms receive the same selected constructor value; guidance, speed/anchor checks, STOP criteria and the monitor remain unchanged. Results/manifests record `recovery_steps_limit`. The analyzer checks budget agreement, uniformity and counters while leaving legacy missing values unknown.

The plan `V9_M5_RECOVERY_BUDGET_EXPERIMENT_PLAN_2026-10-31.md` was saved before execution. Its two repeated diagnostic seeds2252000/2254000, two biases and two controllers were crossed with budgets100/300. Direction-preserving guidance and nominal sensor configuration were fixed, overall horizon800/postSTOP50, sixteen total assignments. These are only two previously inspected worlds; findings do not estimate generalization or an independent success probability. Comparing the two new ledgers isolates budget; comparing with older600-step studies would also change overall horizon.

## Outcomes

| Recovery budget | Assigned/completed | Decision-time true STOP | False STOP | Abstain | Timeout |
|---|---:|---:|---:|---:|---:|
| 100 | 8/8 | 0 | 0 | 8 | 0 |
| 300 | 8/8 | 5 | 0 | 3 | 0 |

All five earlier RECOVERY_TIMEOUT assignments reached EXPLORATORY_STABILIZED_ANCHOR_CONFIRMED under budget300, at overall steps400–491. The other three retained exactly the same stopping step and terminal reason: one POSTPROPOSAL_MONITOR_ALARM, two POSTPROPOSAL_RANGE_UNAVAILABLE. Increasing time did not bypass those monitors. No execution errors were recorded.

For these selected worlds, the budget100 limit was an active obstacle to confirmation; the larger limit permits completion with unchanged decision criteria. This is not a recommendation to replace the default or a claim that300 is optimal/safe. Increased exposure and other geometries, faults and noisy trajectories remain untested.

## Physical observations after STOP

Each of the five STOP assignments retained50 post-STOP physics samples (one simulated second at timestep.02), under the existing truth-state CBF braking diagnostic. At decision, observed true distances were .05067–.08157m and true speeds .06550–.09035m/s. Across the recorded post-STOP samples, maximum distance was .08020m and maximum speed .08673m/s; no collision flag appeared.

The system was still moving. In particular, one truth speed at STOP was .09035m/s despite the candidate's measured-speed gate .08m/s: noisy estimated speed does not certify the true speed. The distance stayed within the configured.25m arrival region over this short observed horizon, which is not proof of rest, indefinite stability or real-robot safety. No new stable-stop threshold was invented. Post-STOP records remain terminal-only and can be lost on interruption before terminal persistence.

## Preserved artifacts and verification

- Budget100 raw: `results/research_development/dev/team_recovery_budget_100_v1.jsonl`, SHA-256 `155059bc5bb15b6c9150a107c226175c591f9d81a590f3e478b87aaf87b3a92c`.
- Budget300 raw: `results/research_development/dev/team_recovery_budget_300_v1.jsonl`, SHA-256 `22f1b9236434f89b64322f5afd70c8d60dc69582163d83c9b6bb922d058e4d2d`.
- Matched comparison: `results/research_development/analysis/team_recovery_budget_comparison_v1.json`.
- Tool: `scripts/research/compare_recovery_budgets.py`; validates both inputs, requires identical assignments/settings except budget, retains ERROR/INCOMPLETE and creates output exclusively.

Both ledgers pass the strengthened analyzer; six prior ledgers retain compatibility. Final targeted tests:147 passed; `git diff --check` passed. AI engineering review is not independent statistical approval. Source hashes/runtime are self-reported, not externally authenticated. No commit, push or release decision was performed.

## Next experiment

Predeclare fresh development worlds and a small factorial comparison separating budget100/300 from baseline/direction-preserving guidance; keep all assigned failures and trigger denominators. Examine noisy-speed gate versus true motion descriptively, preserve every raw observation and avoid selecting only successful STOP cases. Extend physical post-abstention/post-STOP logging incrementally before claims about safe fallback. A real-world claim still requires hardware, independent scientific/security review, and explicit owner approvals under the governing protocol.
