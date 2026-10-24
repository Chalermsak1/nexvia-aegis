"""
NEXVIA AEGIS V7.0 — Anchor Query Scheduler and Integrity Gate.

Governs when to query the independent 3rd sensor modality and validates
anchor measurements against physical cross-modal invariants before accepting them.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v6.hypothesis_models import DiagnosticReport, FaultHypothesis
from aegis.v7.anchor_sensor import AnchorReading


@dataclass
class AnchorScheduleConfig:
    entropy_threshold: float = 0.95
    consecutive_mismatches_threshold: int = 2
    max_queries_per_episode: int = 5
    consistency_tolerance: float = 0.35


class AnchorQueryScheduler:
    """
    Event-triggered scheduler for querying the intermittent anchor sensor.
    """

    def __init__(self, config: AnchorScheduleConfig | None = None):
        self.config = config or AnchorScheduleConfig()

    def should_query(
        self,
        diagnostic_report: DiagnosticReport | None,
        consecutive_mismatches: int,
        total_queries: int,
        unconditional: bool = False,
    ) -> bool:
        """
        Determines whether an anchor query is justified at this decision step.
        """
        if total_queries >= self.config.max_queries_per_episode:
            return False

        if unconditional:
            return True

        # Condition 1: High diagnostic entropy (unresolved hypotheses)
        if diagnostic_report is not None:
            if diagnostic_report.entropy >= self.config.entropy_threshold:
                return True

            # Condition 2: Suspected common-mode failure (H4) or unobservable ambiguity (H6)
            if diagnostic_report.leading_hypothesis in (
                FaultHypothesis.H4_CORRELATED_BIAS,
                FaultHypothesis.H6_AMBIGUOUS,
            ):
                return True

        # Condition 3: Persistent cross-modal sensor disagreement
        if consecutive_mismatches >= self.config.consecutive_mismatches_threshold:
            return True

        return False


class AnchorIntegrityGate:
    """
    Integrity verification gate ensuring corrupted anchor measurements
    are detected and rejected before affecting state estimation or recovery.
    """

    def __init__(self, consistency_tolerance: float = 0.35):
        self.consistency_tolerance = consistency_tolerance

    def validate_anchor(
        self,
        anchor_reading: AnchorReading,
        range_reading: RangeReading,
        raw_vector: np.ndarray,
    ) -> tuple[bool, str, np.ndarray | None]:
        """
        Validates anchor measurement against range sensor physics.
        Returns:
            (is_valid, reason_code, inferred_vector_bias)
        """
        if not anchor_reading.valid or not range_reading.valid:
            return False, "INVALID_READINGS", None

        anchor_dist = float(np.linalg.norm(anchor_reading.estimate))
        range_dist = float(range_reading.distance)

        # Cross-check anchor magnitude against radar range measurement
        discrepancy = abs(anchor_dist - range_dist)

        if discrepancy > self.consistency_tolerance:
            # Anchor disagrees with physical radar range -> Anchor is corrupted!
            return False, "REJECTED_ANCHOR_RANGE_INCONSISTENT", None

        # Anchor is consistent with range sensor.
        # Now compare anchor with raw vector to see if vector has bias
        vector_discrepancy = float(np.linalg.norm(raw_vector - anchor_reading.estimate))

        if vector_discrepancy > 0.25:
            # Vector sensor is biased; anchor breaks the common-mode symmetry!
            inferred_bias = raw_vector - anchor_reading.estimate
            return True, "VALIDATED_CORRELATED_BIAS_RESOLVED", inferred_bias
        else:
            return True, "VALIDATED_NOMINAL_ALIGNMENT", np.zeros(2, dtype=np.float64)
