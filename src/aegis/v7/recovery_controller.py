"""
NEXVIA AEGIS V7.0 — Integrated Safe Recovery Controller.

Integrates:
- Risk-Constrained Model Predictive Control (receding horizon with terminal velocity penalty)
- Multi-Hypothesis Diagnosis Engine (H0–H6)
- Intermittent Independent Sensor Anchoring (AEGIS-Anchor)
- Event-triggered anchor scheduling and integrity verification gate
- Online Huber M-estimation and held-out cross-modal validation gates
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from aegis.calibration import CalibrationResult, OnlineBiasEstimator
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v6.diagnosis import MultiHypothesisDiagnosisEngine
from aegis.v6.hypothesis_models import DiagnosticReport, FaultHypothesis
from aegis.v7.anchor_scheduler import AnchorIntegrityGate, AnchorQueryScheduler, AnchorScheduleConfig
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v7.mpc_planner import RiskConstrainedMPCPlanner


@dataclass
class V7ControllerState:
    mode: str  # "NOMINAL", "ACTIVE_PROBING", "CALIBRATED", "ABSTAIN"
    probing_step_count: int
    active_bias: np.ndarray
    last_calibration: CalibrationResult | None
    last_report: DiagnosticReport | None
    consecutive_mismatches: int
    anchor_resolved_bias: bool
    total_anchor_queries: int


class AegisV7RecoveryController:
    """
    AEGIS V7.0 Integrated Recovery Controller.
    """

    def __init__(
        self,
        use_mpc: bool = True,
        use_anchor: bool = True,
        unconditional_anchor: bool = False,
        generic_fim_only: bool = False,
        fixed_probe_only: bool = False,
        enforce_observability_gate: bool = True,
        enforce_validation_gate: bool = True,
        enforce_terminal_braking: bool = True,
        probing_steps: int = 32,
        target_tolerance: float = 0.25,
        window_size: int = 35,
        min_samples: int = 6,
    ):
        self.use_mpc = use_mpc
        self.use_anchor = use_anchor
        self.unconditional_anchor = unconditional_anchor
        self.generic_fim_only = generic_fim_only
        self.fixed_probe_only = fixed_probe_only
        self.enforce_observability_gate = enforce_observability_gate
        self.enforce_validation_gate = enforce_validation_gate
        self.probing_steps = probing_steps
        self.target_tolerance = target_tolerance

        # Multi-hypothesis diagnosis
        self.diagnosis_engine = MultiHypothesisDiagnosisEngine(
            window_size=window_size,
            min_samples=min_samples,
        )

        # MPC Motion Planner
        w_term = 12.0 if enforce_terminal_braking else 0.0
        self.mpc_planner = RiskConstrainedMPCPlanner(
            horizon_steps=5,
            timestep=0.02,
            w_terminal_velocity=w_term,
        )

        # Anchor scheduler and integrity gate
        self.anchor_scheduler = AnchorQueryScheduler(
            config=AnchorScheduleConfig(
                entropy_threshold=0.95,
                consecutive_mismatches_threshold=2,
                max_queries_per_episode=5,
                consistency_tolerance=0.35,
            )
        )
        self.anchor_gate = AnchorIntegrityGate(consistency_tolerance=0.35)

        # Online Bias Estimator
        self.estimator = OnlineBiasEstimator(
            window_size=window_size,
            min_samples=min_samples,
        )

        self._validation_vectors: list[np.ndarray] = []
        self._validation_ranges: list[float] = []
        self._observed_vectors: list[np.ndarray] = []
        self._prev_raw_vector: np.ndarray | None = None
        self._prev_velocity: np.ndarray = np.zeros(2, dtype=np.float64)

        self.state = V7ControllerState(
            mode="NOMINAL",
            probing_step_count=0,
            active_bias=np.zeros(2, dtype=np.float64),
            last_calibration=None,
            last_report=None,
            consecutive_mismatches=0,
            anchor_resolved_bias=False,
            total_anchor_queries=0,
        )

    def reset(self) -> None:
        self.diagnosis_engine.clear()
        self.estimator.clear()
        self.mpc_planner.reset()
        self._validation_vectors.clear()
        self._validation_ranges.clear()
        self._observed_vectors.clear()
        self._prev_raw_vector = None
        self._prev_velocity = np.zeros(2, dtype=np.float64)

        self.state = V7ControllerState(
            mode="NOMINAL",
            probing_step_count=0,
            active_bias=np.zeros(2, dtype=np.float64),
            last_calibration=None,
            last_report=None,
            consecutive_mismatches=0,
            anchor_resolved_bias=False,
            total_anchor_queries=0,
        )

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None,
        verification_status: str,
        step: int,
        rng: np.random.Generator | None = None,
    ) -> tuple[np.ndarray, str, DiagnosticReport | None, np.ndarray, bool]:
        """
        Closed-loop V7 decision step.
        Returns:
            (force_action, decision_type, diagnostic_report, calibrated_vector, query_anchor_next)
        """
        if rng is None:
            rng = np.random.default_rng(42)

        # 1. Fuse best available vector reading
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

        # Fail-safe against complete vector sensor dropout
        if not has_valid_vector:
            return np.zeros(2, dtype=np.float64), "VERIFY", self.state.last_report, raw_vector, False

        # Add observation to diagnosis engine
        self.diagnosis_engine.add_observation(reading_a, reading_b, range_reading, step)
        self._observed_vectors.append(raw_vector.copy())

        # Determine whether to query the anchor
        query_anchor = False
        if self.use_anchor:
            query_anchor = self.anchor_scheduler.should_query(
                diagnostic_report=self.state.last_report,
                consecutive_mismatches=self.state.consecutive_mismatches,
                total_queries=self.state.total_anchor_queries,
                unconditional=self.unconditional_anchor,
            )
            if query_anchor:
                self.state.total_anchor_queries += 1

        # Process anchor observation if available
        if anchor_reading is not None and anchor_reading.valid and range_reading.valid:
            valid_anchor, code, inferred_b = self.anchor_gate.validate_anchor(
                anchor_reading, range_reading, raw_vector
            )
            if valid_anchor and inferred_b is not None:
                # Successfully broke common-mode ambiguity
                if np.linalg.norm(inferred_b) > 0.20:
                    self.state.active_bias = inferred_b.copy()
                    self.state.anchor_resolved_bias = True

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

            # Store baseline observation for estimation
            if range_reading.valid and has_valid_vector:
                self.estimator.add_observation(raw_vector, range_reading.distance, True)

            # Check arrival tolerance
            dist = float(np.linalg.norm(raw_vector))
            if dist <= self.target_tolerance:
                if range_reading.valid and range_reading.distance > 0.45:
                    return np.zeros(2, dtype=np.float64), "VERIFY", None, raw_vector, query_anchor
                return np.zeros(2, dtype=np.float64), "STOP", None, raw_vector, query_anchor

            if mismatch_present:
                return np.zeros(2, dtype=np.float64), "VERIFY", None, raw_vector, query_anchor

            # Motion control via MPC or proportional baseline
            if self.use_mpc:
                plan = self.mpc_planner.plan_approach_step(
                    current_pos=np.zeros(2),  # Target relative origin
                    current_vel=self._prev_velocity,
                    calibrated_target_vector=raw_vector,
                    target_tolerance=self.target_tolerance,
                )
                action = plan.action
            else:
                direction = raw_vector / max(dist, 1e-8)
                action = np.clip(direction - 0.20 * self._prev_velocity, -1.0, 1.0)

            return action, "ACT", None, raw_vector, query_anchor

        # -------------------------------------------------------------
        # STATE 2: ACTIVE_PROBING
        # -------------------------------------------------------------
        elif self.state.mode == "ACTIVE_PROBING":
            self.state.probing_step_count += 1

            if range_reading.valid and has_valid_vector:
                self.estimator.add_observation(raw_vector, range_reading.distance, True)
                if self.state.probing_step_count % 2 == 0:
                    self._validation_vectors.append(raw_vector.copy())
                    self._validation_ranges.append(float(range_reading.distance))

            # Run online multi-hypothesis diagnosis
            report = self.diagnosis_engine.diagnose()
            self.state.last_report = report

            # Plan probing action
            if self.use_mpc:
                plan = self.mpc_planner.plan_probing_step(
                    current_pos=np.zeros(2),
                    current_vel=self._prev_velocity,
                    target_relative_vector=raw_vector,
                    step_in_probing=self.state.probing_step_count,
                    diagnostic_report=report,
                    generic_fim_only=self.generic_fim_only,
                    fixed_probe_only=self.fixed_probe_only,
                )
                action = plan.action
            else:
                # V6 open-loop probing baseline
                norm_r = float(np.linalg.norm(raw_vector))
                r_unit = raw_vector / max(norm_r, 1e-6)
                ortho = np.array([-r_unit[1], r_unit[0]])
                cycle = (self.state.probing_step_count // 4) % 2
                sign = 1.0 if cycle == 0 else -1.0
                action = np.clip(sign * ortho * 0.70 - 0.20 * self._prev_velocity, -1.0, 1.0)

            # Check if probing completed
            if self.state.probing_step_count >= self.probing_steps:
                # If anchor broke common-mode symmetry, transition immediately to CALIBRATED
                if self.state.anchor_resolved_bias:
                    self.state.mode = "CALIBRATED"
                    self.state.consecutive_mismatches = 0
                    return action, "PROBE", report, raw_vector, False

                # If reference sensor is corrupted, DO NOT calibrate! Abstain!
                if report is not None and report.leading_hypothesis == FaultHypothesis.H3_REFERENCE_FAULT:
                    self.state.mode = "ABSTAIN"
                    return np.zeros(2, dtype=np.float64), "ABSTAIN", report, raw_vector, False

                # If dropout, zero spatial bias
                if report is not None and report.leading_hypothesis == FaultHypothesis.H5_SENSOR_DROPOUT:
                    self.state.mode = "CALIBRATED"
                    self.state.active_bias = np.zeros(2, dtype=np.float64)
                    return action, "PROBE", report, raw_vector, False

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

            return action, "PROBE", self.state.last_report, raw_vector, query_anchor

        # -------------------------------------------------------------
        # STATE 3: CALIBRATED
        # -------------------------------------------------------------
        elif self.state.mode == "CALIBRATED":
            calibrated_vector = raw_vector - self.state.active_bias
            calibrated_dist = float(np.linalg.norm(calibrated_vector))

            # Continuous cross-modal residual check
            if range_reading.valid:
                current_residual = abs(calibrated_dist - range_reading.distance)
                if current_residual > 0.45:
                    self.state.mode = "ABSTAIN"
                    return np.zeros(2, dtype=np.float64), "ABSTAIN", self.state.last_report, calibrated_vector, False

            # Target arrival check
            if calibrated_dist <= self.target_tolerance:
                if range_reading.valid and range_reading.distance > 0.45:
                    return np.zeros(2, dtype=np.float64), "VERIFY", self.state.last_report, calibrated_vector, False
                return np.zeros(2, dtype=np.float64), "STOP", self.state.last_report, calibrated_vector, False

            # Approach target under MPC
            if self.use_mpc:
                plan = self.mpc_planner.plan_approach_step(
                    current_pos=np.zeros(2),
                    current_vel=self._prev_velocity,
                    calibrated_target_vector=calibrated_vector,
                    target_tolerance=self.target_tolerance,
                )
                action = plan.action
            else:
                direction = calibrated_vector / max(calibrated_dist, 1e-8)
                action = np.clip(direction - 0.20 * self._prev_velocity, -1.0, 1.0)

            return action, "ACT", self.state.last_report, calibrated_vector, False

        # -------------------------------------------------------------
        # STATE 4: ABSTAIN
        # -------------------------------------------------------------
        elif self.state.mode == "ABSTAIN":
            return np.zeros(2, dtype=np.float64), "ABSTAIN", self.state.last_report, raw_vector, False

        return np.zeros(2, dtype=np.float64), "STOP", None, raw_vector, False
