from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from aegis.calibration import CalibrationResult, OnlineBiasEstimator
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading


@dataclass
class ControllerState:
    mode: str  # "NOMINAL", "PROBING", "CALIBRATED", "ABSTAIN"
    probing_step_count: int
    active_bias: np.ndarray
    last_calibration: CalibrationResult | None
    consecutive_mismatches: int


class SafeRecoveryController:
    """
    AEGIS V5.0 Safe Recovery Controller.

    Integrates:
    - Fault/mismatch detection from verification status.
    - Active orthogonal probing trajectory to guarantee geometric diversity.
    - Online bias estimation (OLS or Huber).
    - Observability qualification gate (Fisher information condition number).
    - Independent temporal/held-out validation gate.
    - Safe execution with calibrated vector estimates or conservative abstention.
    """

    def __init__(
        self,
        estimation_method: str = "HUBER",
        enforce_observability: bool = True,
        enforce_validation: bool = True,
        probing_steps: int = 32,
        probing_force: float = 0.9,
        target_tolerance: float = 0.22,
        window_size: int = 35,
        min_samples: int = 6,
    ):
        self.estimation_method = estimation_method
        self.enforce_observability = enforce_observability
        self.enforce_validation = enforce_validation
        self.probing_steps = probing_steps
        self.probing_force = probing_force
        self.target_tolerance = target_tolerance

        self.estimator = OnlineBiasEstimator(
            window_size=window_size,
            min_samples=min_samples,
        )

        self._validation_vectors: list[np.ndarray] = []
        self._validation_ranges: list[float] = []
        self._prev_raw_vector: np.ndarray | None = None

        self.state = ControllerState(
            mode="NOMINAL",
            probing_step_count=0,
            active_bias=np.zeros(2, dtype=np.float64),
            last_calibration=None,
            consecutive_mismatches=0,
        )

    def reset(self) -> None:
        self.estimator.clear()
        self._validation_vectors.clear()
        self._validation_ranges.clear()
        self._prev_raw_vector = None
        self.state = ControllerState(
            mode="NOMINAL",
            probing_step_count=0,
            active_bias=np.zeros(2, dtype=np.float64),
            last_calibration=None,
            consecutive_mismatches=0,
        )

    def _orthogonal_probing_force(self, base_vector: np.ndarray, step: int) -> np.ndarray:
        """
        Generates an active two-phase orthogonal probing trajectory:
        Phase 1: Lateral excitation to break collinearity and ensure non-zero lambda_min.
        Phase 2: Longitudinal excitation and lateral deceleration to maintain forward momentum.
        """
        norm = float(np.linalg.norm(base_vector))
        if norm <= 1e-6:
            return np.array([self.probing_force, 0.0], dtype=np.float64)

        forward = base_vector / norm
        ortho = np.array([-forward[1], forward[0]])

        half = self.probing_steps // 2
        if step < half:
            probe_vec = self.probing_force * ortho + 0.35 * self.probing_force * forward
        else:
            probe_vec = -0.5 * self.probing_force * ortho + self.probing_force * forward

        return np.clip(probe_vec, -1.0, 1.0)

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        verification_status: str,
        step: int,
    ) -> tuple[np.ndarray, str, CalibrationResult | None, np.ndarray]:
        """
        Processes measurements and returns:
            (force_action, decision_type, calibration_result, calibrated_vector)
        """
        # Determine current best raw vector observation
        has_valid_vector = reading_a.valid or reading_b.valid
        if reading_a.valid and reading_b.valid:
            w_a = 1.0 / max(reading_a.sigma**2, 1e-8)
            w_b = 1.0 / max(reading_b.sigma**2, 1e-8)
            raw_vector = (w_a * reading_a.estimate + w_b * reading_b.estimate) / (w_a + w_b)
        elif reading_a.valid:
            raw_vector = reading_a.estimate.copy()
        elif reading_b.valid:
            raw_vector = reading_b.estimate.copy()
        else:
            raw_vector = np.zeros(2, dtype=np.float64)

        # Fail-safe against complete sensor dropout: never declare STOP when sensors are invalid
        if not has_valid_vector:
            return np.zeros(2, dtype=np.float64), "VERIFY", self.state.last_calibration, raw_vector

        # -------------------------------------------------------------
        # 1. State: NOMINAL
        # -------------------------------------------------------------
        if self.state.mode == "NOMINAL":
            mismatch_present = verification_status in (
                "CROSS_MODAL_MISMATCH",
                "MULTI_MODAL_MISMATCH",
                "SENSOR_MISMATCH",
            )

            if mismatch_present:
                self.state.consecutive_mismatches += 1
                if self.state.consecutive_mismatches >= 2:
                    self.state.mode = "PROBING"
                    self.state.probing_step_count = 0
                    self.estimator.clear()
                    self._validation_vectors.clear()
                    self._validation_ranges.clear()
            else:
                self.state.consecutive_mismatches = 0

            # Under nominal mode, record observation into window
            if range_reading.valid:
                self.estimator.add_observation(raw_vector, range_reading.distance, True)

            # Check stopping distance
            dist = float(np.linalg.norm(raw_vector))
            if dist <= self.target_tolerance:
                if range_reading.valid and range_reading.distance > 0.45:
                    return np.zeros(2, dtype=np.float64), "VERIFY", None, raw_vector
                return np.zeros(2, dtype=np.float64), "STOP", None, raw_vector

            if mismatch_present:
                return np.zeros(2, dtype=np.float64), "VERIFY", None, raw_vector

            direction = raw_vector / max(dist, 1e-8)
            return direction, "ACT", None, raw_vector

        # -------------------------------------------------------------
        # 2. State: PROBING (Collecting geometrically observable window)
        # -------------------------------------------------------------
        elif self.state.mode == "PROBING":
            self.state.probing_step_count += 1

            # Store observation
            if range_reading.valid and has_valid_vector:
                self.estimator.add_observation(raw_vector, range_reading.distance, True)
                if self.state.probing_step_count % 2 == 0:
                    self._validation_vectors.append(raw_vector.copy())
                    self._validation_ranges.append(float(range_reading.distance))

            probe_action = self._orthogonal_probing_force(raw_vector, self.state.probing_step_count)

            # Check if probing phase is complete
            if self.state.probing_step_count >= self.probing_steps:
                cal_res = self.estimator.estimate(
                    method=self.estimation_method,
                    enforce_observability_gate=self.enforce_observability,
                )
                self.state.last_calibration = cal_res

                if cal_res.status == "CALIBRATED":
                    val_passed = True
                    if self.enforce_validation and self._validation_vectors:
                        val_passed, val_rmse = self.estimator.validate_candidate_bias(
                            cal_res.bias, self._validation_vectors, self._validation_ranges
                        )

                    if val_passed:
                        self.state.mode = "CALIBRATED"
                        self.state.active_bias = cal_res.bias.copy()
                        self.state.consecutive_mismatches = 0
                    else:
                        self.state.mode = "ABSTAIN"
                else:
                    self.state.mode = "ABSTAIN"

            return probe_action, "PROBE", self.state.last_calibration, raw_vector

        # -------------------------------------------------------------
        # 3. State: CALIBRATED (Executing with certified bias correction)
        # -------------------------------------------------------------
        elif self.state.mode == "CALIBRATED":
            calibrated_vector = raw_vector - self.state.active_bias
            calibrated_dist = float(np.linalg.norm(calibrated_vector))

            # Monitor ongoing cross-modal residual
            if range_reading.valid:
                current_residual = abs(calibrated_dist - range_reading.distance)
                if current_residual > 0.45:
                    self.state.mode = "ABSTAIN"
                    return np.zeros(2, dtype=np.float64), "ABSTAIN", self.state.last_calibration, calibrated_vector

            if calibrated_dist <= self.target_tolerance:
                if range_reading.valid and range_reading.distance > 0.45:
                    return np.zeros(2, dtype=np.float64), "VERIFY", self.state.last_calibration, calibrated_vector
                return np.zeros(2, dtype=np.float64), "STOP", self.state.last_calibration, calibrated_vector

            # Finite-difference velocity estimation for PD damping
            if self._prev_raw_vector is not None:
                v_est = -(raw_vector - self._prev_raw_vector) / 0.02
            else:
                v_est = np.zeros(2, dtype=np.float64)
            self._prev_raw_vector = raw_vector.copy()

            f_dir = calibrated_vector / max(calibrated_dist, 1e-8)
            action = f_dir - 0.25 * v_est
            action = np.clip(action, -1.0, 1.0)
            return action, "ACT", self.state.last_calibration, calibrated_vector

        # -------------------------------------------------------------
        # 4. State: ABSTAIN (Safe Hold)
        # -------------------------------------------------------------
        else:
            return np.zeros(2, dtype=np.float64), "ABSTAIN", self.state.last_calibration, raw_vector
