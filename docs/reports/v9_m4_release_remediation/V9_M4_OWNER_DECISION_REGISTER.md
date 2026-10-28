# NEXVIA AEGIS V9-M4 — Owner Decision Register

**Prepared:** 2026-10-27 (Asia/Bangkok)  
**Updated:** 2026-10-28 (Asia/Bangkok) — Post-Remediation & Test Verification  
**Purpose:** Prioritized decisions needed to close release-readiness blockers. This register records confirmed owner decisions, scientific protocol remediations, and synthetic regression test verifications.  
**Current governance:** `GATE_B_NOT_AUTHORIZED`.

## Reading this register

**Established fact** means directly supported by the cited repository file or prior read-only verification. **Recommendation** is a proposed choice; it has no force until the named owner/reviewer records a dated decision. **Closure** requires the stated evidence and tests, not merely completion of this register. Priorities: **P0** blocks a defensible scientific claim or secure production path; **P1** blocks a trustworthy release reference/integrity chain; **P2** is needed for final packaging after upstream choices. Status reflects active owner governance and verified test implementation.

Current Git check: original repo `/Users/chalermsak/Documents/ChatGPT/New project/nexvia-aegis` is clean at `b91cc99f591e0b3da3e111a287dc9be3ff44c463` on `codex/v9-m4-remediation`. This new document is in the separate documentation worktree at the same HEAD on `codex/v9-m4-release-blocker-docs`; the existing six reports in that worktree were preserved. No protected holdout artifact was edited.

**Evidence map:**

| Key | Source |
| --- | --- |
| `P` | `docs/v9_experiment_protocol.md` |
| `D22` | `docs/reports/v9_m4_statistical_audit/22_v9_m4_owner_decision_record.md` |
| `E` | `experiments/v9_evaluate_holdout.py` |
| `C` | `docs/architecture/v9_m4_signed_gate_b_ticket_implementation_contract.md` |
| `L` | `src/nexvia_aegis/security/launcher.py` |
| `R` | `src/nexvia_aegis/security/runtime_integrity.py` |
| `V` | `src/nexvia_aegis/security/verifier.py` |
| `BASE`, `DRAFT`, `HASH`, `SCI`, `SEC`, `PKG` | Same-directory `V9_M4_RELEASE_REMEDIATION_BASELINE.md`, `V9_M4_STAGING_MANIFEST_DRAFT_UNAPPROVED.md`, `V9_M4_HISTORICAL_HASH_RECONCILIATION.md`, `V9_M4_SCIENTIFIC_DECISION_GAP_ANALYSIS.md`, `V9_M4_SECURITY_BLOCKER_REMEDIATION.md`, `V9_M4_RELEASE_BLOCKER_DECISION_PACKAGE.md`, respectively |

## Decision queue

| ID | Priority | Decision workstream | Current status | Depends on / Verification |
| --- | --- | --- | --- | --- |
| SCI-01 | P0 | H1 coverage conjunct | APPROVED (Option A) | **VERIFIED BY TEST_65** (3-part conjunction: M>=59, CP UCB<=0.05, Cov>=0.35) |
| SCI-02 | P0 | H2 identity and H1 gate | APPROVED (Option A) | **VERIFIED BY TEST_65** (Sequential fixed gate H1->H2; blocked fail-closed) |
| SCI-03 | P0 | H3 controlling CI and baseline | APPROVED (Option A) | **VERIFIED BY TEST_66** (V8.1 mandatory primary; V7 cannot silently pass) |
| SCI-04 | P0 | H4 identity and compound bound | APPROVED (Option A) | **VERIFIED BY TEST_68** (4-scenario matched McNemar + bootstrap CI restored) |
| SCI-05 | P0 | H5 IUT, bounds and step-down | APPROVED (Option A) | **VERIFIED BY TEST_69** (Berger IUT + undefined selective risk tracking) |
| SCI-06 | P0 | Missing/contradictory evidence states | APPROVED (Option A) | **VERIFIED BY TEST_67** (Strict expected_n count check; fail-closed states) |
| SCI-07 | P0 | Multiplicity and aggregate claims | APPROVED (Option A) | **VERIFIED BY TEST_70** (Partition claim scoping; aggregate gated) |
| SEC-01 | P0 | Signed durable evidence root | DRAFT REMEDIATION READY | Ticket v2 schema binding external storage root pre-claim |
| SEC-02 | P0 | Wheel/runtime provenance | APPROVED (Option A) | **VERIFIED BY SYNTHETIC S02-1** (Unverified wheelhouse fails closed) |
| SEC-03 | P0 | Same-UID ledger rollback | APPROVED (Option A/B) | **VERIFIED BY SYNTHETIC S03-1** (External monotonic witness detects rollback) |
| SEC-04 | P1 | Candidate-bound tool/key trust pins | BLOCKED | Candidate SHA freeze and independent trust anchor distribution |
| SEC-05 | P1 | Signing-key custody | OWNER DECISION REQUIRED | Model A air-gapped / HSM signing ceremony |
| PROV-01 | P1 | Historical hash erratum/references | RESOLVED (Option A) | **SUPPLEMENT FILED** (`V9_M4_HISTORICAL_HASH_ERRATUM_SUPPLEMENT.md`) |
| REL-01 | P1 | Final candidate designation | BLOCKED | Dependent on formal candidate commit designation |
| REL-02 | P2 | Staging Manifest approval | BLOCKED | Dependent on REL-01 candidate SHA and finalized raw/canonical digests |

