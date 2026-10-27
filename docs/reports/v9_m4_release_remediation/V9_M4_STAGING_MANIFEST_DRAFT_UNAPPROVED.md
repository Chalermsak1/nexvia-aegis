# V9-M4 Staging Manifest specification — DRAFT, NOT APPROVED

**Draft revision:** 0.1, prepared 2026-10-27 (Asia/Bangkok).  
**Project/milestone:** NEXVIA AEGIS V9-M4.  
**Authority:** None. This is a proposed inventory for owner review, **not** a signed release manifesto, trusted hash source, Gate B authorization, or final release-candidate selection.

## Candidate and scope

| Field | Proposed/observed value | Status |
| --- | --- | --- |
| Proposed engineering candidate | `b91cc99f591e0b3da3e111a287dc9be3ff44c463`, branch `codex/v9-m4-remediation` | **UNAPPROVED; owner may choose a later commit after remediation** |
| Previous release | `bc440151545aad6795902b285972faac7534c92e` | Historical reference only |
| Hash definition | Raw SHA-256 of exact file bytes for release artifacts. Canonical JSON payload SHA-256 is a distinct secondary field where documented. | Proposed manifest rule; owner must approve |
| Evaluation mode | Safe synthetic regression only before Gate B. Reserved Holdout contents remain inaccessible. | Required safety boundary |
| Test command proposed | `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q -p no:cacheprovider` in an approved isolated checkout/venv | Last actual run at same SHA: 301 passed; owner must select final test scope and runtime |

## Proposed artifact inventory

Values in the “local observed” column were calculated from unrestricted files at `b91cc99`; they are **not independently authenticated**. An owner-controlled staging record must declare whether each row is mandatory, its exact revision, and its expected digest. The rightmost column is deliberately not an approval.

| Artifact identity | Local observed raw SHA-256 | Reference/remaining decision |
| --- | --- | --- |
| `experiments/v9_evaluate_holdout.py` | `3f6869a92f0a090ff07e275f592dfee54f7a86230ac44bb3bc8c572f90a22d80` | Candidate-bound evaluator; previous manifesto's evaluator hash is stale |
| `src/nexvia_aegis/security/launcher.py` | `cd35d855cf98f6b263ac3e4debcd46ad4586ca8bf98ec118ebf3e491511847cc` | Owner must pin independently after approved changes |
| `src/nexvia_aegis/security/runtime_integrity.py` | `0ecb8e480c7be3bfbf9e6861029d1909bb9a79e3f29ea216ce2b1c65a1a11a7c` | Current verifier does not prove wheel-archive identity |
| `src/nexvia_aegis/security/ledger.py` | `56bfb3dc03285df555e411ce060de27eb6bdafbf8a72d562c7f1b7c44603f22a` | Local ledger lacks external rollback witness |
| `src/nexvia_aegis/security/verifier.py` | `491430bcda2aa31b75fa2ce0f098583fe8994ec41d8b1d0dd9b9a04af41986a1` | Ticket v1 schema only; owner-approved revision needed |
| `src/nexvia_aegis/security/canonical.py` | `b7636b32b7376751f4dedbb93a53bb946878425742c0adc7dbf1fc60d09b1827` | Include in final trusted-tool inventory |
| `scripts/tools/sign_gate_b_ticket.py` | `1610a72c85a9c2447f6c37bf5d330732240592c77cb9083a8735c28a7b63f95e` | Owner must authenticate outside agent-writable checkout before signing |
| `scripts/tools/run_gate_b_launcher.py` | `3fccb784e3f564af938bde7cbc870ac2534fdc96941f4328adacca21d1f5db3c` | Include launcher entrypoint in trusted-tool inventory |
| `uv.lock` | `f90654ab95d7b7c543179fc64fe666a912e10f5c9b2e3d72bb9223f2a7e3c2aa` | Lock bytes only; package/wheel provenance unresolved |
| `results/v9/cal_r2/selected_policy.json` | `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` | Matches previous manifesto and contract locked policy |
| `results/v9/manifests/test_mix_manifest_r1.json` | **NOT COMPUTED** | Restricted Holdout; contract:151–156 records a locked digest, but this draft has not rechecked contents |
| `results/v9/manifests/test_scen_manifest_r1.json` | **NOT COMPUTED** | Restricted Holdout; same boundary |
| Historical M2R2 Cal/Val and benchmark files | See `V9_M4_HISTORICAL_HASH_RECONCILIATION.md` and previous audit §5 | Exact mandatory set and controlling raw references require owner decision |

## Proposed execution and trust fields still empty

| Required field | Current state / approval needed |
| --- | --- |
| `approved_candidate_sha` | **UNSET**; owner must name full SHA after remediation review. Do not derive from HEAD. |
| `staging_manifest_version`, approval identity, decision date, signature/fingerprint, change history | **UNSET**; owner-controlled governance record required. |
| Scientific protocol revision and H1–H5 rules | **UNSET** pending prospective reconciliation of preregistration and Decision Record 22, with independent statistical review where specified. |
| Durable evidence-root binding | **UNSET** pending ticket schema revision and owner selection of exact external root/storage identifier. |
| Execution checkout and Python environment | **UNSET** pending owner choice of reproducible, noneditable or explicitly authenticated runtime model. |
| Package/wheel trust source | **UNSET**; lock closure and installed RECORD checks do not establish independently trusted wheel archives. |
| Replay checkpoint source and recovery authority | **UNSET**; same-UID rollback protection requires owner trust decision. |
| Owner-pinned launcher/signer/runtime/verifier/public-key references | **UNSET**; local computed hashes cannot self-authenticate. Never place a private key in this manifest. |
| Required safe tests, expected outcomes, and environment | **UNSET** as an approved final matrix; previous 301-pass run is evidence at current engineering SHA only. |
| Holdout authorization | **NOT AUTHORIZED**; no ticket or reserved-data access permitted by this draft. |

## Approval sequence proposed

1. Reconcile historical hash citations without changing artifacts; adopt controlling raw references in a dated owner record.
2. Resolve H1–H5 scientific rules and claim wording prospectively, with independent statistical review for CI, multiplicity, and missing-data questions.
3. Approve security contract revision, evidence-root, wheel provenance, ledger witness, key custody and tool pins; implement and synthetically test resulting code on a separate development path.
4. Review a specific code commit and select the full release-candidate SHA. Produce and approve a new Staging Manifest tied to that SHA and an independent trust source.
5. Only then perform authoritative detached-worktree release verification and re-evaluate readiness. A separate explicit owner decision is required for any Final Release Commit and for Gate B.

**Approval fields:** owner decision record: **PENDING**; owner signature/fingerprint: **PENDING**; independent statistical review: **PENDING**; security reviewer decision: **PENDING**. No approval is implied.
