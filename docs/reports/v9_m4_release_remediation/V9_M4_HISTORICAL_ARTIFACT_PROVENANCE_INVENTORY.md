# V9-M4 historical Calibration and Validation artifact provenance inventory

**Prepared:** 2026-10-27 (Asia/Bangkok). **Status:** read-only evidence inventory; not an approved release reference. **Boundary:** Calibration M2R2 and Validation M3 files only. No restricted Holdout manifest, reserved seed content, or confirmatory output was opened or hashed. Gate B remains `GATE_B_NOT_AUTHORIZED`.

## Identity, method, and limits

This inventory was checked in the documentation worktree `codex/v9-m4-release-blocker-docs`, based on `b91cc99f591e0b3da3e111a287dc9be3ff44c463`. The two producer reports declare `COMPLETE_VALID` and creation times at `results/v9/cal_r2/calibration_report.json:2-9` and `results/v9/val_r1/validation_report.json:2-9`. Those are **producer claims**, not an independent attestation that the simulations were run as described. The Validation narrative reports 480 simulated episodes and a post-processing-only repair at `docs/v9_m3_post_validation_audit.md:18-23`; this inventory verifies bytes and internal records, not the physical execution history or real-robot performance.

Commands executed from the repository root (read-only). The Python allowlist prevents a producer inventory from expanding the read scope into a reserved Holdout path:

```sh
git diff --name-only 74f93fe2613221c476828d1558c03d0598c06b7e HEAD -- results/v9/cal_r2 results/v9/val_r1 results/v9/manifests/cal_manifest_r2.json results/v9/manifests/val_manifest_r1.json
git log --diff-filter=A -1 --format='%H %ad %s' --date=iso-strict -- results/v9/cal_r2/calibration_report.json
git log --diff-filter=A -1 --format='%H %ad %s' --date=iso-strict -- results/v9/manifests/cal_manifest_r2.json
git log --diff-filter=A -1 --format='%H %ad %s' --date=iso-strict -- results/v9/manifests/val_manifest_r1.json
python3 - <<'PY'
import hashlib, json, pathlib, subprocess
reports = ['results/v9/cal_r2/calibration_report.json', 'results/v9/val_r1/validation_report.json']
allowed = {'configs/v9_candidates_frozen_r1.json', 'results/v9/manifests/cal_manifest_r2.json', 'results/v9/manifests/val_manifest_r1.json'}
paths = set(reports)
for report in reports:
    data = json.loads(pathlib.Path(report).read_bytes())
    for path, expected in data['artifact_sha256'].items():
        assert path in allowed or path.startswith(('results/v9/cal_r2/', 'results/v9/val_r1/'))
        assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() == expected
        paths.add(path)
    print(report, 'inventory', len(data['artifact_sha256']), 'MATCH')
canonical_matches = 0
for path in sorted(paths):
    raw = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    blob = subprocess.check_output(['git', 'show', f'74f93fe:{path}'])
    assert raw == hashlib.sha256(blob).hexdigest()
    if path.endswith('.json'):
        data = json.loads(pathlib.Path(path).read_bytes())
        if 'integrity_sha256' in data:
            payload = {k: v for k, v in data.items() if k != 'integrity_sha256'}
            kwargs = {'sort_keys': True, 'indent': 2} if '/manifests/' in path else {'sort_keys': True, 'separators': (',', ':'), 'ensure_ascii': True}
            assert hashlib.sha256(json.dumps(payload, **kwargs).encode()).hexdigest() == data['integrity_sha256']
            canonical_matches += 1
print('paths', len(paths), 'raw_git_match', len(paths), 'stored_canonical_matches', canonical_matches)
PY
```

**Actual outcomes:** the Git diff printed no paths; Git introductions were `74f93fe` for the Calibration report, `cbd9910` for the Calibration manifest, and `dd58b83` for the Validation manifest. The script printed producer-inventory **7 MATCH** and **6 MATCH**, followed by `paths 14 raw_git_match 14 stored_canonical_matches 8`; every assertion succeeded. Raw SHA-256 is over exact bytes. For non-manifest JSON, canonical payload means sorted keys, compact separators, ASCII-escaped JSON, UTF-8, excluding top-level `integrity_sha256` (`src/aegis/v9/risk_statistics.py:636-640`). Manifest integrity uses sorted keys with `indent=2`, excluding the same top-level field (`src/aegis/v9/randomization.py:162-167,251-256`). The two canonical serializations are **not interchangeable**. CSV has no defined canonical-payload digest here. Report writers serialize pretty-printed JSON (`experiments/v9_calibrate_ltt.py:970-974`; `experiments/v9_validate.py:744-747`). No packages were installed, and no experiment runner was executed.