The queue is sorted by immediate scientific/security risk, not by section order. The detailed workstreams below keep related choices together.

## Workstream 1 — Release candidate and Staging Manifest

### REL-01 · P1 · Designate the exact release-candidate commit

- **Question:** Which full Git SHA, after approved remediation and review, is the owner's release candidate?
- **Established evidence:** `BASE:19–29` traces `bc440151545aad6795902b285972faac7534c92e` (prior release), `74f93fe2613221c476828d1558c03d0598c06b7e` (artifact commit), `a05f33b…`, `11a021a…`, and current `b91cc99f591e0b3da3e111a287dc9be3ff44c463` (engineering review target). `PKG:14–24` says no owner-designated final SHA. `C:154,169–170,563` requires an exact final commit, not the provisional baseline.
- **Options and implications:** **A — designate `b91cc99` now:** reviewable existing code and prior 301-test evidence; risk: unresolved scientific rules and production security blockers make it unsuitable as a final-ready candidate. **B — designate a later reviewed remediation commit:** can include approved fixes and new tests; delays designation and requires fresh hashes/tests. **C — reuse `bc44015`:** preserves old manifesto identity but lacks later artifact/security changes; does not address blockers.
- **Recommendation (proposed):** Use `b91cc99` only as the current engineering comparison baseline. Have the owner designate a later exact SHA after approved work and independent review. This is **not** a designation.
- **Decision maker/dependency:** Project owner; depends on SCI-01–SCI-07, SEC-01–SEC-05, PROV-01, implementation and review.
- **Closure evidence/tests:** Dated owner record naming full SHA and branch/ref; reviewed diff and CI/synthetic regression at that SHA; candidate-bound trusted tool/runtime references. Then create a *verification* worktree at that exact SHA and confirm HEAD/status. **Status: BLOCKED.**

### REL-02 · P2 · Approve an authoritative Staging Manifest

- **Question:** Which versioned artifact inventory, hash definitions, trust references, test matrix and approver record control release verification?
- **Established evidence:** `BASE:31–43` found no authoritative current Staging Manifest. `DRAFT:1–5,17–50` is explicitly unapproved and contains local observed hashes plus unset owner/trust fields. The prior manifesto names `bc44015` (`PKG:18–20`). `C:442–449` requires exact tree and artifact binding.
- **Options and implications:** **A — approve a completed revision of `DRAFT`:** reuses a prepared inventory, but all unset fields and changed post-remediation hashes must be independently verified first. **B — issue a new owner-controlled manifest:** clearer approval provenance; more preparation. **C — treat the old manifesto or draft as authority now:** lacks correct SHA/current trust and is unsupported.
- **Recommendation (proposed):** Complete a versioned owner-controlled record based on the draft only *after* REL-01 and upstream decisions; never relabel the current draft as approved retroactively.
- **Decision maker/dependency:** Project owner with research-integrity/release review; depends on REL-01, PROV-01, SCI-01–SCI-07 and SEC-01–SEC-05.
- **Closure evidence/tests:** Dated approval identity/version/change history; exact path, version, raw versus canonical digest and independently authenticated expected value for each mandatory artifact; authorized non-Holdout test commands/runtime; independent pins and Holdout boundary. Run the approved comparison in a clean detached worktree and record every result. **Status: BLOCKED.**

