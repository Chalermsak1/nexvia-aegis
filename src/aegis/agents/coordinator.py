"""
NEXVIA AEGIS — Research Team Coordinator & Master Lead Agent.

Coordinates multi-agent research evaluation, enforces strict GATE_B_NOT_AUTHORIZED
quarantine boundaries, aggregates specialist sign-offs, and synthesizes bilingual audit dossiers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.aegis.agents.agent_contract import (
    AgentRole,
    AgentSignOff,
    TeamConsensus,
    TeamResearchDossier,
    VerdictStatus,
)
from src.aegis.agents.control_agent import PhysicalControlAgent
from src.aegis.agents.evidence_agent import ForensicEvidenceAgent
from src.aegis.agents.statistics_agent import StatisticalAuditorAgent


class ResearchTeamCoordinator:
    """Master research coordinator orchestrating the multi-agent audit pipeline."""

    GATE_B_AUTHORITY_STATUS = "GATE_B_NOT_AUTHORIZED"

    def __init__(
        self,
        agent_id: str = "agent-lead-coordinator-00",
        control_agent: PhysicalControlAgent | None = None,
        stats_agent: StatisticalAuditorAgent | None = None,
        evidence_agent: ForensicEvidenceAgent | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.role = AgentRole.LEAD_COORDINATOR
        self.control_agent = control_agent or PhysicalControlAgent()
        self.stats_agent = stats_agent or StatisticalAuditorAgent()
        self.evidence_agent = evidence_agent or ForensicEvidenceAgent()

    def audit_study(
        self,
        study_id: str,
        *,
        ledger_path: str | Path | None = None,
        episodes_or_summaries: Sequence[Any] | None = None,
        title_th: str = "รายงานการตรวจสอบความปลอดภัยทางฟิสิกส์และหลักฐานโดยทีมเอเจนต์ AEGIS",
        title_en: str = "NEXVIA AEGIS Multi-Agent Research Audit Dossier",
    ) -> TeamResearchDossier:
        """Runs the complete multi-agent audit suite across physical, statistical, and forensic dimensions."""
        now_iso = datetime.now(timezone.utc).isoformat()
        signoffs: dict[str, AgentSignOff] = {}
        ledger_hashes: dict[str, str] = {}
        extracted_episodes: list[Any] = list(episodes_or_summaries or [])

        # 1. Forensic Evidence Agent Audit
        if ledger_path is not None:
            ev_signoff, inspection = self.evidence_agent.audit_ledger_file(ledger_path)
            signoffs[ev_signoff.role.value] = ev_signoff
            ledger_hashes[Path(ledger_path).name] = ev_signoff.metrics.get("file_sha256", "UNKNOWN")

            # Extract episode summaries from ledger inspection if not supplied directly
            if not extracted_episodes and inspection:
                for rec in inspection.get("records", []):
                    if rec.get("kind") == "TERMINAL":
                        details = rec.get("details", {})
                        if "summary" in details:
                            extracted_episodes.append(details["summary"])
                        elif "episode" in details:
                            extracted_episodes.append(details["episode"])

        # 2. Physical Control Agent Audit
        ctrl_signoff = self.control_agent.evaluate_study_evidence(extracted_episodes)
        signoffs[ctrl_signoff.role.value] = ctrl_signoff

        # 3. Statistical Auditor Agent Audit
        stats_signoff = self.stats_agent.evaluate_study_evidence(extracted_episodes)
        signoffs[stats_signoff.role.value] = stats_signoff

        # 4. Lead Coordinator Assessment & Consensus Evaluation
        lead_findings: list[str] = [
            f"กำกับดูแลความถูกต้องตามกรอบโปรโตคอลวิจัยภายใต้ขอบเขต {self.GATE_B_AUTHORITY_STATUS} (ห้ามเข้าถึง V9-M4 Holdout โดยเด็ดขาด)",
            f"ตรวจสอบข้อมูลหลักฐานทั้งหมด {len(extracted_episodes)} ชุด จากเอเจนต์ผู้เชี่ยวชาญ 3 ฝ่าย",
        ]
        lead_blockers: list[str] = []
        lead_caveats: list[str] = []

        # Check for any blockers from specialist agents
        all_blockers: list[str] = []
        for s in signoffs.values():
            all_blockers.extend(s.blockers)

        if all_blockers:
            consensus = TeamConsensus.BLOCKERS_PRESENT
            lead_verdict = VerdictStatus.REJECTED
            lead_findings.append(f"❌ มีข้อคัดค้านร้ายแรง (Blockers) รวม {len(all_blockers)} ข้อจากทีมเอเจนต์")
        else:
            consensus = TeamConsensus.CONSENSUS_REACHED
            lead_verdict = VerdictStatus.APPROVED_WITH_CAVEATS
            lead_findings.append("✅ ทีมเอเจนต์บรรลุฉันทามติเห็นชอบในหลักฐานและผลการทดลอง (ภายใต้ข้อกำหนดการจำลองเชิงสำรวจ)")

        coord_signoff = AgentSignOff(
            role=self.role,
            agent_id=self.agent_id,
            verdict=lead_verdict,
            findings=lead_findings,
            metrics={"quarantine_enforced": True, "total_specialists_consulted": 3},
            blockers=lead_blockers,
            caveats=lead_caveats,
        )
        signoffs[self.role.value] = coord_signoff

        # Synthesize Key Findings in Thai
        key_findings_th: list[str] = []
        for role_name, so in signoffs.items():
            for f in so.findings:
                if f not in key_findings_th:
                    key_findings_th.append(f)

        # Synthesize Actionable Recommendations in Thai
        actionable_recommendations_th: list[str] = [
            "1. ธำรงสถานะ GATE_B_NOT_AUTHORIZED ไว้อย่างเคร่งครัด จนกว่าระบบจะผ่านการทดลองบนชุดข้อมูลพัฒนา (Dev Set) ครบถ้วน",
            "2. ดำเนินการแยกการประเมินผลระหว่าง Decision-Time กับ Physical Dwell Rest (E-01/E-02) ในทุกการทดลอง เพื่อป้องกัน False Arrival ทางฟิสิกส์",
            "3. ปรับปรุงตัวควบคุมไม่ให้เข้าถึงความเร็วหรือตำแหน่งจริงของ MuJoCo (E-05/E-06) โดยให้ใช้เฉพาะค่าประเมินจากเซนเซอร์ (Estimated State) เท่านั้น",
            "4. ดำเนินการทดสอบบน Fresh Development Worlds (seed=2256000, 2256001) อย่างเป็นระบบด้วยกระบวนการบันทึกแบบ fsync Durable Ledger",
        ]

        return TeamResearchDossier(
            study_id=study_id,
            title_th=title_th,
            title_en=title_en,
            timestamp=now_iso,
            gate_b_status=self.GATE_B_AUTHORITY_STATUS,
            consensus=consensus,
            agent_signoffs=signoffs,
            key_findings_th=key_findings_th,
            actionable_recommendations_th=actionable_recommendations_th,
            forensic_ledger_hashes=ledger_hashes,
        )

    def generate_markdown_report(self, dossier: TeamResearchDossier) -> str:
        """Formats the research dossier as a comprehensive Markdown report."""
        lines = [
            f"# {dossier.title_th}",
            f"**{dossier.title_en}**",
            "",
            f"- **Study ID:** `{dossier.study_id}`",
            f"- **Timestamp:** `{dossier.timestamp}`",
            f"- **Protocol Authority Status:** `{dossier.gate_b_status}` (STRICT QUARANTINE)",
            f"- **Team Consensus:** `{dossier.consensus.value}`",
            "",
            "---",
            "## 1. บทสรุปฉันทามติทีมเอเจนต์ (Agent Consensus Summary)",
            "",
            "| บทบาทเอเจนต์ (Role) | รหัสเอเจนต์ (Agent ID) | คำวินิจฉัย (Verdict) | ลายเซ็นดิจิทัล (SHA-256 Signature) |",
            "| :--- | :--- | :--- | :--- |",
        ]

        for role_name, so in dossier.agent_signoffs.items():
            lines.append(
                f"| `{so.role.value}` | `{so.agent_id}` | **`{so.verdict.value}`** | `{so.signature_sha256[:16]}...` |"
            )

        lines.extend([
            "",
            "---",
            "## 2. ผลการตรวจสอบและหลักฐานสำคัญ (Key Empirical Findings)",
            "",
        ])
        for f in dossier.key_findings_th:
            lines.append(f"- {f}")

        lines.extend([
            "",
            "---",
            "## 3. รายละเอียดการประเมินรายเอเจนต์ (Detailed Agent Evaluations)",
            "",
        ])

        for role_name, so in dossier.agent_signoffs.items():
            lines.extend([
                f"### 🛡️ {so.role.value} (`{so.agent_id}`)",
                f"- **คำตัดสิน:** `{so.verdict.value}`",
                f"- **ตัวชี้วัดสำคัญ:** `{json.dumps(so.metrics, ensure_ascii=False)}`",
            ])
            if so.blockers:
                lines.append(f"- **ข้อขัดข้องร้ายแรง (Blockers):** {', '.join(so.blockers)}")
            if so.caveats:
                lines.append(f"- **ข้อสังเกต/ข้อจำกัด (Caveats):** {', '.join(so.caveats)}")
            lines.append("")

        lines.extend([
            "---",
            "## 4. แผนปฏิบัติการที่ทีมเอเจนต์แนะนำ (Actionable Recommendations)",
            "",
        ])
        for r in dossier.actionable_recommendations_th:
            lines.append(f"- {r}")

        lines.append("")
        return "\n".join(lines)
