# V9-M4 synthetic statistical test specification — draft, 2026-10-27

**Classification:** PROPOSED test plan, not an approved decision rule or confirmatory result. **Release:** `BLOCKED — GATE_B_NOT_AUTHORIZED`.

## Boundary and evidence

This specification was prepared by source inspection and isolated arithmetic only. No reserved Holdout seed, manifest, outcome, production launcher, or confirmatory evaluation was opened or run. The checked-out documentation worktree started at `3a8cea5f4a4534df4edd1cc1320bdd75585bc7e7`; the production evaluator is the inherited `b91cc99f591e0b3da3e111a287dc9be3ff44c463` version. Existing tests were **read**, not executed or modified. No executable draft was created: disputed scientific rules would otherwise risk encoding an unapproved pass oracle, and current test helpers load a selected policy (`tests/test_v9_holdout_preflight.py:213-218,359-361`). After approval, create isolated drafts under `research/v9_m4_synthetic_test_drafts/` with an explicit command, no default `test_*.py` discovery path, only invented identities and temporary storage.

**Controlling-source conflict:** Original H1–H5 wording is `docs/v9_experiment_protocol.md:15-37,245-254`; Decision Record 22 differs at `docs/reports/v9_m4_statistical_audit/22_v9_m4_owner_decision_record.md:49-81`; the open decisions are `docs/reports/v9_m4_release_remediation/V9_M4_OWNER_DECISION_REGISTER.md:81-142` and the detailed SCI-01 analysis is `docs/reports/v9_m4_release_remediation/V9_M4_SCI01_OWNER_DECISION_BRIEF.md:9-101`. No test below resolves those conflicts by itself.

**Fixture convention:** Construct episode records entirely in memory with invented, nonreserved `(scenario, seed)` identities, deterministic accepted/true-success/false-success/abstention flags and exact matching keys when required. Use `tmp_path` only for failure-output tests. For mixture `N=1,440`; for scenario `12×120=1,440`, S10 `10×120=1,200`, and compound set `4×120=480` only where the cited source requires them (`docs/v9_experiment_protocol.md:19-37`; Decision 22 `:68-72`). Never copy or derive identities from any reserved manifest. Any expected status name below marked **PROPOSED** requires a dated owner rule.

## H1 — mixture selective risk and coverage (SCI-01)

| ID | Synthetic input | Present/source observation | Competing expected outcomes / required assertion after approval |
| --- | --- | --- | --- |
| H1-01 | Complete `N=1440`; `M=0,K=0`, then `M=58,K=0` | UCB is undefined for `M=0`; existing test expects `INSUFFICIENT_COVERAGE` (`experiments/v9_evaluate_holdout.py:788-796,973-977`; `tests/test_v9_holdout_preflight.py:352-365`). | No H1 pass under either interpretation. Owner/statistician must distinguish complete-data threshold failure from undefined/NOT ESTABLISHED state. Never encode undefined risk as zero. |
| H1-02 | Complete `N=1440,M=59,K=0` | Exact synthetic arithmetic gives coverage `0.040972222`, UCB `0.049507610`; current `h1_passed` ignores coverage (`experiments/v9_evaluate_holdout.py:968-981`). | Original protocol `:22`: H1 fails; Decision 22 `:68,71` / current two-part rule: H1 passes but utility H4 fails. Assert the **approved** interpretation and retain both metrics. |
| H1-03 | Complete `N=1440,K=0`, first `M=503`, then `M=504` | Coverage is `0.349305556` then exactly `0.35`; current evaluator passes H1 in both (`:973-981`). | Three-conjunct interpretation: fail then pass. Two-part interpretation: both H1 pass but separate coverage status changes. Do not round a below-floor ratio into a pass. |
| H1-04 | Complete `N=1440,M=504`, compare `K=16` and `K=17` | Exact CP formula in evaluator (`:788-796`); SCI-01 brief `:38-49` gives synthetic UCBs about `0.047819` and `0.050166`. | CP pass then fail using unrounded bound and `<=0.05`; coverage passes in both. |
| H1-05 | Frozen-policy certification set empty | Original protocol `:15` makes H1/H2 NOT ESTABLISHED. | No formal H1/H2 claim even if invented outcomes appear favorable; fixture must not invoke a production policy loader. |