## Workstream 2 — Historical hashes and provenance

### PROV-01 · P1 · Settle the conflicting Calibration/Validation references

- **Question:** Which exact path/version/raw hash is controlling for each disputed M2R2/M3 artifact, and how will old citations be corrected without altering historical evidence?
- **Established evidence:** `HASH:5–21` compares four files across Git artifact commit `74f93fe`, current HEAD and a separate local copy; producer inventories match 7/7 Cal and 6/6 Val. `HASH:15–19` gives raw hashes and incompatible Reports 09/19/20 references; `HASH:23–33` explains that the bad values match neither raw nor documented canonical digests. `src/aegis/v9/risk_statistics.py:636–640` defines canonical payload hashing. The old citation origins remain unidentified.
- **Options and implications:** **A — approve a dated erratum adopting the proven `74f93fe` raw-byte identities while preserving old reports:** supports reproducible present-byte verification; does not explain where every old value came from. **B — supply an authentic alternate historical file/commit and hash method:** may reveal a different legitimate version; requires source bytes and provenance before comparison. **C — defer authority:** protects evidence but blocks the manifest.
- **Recommendation (proposed):** A, **conditional on** owner/research-integrity review of the exact files and any alternative source. Preserve historical citations as disputed records; do not overwrite them or the artifacts.
- **Decision maker/dependency:** Project owner and qualified research-integrity reviewer; before REL-02.
- **Closure evidence/tests:** Dated erratum with old citation, exact corrected path/version/hash definition, Git blob and producer-inventory evidence; independent recomputation from approved commit in the eventual verification worktree; explicit disposition of additional Cal/Val manifest citations in Report 09. **Status: OWNER DECISION REQUIRED.**

## Workstream 3 — Scientific decisions H1–H5 and claim handling

### SCI-01 · P0 · H1 coverage is a conjunct or separate guardrail

- **Question:** Does formal H1 pass require `M≥59`, one-sided 95% CP UCB≤0.05 **and** mixture coverage≥0.35?
- **Established evidence:** `P:19–22` states all three conjuncts; `P:245,248` separates a shorthand H1 row and utility guardrail. `D22:68,71` places coverage under H4. `E:973–981` can report H1 pass without the 0.35 coverage floor (`SCI:15`).
- **Options and implications:** **A — use all three registered conjuncts:** follows `P:22`, prevents a low-coverage H1 pass; requires evaluator/report change. **B — treat coverage only as an independent utility gate:** follows D22's layout but changes the explicit H1 criterion and can produce a false H1 pass against P:22.
- **Recommendation (proposed):** A as a prospective clarification of the original explicit H1 line; preserve separate coverage reporting. Do not implement without an owner decision on missing evidence.
- **Decision maker/dependency:** Project owner; independent statistician should confirm classification implications; prerequisite for SCI-02.
- **Closure evidence/tests:** Dated controlling wording; synthetic boundary fixtures at `M=0,58,59`, CP boundary and coverage just below/at 0.35, plus incomplete N/K/M cases; no Holdout data. **Status: OWNER DECISION REQUIRED.**

### SCI-02 · P0 · H2 estimand and fixed-sequence gate

- **Question:** Is H2 the preregistered S10 mixture selective-risk certification after H1, or Decision 22's whole-mixture paired incidence reduction versus baselines?
- **Established evidence:** `P:17,24–26` defines core-10 `K10/M10`, `M10≥59`, one-sided CP UCB≤0.05 and H1→H2 fixed sequence. `D22:69` substitutes paired incidence vs V8.1/V7. `E:983–1029` implements incidence and `E:1027` can pass without a baseline or with any one favorable comparison; it has no H1 gate (`SCI:16`).
- **Options and implications:** **A — retain preregistered H2:** preserves estimand/familywise plan; paired incidence can be separately descriptive or prospectively amended. **B — adopt D22 H2 as a substantive amendment:** changes denominator/comparator and needs exact required baseline(s), paired test/CI decision role, multiplicity and gate rule. **C — leave both as “H2”:** contradictory labels and potential false pass.
- **Recommendation (proposed):** A, with a distinct name for any paired-incidence analysis. The owner must explicitly decide whether an amended confirmatory incidence claim is wanted.
- **Decision maker/dependency:** Project owner; independent statistician if B or a new confirmatory comparison is chosen; depends on SCI-01.
- **Closure evidence/tests:** Dated protocol/Decision-22 reconciliation; H1 pass/fail/unevaluable → H2 formal-state tests, S10-only denominator and exact CP boundary tests; if amended, missing/both-baseline and multiplicity fixtures. **Status: OWNER DECISION REQUIRED.**

