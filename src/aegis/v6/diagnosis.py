"""
NEXVIA AEGIS V6.0 — Multi-Hypothesis Sensor Diagnosis Engine.

Maintains competing explanations for sensor inconsistencies, evaluates Bayesian
likelihoods from cross-modal and odometric evidence, computes diagnostic entropy,
and guards against false calibration attribution.
"""

from __future__ import annotations

import numpy as np

from aegis.calibration import OnlineBiasEstimator
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v6.hypothesis_models import (
    DiagnosticReport,
    FaultHypothesis,
    HypothesisEvidence,
    HypothesisScore,
    compute_fisher_information,
)


class MultiHypothesisDiagnosisEngine:
    """
    AEGIS V6.0 Multi-Hypothesis Diagnosis Engine.

    Continuously monitors dual vector sensors and scalar range reference,
    scoring 7 candidate hypotheses (H0–H6) to determine the root cause of
    sensor discrepancies without ground truth leakage.
    """

    def __init__(
        self,
        window_size: int = 35,
        min_samples: int = 6,
        nominal_threshold: float = 0.25,
        entropy_threshold: float = 1.45,
    ):
        self.window_size = window_size
        self.min_samples = min_samples
        self.nominal_threshold = nominal_threshold
        self.entropy_threshold = entropy_threshold

        self.estimator = OnlineBiasEstimator(
            window_size=window_size,
            min_samples=min_samples,
        )

        self._vec_a_history: list[np.ndarray] = []
        self._vec_b_history: list[np.ndarray] = []
        self._range_history: list[float] = []
        self._step_history: list[int] = []
        self._valid_a_history: list[bool] = []
        self._valid_b_history: list[bool] = []
        self._valid_r_history: list[bool] = []

    def clear(self) -> None:
        """Resets all observation buffers and the internal estimator."""
        self.estimator.clear()
        self._vec_a_history.clear()
        self._vec_b_history.clear()
        self._range_history.clear()
        self._step_history.clear()
        self._valid_a_history.clear()
        self._valid_b_history.clear()
        self._valid_r_history.clear()

    def add_observation(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        reading_range: RangeReading,
        step: int,
    ) -> None:
        """Records synchronized measurements into receding history."""
        self._vec_a_history.append(reading_a.estimate.copy() if reading_a.valid else np.zeros(2))
        self._vec_b_history.append(reading_b.estimate.copy() if reading_b.valid else np.zeros(2))
        self._range_history.append(float(reading_range.distance) if reading_range.valid else 0.0)
        self._step_history.append(step)

        self._valid_a_history.append(bool(reading_a.valid))
        self._valid_b_history.append(bool(reading_b.valid))
        self._valid_r_history.append(bool(reading_range.valid))

        # Forward valid readings to bias estimator
        if reading_a.valid and reading_range.valid:
            self.estimator.add_observation(reading_a.estimate, reading_range.distance, True)

        # Enforce maximum buffer length
        if len(self._step_history) > self.window_size * 2:
            self._vec_a_history.pop(0)
            self._vec_b_history.pop(0)
            self._range_history.pop(0)
            self._step_history.pop(0)
            self._valid_a_history.pop(0)
            self._valid_b_history.pop(0)
            self._valid_r_history.pop(0)

    def diagnose(self) -> DiagnosticReport:
        """
        Evaluates the current evidence window and computes the full diagnostic report.
        """
        n_samples = len(self._step_history)
        zero_bias = np.zeros(2, dtype=np.float64)

        # Case 1: Insufficient history
        if n_samples < self.min_samples:
            return DiagnosticReport(
                leading_hypothesis=FaultHypothesis.H6_AMBIGUOUS,
                scores={h: HypothesisScore(h, 0.0, 1.0 / 7, 0.0, "Insufficient samples") for h in FaultHypothesis},
                probabilities={h.value: 1.0 / 7 for h in FaultHypothesis},
                entropy=float(np.log(7)),
                is_ambiguous=True,
                can_recalibrate=False,
                estimated_bias=zero_bias,
                reason_code="INSUFFICIENT_WINDOW",
            )

        # Extract recent active window
        w_len = min(n_samples, self.window_size)
        vec_a_w = self._vec_a_history[-w_len:]
        vec_b_w = self._vec_b_history[-w_len:]
        rng_w = self._range_history[-w_len:]
        steps_w = self._step_history[-w_len:]
        val_a_w = self._valid_a_history[-w_len:]
        val_b_w = self._valid_b_history[-w_len:]
        val_r_w = self._valid_r_history[-w_len:]

        # Dropout fraction
        drop_a = 1.0 - (sum(val_a_w) / w_len)
        drop_b = 1.0 - (sum(val_b_w) / w_len)
        drop_r = 1.0 - (sum(val_r_w) / w_len)
        max_dropout = max(drop_a, drop_b, drop_r)

        # Valid pairs for geometric checks
        valid_indices = [i for i in range(w_len) if val_a_w[i] and val_r_w[i]]
        if len(valid_indices) < self.min_samples:
            # High dropout dominance
            prob_dict = {h.value: 0.05 for h in FaultHypothesis}
            prob_dict[FaultHypothesis.H5_SENSOR_DROPOUT.value] = 0.70
            return DiagnosticReport(
                leading_hypothesis=FaultHypothesis.H5_SENSOR_DROPOUT,
                scores={},
                probabilities=prob_dict,
                entropy=1.0,
                is_ambiguous=False,
                can_recalibrate=False,
                estimated_bias=zero_bias,
                reason_code="SENSOR_DROPOUT_DETECTED",
            )

        # Compute empirical discrepancies on valid frames
        vec_a_valid = [vec_a_w[i] for i in valid_indices]
        vec_b_valid = [vec_b_w[i] for i in valid_indices if val_b_w[i]]
        rng_valid = [rng_w[i] for i in valid_indices]
        steps_valid = [steps_w[i] for i in valid_indices]

        # 1. Vector sensor mutual disagreement
        if len(vec_b_valid) == len(vec_a_valid):
            disagreements = [float(np.linalg.norm(vec_a_valid[i] - vec_b_valid[i])) for i in range(len(vec_a_valid))]
            vec_disagreement = float(np.mean(disagreements))
        else:
            vec_disagreement = 0.8  # One sensor dropped out or mismatched length

        # 2. Cross-modal nominal residual (assuming b = 0)
        nom_residuals = [abs(float(np.linalg.norm(vec_a_valid[i])) - rng_valid[i]) for i in range(len(vec_a_valid))]
        mean_nom_residual = float(np.mean(nom_residuals))

        # 3. Fit optimal Huber bias using estimator
        cal_res = self.estimator.estimate(method="HUBER", enforce_observability_gate=False)
        estimated_bias = cal_res.bias if cal_res.status == "CALIBRATED" else zero_bias
        bias_norm = float(np.linalg.norm(estimated_bias))

        # Compute post-calibration residual
        cal_residuals = [abs(float(np.linalg.norm(vec_a_valid[i] - estimated_bias)) - rng_valid[i]) for i in range(len(vec_a_valid))]
        mean_cal_residual = float(np.mean(cal_residuals))

        # 4. Range discrepancy standard deviation across spatial positions
        # (For range bias r = ||d|| + beta, ||z|| - r = -beta = constant, so std is low!)
        signed_discrepancies = [float(np.linalg.norm(vec_a_valid[i])) - rng_valid[i] for i in range(len(vec_a_valid))]
        discrepancy_std = float(np.std(signed_discrepancies))

        # 5. Residual temporal drift slope:
        # True drift produces a systematic temporal slope in post-calibration residuals,
        # whereas a constant bias has flat near-zero post-calibration residuals.
        if len(steps_valid) >= 6 and (steps_valid[-1] - steps_valid[0]) > 0:
            time_norm = np.array(steps_valid, dtype=np.float64) - steps_valid[0]
            slope, _ = np.polyfit(time_norm, cal_residuals, 1)
            residual_slope = float(abs(slope))
        else:
            residual_slope = 0.0

        # 6. Fisher Information Matrix
        _, lambda_min, cond_num = compute_fisher_information(vec_a_valid, estimated_bias)

        evidence = HypothesisEvidence(
            window_length=len(valid_indices),
            vector_disagreement=vec_disagreement,
            nominal_residual=mean_nom_residual,
            bias_fit_residual=mean_cal_residual,
            range_discrepancy_std=discrepancy_std,
            residual_temporal_slope=residual_slope,
            fim_min_eigenvalue=lambda_min,
            fim_condition_number=cond_num,
            dropout_fraction=max_dropout,
            best_estimated_bias=estimated_bias.copy(),
        )

        # -------------------------------------------------------------
        # Log-Likelihood Scoring for Competing Hypotheses
        # -------------------------------------------------------------
        log_liks: dict[FaultHypothesis, float] = {}

        # H0: Nominal
        # Requires low nominal residual, low vector disagreement, low dropout
        log_liks[FaultHypothesis.H0_NOMINAL] = -(
            (mean_nom_residual / 0.15) ** 2
            + (vec_disagreement / 0.15) ** 2
            + (max_dropout / 0.05) ** 2
        )

        # H1: Constant Vector Bias
        # Requires high nominal residual, low calibrated residual, significant bias norm,
        # vector disagreement (primary biased, secondary nominal), stable residual slope
        is_bias_separable = (vec_disagreement > 0.35) or (discrepancy_std > 0.12)
        log_liks[FaultHypothesis.H1_VECTOR_BIAS] = -(
            (mean_cal_residual / 0.15) ** 2
            + (max(0.0, 0.40 - bias_norm) / 0.20) ** 2
            + (0.0 if is_bias_separable else 4.0)
            + (residual_slope / 0.003) ** 2
        )

        # H2: Vector Drift
        # Requires non-zero temporal slope and increasing residual over time
        log_liks[FaultHypothesis.H2_VECTOR_DRIFT] = -(
            (max(0.0, 0.003 - residual_slope) / 0.002) ** 2
            + (mean_cal_residual / 0.25) ** 2
        )

        # H3: Reference Sensor Fault (Range Bias)
        # Vector sensors agree with each other (low disagreement), but both disagree
        # with range sensor by constant offset (low discrepancy_std, high mean_nom_residual)
        is_ref_fault_pattern = (vec_disagreement < 0.25) and (mean_nom_residual > 0.45) and (discrepancy_std < 0.14)
        log_liks[FaultHypothesis.H3_REFERENCE_FAULT] = -(
            (vec_disagreement / 0.15) ** 2
            + (discrepancy_std / 0.10) ** 2
            + (0.0 if is_ref_fault_pattern else 6.0)
        )

        # H4: Correlated / Common-mode Vector Bias
        # Vector sensors agree with each other, but disagree with range sensor,
        # AND discrepancy changes across heading (discrepancy_std > 0.15)
        is_correlated_pattern = (vec_disagreement < 0.25) and (mean_nom_residual > 0.45) and (discrepancy_std >= 0.14)
        log_liks[FaultHypothesis.H4_CORRELATED_BIAS] = -(
            (vec_disagreement / 0.15) ** 2
            + (mean_cal_residual / 0.20) ** 2
            + (0.0 if is_correlated_pattern else 6.0)
        )

        # H5: Sensor Dropout
        log_liks[FaultHypothesis.H5_SENSOR_DROPOUT] = -(
            (max(0.0, 0.15 - max_dropout) / 0.05) ** 2
        )

        # H6: Ambiguous / Poor Observability
        # Poor FIM conditioning or collinear motion
        is_poor_obs = (lambda_min < 0.0005) or (cond_num > 10000.0)
        log_liks[FaultHypothesis.H6_AMBIGUOUS] = -(
            0.0 if is_poor_obs else 8.0
        )

        # Normalize via Softmax
        max_ll = max(log_liks.values())
        exp_ll = {h: np.exp(ll - max_ll) for h, ll in log_liks.items()}
        sum_exp = sum(exp_ll.values())
        probabilities = {h: float(exp_ll[h] / sum_exp) for h in FaultHypothesis}

        # Shannon Entropy
        entropy = float(-sum(p * np.log(max(p, 1e-12)) for p in probabilities.values()))

        # Determine leading hypothesis
        leading_h = max(probabilities.keys(), key=lambda h: probabilities[h])
        leading_prob = probabilities[leading_h]

        is_ambiguous = (entropy > self.entropy_threshold) or (leading_prob < 0.40) or (leading_h == FaultHypothesis.H6_AMBIGUOUS)

        # Decision on recalibration eligibility
        can_recalibrate = False
        reason_code = "UNKNOWN"

        if leading_h == FaultHypothesis.H0_NOMINAL:
            reason_code = "NOMINAL_STABLE"
            can_recalibrate = False
        elif leading_h == FaultHypothesis.H1_VECTOR_BIAS:
            if not is_ambiguous and lambda_min >= 0.0005 and cond_num <= 15000:
                can_recalibrate = True
                reason_code = "VECTOR_BIAS_IDENTIFIED"
            else:
                reason_code = "VECTOR_BIAS_UNOBSERVABLE"
        elif leading_h == FaultHypothesis.H2_VECTOR_DRIFT:
            can_recalibrate = not is_ambiguous
            reason_code = "SENSOR_DRIFT_DETECTED"
        elif leading_h == FaultHypothesis.H3_REFERENCE_FAULT:
            can_recalibrate = False
            reason_code = "REFERENCE_SENSOR_CORRUPTED"
        elif leading_h == FaultHypothesis.H4_CORRELATED_BIAS:
            can_recalibrate = not is_ambiguous and (lambda_min >= 0.001)
            reason_code = "CORRELATED_VECTOR_BIAS_DETECTED"
        elif leading_h == FaultHypothesis.H5_SENSOR_DROPOUT:
            can_recalibrate = False
            reason_code = "SENSOR_DROPOUT_DETECTED"
        elif leading_h == FaultHypothesis.H6_AMBIGUOUS:
            can_recalibrate = False
            reason_code = "POOR_OBSERVABILITY_AMBIGUOUS"

        if is_ambiguous and reason_code not in ("POOR_OBSERVABILITY_AMBIGUOUS", "REFERENCE_SENSOR_CORRUPTED"):
            reason_code = "HIGH_ENTROPY_AMBIGUITY"

        scores_dict = {
            h: HypothesisScore(
                hypothesis=h,
                log_likelihood=float(log_liks[h]),
                probability=probabilities[h],
                confidence=float(probabilities[h]),
                description=h.name,
            )
            for h in FaultHypothesis
        }

        prob_str_dict = {h.value: probabilities[h] for h in FaultHypothesis}

        return DiagnosticReport(
            leading_hypothesis=leading_h,
            scores=scores_dict,
            probabilities=prob_str_dict,
            entropy=entropy,
            is_ambiguous=is_ambiguous,
            can_recalibrate=can_recalibrate,
            estimated_bias=estimated_bias if can_recalibrate else zero_bias,
            reason_code=reason_code,
            evidence=evidence,
        )
