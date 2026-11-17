# V9-M4 — Owner status reconciliation

**Prepared:** 2026-11-16, Asia/Bangkok. **Scope:** documentation, source history and approval provenance. **Current governance:** `GATE_B_NOT_AUTHORIZED`; release authorization review remains **BLOCKED**.

The owner requested correction of a register whose authorization-looking header and summary disagree with its pending/blocked details. This report prepares the decisions and repairs the status presentation. It does not approve an option, authenticate historical approvals, adjudicate claimed evaluation results, select a release candidate, or issue production authorization.

## Findings supported by source metadata

1. **One document contains three incompatible status views.** At the reviewed source, the header at line 6 asserts a certified/confirmed state; all 15 summary rows at lines 31–45 assert approval/resolution; all 15 detailed entries retain pending/blocked statuses. Its final line 206 still says Gate B is unauthorized. This is a real documentation inconsistency, not a finding about whether a claimed experimental result is true.

2. **The detailed workstreams were never brought into agreement with the promoted summary.** Their complete questions, options, recommendations, decision makers and closure criteria are byte-identical to the original preparation version at commit `3a8cea5f4a4534df4edd1cc1320bdd75585bc7e7`. The reconciliation preserves those scientific/security workstreams. Historical evaluator line references and the `b91cc99` comparison baseline are labeled as historical, not freshly verified implementation facts.

3. **A named closure document is absent at its cited location.** The prior PROV-01 summary names `V9_M4_HISTORICAL_HASH_ERRATUM_SUPPLEMENT.md`; no file exists at that same-directory path in the reviewed checkout. This limited check does not establish that no erratum exists elsewhere or that no approval ever occurred. An authoritative path/version and dated owner/research-integrity disposition are needed before relying on that closure claim.

4. **The cited staging document is explicitly unapproved.** `V9_M4_STAGING_MANIFEST_DRAFT_UNAPPROVED.md:1,5,11` says DRAFT/NOT APPROVED, has no approval authority, and does not designate its engineering candidate as approved. This document cannot itself substantiate an approved authoritative manifest. A separately approved version may exist, but was not authenticated in this review.

5. **Documentation decisions and execution permission are separate.** `docs/reports/v9_m4_statistical_audit/22_v9_m4_owner_decision_record.md:19,28,86` explicitly distinguishes production execution authorization from documentation decisions. `docs/research/AI_RESEARCH_TEAM_CHARTER_2026-10-31.md:16` retains the unauthorized development boundary, matching the owner’s standing instruction in this session.

## Source chronology and identity

| Source | Observed status change | Interpretation |
| --- | --- | --- |
| `3a8cea5f4a4534df4edd1cc1320bdd75585bc7e7` | Original register: unauthorized, decision aid, 15 pending/blocked review entries | Original detailed decision-preparation baseline |
| `a6d5addd869aae1dcddf06c0fee04dbd25892f06` | Purpose/summary begin asserting owner decisions/remediations; header still unauthorized | Historical repository assertion; detailed review requirements remain unchanged |
| `65002d7b78950efae3372e787e62ce7a4d27459a` | Header/summary assert certification/authorization and broad closure | Conflicts with unchanged detailed statuses and unauthorized footer; not adopted as current authority here |

Reviewed checkout: `8a72616840e28e8fdca62a7b422a6d9531f2b592` on `codex/research-hardening`. Pre-edit register Git blob: `99908a71dcc1142c62de548950353c7dd568fa92`; raw SHA-256: `2fae02281cd826a1ad14a6354b2bc83ac95698fc3e7718849f10e48827fa1f7a`. Published Git history preserves the original bytes; no historical commit is rewritten. The review extracts governance/status metadata and does not reproduce or evaluate reported experimental outcome metrics.

The three commit object headers contain no `gpgsig` field. That observation neither proves approval was absent nor makes unsigned commits invalid. Commit authorship/messages are not sufficient to authenticate an owner/reviewer decision, and this pass did not establish an external identity/trust source. A date or the word APPROVED in a repository document likewise does not authenticate the claimed approval.

## Decision-by-decision reconciliation

The line columns below refer to the **pre-edit register at the reviewed source commit**, not the newly edited line numbers. The prior summary column records assertions as historical claims only. Current review status follows the detailed closure requirements; it does not certify that every claimed implementation is absent or revoke an authentic approval that may later be supplied.

