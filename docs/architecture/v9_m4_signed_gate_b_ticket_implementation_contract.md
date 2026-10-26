# NEXVIA AEGIS V9-M4 — Final Signed Gate B Authorization Implementation Contract

**Contract ID:** `AEGIS-V9-M4-CTR-01`<br>
**Revision:** `2.3` (Pre-Implementation Integrity Hardening)<br>
**Milestone:** V9-M4 (Confirmatory Holdout Evaluation)<br>
**Governance State:** Gate A: PASSED; Gate B: NOT AUTHORIZED (STRICTLY LOCKED)<br>
**Repository:** `/Users/chalermsak/Desktop/nexvia-aegis-main`<br>
**Active Branch:** `v9.0-runtime-assurance`<br>
**Current Baseline Reference Commit:** `c511a0bcae93ed969ffb50504017ca2be88fde95`<br>
**Document Classification:** Architecture and Implementation Specification (Read-Only Contract)

---

## 1. Architecture Decision

### 1.1 Context and Operational Realities
Confirmatory holdout evaluation for Milestone V9-M4 requires strict runtime assurance that production evaluation occurs exactly once per registered partition on pristine, unobserved data using the locked, frozen policy.

Adversarial security reviews identified critical trust-boundary realities:
1. Symmetric credentials or environment variables can be leaked through process arguments, shell histories, subshell environments, or agent tool outputs.
2. In-process verification guards running within the agent-writable repository under the same operating system user identity (`chalermsak`, UID 501) cannot defend against a process that can modify Python source code, substitute repository public keys, or delete local state files.
3. Placing files outside the repository or setting POSIX permissions to `0600` or `0555` protects against *other* local users, but provides **zero protection against an active process running under the same UID 501**.

### 1.2 The Three-Pillar Architecture Decision
To achieve defense-in-depth while maintaining complete intellectual honesty regarding single-user workstation boundaries, NEXVIA AEGIS adopts a **Hybrid Three-Pillar Authorization Architecture**:

$$\mathbf{Architecture} = \mathbf{Owner\text{-}Controlled\ Trusted\ Launcher} \;+\; \mathbf{Ed25519\ Signed\ Ticket\ (RFC\ 8785\ JCS)} \;+\; \mathbf{External\ Persistent\ Anti\text{-}Replay\ Ledger}$$

