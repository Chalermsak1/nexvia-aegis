"""
NEXVIA AEGIS-Next — Classical, Statistical, and Architectural Baseline Suite.

Provides standardized, fair implementations of 7 competing baseline controllers:
1. UnshieldedAlwaysActController: Naive sensor fusion, zero monitoring, zero abstention.
2. ChiSquareNISGatingController: Classical Normalized Innovation Squared (NIS) chi-square test.
3. EKFConsistencyController: EKF state-tracking with innovation consistency gating.
4. AegisV4PassiveController: Passive cross-modal geometric verification with certified abstention.
5. AegisV5HuberController: Online Huber M-estimation with fixed orthogonal probing.
6. AegisV6DiscriminativeController: Multi-hypothesis Bayesian diagnosis with active probing.
7. AegisV7MPCBaselineController: Risk-constrained pseudo-MPC with on-demand anchor.
"""

from __future__ import annotations

import numpy as np

from aegis.calibration import OnlineBiasEstimator
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v6.diagnosis import MultiHypothesisDiagnosisEngine
from aegis.v6.hypothesis_models import FaultHypothesis
from aegis.v6.recovery_controller import AegisV6RecoveryController
from aegis.v6.trajectory_planner import ProbingStrategy
from aegis.v7.anchor_scheduler import AnchorIntegrityGate, AnchorQueryScheduler, AnchorScheduleConfig
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v7.recovery_controller import AegisV7RecoveryController


def fuse_vector_sensors(reading_a: SensorReading, reading_b: SensorReading) -> tuple[np.ndarray, bool]:
    """Computes inverse-variance weighted fusion of dual vector sensors."""
    if reading_a.valid and reading_b.valid:
        w_a = 1.0 / max(reading_a.sigma**2, 1e-8)
        w_b = 1.0 / max(reading_b.sigma**2, 1e-8)
        return (w_a * reading_a.estimate + w_b * reading_b.estimate) / (w_a + w_b), True
    elif reading_a.valid:
        return reading_a.estimate.copy(), True
    elif reading_b.valid:
        return reading_b.estimate.copy(), True
    return np.zeros(2, dtype=np.float64), False


# ---------------------------------------------------------------------------
# Baseline 1: Unshielded Always Act
# ---------------------------------------------------------------------------
class UnshieldedAlwaysActController:
    """Naive unshielded proportional pursuit controller."""

    def __init__(self, target_tolerance: float = 0.22, v_max: float = 0.50):
        self.target_tolerance = target_tolerance
        self.v_max = v_max
        self._prev_vector: np.ndarray | None = None
        self._velocity: np.ndarray = np.zeros(2)

    def reset(self) -> None:
        self._prev_vector = None
        self._velocity = np.zeros(2)

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        raw_vec, valid = fuse_vector_sensors(reading_a, reading_b)
        if not valid:
            return np.zeros(2), "VERIFY", raw_vec, False

        if self._prev_vector is not None:
            self._velocity = -(raw_vec - self._prev_vector) / 0.02
        self._prev_vector = raw_vec.copy()

        dist = float(np.linalg.norm(raw_vec))
        if dist <= self.target_tolerance:
            return np.zeros(2), "STOP", raw_vec, False

        u_dir = raw_vec / max(dist, 1e-6)
        action = np.clip(u_dir * self.v_max - 0.20 * self._velocity, -1.0, 1.0)
        return action, "ACT", raw_vec, False