## H2 — identity, baseline dispute and H1 gate (SCI-02)

| ID | Synthetic input | Source/current behavior | Competing expected outcomes / approval dependency |
| --- | --- | --- | --- |
| H2-01 | Complete mixture with H1 status pass, fail, and unevaluable; S10 subset with `M10=59,K10=0` | Protocol defines core-10 mixture selective-risk CP and fixed-sequence H1→H2 (`docs/v9_experiment_protocol.md:17,24-26`). Evaluator uses whole-mixture paired incidence with no H1 gate (`experiments/v9_evaluate_holdout.py:983-1029`). | If original H2 controls, formal H2 is possible only after approved H1 pass and S10 CP success; otherwise descriptive/not established. If amended H2 controls, owner/statistician must supply exact gate and amended estimand. |
| H2-02 | Pooled `K/N` bound favorable; no baseline rows, then V7-only favorable, then V8 favorable/V7 unfavorable | Current `not h2_results or any(...)` can pass in first two cases and either-one case (`experiments/v9_evaluate_holdout.py:988-1029`). | Original H2 needs no baseline but does need S10 selective-risk rule and H1 gate. Decision-22 incidence H2 needs a separately approved required-baseline and multiplicity rule: possible outcomes include primary-V8 only, both, or separately reported auxiliary V7. Mark unresolved, never treat absence as favorable by default. |
| H2-03 | Same matched pairs in reverse row order, then one missing/duplicate `(seed,scenario)` key | Pairing is keyed and rejects missing/duplicate keys (`experiments/v9_evaluate_holdout.py:678-759`; `tests/test_v9_holdout_preflight.py:823-903`). | Reverse ordering is invariant; incomplete or contradictory pairing withholds any amended paired H2 claim. Exact status PROPOSED. |

## H3 — paired TSR noninferiority (SCI-03)

| ID | Synthetic input | Source/current behavior | Competing expected outcomes / approval dependency |
| --- | --- | --- | --- |
| H3-01 | Full S10 `N=1200` matched policy/V8.1/V7 pairs; vary NOMINAL true successes `112/120` versus `113/120` while holding paired LCB safely above `−0.05` | Protocol requires nominal TSR `>=0.94` (`docs/v9_experiment_protocol.md:28-30`); Decision 22 uses V8.1 primary (`:70,79-81`); evaluator checks both conjuncts (`experiments/v9_evaluate_holdout.py:1212-1256`). | 112 fails nominal guardrail; 113 passes that guardrail. Full H3 pass still requires the controlling paired LCB, independently approved. |
| H3-02 | Paired table `n11=120,n10=2,n01=50,n00=1028` on S10; NOMINAL 120/120 | Existing synthetic test records Student-t LCB `−0.049712` (pass) but Newcombe LCB `−0.050149` (fail), `tests/test_v9_holdout_preflight.py:2280-2297`. Protocol says “Newcombe/Wald” (`docs/v9_experiment_protocol.md:30`); Decision 22 names Student-t authoritative (`:81`). | Student-t-controlled H3 passes; Newcombe-controlled H3 fails. Assert both raw bounds and concurrence/disagreement; formal Boolean awaits independent statistician and owner. |
| H3-03 | V8.1 baseline absent, V7 present and favorable; then V8.1 present but missing or duplicate pair | Current code falls back to V7 (`experiments/v9_evaluate_holdout.py:1294-1303`), while Decision 22 names V8.1 primary (`:79-81`). Pair checker at `:678-759`. | Proposed no substitution: primary H3 NOT_EVALUATED on missing/incomplete V8.1. If owner explicitly approves alternate comparator, that is an estimand amendment requiring statistical review. |

## H4 — compound comparison versus coverage label (SCI-04)

