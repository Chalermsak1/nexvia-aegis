# V9-M4 package and runtime provenance inventory

**Prepared:** 2026-10-27 (Asia/Bangkok). **Finding state:** VERIFIED local identity; package origin UNVERIFIED. **Release:** BLOCKED; `GATE_B_NOT_AUTHORIZED`.

This is a read-only inspection of the documentation worktree at `3a8cea5f4a4534df4edd1cc1320bdd75585bc7e7` and the separate engineering checkout at `b91cc99f591e0b3da3e111a287dc9be3ff44c463`. Paths below are repository-relative unless explicitly identified as local runtime paths. No Holdout inputs, reserved seeds, confirmatory outcomes, production launcher, package installation, rebuild, or signing operation were used. The test of the verifier below used a locally computed expected lock digest; it **does not authenticate that digest**.

## Tracked source inventory

| Item | Observed evidence | Classification |
| --- | --- | --- |
| Dependency declaration and build backend | `pyproject.toml:1-17` declares Python `>=3.12` and six top-level dependency groups; `:22-29` declares `uv_build>=0.12.19,<0.13.0` and pytest dev dependency. These are lower-bound declarations, not an artifact inventory. | VERIFIED contents; origin trust UNVERIFIED. |
| Lockfile | `uv.lock:1-3` has lock version 1/revision 3/Python `>=3.12`; `:631-660` lists editable project `nexvia-aegis==0.1.0` and dependency closure; `:663-669` shows NumPy `2.5.3` plus sdist and platform-specific wheel URLs/hashes. A read-only TOML count found 35 package entries, 34 with sdists, 34 with wheel lists, and 751 wheel *variants* across platforms. Those are lock entries, not verified local archives. | VERIFIED local bytes/structure; trust source UNVERIFIED. |
| Raw lock identity | `shasum -a 256 uv.lock` returned `f90654ab95d7b7c543179fc64fe666a912e10f5c9b2e3d72bb9223f2a7e3c2aa`. `git show bc440151545aad6795902b285972faac7534c92e:uv.lock | shasum -a 256` returned the same digest; both commits resolve `uv.lock` to Git blob `78dcba303f69035c4204a6774aa1812eef4b6b0a`. The local draft repeats this raw digest (`docs/reports/v9_m4_release_remediation/V9_M4_STAGING_MANIFEST_DRAFT_UNAPPROVED.md:31`). | VERIFIED within Git/local checkout; **not an independently authenticated release pin**. |
| Contract's older lock reference | `docs/architecture/v9_m4_signed_gate_b_ticket_implementation_contract.md:428-440` states Python `3.12.14`, a *provisional* `uv.lock` digest `345628a865b28e9c5422fd4bc52fd6e23864bd58feaa4b418e8389192c0e7d56`, and a requirement to match recorded wheel hashes. The provisional digest differs from observed bytes. The contract does not identify an approved replacement. | CONFLICTING reference; owner/release reconciliation required. |
| Tracked build/CI records | `git ls-tree -r --name-only HEAD` filtered for `.github/`, `.gitlab-ci`, Dockerfile, requirements, environment file, Makefile, `dist/`, and `*.whl` yielded only `scripts/tools/generate_release_manifesto.py`. That script computes six artifact hashes and Git commit (`scripts/tools/generate_release_manifesto.py:48-99`), not a wheel build/install attestation; its default inputs include restricted manifest paths, so it was **not run**. | MISSING tracked CI build attestation in searched paths; search does not prove no external CI exists. |
| Editable package install | `uv.lock:631-634` declares `source = { editable = "." }`. Local engineering `.venv/lib/python3.12/site-packages/nexvia_aegis-0.1.0.dist-info/direct_url.json` reports `editable:true` and points to the engineering checkout. This is local install metadata, not an authenticated build provenance record. | VERIFIED local metadata; trust UNVERIFIED. |

## Actual runtime and installed package observations

`src/nexvia_aegis/security/runtime_integrity.py:46-78` resolves the active lock dependency closure. Its probe checks installed distribution file hashes from local RECORD metadata, reports versions and selected import origins (`:81-143`), and checks expected lock digest, `-I` isolation, venv/interpreter path, dependency set, and origins (`:147-228`). It explicitly returns `wheel_archive_sha256_verified: false` (`:229-242`) and itself cautions that local RECORD is not independently authenticated archive provenance (`:1-4`). The launcher calls it before evidence-root selection/claim (`src/nexvia_aegis/security/launcher.py:858-874`).

Read-only direct probe in the **engineering checkout** used `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -I -c '...verify_runtime_integrity(p/".venv/bin/python",p,sha256(p/"uv.lock"),approved_venv_root=p/".venv")...'` and exited 0. Selected actual output:

```text
schema_version=nexvia-aegis-runtime-integrity/1.0
verification=LOCK_CLOSURE_VERSIONS_IMPORT_ORIGINS_AND_INSTALLED_RECORDS
lockfile_sha256=f90654ab95d7b7c543179fc64fe666a912e10f5c9b2e3d72bb9223f2a7e3c2aa
python_version=3.12.14; package_count=34; numpy_version=2.5.3
numpy_record_file_count=926
numpy_import_origin=<engineering checkout>/.venv/lib/python3.12/site-packages/numpy/__init__.py
wheel_archive_sha256_verified=false
```

The full executable call was:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -I -c 'import hashlib,json,sys; from pathlib import Path; p=Path.cwd(); sys.path.insert(0,str(p/"src")); from nexvia_aegis.security.runtime_integrity import verify_runtime_integrity; h=hashlib.sha256((p/"uv.lock").read_bytes()).hexdigest(); r=verify_runtime_integrity(p/".venv/bin/python",p,h,approved_venv_root=p/".venv"); print(json.dumps({"schema_version":r["schema_version"],"verification":r["verification"],"lockfile_sha256":r["lockfile_sha256"],"python_version":r["python_version"],"interpreter":r["interpreter"],"package_count":r["package_count"],"wheel_archive_sha256_verified":r["wheel_archive_sha256_verified"],"numpy_version":r["installed_packages"]["numpy"]["version"],"numpy_record_file_count":r["installed_packages"]["numpy"]["record_file_count"],"numpy_import_origin":r["import_origins"]["numpy"]},sort_keys=True))'
```

Two read-only negative calls with fabricated inputs produced `wrong_lock RUNTIME_INTEGRITY_MISMATCH: uv.lock SHA-256 mismatch.` and `wrong_interpreter RUNTIME_INTERPRETER_LOCATION_MISMATCH: Worker must use the approved .venv/bin/python.` The exact command, run in the engineering checkout, was:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -I - <<'PY'
import hashlib
import sys
from pathlib import Path
p = Path.cwd()
sys.path.insert(0, str(p / 'src'))
from nexvia_aegis.security.runtime_integrity import verify_runtime_integrity
from nexvia_aegis.security.ledger import SecurityError
lock_sha = hashlib.sha256((p / 'uv.lock').read_bytes()).hexdigest()
for label, python_path, digest in (
    ('wrong_lock', p / '.venv/bin/python', '00' * 32),
    ('wrong_interpreter', p / '.venv/bin/python3', lock_sha),
):
    try:
        verify_runtime_integrity(python_path, p, digest, approved_venv_root=p / '.venv')
        print(label, 'UNEXPECTED_PASS')
    except SecurityError as exc:
        print(label, str(exc))
PY
```

Neither call touched package files or ran a launcher. Existing synthetic tests assert the same positive behavior, no archive verification, and these two rejections (`tests/test_v9_engineering_remediation.py:139-174`). These observations establish local drift controls, not package-origin authenticity or release readiness.

The local engineering `.venv/pyvenv.cfg:1-6` records CPython 3.12, uv 0.12.19, and no system site packages; it does not authenticate the interpreter binary. The local NumPy `numpy-2.5.3.dist-info/WHEEL` identifies a macOS arm64 wheel tag, `INSTALLER` says `uv`, and `RECORD` contains SHA-256 entries for installed files (and an unhashed RECORD self-entry). These files reside inside the same mutable `.venv` being checked. The verifier hashes entries with a RECORD hash (`runtime_integrity.py:103-127`); it does not compare the original wheel archive bytes to an external owner pin. Its fixed import-origin list appears at `runtime_integrity.py:23-24,128-143,220-228`.

## Archive availability checked, with limits

- `find . -path './results' -prune -o -path './.git' -prune -o -name '*.whl' -print` in the documentation worktree and equivalent search in the engineering checkout (excluding `results` and `.git`) returned no repository/venv wheel archive paths.
- `find /Users/chalermsak/.cache/uv -type f -name '*.whl' -print | wc -l` returned **18** cached wheel files across the user cache; **10** filenames matched `nexvia_aegis-0.1.0*.whl`, all under an editable-build cache. `find ... -name 'numpy*.whl' ... | wc -l` returned **0**. These are local cache snapshots and do not constitute a complete, owner-approved wheelhouse. The cache also includes unrelated projects. No cached wheel was treated as trusted or installed from in this audit.
- The lock lists SHA-256 hashes of remote wheel *variants* (`uv.lock:5-12,663-669`), but this inspection did not establish which archive created each installed distribution or obtain a separately authenticated archive inventory.

## Provenance conclusion

**Verified locally:** exact checked-out lock bytes, local venv/interpreter path and version, 34 selected installed distribution versions, hashed installed RECORD entries, and selected import origins. **Conflicting:** provisional contract lock digest versus the observed checked-in bytes. **Missing/unverified:** independently authenticated candidate-bound lock pin; original wheel archive bytes and a complete platform-specific wheel inventory; signed or owner-controlled build/install attestation; interpreter/build-tool provenance; independent trust over editable checkout and runtime. The current direct probe is useful drift evidence only. SEC-02 remains BLOCKED and Gate B remains `GATE_B_NOT_AUTHORIZED`.