# ---------------------------------------------------------------------------
# Baseline 2: Chi-Square Innovation Residual Gating (Mehra, Willsky)
# ---------------------------------------------------------------------------
class ChiSquareNISGatingController:
    """
    Classical Normalized Innovation Squared (NIS) Chi-Square Monitor.
    Monitors inter-sensor innovation: y_t = z_a - z_b.
    NIS = y_t^T S_t^{-1} y_t ~ chi_2^2 under H0. Threshold = 5.991 (95%).
    """

    def __init__(self, target_tolerance: float = 0.22, chi2_threshold: float = 5.991):
        self.target_tolerance = target_tolerance
        self.chi2_threshold = chi2_threshold
        self.consecutive_breaches: int = 0
        self._prev_vector: np.ndarray | None = None
        self._velocity: np.ndarray = np.zeros(2)
        self.mode = "NOMINAL"

    def reset(self) -> None:
        self.consecutive_breaches = 0
        self._prev_vector = None
        self._velocity = np.zeros(2)
        self.mode = "NOMINAL"

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        raw_vec, valid = fuse_vector_sensors(reading_a, reading_b)
        if not valid:
            return np.zeros(2), "ABSTAIN", raw_vec, False

        if self._prev_vector is not None:
            self._velocity = -(raw_vec - self._prev_vector) / 0.02
        self._prev_vector = raw_vec.copy()

        if self.mode == "ABSTAIN":
            return np.zeros(2), "ABSTAIN", raw_vec, False

        # Compute NIS if both vector readings are valid
        if reading_a.valid and reading_b.valid:
            diff = reading_a.estimate - reading_b.estimate
            cov_diag = reading_a.sigma**2 + reading_b.sigma**2
            nis = float(np.sum(diff**2) / max(cov_diag, 1e-8))

            if nis > self.chi2_threshold:
                self.consecutive_breaches += 1
                if self.consecutive_breaches >= 2:
                    self.mode = "ABSTAIN"
                    return np.zeros(2), "ABSTAIN", raw_vec, False
            else:
                self.consecutive_breaches = 0

        dist = float(np.linalg.norm(raw_vec))
        if dist <= self.target_tolerance:
            return np.zeros(2), "STOP", raw_vec, False

        u_dir = raw_vec / max(dist, 1e-6)
        action = np.clip(u_dir * 0.50 - 0.20 * self._velocity, -1.0, 1.0)
        return action, "ACT", raw_vec, False


# ---------------------------------------------------------------------------
# Baseline 3: EKF State & Innovation Consistency Monitor
# ---------------------------------------------------------------------------
class EKFConsistencyController:
    """
    Extended Kalman Filter with online innovation-covariance consistency monitoring.
    Estimates 2D target vector state d_t and monitors range innovation:
    r_innov = | ||d_hat|| - r_t |.
    """

    def __init__(self, target_tolerance: float = 0.22, gate_sigma: float = 3.0):
        self.target_tolerance = target_tolerance
        self.gate_threshold = gate_sigma**2  # 9.0 for 3-sigma
        self.d_hat = np.zeros(2)
        self.P = np.eye(2) * 0.1
        self.Q = np.eye(2) * 1e-4
        self._prev_vector: np.ndarray | None = None
        self._velocity: np.ndarray = np.zeros(2)
        self.mode = "NOMINAL"

    def reset(self) -> None:
        self.d_hat = np.zeros(2)
        self.P = np.eye(2) * 0.1
        self._prev_vector = None
        self._velocity = np.zeros(2)
        self.mode = "NOMINAL"

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        raw_vec, valid = fuse_vector_sensors(reading_a, reading_b)
        if not valid:
            return np.zeros(2), "ABSTAIN", raw_vec, False

        if self._prev_vector is not None:
            self._velocity = -(raw_vec - self._prev_vector) / 0.02
        self._prev_vector = raw_vec.copy()

        if self.mode == "ABSTAIN":
            return np.zeros(2), "ABSTAIN", raw_vec, False

        if step == 0 or np.linalg.norm(self.d_hat) == 0.0:
            self.d_hat = raw_vec.copy()

        # EKF Time update: d_{k+1} = d_k - v * dt
        self.d_hat = self.d_hat - self._velocity * 0.02
        self.P = self.P + self.Q

        # Vector measurement update
        R_vec = np.eye(2) * (reading_a.sigma**2 if reading_a.valid else 0.01)
        K_vec = self.P @ np.linalg.inv(self.P + R_vec)
        self.d_hat = self.d_hat + K_vec @ (raw_vec - self.d_hat)
        self.P = (np.eye(2) - K_vec) @ self.P

        # Range innovation consistency check
        if range_reading.valid:
            norm_est = float(np.linalg.norm(self.d_hat))
            H_range = self.d_hat / max(norm_est, 1e-6)
            S_range = float(H_range.T @ self.P @ H_range + range_reading.sigma**2)
            innov = norm_est - range_reading.distance
            norm_innov_sq = (innov**2) / max(S_range, 1e-8)

            if norm_innov_sq > self.gate_threshold:
                self.mode = "ABSTAIN"
                return np.zeros(2), "ABSTAIN", self.d_hat, False

        dist = float(np.linalg.norm(self.d_hat))
        if dist <= self.target_tolerance:
            return np.zeros(2), "STOP", self.d_hat, False

        u_dir = self.d_hat / max(dist, 1e-6)
        action = np.clip(u_dir * 0.50 - 0.20 * self._velocity, -1.0, 1.0)
        return action, "ACT", self.d_hat, False


