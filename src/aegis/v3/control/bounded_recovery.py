from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BoundedRecoveryAction:
    action: np.ndarray
    mode: str
    reason: str
    level: int
    terminal: bool


class BoundedRecoveryManager:
    """
    Fault-aware bounded recovery for Nexvia Aegis 3.1.

    Design goals:
        - never loop indefinitely on a persistent fault
        - do not trust a corrupted estimate for common-mode faults
        - provide a terminal FAIL_SAFE state
        - preserve the exploratory RecoveryManager as a baseline

    Recovery levels:
        1 -> HOLD
        2 -> SAFE_PROBE
        3 -> FAIL_SAFE
    """

    def __init__(
        self,
        max_recovery_steps: int = 3,
        probe_magnitude: float = 0.10,
    ):
        self.max_recovery_steps = int(
            max_recovery_steps
        )

        self.probe_magnitude = float(
            probe_magnitude
        )

        self.failure_streak = 0

    def reset(self) -> None:
        self.failure_streak = 0

    def update(
        self,
        *,
        fault_status: str,
    ) -> BoundedRecoveryAction:

        if fault_status == "NONE":
            self.failure_streak = 0

            return BoundedRecoveryAction(
                action=np.zeros(
                    2,
                    dtype=np.float64,
                ),
                mode="NORMAL",
                reason="no_active_fault",
                level=0,
                terminal=False,
            )

        self.failure_streak += 1

        # --------------------------------------------------
        # Level 1: stop and acquire fresh evidence.
        # --------------------------------------------------

        if self.failure_streak == 1:
            return BoundedRecoveryAction(
                action=np.zeros(
                    2,
                    dtype=np.float64,
                ),
                mode="HOLD",
                reason="initial_fault_confirmation",
                level=1,
                terminal=False,
            )

        # --------------------------------------------------
        # Level 2: small deterministic active sensing motion.
        #
        # IMPORTANT:
        # This action does not use the untrusted target
        # estimate. The motion is fixed and bounded.
        # --------------------------------------------------

        if self.failure_streak == 2:
            return BoundedRecoveryAction(
                action=np.array(
                    [
                        self.probe_magnitude,
                        0.0,
                    ],
                    dtype=np.float64,
                ),
                mode="SAFE_PROBE",
                reason="independent_active_sensing_probe",
                level=2,
                terminal=False,
            )

        # --------------------------------------------------
        # Level 3+: persistent fault.
        #
        # Do not continue probing forever.
        # Enter terminal fail-safe state.
        # --------------------------------------------------

        return BoundedRecoveryAction(
            action=np.zeros(
                2,
                dtype=np.float64,
            ),
            mode="FAIL_SAFE",
            reason=(
                "persistent_unresolved_fault"
            ),
            level=min(
                self.failure_streak,
                self.max_recovery_steps,
            ),
            terminal=True,
        )

