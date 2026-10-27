# V9-M4 release remediation baseline — 2026-10-27

**Status:** Investigation baseline; no release, Gate B, or Staging Manifest approval. **GATE_B_NOT_AUTHORIZED**.

## Verified repository state

| Item | Direct observation |
| --- | --- |
| Repository/origin | `/Users/chalermsak/Documents/ChatGPT/New project/nexvia-aegis`; `https://github.com/Chalermsak1/nexvia-aegis.git` |
| Branch/HEAD | `codex/v9-m4-remediation`; `b91cc99f591e0b3da3e111a287dc9be3ff44c463`; origin branch at same SHA |
| Initial worktree | `git status --short --branch` showed no staged, unstaged, or untracked change; `git diff --stat` and `git diff --cached --stat` empty |
| Worktrees | `git worktree list --porcelain`: only the original checkout |
| Historical artifact baseline | `74f93fe2613221c476828d1558c03d0598c06b7e` is an ancestor; historical Cal/Val paths have no tracked changes through HEAD |
| Previous release | `bc440151545aad6795902b285972faac7534c92e` is an ancestor; the Desktop release manifesto's `approved_commit` names it |
| Instructions | No repository `AGENTS.md` found; read `README.md`, `docs/v9_experiment_protocol.md`, Gate B contract, prior audits and this task |

The prior audit's actual 301-test log was checked against the same HEAD and is still present at `/private/tmp/nexvia_v9m4_final_release_pytest_20261027.log` (301 passed in 32.35 s; log SHA-256 `cb31d777cfea7a133b795601fcefd28f7d87505a595ee8396c7baa8f4982cd95`). This is previous execution evidence, not a test rerun in this workstream. Current source changed neither code nor test criteria.

## Candidate evidence, without owner designation

| Full SHA | Branch/history role | Direct changes / limitation |
| --- | --- | --- |
| `bc440151545aad6795902b285972faac7534c92e` | Previous Gate B security release baseline; ancestor | Previous manifesto binds this SHA. Predates addition of many Cal/Val files and current engineering fixes; cannot authenticate current code. |
| `74f93fe2613221c476828d1558c03d0598c06b7e` | `origin/main`, artifact baseline; ancestor | Commit adds historical Cal/Val files. It is not a final remediation candidate. |
| `a05f33b61a8ccc03706ff39fb45bc3f229bd9611` | Engineering remediation ancestor | Changes launcher/evaluator status reporting and synthetic tests; later runtime and ledger fixes supersede it. |
| `11a021a42b5afbcd87f54e791565cc48e1499af8` | Engineering remediation ancestor | Adds runtime probe and preclaim/ledger hardening; later checkout-path fix supersedes it. |
| `b91cc99f591e0b3da3e111a287dc9be3ff44c463` | Current branch and prior *engineering review target* | Adds exact editable-checkout path allowance in runtime probe; plausible candidate for further owner review, **not owner-selected** and still blocked scientifically/security-wise. |

Commit roles come from `git log`, `git show --stat`, `git merge-base --is-ancestor`, and `V9_M4_SECOND_AUDIT_CANDIDATE_REPORT.md:10–22, 116–121`. Current local tool hashes are listed in the separate **DRAFT — NOT APPROVED** staging specification; a hash computed in this mutable checkout is not a trust anchor.

## Evidence and authority inventory

| Subject | Source and location | What it establishes | Limit |
| --- | --- | --- | --- |
| Scientific preregistration | `docs/v9_experiment_protocol.md:13–37, 240–254, 258–290` | Registered H1–H5, gatekeeping, artifact preservation and safe test scope | Internal H1/H3/H5 wording ambiguities remain; cannot be silently changed |
| Decision Record 22 | `docs/reports/v9_m4_statistical_audit/22_v9_m4_owner_decision_record.md:13–29, 45–81, 86–110` | Records an owner decision and `NOT AUTHORIZED` execution status | Its H2/H4 table contradicts the original protocol; some operational descriptions are stale |
| Security contract | `docs/architecture/v9_m4_signed_gate_b_ticket_implementation_contract.md:90–100, 146–170, 229–262, 437–450, 545–565` | Ticket v1 fields, trust model, exact tree/hash checks, pending owner decisions | Does not approve durable signed evidence-root binding or same-UID rollback control |
| Previous release manifesto | `/Users/chalermsak/Desktop/nexvia-aegis-v9-m4-release-evidence/release_manifesto_bc440151545aad6795902b285972faac7534c92e.json` | Six-hash binding for `bc44015` only | Not an authoritative current Staging Manifest |
| Historical Cal/Val provenance | `74f93fe`; `results/v9/cal_r2/calibration_report.json` and `results/v9/val_r1/validation_report.json` inventories; `docs/v9_m3_post_validation_audit.md:57–68` | Raw-file identities and report-internal inventory | Later narrative reports cite incompatible raw hashes; owner must approve controlling references |
| Current engineering evidence | `V9_M4_SECOND_AUDIT_CANDIDATE_REPORT.md`, source/tests at `b91cc99` | Safe synthetic regression and known residual risks | Not a final release authorization or authenticated trust anchor |
| Staging approval/candidate designation | Search of tracked files, workspace filenames/text, and known release-evidence directory | No authoritative current record identified | **Unavailable**; owner must supply/approve exact version and SHA |

Restricted Holdout manifests, seed contents, and outcomes were not opened, parsed, or hashed for this baseline. The old manifest and contract were read as documents only. `scripts/tools/generate_release_manifesto.py` was inspected but **not run**, because it would hash restricted Holdout manifests and cannot confer approval.

## Conflicts, assumptions and approval boundary

- **Conflict:** `docs/v9_experiment_protocol.md:24–26, 32–34` defines H2 as core-10 selective risk and H4 as compound-fault incidence reduction, while Decision Record 22:69,71 and the evaluator use incidence H2 and coverage H4. See `V9_M4_SCIENTIFIC_DECISION_GAP_ANALYSIS.md`.
- **Conflict:** Narrative raw hashes in Reports 09/19/20 differ from the files at `74f93fe` and current HEAD. The producer report inventories and a separate local Desktop copy match current bytes. See `V9_M4_HISTORICAL_HASH_RECONCILIATION.md`.
- **Assumption to avoid:** Current HEAD, previous release SHA, generated manifesto, or local digest is not an owner-approved release reference.
- **Unavailable:** owner-controlled Staging Manifest; owner-selected final candidate; independent package/wheel provenance; owner-pinned tool/key hashes; rollback-resistant ledger checkpoint; approved scientific reconciliation.
- **Owner approvals required:** candidate SHA and staging references; corrections to historical hash citations; H1–H5 controlling interpretation; signed evidence-root schema and trust model; runtime/wheel and ledger trust sources. No such approval is inferred from this document.

**Baseline outcome:** `BLOCKED — OWNER RELEASE REFERENCES NOT APPROVED`. Safe independent provenance analysis and design recommendations can continue. Final detached-worktree release verification, production authorization, Holdout, release commit, tag, and push cannot.
