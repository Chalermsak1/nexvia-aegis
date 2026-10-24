"""
NEXVIA AEGIS V9.0 — Channel A: Exact Nonnegative Ville e-Process Monitor.

Implements Proposition 2.1 of `docs/v9_risk_calibration_design.md`:
- Multiplicative wealth update with gamma = 1.0 (no exponential forgetting).
- Strictly predictable betting fractions lambda_{c,t} in F_{t-1} (lambda_{c,1} = 0).
- Nonnegative wealth multipliers m_{c,t} = 1 + V_{c,t} * lambda_{c,t} * x_{c,t} >= 0.10 > 0
  without any reflecting lower floor or invalidating upper wealth cap.
- Equal-weight convex mixture E_t^{Ville} = (1 / |C|) * sum_{c in C} E_t^{(c)} across
  residual subchannels, requiring zero independence assumption across subchannels.

IMPORTANT STATISTICAL SCOPE & VALIDITY BOUNDARIES:
1. Tested Null Hypothesis (H_{0,mon}):
   For every active subchannel c in C and every step t >= 1,
       E[e_{c,t} | F_{t-1}, V_{c,t} = 1] <= mu_{0,c},
   with e_{c,t} >= 0 almost surely when V_{c,t} = 1.
2. Under H_{0,mon}, (E_t^{Ville})_{t >= 0} is a nonnegative supermartingale with E_0 = 1,
   so Ville's inequality guarantees:
       P_{H_{0,mon}}(exists t >= 1 : E_t^{Ville} >= 1 / alpha) <= alpha.
3. Log-space arithmetic (log_wealth_mixture = ln E_t^{Ville}) is used internally strictly
   to represent positive wealth without IEEE-754 overflow/underflow. Log-wealth itself is
   NOT an e-process and is never labeled as one.
4. Validity Boundaries:
   - Violated under heavy-tailed outlier contamination (e.g., 12% 4.5x bursts where
     E[e_{c,t}] > mu_{0,c}), understated sensor sigma, or nonzero bias estimation error
     (Delta b_k = b_k - b_hat_k != 0 in post-calibration monitoring).
   - Controlling nominal Type-I monitor false alarms under H_{0,mon} NEVER directly bounds
     closed-loop selective false-success risk R_sel(pi) under faults.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import numpy as np
from scipy.special import logsumexp


@dataclass(frozen=True)
class VilleChannelSpec:
    """Configuration for a single nonnegative residual subchannel c in C."""

    name: str
    mu0: float
    vmax: float = 0.40
    x_max: float = 3.50
    lambda_max: float = 0.85
    window_lambda: int = 14
    eps_lambda: float = 1e-2

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Channel name must be non-empty.")
        if not math.isfinite(self.mu0) or self.mu0 <= 0.0:
            raise ValueError(f"mu0 must be finite and > 0, got {self.mu0}.")
        if not math.isfinite(self.vmax) or self.vmax <= 0.0:
            raise ValueError(f"vmax must be finite and > 0, got {self.vmax}.")
        if not math.isfinite(self.x_max) or self.x_max <= 0.0:
            raise ValueError(f"x_max must be finite and > 0, got {self.x_max}.")
        if not math.isfinite(self.lambda_max) or not (0.0 < self.lambda_max < 1.0):
            raise ValueError(f"lambda_max must lie in (0, 1), got {self.lambda_max}.")
        if self.window_lambda < 1:
            raise ValueError(f"window_lambda must be >= 1, got {self.window_lambda}.")
        if not math.isfinite(self.eps_lambda) or self.eps_lambda <= 0.0:
            raise ValueError(f"eps_lambda must be > 0, got {self.eps_lambda}.")

    @property
    def predictable_lambda_cap(self) -> float:
        """
        F_0-measurable upper bound bar_lambda_c = min(lambda_max, 0.90 * vmax / mu0).
        Ensures 1 + lambda_{c,t} * x_{c,t} >= 1 - 0.90 = 0.10 > 0 for all e_{c,t} >= 0.
        """
        return min(self.lambda_max, (0.90 * self.vmax) / self.mu0)

    @classmethod
    def inter_sensor_ab(
        cls,
        sigma_a: float,
        sigma_b: float,
        *,
        name: str = "ab",
        vmax: float = 0.40,
        x_max: float = 3.50,
        lambda_max: float = 0.85,
        window_lambda: int = 14,
    ) -> VilleChannelSpec:
        """
        Constructs subchannel spec for e_{ab,t} = ||z_{a,t} - z_{b,t}||_2.
        Under unbiased 2D isotropic Gaussian noise, ||eps_a - eps_b||_2 follows
        Rayleigh(sqrt(sigma_a^2 + sigma_b^2)) with exact mean sqrt((pi/2)*(sigma_a^2 + sigma_b^2)).
        """
        if not (math.isfinite(sigma_a) and math.isfinite(sigma_b) and sigma_a > 0.0 and sigma_b > 0.0):
            raise ValueError("Sensor standard deviations must be finite and > 0.")
        mu0 = math.sqrt(0.5 * math.pi * (sigma_a**2 + sigma_b**2))
        return cls(
            name=name,
            mu0=mu0,
            vmax=vmax,
            x_max=x_max,
            lambda_max=lambda_max,
            window_lambda=window_lambda,
        )

    @classmethod
    def vector_range(
        cls,
        name: str,
        sigma_vec: float,
        sigma_range: float,
        *,
        vmax: float = 0.40,
        x_max: float = 3.50,
        lambda_max: float = 0.85,
        window_lambda: int = 14,
    ) -> VilleChannelSpec:
        """
        Constructs subchannel spec for e_{vr,k,t} = | ||z_{k,t}||_2 - r_t |.
        By 1-Lipschitz clamping of r_t = max(0, ||d_t|| + nu_t) and the reverse triangle
        inequality, e_{vr,k,t} <= ||eps_{k,t}||_2 + |nu_t| pointwise for all d_t in R^2,
        giving analytical upper mean bound sigma_vec*sqrt(pi/2) + sigma_range*sqrt(2/pi).
        """
        if not (
            math.isfinite(sigma_vec)
            and math.isfinite(sigma_range)
            and sigma_vec > 0.0
            and sigma_range > 0.0
        ):
            raise ValueError("Sensor standard deviations must be finite and > 0.")
        mu0 = sigma_vec * math.sqrt(0.5 * math.pi) + sigma_range * math.sqrt(2.0 / math.pi)
        return cls(
            name=name,
            mu0=mu0,
            vmax=vmax,
            x_max=x_max,
            lambda_max=lambda_max,
            window_lambda=window_lambda,
        )


@dataclass(frozen=True)
class VilleStepResult:
    """Audit snapshot returned by MultiChannelVilleMonitor.update."""

    wealth: float
    max_wealth: float
    log_wealth_mixture: float
    anytime_p_value: float
    is_alarm: bool
    invalid_input_detected: bool
    step_count: int
    subchannel_wealths: dict[str, float]
    subchannel_log_wealths: dict[str, float]
    subchannel_lambdas: dict[str, float]
    subchannel_multipliers: dict[str, float]


class MultiChannelVilleMonitor:
    """
    Exact gamma = 1.0 nonnegative Ville e-process mixture across residual subchannels.

    Note: `wealth` is the nonnegative e-process E_t^{Ville} (with E_0^{Ville} = 1.0).
    `log_wealth_mixture` stores ln(E_t^{Ville}) strictly for numerical representation of
    positive wealth without floating-point overflow or underflow; log-wealth is NOT an e-process.
    """

    _MAX_EXP_ARG: float = 709.78

    def __init__(self, channels: Sequence[VilleChannelSpec], alpha: float = 0.05) -> None:
        if not channels:
            raise ValueError("MultiChannelVilleMonitor requires at least one channel.")
        if not math.isfinite(alpha) or not (0.0 < alpha < 1.0):
            raise ValueError(f"alpha must lie strictly in (0, 1), got {alpha}.")

        names = [c.name for c in channels]
        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate Ville channel names are not allowed: {names}.")

        self._specs: dict[str, VilleChannelSpec] = {c.name: c for c in channels}
        self._channel_order: tuple[str, ...] = tuple(names)
        self.alpha: float = float(alpha)
        self.threshold_wealth: float = 1.0 / self.alpha
        self._log_threshold: float = math.log(self.threshold_wealth)

        self._log_wealths: dict[str, float] = {name: 0.0 for name in self._channel_order}
        self._past_valid_scores: dict[str, list[float]] = {name: [] for name in self._channel_order}
        self._max_log_wealth_mixture: float = 0.0
        self._invalid_latched: bool = False
        self._step_count: int = 0

    @property
    def channel_names(self) -> tuple[str, ...]:
        return self._channel_order

    def reset(self) -> None:
        """Resets e-process wealth to E_0 = 1.0 (log-wealth 0.0) and clears all history."""
        for name in self._channel_order:
            self._log_wealths[name] = 0.0
            self._past_valid_scores[name].clear()
        self._max_log_wealth_mixture = 0.0
        self._invalid_latched = False
        self._step_count = 0

    @staticmethod
    def _exp_safe(log_val: float) -> float:
        if log_val >= MultiChannelVilleMonitor._MAX_EXP_ARG:
            return float("inf")
        return float(math.exp(log_val))

    @property
    def log_wealth_mixture(self) -> float:
        """Natural logarithm ln(E_t^{Ville}) of the equal-weight mixture wealth (NOT an e-process)."""
        lw = np.array([self._log_wealths[name] for name in self._channel_order], dtype=np.float64)
        return float(logsumexp(lw) - math.log(len(self._channel_order)))

    @property
    def wealth(self) -> float:
        """Current nonnegative mixture e-process value E_t^{Ville} > 0."""
        return self._exp_safe(self.log_wealth_mixture)

    @property
    def max_wealth(self) -> float:
        """Running supremum max_{0 <= s <= t} E_s^{Ville}."""
        return self._exp_safe(self._max_log_wealth_mixture)

    @property
    def anytime_p_value(self) -> float:
        """Anytime-valid p-value p_t = min(1, inf_{0 <= s <= t} 1 / E_s^{Ville}) under H_{0,mon}."""
        if self._max_log_wealth_mixture <= 0.0:
            return 1.0
        return float(math.exp(-self._max_log_wealth_mixture))

    def compute_predictable_lambda(self, channel_name: str) -> float:
        """
        Computes F_{t-1}-measurable betting parameter lambda_{c,t} strictly from valid
        observations prior to step t. Returns 0.0 when no prior valid observation exists.
        """
        spec = self._specs[channel_name]
        hist = self._past_valid_scores[channel_name]
        if not hist:
            return 0.0

        recent = np.asarray(hist[-spec.window_lambda :], dtype=np.float64)
        x_bar = float(np.mean(recent))
        if x_bar <= 0.0:
            return 0.0
        var_x = float(np.var(recent))
        lam_raw = x_bar / (var_x + x_bar * x_bar + spec.eps_lambda)
        return float(np.clip(lam_raw, 0.0, spec.predictable_lambda_cap))

    def update(self, observations: Mapping[str, tuple[float, bool]]) -> VilleStepResult:
        """
        Updates all subchannels at step t.

        Args:
            observations: Mapping channel_name -> (residual_e_t, is_valid).
                Missing channels default to (0.0, False) (packet dropout / unmeasured).
                If is_valid is True and residual_e_t is NaN, Inf, or negative (< -1e-12),
                latches `invalid_input_detected = True` and fails closed (`is_alarm = True`)
                without corrupting wealth state.
        """
        self._step_count += 1
        lambdas_used: dict[str, float] = {}
        multipliers_used: dict[str, float] = {}

        # First pass: validate all active inputs before mutating state so malformed
        # inputs fail closed cleanly without partial state corruption.
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
                for ch in self._channel_order:
                    lambdas_used[ch] = 0.0
                    multipliers_used[ch] = 1.0
                return self._snapshot(lambdas_used, multipliers_used)

            cleaned_obs[name] = (max(0.0, e_val), True)

        if self._invalid_latched:
            for ch in self._channel_order:
                lambdas_used[ch] = 0.0
                multipliers_used[ch] = 1.0
            return self._snapshot(lambdas_used, multipliers_used)

        # Second pass: exact gamma = 1.0 predictable multiplicative update per channel.
        for name in self._channel_order:
            spec = self._specs[name]
            e_t, valid_flag = cleaned_obs[name]

            # 1. Compute predictable lambda_{c,t} BEFORE using or recording step t.
            lam_t = self.compute_predictable_lambda(name)
            lambdas_used[name] = lam_t

            if not valid_flag:
                multipliers_used[name] = 1.0
                continue

            # 2. Upper-only concave score x_{c,t} = min((e_{c,t} - mu_{0,c}) / vmax_c, x_max_c).
            # No lower floor is applied; since e_{c,t} >= 0 and lam_t <= 0.90*vmax_c/mu_{0,c},
            # m_{c,t} = 1 + lam_t * x_{c,t} >= 0.10 > 0 holds identically.
            x_t = min((e_t - spec.mu0) / spec.vmax, spec.x_max)
            prod = lam_t * x_t
            m_t = 1.0 + prod
            if m_t <= 0.0:  # Defensive invariant guard
                raise RuntimeError(f"Non-positive Ville multiplier {m_t} in channel {name}.")

            self._log_wealths[name] += math.log1p(prod)
            multipliers_used[name] = m_t

            # 3. Append x_t to history strictly AFTER step-t wealth update.
            hist = self._past_valid_scores[name]
            hist.append(float(x_t))
            if len(hist) > spec.window_lambda:
                del hist[: len(hist) - spec.window_lambda]

        curr_log_mix = self.log_wealth_mixture
        if curr_log_mix > self._max_log_wealth_mixture:
            self._max_log_wealth_mixture = curr_log_mix

        return self._snapshot(lambdas_used, multipliers_used)

    def _snapshot(
        self,
        lambdas_used: dict[str, float],
        multipliers_used: dict[str, float],
    ) -> VilleStepResult:
        curr_log_mix = self.log_wealth_mixture
        curr_wealth = self._exp_safe(curr_log_mix)
        max_w = self.max_wealth
        # Exact boundary equivalence in both wealth and log-wealth domains
        threshold_crossed = (curr_wealth >= self.threshold_wealth) or (
            curr_log_mix >= self._log_threshold
        )
        is_alarm = bool(self._invalid_latched or threshold_crossed)

        sub_log = {name: float(self._log_wealths[name]) for name in self._channel_order}
        sub_w = {name: self._exp_safe(self._log_wealths[name]) for name in self._channel_order}
        return VilleStepResult(
            wealth=curr_wealth,
            max_wealth=max_w,
            log_wealth_mixture=curr_log_mix,
            anytime_p_value=self.anytime_p_value,
            is_alarm=is_alarm,
            invalid_input_detected=self._invalid_latched,
            step_count=self._step_count,
            subchannel_wealths=sub_w,
            subchannel_log_wealths=sub_log,
            subchannel_lambdas=dict(lambdas_used),
            subchannel_multipliers=dict(multipliers_used),
        )
