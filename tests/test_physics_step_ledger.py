"""
Tests for Incremental Physics Ledger (E-01, E-02, E-03, E-04).
Verifies decoupled physical horizon tracking, hash chaining, and crash durability.
"""

from pathlib import Path
import pytest
import numpy as np

from scripts.research.development_ledger import inspect as inspect_ledger
from src.aegis.evidence.physics_step_ledger import (
    IncrementalPhysicsLedger,
    STAGE_MAIN_TRANSIT,
    STAGE_POST_STOP_DWELL,
    STAGE_POST_ABSTAIN_COAST,
    DecoupledHorizonSummary,
)


def test_incremental_physics_ledger_e01_stage_tagging_and_hash_chain(tmp_path: Path):
    """E-01: Verifies stage tagging across transit, dwell, and coast with SHA-256 chain."""
    ledger_path = tmp_path / "test_physics.jsonl"
    assignment_id = "test_run_001"
    assignments = [{"id": assignment_id, "seed": 42}]

    with IncrementalPhysicsLedger.create(
        ledger_path,
        study="physics_ledger_unit_test",
        assignments=assignments,
        success_radius=0.25,
        rest_speed_threshold=0.05,
    ) as phys_ledger:
        phys_ledger.start_assignment(assignment_id)

        # 1. Main Transit step
        phys_ledger.record_step(
            assignment_id=assignment_id,
            stage=STAGE_MAIN_TRANSIT,
            decision_step=1,
            true_pos=[1.0, 1.0, 1.0],
            true_vel=[0.2, 0.0, 0.0],
            dist_to_goal=1.5,
            decision="CONTINUE",
            applied_force=[1.0, 0.0, 9.81],
            cbf_residual=0.1,
            collision=False,
        )

        # 2. Transition to STOP decision
        phys_ledger.record_step(
            assignment_id=assignment_id,
            stage=STAGE_MAIN_TRANSIT,
            decision_step=2,
            true_pos=[0.1, 0.0, 0.0],
            true_vel=[0.1, 0.0, 0.0],
            dist_to_goal=0.1,
            decision="STOP",
            applied_force=[0.0, 0.0, 9.81],
            cbf_residual=0.2,
            collision=False,
        )

        # 3. Post-STOP Dwell steps
        phys_ledger.record_step(
            assignment_id=assignment_id,
            stage=STAGE_POST_STOP_DWELL,
            decision_step=2,
            true_pos=[0.11, 0.0, 0.0],
            true_vel=[0.04, 0.0, 0.0],
            dist_to_goal=0.11,
            decision="STOP",
            applied_force=[0.0, 0.0, 9.81],
            cbf_residual=0.2,
            collision=False,
        )
        phys_ledger.record_step(
            assignment_id=assignment_id,
            stage=STAGE_POST_STOP_DWELL,
            decision_step=2,
            true_pos=[0.12, 0.0, 0.0],
            true_vel=[0.01, 0.0, 0.0],
            dist_to_goal=0.12,
            decision="STOP",
            applied_force=[0.0, 0.0, 9.81],
            cbf_residual=0.2,
            collision=False,
        )

        # Complete assignment
        summary = phys_ledger.complete_assignment(
            assignment_id=assignment_id,
            status="COMPLETED",
            final_decision="STOP",
            terminal_reason="GOAL_CONFIRMED",
        )
        phys_ledger.finalize()

    assert summary.assignment_id == assignment_id
    assert summary.decision == "STOP"
    assert summary.has_post_stop_dwell is True
    assert summary.dwell_steps_observed == 2
    assert summary.dwell_final_speed == pytest.approx(0.01, abs=1e-4)
    assert summary.dwell_is_physically_sustained_rest is True
    assert summary.dwell_final_dist_to_goal <= 0.25

    # Verify ledger integrity
    inspection = inspect_ledger(ledger_path)
    assert inspection["integrity"] == "VALID_SELF_REPORTED_CHAIN"
    assert inspection["state"] == "FINALIZED"
    assert inspection["counts"]["COMPLETED"] == 1

    records = inspection["records"]
    assert records[0]["kind"] == "HEADER"
    assert records[1]["kind"] == "START"
    assert records[2]["kind"] == "EVENT"
    assert records[2]["details"]["stage"] == STAGE_MAIN_TRANSIT
    assert records[4]["details"]["stage"] == STAGE_POST_STOP_DWELL
    assert records[6]["kind"] == "TERMINAL"
    assert records[6]["details"]["summary"]["dwell_is_physically_sustained_rest"] is True
    assert records[7]["kind"] == "FINAL"


