from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    action: str
    confidence: float
    reason: str


class AegisDecisionPolicy:
    """
    Risk-aware decision layer for Nexvia Aegis v2.0.

    The policy never sees ground truth.
    It makes a decision from sensor-derived estimates only.
    """

    def __init__(
        self,
        act_confidence: float = 0.75,
        verify_confidence: float = 0.50,
        max_disagreement: float = 0.35,
        target_tolerance: float = 0.25,
    ):
        self.act_confidence = act_confidence
        self.verify_confidence = verify_confidence
        self.max_disagreement = max_disagreement
        self.target_tolerance = target_tolerance

    def decide(
        self,
        estimated_distance: float,
        confidence: float,
        sensor_disagreement: float,
        cross_mismatch: bool,
    ) -> Decision:

        if cross_mismatch:
            return Decision(
                action="ABSTAIN",
                confidence=confidence,
                reason="cross_sensor_mismatch",
            )

        if sensor_disagreement > self.max_disagreement:
            return Decision(
                action="VERIFY",
                confidence=confidence,
                reason="sensor_disagreement",
            )

        if estimated_distance <= self.target_tolerance:
            if confidence >= self.act_confidence:
                return Decision(
                    action="ACT",
                    confidence=confidence,
                    reason="high_confidence_target",
                )

            return Decision(
                action="VERIFY",
                confidence=confidence,
                reason="target_near_but_uncertain",
            )

        if confidence >= self.act_confidence:
            return Decision(
                action="ACT",
                confidence=confidence,
                reason="high_confidence",
            )

        if confidence >= self.verify_confidence:
            return Decision(
                action="VERIFY",
                confidence=confidence,
                reason="moderate_confidence",
            )

        return Decision(
            action="ABSTAIN",
            confidence=confidence,
            reason="low_confidence",
        )
