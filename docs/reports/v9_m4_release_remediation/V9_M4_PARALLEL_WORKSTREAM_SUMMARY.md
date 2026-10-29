# V9-M4 parallel audit and synthetic-test preparation — summary

**Prepared:** 2026-10-27 (Asia/Bangkok). **Overall:** `BLOCKED — GATE_B_NOT_AUTHORIZED`. This is a documentation and safe-readiness package, not an approval, release-candidate designation, Staging Manifest, release commit, signed ticket, or confirmatory result.

## Repository boundary and deliverables

At task start, `git worktree list --porcelain` identified two clean worktrees: the engineering checkout on `codex/v9-m4-remediation` at `b91cc99f591e0b3da3e111a287dc9be3ff44c463`, and the documentation checkout on `codex/v9-m4-release-blocker-docs` at `3a8cea5f4a4534df4edd1cc1320bdd75585bc7e7`. `git status --short --untracked-files=all` returned no changes in either. All seven outputs below are **new** files in `docs/reports/v9_m4_release_remediation/`; the eight previously tracked documents there were preserved. No production code, existing tests, approved protocol, Calibration/Validation artifact, or earlier report was modified.

| Workstream | New deliverable | State |
| --- | --- | --- |
| A — historical provenance | `V9_M4_HISTORICAL_ARTIFACT_PROVENANCE_INVENTORY.md` | **VERIFIED local/Git identities; older citation origins UNVERIFIED**. |
| A — historical provenance | `V9_M4_HISTORICAL_HASH_ERRATUM_DRAFT.md` | **PROPOSED, UNAPPROVED** dated annotation; no historical rewrite. |
| B — package/runtime | `V9_M4_PACKAGE_RUNTIME_PROVENANCE_INVENTORY.md` | **VERIFIED local lock/install observations; origin trust MISSING**. |
| B — package/runtime | `V9_M4_RUNTIME_TRUST_GAP_REPORT.md` | **BLOCKED** SEC-02 assessment and approval-dependent closure plan. |
| C — scientific tests | `V9_M4_SYNTHETIC_TEST_SPECIFICATION.md` | **PROPOSED** H1–H5, evidence-state and aggregate test cases; arithmetic probe only, no evaluator or pytest execution. |
| D — security tests | `V9_M4_SECURITY_TEST_MATRIX.md` | **PROPOSED** 20 SEC-01–05 cases; source inspection only, no security test execution. |
| Integration | `V9_M4_PARALLEL_WORKSTREAM_SUMMARY.md` | This cross-workstream record; no blocker closed by its creation. |

## Actual findings and evidence limits

**Historical artifacts (A).** The allowlisted read-only hash check in `V9_M4_HISTORICAL_ARTIFACT_PROVENANCE_INVENTORY.md` matched the raw SHA-256 of 14 explicit Calibration/Validation files to their blobs in Git artifact commit `74f93fe2613221c476828d1558c03d0598c06b7e`. The Calibration and Validation producer inventories matched **7/7** and **6/6** entries, and eight stored canonical JSON digests recomputed under their respective serialization rules (`src/aegis/v9/risk_statistics.py:636-640`; `src/aegis/v9/randomization.py:162-167,251-256`). These results verify identity of available bytes and internal consistency; they do not authenticate an external release trust source or independently prove the historical simulation run. Six files have older nonmatching hash citations in Reports 09/10/13/19/20 (`V9_M4_HISTORICAL_HASH_ERRATUM_DRAFT.md`, disputed-citation table). The origin of those older values is **UNVERIFIED**. The dated erratum remains **UNAPPROVED**; exact controlling paths, versions, raw/canonical scopes, and owner/research-integrity disposition are still required.

**Package and runtime (B).** The raw `uv.lock` SHA-256 observed at the engineering checkout and old release commit is `f90654ab95d7b7c543179fc64fe666a912e10f5c9b2e3d72bb9223f2a7e3c2aa`, while the contract records a different **provisional** digest (`docs/architecture/v9_m4_signed_gate_b_ticket_implementation_contract.md:428-440`); neither becomes an owner-approved pin by appearing here. A read-only direct runtime-integrity call in the engineering `.venv` exited 0 and reported Python **3.12.14**, **34** selected packages, installed RECORD/import-origin checks, and `wheel_archive_sha256_verified=false` (`src/nexvia_aegis/security/runtime_integrity.py:147-242`). Wrong-lock and wrong-interpreter synthetic input calls were rejected with `RUNTIME_INTEGRITY_MISMATCH` and `RUNTIME_INTERPRETER_LOCATION_MISMATCH`. The exact commands and selected outputs are in `V9_M4_PACKAGE_RUNTIME_PROVENANCE_INVENTORY.md`. No complete independently authenticated wheelhouse, tracked build/CI attestation, interpreter provenance, or approved candidate-bound runtime trust record was established. The inspected uv cache is neither complete nor a trust anchor. **SEC-02 remains BLOCKED.**

