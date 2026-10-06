from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class WindowedTemporalResult:
    status: str
    consistent: bool

    previous_distance: float
    current_distance: float
    distance_change: float

    directional_consistency: float
    jump_magnitude: float

    confidence: float


class WindowedTemporalConsistencyMonitor:
    """
    Windowed temporal consistency monitor.

    Instead of comparing adjacent noisy measurements,
    compare estimates across a short temporal window.

    This reduces false temporal contradictions caused by
    sensor noise dominating small per-step robot motion.
    """

    def __init__(
        self,
        window_size: int = 5,
        max_window_jump: float = 0.80,
        distance_increase_tolerance: float = 0.25,
        minimum_action_norm: float = 0.05,
        direction_threshold: float = -0.75,
    ):
        self.window_size = int(window_size)
        self.max_window_jump = float(
            max_window_jump
        )
        self.distance_increase_tolerance = float(
            distance_increase_tolerance
        )
        self.minimum_action_norm = float(
            minimum_action_norm
        )
        self.direction_threshold = float(
            direction_threshold
        )

        self.estimates = deque(
            maxlen=self.window_size
        )

        self.actions = deque(
            maxlen=self.window_size
        )

    def reset(self) -> None:
        self.estimates.clear()
        self.actions.clear()

    def update(
        self,
        estimate: np.ndarray,
        action: np.ndarray,
    ) -> WindowedTemporalResult:

        estimate = np.asarray(
            estimate,
            dtype=np.float64,
        )

        action = np.asarray(
            action,
            dtype=np.float64,
        )

        self.estimates.append(
            estimate.copy()
        )

        self.actions.append(
            action.copy()
        )

        current_distance = float(
            np.linalg.norm(estimate)
        )

        if len(self.estimates) < self.window_size:
            return WindowedTemporalResult(
                status="WARMUP",
                consistent=True,
                previous_distance=current_distance,
                current_distance=current_distance,
                distance_change=0.0,
                directional_consistency=1.0,
                jump_magnitude=0.0,
                confidence=1.0,
            )

        previous = self.estimates[0]

        previous_distance = float(
            np.linalg.norm(previous)
        )

        displacement = (
            estimate - previous
        )

        jump_magnitude = float(
            np.linalg.norm(displacement)
        )

        distance_change = (
            current_distance
            - previous_distance
        )

        total_action = np.sum(
            np.asarray(
                self.actions
            ),
            axis=0,
        )

        action_norm = float(
            np.linalg.norm(total_action)
        )

        directional_consistency = 1.0

        if (
            action_norm
            >= self.minimum_action_norm
            and jump_magnitude > 1e-8
        ):
            action_direction = (
                total_action
                / action_norm
            )

            displacement_direction = (
                displacement
                / jump_magnitude
            )

            directional_consistency = float(
                np.dot(
                    displacement_direction,
                    -action_direction,
                )
            )

        jump_failure = (
            jump_magnitude
            > self.max_window_jump
        )

        distance_failure = (
            action_norm
            >= self.minimum_action_norm
            and distance_change
            > self.distance_increase_tolerance
        )

        direction_failure = (
            action_norm
            >= self.minimum_action_norm
            and directional_consistency
            < self.direction_threshold
            and distance_change
            > 0.05
        )

        if jump_failure:
            status = "ESTIMATE_JUMP"
            consistent = False

        elif direction_failure:
            status = "DIRECTION_CONTRADICTION"
            consistent = False

        elif distance_failure:
            status = "UNEXPECTED_DISTANCE_CHANGE"
            consistent = False

        else:
            status = "CONSISTENT"
            consistent = True

        confidence = float(
            np.exp(
                -0.75
                * jump_magnitude
            )
        )

        if direction_failure:
            confidence *= 0.30

        if distance_failure:
            confidence *= 0.30

        if jump_failure:
            confidence *= 0.20

        confidence = float(
            np.clip(
                confidence,
                0.0,
                1.0,
            )
        )

        return WindowedTemporalResult(
            status=status,
            consistent=consistent,
            previous_distance=previous_distance,
            current_distance=current_distance,
            distance_change=distance_change,
            directional_consistency=(
                directional_consistency
            ),
            jump_magnitude=jump_magnitude,
            confidence=confidence,
        )
