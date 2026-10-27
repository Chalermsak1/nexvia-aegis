# NEXVIA AEGIS V9-M4 — release blocker decision package

**Prepared:** 2026-10-27, Asia/Bangkok  
**Overall readiness:** **BLOCKED**  
**Governance:** **GATE_B_NOT_AUTHORIZED**  
**Purpose:** Owner review of release references, historical provenance, scientific rules and security controls. This report is not a release approval.

## A. Executive summary

The actual repository remains at engineering review SHA `b91cc99f591e0b3da3e111a287dc9be3ff44c463` on `codex/v9-m4-remediation`. It is not designated by the owner as a final release candidate. No authoritative current Staging Manifest was found. The old release manifesto binds `bc440151545aad6795902b285972faac7534c92e` and cannot authenticate current code. The 301-test safe regression result at this same SHA was checked from its prior log, but no new code was changed and the suite was not rerun for this documentation task.

The four disputed historical artifacts have a reproducible current identity across original artifact commit `74f93fe`, current HEAD and a separate local copy; their producer inventories and three stored canonical digests agree. Several narrative raw-hash citations do not. That provenance supports a dated erratum proposal, not unilateral choice of authoritative release hashes. H1–H5 and production security contain unresolved owner/statistical/trust decisions. The launcher currently fails closed before claim on the unsigned durable evidence root. Therefore mandatory release-readiness criteria are not satisfied, and authoritative detached-worktree release verification was not authorized or performed.

## B. Release reference status and proposed candidate choice

| Reference | State and evidence | Decision |
| --- | --- | --- |
| Owner-approved release-candidate SHA | **None identified.** Current `b91cc99` is an engineering target (`V9_M4_RELEASE_REMEDIATION_BASELINE.md` candidate table). | Owner must explicitly designate a full SHA after scientific/security remediation review. |
| Current Staging Manifest | **None identified.** `V9_M4_STAGING_MANIFEST_DRAFT_UNAPPROVED.md` is a proposal, not an authority. | Owner must approve a versioned manifest and independent hash/trust references. |
| Previous release manifesto | Desktop `release_manifesto_bc440151545aad6795902b285972faac7534c92e.json` binds `bc44015`. | Retain as historical evidence only. |
| Historical artifact baseline | `74f93fe2613221c476828d1558c03d0598c06b7e`; current protected Cal/Val bytes unchanged from it. | Decide controlling path/version/raw digests via erratum and staging approval. |
| Trusted release pins | Local hashes exist in draft, but no external owner-controlled authentication for current final toolset, wheelhouse or key. | Supply authenticated trust record and security decision. |

**Candidate recommendation:** Treat `b91cc99` as the best *current engineering review baseline* because it includes the later launcher, runtime and ledger fixes and passed the safe 301-test suite. Do **not** select it as the final release SHA now: scientific decision logic is unresolved, production ticket v1 intentionally blocks launch, and wheel/ledger/tool trust is incomplete. A later reviewed remediation commit is likely necessary. `a05f33b` and `11a021a` omit later fixes; `74f93fe` is artifact provenance, and `bc44015` is the prior release. This is technical advice, not an owner designation.

## C. Historical hash reconciliation

Raw SHA-256 is over exact file bytes; canonical payload SHA-256 removes `integrity_sha256` and serializes sorted compact JSON as defined in `src/aegis/v9/risk_statistics.py:636–640`. Full source-by-source comparison, methods and proposed erratum are in `V9_M4_HISTORICAL_HASH_RECONCILIATION.md`.

