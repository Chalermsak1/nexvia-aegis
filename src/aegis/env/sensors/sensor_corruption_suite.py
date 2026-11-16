"""
NEXVIA-AEGIS: Real-World Sensor Corruption & Calibration Suite (Pillar 2).

Provides realistic environmental degradation models for physical autonomous systems:
1. CameraGlareModel:
   - Sun glare / high-beam blooming saturation holes.
   - Specular reflections causing optical feature track loss.
2. AtmosphericSmokeFogModel:
   - Aerosol particle scattering via Beer-Lambert attenuation (I = I_0 * exp(-alpha * d)).
   - Backscatter returns creating phantom obstacles and range truncation.
3. OnlineCovarianceEstimator:
   - Recursive moving-window innovation covariance filter.
   - Real-time sigma_p and sigma_v tracking with blackout detection triggers.
"""

from dataclasses import dataclass, field
import math
from typing import Optional, Tuple
import numpy as np


@dataclass
class GlareConfig:
    glare_source_dir: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.5]))
    blooming_half_angle_rad: float = 0.35  # ~20 degrees cone
    intensity: float = 1.0  # [0.0, 1.0]
    dropout_probability: float = 0.85
    noise_inflation_factor: float = 8.0


class CameraGlareModel:
    """
    Simulates optical sensor degradation from bright sunlight or intense headlamps.
    When looking toward the glare source, optical features wash out and covariance surges.
    """

    def __init__(self, config: Optional[GlareConfig] = None):
        self.config = config or GlareConfig()
        norm = np.linalg.norm(self.config.glare_source_dir)
        if norm > 1e-6:
            self.config.glare_source_dir = self.config.glare_source_dir / norm

    def compute_glare_factor(self, optical_axis: np.ndarray) -> float:
        """
        Computes the glare intensity factor in [0.0, 1.0] based on angular alignment.
        """
        axis_norm = np.linalg.norm(optical_axis)
        if axis_norm < 1e-6:
            return 0.0
        unit_axis = optical_axis / axis_norm
        cos_theta = np.clip(np.dot(unit_axis, self.config.glare_source_dir), -1.0, 1.0)
        angle = np.arccos(cos_theta)

        if angle > self.config.blooming_half_angle_rad:
            return 0.0
        # Smooth quadratic decay from center of blooming cone
        factor = (1.0 - (angle / self.config.blooming_half_angle_rad) ** 2) * self.config.intensity
        return float(np.clip(factor, 0.0, 1.0))

    def corrupt_measurement(
        self,
        true_pos: np.ndarray,
        optical_axis: np.ndarray,
        nominal_sigma: float = 0.05,
        rng: Optional[np.random.Generator] = None,
    ) -> Tuple[np.ndarray, float, bool]:
        """
        Applies glare corruption to a 3D position measurement.
        Returns:
            (corrupted_pos, effective_sigma, is_dropped_out)
        """
        if rng is None:
            rng = np.random.default_rng()

        glare_factor = self.compute_glare_factor(optical_axis)
        if glare_factor <= 1e-4:
            noise = rng.normal(0.0, nominal_sigma, size=true_pos.shape)
            return true_pos + noise, nominal_sigma, False

        # Glare present: check for total saturation blackout
        if rng.random() < (glare_factor * self.config.dropout_probability):
            # Measurement is completely lost (NaN / blackout hole)
            nan_pos = np.full_like(true_pos, np.nan)
            inflated_sigma = nominal_sigma * self.config.noise_inflation_factor * 5.0
            return nan_pos, inflated_sigma, True

        # Degraded measurement: variance scales with glare factor
        effective_sigma = nominal_sigma * (1.0 + (self.config.noise_inflation_factor - 1.0) * glare_factor)
        noise = rng.normal(0.0, effective_sigma, size=true_pos.shape)
        return true_pos + noise, effective_sigma, False


@dataclass
class SmokeFogConfig:
    attenuation_coeff: float = 0.15  # alpha in m^-1 (0.05 = light haze, 0.35 = dense smoke)
    backscatter_intensity: float = 0.40  # Probability of false phantom obstacle returns
    max_penetration_range_m: float = 12.0
    velocity_noise_scaling: float = 4.0


