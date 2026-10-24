"""
NEXVIA AEGIS-Next (V8) — Sequential Risk-Calibrated Runtime Assurance Controller.

Integrates:
1. Anytime-Valid Sequential Martingale Monitor (Testing by Betting, Ville's inequality bound).
2. Kinematic Velocity Profile Controller (resolving the V7 timeout and coasting overshoot paradox).
3. Martingale-Gated Event-Triggered Anchoring (conserving query costs while resolving H4).
4. Online Huber M-estimation with FIM observability and held-out validation gates.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from aegis.calibration import CalibrationResult, OnlineBiasEstimator
from aegis.next.martingale_monitor import AnytimeValidSequentialMonitor, MartingaleConfig
from aegis.next.velocity_controller import KinematicVelocityController, VelocityProfileConfig
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v6.diagnosis import MultiHypothesisDiagnosisEngine
from aegis.v6.hypothesis_models import DiagnosticReport, FaultHypothesis
from aegis.v7.anchor_scheduler import AnchorIntegrityGate
from aegis.v7.anchor_sensor import AnchorReading


@dataclass
class AegisNextState:
    mode: str  # "NOMINAL", "ACTIVE_PROBING", "CALIBRATED", "ABSTAIN"
    probing_step_count: int
    active_bias: np.ndarray
    last_calibration: CalibrationResult | None
    last_report: DiagnosticReport | None
    total_anchor_queries: int
    anchor_resolved_bias: bool
    martingale_wealth: float
    anytime_p_value: float


class AegisNextController:
    """
    AEGIS-Next (V8) Integrated Controller.
    """

    def __init__(
        self,
        target_tolerance: float = 0.22,
        probing_steps: int = 32,
        alpha: float = 0.05,
        max_anchor_queries: int = 5,
        use_anchor: bool = True,
    ):
        self.target_tolerance = target_tolerance
        self.probing_steps = probing_steps
        self.alpha = alpha
        self.max_anchor_queries = max_anchor_queries
        self.use_anchor = use_anchor

        # Statistical Risk Monitor: nominal mean = 0.065m (conservative folded normal threshold)
        self.martingale_monitor = AnytimeValidSequentialMonitor(
            config=MartingaleConfig(alpha=alpha, nominal_mean=0.065, scale_vmax=0.40)
        )
        self.calibrated_martingale = AnytimeValidSequentialMonitor(
            config=MartingaleConfig(alpha=alpha, nominal_mean=0.065, scale_vmax=0.40)
        )

        # Dynamic Velocity Controller
        self.motion_controller = KinematicVelocityController(
            config=VelocityProfileConfig(arrival_tolerance=target_tolerance)
        )

        # Multi-Hypothesis Diagnosis
        self.diagnosis_engine = MultiHypothesisDiagnosisEngine()

        # Online Bias Estimator
        self.estimator = OnlineBiasEstimator()

        # Anchor Integrity Gate
        self.anchor_gate = AnchorIntegrityGate(consistency_tolerance=0.35)

        self._validation_vectors: list[np.ndarray] = []
        self._validation_ranges: list[float] = []
        self._prev_vector: np.ndarray | None = None
        self._velocity: np.ndarray = np.zeros(2, dtype=np.float64)

        self.state = AegisNextState(
            mode="NOMINAL",
            probing_step_count=0,
            active_bias=np.zeros(2, dtype=np.float64),
            last_calibration=None,
            last_report=None,
            total_anchor_queries=0,
            anchor_resolved_bias=False,
            martingale_wealth=1.0,
            anytime_p_value=1.0,
        )

    def reset(self) -> None:
        self.martingale_monitor.reset()
        self.calibrated_martingale.reset()
        self.diagnosis_engine.clear()
        self.estimator.clear()
        self._validation_vectors.clear()
        self._validation_ranges.clear()
        self._prev_vector = None
        self._velocity = np.zeros(2, dtype=np.float64)

        self.state = AegisNextState(
            mode="NOMINAL",
            probing_step_count=0,
            active_bias=np.zeros(2, dtype=np.float64),
            last_calibration=None,
            last_report=None,
            total_anchor_queries=0,
            anchor_resolved_bias=False,
            martingale_wealth=1.0,
            anytime_p_value=1.0,
        )

    def update(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        anchor_reading: AnchorReading | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, str, np.ndarray, bool]:
        """
        Executes one closed-loop AEGIS-Next decision step.
        Returns:
            (force_action, decision_type, calibrated_vector, query_anchor_next)
        """
        # 1. Inverse-variance vector fusion
        if reading_a.valid and reading_b.valid:
            w_a = 1.0 / max(reading_a.sigma**2, 1e-8)
            w_b = 1.0 / max(reading_b.sigma**2, 1e-8)
            raw_vector = (w_a * reading_a.estimate + w_b * reading_b.estimate) / (w_a + w_b)
            has_vector = True
        elif reading_a.valid:
            raw_vector = reading_a.estimate.copy()
            has_vector = True
        elif reading_b.valid:
            raw_vector = reading_b.estimate.copy()
            has_vector = True
        else:
            raw_vector = np.zeros(2, dtype=np.float64)
            has_vector = False

        if not has_vector:
            # Complete vector dropout
            return np.zeros(2), "ABSTAIN", raw_vector, False

        # EMA-filtered velocity estimation (robust to high-frequency sensor noise)
        if self._prev_vector is not None:
            raw_v = -(raw_vector - self._prev_vector) / 0.02
            self._velocity = 0.80 * self._velocity + 0.20 * raw_v
        self._prev_vector = raw_vector.copy()

        # Update diagnostic engine
        self.diagnosis_engine.add_observation(reading_a, reading_b, range_reading, step)

        # 2. Compute cross-modal residual and update Sequential Martingale
        cross_res = 0.0
        is_alarm = False
        if range_reading.valid:
            cross_res = abs(float(np.linalg.norm(raw_vector)) - range_reading.distance)
            wealth, p_val, is_alarm = self.martingale_monitor.update(cross_res)
            self.state.martingale_wealth = wealth
            self.state.anytime_p_value = p_val

        # 3. Process incoming anchor observation if available
        if anchor_reading is not None and anchor_reading.valid and range_reading.valid:
            valid_anchor, code, inferred_b = self.anchor_gate.validate_anchor(
                anchor_reading, range_reading, raw_vector
            )
            if valid_anchor and inferred_b is not None:
                if np.linalg.norm(inferred_b) > 0.20:
                    self.state.active_bias = inferred_b.copy()
                    self.state.anchor_resolved_bias = True
                    self.state.mode = "CALIBRATED"
                    self.calibrated_martingale.reset()

        # -------------------------------------------------------------
        # STATE 1: NOMINAL
        # -------------------------------------------------------------
        if self.state.mode == "NOMINAL":
            # If martingale triggers certified alarm, transition to active probing
            if is_alarm or cross_res > 0.35:
                self.state.mode = "ACTIVE_PROBING"
                self.state.probing_step_count = 0
                self.estimator.clear()
                self._validation_vectors.clear()
                self._validation_ranges.clear()

            # Store baseline data for estimation
            if range_reading.valid:
                self.estimator.add_observation(raw_vector, range_reading.distance, True)

            # Plan approach via kinematically optimal velocity controller
            action, arrived = self.motion_controller.plan_approach_action(raw_vector, self._velocity)
            if arrived:
                # Target arrival reached: verify range consistency before STOP
                if range_reading.valid and range_reading.distance > 0.45:
                    return np.zeros(2), "VERIFY", raw_vector, False
                return np.zeros(2), "STOP", raw_vector, False

            return action, "ACT", raw_vector, False

        # -------------------------------------------------------------
        # STATE 2: ACTIVE_PROBING
        # -------------------------------------------------------------
        elif self.state.mode == "ACTIVE_PROBING":
            self.state.probing_step_count += 1
            if range_reading.valid:
                self.estimator.add_observation(raw_vector, range_reading.distance, True)
                if self.state.probing_step_count % 2 == 0:
                    self._validation_vectors.append(raw_vector.copy())
                    self._validation_ranges.append(float(range_reading.distance))

            report = self.diagnosis_engine.diagnose()
            self.state.last_report = report

            # Event-Triggered Anchor Scheduling during probing
            query_anchor_next = False
            if self.use_anchor and self.state.total_anchor_queries < self.max_anchor_queries:
                is_h4 = report is not None and report.leading_hypothesis == FaultHypothesis.H4_CORRELATED_BIAS
                is_ambig = report is not None and report.entropy > 0.95
                if (is_h4 or is_ambig or cross_res > 0.40) and self.state.probing_step_count in (4, 12, 20):
                    query_anchor_next = True
                    self.state.total_anchor_queries += 1

            action = self.motion_controller.plan_probing_action(
                raw_vector, self._velocity, self.state.probing_step_count, self.probing_steps
            )

            # Check if probing budget complete
            if self.state.probing_step_count >= self.probing_steps:
                if self.state.anchor_resolved_bias:
                    self.state.mode = "CALIBRATED"
                    self.calibrated_martingale.reset()
                    return action, "PROBE", raw_vector, False

                # If reference range sensor is corrupted (H3), do NOT calibrate against it: ABSTAIN!
                if report is not None and report.leading_hypothesis == FaultHypothesis.H3_REFERENCE_FAULT:
                    self.state.mode = "ABSTAIN"
                    return np.zeros(2), "ABSTAIN", raw_vector, False

                # If dropout (H5), reset active bias
                if report is not None and report.leading_hypothesis == FaultHypothesis.H5_SENSOR_DROPOUT:
                    self.state.mode = "CALIBRATED"
                    self.state.active_bias = np.zeros(2)
                    self.calibrated_martingale.reset()
                    return action, "PROBE", raw_vector, False

                # Huber M-Estimation with FIM observability gating
                cal_res = self.estimator.estimate(method="HUBER", enforce_observability_gate=True)
                self.state.last_calibration = cal_res

                if cal_res.status == "CALIBRATED":
                    val_passed = True
                    if self._validation_vectors:
                        val_passed, _ = self.estimator.validate_candidate_bias(
                            cal_res.bias, self._validation_vectors, self._validation_ranges
                        )
                    if val_passed:
                        self.state.mode = "CALIBRATED"
                        self.state.active_bias = cal_res.bias.copy()
                        self.calibrated_martingale.reset()
                    else:
                        self.state.mode = "ABSTAIN"
                        return np.zeros(2), "ABSTAIN", raw_vector, False
                else:
                    self.state.mode = "ABSTAIN"
                    return np.zeros(2), "ABSTAIN", raw_vector, False

            return action, "PROBE", raw_vector, query_anchor_next

        # -------------------------------------------------------------
        # STATE 3: CALIBRATED
        # -------------------------------------------------------------
        elif self.state.mode == "CALIBRATED":
            cal_vector = raw_vector - self.state.active_bias
            dist = float(np.linalg.norm(cal_vector))

            # Monitor post-calibration residual with secondary martingale
            if range_reading.valid:
                post_res = abs(dist - range_reading.distance)
                c_wealth, _, c_alarm = self.calibrated_martingale.update(post_res)
                if c_alarm or post_res > 0.45:
                    # Calibration invalidated (e.g. non-stationary drift or incorrect bias): ABSTAIN!
                    self.state.mode = "ABSTAIN"
                    return np.zeros(2), "ABSTAIN", cal_vector, False

            action, arrived = self.motion_controller.plan_approach_action(cal_vector, self._velocity)
            if arrived:
                if range_reading.valid and range_reading.distance > 0.45:
                    return np.zeros(2), "VERIFY", cal_vector, False
                return np.zeros(2), "STOP", cal_vector, False

            return action, "ACT", cal_vector, False

        # -------------------------------------------------------------
        # STATE 4: ABSTAIN
        # -------------------------------------------------------------
        return np.zeros(2), "ABSTAIN", raw_vector, False
