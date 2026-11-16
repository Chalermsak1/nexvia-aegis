"""
Tests for NEXVIA AEGIS Multi-Agent Research Team.
Verifies role execution, cryptographic sign-offs, consensus building, and Gate B quarantine.
"""

from pathlib import Path
import pytest

from scripts.research.development_ledger import DevelopmentLedger
from src.aegis.agents import (
    AgentRole,
    AgentSignOff,
    ForensicEvidenceAgent,
    PhysicalControlAgent,
    ResearchTeamCoordinator,
    StatisticalAuditorAgent,
    TeamConsensus,
    VerdictStatus,
)
from src.aegis.evidence.physics_step_ledger import DecoupledHorizonSummary, IncrementalPhysicsLedger


def test_control_agent_evaluates_dwell_and_detects_drift():
    """Verifies that PhysicalControlAgent distinguishes physical rest from drift."""
    agent = PhysicalControlAgent()

    # Episode 1: Sustained rest
    e1 = DecoupledHorizonSummary(
        assignment_id="a1",
        decision="STOP",
        terminal_reason="GOAL_CONFIRMED",
        has_post_stop_dwell=True,
        dwell_steps_observed=50,
        dwell_final_speed=0.01,
        dwell_final_dist_to_goal=0.15,
        dwell_is_physically_sustained_rest=True,
        dwell_collision=False,
    )

    # Episode 2: Drifted out
    e2 = DecoupledHorizonSummary(
        assignment_id="a2",
        decision="STOP",
        terminal_reason="GOAL_CONFIRMED",
        has_post_stop_dwell=True,
        dwell_steps_observed=50,
        dwell_final_speed=0.18,  # > 0.05
        dwell_final_dist_to_goal=0.45,  # > 0.25
        dwell_is_physically_sustained_rest=False,
        dwell_collision=False,
    )

    signoff = agent.evaluate_study_evidence([e1, e2])
    assert signoff.role == AgentRole.PHYSICAL_CONTROL_AGENT
    assert signoff.verdict == VerdictStatus.APPROVED_WITH_CAVEATS
    assert signoff.metrics["dwell_sustained_rest_count"] == 1
    assert signoff.metrics["dwell_drift_count"] == 1
    assert signoff.metrics["dwell_rest_rate"] == 0.5
    assert len(signoff.signature_sha256) == 64


def test_statistical_agent_computes_clopper_pearson_bounds():
    """Verifies StatisticalAuditorAgent calculates exact 95% CIs and identifies small samples."""
    agent = StatisticalAuditorAgent()

    episodes = [
        {"seed": 1, "true_success": 1, "false_arrival": 0, "abstained": 0},
        {"seed": 2, "true_success": 1, "false_arrival": 0, "abstained": 0},
        {"seed": 3, "true_success": 0, "false_arrival": 0, "abstained": 1},
        {"seed": 4, "true_success": 0, "false_arrival": 1, "abstained": 0},
    ]

    signoff = agent.evaluate_study_evidence(episodes)
    assert signoff.role == AgentRole.STATISTICAL_AUDITOR_AGENT
    assert signoff.metrics["total_samples"] == 4
    assert signoff.metrics["true_success_count"] == 2
    assert signoff.metrics["false_arrival_count"] == 1
    assert signoff.metrics["abstain_count"] == 1
    assert "true_success_95_ci" in signoff.metrics
    assert len(signoff.signature_sha256) == 64


def test_evidence_agent_validates_ledger_hash_chain(tmp_path: Path):
    """Verifies ForensicEvidenceAgent verifies unbroken hash chains and flags missing files."""
    agent = ForensicEvidenceAgent()

    # 1. Non-existent file
    so_missing, _ = agent.audit_ledger_file(tmp_path / "nonexistent.jsonl")
    assert so_missing.verdict == VerdictStatus.REJECTED
    assert len(so_missing.blockers) > 0

    # 2. Valid durable ledger
    ledger_path = tmp_path / "valid_audit.jsonl"
    assignments = [{"id": "assign_01", "seed": 100}]
    with IncrementalPhysicsLedger.create(ledger_path, study="audit_test", assignments=assignments) as pl:
        pl.start_assignment("assign_01")
        pl.record_step(
            assignment_id="assign_01",
            stage="MAIN_TRANSIT",
            decision_step=1,
            true_pos=[0.0, 0.0, 1.0],
            true_vel=[0.0, 0.0, 0.0],
            dist_to_goal=1.0,
            decision="NAVIGATE",
            applied_force=[0.0, 0.0, 9.81],
        )
        pl.complete_assignment("assign_01", status="COMPLETED", final_decision="STOP", terminal_reason="GOAL_CONFIRMED")
        pl.finalize()

    so_valid, inspection = agent.audit_ledger_file(ledger_path)
    assert so_valid.verdict == VerdictStatus.APPROVED
    assert so_valid.metrics["chain_state"] == "FINALIZED"
    assert so_valid.metrics["completed_count"] == 1
    assert inspection["integrity"] == "VALID_SELF_REPORTED_CHAIN"


def test_coordinator_enforces_gate_b_quarantine_and_builds_consensus(tmp_path: Path):
    """Verifies ResearchTeamCoordinator enforces GATE_B_NOT_AUTHORIZED and creates dossier."""
    coordinator = ResearchTeamCoordinator()

    # Create dummy verified ledger
    ledger_path = tmp_path / "team_study.jsonl"
    assignments = [{"id": "run_seed_2256000", "seed": 2256000}]
    with IncrementalPhysicsLedger.create(ledger_path, study="team_pilot", assignments=assignments) as pl:
        pl.start_assignment("run_seed_2256000")
        pl.record_step(
            assignment_id="run_seed_2256000",
            stage="MAIN_TRANSIT",
            decision_step=1,
            true_pos=[0.1, 0.0, 1.0],
            true_vel=[0.02, 0.0, 0.0],
            dist_to_goal=0.1,
            decision="STOP",
            applied_force=[0.0, 0.0, 9.81],
        )
        pl.complete_assignment("run_seed_2256000", status="COMPLETED", final_decision="STOP", terminal_reason="GOAL_CONFIRMED")
        pl.finalize()

    dossier = coordinator.audit_study(
        study_id="STUDY-PILOT-2026-10-31",
        ledger_path=ledger_path,
    )

    # Core governance check: GATE_B_NOT_AUTHORIZED must be invariant
    assert dossier.gate_b_status == "GATE_B_NOT_AUTHORIZED"
    assert dossier.consensus == TeamConsensus.CONSENSUS_REACHED
    assert len(dossier.agent_signoffs) == 4  # Lead + 3 specialists
    assert AgentRole.LEAD_COORDINATOR.value in dossier.agent_signoffs
    assert AgentRole.PHYSICAL_CONTROL_AGENT.value in dossier.agent_signoffs
    assert AgentRole.STATISTICAL_AUDITOR_AGENT.value in dossier.agent_signoffs
    assert AgentRole.FORENSIC_EVIDENCE_AGENT.value in dossier.agent_signoffs

    # Check Markdown report generation
    md_report = coordinator.generate_markdown_report(dossier)
    assert "# รายงานการตรวจสอบความปลอดภัยทางฟิสิกส์และหลักฐานโดยทีมเอเจนต์ AEGIS" in md_report
    assert "GATE_B_NOT_AUTHORIZED" in md_report
    assert "SHA-256 Signature" in md_report