**Scientific tests (C).** Source comparison confirms the open H1–H5 discrepancies: explicit three-part H1 versus the evaluator's two-part H1 (`docs/v9_experiment_protocol.md:19-22`; `experiments/v9_evaluate_holdout.py:973-981`); registered H1-gated core-10 selective-risk H2 versus Decision-22/current whole-mixture incidence H2 (`protocol:17,24-26`; Decision 22 `:69`; evaluator `:983-1029`); H3 controlling CI/baseline substitution (`protocol:28-30`; evaluator `:1222-1303`); registered compound H4 versus coverage relabeling (`protocol:32-34`; evaluator `:979-981`); and H5 IUT versus bound/step-down reporting (`protocol:36-37`; evaluator `:1150-1172,1305-1318`). The test specification preserves competing expected outcomes until owner/statistician decisions. Standalone math on invented counts confirmed boundary examples: `N=1440,M=59,K=0` gives coverage `0.040972222` and CP UCB `0.049507610`; scenario `n=120,K=0/1/2` gives binomial p values `0.002122426/0.015527225/0.057505408`. These are **synthetic arithmetic results, not Holdout findings**. No executable test draft was installed: unresolved pass rules should not become a default-discovered oracle. Existing test files were read only.

**Security tests (D).** `V9_M4_SECURITY_TEST_MATRIX.md` defines 20 synthetic cases for signed evidence-root/path and postclaim retention (SEC-01), wheel/RECORD/runtime origin (SEC-02), rollback/replay/crash recovery (SEC-03), candidate/tool/public-key substitution (SEC-04), and signer custody/revocation (SEC-05). Each case specifies threat, fixture, expected rejection or behavior, evidence, safe boundary, approval and closure. Source inspection found that the current launcher intentionally rejects an unsigned external evidence root before claim (`src/nexvia_aegis/security/launcher.py:867-895`), the runtime probe does not verify wheel archives (`runtime_integrity.py:229-242`), and local ledger durability does not provide an independent rollback witness (`src/nexvia_aegis/security/ledger.py:202-271`; contract `:94-98,250-262`). Owner-authenticated candidate/tool/key pins and custody remain undecided (`docs/reports/v9_m4_release_remediation/V9_M4_OWNER_DECISION_REGISTER.md:146-195`). The 20 cases were **prepared, not executed**; no production signing key or ticket was created.

## Required decisions and next engineering work

1. **Research integrity / owner:** Decide each disputed historical citation, identify any authentic alternate source bytes, and approve or reject a dated erratum with exact raw/canonical hash definitions. An owner-controlled staging reference is still missing.
2. **Independent statistician / owner:** Decide H1–H5 identities and thresholds, H1→H2 gate, H3 controlling paired CI, H4 pooled-bound role, H5 multiplicity/claim role, all missing/contradictory-evidence states, and secondary/aggregate claim scope (`V9_M4_OWNER_DECISION_REGISTER.md:81-142`). Test rows with competing outcomes cannot be converted to formal pass assertions before these rulings.
3. **Security reviewer / owner:** Approve the signed durable-root contract, independent wheel/install trust source, external ledger rollback witness and recovery authority, candidate-bound tool/public-key pins, and signer/key custody (`V9_M4_OWNER_DECISION_REGISTER.md:146-195`). Local hashes and RECORDs alone do not close these items.
4. **Engineering after approval:** Implement only the approved code/contract changes on an isolated development path; turn the specifications into isolated synthetic fixtures, record exact commands and outputs, run the approved non-Holdout regression suite in an owner-designated exact candidate checkout, and independently verify the owner-approved manifest and trust records. No approval or final candidate was inferred from this preparation.

## Final verification and limitations

Final checks after all seven files were present:

| Exact command and checkout | Actual outcome |
| --- | --- |
| `git worktree list --porcelain` in documentation checkout | Engineering worktree still at `b91cc99` on `codex/v9-m4-remediation`; documentation worktree still at `3a8cea5` on `codex/v9-m4-release-blocker-docs`. |
| `git status --short --untracked-files=all` and `git diff --name-only` in documentation checkout | Exactly the seven named new `.md` files are untracked; **no tracked-file diff**. The eight earlier reports remain present. |
| `git status --short --untracked-files=all` and `git diff --name-only` in engineering checkout | Both empty; HEAD remains `b91cc99f591e0b3da3e111a287dc9be3ff44c463`. |
| `wc -l` on the seven new documents | 82, 35, 76, 27, 89, 80, and 49 lines respectively in the deliverable-table order above; all seven exist. |

This task's read operations were confined to source, allowed Calibration/Validation files, runtime metadata, local cache filenames, and existing audit documents. No restricted Holdout file, reserved seed content, confirmatory outcome, production launcher, or signing ceremony was accessed or run. No new scientific acceptance rule was implemented; no protected artifact or existing user work was discarded. The direct runtime probe tests **local consistency**, not independent supply-chain provenance. Prepared security/scientific cases remain unexecuted except the explicitly reported standalone arithmetic and read-only runtime calls.

**Final status: `BLOCKED — GATE_B_NOT_AUTHORIZED`.**