### SCI-03 · P0 · H3 controlling paired CI and required baseline

- **Question:** Which paired one-sided 95% LCB controls H3 at `−0.05`, and may V7 ever replace missing primary V8.1?
- **Established evidence:** `P:28–30,247` says “Newcombe/Wald” for 1,200 S10 pairs plus NOMINAL TSR≥0.94. `D22:70,79–81` selects Student-t Wald controlling and Newcombe sensitivity, with V8.1 primary. `E:1222–1256` computes both; `E:1294–1303` falls back to V7 if V8.1 is absent (`SCI:17`).
- **Options and implications:** **A — Student-t Wald controls, Newcombe sensitivity, V8.1 mandatory:** follows D22's stated hierarchy but resolves an ambiguity in P and needs statistical justification. **B — Newcombe controls or both must concur:** may classify boundary cases differently and is not uniquely specified by P. **C — permit V7 fallback:** changes the registered primary comparator and could create a false primary pass.
- **Recommendation (proposed):** Require V8.1 for a primary H3 claim and report V7/Newcombe separately. Defer the exact controlling CI choice to independent statistical review, then owner approval.
- **Decision maker/dependency:** Independent statistician followed by project owner; before implementation/Holdout.
- **Closure evidence/tests:** Reviewer memorandum on binary paired CI, boundary calibration and disagreement; dated formula/level/baseline decision; synthetic 1,200-pair boundary, missing V8.1, mismatched/duplicate pairing and NOMINAL 112/120 vs 113/120 tests. **Status: INDEPENDENT REVIEW REQUIRED.**

### SCI-04 · P0 · H4 identity and pooled incidence bound

- **Question:** Is H4 the preregistered four-scenario compound-fault comparison, and does the pooled one-sided CP incidence UCB≤0.05 constrain H4, a separate guardrail, or overall acceptance?
- **Established evidence:** `P:32–34` specifies 480 V8.1 matched pairs, exact two-sided McNemar `p<0.05` with favorable direction and bootstrap CI reporting. `P:246` says pooled CP bound “must satisfy” without assigning it. `D22:71` and `E:979–981` relabel mixture coverage as H4 (`SCI:18`).
- **Options and implications:** **A — restore registered compound H4 and put pooled bound in an explicitly chosen role:** preserves the original comparison but needs a ruling on the internal ambiguity. **B — retain D22 coverage H4:** drops the registered compound test and requires a substantive amendment. For the bound: H4 conjunct tightens H4; separate guardrail changes overall eligibility; descriptive only may conflict with “must satisfy.”
- **Recommendation (proposed):** Restore compound H4; obtain independent statistical advice on the pooled-bound role before the owner selects the exact rule. Keep coverage associated with H1/utility.
- **Decision maker/dependency:** Independent statistician on pooled-bound/claim scope; project owner on controlling hypothesis. Depends on SCI-02/SCI-07.
- **Closure evidence/tests:** Dated four-scenario list, V8.1 pairing, McNemar direction/p rule, bootstrap reporting and pooled-bound role; synthetic 480-pair, unfavorable-direction, missing-baseline and pooled-bound boundary tests. **Status: INDEPENDENT REVIEW REQUIRED.**

### SCI-05 · P0 · H5 IUT, simultaneous bounds and step-down

- **Question:** Which method controls H5 pass, which step-down procedure and family are required, and what claim is allowed when scenario selective risk is undefined?
- **Established evidence:** `P:36–37,252` specifies 12×120, simultaneous one-sided CP bounds using Šidák allocation “and Holm step-down,” `M_s=0` as `UNDEFINED`, plus Berger IUT on unconditional incidence. `D22:55–56,72` names Holm–Šidák. `E:1150–1172,1305–1318,1369–1376` computes bounds/step-down but makes H5 pass depend only on IUT (`SCI:19`).
- **Options and implications:** **A — IUT controls incidence, bounds/step-down are mandatory separate reports:** fits the protocol's “plus” wording but does not certify selective risk. **B — require bound/step-down success as additional H5 conjuncts:** may change acceptance and needs prospective amendment. Ordinary Holm vs Holm–Šidák has different thresholds and must be chosen explicitly.
- **Recommendation (proposed):** Provisionally A; let an independent statistician settle exact family, ordinary Holm vs Holm–Šidák, dependence assumptions and whether extra conjuncts are intended. Never interpret `M_s=0` as selective-risk pass.
- **Decision maker/dependency:** Independent statistician followed by project owner; depends on SCI-07 claim scope.
- **Closure evidence/tests:** Dated test/CI/multiplicity specification; synthetic per-scenario boundary cases, all-abstain scenario, discordant IUT/step-down outcomes and simultaneous-bound reporting checks. **Status: INDEPENDENT REVIEW REQUIRED.**