# ---------------------------------------------------------------------------
# Baseline 4: AEGIS V4 Passive Geometric Verification
# ---------------------------------------------------------------------------
class AegisV4PassiveController:
    """Passive cross-modal geometric verification with safe abstention."""

    def __init__(self, target_tolerance: float = 0.22, geometric_threshold: float = 0.35):
        self.target_tolerance = target_tolerance
        self.geometric_threshold = geometric_threshold
        self._prev_vector: np.ndarray | None = None
        self._velocity: np.ndarray = np.zeros(2)
        self.mode = "NOMINAL"

    def reset(self) -> None:
        self._prev_vector = None
        self._velocity = np.zeros(2)
        self.mode = "NOMINAL"

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        raw_vec, valid = fuse_vector_sensors(reading_a, reading_b)
        if not valid:
            return np.zeros(2), "ABSTAIN", raw_vec, False

        if self._prev_vector is not None:
            self._velocity = -(raw_vec - self._prev_vector) / 0.02
        self._prev_vector = raw_vec.copy()

        if self.mode == "ABSTAIN":
            return np.zeros(2), "ABSTAIN", raw_vec, False

        # Geometric cross-modal verification check
        if range_reading.valid:
            residual = abs(float(np.linalg.norm(raw_vec)) - range_reading.distance)
            if residual > self.geometric_threshold:
                self.mode = "ABSTAIN"
                return np.zeros(2), "ABSTAIN", raw_vec, False

        dist = float(np.linalg.norm(raw_vec))
        if dist <= self.target_tolerance:
            return np.zeros(2), "STOP", raw_vec, False

        u_dir = raw_vec / max(dist, 1e-6)
        action = np.clip(u_dir * 0.50 - 0.20 * self._velocity, -1.0, 1.0)
        return action, "ACT", raw_vec, False


