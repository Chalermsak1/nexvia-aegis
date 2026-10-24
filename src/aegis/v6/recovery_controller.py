"""
NEXVIA AEGIS V6.0 — Integrated Active Recovery Controller.

Integrates:
- Multi-hypothesis diagnosis engine (H0–H6)
- Risk-constrained trajectory planner (Strategies A–F)
- Online bounded Huber bias estimation
- Held-out validation and observability qualification gates
- Finite-difference velocity damping and dropout fail-safes
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from aegis.calibration import CalibrationResult, OnlineBiasEstimator
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v6.diagnosis import MultiHypothesisDiagnosisEngine
from aegis.v6.hypothesis_models import DiagnosticReport, FaultHypothesis
from aegis.v6.trajectory_planner import ProbingStrategy, RiskConstrainedTrajectoryPlanner


@dataclass
class V6ControllerState:
    mode: str  # "NOMINAL", "FAULT_SUSPECTED", "ACTIVE_PROBING", "CALIBRATED", "ABSTAIN"
    probing_step_count: int
    active_bias: np.ndarray
    last_calibration: CalibrationResult | None
    last_report: DiagnosticReport | None
    consecutive_mismatches: int


class AegisV6RecoveryController:
    """
    AEGIS V6.0 Safe Recovery Controller.
    """

    def __init__(
        self,
        strategy: ProbingStrategy = ProbingStrategy.STRATEGY_F_DISCRIMINATIVE,
        enable_multi_hypothesis: bool = True,
        enforce_observability_gate: bool = True,
        enforce_validation_gate: bool = True,
        enforce_risk_constraints: bool = True,
        probing_steps: int = 32,
        probing_force: float = 0.85,
        target_tolerance: float = 0.22,
        window_size: int = 35,
        min_samples: int = 6,
    ):
        self.strategy = strategy
        self.enable_multi_hypothesis = enable_multi_hypothesis
        self.enforce_observability_gate = enforce_observability_gate
        self.enforce_validation_gate = enforce_validation_gate
        self.enforce_risk_constraints = enforce_risk_constraints
        self.probing_steps = probing_steps
        self.probing_force = probing_force
        self.target_tolerance = target_tolerance

        self.diagnosis_engine = MultiHypothesisDiagnosisEngine(
            window_size=window_size,
            min_samples=min_samples,
        )

        self.planner = RiskConstrainedTrajectoryPlanner(
            strategy=strategy,
            probing_force=probing_force,
            max_probing_steps=probing_steps,
        )

        self.estimator = OnlineBiasEstimator(
            window_size=window_size,
            min_samples=min_samples,
        )

        self._validation_vectors: list[np.ndarray] = []
        self._validation_ranges: list[float] = []
        self._observed_vectors: list[np.ndarray] = []
        self._prev_raw_vector: np.ndarray | None = None
        self._prev_velocity: np.ndarray = np.zeros(2, dtype=np.float64)

        self.state = V6ControllerState(
            mode="NOMINAL",
            probing_step_count=0,
            active_bias=np.zeros(2, dtype=np.float64),
            last_calibration=None,
            last_report=None,
            consecutive_mismatches=0,
        )

    def reset(self) -> None:
        self.diagnosis_engine.clear()
        self.estimator.clear()
        self._validation_vectors.clear()
        self._validation_ranges.clear()
        self._observed_vectors.clear()
        self._prev_raw_vector = None
        self._prev_velocity = np.zeros(2, dtype=np.float64)
        self.state = V6ControllerState(
            mode="NOMINAL",
            probing_step_count=0,
            active_bias=np.zeros(2, dtype=np.float64),
            last_calibration=None,
            last_report=None,
            consecutive_mismatches=0,
        )

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        verification_status: str,
        step: int,
        rng: np.random.Generator | None = None,
    ) -> tuple[np.ndarray, str, DiagnosticReport | None, np.ndarray]:
        """
        Processes measurements and executes the closed-loop V6 decision cycle.
        Returns:
            (force_action, decision_type, diagnostic_report, calibrated_vector)
        """
        if rng is None:
            rng = np.random.default_rng(42)

        # 1. Best available raw vector observation
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

        # Finite-difference velocity estimation
        if self._prev_raw_vector is not None and has_valid_vector:
            self._prev_velocity = -(raw_vector - self._prev_raw_vector) / 0.02
        self._prev_raw_vector = raw_vector.copy() if has_valid_vector else None

        # Fail-safe against total sensor blackout
        if not has_valid_vector:
            return np.zeros(2, dtype=np.float64), "VERIFY", self.state.last_report, raw_vector

        # Record observation in diagnosis engine
        self.diagnosis_engine.add_observation(reading_a, reading_b, range_reading, step)
        if has_valid_vector:
            self._observed_vectors.append(raw_vector.copy())

        # -------------------------------------------------------------
        # STATE 1: NOMINAL
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
                    self.state.mode = "ACTIVE_PROBING"
                    self.state.probing_step_count = 0
                    self.estimator.clear()
                    self._validation_vectors.clear()
                    self._validation_ranges.clear()
            else:
                self.state.consecutive_mismatches = 0

            # Store baseline observation
            if range_reading.valid and has_valid_vector:
                self.estimator.add_observation(raw_vector, range_reading.distance, True)

            # Check stopping distance
            dist = float(np.linalg.norm(raw_vector))
            if dist <= self.target_tolerance:
                # Require range sensor confirmation before stopping
                if range_reading.valid and range_reading.distance > 0.45:
                    return np.zeros(2, dtype=np.float64), "VERIFY", None, raw_vector
                return np.zeros(2, dtype=np.float64), "STOP", None, raw_vector

            if mismatch_present:
                return np.zeros(2, dtype=np.float64), "VERIFY", None, raw_vector

            direction = raw_vector / max(dist, 1e-8)
            action = direction - 0.20 * self._prev_velocity
            return np.clip(action, -1.0, 1.0), "ACT", None, raw_vector

        # -------------------------------------------------------------
        # STATE 2: ACTIVE_PROBING
        # -------------------------------------------------------------
        elif self.state.mode == "ACTIVE_PROBING":
            self.state.probing_step_count += 1

            # Accumulate observations
            if range_reading.valid and has_valid_vector:
                self.estimator.add_observation(raw_vector, range_reading.distance, True)
                if self.state.probing_step_count % 2 == 0:
                    self._validation_vectors.append(raw_vector.copy())
                    self._validation_ranges.append(float(range_reading.distance))

            # Run online multi-hypothesis diagnosis
            if self.enable_multi_hypothesis:
                report = self.diagnosis_engine.diagnose()
                self.state.last_report = report
            else:
                report = None

            # Plan trajectory action
            probe_action = self.planner.plan_action(
                step_in_probing=self.state.probing_step_count,
                base_vector=raw_vector,
                current_velocity=self._prev_velocity,
                diagnostic_report=report,
                observed_vectors=self._observed_vectors,
                rng=rng,
            )

            # Check if probing budget is reached
            if self.state.probing_step_count >= self.probing_steps:
                # If multi-hypothesis enabled, check leading diagnosis first
                if self.enable_multi_hypothesis and report is not None:
                    # If reference sensor is corrupted, DO NOT calibrate! Abstain!
                    if report.leading_hypothesis == FaultHypothesis.H3_REFERENCE_FAULT:
                        self.state.mode = "ABSTAIN"
                        return np.zeros(2, dtype=np.float64), "ABSTAIN", report, raw_vector

                    # If sensor dropout, no spatial bias to calibrate
                    if report.leading_hypothesis == FaultHypothesis.H5_SENSOR_DROPOUT:
                        self.state.mode = "CALIBRATED"
                        self.state.active_bias = np.zeros(2, dtype=np.float64)
                        return probe_action, "PROBE", report, raw_vector

                # Perform Huber Calibration
                cal_res = self.estimator.estimate(
                    method="HUBER",
                    enforce_observability_gate=self.enforce_observability_gate,
                )
                self.state.last_calibration = cal_res

                if cal_res.status == "CALIBRATED":
                    val_passed = True
                    if self.enforce_validation_gate and self._validation_vectors:
                        val_passed, _ = self.estimator.validate_candidate_bias(
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

            return probe_action, "PROBE", self.state.last_report, raw_vector

        # -------------------------------------------------------------
        # STATE 3: CALIBRATED (Execution with Bias Correction & Safeguards)
        # -------------------------------------------------------------
        elif self.state.mode == "CALIBRATED":
            calibrated_vector = raw_vector - self.state.active_bias
            calibrated_dist = float(np.linalg.norm(calibrated_vector))

            # Runtime continuous cross-modal residual monitor
            if range_reading.valid:
                current_residual = abs(calibrated_dist - range_reading.distance)
                if current_residual > 0.45:
                    self.state.mode = "ABSTAIN"
                    return np.zeros(2, dtype=np.float64), "ABSTAIN", self.state.last_report, calibrated_vector

            # Arrival check
            if calibrated_dist <= self.target_tolerance:
                if range_reading.valid and range_reading.distance > 0.45:
                    return np.zeros(2, dtype=np.float64), "VERIFY", self.state.last_report, calibrated_vector
                return np.zeros(2, dtype=np.float64), "STOP", self.state.last_report, calibrated_vector

            # Finite-difference velocity damped control
            f_dir = calibrated_vector / max(calibrated_dist, 1e-8)
            action = f_dir - 0.25 * self._prev_velocity
            return np.clip(action, -1.0, 1.0), "ACT", self.state.last_report, calibrated_vector

        # -------------------------------------------------------------
        # STATE 4: ABSTAIN
        # -------------------------------------------------------------
        else:
            return np.zeros(2, dtype=np.float64), "ABSTAIN", self.state.last_report, raw_vector