| ID | Synthetic input | Source/current behavior | Competing expected outcomes / approval dependency |
| --- | --- | --- | --- |
| H4-01 | Exactly 480 paired episodes in four registered compound scenarios; discordances `n10=0,n01=5`, then `n10=0,n01=6` (policy false-success is the first member) | Original H4 requires favorable direction and exact **two-sided** McNemar `p<0.05`, plus bootstrap CI reporting (`docs/v9_experiment_protocol.md:32-34`). Standalone exact p values are `0.0625` and `0.03125`. Current H4 is mixture coverage (`experiments/v9_evaluate_holdout.py:979-981`; Decision 22 `:71`). | Registered H4 would fail then pass its McNemar/direction portion; any additional pooled-bound conjunct is unresolved (`docs/v9_experiment_protocol.md:246`). Under Decision-22 H4, these pairs do not enter H4 at all; owner must reconcile the identity. |
| H4-02 | Reverse discordance direction with same exact p; omit V8.1 or one pair; pool incidence UCB favorable/unfavorable independently | Protocol `:32-34,246`; Owner Register `:108-115`; strict pair checker `experiments/v9_evaluate_holdout.py:678-759`. | Reverse direction must not satisfy registered H4; missing controlling pairs make comparison unevaluable. Pooled-bound role may be H4 conjunct, separate gate, or descriptive under source ambiguity; assert only approved branch. |

## H5 — 12-scenario IUT, simultaneous bounds and step-down (SCI-05)

| ID | Synthetic input | Source/current behavior | Competing expected outcomes / approval dependency |
| --- | --- | --- | --- |
| H5-01 | 12 scenarios×120 each; false-success counts `[0]*12`, `[1]*12`, `[0]*11+[2]` | `tests/test_v9_holdout_preflight.py:715-783` already encodes IUT/step-down discordance. Isolated binomial arithmetic gives `p(K=0)=0.002122426`, `p(K=1)=0.015527225`, `p(K=2)=0.057505408` at `n=120,p0=0.05`. | IUT passes first two, fails third; Holm–Šidák rejection counts differ (12, 0, 11 in existing test). If step-down is merely mandatory reporting, second can be H5 incidence-IUT pass; if conjunctive, second fails. This acceptance role is unresolved. |
| H5-02 | One scenario all abstains (`M_s=0,K_s=0`), others complete; then one missing scenario row | Protocol requires selective risk `UNDEFINED` at `M_s=0` plus 12-scenario incidence reporting (`docs/v9_experiment_protocol.md:36-37`); evaluator sets NaNs (`experiments/v9_evaluate_holdout.py:1160-1172`) and checks scenario counts (`:1110-1137`). | No selective-risk success may be inferred from zero accepted. Missing row invalidates partition. Whether defined incidence IUT can pass while selective risk is undefined needs approved claim wording. |
| H5-03 | Same 12 per-scenario p-values, permuted scenario order; one p just on either side of each approved step threshold; compare ordinary Holm and Holm–Šidák | Protocol says Šidák allocation “and Holm step-down” (`:37`); Decision 22 says Holm–Šidák (`:55-56,72`); current code uses Holm–Šidák (`experiments/v9_evaluate_holdout.py:1305-1318`). | Report permutation-invariant adjusted decisions, all one-sided simultaneous incidence and selective-risk bounds, family size, exact threshold; formal role/method awaits statistical decision. No display rounding may set acceptance. |

## Evidence-state, execution, multiplicity and aggregate-claim tests (SCI-06/07)

