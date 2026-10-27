# V9-M4 SCI-01 — Owner Decision Brief: H1 Mixture Coverage

**Status:** OWNER DECISION REQUIRED; SCI-01 unapproved. **Release:** BLOCKED. **Governance:** `GATE_B_NOT_AUTHORIZED`.

**Scope and method.** This brief compares the checked-in protocol, Decision Record 22, Owner Decision Register, evaluator, and tests by source inspection. The numerical examples below use invented counts only. No reserved seeds, Holdout outcomes, confirmatory runs, ticket, or frozen artifact were accessed or changed. All paths and line numbers below are relative to the documentation worktree root. Its checked-out HEAD when this brief was prepared was `b91cc99f591e0b3da3e111a287dc9be3ff44c463`; the Owner Decision Register was then an untracked worktree document, not part of that reviewed commit.

## Decision question

For an otherwise complete and valid 12-scenario mixture evaluation, must **formal H1 pass** require the conjunction

`M_mix >= 59 AND U_CP,one-sided-95%(K_mix,M_mix) <= 0.05 AND M_mix/N_mix >= 0.35`,

or may H1 pass on the first two conditions while coverage is assessed only as a separate utility guardrail? Here `N_mix` is the number of required mixture episodes, `M_mix` accepted decisions, and `K_mix` false successes among accepted decisions. The registered mixture partition has `N_mix = 1,440` in Decision Record 22 (`docs/reports/v9_m4_statistical_audit/22_v9_m4_owner_decision_record.md:68,71`); the explicit H1 rule is in the original protocol (`docs/v9_experiment_protocol.md:19-22`). This decision also determines whether H1 can open the registered H1→H2 fixed-sequence gate (`docs/v9_experiment_protocol.md:17,24-26`). The distinct H2 definition dispute is SCI-02 and is not decided here.

## Authoritative evidence and conflict

| Source | Exact operative evidence | Meaning for SCI-01 |
| --- | --- | --- |
| Original preregistered protocol, `docs/v9_experiment_protocol.md:19-22` | H1 is mixture selective-risk certification; line 22 calls its **“Confirmatory Pass Criterion”** `M >= 59` **and** exact one-sided 95% Clopper–Pearson UCB `<= 0.05` **and** empirical mixture coverage `>= C_min = 0.35`. | Direct and explicit support for all three H1 conjuncts. The null/alternative at lines 20-21 use population coverage `C > 0`, rather than the empirical `0.35` threshold; the statistical relationship needs independent review. |
| Same protocol, `docs/v9_experiment_protocol.md:15,17,24-26` | Frozen policy only; empty certified Calibration set makes H1/H2 NOT ESTABLISHED; H2 formal certification is conditional on H1 pass at `delta=0.05`. | A low-coverage H1 result has downstream gatekeeping consequences. |
| Same protocol, `docs/v9_experiment_protocol.md:241,245,248,254` | The outcomes table abbreviates H1 as `M >= 59` plus UCB, labels `M/N >= 0.35` an overall utility guardrail, and bars low-coverage risk reduction from an overall operational-improvement claim. | Supports separate *reporting* of utility, but conflicts internally with the explicit three-part H1 pass criterion at line 22. The target `>= 0.45` at line 248 is not an H1 acceptance threshold. |
| Decision Record 22, `docs/reports/v9_m4_statistical_audit/22_v9_m4_owner_decision_record.md:47-52,62-71` | It describes H1 as `M >= 59` plus UCB and puts `M/N >= 0.35` under H4, stating `M >= 504` for `N=1,440`. | Supports a separate H4/utility interpretation, but its claim that corrections preserve governing criteria does not reconcile the explicit protocol line 22. A later decision record cannot silently remove that registered conjunct. |
| Owner Decision Register, `docs/reports/v9_m4_release_remediation/V9_M4_OWNER_DECISION_REGISTER.md:81-88` | SCI-01 is `P0`, recommends all three as a proposal, asks for dated owner decision and independent statistical confirmation, and remains OWNER DECISION REQUIRED. | This is a decision request, not approval. |
| Current evaluator, `experiments/v9_evaluate_holdout.py:945-981,1033-1039` | It computes `coverage=M/N`, but `h1_passed` checks only `M>=59` and UCB. Coverage is separate `h4_passed`. Low coverage may produce `CONSERVATIVE_RISK_COVERAGE_TRADEOFF` while the H1 field still says `CONFIRMATORY_PASS`. | Implements the two-part interpretation and can disagree with the explicit registered H1 criterion. Overall classification does not cure the H1-field false-pass. |
| Existing tests, `tests/test_v9_holdout_preflight.py:213-239,352-392` | An `M=60,N=100,K=0` synthetic case tests a pass at 60% coverage; an all-abstain case tests H1 false and undefined selective risk; other assertions expect distinct H1/H4 fields. | They do not test a UCB-qualified H1 result with coverage below 0.35. |