### SCI-06 · P0 · Missing, incomplete and contradictory evidence states

- **Question:** What exact state applies when a partition, controlling baseline, pair set, report or execution is missing, incomplete, inconsistent or failed?
- **Established evidence:** `E:958` checks records against `len(records)` rather than a registered manifest count; `E:1027` permits H2 baseline absence; `E:1294–1303` substitutes V7 for missing V8.1. `SCI:23–31` proposes explicit `NOT_EVALUATED`/`INCOMPLETE_INVALID` states; `PKG:41–52` shows scientific consequences.
- **Options and implications:** **A — fail closed to an unevaluable/incomplete state with no favorable fallback:** protects claim validity and makes the cause visible; may delay a claim after operational failure. **B — accept a reduced data set or alternate baseline:** can change estimand/error control; requires a separate prospective, statistically reviewed amendment. A failed worker should never be converted into a statistical pass by a count or Boolean fallback.
- **Recommendation (proposed):** A, with exact state names and propagation through H1→H2 and all dependent claims approved prospectively.
- **Decision maker/dependency:** Independent statistician for inferential handling; project owner for protocol and operational status vocabulary. Depends on SCI-01–SCI-05.
- **Closure evidence/tests:** Dated rule table for missing baseline, N/denominator, duplicates, `M_s=0`, conflicting reports, timeout/crash/invalid digest; synthetic partial partition and fail-closed integration tests; confirm no threshold or assertion was weakened. **Status: INDEPENDENT REVIEW REQUIRED.**

### SCI-07 · P0 · Secondary multiplicity and aggregate operational-improvement claim

- **Question:** Are H3–H5 separate secondary reports or a familywise-controlled joint claim, and what complete rule permits any aggregate “operational improvement” label?
- **Established evidence:** `P:17` explicitly controls H1→H2 fixed sequence. `P:28–37` names H3–H5 secondary but lacks a complete joint adjustment; `P:254` supplies necessary anti-gaming exclusions, not sufficient positive acceptance. `E:1033–1039` emits `CERTIFIED_OPERATIONAL_IMPROVEMENT` after mixture H1/coverage, before Scenario H3–H5 (`SCI:21–22`).
- **Options and implications:** **A — report components separately and withhold aggregate certification:** avoids unsupported familywise/overall claim. **B — seek a prospective joint rule:** may permit one label but needs explicit family, allocation/gates and full-partition evidence before data access. **C — keep current mixture-only label:** can overclaim despite missing Scenario evidence.
- **Recommendation (proposed):** A until independent statistical review and owner approval establish a complete joint rule, if the project wants one.
- **Decision maker/dependency:** Independent statistician followed by project owner; depends on SCI-01–SCI-06.
- **Closure evidence/tests:** Dated allowed-claims matrix, multiplicity plan (if any), complete aggregate Boolean/evidence dependencies; synthetic cases where mixture passes but H3/H4/H5 fails or is unevaluable; report-label tests. **Status: INDEPENDENT REVIEW REQUIRED.**

## Workstream 4 — Durable evidence root and signed ticket

### SEC-01 · P0 · Bind durable output storage into authorization

