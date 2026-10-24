"""
NEXVIA AEGIS V9.0 — Disjoint Per-Sensor Bias Calibration & Uncertainty Engine (Decision 2).

Implements Section 3.4.2 of `docs/v9_experiment_protocol.md`:
1. Separate `OnlineBiasEstimator` instances (`estimator_a`, `estimator_b`) for `vec_a` and `vec_b`.
2. Preserves raw inter-sensor disagreement ||z_a - z_b||_2 and bias-corrected disagreement
   ||(z_a - b_hat_a) - (z_b - b_hat_b)||_2 separately; never performs blind pre-fusion.
3. Strict input hygiene: missing/dropout packets are discarded before buffer insertion;
   `NaN`, `Inf`, or malformed values on `valid == True` readings latch fail-closed abstention.
4. Code-enforced disjoint probing partition (T_probe = 36):
   - Fit window I_fit = {1..22}: writes exclusively to fit buffers; locks frozen biases at step 22.
   - Transition gap I_gap = {23, 24}: zero writes to fit or validation buffers.
   - Held-out validation window I_val = {25..36}: writes exclusively to validation buffers.
5. Enforces n_fit >= 10, FIM lambda_min >= 1e-3, held-out n_val >= 6, RMSE_val <= tau_val,
   validation drift checks, and post-calibration inter-sensor agreement <= tau_diff.
6. Immutable bias freeze (`b_hat.setflags(write=False)`): prohibits continuous online refitting
   during `CALIBRATED` approach.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import numpy as np
from scipy.optimize import least_squares

from aegis.calibration import OnlineBiasEstimator
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading


class SensorCalStatus(str, Enum):
    """Per-sensor calibration status states required by Approved Decision 2."""

    UNCALIBRATED = "UNCALIBRATED"
    CALIBRATED_VALID = "CALIBRATED_VALID"
    DROPOUT_INSUFFICIENT = "DROPOUT_INSUFFICIENT"
    REJECTED_OR_FAULTY = "REJECTED_OR_FAULTY"


@dataclass(frozen=True)
class PerSensorCalibrationState:
    """Immutable audit state for a single vector sensor k in {a, b}."""

    sensor_name: str
    status: SensorCalStatus
    bias: np.ndarray
    variance_u2: float
    n_fit: int
    n_val: int
    n_anchor_fit: int
    fim_lambda_min: float
    fit_rmse: float
    val_rmse: float
    val_residual_slope: float
    rejection_reason: str


@dataclass(frozen=True)
class CalibratedFusionResult:
    """Output of inverse-uncertainty fusion across valid calibrated sensors."""

    fused_vector: np.ndarray
    valid: bool
    active_sensors: tuple[str, ...]
    raw_disagreement_norm: float | None
    calibrated_disagreement_norm: float | None
    normalized_calibrated_disagreement: float | None
    invalid_input_detected: bool


def _immutable_vec2(arr: np.ndarray) -> np.ndarray:
    out = np.array(arr, dtype=np.float64, copy=True).reshape(2)
    out.setflags(write=False)
    return out


class DisjointPerSensorCalibrator:
    """
    Independent per-sensor calibration and disjoint-window validation engine.
    """

    def __init__(
        self,
        *,
        fit_start: int = 1,
        fit_end: int = 22,
        gap_start: int = 23,
        gap_end: int = 24,
        val_start: int = 25,
        val_end: int = 36,
        n_fit_min: int = 10,
        n_val_min: int = 6,
        lambda_fim_min: float = 1e-3,
        min_range_only_span_m: float = 0.35,
    ) -> None:
        if not (1 <= fit_start <= fit_end < gap_start <= gap_end < val_start <= val_end):
            raise ValueError("Invalid probing window partition indices.")
        if n_fit_min < 2 or n_val_min < 1:
            raise ValueError("Minimum fit/validation counts must be positive.")

        self.fit_start = int(fit_start)
        self.fit_end = int(fit_end)
        self.gap_start = int(gap_start)
        self.gap_end = int(gap_end)
        self.val_start = int(val_start)
        self.val_end = int(val_end)
        self.n_fit_min = int(n_fit_min)
        self.n_val_min = int(n_val_min)
        self.lambda_fim_min = float(lambda_fim_min)
        self.min_range_only_span_m = float(min_range_only_span_m)

        fit_capacity = self.fit_end - self.fit_start + 1
        self.estimator_a = OnlineBiasEstimator(
            window_size=fit_capacity,
            min_samples=self.n_fit_min,
            lambda_min_threshold=self.lambda_fim_min,
            max_residual_threshold=0.25,
        )
        self.estimator_b = OnlineBiasEstimator(
            window_size=fit_capacity,
            min_samples=self.n_fit_min,
            lambda_min_threshold=self.lambda_fim_min,
            max_residual_threshold=0.25,
        )

        self._fit_obs: dict[str, list[tuple[int, np.ndarray, float, float, float]]] = {
            "vec_a": [],
            "vec_b": [],
        }
        self._anchor_fit_obs: dict[str, list[tuple[int, np.ndarray, np.ndarray, float, float]]] = {
            "vec_a": [],
            "vec_b": [],
        }
        self._val_obs: dict[str, list[tuple[int, np.ndarray, float, float, float]]] = {
            "vec_a": [],
            "vec_b": [],
        }

        self._fit_raw_diffs: list[np.ndarray] = []
        self._val_raw_diffs: list[np.ndarray] = []
        self._val_cal_diffs: list[np.ndarray] = []

        self._fit_frozen: bool = False
        self._validation_finalized: bool = False
        self._invalid_latched: bool = False

        zero = _immutable_vec2(np.zeros(2, dtype=np.float64))
        self._states: dict[str, PerSensorCalibrationState] = {
            name: PerSensorCalibrationState(
                sensor_name=name,
                status=SensorCalStatus.UNCALIBRATED,
                bias=zero,
                variance_u2=float("inf"),
                n_fit=0,
                n_val=0,
                n_anchor_fit=0,
                fim_lambda_min=0.0,
                fit_rmse=float("inf"),
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason="NOT_YET_CALIBRATED",
            )
            for name in ("vec_a", "vec_b")
        }

    @property
    def total_probing_steps(self) -> int:
        return self.val_end

    @property
    def is_fit_frozen(self) -> bool:
        return self._fit_frozen

    @property
    def is_validation_finalized(self) -> bool:
        return self._validation_finalized

    @property
    def invalid_input_detected(self) -> bool:
        return self._invalid_latched

    @property
    def state_a(self) -> PerSensorCalibrationState:
        return self._states["vec_a"]

    @property
    def state_b(self) -> PerSensorCalibrationState:
        return self._states["vec_b"]

    def fit_step_indices(self, sensor_name: str) -> tuple[int, ...]:
        return tuple(item[0] for item in self._fit_obs[sensor_name])

    def val_step_indices(self, sensor_name: str) -> tuple[int, ...]:
        return tuple(item[0] for item in self._val_obs[sensor_name])

    @property
    def raw_disagreement_rms(self) -> float | None:
        all_diffs = self._fit_raw_diffs + self._val_raw_diffs
        if not all_diffs:
            return None
        sq = [float(np.dot(d, d)) for d in all_diffs]
        return float(math.sqrt(float(np.mean(sq))))

    @property
    def calibrated_disagreement_rms(self) -> float | None:
        if not self._val_cal_diffs:
            return None
        sq = [float(np.dot(d, d)) for d in self._val_cal_diffs]
        return float(math.sqrt(float(np.mean(sq))))

    def reset(self) -> None:
        """Clears all fit/validation buffers and resets both sensors to UNCALIBRATED."""
        self.estimator_a.clear()
        self.estimator_b.clear()
        for name in ("vec_a", "vec_b"):
            self._fit_obs[name].clear()
            self._anchor_fit_obs[name].clear()
            self._val_obs[name].clear()
        self._fit_raw_diffs.clear()
        self._val_raw_diffs.clear()
        self._val_cal_diffs.clear()
        self._fit_frozen = False
        self._validation_finalized = False
        self._invalid_latched = False

        zero = _immutable_vec2(np.zeros(2, dtype=np.float64))
        for name in ("vec_a", "vec_b"):
            self._states[name] = PerSensorCalibrationState(
                sensor_name=name,
                status=SensorCalStatus.UNCALIBRATED,
                bias=zero,
                variance_u2=float("inf"),
                n_fit=0,
                n_val=0,
                n_anchor_fit=0,
                fim_lambda_min=0.0,
                fit_rmse=float("inf"),
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason="NOT_YET_CALIBRATED",
            )

    @staticmethod
    def _validate_vector_reading(rd: SensorReading) -> tuple[np.ndarray | None, float, bool]:
        """Returns (vec_or_none, sigma, is_malformed)."""
        if not rd.valid:
            return None, 0.0, False
        arr = np.asarray(rd.estimate, dtype=np.float64)
        sig = float(rd.sigma)
        if arr.shape != (2,) or not np.all(np.isfinite(arr)) or not math.isfinite(sig) or sig <= 0.0:
            return None, 0.0, True
        return arr.copy(), sig, False

    @staticmethod
    def _validate_range_reading(rr: RangeReading) -> tuple[float | None, float, bool]:
        """Returns (dist_or_none, sigma, is_malformed)."""
        if not rr.valid:
            return None, 0.0, False
        dist = float(rr.distance)
        sig = float(rr.sigma)
        if not math.isfinite(dist) or dist < 0.0 or not math.isfinite(sig) or sig <= 0.0:
            return None, 0.0, True
        # RangeSensor clamps negative noisy ranges to 0.0; skip clamped <= 1e-4 samples
        if dist <= 1e-4:
            return None, sig, False
        return dist, sig, False

    def record_probing_step(
        self,
        probing_step: int,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        *,
        verified_anchor_estimate: np.ndarray | None = None,
        verified_anchor_sigma: float = 0.04,
        range_corroborated_biased: bool = False,
    ) -> bool:
        """
        Routes a single probing step into I_fit, I_gap, or I_val.
        Returns False immediately if malformed/NaN/Inf input is detected.
        Raises RuntimeError if called after calibration validation is finalized or if
        attempting to write into I_fit after fit freeze.
        """
        if self._validation_finalized:
            raise RuntimeError(
                "Calibration is finalized and frozen; online refitting/mutation is prohibited."
            )
        if probing_step < self.fit_start or probing_step > self.val_end:
            raise ValueError(
                f"probing_step {probing_step} outside [{self.fit_start}, {self.val_end}]."
            )
        if probing_step <= self.fit_end and self._fit_frozen:
            raise RuntimeError(
                f"Cannot record fit step {probing_step}: fit window is already frozen."
            )

        vec_a, sig_a, bad_a = self._validate_vector_reading(reading_a)
        vec_b, sig_b, bad_b = self._validate_vector_reading(reading_b)
        r_dist, sig_r, bad_r = self._validate_range_reading(range_reading)

        anc_vec: np.ndarray | None = None
        if verified_anchor_estimate is not None:
            anc_arr = np.asarray(verified_anchor_estimate, dtype=np.float64)
            if (
                anc_arr.shape != (2,)
                or not np.all(np.isfinite(anc_arr))
                or not math.isfinite(verified_anchor_sigma)
                or verified_anchor_sigma <= 0.0
            ):
                self._invalid_latched = True
                return False
            anc_vec = anc_arr.copy()

        if bad_a or bad_b or bad_r:
            self._invalid_latched = True
            return False

        # Phase 1: Fit Window I_fit = {1..22}
        if self.fit_start <= probing_step <= self.fit_end:
            if vec_a is not None and vec_b is not None:
                self._fit_raw_diffs.append(vec_a - vec_b)

            if vec_a is not None and anc_vec is not None:
                self._anchor_fit_obs["vec_a"].append(
                    (probing_step, vec_a, anc_vec, sig_a, float(verified_anchor_sigma))
                )
            if vec_b is not None and anc_vec is not None:
                self._anchor_fit_obs["vec_b"].append(
                    (probing_step, vec_b, anc_vec, sig_b, float(verified_anchor_sigma))
                )

            if r_dist is not None and not range_corroborated_biased:
                if vec_a is not None and not np.all(vec_a == 0.0):
                    self.estimator_a.add_observation(vec_a, r_dist, True)
                    self._fit_obs["vec_a"].append((probing_step, vec_a, r_dist, sig_a, sig_r))
                if vec_b is not None and not np.all(vec_b == 0.0):
                    self.estimator_b.add_observation(vec_b, r_dist, True)
                    self._fit_obs["vec_b"].append((probing_step, vec_b, r_dist, sig_b, sig_r))

            if probing_step == self.fit_end:
                self.freeze_fit(range_corroborated_biased=range_corroborated_biased)
            return True

        # Transition past fit_end automatically locks fit estimates before gap/val!
        if not self._fit_frozen:
            self.freeze_fit(range_corroborated_biased=range_corroborated_biased)

        # Phase 2: Transition Gap I_gap = {23, 24} -> strictly zero buffer writes!
        if self.gap_start <= probing_step <= self.gap_end:
            return True

        # Phase 3: Held-Out Validation Window I_val = {25..36} -> strictly validation buffers only!
        if vec_a is not None and vec_b is not None:
            self._val_raw_diffs.append(vec_a - vec_b)
            b_a = self._states["vec_a"].bias
            b_b = self._states["vec_b"].bias
            self._val_cal_diffs.append((vec_a - b_a) - (vec_b - b_b))

        if r_dist is not None:
            if vec_a is not None:
                self._val_obs["vec_a"].append((probing_step, vec_a, r_dist, sig_a, sig_r))
            if vec_b is not None:
                self._val_obs["vec_b"].append((probing_step, vec_b, r_dist, sig_b, sig_r))

        return True

    def freeze_fit(self, *, range_corroborated_biased: bool = False) -> None:
        """
        Computes per-sensor bias estimates strictly from I_fit observations and permanently
        locks them (`b_hat.setflags(write=False)`). Idempotent once frozen.
        """
        if self._fit_frozen:
            return

        for name, est in (("vec_a", self.estimator_a), ("vec_b", self.estimator_b)):
            self._states[name] = self._fit_single_sensor(
                name,
                est,
                range_corroborated_biased=range_corroborated_biased,
            )

        self._fit_frozen = True

    def _fit_single_sensor(
        self,
        sensor_name: str,
        estimator: OnlineBiasEstimator,
        *,
        range_corroborated_biased: bool,
    ) -> PerSensorCalibrationState:
        zero = _immutable_vec2(np.zeros(2, dtype=np.float64))
        if self._invalid_latched:
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.REJECTED_OR_FAULTY,
                bias=zero,
                variance_u2=float("inf"),
                n_fit=0,
                n_val=0,
                n_anchor_fit=0,
                fim_lambda_min=0.0,
                fit_rmse=float("inf"),
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason="INVALID_SENSOR_INPUT_IN_FIT",
            )

        fit_list = self._fit_obs[sensor_name]
        anc_list = self._anchor_fit_obs[sensor_name]
        n_fit = len(fit_list)
        n_anc = len(anc_list)

        # If range was corroborated as biased via Decision 3, rely on verified anchor samples
        if range_corroborated_biased:
            if n_anc < 2:
                return PerSensorCalibrationState(
                    sensor_name=sensor_name,
                    status=SensorCalStatus.DROPOUT_INSUFFICIENT,
                    bias=zero,
                    variance_u2=float("inf"),
                    n_fit=n_fit,
                    n_val=0,
                    n_anchor_fit=n_anc,
                    fim_lambda_min=0.0,
                    fit_rmse=float("inf"),
                    val_rmse=float("inf"),
                    val_residual_slope=0.0,
                    rejection_reason="INSUFFICIENT_ANCHOR_EPOCHS_FOR_BIASED_RANGE",
                )
            diffs = np.array([z_k - z_a for (_, z_k, z_a, _, _) in anc_list], dtype=np.float64)
            b_hat = _immutable_vec2(np.median(diffs, axis=0))
            res = np.linalg.norm(diffs - b_hat, axis=1)
            rmse = float(np.sqrt(np.mean(res**2)))
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.UNCALIBRATED,
                bias=b_hat,
                variance_u2=float("inf"),
                n_fit=max(n_fit, n_anc),
                n_val=0,
                n_anchor_fit=n_anc,
                fim_lambda_min=float(n_anc),
                fit_rmse=rmse,
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason="FIT_FROZEN_AWAITING_VALIDATION",
            )

        if n_fit < self.n_fit_min:
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.DROPOUT_INSUFFICIENT,
                bias=zero,
                variance_u2=float("inf"),
                n_fit=n_fit,
                n_val=0,
                n_anchor_fit=n_anc,
                fim_lambda_min=0.0,
                fit_rmse=float("inf"),
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason=f"INSUFFICIENT_FIT_SAMPLES ({n_fit} < {self.n_fit_min})",
            )

        z_arr = np.array([item[1] for item in fit_list], dtype=np.float64)
        r_arr = np.array([item[2] for item in fit_list], dtype=np.float64)
        sig_v = float(np.median([item[3] for item in fit_list]))
        sig_r = float(np.median([item[4] for item in fit_list]))

        # Case A: Gate-verified anchor sample(s) available in I_fit -> full-rank 2D Huber fit
        # combining sensor k's fit-window range residuals and anchor residuals.
        if n_anc >= 1:
            anc_diffs = np.array([z_k - z_a for (_, z_k, z_a, _, _) in anc_list], dtype=np.float64)
            x0 = np.clip(np.median(anc_diffs, axis=0), -1.5, 1.5)
            scale_rng = math.sqrt(sig_v**2 + sig_r**2)

            def joint_res(b: np.ndarray) -> np.ndarray:
                r_res = (np.linalg.norm(z_arr - b, axis=1) - r_arr) / scale_rng
                a_parts = []
                for _, z_k, z_a, s_k, s_a in anc_list:
                    s_ka = math.sqrt(s_k**2 + s_a**2)
                    # Weight anchor 2D constraint proportionally so 1-2 anchor queries break
                    # rotational circle symmetry while remaining Huber-robust to bursts.
                    a_parts.extend(((z_k - b - z_a) / s_ka) * 2.5)
                return np.concatenate([r_res, np.asarray(a_parts, dtype=np.float64)])

            opt = least_squares(
                joint_res,
                x0=x0,
                bounds=(-1.5, 1.5),
                loss="huber",
                f_scale=1.35,
                method="trf",
                ftol=1e-6,
                xtol=1e-6,
                max_nfev=200,
            )
            b_hat = _immutable_vec2(opt.x if opt.success else x0)
            rng_res = np.linalg.norm(z_arr - b_hat, axis=1) - r_arr
            fit_rmse = float(np.sqrt(np.mean(rng_res**2)))
            l_min_rng, _, _ = estimator.compute_observability(b_hat)
            l_min_total = float(l_min_rng + float(n_anc))

            # Cross-consistency check between fitted b_hat and verified anchor bias mean:
            # prevents 22 biased range equations from silently dragging b_hat away from z_anc!
            anc_mean_bias = np.mean(anc_diffs, axis=0)
            anc_sig_med = float(np.median([item[4] for item in anc_list]))
            anc_bias_se = math.sqrt((sig_v**2 + anc_sig_med**2) / float(n_anc))
            anc_fit_gap = float(np.linalg.norm(b_hat - anc_mean_bias))

            if (
                fit_rmse > 0.25
                or l_min_total < self.lambda_fim_min
                or anc_fit_gap > 3.5 * anc_bias_se
            ):
                return PerSensorCalibrationState(
                    sensor_name=sensor_name,
                    status=SensorCalStatus.REJECTED_OR_FAULTY,
                    bias=b_hat,
                    variance_u2=float("inf"),
                    n_fit=n_fit,
                    n_val=0,
                    n_anchor_fit=n_anc,
                    fim_lambda_min=l_min_total,
                    fit_rmse=fit_rmse,
                    val_rmse=float("inf"),
                    val_residual_slope=0.0,
                    rejection_reason=(
                        "ANCHOR_RANGE_BIAS_FIT_CONFLICT"
                        if anc_fit_gap > 3.5 * anc_bias_se
                        else "HIGH_FIT_RESIDUAL_OR_POOR_FIM"
                    ),
                )

            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.UNCALIBRATED,
                bias=b_hat,
                variance_u2=float("inf"),
                n_fit=n_fit,
                n_val=0,
                n_anchor_fit=n_anc,
                fim_lambda_min=l_min_total,
                fit_rmse=fit_rmse,
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason="FIT_FROZEN_AWAITING_VALIDATION",
            )

        # Case B: No verified anchor observation in I_fit (range-only Huber calibration).
        # First check whether zero bias already explains the sensor's range observations;
        # otherwise require genuine spatial chord diversity (>= min_range_only_span_m) so
        # sensor noise jitter over a stationary cluster never masquerades as 2D observability!
        zero_res = np.linalg.norm(z_arr, axis=1) - r_arr
        zero_rmse = float(np.sqrt(np.mean(zero_res**2)))
        diffs_span = z_arr - z_arr[0]
        max_span = float(np.max(np.linalg.norm(diffs_span, axis=1)))

        if max_span < self.min_range_only_span_m:
            # Without spatial chord diversity or anchor, only zero-bias consistency can be verified
            nom_tol = 2.0 * math.sqrt(sig_v**2 + sig_r**2)
            if zero_rmse <= nom_tol:
                l_min_zero, _, _ = estimator.compute_observability(zero)
                # Unbiased hypothesis has 0 free parameters estimated, use conservative floor
                eff_l_min = max(l_min_zero, 0.25)
                return PerSensorCalibrationState(
                    sensor_name=sensor_name,
                    status=SensorCalStatus.UNCALIBRATED,
                    bias=zero,
                    variance_u2=float("inf"),
                    n_fit=n_fit,
                    n_val=0,
                    n_anchor_fit=0,
                    fim_lambda_min=eff_l_min,
                    fit_rmse=zero_rmse,
                    val_rmse=float("inf"),
                    val_residual_slope=0.0,
                    rejection_reason="ZERO_BIAS_FIT_AWAITING_VALIDATION",
                )
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.REJECTED_OR_FAULTY,
                bias=zero,
                variance_u2=float("inf"),
                n_fit=n_fit,
                n_val=0,
                n_anchor_fit=0,
                fim_lambda_min=0.0,
                fit_rmse=zero_rmse,
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason=(
                    f"INSUFFICIENT_SPATIAL_BASELINE_WITHOUT_ANCHOR ({max_span:.3f}m < {self.min_range_only_span_m:.2f}m)"
                ),
            )

        cal_res = estimator.estimate(method="HUBER", enforce_observability_gate=True)
        b_hat = _immutable_vec2(cal_res.bias)
        if cal_res.status != "CALIBRATED" or cal_res.lambda_min < self.lambda_fim_min:
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.REJECTED_OR_FAULTY,
                bias=b_hat,
                variance_u2=float("inf"),
                n_fit=n_fit,
                n_val=0,
                n_anchor_fit=0,
                fim_lambda_min=float(cal_res.lambda_min),
                fit_rmse=float(cal_res.residual_rmse),
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason=cal_res.rejection_reason or cal_res.status,
            )

        return PerSensorCalibrationState(
            sensor_name=sensor_name,
            status=SensorCalStatus.UNCALIBRATED,
            bias=b_hat,
            variance_u2=float("inf"),
            n_fit=n_fit,
            n_val=0,
            n_anchor_fit=0,
            fim_lambda_min=float(cal_res.lambda_min),
            fit_rmse=float(cal_res.residual_rmse),
            val_rmse=float("inf"),
            val_residual_slope=0.0,
            rejection_reason="FIT_FROZEN_AWAITING_VALIDATION",
        )

    def finalize_validation(
        self,
        *,
        tau_val: float,
        tau_diff: float,
        range_corroborated_biased: bool = False,
    ) -> tuple[PerSensorCalibrationState, PerSensorCalibrationState]:
        """
        Evaluates locked fit estimates exclusively on held-out I_val = {25..36} observations.
        Never mutates `bias` on either sensor.
        """
        if not self._fit_frozen:
            self.freeze_fit(range_corroborated_biased=range_corroborated_biased)

        # Invariant verification: fit and validation step indices must be strictly disjoint!
        for name in ("vec_a", "vec_b"):
            overlap = set(self.fit_step_indices(name)) & set(self.val_step_indices(name))
            if overlap:
                raise RuntimeError(f"Fit/validation leakage detected on {name}: {overlap}")

        # Diagnostic D2: Check inter-window inter-sensor drift shift between I_fit and I_val
        drifting_sensor_from_d2: str | None = None
        if len(self._fit_raw_diffs) >= 6 and len(self._val_raw_diffs) >= 6:
            mean_fit_diff = np.mean(np.asarray(self._fit_raw_diffs, dtype=np.float64), axis=0)
            mean_val_diff = np.mean(np.asarray(self._val_raw_diffs, dtype=np.float64), axis=0)
            shift_norm = float(np.linalg.norm(mean_val_diff - mean_fit_diff))
            # Nominal SD of ||mean_val - mean_fit|| in 2D is sqrt(2*(sigma_a^2+sigma_b^2)*(1/n1+1/n2))
            sig_a_nom = (
                float(np.median([x[3] for x in self._val_obs["vec_a"]]))
                if self._val_obs["vec_a"]
                else 0.05
            )
            sig_b_nom = (
                float(np.median([x[3] for x in self._val_obs["vec_b"]]))
                if self._val_obs["vec_b"]
                else 0.05
            )
            sig_diff = math.sqrt(sig_a_nom**2 + sig_b_nom**2)
            se_shift = sig_diff * math.sqrt(
                (1.0 / len(self._fit_raw_diffs)) + (1.0 / len(self._val_raw_diffs))
            )
            if shift_norm > 3.6 * se_shift and not range_corroborated_biased:
                # Identify which sensor's range residual shifted more across windows
                err_a = self._sensor_val_rmse_raw("vec_a")
                err_b = self._sensor_val_rmse_raw("vec_b")
                drifting_sensor_from_d2 = "vec_a" if err_a >= err_b else "vec_b"

        for name in ("vec_a", "vec_b"):
            self._states[name] = self._validate_single_sensor(
                name,
                tau_val=tau_val,
                range_corroborated_biased=range_corroborated_biased,
                flagged_drifting=(drifting_sensor_from_d2 == name),
            )

        # Post-calibration inter-sensor agreement check when BOTH sensors are CALIBRATED_VALID
        st_a = self._states["vec_a"]
        st_b = self._states["vec_b"]
        if (
            st_a.status == SensorCalStatus.CALIBRATED_VALID
            and st_b.status == SensorCalStatus.CALIBRATED_VALID
            and self._val_cal_diffs
        ):
            cal_rms = self.calibrated_disagreement_rms or 0.0
            denom = math.sqrt(st_a.variance_u2 + st_b.variance_u2)
            norm_dis = cal_rms / max(denom, 1e-6)
            if norm_dis > tau_diff:
                for name in ("vec_a", "vec_b"):
                    prev = self._states[name]
                    self._states[name] = PerSensorCalibrationState(
                        sensor_name=name,
                        status=SensorCalStatus.REJECTED_OR_FAULTY,
                        bias=prev.bias,
                        variance_u2=float("inf"),
                        n_fit=prev.n_fit,
                        n_val=prev.n_val,
                        n_anchor_fit=prev.n_anchor_fit,
                        fim_lambda_min=prev.fim_lambda_min,
                        fit_rmse=prev.fit_rmse,
                        val_rmse=prev.val_rmse,
                        val_residual_slope=prev.val_residual_slope,
                        rejection_reason=(
                            f"POST_CALIBRATION_INTER_SENSOR_DISAGREEMENT ({norm_dis:.2f} > {tau_diff:.2f})"
                        ),
                    )

        self._validation_finalized = True
        return self._states["vec_a"], self._states["vec_b"]

    def _sensor_val_rmse_raw(self, sensor_name: str) -> float:
        val_list = self._val_obs[sensor_name]
        if not val_list:
            return float("inf")
        b_hat = self._states[sensor_name].bias
        res = [float(np.linalg.norm(z - b_hat)) - r for (_, z, r, _, _) in val_list]
        return float(np.sqrt(np.mean(np.square(res))))

    def _validate_single_sensor(
        self,
        sensor_name: str,
        *,
        tau_val: float,
        range_corroborated_biased: bool,
        flagged_drifting: bool,
    ) -> PerSensorCalibrationState:
        prev = self._states[sensor_name]
        val_list = self._val_obs[sensor_name]
        n_val = len(val_list)

        if self._invalid_latched:
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.REJECTED_OR_FAULTY,
                bias=prev.bias,
                variance_u2=float("inf"),
                n_fit=prev.n_fit,
                n_val=n_val,
                n_anchor_fit=prev.n_anchor_fit,
                fim_lambda_min=prev.fim_lambda_min,
                fit_rmse=prev.fit_rmse,
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason="INVALID_SENSOR_INPUT_DETECTED",
            )

        if prev.status in (SensorCalStatus.DROPOUT_INSUFFICIENT, SensorCalStatus.REJECTED_OR_FAULTY):
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=prev.status,
                bias=prev.bias,
                variance_u2=float("inf"),
                n_fit=prev.n_fit,
                n_val=n_val,
                n_anchor_fit=prev.n_anchor_fit,
                fim_lambda_min=prev.fim_lambda_min,
                fit_rmse=prev.fit_rmse,
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason=prev.rejection_reason,
            )

        if n_val < self.n_val_min:
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.DROPOUT_INSUFFICIENT,
                bias=prev.bias,
                variance_u2=float("inf"),
                n_fit=prev.n_fit,
                n_val=n_val,
                n_anchor_fit=prev.n_anchor_fit,
                fim_lambda_min=prev.fim_lambda_min,
                fit_rmse=prev.fit_rmse,
                val_rmse=float("inf"),
                val_residual_slope=0.0,
                rejection_reason=f"INSUFFICIENT_VAL_SAMPLES ({n_val} < {self.n_val_min})",
            )

        steps_arr = np.array([item[0] for item in val_list], dtype=np.float64)
        z_val = np.array([item[1] for item in val_list], dtype=np.float64)
        r_val = np.array([item[2] for item in val_list], dtype=np.float64)
        sig_k = float(np.median([item[3] for item in val_list]))

        if range_corroborated_biased:
            # When static range bias b_r != 0 was explicitly corroborated via Decision 3,
            # subtract the fit-window median range offset so held-out validation tests residual
            # consistency and drift without treating unshifted r_t as zero-bias!
            fit_list = self._fit_obs[sensor_name]
            if fit_list:
                z_fit = np.array([item[1] for item in fit_list], dtype=np.float64)
                r_fit = np.array([item[2] for item in fit_list], dtype=np.float64)
                b_r_hat = float(np.median(r_fit - np.linalg.norm(z_fit - prev.bias, axis=1)))
            else:
                b_r_hat = 0.0
            signed_res = np.linalg.norm(z_val - prev.bias, axis=1) - (r_val - b_r_hat)
        else:
            signed_res = np.linalg.norm(z_val - prev.bias, axis=1) - r_val

        val_rmse = float(np.sqrt(np.mean(signed_res**2)))
        if float(steps_arr[-1] - steps_arr[0]) > 0.0:
            slope = float(np.polyfit(steps_arr - steps_arr[0], signed_res, 1)[0])
        else:
            slope = 0.0

        if flagged_drifting or abs(slope) > 0.022:
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.REJECTED_OR_FAULTY,
                bias=prev.bias,
                variance_u2=float("inf"),
                n_fit=prev.n_fit,
                n_val=n_val,
                n_anchor_fit=prev.n_anchor_fit,
                fim_lambda_min=prev.fim_lambda_min,
                fit_rmse=prev.fit_rmse,
                val_rmse=val_rmse,
                val_residual_slope=slope,
                rejection_reason=f"VALIDATION_DRIFT_DETECTED (slope={slope:.4f})",
            )

        if val_rmse > tau_val:
            return PerSensorCalibrationState(
                sensor_name=sensor_name,
                status=SensorCalStatus.REJECTED_OR_FAULTY,
                bias=prev.bias,
                variance_u2=float("inf"),
                n_fit=prev.n_fit,
                n_val=n_val,
                n_anchor_fit=prev.n_anchor_fit,
                fim_lambda_min=prev.fim_lambda_min,
                fit_rmse=prev.fit_rmse,
                val_rmse=val_rmse,
                val_residual_slope=slope,
                rejection_reason=f"VALIDATION_RMSE_EXCEEDED ({val_rmse:.4f} > {tau_val:.4f})",
            )

        u2 = float(sig_k**2 + (val_rmse**2) / max(prev.fim_lambda_min, 1e-6))
        return PerSensorCalibrationState(
            sensor_name=sensor_name,
            status=SensorCalStatus.CALIBRATED_VALID,
            bias=prev.bias,
            variance_u2=u2,
            n_fit=prev.n_fit,
            n_val=n_val,
            n_anchor_fit=prev.n_anchor_fit,
            fim_lambda_min=prev.fim_lambda_min,
            fit_rmse=prev.fit_rmse,
            val_rmse=val_rmse,
            val_residual_slope=slope,
            rejection_reason="PASSED_DISJOINT_VALIDATION",
        )

    def isolate_faulty_sensor(self, sensor_name: str, *, reason: str) -> None:
        """
        Demotes a calibrated sensor to REJECTED_OR_FAULTY (w_k = 0) during CALIBRATED
        approach WITHOUT modifying any frozen bias estimate.
        """
        if sensor_name not in self._states:
            raise ValueError(f"Unknown sensor {sensor_name}.")
        prev = self._states[sensor_name]
        self._states[sensor_name] = PerSensorCalibrationState(
            sensor_name=sensor_name,
            status=SensorCalStatus.REJECTED_OR_FAULTY,
            bias=prev.bias,
            variance_u2=float("inf"),
            n_fit=prev.n_fit,
            n_val=prev.n_val,
            n_anchor_fit=prev.n_anchor_fit,
            fim_lambda_min=prev.fim_lambda_min,
            fit_rmse=prev.fit_rmse,
            val_rmse=prev.val_rmse,
            val_residual_slope=prev.val_residual_slope,
            rejection_reason=reason,
        )

    def has_any_valid_calibrated_sensor(self) -> bool:
        return any(
            st.status == SensorCalStatus.CALIBRATED_VALID for st in self._states.values()
        )

    def fuse_calibrated(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        *,
        range_reading: RangeReading | None = None,
        tau_diff: float | None = None,
    ) -> CalibratedFusionResult:
        """
        Fuses currently valid readings from CALIBRATED_VALID sensors using inverse-uncertainty
        weights w_k = 1 / u_k^2, preserving raw and bias-corrected disagreement separately
        and avoiding single-sensor dropout bias jumps. Never mutates bias estimates.
        """
        vec_a, sig_a, bad_a = self._validate_vector_reading(reading_a)
        vec_b, sig_b, bad_b = self._validate_vector_reading(reading_b)
        if bad_a or bad_b:
            self._invalid_latched = True
            return CalibratedFusionResult(
                fused_vector=np.zeros(2, dtype=np.float64),
                valid=False,
                active_sensors=(),
                raw_disagreement_norm=None,
                calibrated_disagreement_norm=None,
                normalized_calibrated_disagreement=None,
                invalid_input_detected=True,
            )

        raw_dis: float | None = None
        cal_dis: float | None = None
        norm_cal_dis: float | None = None

        st_a = self._states["vec_a"]
        st_b = self._states["vec_b"]

        if vec_a is not None and vec_b is not None:
            raw_dis = float(np.linalg.norm(vec_a - vec_b))
            corr_a = vec_a - st_a.bias
            corr_b = vec_b - st_b.bias
            cal_dis = float(np.linalg.norm(corr_a - corr_b))
            if (
                st_a.status == SensorCalStatus.CALIBRATED_VALID
                and st_b.status == SensorCalStatus.CALIBRATED_VALID
            ):
                denom = math.sqrt(st_a.variance_u2 + st_b.variance_u2)
                norm_cal_dis = cal_dis / max(denom, 1e-6)

        a_usable = vec_a is not None and st_a.status == SensorCalStatus.CALIBRATED_VALID
        b_usable = vec_b is not None and st_b.status == SensorCalStatus.CALIBRATED_VALID

        if a_usable and b_usable:
            assert vec_a is not None and vec_b is not None
            corr_a = vec_a - st_a.bias
            corr_b = vec_b - st_b.bias

            # Protect fused pursuit action from a 1-step heavy-tailed burst on one sensor
            # when range clearly corroborates the companion sensor!
            if (
                tau_diff is not None
                and norm_cal_dis is not None
                and norm_cal_dis > tau_diff
                and range_reading is not None
                and range_reading.valid
                and math.isfinite(range_reading.distance)
                and range_reading.distance > 1e-4
            ):
                err_a = abs(float(np.linalg.norm(corr_a)) - float(range_reading.distance))
                err_b = abs(float(np.linalg.norm(corr_b)) - float(range_reading.distance))
                tol_a = 2.5 * math.sqrt(sig_a**2 + float(range_reading.sigma) ** 2)
                tol_b = 2.5 * math.sqrt(sig_b**2 + float(range_reading.sigma) ** 2)
                if err_b <= tol_b and err_a > 2.0 * tol_a:
                    return CalibratedFusionResult(
                        fused_vector=corr_b,
                        valid=True,
                        active_sensors=("vec_b",),
                        raw_disagreement_norm=raw_dis,
                        calibrated_disagreement_norm=cal_dis,
                        normalized_calibrated_disagreement=norm_cal_dis,
                        invalid_input_detected=False,
                    )
                if err_a <= tol_a and err_b > 2.0 * tol_b:
                    return CalibratedFusionResult(
                        fused_vector=corr_a,
                        valid=True,
                        active_sensors=("vec_a",),
                        raw_disagreement_norm=raw_dis,
                        calibrated_disagreement_norm=cal_dis,
                        normalized_calibrated_disagreement=norm_cal_dis,
                        invalid_input_detected=False,
                    )

            w_a = 1.0 / max(st_a.variance_u2, 1e-8)
            w_b = 1.0 / max(st_b.variance_u2, 1e-8)
            fused = (w_a * corr_a + w_b * corr_b) / (w_a + w_b)
            return CalibratedFusionResult(
                fused_vector=fused,
                valid=True,
                active_sensors=("vec_a", "vec_b"),
                raw_disagreement_norm=raw_dis,
                calibrated_disagreement_norm=cal_dis,
                normalized_calibrated_disagreement=norm_cal_dis,
                invalid_input_detected=False,
            )

        if a_usable:
            assert vec_a is not None
            return CalibratedFusionResult(
                fused_vector=vec_a - st_a.bias,
                valid=True,
                active_sensors=("vec_a",),
                raw_disagreement_norm=raw_dis,
                calibrated_disagreement_norm=cal_dis,
                normalized_calibrated_disagreement=norm_cal_dis,
                invalid_input_detected=False,
            )

        if b_usable:
            assert vec_b is not None
            return CalibratedFusionResult(
                fused_vector=vec_b - st_b.bias,
                valid=True,
                active_sensors=("vec_b",),
                raw_disagreement_norm=raw_dis,
                calibrated_disagreement_norm=cal_dis,
                normalized_calibrated_disagreement=norm_cal_dis,
                invalid_input_detected=False,
            )

        return CalibratedFusionResult(
            fused_vector=np.zeros(2, dtype=np.float64),
            valid=False,
            active_sensors=(),
            raw_disagreement_norm=raw_dis,
            calibrated_disagreement_norm=cal_dis,
            normalized_calibrated_disagreement=norm_cal_dis,
            invalid_input_detected=False,
        )
