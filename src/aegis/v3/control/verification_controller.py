from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.v3.sensors.sensors import SensorReading
from aegis.v3.sensors.verification import (
    SensorVerifier,
    VerificationResult,
)
from aegis.v3.sensors.cross_modal import (
    CrossModalVerifier,
    CrossModalResult,
    RangeReading,
)


@dataclass(frozen=True)
class UnifiedVerification:
    estimate: np.ndarray
    sigma: float
    confidence: float

    status: str

    vector_status: str
    cross_modal_status: str

    sensor_disagreement: float
    cross_modal_discrepancy: float

    valid_sensors: int
    total_sensors: int

    anomaly_detected: bool
    dropout_detected: bool

    safe_to_act: bool


class VerificationController:
    """
    Unified verification layer for Nexvia Aegis 3.0.

    Combines:
        1. multi-sensor vector verification
        2. independent range verification

    The controller never receives ground truth.
    """

    def __init__(
        self,
        sensor_verifier: SensorVerifier | None = None,
        cross_modal_verifier: CrossModalVerifier | None = None,
    ):
        self.sensor_verifier = (
            sensor_verifier
            or SensorVerifier()
        )

        self.cross_modal_verifier = (
            cross_modal_verifier
            or CrossModalVerifier()
        )

    def verify(
        self,
        vector_readings: list[SensorReading],
        range_reading: RangeReading,
    ) -> UnifiedVerification:

        vector_result: VerificationResult = (
            self.sensor_verifier.verify(
                vector_readings
            )
        )

        # No vector information means we cannot
        # establish a target estimate.
        if vector_result.status == "NO_SIGNAL":
            return UnifiedVerification(
                estimate=np.zeros(
                    2,
                    dtype=np.float64,
                ),
                sigma=10.0,
                confidence=0.0,
                status="NO_SIGNAL",
                vector_status=vector_result.status,
                cross_modal_status="NOT_EVALUATED",
                sensor_disagreement=(
                    vector_result.disagreement
                ),
                cross_modal_discrepancy=0.0,
                valid_sensors=(
                    vector_result.valid_sensors
                ),
                total_sensors=(
                    vector_result.total_sensors
                ),
                anomaly_detected=(
                    vector_result.anomaly_detected
                ),
                dropout_detected=(
                    vector_result.dropout_detected
                ),
                safe_to_act=False,
            )

        cross_modal: CrossModalResult = (
            self.cross_modal_verifier.verify(
                vector_estimate=vector_result.estimate,
                vector_sigma=vector_result.sigma,
                range_reading=range_reading,
            )
        )

        # --------------------------------------------------
        # Fault hierarchy.
        # --------------------------------------------------

        if (
            vector_result.status == "MISMATCH"
            and cross_modal.status == "MISMATCH"
        ):
            status = "MULTI_MODAL_MISMATCH"

        elif cross_modal.status == "MISMATCH":
            status = "CROSS_MODAL_MISMATCH"

        elif vector_result.status == "MISMATCH":
            status = "SENSOR_MISMATCH"

        elif vector_result.status == "DEGRADED":
            if cross_modal.status == "CONSISTENT":
                status = "DEGRADED_VERIFIED"
            else:
                status = "DEGRADED"

        elif cross_modal.status == "RANGE_UNAVAILABLE":
            status = "RANGE_UNAVAILABLE"

        else:
            status = "VERIFIED"

        # --------------------------------------------------
        # Combine confidence conservatively.
        #
        # We use the weaker evidence rather than averaging
        # confidence values, because a single failed modality
        # should be able to prevent unsafe action.
        # --------------------------------------------------

        if cross_modal.status == "CONSISTENT":
            normalized = (
                cross_modal.discrepancy
                / max(
                    self.cross_modal_verifier.distance_threshold,
                    1e-8,
                )
            )

            consistency_factor = float(
                np.exp(-0.5 * normalized**2)
            )

            confidence = min(
                1.0,
                vector_result.confidence
                * consistency_factor,
            )

        elif cross_modal.status == "MISMATCH":
            confidence = min(
                vector_result.confidence,
                cross_modal.confidence,
            )

        else:
            confidence = min(
                vector_result.confidence,
                0.50,
            )

        sigma = max(
            vector_result.sigma,
            range_reading.sigma
            if range_reading.valid
            else vector_result.sigma * 2.0,
        )

        # --------------------------------------------------
        # Action gate.
        #
        # Only fully verified evidence can directly ACT.
        # --------------------------------------------------

        safe_to_act = (
            status == "VERIFIED"
            and confidence >= 0.75
            and not vector_result.anomaly_detected
            and not vector_result.dropout_detected
        )

        # A degraded system can continue sensing but should
        # not directly execute a normal action.
        if status == "DEGRADED_VERIFIED":
            safe_to_act = False

        return UnifiedVerification(
            estimate=vector_result.estimate.copy(),
            sigma=float(sigma),
            confidence=float(confidence),

            status=status,

            vector_status=(
                vector_result.status
            ),
            cross_modal_status=(
                cross_modal.status
            ),

            sensor_disagreement=(
                vector_result.disagreement
            ),
            cross_modal_discrepancy=(
                cross_modal.discrepancy
            ),

            valid_sensors=(
                vector_result.valid_sensors
            ),
            total_sensors=(
                vector_result.total_sensors
            ),

            anomaly_detected=(
                vector_result.anomaly_detected
            ),

            dropout_detected=(
                vector_result.dropout_detected
            ),

            safe_to_act=safe_to_act,
        )
