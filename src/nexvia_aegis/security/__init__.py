"""NEXVIA AEGIS Security and Runtime Assurance Module.

Implements cryptographic authorization primitives, RFC 8785 canonicalization,
and Gate B ticket verification for Milestone V9-M4.
"""

from nexvia_aegis.security.canonical import (
    canonicalize_payload,
    parse_strict_json,
    strict_json_pairs_hook,
)
from nexvia_aegis.security.verifier import (
    SecurityError,
    validate_semantic_payload,
    verify_ticket_envelope,
)

from nexvia_aegis.security.ledger import (
    LOCK_FILE_NAME,
    LEDGER_FILE_NAME,
    PersistentLedgerLock,
    bootstrap_security_directory,
    execute_claim_transaction,
    execute_outcome_transaction,
    read_ledger,
    reconcile_stranded_claim,
    register_ticket,
    resolve_security_dir,
)
from nexvia_aegis.security.launcher import (
    cleanup_detached_worktree,
    evaluate_execution_statuses,
    launch_gate_b_partition,
    prepare_detached_worktree,
    reconcile_execution_tree,
    sanitize_environment,
    supervise_worker,
    validate_output_report,
    verify_launcher_integrity,
    verify_runtime_integrity,
    verify_trust_anchor,
)

__all__ = [
    "LOCK_FILE_NAME",
    "LEDGER_FILE_NAME",
    "PersistentLedgerLock",
    "SecurityError",
    "bootstrap_security_directory",
    "canonicalize_payload",
    "cleanup_detached_worktree",
    "evaluate_execution_statuses",
    "execute_claim_transaction",
    "execute_outcome_transaction",
    "launch_gate_b_partition",
    "parse_strict_json",
    "prepare_detached_worktree",
    "read_ledger",
    "reconcile_execution_tree",
    "reconcile_stranded_claim",
    "register_ticket",
    "resolve_security_dir",
    "sanitize_environment",
    "strict_json_pairs_hook",
    "supervise_worker",
    "validate_output_report",
    "validate_semantic_payload",
    "verify_launcher_integrity",
    "verify_runtime_integrity",
    "verify_ticket_envelope",
    "verify_trust_anchor",
]
