"""
NEXVIA AEGIS V6.0 — Multi-Hypothesis Fault Models & Likelihood Formulations.

Defines competing fault hypotheses (H0–H6), observation likelihoods,
and diagnostic evidence models for physical AI under sensor uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import numpy as np


class FaultHypothesis(str, Enum):
    """Configurable candidate fault hypotheses for cross-modal physical AI."""
    H0_NOMINAL = "H0_NOMINAL"                   # All sensors operating within nominal bounds
    H1_VECTOR_BIAS = "H1_VECTOR_BIAS"           # Constant spatial bias in primary vector sensor
    H2_VECTOR_DRIFT = "H2_VECTOR_DRIFT"         # Time-varying non-stationary drift
    H3_REFERENCE_FAULT = "H3_REFERENCE_FAULT"   # Corrupted scalar range reference sensor
    H4_CORRELATED_BIAS = "H4_CORRELATED_BIAS"   # Shared common-mode bias across vector sensors
    H5_SENSOR_DROPOUT = "H5_SENSOR_DROPOUT"     # Transient packet loss or zero-voltage dropout
    H6_AMBIGUOUS = "H6_AMBIGUOUS"               # Low observability, rank deficiency, or high entropy


@dataclass
class HypothesisEvidence:
    """Quantitative evidence metrics evaluated over an observation window."""
    window_length: int
    vector_disagreement: float      # Mean Euclidean norm between vector sensor A and B
    nominal_residual: float         # Mean cross-modal residual assuming b = 0: | ||z|| - r |
    bias_fit_residual: float        # Residual after optimal Huber/OLS bias correction
    range_discrepancy_std: float    # Std dev of (||z|| - r) over time (constant for range bias)
    residual_temporal_slope: float  # Slope of residual over time (positive for drift)
    fim_min_eigenvalue: float       # Smallest eigenvalue of Fisher Information Matrix
    fim_condition_number: float     # Condition number of Fisher Information Matrix
    dropout_fraction: float         # Fraction of invalid/dropped sensor packets
    best_estimated_bias: np.ndarray # Estimated vector bias [bx, by]


@dataclass
class HypothesisScore:
    """Individual score and calibrated probability for a fault hypothesis."""
    hypothesis: FaultHypothesis
    log_likelihood: float
    probability: float
    confidence: float
    description: str


@dataclass
class DiagnosticReport:
    """Comprehensive multi-hypothesis diagnostic state returned by the diagnosis engine."""
    leading_hypothesis: FaultHypothesis
    scores: dict[FaultHypothesis, HypothesisScore]
    probabilities: dict[str, float]
    entropy: float
    is_ambiguous: bool
    can_recalibrate: bool
    estimated_bias: np.ndarray
    reason_code: str
    evidence: HypothesisEvidence | None = None


def compute_fisher_information(
    vector_observations: list[np.ndarray],
    bias_candidate: np.ndarray,
) -> tuple[np.ndarray, float, float]:
    """
    Computes Fisher Information Matrix for 2D relative displacement measurements:
        z_t = d_t + b + eps_t
        r_t = ||d_t|| + nu_t
    Unit line-of-sight vector u_t = (z_t - b) / ||z_t - b||
    FIM F = sum_t (u_t u_t^T)
    """
    if len(vector_observations) < 2:
        return np.zeros((2, 2)), 0.0, float("inf")

    fim = np.zeros((2, 2), dtype=np.float64)
    for z in vector_observations:
        corrected = z - bias_candidate
        norm = float(np.linalg.norm(corrected))
        if norm > 1e-6:
            u = corrected / norm
            fim += np.outer(u, u)

    eigvals = np.linalg.eigvalsh(fim)
    lambda_min = float(max(0.0, eigvals[0]))
    lambda_max = float(max(1e-12, eigvals[1]))
    cond = float(lambda_max / max(lambda_min, 1e-12))
    return fim, lambda_min, cond
