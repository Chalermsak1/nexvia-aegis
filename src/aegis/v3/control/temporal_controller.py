from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.v3.control.windowed_temporal import (
    WindowedTemporalConsistencyMonitor,
    WindowedTemporalResult,
)
from aegis.v3.control.verification_controller import (
    UnifiedVerification,
    VerificationController,
)
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading


@dataclass(frozen=True)
class TemporalAwareVerification:
    base: UnifiedVerification
    temporal: WindowedTemporalResult

    estimate: np.ndarray
    sigma: float
    confidence: float

    status: str
    safe_to_act: bool

    temporal_consistent: bool


class TemporalAwareVerificationController:
    """
    v3.1 verification controller.

    Combines:
        - vector sensor verification
        - cross-modal range verification
        - temporal consistency

    The temporal monitor receives the action executed on the
    previous cycle, not the action currently being decided.
    """

    def __init__(
        self,
        verification_controller: (
            VerificationController | None
        ) = None,
        temporal_monitor: (
            WindowedTemporalConsistencyMonitor | None
        ) = None,
    ):
        self.verification_controller = (
            verification_controller
            or VerificationController()
        )

        self.temporal_monitor = (
            temporal_monitor
            or WindowedTemporalConsistencyMonitor()
        )

    def reset(self) -> None:
        self.temporal_monitor.reset()

    def verify(
        self,
        vector_readings: list[SensorReading],
        range_reading: RangeReading,
        previous_action: np.ndarray,
    ) -> TemporalAwareVerification:

        base = self.verification_controller.verify(
            vector_readings=vector_readings,
            range_reading=range_reading,
        )

        temporal = self.temporal_monitor.update(
            estimate=base.estimate,
            action=previous_action,
        )

        # --------------------------------------------------
        # First temporal observation.
        # --------------------------------------------------

        if temporal.status == "INIT":
            return TemporalAwareVerification(
                base=base,
                temporal=temporal,
                estimate=base.estimate.copy(),
                sigma=base.sigma,
                confidence=base.confidence,
                status=base.status,
                safe_to_act=base.safe_to_act,
                temporal_consistent=True,
            )

        # --------------------------------------------------
        # Existing sensor / cross-modal fault plus
        # temporal contradiction.
        # --------------------------------------------------

        if (
            not temporal.consistent
            and "MISMATCH" in base.status
        ):
            status = "MULTI_MODAL_MISMATCH"

            confidence = min(
                base.confidence,
                temporal.confidence,
            )

            safe_to_act = False

        # --------------------------------------------------
        # Temporal failure by itself.
        # --------------------------------------------------

        elif not temporal.consistent:
            status = "TEMPORAL_CONTRADICTION"

            confidence = min(
                base.confidence,
                temporal.confidence,
            )

            safe_to_act = False

        # --------------------------------------------------
        # Base verification is already degraded or unsafe.
        # --------------------------------------------------

        else:
            status = base.status

            confidence = min(
                base.confidence,
                temporal.confidence,
            )

            safe_to_act = (
                base.safe_to_act
                and temporal.consistent
            )

        return TemporalAwareVerification(
            base=base,
            temporal=temporal,
            estimate=base.estimate.copy(),
            sigma=max(
                base.sigma,
                temporal.jump_magnitude,
            ),
            confidence=float(
                np.clip(
                    confidence,
                    0.0,
                    1.0,
                )
            ),
            status=status,
            safe_to_act=safe_to_act,
            temporal_consistent=(
                temporal.consistent
            ),
        )
