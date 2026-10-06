from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TemporalResult:
    status: str

    consistent: bool

    previous_distance: float
    current_distance: float

    distance_change: float

    directional_consistency: float

    jump_magnitude: float

    confidence: float


class TemporalConsistencyMonitor:
    """
    Checks whether consecutive sensor estimates evolve
    consistently with the commanded action.

    No ground truth is used.

    This is deliberately based on relative temporal behavior,
    not exact physics prediction, so it remains useful when
    the simulator or real robot has model mismatch.
    """

    def __init__(
        self,
        max_estimate_jump: float = 0.60,
        distance_increase_tolerance: float = 0.15,
        minimum_action_norm: float = 0.05,
    ):
        self.max_estimate_jump = float(
            max_estimate_jump
        )

        self.distance_increase_tolerance = float(
            distance_increase_tolerance
        )

        self.minimum_action_norm = float(
            minimum_action_norm
        )

        self.previous_estimate = None

    def reset(self) -> None:
        self.previous_estimate = None

    def update(
        self,
        estimate: np.ndarray,
        action: np.ndarray,
    ) -> TemporalResult:

        estimate = np.asarray(
            estimate,
            dtype=np.float64,
        )

        action = np.asarray(
            action,
            dtype=np.float64,
        )

        current_distance = float(
            np.linalg.norm(estimate)
        )

        if self.previous_estimate is None:
            self.previous_estimate = estimate.copy()

            return TemporalResult(
                status="INIT",
                consistent=True,
                previous_distance=current_distance,
                current_distance=current_distance,
                distance_change=0.0,
                directional_consistency=1.0,
                jump_magnitude=0.0,
                confidence=1.0,
            )

        previous = self.previous_estimate.copy()

        previous_distance = float(
            np.linalg.norm(previous)
        )

        change = estimate - previous

        jump_magnitude = float(
            np.linalg.norm(change)
        )

        distance_change = (
            current_distance
            - previous_distance
        )

        action_norm = float(
            np.linalg.norm(action)
        )

        directional_consistency = 1.0

        # --------------------------------------------------
        # When the agent actually moves, the target-relative
        # vector should generally move in the opposite
        # direction to the commanded action.
        # --------------------------------------------------

        if (
            action_norm
            >= self.minimum_action_norm
            and jump_magnitude > 1e-8
        ):
            action_direction = (
                action / action_norm
            )

            change_direction = (
                change / jump_magnitude
            )

            directional_consistency = float(
                np.dot(
                    change_direction,
                    -action_direction,
                )
            )

        # --------------------------------------------------
        # Detect implausibly large estimate jumps.
        # --------------------------------------------------

        jump_failure = (
            jump_magnitude
            > self.max_estimate_jump
        )

        # --------------------------------------------------
        # If the robot intentionally moved toward its
        # current estimate, a large sudden increase in
        # estimated distance is suspicious.
        # --------------------------------------------------

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
            < -0.25
        )

        consistent = not (
            jump_failure
            or distance_failure
            or direction_failure
        )

        if jump_failure:
            status = "ESTIMATE_JUMP"

        elif direction_failure:
            status = "DIRECTION_CONTRADICTION"

        elif distance_failure:
            status = "UNEXPECTED_DISTANCE_CHANGE"

        else:
            status = "CONSISTENT"

        # Conservative confidence estimate.
        confidence = 1.0

        confidence *= float(
            np.exp(
                -1.5
                * jump_magnitude
            )
        )

        if directional_consistency < 0.0:
            confidence *= 0.25

        if distance_failure:
            confidence *= 0.25

        if jump_failure:
            confidence *= 0.20

        confidence = float(
            np.clip(
                confidence,
                0.0,
                1.0,
            )
        )

        self.previous_estimate = estimate.copy()

        return TemporalResult(
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
