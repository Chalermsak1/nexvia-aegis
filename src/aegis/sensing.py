from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SensorReading:
    estimate: np.ndarray
    sigma: float
    valid: bool = True
    anomaly: bool = False


class NoisyPositionSensor:
    """
    Generic noisy sensor that estimates a 2D target-relative position.

    Ground truth is used internally only to generate a measurement.
    The downstream decision layer receives only the measurement.
    """

    def __init__(
        self,
        noise_sigma: float = 0.05,
        bias: tuple[float, float] = (0.0, 0.0),
        heavy_tail_probability: float = 0.0,
        outlier_scale: float = 1.0,
    ):
        self.noise_sigma = float(noise_sigma)
        self.bias = np.asarray(bias, dtype=np.float64)
        self.heavy_tail_probability = float(
            heavy_tail_probability
        )
        self.outlier_scale = float(outlier_scale)

    def measure(
        self,
        true_delta: np.ndarray,
        rng: np.random.Generator,
    ) -> SensorReading:
        true_delta = np.asarray(
            true_delta,
            dtype=np.float64,
        )

        noise = rng.normal(
            0.0,
            self.noise_sigma,
            size=2,
        )

        anomaly = False

        # Occasional heavy-tailed measurement.
        if rng.random() < self.heavy_tail_probability:
            noise += rng.normal(
                0.0,
                self.noise_sigma * self.outlier_scale,
                size=2,
            )
            anomaly = True

        estimate = true_delta + self.bias + noise

        return SensorReading(
            estimate=estimate,
            sigma=self.noise_sigma,
            valid=True,
            anomaly=anomaly,
        )


class SensorArbitrator:
    """
    Cross-sensor consistency checker.

    The arbitrator does not know the ground truth.
    It only compares the two sensor measurements.
    """

    def __init__(
        self,
        disagreement_threshold: float = 0.35,
    ):
        self.disagreement_threshold = float(
            disagreement_threshold
        )

    def compare(
        self,
        primary: SensorReading,
        verifier: SensorReading,
    ) -> dict:
        delta = primary.estimate - verifier.estimate

        disagreement = float(
            np.linalg.norm(delta)
        )

        combined_sigma = max(
            np.sqrt(
                primary.sigma**2
                + verifier.sigma**2
            ),
            1e-8,
        )

        normalized_disagreement = (
            disagreement / combined_sigma
        )

        cross_mismatch = (
            disagreement
            > self.disagreement_threshold
        )

        if cross_mismatch:
            # Conservative estimate:
            # use the sensor with the smaller uncertainty.
            if primary.sigma <= verifier.sigma:
                selected = primary.estimate.copy()
            else:
                selected = verifier.estimate.copy()
        else:
            # Fuse both estimates using inverse variance weighting.
            w_primary = 1.0 / max(primary.sigma**2, 1e-8)
            w_verifier = 1.0 / max(verifier.sigma**2, 1e-8)

            selected = (
                w_primary * primary.estimate
                + w_verifier * verifier.estimate
            ) / (
                w_primary + w_verifier
            )

        fused_sigma = float(
            np.sqrt(
                1.0
                / (
                    1.0 / max(primary.sigma**2, 1e-8)
                    + 1.0 / max(verifier.sigma**2, 1e-8)
                )
            )
        )

        return {
            "estimate": selected,
            "sigma": fused_sigma,
            "disagreement": disagreement,
            "normalized_disagreement": normalized_disagreement,
            "cross_mismatch": cross_mismatch,
            "anomaly": (
                primary.anomaly
                or verifier.anomaly
            ),
        }
