from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RecoveryAction:
    action: np.ndarray
    mode: str
    reason: str
    level: int


class RecoveryManager:
    """
    Active recovery controller for Nexvia Aegis 3.1.

    Recovery strategy:
        Level 0 -> normal operation
        Level 1 -> safe hold
        Level 2 -> active probe
        Level 3 -> controlled retreat / reacquisition
        Level 4 -> persistent-fault hold

    The manager does not use ground truth.
    """

    def __init__(
        self,
        max_recovery_level: int = 4,
        hold_steps: int = 1,
        probe_magnitude: float = 0.20,
        retreat_magnitude: float = 0.35,
    ):
        self.max_recovery_level = int(
            max_recovery_level
        )

        self.hold_steps = int(hold_steps)

        self.probe_magnitude = float(
            probe_magnitude
        )

        self.retreat_magnitude = float(
            retreat_magnitude
        )

        self.failure_streak = 0

    def reset(self) -> None:
        self.failure_streak = 0

    def _normalize(
        self,
        vector: np.ndarray,
    ) -> np.ndarray:
        vector = np.asarray(
            vector,
            dtype=np.float64,
        )

        norm = float(
            np.linalg.norm(vector)
        )

        if norm <= 1e-8:
            return np.zeros(
                2,
                dtype=np.float64,
            )

        return vector / norm

    def _probe(
        self,
        estimate: np.ndarray,
    ) -> np.ndarray:
        direction = self._normalize(
            estimate
        )

        # Rotate 90 degrees.
        lateral = np.array(
            [-direction[1], direction[0]],
            dtype=np.float64,
        )

        return (
            lateral
            * self.probe_magnitude
        )

    def _retreat(
        self,
        estimate: np.ndarray,
    ) -> np.ndarray:
        direction = self._normalize(
            estimate
        )

        return (
            -direction
            * self.retreat_magnitude
        )

    def update(
        self,
        *,
        fault_detected: bool,
        estimate: np.ndarray,
    ) -> RecoveryAction:

        if not fault_detected:
            self.failure_streak = 0

            return RecoveryAction(
                action=np.zeros(
                    2,
                    dtype=np.float64,
                ),
                mode="NORMAL",
                reason="no_active_fault",
                level=0,
            )

        self.failure_streak += 1

        level = min(
            self.failure_streak,
            self.max_recovery_level,
        )

        # ----------------------------------------------
        # Level 1: hold position and acquire fresh
        # evidence.
        # ----------------------------------------------
        if level == 1:
            return RecoveryAction(
                action=np.zeros(
                    2,
                    dtype=np.float64,
                ),
                mode="HOLD",
                reason="initial_fault_confirmation",
                level=level,
            )

        # ----------------------------------------------
        # Level 2: lateral active probe.
        #
        # A small orthogonal motion changes geometry
        # without committing to the suspected target path.
        # ----------------------------------------------
        if level == 2:
            return RecoveryAction(
                action=self._probe(estimate),
                mode="PROBE",
                reason="active_reacquisition_probe",
                level=level,
            )

        # ----------------------------------------------
        # Level 3: controlled retreat.
        # ----------------------------------------------
        if level == 3:
            return RecoveryAction(
                action=self._retreat(estimate),
                mode="RETREAT",
                reason="controlled_recovery_retreat",
                level=level,
            )

        # ----------------------------------------------
        # Persistent fault.
        # ----------------------------------------------
        return RecoveryAction(
            action=np.zeros(
                2,
                dtype=np.float64,
            ),
            mode="ESCALATE",
            reason="persistent_fault",
            level=level,
        )