def test_incremental_physics_ledger_e02_drift_after_stop_detected(tmp_path: Path):
    """E-02: Verifies that controller STOP without sustained physical rest is flagged as dwell failure."""
    ledger_path = tmp_path / "test_drift.jsonl"
    assignment_id = "drift_run_002"
    assignments = [{"id": assignment_id, "seed": 43}]

    with IncrementalPhysicsLedger.create(
        ledger_path,
        study="drift_test",
        assignments=assignments,
        success_radius=0.25,
        rest_speed_threshold=0.05,
    ) as phys_ledger:
        phys_ledger.start_assignment(assignment_id)

        # Drone claimed STOP while inside radius, but moving too fast
        phys_ledger.record_step(
            assignment_id=assignment_id,
            stage=STAGE_MAIN_TRANSIT,
            decision_step=1,
            true_pos=[0.1, 0.0, 0.0],
            true_vel=[0.4, 0.0, 0.0],  # 0.4 m/s (not stopped!)
            dist_to_goal=0.1,
            decision="STOP",
            applied_force=[0.0, 0.0, 9.81],
            cbf_residual=0.1,
            collision=False,
        )

        # During dwell, it drifts outside the goal radius (dist=0.6 > 0.25)
        phys_ledger.record_step(
            assignment_id=assignment_id,
            stage=STAGE_POST_STOP_DWELL,
            decision_step=1,
            true_pos=[0.6, 0.0, 0.0],
            true_vel=[0.3, 0.0, 0.0],
            dist_to_goal=0.6,
            decision="STOP",
            applied_force=[0.0, 0.0, 9.81],
            cbf_residual=0.1,
            collision=False,
        )

        summary = phys_ledger.complete_assignment(
            assignment_id=assignment_id,
            status="COMPLETED",
            final_decision="STOP",
            terminal_reason="GOAL_CONFIRMED",
        )
        phys_ledger.finalize()

    # Decision-time said inside 0.25m, but dwell physically drifted out!
    assert summary.decision_dist_to_goal == pytest.approx(0.1, abs=1e-4)
    assert summary.dwell_final_dist_to_goal == pytest.approx(0.6, abs=1e-4)
    assert summary.dwell_is_physically_sustained_rest is False  # Correctly rejected!


