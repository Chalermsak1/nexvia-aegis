from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.v3.sensors.cross_modal import RangeReading


@dataclass(frozen=True)
class PostActionResult:
    status: str
    distance_change: float
    normalized_change: float
    confidence: float
    consistent: bool


class PostActionVerifier:
    """
    Verifies whether the physical effect of the previous action
    is consistent with the direction implied by the controller.

    No ground truth is used.

    Positive distance_change:
        range increased after the action.

    Negative distance_change:
        range decreased after the action.

    The verifier only evaluates actions that were intended to
    move toward the target. Small actions below min_action_norm
    are treated as insufficient evidence.
    """

    def __init__(
        self,
        min_action_norm: float = 0.05,
        progress_z_threshold: float = 1.5,
        contradiction_z_threshold: float = 2.0,
    ):
        self.min_action_norm = float(
            min_action_norm
        )

        self.progress_z_threshold = float(
            progress_z_threshold
        )

        self.contradiction_z_threshold = float(
            contradiction_z_threshold
        )

    def verify(
        self,
        previous_range: RangeReading | None,
        current_range: RangeReading,
        previous_action: np.ndarray,
    ) -> PostActionResult:

        if (
            previous_range is None
            or not previous_range.valid
            or not current_range.valid
        ):
            return PostActionResult(
                status="INSUFFICIENT_EVIDENCE",
                distance_change=0.0,
                normalized_change=0.0,
                confidence=0.0,
                consistent=False,
            )

        action = np.asarray(
            previous_action,
            dtype=np.float64,
        )

        action_norm = float(
            np.linalg.norm(action)
        )

        if action_norm < self.min_action_norm:
            return PostActionResult(
                status="INSUFFICIENT_EVIDENCE",
                distance_change=0.0,
                normalized_change=0.0,
                confidence=0.0,
                consistent=False,
            )

        distance_change = float(
            current_range.distance
            - previous_range.distance
        )

        combined_sigma = max(
            float(
                np.sqrt(
                    previous_range.sigma**2
                    + current_range.sigma**2
                )
            ),
            1e-8,
        )

        normalized_change = (
            distance_change
            / combined_sigma
        )

        # --------------------------------------------------
        # Range decreased.
        #
        # This is physical evidence consistent with
        # moving toward the target.
        # --------------------------------------------------

        if (
            normalized_change
            <= -self.progress_z_threshold
        ):
            confidence = float(
                np.clip(
                    0.5
                    + min(
                        abs(normalized_change)
                        / 4.0,
                        0.5,
                    ),
                    0.0,
                    1.0,
                )
            )

            return PostActionResult(
                status="PROGRESS_CONFIRMED",
                distance_change=distance_change,
                normalized_change=normalized_change,
                confidence=confidence,
                consistent=True,
            )

        # --------------------------------------------------
        # Distance essentially unchanged.
        #
        # This is ambiguous evidence and should not by itself
        # declare a fault.
        # --------------------------------------------------

        if (
            abs(normalized_change)
            <= self.progress_z_threshold
        ):
            return PostActionResult(
                status="NO_CLEAR_PROGRESS",
                distance_change=distance_change,
                normalized_change=normalized_change,
                confidence=0.50,
                consistent=True,
            )

        # --------------------------------------------------
        # Range increased.
        #
        # This contradicts the assumption that the previous
        # action moved toward the target.
        # --------------------------------------------------

        if (
            normalized_change
            >= self.contradiction_z_threshold
        ):
            confidence = float(
                np.clip(
                    0.5
                    + min(
                        abs(normalized_change)
                        / 4.0,
                        0.5,
                    ),
                    0.0,
                    1.0,
                )
            )

            return PostActionResult(
                status="POST_ACTION_CONTRADICTION",
                distance_change=distance_change,
                normalized_change=normalized_change,
                confidence=confidence,
                consistent=False,
            )

        return PostActionResult(
            status="NO_CLEAR_PROGRESS",
            distance_change=distance_change,
            normalized_change=normalized_change,
            confidence=0.50,
            consistent=True,
        )
