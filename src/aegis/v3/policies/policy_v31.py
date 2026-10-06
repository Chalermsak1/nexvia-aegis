from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aegis.v3.control.fault_aware_controller import (
    FaultAwareVerification,
)


@dataclass(frozen=True)
class AegisDecisionV31:
    action: str
    reason: str
    confidence: float
    recovery_level: int


class AegisPolicyV31:
    """
    Fault-tolerant decision policy for Nexvia Aegis 3.1.

    Actions:
        ACT
        VERIFY
        ABSTAIN
        RECOVER

    Key behavior:
        - Fully verified evidence can ACT.
        - A single isolated sensor fault may ACT in degraded mode
          when an independent modality still verifies the estimate.
        - Multi-sensor/common-mode faults must not ACT.
        - Persistent uncertainty escalates into recovery.
    """

    def __init__(
        self,
        act_confidence: float = 0.75,
        verify_confidence: float = 0.50,
        target_tolerance: float = 0.25,
        recovery_after: int = 3,
    ):
        self.act_confidence = float(act_confidence)
        self.verify_confidence = float(verify_confidence)
        self.target_tolerance = float(target_tolerance)
        self.recovery_after = int(recovery_after)

        self.failure_streak = 0

    def reset(self) -> None:
        self.failure_streak = 0

    def decide(
        self,
        verification: FaultAwareVerification,
    ) -> AegisDecisionV31:

        estimated_distance = float(
            np.linalg.norm(verification.estimate)
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
            and confidence >= self.act_confidence
        ):
            self.failure_streak = 0

            return AegisDecisionV31(
                action="ACT",
                reason="verified_evidence",
                confidence=confidence,
                recovery_level=0,
            )

        # --------------------------------------------------
        # Single sensor fault successfully isolated.
        #
        # Independent modality verifies the trusted sensor,
        # so we can continue operating in degraded mode.
        # --------------------------------------------------

        if (
            status == "ISOLATED_SENSOR_FAULT"
            and verification.safe_to_act
            and confidence >= self.act_confidence
        ):
            self.failure_streak = 0

            return AegisDecisionV31(
                action="ACT",
                reason="isolated_fault_degraded_operation",
                confidence=confidence,
                recovery_level=0,
            )

        # --------------------------------------------------
        # Verified final approach.
        # --------------------------------------------------

        if (
            status in {
                "VERIFIED",
                "ISOLATED_SENSOR_FAULT",
            }
            and verification.safe_to_act
            and estimated_distance <= self.target_tolerance
            and confidence >= self.verify_confidence
        ):
            self.failure_streak = 0

            return AegisDecisionV31(
                action="ACT",
                reason="verified_final_approach",
                confidence=confidence,
                recovery_level=0,
            )

        # --------------------------------------------------
        # Strong multi-sensor / common-mode failure.
        #
        # No independent trusted sensor exists.
        # Never allow ACT.
        # --------------------------------------------------

        if status == "MULTI_SENSOR_FAULT":
            self.failure_streak += 1

            if self.failure_streak >= self.recovery_after:
                return AegisDecisionV31(
                    action="RECOVER",
                    reason="persistent_multi_sensor_fault",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecisionV31(
                action="ABSTAIN",
                reason="multi_sensor_fault",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        # --------------------------------------------------
        # Temporal contradiction.
        # --------------------------------------------------

        if status == "TEMPORAL_CONTRADICTION":
            self.failure_streak += 1

            if self.failure_streak >= self.recovery_after:
                return AegisDecisionV31(
                    action="RECOVER",
                    reason="persistent_temporal_contradiction",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecisionV31(
                action="ABSTAIN",
                reason="temporal_contradiction",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        # --------------------------------------------------
        # Generic mismatch states.
        # --------------------------------------------------

        if status in {
            "SENSOR_MISMATCH",
            "SINGLE_SENSOR_MISMATCH",
            "CROSS_MODAL_MISMATCH",
            "MULTI_MODAL_MISMATCH",
        }:
            self.failure_streak += 1

            if self.failure_streak >= self.recovery_after:
                return AegisDecisionV31(
                    action="RECOVER",
                    reason="persistent_verification_mismatch",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecisionV31(
                action="ABSTAIN",
                reason="verification_mismatch",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        # --------------------------------------------------
        # No signal / unavailable verification.
        # --------------------------------------------------

        if status in {
            "NO_SIGNAL",
            "NO_VECTOR_SIGNAL",
            "RANGE_UNAVAILABLE",
        }:
            self.failure_streak += 1

            if self.failure_streak >= self.recovery_after:
                return AegisDecisionV31(
                    action="RECOVER",
                    reason="persistent_missing_verification",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecisionV31(
                action="ABSTAIN",
                reason="verification_unavailable",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        # --------------------------------------------------
        # Degraded but not explicitly isolated.
        # --------------------------------------------------

        if status == "DEGRADED_VERIFIED":
            if (
                verification.safe_to_act
                and confidence >= self.act_confidence
            ):
                self.failure_streak = 0

                return AegisDecisionV31(
                    action="ACT",
                    reason="degraded_verified_operation",
                    confidence=confidence,
                    recovery_level=0,
                )

            self.failure_streak += 1

            if self.failure_streak >= self.recovery_after:
                return AegisDecisionV31(
                    action="RECOVER",
                    reason="persistent_degraded_sensing",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecisionV31(
                action="VERIFY",
                reason="degraded_but_not_actionable",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        # --------------------------------------------------
        # Generic uncertainty.
        # --------------------------------------------------

        if confidence >= self.verify_confidence:
            self.failure_streak += 1

            if self.failure_streak >= self.recovery_after:
                return AegisDecisionV31(
                    action="RECOVER",
                    reason="persistent_uncertain_evidence",
                    confidence=confidence,
                    recovery_level=self.failure_streak,
                )

            return AegisDecisionV31(
                action="VERIFY",
                reason="uncertain_evidence",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        self.failure_streak += 1

        if self.failure_streak >= self.recovery_after:
            return AegisDecisionV31(
                action="RECOVER",
                reason="persistent_low_confidence",
                confidence=confidence,
                recovery_level=self.failure_streak,
            )

        return AegisDecisionV31(
            action="ABSTAIN",
            reason="low_confidence",
            confidence=confidence,
            recovery_level=self.failure_streak,
        )