- **Question:** What owner-approved external evidence-root identity must the signature bind, and how will v1 tickets be treated?
- **Established evidence:** `C:150–165` signs relative `target_output_root="results/v9"` only; `V:250–278` rejects unrecognized fields. `L:868–890` chooses an external path but rejects production before claim because the path is unsigned; `L:914–918` records that fact. `SEC:20–27` defines the threat and proposed versioned interface.
- **Options and implications:** **A — signed canonical absolute path plus volume/retention identity:** direct comparison; path/volume moves require new approval. **B — signed stable owner-controlled storage ID with authenticated resolution:** portable; resolver becomes a new trust dependency. **C — accept operator-supplied unsigned path:** leaves output destination outside authorization and weakens the current fail-closed guard.
- **Recommendation (proposed):** Version the ticket and sign A or B only after owner/security reviewer selects the trust model; reject v1 for the production external-root path. Preserve current preclaim failure until then.
- **Decision maker/dependency:** Project owner and qualified security reviewer; prerequisite to production launcher implementation and REL-01.
- **Closure evidence/tests:** Approved contract revision and exact root/storage identity; authenticated signer/verifier/launcher change; synthetic wrong-root, symlink, path escape, storage swap, missing-root, duplicate-output, preclaim and postclaim failure tests; preserved raw/log/hash evidence. **Status: OWNER DECISION REQUIRED.**

## Workstream 5 — Package/runtime and wheel provenance

### SEC-02 · P0 · Authenticate wheel archives and execution environment

- **Question:** Which independently trusted package archive/installation record and exact venv/checkout procedure establish the runtime actually executing the candidate?
- **Established evidence:** `C:437–440` requires installed distributions matching recorded wheel hashes. `R:147–242` checks lock hash, isolated interpreter, packages, installed RECORD files and import origins, but explicitly sets `wheel_archive_sha256_verified=False` at `R:232`. `DRAFT:23–31,44–49` provides local hashes only; `SEC:29–35` describes the missing trust chain.
- **Options and implications:** **A — owner-authenticated offline wheelhouse with exact archive digests and clean candidate venv:** directly verifies package origin; requires protected storage/platform-specific inventory. **B — independently signed build/install attestation of an equivalent complete archive set:** may fit existing infrastructure; verifier and attestation authority must be specified. **C — rely only on `uv.lock`, versions and local RECORD:** detects drift but does not independently prove wheel origin.
- **Recommendation (proposed):** Prefer A if the owner can protect a complete wheelhouse; B is defensible only with an independently authenticated equivalent. No trust source is currently identified, so no package-origin claim is made.
- **Decision maker/dependency:** Project owner/release engineer with security reviewer; depends on an available independent source, then candidate-specific build procedure.
- **Closure evidence/tests:** Owner-pinned wheel/attestation inventory, interpreter/build identity and lock digest; offline reproducible environment; synthetic same-version tampered wheel/RECORD, extra package, stale editable path, wrong interpreter and interrupted-build failures; preclaim verified runtime record. **Status: BLOCKED.**

## Workstream 6 — Replay-ledger rollback protection

### SEC-03 · P0 · Select a rollback-resistant nonce witness and recovery rule

- **Question:** Against a same-UID actor, what independent monotonic record proves that a previously claimed ticket/partition cannot be replayed after local ledger rollback?
- **Established evidence:** `C:94–98,250–262` explicitly states local POSIX permissions and ledger files cannot defeat same-UID rollback. `src/nexvia_aegis/security/ledger.py:202–239,242–271,773–785` validates structure and durable writes/reconciliation but has no external witness. `SEC:37–43` specifies candidate approaches.
- **Options and implications:** **A — owner-held offline signed nonce/checkpoint registry:** simple trust separation, but manual synchronization and availability constraints. **B — append-only service under a separate principal:** automated monotonic checks, but service availability/credentials are new dependencies. **C — owner-controlled write-once media:** strong retention, harder operational workflow. **D — local ledger only:** sufficient for accidental corruption/concurrency, insufficient for the stated same-UID threat.
- **Recommendation (proposed):** Require A, B or C if same-UID rollback remains in scope; select based on actual owner-controlled resources. No single implementation can be chosen without that decision.
- **Decision maker/dependency:** Project owner and security reviewer; before any production claim and before REL-01 finalization.
- **Closure evidence/tests:** Dated threat model and witness/recovery authority; monotonic sequence/digest protocol; synthetic restore of old valid ledger, missing/forked checkpoint, replay after rollback, outage and crash-between-writes tests; owner-confirmed incident recovery that never resets a spent claim. **Status: OWNER DECISION REQUIRED.**

## Workstream 7 — Tool/key authenticity and custody

### SEC-04 · P1 · Authenticate every candidate-bound tool and public key