| ID | Synthetic input | Source/current behavior | Competing expected outcomes / approval dependency |
| --- | --- | --- | --- |
| X-01 | 1,439 well-formed mixture rows against an independently declared expected 1,440; duplicate index; invalid `accepted != TS+FS`; conflicting report count | Mixture evaluator self-sizes expected count (`experiments/v9_evaluate_holdout.py:945-959`); integrity rejects duplicate/algebra contradictions (`:645-673`). | Proposed: no statistical pass from incomplete/contradictory evidence, retain evidence and explicit invalid/unevaluable status. Exact status and authorized reconciliation are SCI-06 decisions. |
| X-02 | Synthetic worker exception after three rows, partial CSV/invalid marker in temporary directory | Production pipeline preserves partial evidence, writes `INCOMPLETE_INVALID`, raises before analysis (`experiments/v9_evaluate_holdout.py:2029-2060`); existing mock test `tests/test_v9_holdout_preflight.py:1221-1258`. | Preserve raw partial output and error; never convert `m_accepted` or partial favorable counts into H1–H5 acceptance. No production launcher invocation for this draft. |
| X-03 | Mixture H1/coverage favorable but synthetic Scenario H3, registered H4, or H5 fails/is absent | Current mixture evaluator can issue `CERTIFIED_OPERATIONAL_IMPROVEMENT` from H1+coverage alone (`experiments/v9_evaluate_holdout.py:1033-1039`); protocol's anti-gaming rule is necessary but no complete positive aggregate rule (`docs/v9_experiment_protocol.md:254`; Owner Register `:135-142`). | Proposed: suppress aggregate certification pending independently reviewed, owner-approved cross-partition dependency and multiplicity plan. Existing label is an unsupported possibility, not accepted evidence. |
| X-04 | Every secondary component favorable, then each one missing or contradictory; H1 pass/fail/unevaluable toggled | Explicit fixed-sequence adjustment covers H1→H2 only (`docs/v9_experiment_protocol.md:17`); secondary H3–H5 family is unresolved (`Owner Register:135-142`). | Assert component values independently; no implicit familywise or aggregate pass until exact family, adjustment, missing-state propagation and report labels are approved. |

## Safe verification actually performed

1. `git worktree list --porcelain` and `git status --short --untracked-files=all` showed the original `codex/v9-m4-remediation` checkout at `b91cc99` and clean documentation branch at `3a8cea5` before new documents were written. This records local state, not remote or release authenticity.
2. Source inspection used `nl -ba docs/v9_experiment_protocol.md | sed -n '15,40p'`, `nl -ba docs/reports/v9_m4_statistical_audit/22_v9_m4_owner_decision_record.md | sed -n '64,85p'`, and `nl -ba experiments/v9_evaluate_holdout.py | sed -n '983,1039p;1100,1180p;1210,1319p;1360,1385p'`, plus the cited test-source line ranges. The observed output is the exact numbered source cited in the matrices above. No pytest or evaluator was run for this specification.
3. The exact standalone arithmetic probe was:

   ```sh
   python3 - <<'PY'
   from math import comb
   for m in (58, 59, 503, 504):
       print(f'H1_SYNTH N=1440 M={m} K=0 coverage={m/1440:.9f} UCB={1-0.05**(1/m):.9f}')
   for k in (0, 1, 2):
       p = sum(comb(120,j)*0.05**j*0.95**(120-j) for j in range(k+1))
       print(f'H5_SYNTH n=120 K={k} p_inc={p:.9f}')
   for discordant in (5, 6):
       print(f'H4_SYNTH n10=0 n01={discordant} exact_two_sided_p={2*(0.5**discordant):.9f}')
   print(f'H3_SYNTH nominal_112={112/120:.9f} nominal_113={113/120:.9f}')
   PY
   ```

   Actual output: H1 `M=58/59/503/504` coverage `0.040277778/0.040972222/0.349305556/0.350000000`, UCB `0.050339338/0.049507610/0.005938030/0.005926283`; H5 `K=0/1/2` p values `0.002122426/0.015527225/0.057505408`; H4 discordances `0:5/0:6` two-sided exact p `0.062500000/0.031250000`; NOMINAL `112/120=0.933333333`, `113/120=0.941666667`. These are arithmetic checks, **not executed hypothesis tests on project data**.

## Approval and closure

Before implementation, the owner must date the controlling H1–H5 identities, complete acceptance and missing-evidence rules, permitted aggregate claims, and status vocabulary. Independent statistical review is required for H3 CI/baseline, H4 pooled-bound role, H5 multiplicity/family, secondary-family and aggregate claims; SCI-01 confirmation and SCI-02 amendment review as described in the Owner Register (`:199-203`). Engineering may then convert the relevant rows to isolated executable synthetic fixtures, run them in an authorized safe environment, and record commands, exact results and artifact hashes. This document records no such execution or approval.

**Overall: `BLOCKED — GATE_B_NOT_AUTHORIZED`.**
