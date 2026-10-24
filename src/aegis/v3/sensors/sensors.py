from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SensorConfig:
    name: str

    noise_sigma: float = 0.05

    bias: tuple[float, float] = (0.0, 0.0)

    drift_rate: tuple[float, float] = (0.0, 0.0)

    outlier_probability: float = 0.0
    outlier_scale: float = 1.0

    dropout_probability: float = 0.0

    shared_bias_group: str | None = None


@dataclass(frozen=True)
class SensorReading:
    estimate: np.ndarray
    sigma: float
    valid: bool

    anomaly: bool
    dropped: bool

    bias: np.ndarray
    drift: np.ndarray


class FaultInjectableSensor:
    """
    Fault-injectable 2D sensor.

    The sensor receives the true state only to generate a
    simulated measurement. The downstream agent receives
    SensorReading, never the ground truth directly.
    """

    def __init__(self, config: SensorConfig):
        self.config = config

    def measure(
        self,
        true_delta: np.ndarray,
        rng: np.random.Generator,
        step: int = 0,
        shared_bias: np.ndarray | None = None,
    ) -> SensorReading:

        true_delta = np.asarray(
            true_delta,
            dtype=np.float64,
        )

        base_bias = np.asarray(
            self.config.bias,
            dtype=np.float64,
        )

        drift_rate = np.asarray(
            self.config.drift_rate,
            dtype=np.float64,
        )

        drift = drift_rate * float(step)

        if shared_bias is not None:
            total_bias = (
                base_bias
                + drift
                + shared_bias
            )
        else:
            total_bias = (
                base_bias
                + drift
            )

        # Sensor dropout.
        if (
            self.config.dropout_probability > 0.0
            and rng.random()
            < self.config.dropout_probability
        ):
            return SensorReading(
                estimate=np.zeros(
                    2,
                    dtype=np.float64,
                ),
                sigma=float(
                    self.config.noise_sigma
                ),
                valid=False,
                anomaly=True,
                dropped=True,
                bias=total_bias.copy(),
                drift=drift.copy(),
            )

        noise = rng.normal(
            0.0,
            self.config.noise_sigma,
            size=2,
        )

        anomaly = False

        # Heavy outlier.
        if (
            self.config.outlier_probability > 0.0
            and rng.random()
            < self.config.outlier_probability
        ):
            noise += rng.normal(
                0.0,
                self.config.noise_sigma
                * self.config.outlier_scale,
                size=2,
            )

            anomaly = True

        estimate = (
            true_delta
            + total_bias
            + noise
        )

        return SensorReading(
            estimate=estimate,
            sigma=float(
                self.config.noise_sigma
            ),
            valid=True,
            anomaly=anomaly,
            dropped=False,
            bias=total_bias.copy(),
            drift=drift.copy(),
        )


class SharedFaultModel:
    """
    Generates correlated sensor faults.

    Sensors belonging to the same shared_bias_group
    can receive the same hidden bias.
    """

    def __init__(
        self,
        bias: tuple[float, float] = (0.0, 0.0),
    ):
        self.bias = np.asarray(
            bias,
            dtype=np.float64,
        )

    def sample(self) -> np.ndarray:
        return self.bias.copy()