**Source hierarchy requiring an owner ruling:** The protocol's specifically named confirmatory H1 criterion at line 22 is the strongest direct wording. Its own table at lines 245/248 and Decision Record 22 nonetheless create a real documentary inconsistency. The engineering team must record an explicit controlling interpretation and disposition of both conflicting passages; this brief does not itself change the preregistration or authenticate statistical approval.

## Options, scientific implications, and proposed recommendation

| Option | Advantages | Risks and required report/evaluator changes | Preregistration impact |
| --- | --- | --- | --- |
| **A — All three H1 conjuncts.** Coverage is both an H1 pass precondition and a separately reported utility measure. | Follows the literal, named confirmatory criterion (`docs/v9_experiment_protocol.md:22`); prevents H1 certification at very low acceptance; makes the H1→H2 gate depend on the full registered criterion. | Change H1 decision logic, H1 status/reason, report schema or wording, and H2 gate tests after approval. Continue reporting coverage separately without allowing the H4 label to imply that its failure is irrelevant to H1. Clarify protocol table and Decision 22 prospectively in a dated reconciliation; preserve history. | Best read as clarification/enforcement of the explicit criterion, but the internal protocol conflict and inferential meaning require independent confirmation. |
| **B — Two-part H1; coverage only an independent utility guardrail.** | Aligns with the protocol's table shorthand (`docs/v9_experiment_protocol.md:245,248`) and Decision 22 (`:68,71`); keeps selective-risk and utility fields separate. | A result can be labeled `H1 CONFIRMATORY_PASS` despite failing the literal line-22 criterion. H2 might then open at low coverage. Merely blocking an *overall operational-improvement* label does not remove the H1 false-pass. Requires explicit amendment of line 22, H1/H2 claim language, and reports before any confirmatory claim. | Substantive change to the documented H1 pass rule unless the owner and independent statistician justify the earlier line 22 as an error through a dated amendment. |

**Technical recommendation, not an approval:** Choose **A**, subject to a dated owner decision and independent statistical review. It preserves the most explicit preregistered wording and closes the observable false-pass path. Maintain a separate coverage field for transparency, but make H1 `CONFIRMATORY_PASS` impossible unless all three registered conditions are established from a complete, authenticated mixture partition. If the owner selects B, record it as a prospective protocol amendment, identify which future claims are confirmatory, and resolve H1→H2 gatekeeping before implementation. Neither choice authorizes Gate B.

### Synthetic boundary demonstration (not experimental results)

Using only arithmetic with a hypothetical `N=1,440`, `K=0`, and the evaluator's exact UCB formula (`experiments/v9_evaluate_holdout.py:788-796`), the following distinguishes the current code rule from the literal protocol rule. Values are rounded **for display only**; comparisons must use unrounded calculations.

