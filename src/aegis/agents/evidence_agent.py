"""
NEXVIA AEGIS — Forensic Evidence & Cryptographic Integrity Agent.

Specialist agent responsible for verifying append-only SHA-256 hash chains, schema compliance,
tamper detection, and crash durability across development and post-physics ledgers.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Sequence

from scripts.research.development_ledger import inspect as inspect_ledger, LedgerError
from src.aegis.agents.agent_contract import AgentRole, AgentSignOff, VerdictStatus


class ForensicEvidenceAgent:
    """Audits immutable ledgers, hash chains, and evidence artifacts."""

    def __init__(self, agent_id: str = "agent-forensic-integrity-03") -> None:
        self.agent_id = agent_id
        self.role = AgentRole.FORENSIC_EVIDENCE_AGENT

    def audit_ledger_file(self, ledger_path: str | Path) -> tuple[AgentSignOff, dict[str, Any]]:
        """Performs a full forensic audit on an append-only JSONL ledger file."""
        path = Path(ledger_path)
        findings: list[str] = []
        blockers: list[str] = []
        caveats: list[str] = []

        if not path.exists():
            return (
                AgentSignOff(
                    role=self.role,
                    agent_id=self.agent_id,
                    verdict=VerdictStatus.REJECTED,
                    findings=[f"ไม่พบไฟล์ Ledger ที่ระบุ: {path}"],
                    metrics={"exists": False},
                    blockers=[f"File not found: {path}"],
                ),
                {},
            )

        file_bytes = path.read_bytes()
        file_sha256 = hashlib.sha256(file_bytes).hexdigest()
        file_size_bytes = len(file_bytes)

        try:
            inspection = inspect_ledger(path)
        except LedgerError as exc:
            findings.append(f"❌ ล้มเหลวในการตรวจสอบความถูกต้องของ Ledger: {exc}")
            blockers.append(f"Ledger integrity violation: {exc}")
            return (
                AgentSignOff(
                    role=self.role,
                    agent_id=self.agent_id,
                    verdict=VerdictStatus.REJECTED,
                    findings=findings,
                    metrics={"file_sha256": file_sha256, "file_size_bytes": file_size_bytes, "valid_chain": False},
                    blockers=blockers,
                ),
                {},
            )

        # Hash chain verified
        integrity_status = inspection.get("integrity")
        chain_state = inspection.get("state")
        schema = inspection.get("schema")
        counts = inspection.get("counts", {})
        total_records = len(inspection.get("records", []))
        last_sha256 = inspection.get("last_sha256")

        findings.append(f"ตรวจสอบความสมบูรณ์ของ Ledger: {path.name} (ขนาด {file_size_bytes:,} bytes, {total_records} รายการ)")
        findings.append(f"สถานะ Hash Chain: {integrity_status} (SHA-256 ลำดับสุดท้าย={last_sha256[:16]}...)")
        findings.append(f"โครงสร้าง Schema: {schema}, สถานะประมวลผล: {chain_state}")

        if chain_state == "INCOMPLETE":
            caveats.append("Ledger อยู่ในสถานะ INCOMPLETE (อาจเกิดจากกระบวนการหยุดลงระหว่างทาง แต่บันทึกก่อนหน้าถูก fsync สมบูรณ์)")
            findings.append("ℹ️ พบว่ากระบวนการทดลองยังไม่ได้เรียก finalize() (ทนทานต่อ Crash ตามคุณสมบัติ E-04)")
        elif chain_state == "FINALIZED_WITH_ERRORS":
            caveats.append(f"Ledger มีข้อผิดพลาดบันทึกอยู่ {counts.get('ERROR', 0)} รายการ")
        elif chain_state == "FINALIZED":
            findings.append(f"✅ บันทึกเสร็จสมบูรณ์ 100% (Completed={counts.get('COMPLETED', 0)}, Errors=0)")

        if blockers:
            verdict = VerdictStatus.REJECTED
        elif caveats:
            verdict = VerdictStatus.APPROVED_WITH_CAVEATS
        else:
            verdict = VerdictStatus.APPROVED

        metrics = {
            "file_name": path.name,
            "file_sha256": file_sha256,
            "file_size_bytes": file_size_bytes,
            "schema": schema,
            "chain_state": chain_state,
            "total_records": total_records,
            "completed_count": counts.get("COMPLETED", 0),
            "error_count": counts.get("ERROR", 0),
            "started_count": counts.get("STARTED", 0),
            "last_sha256": last_sha256,
        }

        signoff = AgentSignOff(
            role=self.role,
            agent_id=self.agent_id,
            verdict=verdict,
            findings=findings,
            metrics=metrics,
            blockers=blockers,
            caveats=caveats,
        )

        return signoff, inspection