- **Question:** Which owner-controlled source binds the final candidate's launcher, signer, evaluator, runtime probe, verifier/canonicalizer, ledger, lock/package inventory and public-key fingerprint?
- **Established evidence:** `C:95–96,241–245,442–449` requires independent signer/public-key and exact execution-tree checks. `DRAFT:21–35,41–49` lists local SHA-256 observations but no owner-authenticated pins. `PKG:58–65` and `SEC:45–49` identify the gap; the old manifesto binds a different commit.
- **Options and implications:** **A — owner-held signed/offline pin record for the selected SHA and every required artifact:** clear trust boundary; needs protected custody/change control. **B — independently authenticated immutable repository/release attestation:** can integrate with Git, but its signing/immutability source must be demonstrated. **C — self-compute hashes from the mutable checkout:** detects local mismatch only against itself and cannot establish authenticity.
- **Recommendation (proposed):** A or a demonstrably equivalent B after REL-01. Do not copy provisional local values into an approval record without independent owner authentication.
- **Decision maker/dependency:** Project owner and security reviewer; depends on REL-01, SEC-01/SEC-02 and trust-source availability.
- **Closure evidence/tests:** Dated independent pin record, public-key fingerprint verified outside agent-writable tree, code/lock/wheel digest comparisons at exact candidate SHA, synthetic substituted key/tool and wrong-commit rejection tests before claim. **Status: BLOCKED.**

### SEC-05 · P1 · Select private signing-key custody and ceremony

- **Question:** Where will the production Ed25519 private key live, who may invoke signing, and how will the signer itself be authenticated before a ticket ceremony?
- **Established evidence:** `C:94–96,229–245` describes A out-of-band/air-gapped custody (preferred, pending confirmation), B passphrase-protected local storage, and C unencrypted local storage with operational inactivity; same-UID processes can access local files. `DRAFT:48` deliberately contains no private key.
- **Options and implications:** **A — out-of-band machine/hardware token:** strongest separation from agent process; more ceremony/setup. **B — encrypted local key with owner passphrase:** operationally easier, but active same-UID compromise remains possible. **C — unencrypted local key:** weakest and relies on all agents/processes being inactive; does not meet an active same-UID threat.
- **Recommendation (proposed):** A, consistent with the contract's preferred boundary; have security reviewer document residual risks and recovery. Do not create/sign a production ticket in this task.
- **Decision maker/dependency:** Project owner and security reviewer; depends on SEC-04 trusted signer/public-key record and approved contract.
- **Closure evidence/tests:** Dated custody/authorization procedure, independently checked signer digest and public-key fingerprint, synthetic signing/verification and substituted-key rejection, access/revocation/incident plan. Production key remains outside this register. **Status: OWNER DECISION REQUIRED.**

## Required owner summary

1. **Three highest-priority decisions:** **SCI-02** — choose the controlling H2 estimand and enforce H1 gate; **SEC-01** — approve a signed durable evidence-root identity and ticket version; **SEC-02** — select an independently trusted wheel/runtime provenance source. These decisions unblock major scientific and production paths, but **do not alone close the release**.
2. **Independent statistician required:** SCI-03 (H3 CI/baseline), SCI-04 (pooled-bound role), SCI-05 (H5 family/step-down), SCI-06 (missing/contradictory evidence), SCI-07 (secondary multiplicity/aggregate claims). SCI-01 should receive statistical confirmation; SCI-02 requires independent review if its preregistered identity is changed or a new confirmatory incidence claim is added.
3. **Security reviewer required:** SEC-01 (signed root), SEC-02 (wheel/runtime trust), SEC-03 (rollback witness), SEC-04 (tool/key pin chain), SEC-05 (key custody/ceremony).
4. **Engineering after approval:** implement the approved H1–H5 and evidence-state rules; version signer/verifier/launcher for the approved root; add wheel/runtime provenance checks and ledger witness integration; pin tools/keys; run the listed synthetic regressions and the final authorized non-Holdout suite in a clean candidate checkout. Historical artifacts and old reports remain untouched.
5. **Prerequisites for a future owner-designated release candidate:** dated scientific decisions and independent statistical review; approved security contract/trust model plus implementation and synthetic tests; provenance erratum/reference decision; independent tool, key and package trust sources; reviewed clean commit and reproducible runtime. Only then should the owner designate the full SHA and approve a versioned Staging Manifest, followed by detached-worktree verification.

**Gate B remains `GATE_B_NOT_AUTHORIZED`. No Holdout evaluation was performed. The Final Release Commit has not been created. Preparing this register resolves none of the listed blockers.**