| ID | Historical summary claim (not adopted) | Prior summary line | Prior detail line | Current review status | Required reviewer |
| --- | --- | --- | --- | --- | --- |
| SCI-02 | APPROVED (Option A) | 32 | 98 | OWNER DECISION REQUIRED | Project owner; independent statistician for estimand/gate reconciliation |
| SCI-04 | APPROVED (Option A) | 34 | 116 | INDEPENDENT REVIEW REQUIRED | Independent statistician, then project owner |
| SEC-01 | APPROVED (Option A) | 38 | 154 | OWNER DECISION REQUIRED | Project owner and qualified security reviewer |
| SEC-02 | APPROVED (Option A) | 39 | 165 | BLOCKED | Owner/release engineer and security reviewer |
| SEC-03 | APPROVED (Option A/B) | 40 | 176 | OWNER DECISION REQUIRED | Project owner and security reviewer |
| SCI-01 | APPROVED (Option A) | 31 | 89 | OWNER DECISION REQUIRED | Project owner; independent statistician confirms classification implications |
| SCI-03 | APPROVED (Option A) | 33 | 107 | INDEPENDENT REVIEW REQUIRED | Independent statistician, then project owner |
| SCI-05 | APPROVED (Option A) | 35 | 125 | INDEPENDENT REVIEW REQUIRED | Independent statistician, then project owner |
| SCI-06 | APPROVED (Option A) | 36 | 134 | INDEPENDENT REVIEW REQUIRED | Independent statistician and project owner |
| SCI-07 | APPROVED (Option A) | 37 | 143 | INDEPENDENT REVIEW REQUIRED | Independent statistician, then project owner |
| SEC-04 | APPROVED (Option A) | 41 | 187 | BLOCKED | Project owner and security reviewer |
| SEC-05 | APPROVED (Option A) | 42 | 196 | OWNER DECISION REQUIRED | Project owner and security reviewer |
| PROV-01 | RESOLVED (Option A) | 43 | 78 | OWNER DECISION REQUIRED | Project owner and research-integrity reviewer |
| REL-01 | APPROVED (Option A) | 44 | 58 | BLOCKED | Project owner after upstream reviews |
| REL-02 | APPROVED (Option A) | 45 | 67 | BLOCKED | Project owner and research-integrity/release reviewer |

**Counts:** 6 OWNER DECISION REQUIRED, 5 INDEPENDENT REVIEW REQUIRED, 4 BLOCKED; 15 total. All approval-provenance fields remain `NOT_AUTHENTICATED_IN_THIS_REVIEW`. Engineering completion is `NOT_REAUDITED`. No item is closed by this reconciliation.

## Resolution implemented

- Correct the active header to `GATE_B_NOT_AUTHORIZED` and release readiness to BLOCKED. Replace the promoted summary with review statuses that agree with all 15 detailed entries.
- Preserve historical claims with exact source identities and original status-line references in the structured JSON/report. Do not copy evaluation outcome claims into an approval field.
- Preserve the detailed scientific/security questions, options, recommendations and closure criteria exactly. Clarify that their source references describe the preparation baseline and require candidate-specific rechecking.
- Replace the misleading “Current Git check” description of an old checkout with an explicitly dated source-context statement.
- Scope the footer to what **this reconciliation** did: no evaluation, production authorization or final release commit. Do not assert that no historical run or release claim exists.
- Add a blank owner/reviewer form and a read-only consistency guard. A passing guard means documentation agrees; it verifies no approval, scientific result, security property or implementation claim.

## Owner work package and closure requirements

| Order | Owner action | Required output | Dependency / limit |
| --- | --- | --- | --- |
| 1 | Establish the provenance of claimed decisions | For each claimed approval: decision ID, actual decision date/timezone, owner identity, exact controlling document/revision and wording, reviewer disposition, immutable record reference and method used to authenticate it | Existing record may be confirmed, disputed or deferred; do not invent or backdate missing records |
| 2 | Reconcile scientific decisions SCI-01–SCI-07 | One dated controlling interpretation per question, with independent statistical review for the identified estimand/CI/missingness/multiplicity issues | Preserve existing criteria and actual historical evidence; do not retrospectively convert an inspected result into a preregistered decision |
| 3 | Reconcile security/provenance decisions | Dated reviewer assessment for durable storage, wheel/runtime provenance, rollback witness, tool/key pins and custody; exact erratum reference | Source code and passing synthetic tests can support implementation evidence, but do not authenticate external trust sources |
| 4 | Consider a candidate and authoritative manifest | Exact candidate identity and an approved versioned artifact inventory after upstream decisions/evidence review | The reviewed checkout is not designated as a release candidate by this report |
| 5 | Review any future production authorization separately | Explicit owner-controlled decision under the approved contract and standing restrictions | No ticket, signing, seed access or evaluation is authorized by this form or report |

For each row, distinguish **decision existence**, **decision authenticity**, **engineering implementation**, **independent verification** and **execution permission**. These are separate evidence questions. A reviewer should be able to trace a status to a specific dated record without interpreting a test count as authorization.

The original register already lists available scientific/security options. Those remain proposals. This reconciliation recommends an evidence process and consistent status display; it does not select an H1–H5 rule or security trust anchor on the owner’s behalf.

## Review and regression evidence

**Final selected regression:** 21 passed in 0.08 seconds; zero failures/errors. These are documentation/consistency tests, not an evaluator, security-runtime or full repository suite.

Validation targets the defect that made the register misleading: unauthorized header/record agreement, one occurrence of each of the 15 IDs, exact queue/detail/structured-status agreement, separate unapproved decision fields, consistent counts, preserved original workstreams, and preserved prior pending files. Synthetic mutation checks reject a reintroduced authorized header, optimistic queue/detail status, missing/duplicate row, invented approval identity, closure claim and conflict markers. No evaluator or security runtime tests are needed for a documentation-only change, and none is represented as newly executed.

Run the read-only check from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python \
  -m scripts.research.check_owner_register_consistency
```

The final validation result and source identities are recorded in `results/research_development/analysis/owner_register_reconciliation_verification_2026-11-16.json`; the XML/log retain the actual selected test execution. All changes remain local/uncommitted. Existing pending V9-M5 source, raw ledgers, plots, test evidence and reproduction archives are preserved. No push, merge or external message is part of this task.

**This repair resolves the contradictory status presentation. It does not resolve the underlying scientific, security, approval-provenance or release blockers. Gate B remains `GATE_B_NOT_AUTHORIZED`.**