def test_incremental_physics_ledger_e03_post_abstain_coast(tmp_path: Path):
    """E-03: Verifies post-abstain coasting evaluation (braking deceleration and obstacle clearance)."""
    ledger_path = tmp_path / "test_coast.jsonl"
    assignment_id = "coast_run_003"
    assignments = [{"id": assignment_id, "seed": 44}]

    with IncrementalPhysicsLedger.create(
        ledger_path,
        study="coast_test",
        assignments=assignments,
        success_radius=0.25,
        rest_speed_threshold=0.05,
    ) as phys_ledger:
        phys_ledger.start_assignment(assignment_id)

        # Main transit decided ABSTAIN
        phys_ledger.record_step(
            assignment_id=assignment_id,
            stage=STAGE_MAIN_TRANSIT,
            decision_step=5,
            true_pos=[2.0, 2.0, 1.0],
            true_vel=[0.5, 0.0, 0.0],
            dist_to_goal=3.0,
            decision="ABSTAIN",
            applied_force=[-1.0, 0.0, 9.81],
            cbf_residual=0.05,
            collision=False,
        )

        # Coasting step 1: active braking
        phys_ledger.record_step(
            assignment_id=assignment_id,
            stage=STAGE_POST_ABSTAIN_COAST,
            decision_step=5,
            true_pos=[2.2, 2.0, 1.0],
            true_vel=[0.2, 0.0, 0.0],
            dist_to_goal=3.2,
            decision="ABSTAIN",
            applied_force=[-2.0, 0.0, 9.81],
            cbf_residual=0.08,
            collision=False,
        )

        # Coasting step 2: drone brought to rest
        phys_ledger.record_step(
            assignment_id=assignment_id,
            stage=STAGE_POST_ABSTAIN_COAST,
            decision_step=5,
            true_pos=[2.25, 2.0, 1.0],
            true_vel=[0.02, 0.0, 0.0],
            dist_to_goal=3.25,
            decision="ABSTAIN",
            applied_force=[0.0, 0.0, 9.81],
            cbf_residual=0.1,
            collision=False,
        )

        summary = phys_ledger.complete_assignment(
            assignment_id=assignment_id,
            status="COMPLETED",
            final_decision="ABSTAIN",
            terminal_reason="UNCERTAINTY_EXCEEDED",
        )
        phys_ledger.finalize()

    assert summary.has_post_abstain_coast is True
    assert summary.coast_steps_observed == 2
    assert summary.coast_final_speed == pytest.approx(0.02, abs=1e-4)
    assert summary.coast_collision is False
    assert summary.coast_displacement == pytest.approx(0.25, abs=1e-3)


def test_incremental_physics_ledger_e04_crash_durability_and_fsync(tmp_path: Path):
    """E-04: Verifies partial records remain valid and readable up to the point of simulated crash."""
    ledger_path = tmp_path / "test_crash.jsonl"
    assignment_id = "interrupted_run_004"
    assignments = [{"id": assignment_id, "seed": 45}]

    # Writer starts and writes steps, but process crashes before complete() or finalize()
    phys_ledger = IncrementalPhysicsLedger.create(
        ledger_path,
        study="crash_durability_test",
        assignments=assignments,
    )
    phys_ledger.start_assignment(assignment_id)

    # Step 1 written and fsynced
    phys_ledger.record_step(
        assignment_id=assignment_id,
        stage=STAGE_MAIN_TRANSIT,
        decision_step=1,
        true_pos=[0.0, 0.0, 1.0],
        true_vel=[0.1, 0.0, 0.0],
        dist_to_goal=2.0,
        decision="CONTINUE",
        applied_force=[0.1, 0.0, 9.81],
        cbf_residual=0.15,
        collision=False,
    )

    # Step 2 written and fsynced
    phys_ledger.record_step(
        assignment_id=assignment_id,
        stage=STAGE_MAIN_TRANSIT,
        decision_step=2,
        true_pos=[0.1, 0.0, 1.0],
        true_vel=[0.1, 0.0, 0.0],
        dist_to_goal=1.9,
        decision="CONTINUE",
        applied_force=[0.1, 0.0, 9.81],
        cbf_residual=0.15,
        collision=False,
    )

    # Process "crashes": close raw fd without completing assignment or calling finalize
    phys_ledger.close()

    # Evidence reader opens file: inspect() must successfully read all written records
    inspection = inspect_ledger(ledger_path)
    assert inspection["integrity"] == "VALID_SELF_REPORTED_CHAIN"
    assert inspection["state"] == "INCOMPLETE"  # Explicitly incomplete, not corrupted!
    assert inspection["counts"]["STARTED"] == 1
    assert inspection["event_counts"][assignment_id] == 2
    records = inspection["records"]
    assert len(records) == 4  # HEADER, START, EVENT 0, EVENT 1
    assert records[2]["details"]["decision_step"] == 1
    assert records[3]["details"]["decision_step"] == 2