## Git introduction and producer chain

| Artifact class | Earliest tracked introduction found by `git log --diff-filter=A` | Producer / citation evidence | Status |
| --- | --- | --- | --- |
| Calibration manifest `results/v9/manifests/cal_manifest_r2.json` | `cbd9910053e727be4cfdfb2d7a810d7dbf682ee6`, 2026-10-25 12:13:49 +07:00 | Manifest generator digest scheme `src/aegis/v9/randomization.py:142-167`; contemporaneous digest citation `docs/v9_m2r2_protocol_amendment.md:92-97` | **Verified tracked file identity**; author approval of release reference unverified. |
| Validation manifest `results/v9/manifests/val_manifest_r1.json` | `dd58b83a749980b4aa88de8da77e2d1591a8dac1`, 2026-10-25 13:42:54 +07:00 | Generator `src/aegis/v9/randomization.py:225-256`; `docs/v9_m3_post_validation_audit.md:59-68` | **Verified tracked file identity**; independent trust anchor missing. |
| Frozen candidate family `configs/v9_candidates_frozen_r1.json` | `cd3bb8cc47cf47e3636665b87a1e6694cc0a1e25`, 2026-10-24 23:05:27 +07:00 | Calibration report inventory `results/v9/cal_r2/calibration_report.json:453-460` | **Verified tracked file identity**. |
| Calibration and Validation result files listed below | `74f93fe2613221c476828d1558c03d0598c06b7e`, 2026-10-27 16:37:45 +07:00 | Calibration producer inventory `results/v9/cal_r2/calibration_report.json:453-462`; Validation producer inventory `results/v9/val_r1/validation_report.json:411-419` | **Verified bytes at artifact commit and current checkout**. Some earlier reports predate this Git addition, so their citations cannot by themselves identify those exact blobs. |

The reports' own `artifact_sha256` mappings bind their input and output files internally. Calibration includes seven entries (`results/v9/cal_r2/calibration_report.json:453-460`); Validation includes six (`results/v9/val_r1/validation_report.json:411-417`). Reports themselves are verified by their stored `integrity_sha256` fields at lines 462 and 419; a self-declared digest does not provide an externally authenticated origin. The prior read-only reconciliation records a matching separate Desktop checkout (`docs/reports/v9_m4_release_remediation/V9_M4_HISTORICAL_HASH_RECONCILIATION.md:7`); that claim was **not independently repeated in this workstream** and the Desktop copy is not a cryptographic trust anchor.

## Exact inventory

Each raw digest below was recomputed from local bytes and compared to `git show 74f93fe:<path>`; all Git comparisons were **MATCH**. `MATCH` after a canonical digest means recomputation equaled the stored top-level `integrity_sha256`. Source locations for producer-listed raw digests are Calibration report `:453-460` and Validation report `:411-417`; manifest and other canonical values are in the corresponding file's `integrity_sha256` field.