```
+---------------------------------------------------------------------------------------------------+
| OWNER TRUST DOMAIN (Private / Out-of-Workspace)                                                   |
|   - Ed25519 Private Signing Key (Air-gapped or passphrase-encrypted local path, mode 0600)        |
|   - Verified Signer Utility: scripts/tools/sign_gate_b_ticket.py (digest verified independently)  |
+---------------------------------------------------------------------------------------------------+
                                            |
                                            | Issues signed JSON ticket
                                            v
+---------------------------------------------------------------------------------------------------+
| TRUSTED LAUNCHER BOUNDARY (Owner-Executed Outside Agent Workspace)                                |
|   - Dedicated Setup Tool (Bootstrap): scripts/tools/setup_gate_b_ledger.py (one-time setup only)  |
|   - Stable Concurrency Lock File: ~/.nexvia_security/gate_b_replay_ledger.lock (stable inode)     |
|   - External Replay Ledger: ~/.nexvia_security/gate_b_replay_ledger.json (crash-durable replace)  |
|   - Trusted Public Verification Key Anchor: ~/.nexvia_security/gate_b_owner_pubkey.pem            |
|   - Launcher Script: scripts/launch_gate_b_production.py                                          |
|                                                                                                   |
|   Preflight Verification Sequence:                                                                |
|     1. Pre-lock preliminary clock check (fast-fail if current clock outside signed window)        |
|     2. Acquire exclusive lock via fcntl.flock on existing lock file (fail closed if missing/link) |
|     3. Under-lock definitive expiry check: issued_at_utc <= T_claim <= expires_at_utc             |
|     4. Validate external replay ledger (fail closed if corrupt, missing, or rolled back)          |
|     5. Parse ticket JSON with strict duplicate-key rejection (strict_json_pairs_hook)             |
|     6. Canonicalize payload using RFC 8785 JCS and verify Ed25519 signature                       |
|     7. Only after signature passes: inspect and validate semantic payload claims                 |
|     8. Verify actual execution tree commit: git rev-parse HEAD == approved_commit                 |
|     9. Verify complete execution tree cleanliness: git status --porcelain=v1 --untracked=all == "" |
|    10. Verify runtime interpreter, final lockfile digest, and raw SHA-256 of evaluator, policy   |
|    11. Crash-durable ledger persistence: flush, fsync temp file, os.replace, directory fsync     |
+---------------------------------------------------------------------------------------------------+
                                            |
                                            | Launches simulation worker in validated execution tree
                                            v
+---------------------------------------------------------------------------------------------------+
| EVALUATION RUNTIME (Detached Execution Tree / Subprocess)                                         |
|   - Validated Python Environment: sys.executable, site-packages, dependencies                     |
|   - In-Process Fail-Closed Verification Guard (redundant secondary check)                         |
|   - Executes Exactly One Partition:                                                               |
|       * Mixture: 1,440 episodes, seeds 73000..74439 OR                                           |
|       * Scenario: 1,440 episodes across 12 scenarios, seeds 75000..75119                          |
|   - Emits Output: results/v9/test_mix/ or results/v9/test_scen/                                   |
|   - Writes authorization_record.json and binds ticket to report integrity_sha256                  |
+---------------------------------------------------------------------------------------------------+
                                            |
                                            | Worker exits (exit_code == 0)
                                            v
+---------------------------------------------------------------------------------------------------+
| TRUSTED LAUNCHER POST-EXECUTION TRANSACTION                                                       |
|   - Re-acquires stable lock                                                                       |
|   - If exit_code == 0: updates partition state -> CONSUMED; if both consumed -> CLOSED            |
|   - If exit_code != 0 or abort: updates partition state -> FAILED; ticket -> FAILED_TERMINAL      |
|   - Crash-durably commits updated ledger and releases lock                                        |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Threat Model and Trust Boundaries

### 2.1 The Six Layers of Isolation and Protection
The architecture explicitly distinguishes six layers of security mechanisms:

1. **Repository Isolation:** Physical filesystem boundaries separating the repository workspace (`/Users/chalermsak/Desktop/nexvia-aegis-main`) from external paths like `~/.nexvia_security/`. This prevents authorization state and keys from being tracked, staged, committed, or deleted by standard git operations (`git clean`, `git checkout`).
2. **OS-User Permission Isolation:** POSIX file permissions (`chmod 0600`, `chmod 0400`, `chmod 0555`).<br>
   > [!CAUTION]
   > **The Single-User Workstation Reality:** In macOS, all development processes and agent subshells operate under the user's login account (`chalermsak`, UID 501). POSIX file permissions protect against *other* local accounts, but **cannot prevent any process running under UID 501 from reading, writing, or changing permissions on files owned by UID 501**.
3. **Private-Key Protection:** The owner's Ed25519 private key must be protected by an out-of-band operational boundary (see Section 5). Storing an unencrypted private key file on the same workstation under UID 501 does **not** protect it from a concurrent autonomous agent running under UID 501.
4. **Public-Key Trust-Anchor Protection:** Storing the public key in the repository makes it vulnerable to substitution by any process with write access to the workspace. Placing the public key at `~/.nexvia_security/gate_b_owner_pubkey.pem` protects against repository-scoped edits, but remains readable/writable by UID 501. Absolute public-key integrity requires the owner to verify the public key fingerprint during launch or use an immutable binary anchor.
5. **Replay-Ledger Integrity:** Storing the replay ledger in `~/.nexvia_security/` provides robust protection against accidental duplicate execution, concurrency races, and git cleanups. However, an adversarial same-UID process could delete or roll back the file. Strong anti-replay against a same-UID adversary requires an external append-only service or owner-supervised physical nonces.
6. **Operational Protection Against Concurrent Agents:** The project owner must enforce the operational rule that **the autonomous coding agent must be suspended, terminated, or restricted to read-only tools before the owner executes the Trusted Launcher**.

### 2.2 Threat Matrix and Achieved Mitigations

| Threat Level | Threat Actor & Capability | Attack Vector | Enforced Mitigation | Real Workstation Limitation |
| :---: | :--- | :--- | :--- | :--- |
| **Level 1** | **Accidental Invocation**<br>(Agent, developer, test runner, globbed script) | Unintended invocation during test runs (`pytest`) or general script execution. | In-process fail-closed guard halts immediately if no valid signed ticket is supplied. | None; fully mitigated by code guard. |
| **Level 2** | **Env & CLI Manipulation**<br>(Subshell process, unauthorized caller) | Supplying spoofed environment variables (`V9_M4_AUTH_TOKEN`, etc.) or arbitrary CLI flags. | Ed25519 digital signature over RFC 8785 canonical bytes; requires owner's offline private key. | None; fully mitigated by asymmetric cryptography. |
| **Level 3** | **Evaluator Source Tampering**<br>(Process with workspace write access) | Modifying `v9_evaluate_holdout.py` to bypass guard, return `True`, or mock git/hash checks. | Launcher validates exact git commit, verifies complete git cleanliness, and verifies raw file SHA-256. | If agent runs concurrently under UID 501, it could tamper with launcher; requires owner operational isolation. |
| **Level 4** | **Public Key Substitution**<br>(Process modifying local key files) | Replacing `gate_b_owner_pubkey.pem` with attacker key and signing an unauthorized ticket. | Launcher verifies public key fingerprint against owner-verified external anchor. | Requires owner verification of key fingerprint or external secure storage. |
| **Level 5** | **Anti-Replay State Rollback**<br>(Process modifying local state) | Deleting or editing `gate_b_replay_ledger.json` to repeat a consumed holdout partition. | Persistent lock file (`.lock`) + crash-durable `os.replace` + fail-closed malformed state handling. | Protects against concurrency and crashes; does not protect against intentional deletion by same-UID attacker. |
| **Level 6** | **Host Administrator / Root**<br>(Compromised kernel, root/debugger access) | Direct memory modification, ptrace injection, kernel syscall hooking. | Out of scope for workstation; requires air-gapped machine or hardware enclave. | Unmitigated on local workstation. |

---

## 3. Signed Ticket Specification

### 3.1 Strict JSON Schema
The authorization ticket file (`gate_b_authorization_ticket.json`) contains a top-level envelope enclosing the signed payload and cryptographic metadata:

```json
{
  "ticket_version": "1.0",
  "payload": {
    "milestone": "V9-M4",
    "gate": "GATE_B",
    "scope": "CONFIRMATORY_HOLDOUT_EVALUATION",
    "approved_commit": "c511a0bcae93ed969ffb50504017ca2be88fde95",
    "evaluator_artifact_sha256": "4b83f090b82f8d2eb929a75ff72d9a48970891d4e08f8702c89280d463b7852c",
    "policy_sha256": "5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2",
    "mixture_manifest_sha256": "70fe9d539a7fca7f44e8a1aea2d7193002e520c2d3b4980f461a06a73906f1db",
    "scenario_manifest_sha256": "55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d",
    "lockfile_sha256": "345628a865b28e9c5422fd4bc52fd6e23864bd58feaa4b418e8389192c0e7d56",
    "authorized_partitions": [
      "mixture",
      "scenario"
    ],
    "issued_at_utc": "2026-10-26T06:00:00Z",
    "expires_at_utc": "2026-10-26T08:00:00Z",
    "nonce": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "operator_identity": "chalermsak@project-owner",
    "target_output_root": "results/v9"
  },
  "signature_algorithm": "Ed25519",
  "signature_hex": "4a7d...<128 lowercase hex characters>...9c2e"
}
```

### 3.2 Field Constraints and Provisional vs. Final Release Evidence

| Field | Type | Constraint | Invariant / Expected Value |
| :--- | :---: | :--- | :--- |
| `ticket_version` | `str` | Exact literal | `"1.0"` |
| `milestone` | `str` | Exact literal | `"V9-M4"` |
| `gate` | `str` | Exact literal | `"GATE_B"` |
| `scope` | `str` | Exact literal | `"CONFIRMATORY_HOLDOUT_EVALUATION"` |
| `approved_commit` | `str` | 40-char hex SHA-1 | Final approved Git commit SHA-1 after implementation and testing. *(Current reference: `c511a0bcae93ed969ffb50504017ca2be88fde95` is provisional baseline)* |
| `evaluator_artifact_sha256` | `str` | 64-char hex SHA-256 | Raw file hash of `experiments/v9_evaluate_holdout.py` at `approved_commit`. |
| `policy_sha256` | `str` | 64-char hex SHA-256 | `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` (Locked) |
| `mixture_manifest_sha256` | `str` | 64-char hex SHA-256 | `70fe9d539a7fca7f44e8a1aea2d7193002e520c2d3b4980f461a06a73906f1db` (Locked) |
| `scenario_manifest_sha256` | `str` | 64-char hex SHA-256 | `55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d` (Locked) |
| `lockfile_sha256` | `str` | 64-char hex SHA-256 | Raw file hash of `uv.lock` at `approved_commit`. *(Current reference `345628a...` is provisional baseline)* |
| `authorized_partitions` | `list[str]` | Exact set equality | Exactly `["mixture", "scenario"]` |
| `issued_at_utc` | `str` | ISO 8601 UTC | `YYYY-MM-DDTHH:MM:SSZ` |
| `expires_at_utc` | `str` | ISO 8601 UTC | `YYYY-MM-DDTHH:MM:SSZ`, validity window $\le W_{\max}$ *(Proposed maximum: 120 minutes, PENDING OWNER APPROVAL)*. |
| `nonce` | `str` | 64-char hex | 256 bits of cryptographically secure random entropy (`secrets.token_hex(32)`). |
| `operator_identity` | `str` | Non-empty string | Identified project owner/operator. |
| `target_output_root` | `str` | Exact literal | `"results/v9"` |
| `signature_algorithm` | `str` | Exact literal | `"Ed25519"` |
| `signature_hex` | `str` | 128-char hex | Raw 64-byte Ed25519 signature in lowercase hexadecimal format. |

> [!IMPORTANT]
> **Provisional Baseline vs. Final Release Evidence:** The commit `c511a0b` and `uv.lock` hash `345628a...` are provisional release evidence from the current repository baseline. Once security dependencies (`cryptography`, `rfc8785`) and implementation code are committed, `uv.lock` and `experiments/v9_evaluate_holdout.py` will change. The live Gate B Ticket must bind the **exact final approved values** computed from the Final Commit, not the baseline reference values.

---

## 4. Canonicalization and Signature Verification Sequence

### 4.1 Strict Parsing vs. Semantic Trust
To eliminate confusion between parsing syntactic bytes and trusting semantic claims, the verification pipeline follows a strict, sequential protocol:

```
[Ticket Verification Pipeline]
  1. Syntactic Parse: json.loads(raw_ticket, object_pairs_hook=strict_json_pairs_hook)
     └── Rejects duplicate JSON keys fail-closed.
  2. Envelope Validation:
     ├── Enforce exact envelope keys: {"ticket_version", "payload", "signature_algorithm", "signature_hex"}
     ├── Ensure signature_algorithm == "Ed25519"
     ├── Ensure signature_hex is exactly 128 lowercase hex characters
     └── Ensure payload is a JSON dictionary
  3. Canonicalize Signed Object:
     └── RFC 8785 JCS canonicalization of envelope["payload"] -> canonical_bytes
  4. Cryptographic Verification:
     └── public_key.verify(signature_bytes, canonical_bytes)
     └── If verification fails: ABORT FAIL-CLOSED (INVALID_TICKET_SIGNATURE)
  5. Semantic Trust & Schema Validation (Only executed after signature passes):
     ├── Enforce payload whitelist: exactly 13 required keys, zero unexpected fields
     ├── Enforce strict data types and formats (ISO 8601 UTC, 64-char hex digests)
     ├── Enforce milestone == "V9-M4", gate == "GATE_B", scope == "CONFIRMATORY_HOLDOUT_EVALUATION"
     └── Enforce claim window: issued_at_utc <= T_claim <= expires_at_utc
