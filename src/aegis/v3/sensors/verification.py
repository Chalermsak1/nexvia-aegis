from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.v3.sensors.sensors import SensorReading


@dataclass(frozen=True)
class VerificationResult:
    estimate: np.ndarray
    sigma: float

    confidence: float

    status: str

    disagreement: float
    normalized_disagreement: float

    valid_sensors: int
    total_sensors: int

    anomaly_detected: bool
    dropout_detected: bool

    selected_sensor: str | None


class SensorVerifier:
    """
    Research-oriented sensor verification and arbitration.

    The verifier operates only on sensor measurements.
    It never receives ground truth.

    Status:
        FUSED      -> sensors agree sufficiently
        MISMATCH   -> valid sensors disagree
        DEGRADED   -> only one valid sensor remains
        NO_SIGNAL  -> no valid sensor remains
    """

    def __init__(
        self,
        disagreement_threshold: float = 0.35,
        high_uncertainty_sigma: float = 0.20,
    ):
        self.disagreement_threshold = float(
            disagreement_threshold
        )

        self.high_uncertainty_sigma = float(
            high_uncertainty_sigma
        )

    def verify(
        self,
        readings: list[SensorReading],
    ) -> VerificationResult:

        if not readings:
            return VerificationResult(
                estimate=np.zeros(2, dtype=np.float64),
                sigma=10.0,
                confidence=0.0,
                status="NO_SIGNAL",
                disagreement=0.0,
                normalized_disagreement=0.0,
                valid_sensors=0,
                total_sensors=0,
                anomaly_detected=False,
                dropout_detected=False,
                selected_sensor=None,
            )

        valid = [
            reading
            for reading in readings
            if reading.valid
        ]

        total_sensors = len(readings)
        valid_sensors = len(valid)

        anomaly_detected = any(
            reading.anomaly
            for reading in readings
        )

        dropout_detected = any(
            reading.dropped
            for reading in readings
        )

        # --------------------------------------------------
        # No valid measurements.
        # --------------------------------------------------

        if not valid:
            return VerificationResult(
                estimate=np.zeros(2, dtype=np.float64),
                sigma=10.0,
                confidence=0.0,
                status="NO_SIGNAL",
                disagreement=0.0,
                normalized_disagreement=0.0,
                valid_sensors=0,
                total_sensors=total_sensors,
                anomaly_detected=anomaly_detected,
                dropout_detected=dropout_detected,
                selected_sensor=None,
            )

        # --------------------------------------------------
        # Exactly one valid sensor.
        # --------------------------------------------------

        if len(valid) == 1:
            reading = valid[0]

            # Penalize uncertainty because independent
            # verification is unavailable.
            degraded_sigma = max(
                reading.sigma * 2.5,
                self.high_uncertainty_sigma,
            )

            confidence = float(
                np.exp(
                    -2.0 * degraded_sigma
                )
            )

            return VerificationResult(
                estimate=reading.estimate.copy(),
                sigma=degraded_sigma,
                confidence=confidence,
                status="DEGRADED",
                disagreement=0.0,
                normalized_disagreement=0.0,
                valid_sensors=1,
                total_sensors=total_sensors,
                anomaly_detected=anomaly_detected,
                dropout_detected=dropout_detected,
                selected_sensor="single_valid_sensor",
            )

        # --------------------------------------------------
        # Multiple valid sensors.
        #
        # Current v3 benchmark uses two target sensors.
        # The implementation supports more than two.
        # --------------------------------------------------

        estimates = np.asarray(
            [
                reading.estimate
                for reading in valid
            ],
            dtype=np.float64,
        )

        sigmas = np.asarray(
            [
                max(
                    float(reading.sigma),
                    1e-8,
                )
                for reading in valid
            ],
            dtype=np.float64,
        )

        # Pairwise disagreement.
        disagreements = []

        for i in range(len(valid)):
            for j in range(i + 1, len(valid)):
                delta = (
                    estimates[i]
                    - estimates[j]
                )

                disagreements.append(
                    float(
                        np.linalg.norm(delta)
                    )
                )

        disagreement = (
            max(disagreements)
            if disagreements
            else 0.0
        )

        # Characteristic uncertainty for comparison.
        comparison_sigma = float(
            np.sqrt(
                np.mean(
                    sigmas**2
                )
            )
        )

        normalized_disagreement = (
            disagreement
            / max(
                comparison_sigma,
                1e-8,
            )
        )

        mismatch = (
            disagreement
            > self.disagreement_threshold
        )

        # --------------------------------------------------
        # Mismatch.
        #
        # Do NOT fuse conflicting measurements.
        # Select the lowest-uncertainty sensor only
        # as an evaluation estimate, while marking the
        # result unsafe for direct action.
        # --------------------------------------------------

        if mismatch:
            best_index = int(
                np.argmin(sigmas)
            )

            selected = valid[best_index]

            confidence = float(
                np.exp(
                    -2.0 * selected.sigma
                    -0.75 * disagreement
                )
            )

            confidence *= 0.25

            return VerificationResult(
                estimate=selected.estimate.copy(),
                sigma=float(
                    selected.sigma * 2.0
                ),
                confidence=confidence,
                status="MISMATCH",
                disagreement=disagreement,
                normalized_disagreement=(
                    normalized_disagreement
                ),
                valid_sensors=valid_sensors,
                total_sensors=total_sensors,
                anomaly_detected=anomaly_detected,
                dropout_detected=dropout_detected,
                selected_sensor=(
                    f"sensor_{best_index}"
                ),
            )

        # --------------------------------------------------
        # Agreement.
        #
        # Inverse-variance weighted fusion.
        # --------------------------------------------------

        weights = 1.0 / np.maximum(
            sigmas**2,
            1e-8,
        )

        fused = (
            np.sum(
                estimates
                * weights[:, None],
                axis=0,
            )
            / np.sum(weights)
        )

        fused_sigma = float(
            np.sqrt(
                1.0
                / np.sum(weights)
            )
        )

        confidence = float(
            np.exp(
                -2.0 * fused_sigma
                -0.50 * disagreement
            )
        )

        # Anomalous measurements reduce trust even
        # when their values happen to agree.
        if anomaly_detected:
            confidence *= 0.50

        status = "FUSED"

        return VerificationResult(
            estimate=fused,
            sigma=fused_sigma,
            confidence=confidence,
            status=status,
            disagreement=disagreement,
            normalized_disagreement=(
                normalized_disagreement
            ),
            valid_sensors=valid_sensors,
            total_sensors=total_sensors,
            anomaly_detected=anomaly_detected,
            dropout_detected=dropout_detected,
            selected_sensor=None,
        )