| Artifact | Verified current/Git-74 raw SHA-256 | Canonical payload digest | Incompatible report references | State |
| --- | --- | --- | --- | --- |
| `results/v9/cal_r2/calibration_report.json` | `c07b04ba1600aad2416ade36cc6e9c33501327fb4b0a03d2d5b05b6f9b6a963e` | `016990be14b2e751edfbc9d0620e1f928a7f3ba31e2b2f723d4228c1fe81da1b` | Reports 09/10/13 `a91b9b…`; Report 19 `ef3eb0…` | Proven present-byte identity; citation origin unresolved; staging authority **BLOCKED** |
| `results/v9/cal_r2/calibration_run_config_frozen_r2.json` | `1a19f6b4c294217260540db19af877f514c852d09921cb06523baaca7ab77564` | `390af9d5c953bd09407d046def719bb9e13aec257f0b0d49e28c8d179c10635d` | Report 20 `f3e582…` | Same |
| `results/v9/cal_r2/cal_candidate_summary.csv` | `c37f673d0751e1848687f286c5c8199b151a24d1a199363b1a8191057725a3ae` | N/A (CSV) | Report 19 `043d84…` | Same |
| `results/v9/val_r1/validation_report.json` | `a5f4df07996c6e5c04a48b5ed86668960bafb691aa489c526e5232aea635b500` | `6aa98a3cf5e9d594a3ccae8903881ac62e0fbc80e025704beb65bab1876846d3` | Report 09 `c97fff…`; Reports 19/20 `a84bae…` | Same; M3 audit has the correct raw/canonical values |

Additional mismatches for Calibration/Validation manifest citations in Report 09 are documented in the reconciliation. No value was changed to force agreement. Owner approval of a dated erratum and exact staging references is required.

## D. Scientific readiness

`V9_M4_SCIENTIFIC_DECISION_GAP_ANALYSIS.md` gives source lines, current evaluator behavior, specific false-pass modes, proposed missing-evidence rules and six independent statistical-review questions. The core decisions are:

| Rule | Current gap | Required owner decision |
| --- | --- | --- |
| H1 | Protocol: M≥59 **and** CP UCB≤0.05 **and** coverage≥0.35; evaluator/Decision 22 separate coverage. | Confirm all registered conjuncts and missing/incomplete-data state. |
| H2 | Protocol: H1-gated S10 mixture selective risk; Decision 22/evaluator: whole-mixture paired incidence. Evaluator may pass with no baseline or one favorable baseline. | Retain preregistered H2 or explicitly amend estimand, baseline, test and multiplicity before data access; enforce H1 gate. |
| H3 | “Newcombe/Wald” controlling-CI ambiguity; evaluator lets V7 replace missing primary V8.1. | After independent review, select exact controlling paired CI, required V8.1 completeness, V7 auxiliary role and disagreement reporting. |
| H4 | Protocol: four-scenario compound-fault paired incidence reduction; Decision 22/evaluator: mixture coverage. Pooled incidence CP clause has unclear claim role. | Restore registered comparison or explicitly amend; decide pooled bound's role. |
| H5 | Protocol says Šidák bounds “and Holm step-down”; Decision 22/evaluator use Holm–Šidák; IUT pass is independent of step-down output. | Decide step-down method, reporting family, controlling H5 statement and `M_s=0` treatment after independent review. |
| Aggregate | Secondary multiplicity and sufficient overall-improvement rule absent; evaluator labels improvement after mixture only. | Approve or withhold any aggregate claim and secondary familywise procedure. |

**Scientific status:** No confirmatory H1–H5 result exists; no safe interpretation of the discrepancies can be silently implemented. The current proposals are **not** an independently authenticated statistician's approval. Independent review is specifically needed for H3 paired CI, H4 pooled-bound role, H5 multiplicity and secondary/aggregate claims.

## E. Security readiness

The full threat models, proposed interfaces, trust sources and synthetic regression matrix are in `V9_M4_SECURITY_BLOCKER_REMEDIATION.md`.

| Control | State | Release consequence |
| --- | --- | --- |
| CLI path, preclaim failure handling, external evidence retention | Resolved in current engineering code with synthetic regression evidence. | Does not authorize production. |
| Signed durable evidence root | Owner decision required. Ticket v1 does not bind it; launcher:885–890 rejects before registration/claim. | Production launch is blocked until an approved versioned contract and implementation. |
| Wheel/runtime provenance | Missing independent wheel archive or equivalent installation trust source; `runtime_integrity.py:232` reports false. | Installed versions/RECORD checks cannot prove package origin. |
| Same-UID ledger rollback | Owner must choose external checkpoint/append-only trust boundary and recovery model. | Local atomicity alone cannot prove anti-replay against rollback. |
| Tool/public-key authenticity and signing custody | No owner-pinned final candidate tool hashes or independently authenticated public key/wheel inventory. | Local hashes cannot authenticate the trust chain. |

