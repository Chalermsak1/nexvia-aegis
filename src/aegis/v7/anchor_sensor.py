"""
NEXVIA AEGIS V7.0 — Intermittent Independent Sensor Anchoring (AEGIS-Anchor).

Simulates an on-demand independent localization modality (e.g., UWB anchor network,
external laser tracker, or visual fiducial reference) decoupled from onboard sensors.

Attributes:
- Query-gated: Returns measurements only when explicitly queried.
- Cost-accruing: Each query incurs an operational cost (energy/bandwidth).
- Fault-injectable: Supports nominal low noise, intermittent dropout, and adversarial corruption.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class AnchorSensorConfig:
    name: str = "anchor_uwb"
    noise_sigma: float = 0.04
    bias: tuple[float, float] = (0.0, 0.0)
    dropout_probability: float = 0.0
    query_cost: float = 0.05
    is_corrupted: bool = False
    corrupted_bias: tuple[float, float] = (1.2, -1.0)


@dataclass
class AnchorReading:
    estimate: np.ndarray  # 2D relative vector (p* - p_robot)
    sigma: float
    valid: bool
    queried: bool
    cost_accrued: float


class AnchorSensor:
    """
    Intermittent Independent Anchor Sensor.
    """

    def __init__(self, config: AnchorSensorConfig | None = None):
        self.config = config or AnchorSensorConfig()
        self.total_queries = 0
        self.total_cost = 0.0

    def reset(self) -> None:
        self.total_queries = 0
        self.total_cost = 0.0

    def measure(
        self,
        true_relative_delta: np.ndarray,
        rng: np.random.Generator,
        query: bool = False,
    ) -> AnchorReading:
        """
        Samples the anchor observation if query is True.
        """
        if not query:
            return AnchorReading(
                estimate=np.zeros(2, dtype=np.float64),
                sigma=self.config.noise_sigma,
                valid=False,
                queried=False,
                cost_accrued=0.0,
            )

        self.total_queries += 1
        self.total_cost += self.config.query_cost

        # Dropout check
        if self.config.dropout_probability > 0.0:
            if rng.random() < self.config.dropout_probability:
                return AnchorReading(
                    estimate=np.zeros(2, dtype=np.float64),
                    sigma=self.config.noise_sigma,
                    valid=False,
                    queried=True,
                    cost_accrued=self.config.query_cost,
                )

        # Apply noise
        noise = rng.normal(0.0, self.config.noise_sigma, size=2)

        # Apply bias (nominal or corrupted)
        if self.config.is_corrupted:
            b = np.asarray(self.config.corrupted_bias, dtype=np.float64)
        else:
            b = np.asarray(self.config.bias, dtype=np.float64)

        observed_delta = true_relative_delta + b + noise

        return AnchorReading(
            estimate=observed_delta.copy(),
            sigma=self.config.noise_sigma,
            valid=True,
            queried=True,
            cost_accrued=self.config.query_cost,
        )