| Artifact (repository-relative path) | Raw SHA-256 | Stored/recomputed canonical payload SHA-256 | Source role |
| --- | --- | --- | --- |
| `configs/v9_candidates_frozen_r1.json` | `346f95929f244b4e93f14d784e7dd1d9b5ce0168404745925eac80a5cd11bf18` | `732862c33d5a2e987bd2065e83b92bec5ad4ffb16a9c3b56a7b15ec6cb9b4d72` MATCH | Frozen candidates; `configs/v9_candidates_frozen_r1.json:291`. |
| `results/v9/manifests/cal_manifest_r2.json` | `49bf68b60f7dd76219a17383bdc829005f4dedb0fb1f1ed687ed23eb66fce9e0` | `b0161b8ea2008287744238be219f286bb346599efcd6a8d555abb6258566fa72` MATCH | Calibration manifest; `:38,25001`. |
| `results/v9/cal_r2/calibration_run_config_frozen_r2.json` | `1a19f6b4c294217260540db19af877f514c852d09921cb06523baaca7ab77564` | `390af9d5c953bd09407d046def719bb9e13aec257f0b0d49e28c8d179c10635d` MATCH | Calibration run config; `:86`. |
| `results/v9/cal_r2/cal_episodes.csv` | `f3e153fbc0f919ce60c7b60152094c077eb0ed13be1eeb910d36760df078ac6e` | — | Calibration episode records. |
| `results/v9/cal_r2/cal_candidate_summary.csv` | `c37f673d0751e1848687f286c5c8199b151a24d1a199363b1a8191057725a3ae` | — | Calibration summary. |
| `results/v9/cal_r2/cal_scenario_breakdown_diagnostic.csv` | `264c68620e2b7be1a69c7c5fdcfdedbb014dc12b4295b580e10fa5002f7b4c05` | — | Calibration diagnostic. |
| `results/v9/cal_r2/selected_policy.json` | `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` | `90dc5c0068bb62187415bba57fbf9cafc1f18e111ad5790b0214961490902034` MATCH | Frozen selected policy; `:77`. |
| `results/v9/cal_r2/calibration_report.json` | `c07b04ba1600aad2416ade36cc6e9c33501327fb4b0a03d2d5b05b6f9b6a963e` | `016990be14b2e751edfbc9d0620e1f928a7f3ba31e2b2f723d4228c1fe81da1b` MATCH | Calibration producer report; `:453-462`. |
| `results/v9/manifests/val_manifest_r1.json` | `72d9b98bda622d80db4c5aa8d9e4b1ce88f0bbc52d3bb26258917cea08959175` | `40ff489504ce628f954b735b562474474b746a2c38c65d459d1084b625909f1e` MATCH | Validation manifest; `:72,13035`. |
| `results/v9/val_r1/validation_run_config_frozen_r1.json` | `a09ebc079537233d6ced80c4deba71deed8f49c34ab437c4afa7f4a82d00b100` | `b3ec3c6016295ec377aad05ff533d91b8e6d73266196fe6a92302a4c2d5e5c24` MATCH | Validation run config; `:58`. |
| `results/v9/val_r1/val_episodes.csv` | `1b6b80402ffe40bce66d4bd9df27556433988e54ba813ce26e0fcca886dcc41e` | — | Validation episode records, producer-reported 480 episodes (`docs/v9_m3_post_validation_audit.md:18-23,41-43`). |
| `results/v9/val_r1/val_summary.csv` | `d44a41cf3901e162b9fb46923122bfd5100e6d027fdbf0e98491e7a8ce83783e` | — | Validation summary. |
| `results/v9/val_r1/val_scenario_breakdown.csv` | `60ff1d9fa3a766b3e17a93f92ceffe41cb7c8a74022a1535d3dfc2d4c454de08` | — | Validation scenarios. |
| `results/v9/val_r1/validation_report.json` | `a5f4df07996c6e5c04a48b5ed86668960bafb691aa489c526e5232aea635b500` | `6aa98a3cf5e9d594a3ccae8903881ac62e0fbc80e025704beb65bab1876846d3` MATCH | Validation producer report; `:411-419`. |

## Conflicting citations and unresolved provenance

The exact conflicts are mapped in the companion `V9_M4_HISTORICAL_HASH_ERRATUM_DRAFT.md` and existing `V9_M4_HISTORICAL_HASH_RECONCILIATION.md:14-21`. Reports 09, 10, 13, 19, and 20 cite nonmatching digests for six of the above files (`docs/reports/v9_m4_statistical_audit/09_m4_statistical_remediation.md:155-158`; `10_v9_m4_post_remediation_readiness.md:92-98`; `13_v9_m4_final_preexecution_review.md:68-75`; `19_frozen_policy_and_h3_method_audit.md:235-243`; `20_v9_m4_owner_authorization_readiness.md:284-292`). Report 10's header says *Canonical SHA-256* even when its policy value equals the raw digest (`:92-98`), so digest-scope terminology is itself inconsistent. The source bytes or computation that produced the discrepant full hashes were not established from the inspected evidence. We therefore classify the **available file identities as verified**, but the **older conflicting citations and final authoritative release references as unresolved**. No hash in this inventory is independently owner-authenticated merely by appearing in local Git or a local producer report.

**Required closure:** a dated owner/research-integrity disposition of each old citation, an exact file path/version/commit and raw-versus-canonical definition for each approved reference, and independently authenticated staging trust evidence. Until then, provenance is insufficient for final release comparison; this inventory grants no Gate B authorization.
