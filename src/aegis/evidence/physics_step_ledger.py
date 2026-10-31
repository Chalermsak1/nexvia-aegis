"""
NEXVIA AEGIS — Incremental Post-Physics Ledger and Decoupled Horizon Accounting (E-01, E-02, E-03).

Provides verifiable per-step physical telemetry and decoupled evaluation across:
1. MAIN_TRANSIT: Navigation and probing toward goal up to decision moment.
2. POST_STOP_DWELL: Physical stability, speed decay, and goal containment after STOP.
3. POST_ABSTAIN_COAST: Physical motion, braking deceleration, and obstacle avoidance after ABSTAIN.

Guarantees:
- Schema-versioned append-only records with SHA-256 hash chains.
- Per-step fsync durability preventing silent data loss upon process interruption.
- Decoupled metric summaries preventing false conflation of decision-time distance with physical rest.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
import numpy as np

from scripts.research.development_ledger import DevelopmentLedger, LedgerError


# Authoritative Physical Horizon Stages
STAGE_MAIN_TRANSIT = "MAIN_TRANSIT"
STAGE_POST_STOP_DWELL = "POST_STOP_DWELL"
STAGE_POST_ABSTAIN_COAST = "POST_ABSTAIN_COAST"


@dataclass(frozen=True)
class PhysicsStepTelemetry:
    """Telemetry recorded at each physics integration step."""
    stage: str
    decision_step: int
    physics_step: int
    stage_step: int
    true_pos: list[float]
    true_vel: list[float]
    true_speed: float
    dist_to_goal: float
    decision: str
    applied_force: list[float]
    cbf_residual: float
    collision: bool
    estimated_speed: float | None = None
    sensor_fault_active: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DecoupledHorizonSummary:
    """Decoupled summary metrics separating decision-time state from physical outcome."""
    assignment_id: str
    decision: str
    terminal_reason: str
    seed: int | None = None
    
    # 1. Decision-Time Metrics (at the instant of controller decision)
    decision_step: int = 0
    decision_dist_to_goal: float = 0.0
    decision_true_speed: float = 0.0
    decision_is_true_success: bool = False
    decision_cbf_infeasible_count: int = 0
    decision_collision: bool = False
    
    # 2. Post-STOP Dwell Metrics (physical behavior over post-arrival window)
    has_post_stop_dwell: bool = False
    dwell_steps_observed: int = 0
    dwell_max_speed: float = 0.0
    dwell_final_speed: float = 0.0
    dwell_max_dist_to_goal: float = 0.0
    dwell_final_dist_to_goal: float = 0.0
    dwell_is_physically_sustained_rest: bool = False
    dwell_collision: bool = False
    
    # 3. Post-ABSTAIN Coast Metrics (physical behavior over post-abstention window)
    has_post_abstain_coast: bool = False
    coast_steps_observed: int = 0
    coast_max_speed: float = 0.0
    coast_final_speed: float = 0.0
    coast_displacement: float = 0.0
    coast_collision: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IncrementalPhysicsLedger:
    """
    Append-only physical evidence recorder wrapping DevelopmentLedger schema/2.
    Records per-step physical telemetry across transit, dwell, and coast stages.
    """

    def __init__(self, ledger: DevelopmentLedger, success_radius: float = 0.25, rest_speed_threshold: float = 0.05) -> None:
        self.ledger = ledger
        self.success_radius = float(success_radius)
        self.rest_speed_threshold = float(rest_speed_threshold)
        
        # In-memory tracking per assignment for decoupled summary computation
        self._step_records: dict[str, list[PhysicsStepTelemetry]] = {}
        self._physics_step_counter: dict[str, int] = {}
        self._stage_step_counter: dict[str, dict[str, int]] = {}

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        study: str,
        assignments: list[dict[str, Any]],
        success_radius: float = 0.25,
        rest_speed_threshold: float = 0.05,
    ) -> "IncrementalPhysicsLedger":
        """Creates a new durable ledger with EVENT_SCHEMA (schema/2) enabled."""
        raw_ledger = DevelopmentLedger.create(
            path=path,
            study=study,
            assignments=assignments,
            record_events=True,
        )
        return cls(raw_ledger, success_radius=success_radius, rest_speed_threshold=rest_speed_threshold)

    def start_assignment(self, assignment_id: str) -> None:
        """Starts an assignment in the underlying ledger."""
        self.ledger.start(assignment_id)
        self._step_records[assignment_id] = []
        self._physics_step_counter[assignment_id] = 0
        self._stage_step_counter[assignment_id] = {
            STAGE_MAIN_TRANSIT: 0,
            STAGE_POST_STOP_DWELL: 0,
            STAGE_POST_ABSTAIN_COAST: 0,
        }

    def record_step(
        self,
        assignment_id: str,
        *,
        stage: str,
        decision_step: int,
        true_pos: np.ndarray | Sequence[float],
        true_vel: np.ndarray | Sequence[float],
        dist_to_goal: float,
        decision: str,
        applied_force: np.ndarray | Sequence[float],
        cbf_residual: float = 0.0,
        collision: bool = False,
        estimated_speed: float | None = None,
        sensor_fault_active: bool = False,
        details: dict[str, Any] | None = None,
    ) -> PhysicsStepTelemetry:
        """
        Appends an incremental physical step event to the durable ledger.
        Each event is immediately serialized, hashed, and fsynced.
        """
        if stage not in (STAGE_MAIN_TRANSIT, STAGE_POST_STOP_DWELL, STAGE_POST_ABSTAIN_COAST):
            raise LedgerError(f"Invalid physical stage: {stage}")

        physics_step = self._physics_step_counter[assignment_id]
        stage_step = self._stage_step_counter[assignment_id][stage]

        t_pos = [round(float(x), 6) for x in true_pos]
        t_vel = [round(float(v), 6) for v in true_vel]
        t_speed = round(float(np.linalg.norm(true_vel)), 6)
        a_force = [round(float(f), 6) for f in applied_force]

        step_telemetry = PhysicsStepTelemetry(
            stage=stage,
            decision_step=int(decision_step),
            physics_step=int(physics_step),
            stage_step=int(stage_step),
            true_pos=t_pos,
            true_vel=t_vel,
            true_speed=t_speed,
            dist_to_goal=round(float(dist_to_goal), 6),
            decision=str(decision),
            applied_force=a_force,
            cbf_residual=round(float(cbf_residual), 6),
            collision=bool(collision),
            estimated_speed=round(float(estimated_speed), 6) if estimated_speed is not None else None,
            sensor_fault_active=bool(sensor_fault_active),
            details=details or {},
        )

        # Fsync to disk through underlying ledger event mechanism
        self.ledger.event(assignment_id, details=step_telemetry.to_dict())

        # Update in-memory tracking
        self._step_records[assignment_id].append(step_telemetry)
        self._physics_step_counter[assignment_id] += 1
        self._stage_step_counter[assignment_id][stage] += 1

        return step_telemetry

    def compute_decoupled_summary(
        self,
        assignment_id: str,
        *,
        final_decision: str,
        terminal_reason: str,
        seed: int | None = None,
    ) -> DecoupledHorizonSummary:
        """Computes decoupled metrics separating decision-time state from post-decision physics."""
        records = self._step_records.get(assignment_id, [])
        transit_records = [r for r in records if r.stage == STAGE_MAIN_TRANSIT]
        dwell_records = [r for r in records if r.stage == STAGE_POST_STOP_DWELL]
        coast_records = [r for r in records if r.stage == STAGE_POST_ABSTAIN_COAST]

        summary = DecoupledHorizonSummary(
            assignment_id=assignment_id,
            decision=final_decision,
            terminal_reason=terminal_reason,
            seed=seed,
        )

        # 1. Decision-time evaluation
        if transit_records:
            last_transit = transit_records[-1]
            summary.decision_step = last_transit.decision_step
            summary.decision_dist_to_goal = last_transit.dist_to_goal
            summary.decision_true_speed = last_transit.true_speed
            summary.decision_is_true_success = (last_transit.dist_to_goal <= self.success_radius)
            summary.decision_cbf_infeasible_count = sum(1 for r in transit_records if r.cbf_residual < -1e-4)
            summary.decision_collision = any(r.collision for r in transit_records)
        elif records:
            first_rec = records[0]
            summary.decision_dist_to_goal = first_rec.dist_to_goal
            summary.decision_true_speed = first_rec.true_speed
            summary.decision_is_true_success = (first_rec.dist_to_goal <= self.success_radius)

        # 2. Post-STOP Dwell evaluation
        if dwell_records:
            summary.has_post_stop_dwell = True
            summary.dwell_steps_observed = len(dwell_records)
            summary.dwell_max_speed = max(r.true_speed for r in dwell_records)
            summary.dwell_final_speed = dwell_records[-1].true_speed
            summary.dwell_max_dist_to_goal = max(r.dist_to_goal for r in dwell_records)
            summary.dwell_final_dist_to_goal = dwell_records[-1].dist_to_goal
            summary.dwell_collision = any(r.collision for r in dwell_records)

            # Physically sustained rest requires remaining inside goal radius AND decaying below rest speed threshold
            all_inside_goal = all(r.dist_to_goal <= self.success_radius for r in dwell_records)
            speed_rest = (summary.dwell_final_speed <= self.rest_speed_threshold)
            summary.dwell_is_physically_sustained_rest = bool(all_inside_goal and speed_rest and not summary.dwell_collision)

        # 3. Post-ABSTAIN Coast evaluation
        if coast_records:
            summary.has_post_abstain_coast = True
            summary.coast_steps_observed = len(coast_records)
            summary.coast_max_speed = max(r.true_speed for r in coast_records)
            summary.coast_final_speed = coast_records[-1].true_speed
            summary.coast_collision = any(r.collision for r in coast_records)

            # Total stopping/coasting displacement from decision moment
            if transit_records:
                start_pos = np.array(transit_records[-1].true_pos)
            else:
                start_pos = np.array(coast_records[0].true_pos)
            end_pos = np.array(coast_records[-1].true_pos)
            summary.coast_displacement = round(float(np.linalg.norm(end_pos - start_pos)), 6)

        return summary

    def complete_assignment(
        self,
        assignment_id: str,
        *,
        status: str,
        final_decision: str,
        terminal_reason: str,
        seed: int | None = None,
        extra_details: dict[str, Any] | None = None,
    ) -> DecoupledHorizonSummary:
        """
        Completes an assignment in the durable ledger, recording the decoupled summary
        and closing the assignment state.
        """
        summary = self.compute_decoupled_summary(
            assignment_id,
            final_decision=final_decision,
            terminal_reason=terminal_reason,
            seed=seed,
        )

        details = {
            "summary": summary.to_dict(),
            "extra": extra_details or {},
        }
        self.ledger.complete(assignment_id, status=status, details=details)
        return summary

    def finalize(self) -> None:
        """Finalizes the underlying ledger."""
        self.ledger.finalize()

    def close(self) -> None:
        """Closes the underlying ledger."""
        self.ledger.close()

    def __enter__(self) -> "IncrementalPhysicsLedger":
        return self

    def __exit__(self, *args) -> None:
        self.close()
