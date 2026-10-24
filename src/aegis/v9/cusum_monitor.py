"""
NEXVIA AEGIS V9.0 — Channel B: Complementary Page CUSUM Drift/Change-Point Detector.

Implements the Channel B drift detector from `docs/v9_risk_calibration_design.md`
(Section 2.1.4) and `docs/v9_experiment_protocol.md` (Section 3.4.1):
    z_{c,t} = min(e_{c,t} / sigma_{c,scale}, z_max)
    S_{c,0} = 0
    S_{c,t} = max(0, S_{c,t-1} + V_{c,t} * (z_{c,t} - kappa_{c,drift}))
    Alarm iff max_{c in C} S_{c,t} >= h_cusum.

IMPORTANT STATISTICAL STATUS CONSTRAINT:
Because Page's CUSUM reflects at zero via max(0, .), S_{c,t} is NOT a nonnegative
supermartingale (P_{H_0}(exists t >= 1 : S_{c,t} >= h) -> 1 as t -> infinity) and
MUST NEVER be described as Ville-anytime-valid. Instead, Channel B targets reduced
detection delay on late-onset or slowly ramping sensor faults after nominal intervals,
and its threshold h_cusum is calibrated jointly inside the closed-loop candidate
family Lambda via episode-level selective-risk LTT.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class CusumChannelSpec:
    """Configuration for a single Page CUSUM drift subchannel."""

    name: str
    sigma_scale: float
    kappa_drift: float
    z_max: float = 6.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Channel name must be non-empty.")
        if not math.isfinite(self.sigma_scale) or self.sigma_scale <= 0.0:
            raise ValueError(f"sigma_scale must be finite and > 0, got {self.sigma_scale}.")
        if not math.isfinite(self.kappa_drift) or self.kappa_drift <= 0.0:
            raise ValueError(f"kappa_drift must be finite and > 0, got {self.kappa_drift}.")
        if not math.isfinite(self.z_max) or self.z_max <= self.kappa_drift:
            raise ValueError(
                f"z_max ({self.z_max}) must be finite and strictly exceed kappa_drift ({self.kappa_drift})."
            )

    @classmethod
    def inter_sensor_ab(
        cls,
        sigma_a: float,
        sigma_b: float,
        *,
        name: str = "ab",
        kappa_drift: float = 1.80,
        z_max: float = 6.0,
    ) -> CusumChannelSpec:
        """
        Inter-sensor vector disagreement scale sqrt(sigma_a^2 + sigma_b^2).
        Nominal Rayleigh standardized mean is sqrt(pi/2) ~= 1.2533 < kappa_drift = 1.80.
        """
        if not (math.isfinite(sigma_a) and math.isfinite(sigma_b) and sigma_a > 0.0 and sigma_b > 0.0):
            raise ValueError("Sensor standard deviations must be finite and > 0.")
        scale = math.sqrt(sigma_a**2 + sigma_b**2)
        return cls(name=name, sigma_scale=scale, kappa_drift=kappa_drift, z_max=z_max)

    @classmethod
    def vector_range(
        cls,
        name: str,
        sigma_vec: float,
        sigma_range: float,
        *,
        kappa_drift: float = 1.60,
        z_max: float = 6.0,
    ) -> CusumChannelSpec:
        """
        Vector-vs-range discrepancy scale sqrt(sigma_vec^2 + sigma_range^2).
        Nominal folded-normal standardized mean away from origin is sqrt(2/pi) ~= 0.7979
        (and <= 1.2533 everywhere) < kappa_drift = 1.60.
        """
        if not (
            math.isfinite(sigma_vec)
            and math.isfinite(sigma_range)
            and sigma_vec > 0.0
            and sigma_range > 0.0
        ):
            raise ValueError("Sensor standard deviations must be finite and > 0.")
        scale = math.sqrt(sigma_vec**2 + sigma_range**2)
        return cls(name=name, sigma_scale=scale, kappa_drift=kappa_drift, z_max=z_max)


@dataclass(frozen=True)
class CusumStepResult:
    """Audit snapshot returned by MultiChannelCusumMonitor.update."""

    max_cusum: float
    is_alarm: bool
    invalid_input_detected: bool
    step_count: int
    channel_statistics: dict[str, float]
    triggered_channels: tuple[str, ...]


class MultiChannelCusumMonitor:
    """
    Deterministic multi-channel Page CUSUM change-point / drift detector.
    Explicitly NOT a Ville e-process.
    """

    def __init__(self, channels: Sequence[CusumChannelSpec], threshold_h: float = 8.0) -> None:
        if not channels:
            raise ValueError("MultiChannelCusumMonitor requires at least one channel.")
        if not math.isfinite(threshold_h) or threshold_h <= 0.0:
            raise ValueError(f"threshold_h must be finite and > 0, got {threshold_h}.")

        names = [c.name for c in channels]
        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate CUSUM channel names are not allowed: {names}.")

        self._specs: dict[str, CusumChannelSpec] = {c.name: c for c in channels}
        self._channel_order: tuple[str, ...] = tuple(names)
        self.threshold_h: float = float(threshold_h)
        self._stats: dict[str, float] = {name: 0.0 for name in self._channel_order}
        self._invalid_latched: bool = False
        self._step_count: int = 0

    @property
    def channel_names(self) -> tuple[str, ...]:
        return self._channel_order

    @property
    def statistics(self) -> dict[str, float]:
        return {name: float(self._stats[name]) for name in self._channel_order}

    @property
    def max_cusum(self) -> float:
        return max(self._stats.values())

    def reset(self) -> None:
        """Resets all CUSUM channel accumulators S_{c,t} to 0.0."""
        for name in self._channel_order:
            self._stats[name] = 0.0
        self._invalid_latched = False
        self._step_count = 0

    def update(self, observations: Mapping[str, tuple[float, bool]]) -> CusumStepResult:
        """
        Updates Page CUSUM statistics across all configured subchannels.

        Missing or invalid (`is_valid == False`) packets leave S_{c,t} = S_{c,t-1}.
        Non-finite (`NaN`, `Inf`) or negative (`< -1e-12`) values marked `is_valid == True`
        latch `invalid_input_detected = True` and fail closed (`is_alarm = True`).
        """
        self._step_count += 1

        cleaned_obs: dict[str, tuple[float, bool]] = {}
        for name in self._channel_order:
            raw_e, is_valid = observations.get(name, (0.0, False))
            valid_flag = bool(is_valid)
            if not valid_flag:
                cleaned_obs[name] = (0.0, False)
                continue

            try:
                e_val = float(raw_e)
            except (TypeError, ValueError):
                e_val = float("nan")

            if not math.isfinite(e_val) or e_val < -1e-12:
                self._invalid_latched = True
                return self._snapshot()

            cleaned_obs[name] = (max(0.0, e_val), True)

        if self._invalid_latched:
            return self._snapshot()

        for name in self._channel_order:
            spec = self._specs[name]
            e_t, valid_flag = cleaned_obs[name]
            if not valid_flag:
                continue
            z_t = min(e_t / spec.sigma_scale, spec.z_max)
            self._stats[name] = max(0.0, self._stats[name] + (z_t - spec.kappa_drift))

        return self._snapshot()

    def _snapshot(self) -> CusumStepResult:
        stats_copy = self.statistics
        triggered = tuple(
            name for name in self._channel_order if stats_copy[name] >= self.threshold_h
        )
        max_s = max(stats_copy.values())
        is_alarm = bool(self._invalid_latched or len(triggered) > 0)
        return CusumStepResult(
            max_cusum=float(max_s),
            is_alarm=is_alarm,
            invalid_input_detected=self._invalid_latched,
            step_count=self._step_count,
            channel_statistics=stats_copy,
            triggered_channels=triggered,
        )