| Hypothetical `M` | `M/N` | One-sided 95% CP UCB | Current H1 (`M` + UCB) | Explicit protocol H1 (all three) |
| ---: | ---: | ---: | :---: | :---: |
| 0 | 0 | undefined | fail | fail |
| 58 | 0.040278 | 0.050339 | fail | fail |
| 59 | 0.040972 | 0.049508 | **pass** | **fail** |
| 503 | 0.349306 | 0.005938 | **pass** | **fail** |
| 504 | 0.350000 | 0.005926 | pass | pass |

At `N=1,440, M=504`, the synthetic CP boundary is `K=16: UCB≈0.047819` (pass) and `K=17: UCB≈0.050166` (fail). These examples show a **classification possibility**, not that any real result has this pattern. Since `0.35 × 1,440 = 504`, the `M>=59` condition is arithmetically redundant when the complete `N=1,440` coverage conjunct is enforced; whether it should remain in the formal rule for continuity and interpretation requires statistical confirmation.

## Missing, incomplete, and contradictory evidence — proposed handling only

These are proposed SCI-01 decision rules for owner/statistician review, not current approved behavior. They should be kept distinct from a valid, complete H1 result that genuinely fails a threshold.

| Case | Source evidence / present behavior | Proposed treatment and decision needed |
| --- | --- | --- |
| `M=0` with complete valid partition | Selective risk is undefined; current test expects H1 false, `INSUFFICIENT_COVERAGE` (`tests/test_v9_holdout_preflight.py:352-365`); UCB code returns NaN at denominator 0 (`experiments/v9_evaluate_holdout.py:788-793`). | No H1 pass and no H2 formal claim. Decide whether to label a complete all-abstain evaluation as an evaluable **H1 failure** or as **NOT ESTABLISHED** because selective risk is undefined; never report risk as zero. |
| Fewer than the required mixture episodes, missing rows/IDs, or unknown `N` | `evaluate_mixture_holdout` calls the integrity checker with `len(records)` as its own expected count (`experiments/v9_evaluate_holdout.py:945-959`); the checker then tests equality against that self-sized count (`:659-673`). Thus a well-formed prefix can pass this check. | Require independently authenticated expected count and episode identities before H1 evaluation. Mark missing/partial input `INCOMPLETE_INVALID`/`NOT_EVALUATED` (exact labels to be approved), retain raw evidence, and never shrink the denominator to make coverage pass. |
| Duplicate index or contradictory outcome algebra | Duplicate indices and algebra violations raise (`experiments/v9_evaluate_holdout.py:645-673`). | Treat as invalid evidence with no H1 pass; preserve error and raw output. Decide the canonical report status and whether repair/re-execution is permissible under governance. |
| Reported `N`, `M`, `K`, or coverage contradicts authenticated episode records or manifest | Counts are currently recomputed from records (`experiments/v9_evaluate_holdout.py:959-971`), but that alone does not prove manifest completeness. | Reconcile records to authenticated manifest and report. Until reconciliation, withhold H1 certification and H2 gate. Do not pick whichever conflicting number favors passing. |
| Execution failure / partial CSV | Pipeline writes partial CSV plus `INCOMPLETE_INVALID` marker and raises; analysis follows only after successful execution (`experiments/v9_evaluate_holdout.py:2029-2060`; synthetic test `tests/test_v9_holdout_preflight.py:1221-1258`). | Preserve partial evidence and classify H1 **not evaluated**, not a scientific threshold failure or pass. Decide exact status propagation across launcher, evaluator, and owner report. |
| Full valid partition, any one of the three thresholds false | Explicit conjunctive criterion (`docs/v9_experiment_protocol.md:22`). | Under Option A, H1 does not pass, record which conjunct failed, retain all metric values, and do not open formal H2 gate. A different classification requires an approved amendment. |

## Questions for independent statistical review