# ---------------------------------------------------------------------------
# Baseline 5: AEGIS V5 Online Huber Recalibration
# ---------------------------------------------------------------------------
class AegisV5HuberController:
    """V5 Huber recalibration with fixed 2-phase orthogonal probing."""

    def __init__(self, target_tolerance: float = 0.22, probing_steps: int = 32):
        self.target_tolerance = target_tolerance
        self.probing_steps = probing_steps
        self.estimator = OnlineBiasEstimator()
        self.mode = "NOMINAL"
        self.probing_count = 0
        self.active_bias = np.zeros(2)
        self._prev_vector: np.ndarray | None = None
        self._velocity: np.ndarray = np.zeros(2)

    def reset(self) -> None:
        self.estimator.clear()
        self.mode = "NOMINAL"
        self.probing_count = 0
        self.active_bias = np.zeros(2)
        self._prev_vector = None
        self._velocity = np.zeros(2)

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        raw_vec, valid = fuse_vector_sensors(reading_a, reading_b)
        if not valid:
            return np.zeros(2), "ABSTAIN", raw_vec, False

        if self._prev_vector is not None:
            self._velocity = -(raw_vec - self._prev_vector) / 0.02
        self._prev_vector = raw_vec.copy()

        # Check cross-modal residual
        cross_res = 0.0
        if range_reading.valid:
            cross_res = abs(float(np.linalg.norm(raw_vec - self.active_bias)) - range_reading.distance)

        if self.mode == "NOMINAL":
            if cross_res > 0.35:
                self.mode = "ACTIVE_PROBING"
                self.probing_count = 0
                self.estimator.clear()
            else:
                dist = float(np.linalg.norm(raw_vec))
                if dist <= self.target_tolerance:
                    return np.zeros(2), "STOP", raw_vec, False
                action = np.clip((raw_vec / max(dist, 1e-6)) * 0.50 - 0.20 * self._velocity, -1.0, 1.0)
                return action, "ACT", raw_vec, False

        if self.mode == "ACTIVE_PROBING":
            self.probing_count += 1
            if range_reading.valid:
                self.estimator.add_observation(raw_vec, range_reading.distance, True)

            norm_d = float(np.linalg.norm(raw_vec))
            direction = raw_vec / max(norm_d, 1e-6)
            ortho = np.array([-direction[1], direction[0]])

            # Fixed orthogonal 2-phase probing
            if self.probing_count <= self.probing_steps // 2:
                probe_dir = ortho
            else:
                probe_dir = direction

            action = np.clip(probe_dir * 0.70 - 0.20 * self._velocity, -1.0, 1.0)

            if self.probing_count >= self.probing_steps:
                cal_res = self.estimator.estimate(method="HUBER", enforce_observability_gate=True)
                if cal_res.status == "CALIBRATED":
                    self.active_bias = cal_res.bias.copy()
                    self.mode = "CALIBRATED"
                else:
                    self.mode = "ABSTAIN"
                    return np.zeros(2), "ABSTAIN", raw_vec, False

            return action, "PROBE", raw_vec, False

        if self.mode == "CALIBRATED":
            cal_vec = raw_vec - self.active_bias
            dist = float(np.linalg.norm(cal_vec))
            if cross_res > 0.45:
                self.mode = "ABSTAIN"
                return np.zeros(2), "ABSTAIN", cal_vec, False

            if dist <= self.target_tolerance:
                return np.zeros(2), "STOP", cal_vec, False

            action = np.clip((cal_vec / max(dist, 1e-6)) * 0.50 - 0.20 * self._velocity, -1.0, 1.0)
            return action, "ACT", cal_vec, False

        return np.zeros(2), "ABSTAIN", raw_vec, False


# ---------------------------------------------------------------------------
# Baseline 6: AEGIS V6 Discriminative Probing
# ---------------------------------------------------------------------------
class AegisV6DiscriminativeController:
    """Wrapper around existing V6 recovery controller."""

    def __init__(self):
        self.ctrl = AegisV6RecoveryController(
            strategy=ProbingStrategy.STRATEGY_F_DISCRIMINATIVE,
            enable_multi_hypothesis=True,
        )

    def reset(self) -> None:
        self.ctrl.reset()

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        raw_vec, valid = fuse_vector_sensors(reading_a, reading_b)
        verif_status = "VERIFIED"
        if range_reading.valid and valid:
            res = abs(float(np.linalg.norm(raw_vec)) - range_reading.distance)
            if res > 0.35:
                verif_status = "CROSS_MODAL_MISMATCH"

        action, dec, rep, cal_vec = self.ctrl.update(
            reading_a, reading_b, range_reading, verif_status, step
        )
        return action, dec, cal_vec, False


# ---------------------------------------------------------------------------
# Baseline 7: AEGIS V7 MPC Baseline
# ---------------------------------------------------------------------------
class AegisV7MPCBaselineController:
    """Wrapper around existing V7 recovery controller."""

    def __init__(self):
        self.ctrl = AegisV7RecoveryController(
            use_mpc=True,
            use_anchor=True,
            unconditional_anchor=False,
        )

    def reset(self) -> None:
        self.ctrl.reset()

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        raw_vec, valid = fuse_vector_sensors(reading_a, reading_b)
        verif_status = "VERIFIED"
        if range_reading.valid and valid:
            res = abs(float(np.linalg.norm(raw_vec)) - range_reading.distance)
            if res > 0.35:
                verif_status = "CROSS_MODAL_MISMATCH"

        action, dec, rep, cal_vec, query_anchor = self.ctrl.update(
            reading_a, reading_b, range_reading, anchor_reading, verif_status, step
        )
        return action, dec, cal_vec, query_anchor
