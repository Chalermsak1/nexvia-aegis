# Incremental recovery decision evidence

**Exploratory simulation only; Gate B remains `GATE_B_NOT_AUTHORIZED`.** This is not a V9-M4 confirmatory evaluation or real-robot validation.

## Change

The development runner optionally persists each controller decision before its corresponding physics step as a `/2` ledger `PRE_PHYSICS_DECISION` event. The events record sensor availability, decision and the simulator's diagnostic truth state; they are not evidence that the subsequent actuation or physics step occurred. A completed assignment retains the existing final four events and the analyzer checks their equality to the incremental events, the event count, and sequential step numbers. The `/1` reader and runner default remain available. An event write failure propagates instead of being counted as a completed episode; other execution errors remain explicit terminal errors, with prior recorded events retained.

The post-STOP diagnostic horizon is still stored in the terminal record only. A process interruption during that horizon can therefore lose its in-memory samples. The unkeyed hash chain and local fsync provide neither external authentication nor a guarantee against rollback, storage failure, or power loss. A visible record after a write error does not prove durability. The simulated controller still uses simulator truth in parts of its damping and braking path; this work does not establish a deployable safe fallback.

## Fresh development run

With development seeds 2252000–2252001, four fault cases, two biases, two controllers, 350 decision steps and 50 post-STOP diagnostic steps, all 32 assignments completed with no recorded errors. The analyzer verified 11,200 pre-physics events. All 32 episodes timed out at the decision horizon, and the targeted post-proposal vector-loss condition was **never triggered**. Thus this run tests recording and exposes insufficient progress at that horizon, but provides no evidence of resilience to the targeted fault or of post-STOP behavior.

Raw ledger: `results/research_development/dev/recovery_monitor_step_ledger_v2.jsonl`, SHA-256 `1dda32819f6970b290237ef14906f4b9031ea74690f49fc3a944f1fc1dc07f0a`. Summary: `results/research_development/analysis/recovery_monitor_step_ledger_v2_summary.json`. Source hashes and runtime versions are self-reported inside the ledger; they are not independently authenticated.

Synthetic regression checks cover preserved events on an episode error and reject missing, mismatched, out-of-order, and incorrectly typed event records. Existing actual-process interruption tests cover the shared ledger mechanism, not power-loss behavior or all MuJoCo failure modes.

## Targeted diagnostic repeat

Seed 2251001 was deliberately selected because the earlier development study observed a post-proposal vector-loss trigger on it. This is a diagnostic repeat, **not an independent sample**. At a 400-step horizon all 16 assignments completed and 5,826 pre-physics events were retained. For nominal bias, the original anchor-recovery arm again issued STOP after loss; the recovery-monitor arm abstained after loss. For the heavy bias, both arms abstained after loss. Each result is one selected episode per arm and bias; these observations do not establish a detection probability or physical safety. A decision-time STOP is not evidence of stable arrival.

Raw ledger: `results/research_development/dev/recovery_monitor_step_trigger_diagnostic_v2.jsonl`, SHA-256 `75d15e7c863dc196f2129ceb9e8db776763f51110d84457748ac75966ccc0180`. Summary: `results/research_development/analysis/recovery_monitor_step_trigger_diagnostic_v2_summary.json`. Full diagnostic post-STOP samples exist only where a terminal STOP record was completed.

Next, investigate why the fresh seeds failed to reach a proposal within 350 steps, and use a separately specified development experiment to study intermittent faults, missing velocity and post-decision dynamics without selecting seeds based on outcomes. Preserve the distinction between no command, simulated braking and demonstrated physical stopping.