1. Does enforcing empirical `M/N>=0.35` as a formal H1 conjunct preserve the preregistered test's Type-I and familywise claims, given that H1's null/alternative state population coverage `C>0` (`docs/v9_experiment_protocol.md:17,20-22`)? How should the claim be worded?
2. Is `M>=59` retained as a separately reported registered safeguard despite being implied by `M/N>=0.35` at complete `N=1,440`, and what happens if an authorized future design uses another `N`?
3. What are the scientifically correct states for valid `M=0`, valid low coverage, invalid/incomplete evidence, and contradictory records? Which states may open H2's formal gate?
4. Should coverage remain a separately reported utility/H4 field while also being an H1 conjunct, and how should Decision Record 22's `H4` terminology be reconciled with the original protocol's other use of `H4` (`docs/v9_experiment_protocol.md:246,248`)?
5. Confirm exact CP implementation and numerical boundary handling (`<=`, no rounded-display decisions), and whether any multiplicity adjustment beyond the registered H1→H2 fixed sequence is needed for this interpretation.

Independent review is an input to the owner's decision; this document is neither a statistician's signed opinion nor an approval record.

## Required synthetic tests before any approved implementation

Use in-memory, invented episode records and temporary files with synthetic identifiers only. No reserved-seed manifest, production launcher, or Holdout outcome file is needed. Expected classifications below assume proposed **Option A** and complete authenticated `N=1,440` except where stated.

| Test | Synthetic fixture | Required assertion after rule approval |
| --- | --- | --- |
| Acceptance-count boundary | `(N,M,K)=(1440,0,0),(1440,58,0),(1440,59,0)` | None passes H1: undefined risk at `M=0`, `M<59` at 58, and low coverage at 59 despite passing UCB. Display status distinguishes undefined/inadequate coverage as approved. |
| Coverage boundary | `(1440,503,0)` and `(1440,504,0)` | First H1 fails solely coverage; second H1 passes all three; coverage computed from full 1,440 denominator, without rounding. |
| CP boundary with adequate coverage | `(1440,504,16)` and `(1440,504,17)` | First passes CP and H1; second fails CP and H1, with exact unrounded UCB. |
| Missing or shortened partition | 1,439 valid synthetic records against an **independent** expected count of 1,440; missing manifest identity; unknown `N` | No H1/H2 certification or pass output; explicit incomplete/unevaluable marker. A self-sized 1,439 count is insufficient. |
| Contradictory evidence | Duplicate episode index; `accepted != true_success + false_success`; report count differing from records | Fail integrity/reconciliation and suppress formal pass, retaining diagnostic and raw evidence. |
| Execution failure | Injected synthetic exception after a few records, as in `tests/test_v9_holdout_preflight.py:1221-1258` | Partial CSV and invalid marker retained; no complete H1 report or H2 claim. |
| H1→H2 gate | Stub otherwise H2-qualifying synthetic evidence while H1 is low-coverage, CP-failing, or unevaluable, then all-three-passing | Formal H2 claim blocked in first three states; may be evaluated for formal claim only in the last state, subject to separate SCI-02 approval. |
| Report consistency | Inspect serialized H1 result, coverage field, utility classification, and authorization/statistical status for each boundary case | No `CONFIRMATORY_PASS` H1 when any registered conjunct is false or unverified; an overall trade-off label never masks an H1 mismatch. |

These are test specifications only; no evaluator or statistical decision logic was modified in preparing this brief.

## Owner decision field — explicitly unapproved

- **SCI-01 decision:** `UNAPPROVED / PENDING`.
- **Chosen option:** [ ] A — all three H1 conjuncts; [ ] B — two-part H1 with separate utility guardrail and documented preregistration amendment; [ ] other, with exact controlling wording: __________.
- **Controlling wording and disposition of protocol lines 22/245/248 and Decision 22 lines 68/71:** __________.
- **Approved handling of missing, invalid, and contradictory evidence; H1→H2 gate consequence:** __________.
- **Independent statistician, dated review, and any conditions:** __________.
- **Project owner, dated signature/approval:** __________.

**Release disposition:** SCI-01 remains open; the overall release remains **BLOCKED**, Gate B remains **`GATE_B_NOT_AUTHORIZED`**, and no final release or confirmatory pass is asserted.
