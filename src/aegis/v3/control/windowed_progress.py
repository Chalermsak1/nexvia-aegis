from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from aegis.v3.sensors.cross_modal import RangeReading


@dataclass(frozen=True)
class WindowedProgressResult:
    status: str
    distance_change: float
    normalized_change: float
    confidence: float
    consistent: bool
    window_size: int
    action_coherence: float


class WindowedProgressVerifier:
    """
    Windowed physical-effect verifier.

    Instead of judging one noisy range transition, compare
    averaged range measurements at the beginning and end
    of a fixed temporal window.

    No ground truth is used.

    Status:
        WARMUP
        INSUFFICIENT_ACTION
        PROGRESS_CONFIRMED
        REGRESSION_CONFIRMED
        NO_CLEAR_PROGRESS
    """

    def __init__(
        self,
        window_size: int = 20,
        edge_samples: int = 5,
        min_action_norm: float = 0.05,
        min_action_coherence: float = 0.80,
        z_threshold: float = 1.2,
    ):
        if edge_samples * 2 >= window_size:
            raise ValueError(
                "edge_samples*2 must be smaller than window_size"
            )

        self.window_size = int(window_size)
        self.edge_samples = int(edge_samples)
        self.min_action_norm = float(
            min_action_norm
        )
        self.min_action_coherence = float(
            min_action_coherence
        )
        self.z_threshold = float(
            z_threshold
        )

        self._ranges: deque[RangeReading] = deque(
            maxlen=self.window_size
        )
        self._actions: deque[np.ndarray] = deque(
            maxlen=self.window_size
        )

    def reset(self) -> None:
        self._ranges.clear()
        self._actions.clear()

    @staticmethod
    def _action_coherence(
        actions: list[np.ndarray],
    ) -> float:
        if not actions:
            return 0.0

        directions = []

        for action in actions:
            vector = np.asarray(
                action,
                dtype=np.float64,
            )

            norm = float(
                np.linalg.norm(vector)
            )

            if norm <= 1e-8:
                continue

            directions.append(
                vector / norm
            )

        if not directions:
            return 0.0

        resultant = np.sum(
            np.asarray(directions),
            axis=0,
        )

        return float(
            np.linalg.norm(resultant)
            / len(directions)
        )

    def update(
        self,
        range_reading: RangeReading,
        action: np.ndarray,
    ) -> WindowedProgressResult:

        self._ranges.append(range_reading)
        self._actions.append(
            np.asarray(
                action,
                dtype=np.float64,
            ).copy()
        )

        if len(self._ranges) < self.window_size:
            return WindowedProgressResult(
                status="WARMUP",
                distance_change=0.0,
                normalized_change=0.0,
                confidence=0.0,
                consistent=True,
                window_size=len(
                    self._ranges
                ),
                action_coherence=0.0,
            )

        valid_ranges = [
            reading
            for reading in self._ranges
            if reading.valid
        ]

        if len(valid_ranges) < (
            self.edge_samples * 2
        ):
            return WindowedProgressResult(
                status="INSUFFICIENT_ACTION",
                distance_change=0.0,
                normalized_change=0.0,
                confidence=0.0,
                consistent=False,
                window_size=len(
                    self._ranges
                ),
                action_coherence=0.0,
            )

        actions = list(
            self._actions
        )

        nonzero_actions = [
            action
            for action in actions
            if np.linalg.norm(action)
            >= self.min_action_norm
        ]

        if not nonzero_actions:
            return WindowedProgressResult(
                status="INSUFFICIENT_ACTION",
                distance_change=0.0,
                normalized_change=0.0,
                confidence=0.0,
                consistent=False,
                window_size=len(
                    self._ranges
                ),
                action_coherence=0.0,
            )

        coherence = (
            self._action_coherence(
                nonzero_actions
            )
        )

        if coherence < self.min_action_coherence:
            return WindowedProgressResult(
                status="INSUFFICIENT_ACTION",
                distance_change=0.0,
                normalized_change=0.0,
                confidence=0.0,
                consistent=True,
                window_size=len(
                    self._ranges
                ),
                action_coherence=coherence,
            )

        first = np.asarray(
            [
                reading.distance
                for reading
                in list(self._ranges)[
                    : self.edge_samples
                ]
                if reading.valid
            ],
            dtype=np.float64,
        )

        last = np.asarray(
            [
                reading.distance
                for reading
                in list(self._ranges)[
                    -self.edge_samples :
                ]
                if reading.valid
            ],
            dtype=np.float64,
        )

        if (
            len(first) < 2
            or len(last) < 2
        ):
            return WindowedProgressResult(
                status="INSUFFICIENT_ACTION",
                distance_change=0.0,
                normalized_change=0.0,
                confidence=0.0,
                consistent=False,
                window_size=len(
                    self._ranges
                ),
                action_coherence=coherence,
            )

        first_mean = float(
            np.mean(first)
        )

        last_mean = float(
            np.mean(last)
        )

        distance_change = (
            last_mean - first_mean
        )

        sigma_values = np.asarray(
            [
                reading.sigma
                for reading
                in list(self._ranges)
                if reading.valid
            ],
            dtype=np.float64,
        )

        sigma = max(
            float(
                np.mean(sigma_values)
            ),
            1e-8,
        )

        # Standard error of the difference between
        # two independent edge means.
        edge_sigma = sigma * np.sqrt(
            (1.0 / len(first))
            + (1.0 / len(last))
        )

        edge_sigma = max(
            float(edge_sigma),
            1e-8,
        )

        normalized_change = (
            distance_change
            / edge_sigma
        )

        magnitude = abs(
            normalized_change
        )

        confidence = float(
            np.clip(
                0.50
                + min(
                    magnitude / 4.0,
                    0.50,
                ),
                0.0,
                1.0,
            )
        )

        # --------------------------------------------------
        # Physical progress.
        # --------------------------------------------------

        if (
            normalized_change
            <= -self.z_threshold
        ):
            return WindowedProgressResult(
                status="PROGRESS_CONFIRMED",
                distance_change=distance_change,
                normalized_change=normalized_change,
                confidence=confidence,
                consistent=True,
                window_size=len(
                    self._ranges
                ),
                action_coherence=coherence,
            )

        # --------------------------------------------------
        # Physical regression.
        # --------------------------------------------------

        if (
            normalized_change
            >= self.z_threshold
        ):
            return WindowedProgressResult(
                status="REGRESSION_CONFIRMED",
                distance_change=distance_change,
                normalized_change=normalized_change,
                confidence=confidence,
                consistent=False,
                window_size=len(
                    self._ranges
                ),
                action_coherence=coherence,
            )

        return WindowedProgressResult(
            status="NO_CLEAR_PROGRESS",
            distance_change=distance_change,
            normalized_change=normalized_change,
            confidence=0.50,
            consistent=True,
            window_size=len(
                self._ranges
            ),
            action_coherence=coherence,
        )
