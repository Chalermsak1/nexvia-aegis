from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RangeReading:
    distance: float
    sigma: float
    valid: bool = True
    anomaly: bool = False
    dropped: bool = False


@dataclass(frozen=True)
class CrossModalResult:
    estimated_distance: float
    measured_distance: float
    discrepancy: float
    normalized_discrepancy: float

    confidence: float
    consistent: bool

    status: str


class RangeSensor:
    """
    Independent scalar range measurement.

    This is deliberately a different measurement modality
    from the 2D vector sensors.
    """

    def __init__(
        self,
        noise_sigma: float = 0.05,
        dropout_probability: float = 0.0,
    ):
        self.noise_sigma = float(noise_sigma)
        self.dropout_probability = float(
            dropout_probability
        )

    def measure(
        self,
        true_distance: float,
        rng: np.random.Generator,
    ) -> RangeReading:

        if (
            self.dropout_probability > 0.0
            and rng.random()
            < self.dropout_probability
        ):
            return RangeReading(
                distance=0.0,
                sigma=self.noise_sigma,
                valid=False,
                anomaly=True,
                dropped=True,
            )

        measured = (
            true_distance
            + rng.normal(
                0.0,
                self.noise_sigma,
            )
        )

        measured = max(
            0.0,
            float(measured),
        )

        return RangeReading(
            distance=measured,
            sigma=self.noise_sigma,
            valid=True,
        )


class CrossModalVerifier:
    """
    Compares a fused vector estimate against an
    independent range measurement.

    No ground truth is used here.
    """

    def __init__(
        self,
        distance_threshold: float = 0.25,
    ):
        self.distance_threshold = float(
            distance_threshold
        )

    def verify(
        self,
        vector_estimate: np.ndarray,
        vector_sigma: float,
        range_reading: RangeReading,
    ) -> CrossModalResult:

        estimated_distance = float(
            np.linalg.norm(
                vector_estimate
            )
        )

        if not range_reading.valid:
            return CrossModalResult(
                estimated_distance=estimated_distance,
                measured_distance=0.0,
                discrepancy=0.0,
                normalized_discrepancy=0.0,
                confidence=0.0,
                consistent=False,
                status="RANGE_UNAVAILABLE",
            )

        discrepancy = abs(
            estimated_distance
            - range_reading.distance
        )

        combined_sigma = max(
            np.sqrt(
                vector_sigma**2
                + range_reading.sigma**2
            ),
            1e-8,
        )

        normalized_discrepancy = (
            discrepancy
            / combined_sigma
        )

        consistent = (
            discrepancy
            <= self.distance_threshold
        )

        confidence = float(
            np.exp(
                -0.5
                * normalized_discrepancy
            )
        )

        if not consistent:
            confidence *= 0.20
            status = "MISMATCH"
        else:
            status = "CONSISTENT"

        return CrossModalResult(
            estimated_distance=estimated_distance,
            measured_distance=range_reading.distance,
            discrepancy=discrepancy,
            normalized_discrepancy=normalized_discrepancy,
            confidence=confidence,
            consistent=consistent,
            status=status,
        )