```

### 4.2 RFC 8785 JSON Canonicalization Scheme (JCS) Compliance
Standard `json.dumps(sort_keys=True)` is **not RFC 8785 compliant**:
- It introduces variable whitespace separators unless explicitly overridden.
- It formats floating point numbers with trailing zeros or differing exponent notation compared to the ECMAScript / RFC 8785 specification.
- It permits `NaN` and `Infinity` literals, which are explicitly forbidden by RFC 8785.
- It escapes characters differently from the strict UTF-8 rules of RFC 8785 (which requires minimal escaping: only `"` and `\` and control characters U+0000..U+001F are escaped; forward slashes `/` remain unescaped).

Therefore:
1. Canonicalization must use a dedicated, verified RFC 8785 library (such as `rfc8785` or an audited equivalent).
2. The signature is computed strictly over `canonical_bytes` of the `payload` dictionary. The `signature_hex` field is in the outer envelope and is excluded from the signed payload.

### 4.3 Duplicate Key Rejection Hook
```python
def strict_json_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Rejects JSON objects containing duplicate keys before dictionary instantiation."""
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"DUPLICATE_JSON_KEY_REJECTED: Key '{key}' appears multiple times.")
        seen.add(key)
        result[key] = value
    return result
```

---

## 5. Private-Key Custody and Signer Integrity