No production-security schema or trust control was implemented in this task because the necessary owner decisions/trusted source data are missing. Existing v1 fail-closed behavior was preserved.

## F. Detached-worktree and test verification

**Authoritative detached-worktree release verification: NOT STARTED — entry conditions unmet.** No owner-approved full SHA, approved Staging Manifest, controlling historical references, or scientific/security dispositions exist. No *detached verification* worktree was created at a guessed candidate and no restricted Holdout file was hashed. A separate **documentation worktree** was created from `b91cc99` on branch `codex/v9-m4-release-blocker-docs` at `/Users/chalermsak/Documents/ChatGPT/New project/nexvia-aegis-release-blocker-docs` solely to hold these new, uncommitted reports. The original worktree remained at `b91cc99` and clean. The previous audit's full-suite command and log at this same commit were checked in this task: `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q -p no:cacheprovider`; 301 passed, 32.35 s, exit 0, log `/private/tmp/nexvia_v9m4_final_release_pytest_20261027.log`. **This was not rerun in this task.** Current task ran read-only Git/hash/canonicalization checks only; those outputs are recorded in the supporting reports.

The safe suite verifies synthetic software behavior, not confirmatory Holdout results or real robot validation. Final approved tests must be rerun in the exact approved candidate/environment after remediation and manifest approval.

## G. Outstanding decisions and closure evidence

| Priority | Owner decision / responsible role | Approval dependency | Evidence required to close |
| --- | --- | --- | --- |
| Critical | Designate full candidate SHA and approve versioned Staging Manifest — **project owner** | After code/science/security review | Dated decision, independent trust record, exact artifact paths/hash scopes and safe test matrix; then detached-worktree comparison |
| High | Accept/reject historical hash erratum and controlling raw references — **project owner/research integrity reviewer** | Before staging approval | Source provenance for any disputed alternative; approved path/version/hash table; no artifact rewrite |
| Critical | Decide H1–H5, missing evidence, secondary multiplicity and aggregate claim — **project owner + independent statistician** | Before statistical implementation or Holdout | Signed/dated prospective protocol revision, reviewer response, synthetic boundary tests |
| Critical | Approve signed durable evidence-root schema and storage identity — **project owner/security reviewer** | Before production-path code change | Versioned contract, signed field binding, fail-closed synthetic tests and security review |
| High | Select owner-controlled wheel provenance and execution venv/checkout — **project owner/release engineer** | Before candidate runtime verification | Authenticated wheel inventory/build trace, clean environment and mismatch tests |
| High | Select rollback witness and recovery authority — **project owner/security reviewer** | Before any production claim | External checkpoint/append-only evidence, rollback/replay tests, incident procedure |
| High | Authenticate signer/launcher/runtime/evaluator/public-key pins and key custody — **project owner/security reviewer** | After candidate selection, before ticket ceremony | Owner-held fingerprint/hash record and independent verification evidence |

Once the approvals exist, engineering changes must be isolated, synthetically tested and reviewed; then the owner can designate a new candidate. No item above can be closed by this agent's local hash calculation alone.

## H. Governance and final approval

- **Gate B authorized?** **No — `GATE_B_NOT_AUTHORIZED`.**
- **Holdout evaluation or reserved-material access in this task?** **No.**
- **Mandatory release-readiness criteria satisfied?** **No.**
- **Ready for owner release approval?** **No; BLOCKED pending the decisions and evidence above.**
- **Final Release Commit, release tag, publication push created?** **No.**
- **Historical Cal/Val/benchmark files or prior reports changed?** **No.**

Owner review should first approve or correct the proposed decision fields, not authorize a production run. Final release and Gate B are separate subsequent approval gates.
