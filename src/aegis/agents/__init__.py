"""
NEXVIA AEGIS — Multi-Agent Research Team.

Provides specialized autonomous research agents for:
1. Team Coordination & Protocol Quarantine Governance (ResearchTeamCoordinator)
2. Physical Control, Dwell Stability & CBF Barrier Auditing (PhysicalControlAgent)
3. Statistical Uncertainty & Confidence Bound Verification (StatisticalAuditorAgent)
4. Forensic Ledger Integrity & Cryptographic Sign-Off (ForensicEvidenceAgent)
"""

from src.aegis.agents.agent_contract import (
    AgentRole,
    AgentSignOff,
    TeamConsensus,
    TeamResearchDossier,
    VerdictStatus,
)
from src.aegis.agents.control_agent import PhysicalControlAgent
from src.aegis.agents.coordinator import ResearchTeamCoordinator
from src.aegis.agents.evidence_agent import ForensicEvidenceAgent
from src.aegis.agents.statistics_agent import StatisticalAuditorAgent

__all__ = [
    "AgentRole",
    "VerdictStatus",
    "TeamConsensus",
    "AgentSignOff",
    "TeamResearchDossier",
    "PhysicalControlAgent",
    "StatisticalAuditorAgent",
    "ForensicEvidenceAgent",
    "ResearchTeamCoordinator",
]