### 5.1 Three Operational Models of Private-Key Custody
The security of the digital signature depends entirely on private key custody. We define three distinct operational models:

1. **Model A: Air-Gapped / Out-of-Band Environment (Preferred Security Boundary):**<br>
   The private signing key never resides on the workstation where the agent executes. It is held on an air-gapped machine, hardware security token, or separate offline laptop. The ticket signing tool (`sign_gate_b_ticket.py`) is run on that separate machine, and only the generated `gate_b_authorization_ticket.json` is transferred to the evaluation runner.<br>
   *Designated as the preferred security boundary, PENDING OWNER CONFIRMATION.*
2. **Model B: Local Out-of-Workspace Storage with Passphrase (Intermediate):**<br>
   The private key is stored at `~/.nexvia_security/gate_b_owner_privkey.pem` on the workstation, but is strongly encrypted with an owner-held passphrase (PKCS#8 AES-256). Even if a same-UID process accesses the file, it cannot sign tickets without the passphrase.<br>
   *Limitation:* Does not prevent an active same-UID process from keylogging the passphrase or corrupting the key file.
3. **Model C: Local Unencrypted File with Operational Inactivity (Weakest):**<br>
   The private key is stored unencrypted at `~/.nexvia_security/` with `chmod 0600`. **This model provides zero technical protection against a concurrent process running under UID 501.** It is only secure under the strict operational assumption that no autonomous agent is active.

### 5.2 Independent Signer Tool Digest Verification
To prevent pre-signing script tampering:
- The signing utility `scripts/tools/sign_gate_b_ticket.py` has an exact raw SHA-256 digest.
- Prior to executing the signing ceremony, the owner must verify this digest against an **independent source outside the agent-writable workspace** (e.g., recorded in the owner's offline decision record, published in a cryptographically signed release advisory, or verified by git commit tree hash in an immutable repository history).

---

## 6. Lock-File Initialization, Reinitialization Prevention, and Crash Durability

### 6.1 Owner-Controlled Bootstrap vs. Reinitialization Prevention
To prevent race conditions, accidental re-initializations, or adversarial ledger truncation:

1. **One-Time Bootstrap Setup Preconditions:**
   The Lock File and initial Ledger must be created once prior to production execution using a dedicated setup tool:
   ```bash
   python scripts/tools/setup_gate_b_ledger.py --init-security-dir ~/.nexvia_security
   ```
   - **Strict Precondition:** An empty ledger (`active_tickets: {}`, `historical_nonces: []`) may **ONLY** be created if neither `gate_b_replay_ledger.json` nor `gate_b_replay_ledger.lock` exists in the target directory.
   - **Reinitialization Attack Prevention:** If either file already exists, `setup_gate_b_ledger.py` **must refuse to execute and abort fail-closed** (`SECURITY_DIR_ALREADY_INITIALIZED`).
   - Once any Ticket has been issued, registered, or claimed, loss, corruption, deletion, rollback, or replacement of the ledger file **must never be repaired by silently creating a new empty ledger**.
   - An adversary could intentionally delete or truncate the ledger file to reset historical claims and replay a holdout partition.
   - Any missing, corrupted, or truncated ledger requires explicit, owner-controlled incident handling. Recovery does not restore anti-replay guarantees unless the prior historical state can be independently established from external immutable evidence (such as out-of-band audit records, committed signed report digests in previous milestones, or owner's offline ticket registry).

2. **Runtime Launcher Verification (No Silent Recreation):**
   When the Trusted Launcher (`scripts/launch_gate_b_production.py`) runs:
   - It opens `gate_b_replay_ledger.lock` using `os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)` (strictly **without** `os.O_CREAT`).
   - If the lock file is missing: abort immediately fail-closed (`LOCK_FILE_MISSING: Run setup_gate_b_ledger.py first`).
   - If the lock file is a symbolic link: abort immediately fail-closed (`SYMLINK_LOCK_REJECTED`).
   - Verifies file ownership (`st_uid == os.getuid()`) and permissions (`(st_mode & 0o777) == 0o600`).
   - Records device and inode `(st_dev, st_ino)` and ensures inode identity is maintained across transactions.
   - **The runtime launcher MUST NEVER create or recreate the lock file.**

3. **Persistent Lock File vs. Atomic Data Replacement:**
   - **Stable Lock File:** `~/.nexvia_security/gate_b_replay_ledger.lock` is **never unlinked, deleted, or replaced**. Its inode remains constant across all executions.
   - **Atomic Data File:** `~/.nexvia_security/gate_b_replay_ledger.json` is updated by writing to `.tmp`, flushing, fsyncing, and calling `os.replace`. This safely replaces the data ledger without disturbing the stable lock file descriptor.

### 6.2 Transaction Protocol and Crash Durability
Every state transition must execute within this atomic, crash-durable transaction:

```python
# Atomic Crash-Durable Ledger Transaction Protocol
lock_path = Path("~/.nexvia_security/gate_b_replay_ledger.lock").expanduser()
if lock_path.is_symlink():
    raise SecurityError("SYMLINK_LOCK_REJECTED: Lock file must not be a symbolic link.")

# Open without O_CREAT: must fail closed if lock file is missing
lock_fd = os.open(str(lock_path), os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
try:
    # 1. Acquire exclusive lock on stable lock file inode
    fcntl.flock(lock_fd, fcntl.LOCK_EX)

    # 2. Verify inode stability and ownership
    stat_before = os.fstat(lock_fd)
    if stat_before.st_uid != os.getuid() or (stat_before.st_mode & 0o777) != 0o600:
        raise SecurityError("UNSAFE_LOCK_PERMISSIONS: Lock file permissions must be exactly 0600.")

    # 3. Read existing data ledger (Fail closed if missing or corrupt)
    ledger_path = Path("~/.nexvia_security/gate_b_replay_ledger.json").expanduser()
    if not ledger_path.exists():
        raise FileNotFoundError("CORRUPTED_OR_MISSING_LEDGER: External ledger does not exist.")

    raw_data = ledger_path.read_text(encoding="utf-8")
    ledger = json.loads(raw_data, object_pairs_hook=strict_json_pairs_hook)
    validate_ledger_integrity(ledger)

    # 4. Check ticket and partition state
    ticket_entry = ledger["active_tickets"].get(ticket_nonce)
    if not ticket_entry:
        raise ValueError("TICKET_NOT_REGISTERED: Ticket nonce not found in active ledger.")

    partition_state = ticket_entry["partitions"][target_partition]["status"]
    if partition_state != "UNCLAIMED":
        raise ValueError(f"PARTITION_UNAVAILABLE: Partition is already {partition_state}.")

    # 5. Under-lock definitive expiration check (Immediately before durable claim mutation)
    t_claim = current_utc()
    if t_claim > ticket_entry["expires_at_utc"]:
        raise SecurityError(
            f"TICKET_EXPIRED_AT_CLAIM_BOUNDARY: Current time {t_claim} exceeds ticket expiry {ticket_entry['expires_at_utc']}."
        )
    if t_claim < ticket_entry["issued_at_utc"]:
        raise SecurityError(
            f"TICKET_NOT_YET_VALID: Current time {t_claim} precedes ticket issuance {ticket_entry['issued_at_utc']}."
        )

    # 6. Mutate state: record actual claim timestamp (T_claim)
    ticket_entry["partitions"][target_partition]["status"] = "CLAIMED"
    ticket_entry["partitions"][target_partition]["claimed_at_utc"] = t_claim
    ticket_entry["partitions"][target_partition]["launcher_pid"] = os.getpid()

    # 7. Crash-durable persistence: flush + fsync temp file
    tmp_path = ledger_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp_path, 0o600)

    # 8. Atomic rename replaces data file inode safely
    os.replace(tmp_path, ledger_path)

    # 9. Synchronize containing directory metadata where supported
    try:
        dir_fd = os.open(str(ledger_path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except (OSError, NotImplementedError):
        pass

finally:
    # 10. Release lock on stable lock file inode
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)
```

### 6.3 Behavior on Interruption and Ambiguous Persistence Outcomes
- If an I/O error or crash occurs prior to `os.replace`, the temporary `.tmp` file is either unlinked or orphaned without altering the established ledger. The transaction fails closed (`LEDGER_PERSISTENCE_FAILED`), and the original ledger remains unmodified.
- If a crash or power failure occurs during `os.replace`, the launcher treats any ambiguous, truncated, or unreadable ledger state upon recovery as a critical fault (`AMBIGUOUS_LEDGER_STATE`) and halts fail-closed.
- **The system must never assert that a Claim is durably committed if the implementation cannot establish that result.**

---

## 7. Two-Partition Ticket Lifecycle and Expiration Semantics

### 7.1 Signed Window vs. Actual Claim Timestamps
To eliminate timing confusion:
1. **Signed Issuance and Expiry (`issued_at_utc`, `expires_at_utc`):** Defined by the owner in the signed ticket envelope. Binds the permitted **Claim Window**: $[ \text{issued\_at\_utc}, \text{expires\_at\_utc} ]$.
2. **Actual Claim Timestamp (`claimed_at_utc`):** Not known before execution. Recorded dynamically by the launcher into the persistent ledger during the atomic claim transaction under the exclusive lock.

### 7.2 Strict Ordering of Operations
The launcher enforces this exact chronological ordering:
1. **Clock Verification (Pre-Lock):** Launcher checks system clock $T_{\text{now}}$. If $T_{\text{now}} < \text{issued\_at\_utc}$ or $T_{\text{now}} > \text{expires\_at\_utc}$, halt immediately (`TICKET_NOT_YET_VALID` or `TICKET_EXPIRED`).
2. **Ledger Locking:** Acquire exclusive `fcntl.flock` on `gate_b_replay_ledger.lock`.
3. **Under-Lock Expiry & Precondition Checks:** Re-verify $T_{\text{claim}} \in [\text{issued\_at\_utc}, \text{expires\_at\_utc}]$ and verify partition state is strictly `UNCLAIMED`.
4. **Crash-Durable Claim Persistence:** Atomically persist `claimed_at_utc = current_utc()`, `status = "CLAIMED"`, and `launcher_pid` with full `fsync` steps to `gate_b_replay_ledger.json`.
5. **Lock Release:** Release lock descriptor.
6. **Simulation Worker Launch:** Spawn the evaluation subprocess in the verified execution tree.

### 7.3 Failure Behavior if Claim Committed but Worker Fails to Start
If the worker process cannot be spawned (e.g. `FileNotFoundError`, `PermissionError`, memory exhaustion, immediate crash, or `SIGKILL`):
- The launcher re-acquires the lock, records partition status as `FAILED`, and marks the ticket as `FAILED_TERMINAL`.
- Even if the launcher crashes before updating to `FAILED`, the persistent state in the ledger remains `CLAIMED`. Because the partition state is no longer `UNCLAIMED`, any subsequent attempt to run that partition will fail closed (`PARTITION_ALREADY_CLAIMED`).
- **A committed claim is permanently spent.** Automatic retries, expiration extensions, or seed rerolls are strictly prohibited. Any replacement run requires a new formal owner decision and a newly issued ticket with a fresh nonce.

### 7.4 Sequential Partition Expiry
- Once claimed within the window, a partition simulation is permitted to run to completion even if its execution extends past `expires_at_utc`.
- However, for the **second partition** (`scenario`) to execute, its claim must **also occur before `expires_at_utc`**.
- If the first partition (`mixture`) runs for an extended period such that `expires_at_utc` passes before the second partition is claimed, the launcher **must reject the second partition claim fail-closed** (`TICKET_EXPIRED`).
- Maximum validity window policy: $W_{\max} = 120\text{ minutes}$ is designated as **`PENDING_OWNER_APPROVAL`**.

### 7.5 Formal State Machine

```
                      TICKET: ISSUED
              [mixture: UNCLAIMED, scenario: UNCLAIMED]
                          |
             Claim Mixture (T_claim <= expires_at)
                          v
                  TICKET: ACTIVE_PARTIAL
               [mixture: CLAIMED, scenario: UNCLAIMED]
                     /          \
      Simulation Fail/Crash      Simulation Success (Exit 0)
                   /              \
                  v                v
      TICKET: FAILED_TERMINAL      TICKET: ACTIVE_PARTIAL
      [mixture: FAILED, ...]       [mixture: CONSUMED, scenario: UNCLAIMED]
                                           |
                              Claim Scenario (T_claim <= expires_at)
                                           v
                                   TICKET: ACTIVE_PARTIAL
                                [mixture: CONSUMED, scenario: CLAIMED]
                                      /          \
                       Simulation Fail/Crash      Simulation Success (Exit 0)
                                    /              \
                                   v                v
                       TICKET: FAILED_TERMINAL      TICKET: CLOSED
                       [..., scenario: FAILED]      [mixture: CONSUMED, scenario: CONSUMED]
```

---

## 8. Runtime and Release Integrity Verification

### 8.1 Approved Reproducible Runtime
To guarantee reproducible evaluation, the runtime environment must satisfy:
1. **Python Interpreter:** Python `3.12.14` in virtual environment (`.venv/bin/python`).
2. **Dependency Lock Information:** `uv.lock` at approved commit. *(Current baseline digest `345628a865b28e9c5422fd4bc52fd6e23864bd58feaa4b418e8389192c0e7d56` is provisional evidence; final digest will be locked upon merge)*.
3. **Core Pinned Dependencies:**
   - `gymnasium==1.4.0` (with `mujoco`)
   - `matplotlib==3.11.2`
   - `numpy==2.5.3`
   - `scipy==1.18.1`
   - `pytest==9.1.1` (dev)

### 8.2 Dependency Location vs. Dependency Integrity Checks
The launcher distinguishes two tiers of dependency validation:
- **Location Check (Basic):** Verifies that `sys.executable` matches `.venv/bin/python` and that imported packages resolve strictly from `.venv/lib/python3.12/site-packages/` (rejecting external `PYTHONPATH` tampering).
- **Integrity Check (Cryptographic):** Verifies the raw SHA-256 digest of `uv.lock` against the expected release digest and validates that installed package distributions match their recorded wheel hashes.

### 8.3 Complete Execution Tree Cleanliness
Before execution starts, the launcher verifies directly within the execution tree:
1. `git rev-parse HEAD == payload["approved_commit"]`
2. `git status --porcelain=v1 --untracked-files=all == ""` (Strictly empty: zero staged, unstaged, or untracked files).
3. Raw SHA-256 of evaluator source (`experiments/v9_evaluate_holdout.py`).
4. Raw SHA-256 of frozen policy (`results/v9/cal_r2/selected_policy.json`).
5. Raw SHA-256 of Mixture manifest (`results/v9/manifests/test_mix_manifest_r1.json`).
6. Raw SHA-256 of Scenario manifest (`results/v9/manifests/test_scen_manifest_r1.json`).
7. Raw SHA-256 of dependency lockfile (`uv.lock`).

> [!CAUTION]
> **Workstation Limitation:** Neither dependency path checks nor setting filesystem permissions to `0555` prevent an active malicious process running under the same UID 501 from modifying dynamic libraries (`.dylib`) or memory space. Runtime integrity relies strictly on the operational assumption of an uncompromised user environment without concurrent agent activity.

---

## 9. Preserved Statistical and Protocol Invariants

The authorization system governs **execution rights only**. It has zero authority to alter statistical thresholds, seed ranges, or analysis protocols.

| Invariant | Authoritative Protocol Specification |
| :--- | :--- |
| **Frozen Policy** | `V9_CAND_1_TIER1_STRICTEST` (`5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2`) |
| **Mixture Manifest** | `test_mix_manifest_r1.json` (`70fe9d539a7fca7f44e8a1aea2d7193002e520c2d3b4980f461a06a73906f1db`) |
| **Scenario Manifest** | `test_scen_manifest_r1.json` (`55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d`) |
| **Mixture Seeds** | $N = 1,440$ episodes on seeds `73000 .. 74439`, PRNG branch $p = 4$. |
| **Scenario Seeds** | $N = 1,440$ episodes across 12 scenarios $\times$ 120 seeds (`75000 .. 75119`), PRNG branch $p = 5$. |
| **Hypothesis $H_1$** | 1-sided Clopper–Pearson 95% UCB $\le 0.05$ with minimum accepted count $M \ge 59$. |
| **Hypothesis $H_2$** | Exact 2-sided McNemar test + Newcombe paired CI vs. V7/V8 baselines. |
| **Hypothesis $H_3$** | Paired Student's $t$ Wald LCB $> -0.05$ on 1,200 $S_{10}$ pairs AND $\widehat{TSR} \ge 0.94$. Newcombe Method 10 reported concurrently as prespecified sensitivity analysis. |
| **Hypothesis $H_4$** | Sample empirical task coverage $\hat{C} \ge 0.35$ (target $\ge 0.45$). |
| **Hypothesis $H_5$** | Berger Intersection-Union Test across 12 scenarios (minimum rejection at $\alpha = 0.05$), with Holm–Šidák multiplicity reporting kept distinct. |

---

## 10. Audit Records and Evidence Separation

### 10.1 Separation of Record Domains
- **Production Output Directory (`results/v9/test_{partition}/`):**<br>
  Contains execution artifacts: episodes CSV, summary CSV, final report JSON, and `authorization_record.json` (containing the verified ticket payload, public key fingerprint, verification timestamp, and launcher environment). The final report's `integrity_sha256` covers `authorization_record.json`.
- **External Replay Ledger (`~/.nexvia_security/gate_b_replay_ledger.json`):**<br>
  Contains historical nonces, claim timestamps, completion timestamps, process PIDs, exit codes, and output report SHA-256 hashes.
- **Zero Secret Exposure:** Private keys, signing passphrases, and decrypted credentials must **never** be logged or captured in output files.

---

## 11. Comprehensive Security Test Matrix (26 Invariants)

All tests in `tests/test_v9_gate_b_authorization.py` must use dynamic, in-memory dummy Ed25519 keypairs. Zero real keys or production episodes are used.

| Test ID | Category | Test Condition | Expected Result |
| :---: | :--- | :--- | :--- |
| **TC-01** | Happy Path | Valid ticket, clean commit, mixture partition | `MIXTURE_CLAIMED`, execution proceeds. |
| **TC-02** | Happy Path | Valid ticket, clean commit, scenario partition | `SCENARIO_CLAIMED`, execution proceeds. |
| **TC-03** | Lifecycle | Two sequential invocations under single ticket | Mixture succeeds, Scenario succeeds, ticket `CLOSED`. |
| **TC-04** | Cryptography | Bit-flipped signature byte | Rejects with `INVALID_TICKET_SIGNATURE`. |
| **TC-05** | Cryptography | Modified byte in canonical payload | Rejects with `INVALID_TICKET_SIGNATURE`. |
| **TC-06** | File Handling | Missing ticket JSON file | Rejects with `TICKET_FILE_NOT_FOUND`. |
| **TC-07** | Parsing | Duplicate JSON keys in ticket | Rejects with `DUPLICATE_JSON_KEY_REJECTED`. |
| **TC-08** | Parsing | Unrecognized extra field in payload | Rejects with `UNRECOGNIZED_TICKET_FIELD`. |
| **TC-09** | Expiry | `expires_at_utc` in the past at claim time | Rejects with `TICKET_EXPIRED`. |
| **TC-10** | Expiry | `issued_at_utc` in the future | Rejects with `TICKET_NOT_YET_VALID`. |
| **TC-11** | Expiry | Window exceeds approved maximum ($>W_{\max}$) | Rejects with `VALIDITY_WINDOW_TOO_LONG`. |
| **TC-12** | Release Binding| Git HEAD differs from `approved_commit` | Rejects with `COMMIT_MISMATCH`. |
| **TC-13** | Release Binding| Staged or unstaged tracked git changes | Rejects with `DIRTY_EXECUTION_TREE`. |
| **TC-14** | Release Binding| Untracked files present in execution tree | Rejects with `UNTRACKED_FILES_DETECTED`. |
| **TC-15** | Artifact Binding| Modified `v9_evaluate_holdout.py` hash | Rejects with `EVALUATOR_ARTIFACT_MISMATCH`. |
| **TC-16** | Artifact Binding| Modified `selected_policy.json` hash | Rejects with `POLICY_HASH_MISMATCH`. |
| **TC-17** | Artifact Binding| Modified `test_mix_manifest_r1.json` hash | Rejects with `MIXTURE_MANIFEST_MISMATCH`. |
| **TC-18** | Artifact Binding| Modified `test_scen_manifest_r1.json` hash | Rejects with `SCENARIO_MANIFEST_MISMATCH`. |
| **TC-19** | Anti-Replay | Attempting to run partition already `CONSUMED` | Rejects with `PARTITION_ALREADY_CONSUMED`. |
| **TC-20** | Anti-Replay | Concurrency race (two processes claiming same ticket) | Lock allows exactly one; second gets `ALREADY_CLAIMED`. |
| **TC-21** | Inode Stability| Verifies lock file inode remains constant during update| Lock held across `os.replace` on data ledger. |
| **TC-22** | Robustness | Missing or corrupted external ledger file | Rejects with `CORRUPTED_OR_MISSING_LEDGER` (no silent recreation). |
| **TC-23** | Fault Handling | Crash/abort after durable claim before completion | Partition stays `CLAIMED`/`FAILED`; ticket enters `FAILED_TERMINAL`. |
| **TC-24** | Expiry | Ticket expires after Mixture completes, before Scenario | Mixture valid; Scenario rejected with `TICKET_EXPIRED`. |
| **TC-25** | Anti-Reinit | Bootstrap tool run on existing ledger directory | Rejects with `SECURITY_DIR_ALREADY_INITIALIZED`. |
| **TC-26** | Expiry Lock | System clock exceeds expiry while acquiring lock | Under-lock check aborts `TICKET_EXPIRED_AT_CLAIM_BOUNDARY`. |

---

## 12. Security Claims and Explicit Limitations

### 12.1 Enforced Cryptographic Properties
- **Non-Forgeability:** An autonomous agent or external process cannot construct a valid authorization ticket without possession of the owner's offline Ed25519 private key.
- **Payload Immutability:** Any alteration of commit, policy hash, manifest hashes, lockfile hash, partition names, timestamps, or nonce invalidates the digital signature.
- **Canonical Determinism:** RFC 8785 canonical serialization guarantees identical byte encoding across platforms and parsers.

### 12.2 Enforced Application and State-Machine Properties
- **Single-Shot Partition Execution:** Once a partition claim is written to the ledger, that partition cannot be claimed again under the same ticket.
- **Terminal Lockout on Abort:** A crashed, interrupted, or failed run transitions to `FAILED_TERMINAL`, permanently preventing automated reruns or seed snooping.
- **Fail-Closed Artifact Verification:** Discrepancies in git commit, git cleanliness, policy hash, manifest hashes, or lockfile hash halt execution before any simulation RNG is initialized.

### 12.3 Operational Assumptions
- **Owner-Supervised Invocation:** The owner initiates the Trusted Launcher directly from an interactive, owner-controlled terminal session.
- **Agent Suspension:** Autonomous agents with write access to the workspace or shell tools are deactivated or suspended during the confirmatory execution window.
- **Private Key Custody:** The owner keeps the private signing key strictly offline and never transfers it to the repository or agent environment.

### 12.4 Threats Outside the Chosen Trust Boundary
- **Malicious Same-UID Host Processes:** A malicious process running concurrently under UID 501 with unrestricted filesystem and shell access can modify the launcher or delete the external ledger. This threat is mitigated operationally by owner custody, not by POSIX permissions.
- **Compromised Host Kernel / Root:** Hypervisor, kernel, or root-level compromise is out of scope for workstation execution.

---

## 13. Owner Decision Register

The following register formally categorizes decisions by their evidentiary and governance status:

| Item | Category | Current Status | Description / Resolution Path |
| :--- | :---: | :---: | :--- |
| **Frozen Policy Hash** | Repository Evidence | **LOCKED** | `5a89d6061b379f1b34ab47be0deef8d63180d3e4c21d18c478bc7e451f5c84e2` (Cal R2) |
| **Mixture Manifest Hash** | Repository Evidence | **LOCKED** | `70fe9d539a7fca7f44e8a1aea2d7193002e520c2d3b4980f461a06a73906f1db` (1,440 episodes) |
| **Scenario Manifest Hash** | Repository Evidence | **LOCKED** | `55e04c450ab1bfa5e272003d3b8953b4b8ab65a1a764af97152e7b84e33f4b2d` (1,440 episodes) |
| **Statistical Targets H1–H5** | Repository Evidence | **LOCKED** | Defined in `docs/v9_experiment_protocol.md` and Decision Record 22. |
| **Baseline Reference Commit** | Repository Evidence | **PROVISIONAL** | `c511a0bcae93ed969ffb50504017ca2be88fde95` (Provisional baseline; Final Commit designated upon merge). |
| **Dependency Lockfile SHA-256** | Repository Evidence | **PROVISIONAL** | Baseline `uv.lock`: `345628a865b28e9c5422fd4bc52fd6e23864bd58feaa4b418e8389192c0e7d56` (Final locked upon merge). |
| **Python Version** | Repository Evidence | **LOCKED** | Python `3.12.14` in virtual environment (`.venv/bin/python`). |
| **Dependencies Addition** | Awaiting Owner Approval | **PENDING** | Confirm addition of `cryptography>=42.0.0` and `rfc8785>=0.1.4` (or `canonicaljson>=2.0.0`) to `pyproject.toml`. |
| **RFC 8785 Library Choice** | Awaiting Owner Approval | **PENDING** | Select between Python `rfc8785` package vs. audited in-tree RFC 8785 serializer. |
| **Signing Custody Model** | Awaiting Owner Approval | **PENDING** | Select Model A (air-gapped machine) vs. Model B (passphrase-protected local file). Model A is preferred. |
| **Maximum Validity Window** | Awaiting Owner Approval | **PENDING** | Approve $W_{\max} = 120\text{ minutes}$ for the two-partition claim window. |
| **Execution Tree Model** | Awaiting Owner Approval | **PENDING** | Select detached worktree (`/tmp/nexvia_exec_<nonce>/`) vs. in-tree execution with cleanliness checks. |
| **Final Approved Commit** | Awaiting Owner Approval | **PENDING** | Formal approval of the merge commit SHA-1 after implementation testing passes. |
| **Implementation Prerequisites**| Implementation Task | **PENDING** | Installing dependencies, writing bootstrap tool, canonicalizer, ledger, launcher, and 26 regression tests. |
| **Same-UID Host Limitation** | Inherent Limitation | **ACKNOWLEDGED**| Mitigated strictly through operational owner custody, not local OS permissions. |

---

## 14. Phased Implementation Checklist

- [ ] **Phase 1: Dependencies & Canonicalizer**
  - Add `cryptography` and `rfc8785` to `pyproject.toml`.
  - Implement `src/nexvia_aegis/security/canonical.py` (RFC 8785 JCS + duplicate key detector).
- [ ] **Phase 2: Stable-Lock Anti-Replay Ledger & Bootstrap Utility**
  - Implement `scripts/tools/setup_gate_b_ledger.py` (owner-controlled bootstrap tool with anti-reinitialization).
  - Implement `src/nexvia_aegis/security/ledger.py` with persistent `.lock` file, crash durability (`fsync`), and atomic `os.replace`.
- [ ] **Phase 3: Offline Signing Tool & Trusted Launcher**
  - Implement `scripts/tools/sign_gate_b_ticket.py` (owner offline utility with independent digest verification).
  - Implement `scripts/launch_gate_b_production.py` (independent preflight & supervisory runner).
- [ ] **Phase 4: Evaluator Runtime Integration**
  - Refactor `experiments/v9_evaluate_holdout.py` to record `authorization_record.json`.
- [ ] **Phase 5: 26-Case Test Suite Verification**
  - Implement `tests/test_v9_gate_b_authorization.py` covering TC-01 through TC-26.
  - Verify all 176+ existing regression tests pass with zero regressions.
- [ ] **Phase 6: Final Commit Freeze & Owner Decision Record**
  - Commit implementation, record Final Commit, issue live Gate B decision record.

---

## 15. Governance Certification

It is strictly certified that during this review:
- **No Python source files or test files were modified.**
- **No project dependencies were added or altered.**
- **No real cryptographic keys, signatures, or tickets were generated.**
- **No Holdout episodes were generated, simulated, or loaded.**
- **Gate B remains strictly NOT AUTHORIZED.**

**Contract Author:** NEXVIA AEGIS Automated Assurance Agent<br>
**Review Date:** October 26, 2026<br>
**Status:** `IMPLEMENTATION_CONTRACT_READY_FOR_OWNER_REVIEW`
