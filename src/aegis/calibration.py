from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
from scipy.optimize import least_squares


@dataclass(frozen=True)
class CalibrationResult:
    """
    Standard output schema for the online bias estimation subsystem.
    Contains estimated correction, uncertainty metrics, conditioning diagnostics,
    and formal qualification status.
    """

    bias: np.ndarray
    uncertainty: float
    valid_samples: int
    residual_rmse: float
    lambda_min: float
    condition_number: float
    status: str  # "CALIBRATED" or "REJECTED_*"
    rejection_reason: str | None
    method: str


class OnlineBiasEstimator:
    """
    Online Cross-Modal Sensor Bias Estimator for Physical AI agents.

    Geometry:
        Let z_t be the relative target displacement measurement:
            z_t = d_t + b + epsilon_t
        Let r_t be the independent scalar range measurement:
            r_t = ||d_t|| + nu_t
        The geometric residual for candidate bias b is:
            e_t(b) = ||z_t - b|| - r_t

    Responsibilities:
        - Maintains a rolling history of observable measurements (z_t, r_t).
        - Computes numerical observability diagnostics via Jacobian Gram matrix J^T J.
        - Solves for candidate bias b using OLS or Robust Huber loss.
        - Enforces an observability gate to reject collinear or ill-conditioned trajectories.
        - Validates candidate bias against independent/held-out range observations.
    """

    def __init__(
        self,
        window_size: int = 25,
        min_samples: int = 6,
        lambda_min_threshold: float = 0.0005,
        max_condition_number: float = 15000.0,
        max_residual_threshold: float = 0.25,
        validation_threshold: float = 0.15,
        huber_f_scale: float = 0.08,
    ):
        self.window_size = int(window_size)
        self.min_samples = int(min_samples)
        self.lambda_min_threshold = float(lambda_min_threshold)
        self.max_condition_number = float(max_condition_number)
        self.max_residual_threshold = float(max_residual_threshold)
        self.validation_threshold = float(validation_threshold)
        self.huber_f_scale = float(huber_f_scale)

        self._vector_history: list[np.ndarray] = []
        self._range_history: list[float] = []

    def clear(self) -> None:
        self._vector_history.clear()
        self._range_history.clear()

    def add_observation(
        self,
        vector_measurement: np.ndarray,
        range_measurement: float,
        is_valid: bool = True,
    ) -> None:
        """
        Record an agent-observable measurement pair (z_t, r_t).
        Invalid, zero, or dropped readings are discarded.
        """
        if not is_valid or np.isnan(range_measurement) or range_measurement <= 1e-4:
            return

        vec = np.asarray(vector_measurement, dtype=np.float64)
        if np.any(np.isnan(vec)) or np.all(vec == 0.0):
            return

        self._vector_history.append(vec.copy())
        self._range_history.append(float(range_measurement))

        if len(self._vector_history) > self.window_size:
            self._vector_history.pop(0)
            self._range_history.pop(0)

    @property
    def sample_count(self) -> int:
        return len(self._vector_history)

    def compute_observability(
        self,
        candidate_bias: np.ndarray,
    ) -> tuple[float, float, np.ndarray]:
        """
        Analyzes the Jacobian matrix of geometric residuals:
            J_t = - (z_t - b)^T / ||z_t - b||
            F = J^T J  (2x2 Fisher Information Matrix)
        Returns:
            lambda_min: Minimum eigenvalue of F
            condition_number: lambda_max / lambda_min
            F: 2x2 Gram matrix
        """
        if len(self._vector_history) < 2:
            return 0.0, float("inf"), np.zeros((2, 2))

        b = np.asarray(candidate_bias, dtype=np.float64)
        J = []
        for z in self._vector_history:
            u = z - b
            norm_u = float(np.linalg.norm(u))
            if norm_u <= 1e-8:
                continue
            J.append(-u / norm_u)

        if len(J) < 2:
            return 0.0, float("inf"), np.zeros((2, 2))

        J_mat = np.array(J)
        F = J_mat.T @ J_mat
        eigvals = np.linalg.eigvalsh(F)
        l_min = float(max(0.0, eigvals[0]))
        l_max = float(max(1e-12, eigvals[-1]))
        cond = float(l_max / max(l_min, 1e-12))
        return l_min, cond, F

    def estimate(
        self,
        method: str = "HUBER",
        enforce_observability_gate: bool = True,
        initial_guess: np.ndarray | None = None,
    ) -> CalibrationResult:
        """
        Solves for bias vector b_hat from stored measurement window.
        """
        n_samples = len(self._vector_history)

        # 1. Check sample count
        if n_samples < self.min_samples:
            return CalibrationResult(
                bias=np.zeros(2, dtype=np.float64),
                uncertainty=float("inf"),
                valid_samples=n_samples,
                residual_rmse=float("inf"),
                lambda_min=0.0,
                condition_number=float("inf"),
                status="REJECTED_INSUFFICIENT_DATA",
                rejection_reason=f"Sample count ({n_samples}) < minimum required ({self.min_samples})",
                method=method,
            )

        z_arr = np.array(self._vector_history)
        r_arr = np.array(self._range_history)

        def residual_fn(b):
            diff = z_arr - b
            dists = np.linalg.norm(diff, axis=1)
            return dists - r_arr

        x0 = (
            np.asarray(initial_guess, dtype=np.float64)
            if initial_guess is not None
            else np.zeros(2, dtype=np.float64)
        )

        loss_type = "huber" if method.upper() == "HUBER" else "linear"
        f_scale = self.huber_f_scale if loss_type == "huber" else 1.0
        bounds = (-1.5, 1.5)

        # Multi-start initial guess: evaluate algebraic closed-form linearization and zeros
        candidate_x0 = [np.zeros(2, dtype=np.float64)]
        if initial_guess is not None:
            candidate_x0.insert(0, np.clip(np.asarray(initial_guess, dtype=np.float64), -1.5, 1.5))
        else:
            try:
                z0 = z_arr[0]
                r0 = r_arr[0]
                A = []
                y = []
                for z, r in zip(z_arr[1:], r_arr[1:]):
                    A.append(z - z0)
                    y.append(
                        0.5
                        * (
                            (float(np.dot(z, z)) - float(r**2))
                            - (float(np.dot(z0, z0)) - float(r0**2))
                        )
                    )
                A_mat = np.array(A, dtype=np.float64)
                y_vec = np.array(y, dtype=np.float64)
                b_lin, _, rank, _ = np.linalg.lstsq(A_mat, y_vec, rcond=None)
                if rank == 2 and np.all(np.isfinite(b_lin)):
                    candidate_x0.insert(0, np.clip(b_lin, -1.5, 1.5))
            except Exception:
                pass

        best_opt = None
        best_cost = float("inf")

        for x0 in candidate_x0:
            try:
                opt_res = least_squares(
                    residual_fn,
                    x0=x0,
                    bounds=bounds,
                    loss=loss_type,
                    f_scale=f_scale,
                    method="trf",
                    ftol=1e-5,
                    xtol=1e-5,
                    max_nfev=200,
                )
                if opt_res.success and opt_res.cost < best_cost:
                    best_cost = opt_res.cost
                    best_opt = opt_res
            except Exception:
                continue

        if best_opt is None:
            return CalibrationResult(
                bias=np.zeros(2, dtype=np.float64),
                uncertainty=float("inf"),
                valid_samples=n_samples,
                residual_rmse=float("inf"),
                lambda_min=0.0,
                condition_number=float("inf"),
                status="REJECTED_OPTIMIZER_FAILED",
                rejection_reason="Optimizer failed on all candidate initializations",
                method=method,
            )

        b_hat = best_opt.x
        final_res = residual_fn(b_hat)
        rmse = float(np.sqrt(np.mean(final_res**2)))

        # 2. Residual magnitude check (catches corrupted reference sensor or wrong fault model)
        if rmse > self.max_residual_threshold:
            return CalibrationResult(
                bias=b_hat,
                uncertainty=float("inf"),
                valid_samples=n_samples,
                residual_rmse=rmse,
                lambda_min=0.0,
                condition_number=float("inf"),
                status="REJECTED_HIGH_RESIDUAL",
                rejection_reason=f"Residual RMSE ({rmse:.4f}) exceeds threshold ({self.max_residual_threshold:.4f}) - reference sensor corrupted or invalid fault model",
                method=method,
            )

        # 3. Observability Check
        l_min, cond, _ = self.compute_observability(b_hat)

        if enforce_observability_gate:
            if l_min < self.lambda_min_threshold:
                return CalibrationResult(
                    bias=b_hat,
                    uncertainty=float("inf"),
                    valid_samples=n_samples,
                    residual_rmse=rmse,
                    lambda_min=l_min,
                    condition_number=cond,
                    status="REJECTED_POOR_OBSERVABILITY",
                    rejection_reason=f"Minimum eigenvalue ({l_min:.6f}) below threshold ({self.lambda_min_threshold:.6f}) - trajectory lacks geometric diversity",
                    method=method,
                )

            if cond > self.max_condition_number:
                return CalibrationResult(
                    bias=b_hat,
                    uncertainty=float("inf"),
                    valid_samples=n_samples,
                    residual_rmse=rmse,
                    lambda_min=l_min,
                    condition_number=cond,
                    status="REJECTED_ILL_CONDITIONED",
                    rejection_reason=f"Condition number ({cond:.1f}) exceeds limit ({self.max_condition_number:.1f}) - trajectory is collinear",
                    method=method,
                )

        # 3. Compute parameter uncertainty (approximate covariance from J^T J)
        uncertainty = rmse / max(np.sqrt(l_min), 1e-6)

        return CalibrationResult(
            bias=b_hat,
            uncertainty=uncertainty,
            valid_samples=n_samples,
            residual_rmse=rmse,
            lambda_min=l_min,
            condition_number=cond,
            status="CALIBRATED",
            rejection_reason=None,
            method=method,
        )

    def validate_candidate_bias(
        self,
        candidate_bias: np.ndarray,
        validation_vectors: list[np.ndarray],
        validation_ranges: list[float],
    ) -> tuple[bool, float]:
        """
        Validates candidate bias against an independent or held-out set of range measurements.
        Ensures the candidate bias predicts independent geometric distances accurately.
        """
        if not validation_vectors or not validation_ranges:
            return False, float("inf")

        b = np.asarray(candidate_bias, dtype=np.float64)
        errors = []
        for z, r in zip(validation_vectors, validation_ranges):
            pred_dist = float(np.linalg.norm(z - b))
            errors.append(pred_dist - r)

        val_rmse = float(np.sqrt(np.mean(np.array(errors) ** 2)))
        is_valid = val_rmse <= self.validation_threshold
        return is_valid, val_rmse
