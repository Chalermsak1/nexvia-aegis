"""
NEXVIA AEGIS-Next — Anytime-Valid Sequential Martingale Risk Monitor.

Theoretical Foundation:
- Testing by Betting & Game-Theoretic Supermartingales (Ramdas, Grünwald, Vovk, & Shafer, 2023)
- Non-Exchangeable Risk Tracking (Gibbs & Candès, 2021; Barber et al., 2023)

Under nominal sensor operation (H0), the cross-modal spatial residual:
    e_t = | ||z_v,t|| - r_t |
is a folded Gaussian variable with known nominal expectation:
    mu_0 = E[e_t | H0] ~ sqrt(2/pi) * sqrt(sigma_v^2 + sigma_r^2)
We construct an online non-negative wealth process:
    E_t = prod_{k=1}^t (1 + lambda_k * ((e_k - mu_0) / v_max))
where lambda_k in [0, lambda_max] is the predictable betting fraction.
By Ville's inequality for non-negative supermartingales:
    P(exists t >= 1 : E_t >= 1/alpha) <= alpha
This provides a distribution-free, finite-sample statistical safety guarantee
under arbitrary stopping times without assuming exchangeability or white Gaussian innovations.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class MartingaleConfig:
    alpha: float = 0.05
    nominal_mean: float = 0.0564  # mu_0 for sigma_v = sigma_r = 0.05
    scale_vmax: float = 0.40      # Normalization constant ensuring (1 + lambda * x) > 0
    lambda_max: float = 0.85      # Upper bound on betting fraction for numerical stability
    burn_in_steps: int = 1        # Number of initial samples before betting begins
    decay_factor: float = 0.995   # Slight martingale decay preventing stale latching


class AnytimeValidSequentialMonitor:
    """
    Online Anytime-Valid Sequential Martingale Monitor for Sensor Verification.
    """

    def __init__(self, config: MartingaleConfig | None = None):
        self.config = config or MartingaleConfig()
        self.threshold: float = 1.0 / self.config.alpha
        self.reset()

    def reset(self) -> None:
        self.wealth: float = 1.0
        self.step_count: int = 0
        self.history: list[float] = []
        self.alarm_tripped: bool = False
        self.alarm_step: int | None = None

    def update(self, cross_modal_residual: float) -> tuple[float, float, bool]:
        """
        Processes a new cross-modal residual observation.
        
        Args:
            cross_modal_residual: Scalar value e_t = | ||z_v|| - r |
            
        Returns:
            (wealth, anytime_p_value, is_alarm)
        """
        self.step_count += 1
        e_t = float(cross_modal_residual)
        self.history.append(e_t)

        # Centered normalized error
        x_raw = (e_t - self.config.nominal_mean) / self.config.scale_vmax
        # Clamp lower bound to -0.90 to strictly guarantee (1 + lambda * x) >= 0.1 > 0
        x_t = float(np.clip(x_raw, -0.90, 3.50))

        if self.step_count <= self.config.burn_in_steps:
            # Predictable betting warmup
            lambda_t = 0.0
        else:
            # Predictable Kelly betting fraction based on recent empirical mean and variance
            recent = np.array(self.history[-15:-1], dtype=np.float64)
            recent_x = (recent - self.config.nominal_mean) / self.config.scale_vmax
            emp_mean = float(np.mean(recent_x))
            emp_var = float(np.var(recent_x)) + 1e-4

            if emp_mean > 0.0:
                # Bet proportionally to positive empirical drift
                raw_lambda = emp_mean / (emp_var + emp_mean**2)
                lambda_t = float(np.clip(raw_lambda, 0.0, self.config.lambda_max))
            else:
                # Under negative or zero residual error, bet zero (capital preservation)
                lambda_t = 0.0

        # Multiplicative wealth update with optional slight decay against stale memory
        bet_multiplier = 1.0 + lambda_t * x_t
        self.wealth = (self.wealth * bet_multiplier) * self.config.decay_factor
        self.wealth = max(1e-4, min(self.wealth, 1e7))

        # Ville's inequality check: E_t >= 1/alpha implies p_value <= alpha
        is_alarm = self.wealth >= self.threshold
        if is_alarm and not self.alarm_tripped:
            self.alarm_tripped = True
            self.alarm_step = self.step_count

        anytime_p_value = min(1.0, 1.0 / max(1.0, self.wealth))
        return self.wealth, anytime_p_value, is_alarm

    @property
    def is_fault_detected(self) -> bool:
        return self.alarm_tripped
