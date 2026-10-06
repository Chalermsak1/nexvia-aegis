from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.v3.control.verification_controller import (
    UnifiedVerification,
)


@dataclass(frozen=True)
class AegisDecision:
    action: str
    reason: str
    confidence: float
    recovery_level: int


class AegisPolicyV3:
    """
    State-aware decision policy for Nexvia Aegis 3.0.

    Actions:
        ACT
        VERIFY
        ABSTAIN
        RECOVER
    """

    def __init__(
        self,
        act_confidence: float = 0.75,
        verify_confidence: float = 0.50,
        target_tolerance: float = 0.25,
        recovery_after: int = 3,
    ):
        self.act_confidence = float(
            act_confidence
        )

        self.verify_confidence = float(
            verify_confidence
        )

        self.target_tolerance = float(
            target_tolerance
        )

        self.recovery_after = int(
            recovery_after
        )

        self.failure_streak = 0

    def reset(self) -> None:
        self.failure_streak = 0

    def decide(
        self,
        verification: UnifiedVerification,
    ) -> AegisDecision:

        estimated_distance = float(
            np.linalg.norm(
                verification.estimate
            )
        )

        confidence = float(
            verification.confidence
        )

        status = verification.status

        # --------------------------------------------------
        # Fully verified evidence.
        # --------------------------------------------------

        if (
            status == "VERIFIED"
            and verification.safe_to_act
        ):
            self.failure_streak = 0

            return AegisDecision(
                action="ACT",
                reason="verified_evidence",
                confidence=confidence,
                recovery_level=0,
            )

        # --------------------------------------------------
        # We have verification, but target estimate is
        # close enough that another sensing cycle is safer
        # before final approach.
        # --------------------------------------------------

        if (
            status == "VERIFIED"
            and estimated_distance
            <= self.target_tolerance
        ):
            self.failure_streak = 0

            return AegisDecision(
                action="ACT",
                reason="verified_final_approach",
                confidence=confidence,
                recovery_level=0,
            )

        # --------------------------------------------------
        # Degraded sensing.
        # --------------------------------------------------

        if status == "DEGRADED_VERIFIED":
            self.failure_streak += 1

            if (
                self.failure_streak
                >= self.recovery_after
            ):
                return AegisDecision(
                    action="RECOVER",
                    reason="persistent_degraded_sensing",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecision(
                action="VERIFY",
                reason="degraded_but_independently_verified",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        # --------------------------------------------------
        # Direct sensor mismatch.
        # --------------------------------------------------

        if status == "SENSOR_MISMATCH":
            self.failure_streak += 1

            if (
                self.failure_streak
                >= self.recovery_after
            ):
                return AegisDecision(
                    action="RECOVER",
                    reason="persistent_sensor_mismatch",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecision(
                action="VERIFY",
                reason="sensor_mismatch",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        # --------------------------------------------------
        # Cross-modal mismatch is a stronger fault signal.
        # --------------------------------------------------

        if status in {
            "CROSS_MODAL_MISMATCH",
            "MULTI_MODAL_MISMATCH",
        }:
            self.failure_streak += 1

            if (
                self.failure_streak
                >= self.recovery_after
            ):
                return AegisDecision(
                    action="RECOVER",
                    reason="persistent_cross_modal_failure",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecision(
                action="ABSTAIN",
                reason="cross_modal_mismatch",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        # --------------------------------------------------
        # No signal / unavailable verification.
        # --------------------------------------------------

        if status in {
            "NO_SIGNAL",
            "RANGE_UNAVAILABLE",
        }:
            self.failure_streak += 1

            if (
                self.failure_streak
                >= self.recovery_after
            ):
                return AegisDecision(
                    action="RECOVER",
                    reason="persistent_missing_verification",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecision(
                action="ABSTAIN",
                reason="verification_unavailable",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        # --------------------------------------------------
        # Generic uncertain state.
        # --------------------------------------------------

        if confidence >= self.verify_confidence:
            self.failure_streak += 1

            return AegisDecision(
                action="VERIFY",
                reason="uncertain_evidence",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        self.failure_streak += 1

        if self.failure_streak >= self.recovery_after:
            return AegisDecision(
                action="RECOVER",
                reason="persistent_low_confidence",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        return AegisDecision(
            action="ABSTAIN",
            reason="low_confidence",
            confidence=confidence,
            recovery_level=self.failure_streak,
        )