class AtmosphericSmokeFogModel:
    """
    Simulates optical and LiDAR scattering through aerosol particulates (smoke / fog).
    Follows Beer-Lambert extinction law and Mie scattering backscatter.
    """

    def __init__(self, config: Optional[SmokeFogConfig] = None):
        self.config = config or SmokeFogConfig()

    def transmission_factor(self, distance_m: float) -> float:
        """
        Transmittance T(d) = exp(-alpha * d)
        """
        if distance_m <= 0.0:
            return 1.0
        return float(math.exp(-self.config.attenuation_coeff * distance_m))

    def corrupt_range_measurement(
        self,
        true_range: float,
        nominal_sigma: float = 0.05,
        rng: Optional[np.random.Generator] = None,
    ) -> Tuple[float, float, bool]:
        """
        Corrupts LiDAR/radar range measurement.
        Returns:
            (measured_range, effective_sigma, is_phantom_return)
        """
        if rng is None:
            rng = np.random.default_rng()

        t_factor = self.transmission_factor(true_range)

        # Check for Mie backscatter false return closer than true obstacle
        if rng.random() < (self.config.backscatter_intensity * (1.0 - t_factor)):
            phantom_range = float(rng.uniform(0.5, max(1.0, true_range * 0.5)))
            return phantom_range, nominal_sigma * 3.0, True

        # Beyond penetration range, sensor receives no echo (inf/dropout)
        if true_range > self.config.max_penetration_range_m and t_factor < 0.05:
            return float("inf"), nominal_sigma * 10.0, False

        # Attenuation increases measurement dispersion
        sigma_inflated = nominal_sigma / max(1e-2, t_factor)
        noise = float(rng.normal(0.0, sigma_inflated))
        measured = max(0.05, true_range + noise)
        return measured, sigma_inflated, False


class OnlineCovarianceEstimator:
    """
    Real-time recursive innovation covariance estimator.
    Tracks empirical measurement residuals over a sliding window or EMA filter.
    Directly feeds sigma_p and sigma_v to the AEGIS Observability Gate.
    """

    def __init__(
        self,
        window_size: int = 15,
        nominal_sigma_p: float = 0.05,
        nominal_sigma_v: float = 0.08,
        blackout_sigma_thresh: float = 0.25,
        forgetting_factor: float = 0.88,
    ):
        self.window_size = window_size
        self.nominal_sigma_p = nominal_sigma_p
        self.nominal_sigma_v = nominal_sigma_v
        self.blackout_sigma_thresh = blackout_sigma_thresh
        self.alpha = 1.0 - forgetting_factor

        self._p_residuals: list[float] = []
        self._v_residuals: list[float] = []
        self.current_sigma_p: float = nominal_sigma_p
        self.current_sigma_v: float = nominal_sigma_v
        self.consecutive_blackouts: int = 0

    def update(
        self,
        predicted_pos: np.ndarray,
        measured_pos: np.ndarray,
        predicted_vel: np.ndarray,
        measured_vel: np.ndarray,
        is_dropout: bool = False,
    ) -> Tuple[float, float, bool]:
        """
        Updates covariance estimates.
        Returns:
            (sigma_p, sigma_v, is_blackout_triggered)
        """
        if is_dropout or np.any(np.isnan(measured_pos)) or np.any(np.isinf(measured_pos)):
            # Complete blackout step: rapidly inflate covariance
            self.consecutive_blackouts += 1
            self.current_sigma_p = min(1.5, self.current_sigma_p * 1.35 + 0.08)
            self.current_sigma_v = min(2.0, self.current_sigma_v * 1.35 + 0.10)
            is_blackout = self.current_sigma_p > self.blackout_sigma_thresh
            return self.current_sigma_p, self.current_sigma_v, is_blackout

        # Valid measurement received: compute residual norms
        self.consecutive_blackouts = 0
        r_p = float(np.linalg.norm(measured_pos - predicted_pos))
        r_v = float(np.linalg.norm(measured_vel - predicted_vel))

        self._p_residuals.append(r_p)
        self._v_residuals.append(r_v)
        if len(self._p_residuals) > self.window_size:
            self._p_residuals.pop(0)
            self._v_residuals.pop(0)

        # Empirical standard deviation from window residuals
        sample_std_p = float(np.std(self._p_residuals)) if len(self._p_residuals) > 1 else r_p
        sample_std_v = float(np.std(self._v_residuals)) if len(self._v_residuals) > 1 else r_v

        # Exponential moving average smoothing
        raw_p = max(self.nominal_sigma_p, sample_std_p)
        raw_v = max(self.nominal_sigma_v, sample_std_v)

        self.current_sigma_p = (1.0 - self.alpha) * self.current_sigma_p + self.alpha * raw_p
        self.current_sigma_v = (1.0 - self.alpha) * self.current_sigma_v + self.alpha * raw_v

        is_blackout = (self.current_sigma_p > self.blackout_sigma_thresh) or (self.current_sigma_v > 0.40)
        return self.current_sigma_p, self.current_sigma_v, is_blackout

    def reset(self):
        self._p_residuals.clear()
        self._v_residuals.clear()
        self.current_sigma_p = self.nominal_sigma_p
        self.current_sigma_v = self.nominal_sigma_v
        self.consecutive_blackouts = 0
