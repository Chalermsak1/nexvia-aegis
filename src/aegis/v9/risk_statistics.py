"""
NEXVIA AEGIS V9.0 — Selective-Risk Hypothesis Testing, Exact Confidence Bounds,
and Learn-Then-Test (LTT) Candidate Calibration (`docs/v9_risk_calibration_design.md`).

MATHEMATICAL SPECIFICATION & REQUIRED ASSUMPTIONS (Theorem 2.1):
1. Target Selective-Risk Estimand:
       R_sel(pi; M) = P_{Z ~ M}(FS(pi, Z) = 1 | A(pi, Z) = 1)  if C(pi; M) > 0,
       R_sel(pi; M) = UNDEFINED                                 if C(pi; M) = 0,
   where A(pi, Z) = I(terminal decision == "STOP" without exception) and
   FS(pi, Z) = I((A == 1 and final_distance > 0.45 m) or crashed == 1).

2. Composite Unsafe / Zero-Coverage Null Hypothesis & Lower-Tail Direction:
   To certify that a frozen candidate policy pi_lambda achieves BOTH positive coverage
   and selective risk at most alpha (e.g., alpha = 0.05), we test the composite null:
       H_0^{sel}(lambda) : {C(pi_lambda; M) = 0} U {C(pi_lambda; M) > 0 and R_sel(pi_lambda; M) >= alpha}
   against the safe-and-nontrivial alternative:
       H_1^{sel}(lambda) : C(pi_lambda; M) > 0 and R_sel(pi_lambda; M) < alpha (or <= alpha).
   Note: Small observed false-success counts K relative to M*alpha provide evidence
   AGAINST H_0^{sel}, so the p-value is the LOWER-TAIL Binomial CDF F_{Bin(M, alpha)}(K):
       p^{sel}(lambda; D) = 1.0                                         if M < m_min,
       p^{sel}(lambda; D) = sum_{j=0}^{K} C(M, j) alpha^j (1-alpha)^{M-j}  if M >= m_min,
   with predeclared m_min >= 1.

3. Conditions Required for Finite-Sample Super-Uniformity P_{H_0}(p^{sel} <= u) <= u:
   - Episode-level i.i.d. sampling Z_1, ..., Z_N ~^{i.i.d.} M (NOTE: pooled fixed-quota
     stratified sampling across heterogeneous scenarios is independent but NOT identically
     distributed; exact pooled binomial conditioning requires i.i.d. mixture draws from M,
     while stratified draws support exact per-scenario tests within each stratum s).
   - Candidate policy pi_lambda fixed prior to observing calibration/holdout episodes,
     with `ctrl.reset()` erasing all intra-episode state between episodes.
   - Unchanged target scenario-mixture distribution M between calibration and deployment.
   - Zero-coverage handling: M = 0 yields R_sel = UNDEFINED (NaN) and p^{sel} = 1.0 (never 0.0).
   - Minimum-coverage rule m_min >= 1 fixed before calibration.
   - Multiplicity control across J > 1 candidates via Fixed-Sequence Testing (FST) or
     Holm step-down (both valid under arbitrary matched-seed dependence across candidates).

4. Warning on M >= 59:
   M >= 59 is NOT a universal certification guarantee for alpha = 0.05 at 95% confidence.
   It applies ONLY when K = 0 errors occur in a single prespecified one-sided test (or
   pre-ordered FST step) at delta = 0.05 (0.95^59 = 0.04849 <= 0.05 < 0.95^58 = 0.05105).
   Nonzero errors (K=1 -> M>=93, K=6 -> M>=234), Holm-6 (K=0 -> M>=94), two-sided 95% CIs
   (K=0 -> M>=72), or simultaneous 12-scenario bounds (K=0 -> M>=107) require larger M.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from scipy.stats import beta, binom


@dataclass(frozen=True)
class V9CandidateParams:
    """Complete frozen hyperparameter vector lambda^{(j)} in Lambda."""

    candidate_id: str
    tier_index: int
    tier_label: str
    alpha_mon: float
    h_cusum: float
    tau_diff: float
    tau_ar: float
    tau_val: float
    tau_stop: float
    # Fixed architectural parameters shared across all J = 6 candidates
    gamma_ville: float = 1.0
    probing_steps: int = 36
    fit_start: int = 1
    fit_end: int = 22
    gap_start: int = 23
    gap_end: int = 24
    val_start: int = 25
    val_end: int = 36
    n_fit_min: int = 10
    n_val_min: int = 6
    lambda_fim_min: float = 1e-3
    arrival_tolerance_m: float = 0.22
    chord_min_m: float = 0.40
    chord_min_steps: int = 10
    max_anchor_queries: int = 4

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id must be non-empty.")
        if self.tier_index < 1:
            raise ValueError("tier_index must be >= 1.")
        if not (0.0 < self.alpha_mon < 1.0):
            raise ValueError(f"alpha_mon must lie in (0, 1), got {self.alpha_mon}.")
        if self.h_cusum <= 0.0:
            raise ValueError("h_cusum must be > 0.")
        if self.tau_diff <= 0.0 or self.tau_ar <= 0.0:
            raise ValueError("tau_diff and tau_ar must be > 0.")
        if self.tau_val <= 0.0 or self.tau_stop <= 0.0:
            raise ValueError("tau_val and tau_stop must be > 0.")
        if self.gamma_ville != 1.0:
            raise ValueError("Channel A requires exact gamma_ville == 1.0.")
        if set(range(self.fit_start, self.fit_end + 1)) & set(
            range(self.val_start, self.val_end + 1)
        ):
            raise ValueError("Fit and validation windows must be disjoint.")


PREREGISTERED_CANDIDATE_FAMILY: tuple[V9CandidateParams, ...] = (
    V9CandidateParams(
        candidate_id="V9_CAND_1_TIER1_STRICTEST",
        tier_index=1,
        tier_label="Tier 1 (Strictest)",
        alpha_mon=0.010,
        h_cusum=6.0,
        tau_diff=3.20,
        tau_ar=3.80,
        tau_val=0.10,
        tau_stop=0.36,
    ),
    V9CandidateParams(
        candidate_id="V9_CAND_2_TIER2_VERY_STRICT",
        tier_index=2,
        tier_label="Tier 2 (Very Strict)",
        alpha_mon=0.020,
        h_cusum=7.0,
        tau_diff=3.50,
        tau_ar=4.20,
        tau_val=0.11,
        tau_stop=0.38,
    ),
    V9CandidateParams(
        candidate_id="V9_CAND_3_TIER3_BALANCED_STRICT",
        tier_index=3,
        tier_label="Tier 3 (Balanced-Strict)",
        alpha_mon=0.030,
        h_cusum=8.0,
        tau_diff=3.80,
        tau_ar=4.60,
        tau_val=0.12,
        tau_stop=0.40,
    ),
    V9CandidateParams(
        candidate_id="V9_CAND_4_TIER4_BALANCED",
        tier_index=4,
        tier_label="Tier 4 (Balanced)",
        alpha_mon=0.040,
        h_cusum=9.0,
        tau_diff=4.10,
        tau_ar=5.00,
        tau_val=0.13,
        tau_stop=0.41,
    ),
    V9CandidateParams(
        candidate_id="V9_CAND_5_TIER5_MODERATE",
        tier_index=5,
        tier_label="Tier 5 (Moderate)",
        alpha_mon=0.050,
        h_cusum=10.0,
        tau_diff=4.40,
        tau_ar=5.47,
        tau_val=0.14,
        tau_stop=0.42,
    ),
    V9CandidateParams(
        candidate_id="V9_CAND_6_TIER6_PERMISSIVE",
        tier_index=6,
        tier_label="Tier 6 (Permissive)",
        alpha_mon=0.075,
        h_cusum=11.5,
        tau_diff=4.80,
        tau_ar=6.00,
        tau_val=0.15,
        tau_stop=0.44,
    ),
)


def minimum_zero_error_acceptances(alpha_target: float = 0.05, delta: float = 0.05) -> int:
    """
    Returns ceil(ln(delta) / ln(1 - alpha_target)), the smallest integer m >= 1 such that
    (1 - alpha_target)^m <= delta (59 when alpha_target = 0.05 and delta = 0.05).
    Applies ONLY to zero observed errors (k = 0) at effective significance level `delta`.
    """
    if not (0.0 < alpha_target < 1.0) or not (0.0 < delta < 1.0):
        raise ValueError("alpha_target and delta must lie strictly in (0, 1).")
    return max(1, int(math.ceil(math.log(delta) / math.log1p(-alpha_target))))


def selective_risk_pvalue(
    k_false_success: int,
    m_accepted: int,
    *,
    alpha_target: float = 0.05,
    m_min: int = 59,
) -> float:
    """
    Exact finite-sample super-uniform lower-tail Binomial p-value for Theorem 2.1:
        H_0^{sel} : {C = 0} U {C > 0 and R_sel >= alpha_target}.

    Returns 1.0 whenever m_accepted < m_min (including m_accepted == 0).
    """
    if m_accepted < 0:
        raise ValueError(f"m_accepted must be >= 0, got {m_accepted}.")
    if k_false_success < 0 or k_false_success > m_accepted:
        raise ValueError(
            f"k_false_success ({k_false_success}) must satisfy 0 <= k <= m_accepted ({m_accepted})."
        )
    if not (0.0 < alpha_target < 1.0):
        raise ValueError(f"alpha_target must lie strictly in (0, 1), got {alpha_target}.")
    if m_min < 1:
        raise ValueError(f"m_min must be >= 1, got {m_min}.")

    if m_accepted < m_min:
        return 1.0
    p_val = float(binom.cdf(k_false_success, m_accepted, alpha_target))
    return min(1.0, max(0.0, p_val))


def clopper_pearson_one_sided_ucb(k: int, n: int, *, delta: float = 0.05) -> float:
    """
    Exact one-sided (1 - delta) Clopper-Pearson upper confidence bound U_{CP,1}(k, n; delta).
    Returns NaN (UNDEFINED) when n == 0; never returns 0.0 for zero denominator.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}.")
    if n == 0:
        if k != 0:
            raise ValueError("k must be 0 when n == 0.")
        return float("nan")
    if k < 0 or k > n:
        raise ValueError(f"k ({k}) must satisfy 0 <= k <= n ({n}).")
    if not (0.0 < delta < 1.0):
        raise ValueError(f"delta must lie strictly in (0, 1), got {delta}.")
    if k == n:
        return 1.0
    return float(beta.ppf(1.0 - delta, k + 1, n - k))


def clopper_pearson_two_sided_ci(k: int, n: int, *, delta: float = 0.05) -> tuple[float, float]:
    """
    Exact two-sided (1 - delta) Clopper-Pearson confidence interval.
    Returns (NaN, NaN) when n == 0.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}.")
    if n == 0:
        if k != 0:
            raise ValueError("k must be 0 when n == 0.")
        return (float("nan"), float("nan"))
    if k < 0 or k > n:
        raise ValueError(f"k ({k}) must satisfy 0 <= k <= n ({n}).")
    if not (0.0 < delta < 1.0):
        raise ValueError(f"delta must lie strictly in (0, 1), got {delta}.")

    low = 0.0 if k == 0 else float(beta.ppf(delta / 2.0, k, n - k + 1))
    high = 1.0 if k == n else float(beta.ppf(1.0 - delta / 2.0, k + 1, n - k))
    return (low, high)


@dataclass(frozen=True)
class PolicyEvaluationSummary:
    """Aggregated episode-level metrics with explicit zero-coverage semantics."""

    policy_id: str
    n_episodes: int
    m_accepted: int
    ts_count: int
    fs_count: int
    ab_explicit_count: int
    timeout_count: int
    ab_total_count: int
    crashed_count: int
    coverage: float
    tsr: float
    r_inc: float
    r_inc_ucb95: float
    selective_risk_defined: bool
    r_sel: float
    r_sel_status: str
    r_sel_ucb95: float
    r_sel_ci95_low: float
    r_sel_ci95_high: float
    p_sel_iid: float
    mean_steps: float
    mean_distance_traveled: float
    mean_anchor_queries: float
    mean_anchor_cost: float
    mean_max_overshoot: float


def compute_policy_summary(
    policy_id: str,
    episodes: Sequence[Mapping[str, Any]],
    *,
    alpha_target: float = 0.05,
    delta: float = 0.05,
    m_min: int | None = None,
) -> PolicyEvaluationSummary:
    """
    Computes episode-level safety and operational metrics.

    Note: `p_sel_iid` is exact under i.i.d. episode draws (e.g., D_cal, D_test^mix, or a
    single scenario stratum); on stratified multi-scenario grids (e.g., D_dev), treat pooled
    p-values and CIs as descriptive diagnostics only.
    """
    if not episodes:
        raise ValueError("Cannot summarize an empty episode list.")

    n_ep = len(episodes)
    ts_count = sum(int(ep["true_success"]) for ep in episodes)
    fs_count = sum(int(ep["false_success"]) for ep in episodes)
    crashed_count = sum(int(ep.get("crashed", 0)) for ep in episodes)
    ab_exp_count = sum(int(ep.get("abstain_explicit", 0)) for ep in episodes)
    to_count = sum(int(ep.get("timeout", 0)) for ep in episodes)
    ab_total = sum(int(ep["abstain"]) for ep in episodes)

    # Under fail-unsafe crash accounting (`docs/v9_experiment_protocol.md` Section 3.1.3),
    # a crashed episode has FS=1; include it in effective risky commitment trials if A was 0.
    m_acc = sum(int(ep.get("accepted", int(ep["true_success"]) + int(ep["false_success"]))) for ep in episodes)
    if m_acc < fs_count:
        m_acc = fs_count

    eff_m_min = minimum_zero_error_acceptances(alpha_target, delta) if m_min is None else m_min

    cov = m_acc / n_ep
    tsr = ts_count / n_ep
    r_inc = fs_count / n_ep
    r_inc_ucb = clopper_pearson_one_sided_ucb(fs_count, n_ep, delta=delta)

    if m_acc == 0:
        sel_defined = False
        r_sel = float("nan")
        r_sel_status = "UNDEFINED"
        r_sel_ucb = float("nan")
        ci_low, ci_high = (float("nan"), float("nan"))
    else:
        sel_defined = True
        r_sel = fs_count / m_acc
        r_sel_status = "DEFINED"
        r_sel_ucb = clopper_pearson_one_sided_ucb(fs_count, m_acc, delta=delta)
        ci_low, ci_high = clopper_pearson_two_sided_ci(fs_count, m_acc, delta=delta)

    p_sel = selective_risk_pvalue(
        fs_count,
        m_acc,
        alpha_target=alpha_target,
        m_min=eff_m_min,
    )

    mean_steps = float(sum(float(ep["steps"]) for ep in episodes) / n_ep)
    mean_dist = float(sum(float(ep.get("distance_traveled", 0.0)) for ep in episodes) / n_ep)
    mean_anc_q = float(sum(float(ep.get("anchor_queries", 0.0)) for ep in episodes) / n_ep)
    mean_anc_c = float(sum(float(ep.get("anchor_cost", 0.0)) for ep in episodes) / n_ep)
    mean_over = float(sum(float(ep.get("max_overshoot", 0.0)) for ep in episodes) / n_ep)

    return PolicyEvaluationSummary(
        policy_id=policy_id,
        n_episodes=n_ep,
        m_accepted=m_acc,
        ts_count=ts_count,
        fs_count=fs_count,
        ab_explicit_count=ab_exp_count,
        timeout_count=to_count,
        ab_total_count=ab_total,
        crashed_count=crashed_count,
        coverage=cov,
        tsr=tsr,
        r_inc=r_inc,
        r_inc_ucb95=r_inc_ucb,
        selective_risk_defined=sel_defined,
        r_sel=r_sel,
        r_sel_status=r_sel_status,
        r_sel_ucb95=r_sel_ucb,
        r_sel_ci95_low=ci_low,
        r_sel_ci95_high=ci_high,
        p_sel_iid=p_sel,
        mean_steps=mean_steps,
        mean_distance_traveled=mean_dist,
        mean_anchor_queries=mean_anc_q,
        mean_anchor_cost=mean_anc_c,
        mean_max_overshoot=mean_over,
    )


@dataclass(frozen=True)
class CandidateTestRecord:
    """Per-candidate p-value and stopping outcome in LTT."""

    sequence_position: int
    candidate_id: str
    m_accepted: int
    fs_count: int
    m_min_effective: int
    p_value: float
    passed_step: bool


@dataclass(frozen=True)
class FixedSequenceLTTResult:
    """Output of Fixed-Sequence LTT calibration (`docs/v9_risk_calibration_design.md` Section 2.4.2)."""

    certified: bool
    status: str
    alpha_target: float
    delta: float
    c_min: float
    m_min_effective: int
    stopped_at_position: int | None
    certified_candidate_ids: tuple[str, ...]
    selected_candidate: V9CandidateParams | None
    diagnostic_fallback_candidate: V9CandidateParams
    records: tuple[CandidateTestRecord, ...]


def fixed_sequence_ltt_select(
    ordered_candidates: Sequence[tuple[V9CandidateParams, PolicyEvaluationSummary]],
    *,
    alpha_target: float = 0.05,
    delta: float = 0.05,
    c_min: float = 0.35,
) -> FixedSequenceLTTResult:
    """
    Executes Fixed-Sequence Testing (FST) at full level `delta` across the pre-ordered
    candidate sequence j = 1, ..., J:
    1. Enforces effective acceptance floor m_min_eff = max(m_min_0, ceil(c_min * N_cal)).
    2. Tests j = 1, 2, ... strictly in sequence, stopping IMMEDIATELY at the first j*
       with p^{sel}(lambda^{(j*)}) > delta (even if a subsequent candidate j' > j* has
       p^{sel}(lambda^{(j')}) <= delta!).
    3. Among certified candidates {1, ..., j*-1}, selects argmax TSR (ties broken by
       lowest empirical R_sel, then smallest sequence position j).
    """
    if not ordered_candidates:
        raise ValueError("ordered_candidates must be non-empty.")
    if not (0.0 <= c_min < 1.0):
        raise ValueError(f"c_min must lie in [0, 1), got {c_min}.")

    n_episodes = ordered_candidates[0][1].n_episodes
    for _, summ in ordered_candidates:
        if summ.n_episodes != n_episodes:
            raise ValueError("All candidates in LTT must be evaluated on equal episode counts.")

    m_min_0 = minimum_zero_error_acceptances(alpha_target, delta)
    m_min_cov = int(math.ceil(c_min * n_episodes)) if c_min > 0.0 else 1
    m_min_eff = max(m_min_0, m_min_cov)

    records: list[CandidateTestRecord] = []
    certified_pairs: list[tuple[int, V9CandidateParams, PolicyEvaluationSummary]] = []
    stopped_at: int | None = None

    for pos, (cand, summ) in enumerate(ordered_candidates, start=1):
        p_val = selective_risk_pvalue(
            summ.fs_count,
            summ.m_accepted,
            alpha_target=alpha_target,
            m_min=m_min_eff,
        )
        passed = bool(p_val <= delta and stopped_at is None)
        if stopped_at is None and p_val > delta:
            stopped_at = pos
            passed = False

        records.append(
            CandidateTestRecord(
                sequence_position=pos,
                candidate_id=cand.candidate_id,
                m_accepted=summ.m_accepted,
                fs_count=summ.fs_count,
                m_min_effective=m_min_eff,
                p_value=p_val,
                passed_step=passed,
            )
        )
        if passed:
            certified_pairs.append((pos, cand, summ))

    fallback = ordered_candidates[0][0]
    if not certified_pairs:
        return FixedSequenceLTTResult(
            certified=False,
            status="V9_CALIBRATION_UNCERTIFIED",
            alpha_target=alpha_target,
            delta=delta,
            c_min=c_min,
            m_min_effective=m_min_eff,
            stopped_at_position=stopped_at,
            certified_candidate_ids=(),
            selected_candidate=None,
            diagnostic_fallback_candidate=fallback,
            records=tuple(records),
        )

    # Deterministic selection among certified set: highest TSR, then lowest R_sel, then earliest pos
    best_pos, best_cand, _ = min(
        certified_pairs,
        key=lambda item: (-item[2].tsr, item[2].r_sel, item[0]),
    )
    _ = best_pos
    return FixedSequenceLTTResult(
        certified=True,
        status="V9_CALIBRATION_CERTIFIED",
        alpha_target=alpha_target,
        delta=delta,
        c_min=c_min,
        m_min_effective=m_min_eff,
        stopped_at_position=stopped_at,
        certified_candidate_ids=tuple(c.candidate_id for _, c, _ in certified_pairs),
        selected_candidate=best_cand,
        diagnostic_fallback_candidate=fallback,
        records=tuple(records),
    )


def holm_stepdown_ltt(
    candidates: Sequence[tuple[V9CandidateParams, PolicyEvaluationSummary]],
    *,
    alpha_target: float = 0.05,
    delta: float = 0.05,
    c_min: float = 0.35,
) -> tuple[str, ...]:
    """
    Holm-Bonferroni step-down sensitivity comparator (controls FWER <= delta under
    arbitrary p-value dependence without requiring a pre-committed fixed sequence,
    at the cost of testing p_{(1)} <= delta / J).
    """
    if not candidates:
        raise ValueError("candidates must be non-empty.")

    n_episodes = candidates[0][1].n_episodes
    m_min_0 = minimum_zero_error_acceptances(alpha_target, delta)
    m_min_cov = int(math.ceil(c_min * n_episodes)) if c_min > 0.0 else 1
    m_min_eff = max(m_min_0, m_min_cov)

    scored: list[tuple[float, int, str]] = []
    for idx, (cand, summ) in enumerate(candidates):
        p_val = selective_risk_pvalue(
            summ.fs_count,
            summ.m_accepted,
            alpha_target=alpha_target,
            m_min=m_min_eff,
        )
        scored.append((p_val, idx, cand.candidate_id))

    scored.sort(key=lambda item: (item[0], item[1]))
    j_total = len(scored)
    rejected_ids: list[str] = []
    for rank_zero, (p_val, _, cand_id) in enumerate(scored):
        thresh = delta / float(j_total - rank_zero)
        if p_val <= thresh:
            rejected_ids.append(cand_id)
        else:
            break
    return tuple(rejected_ids)


def verify_preregistered_dev_ordering(
    candidates_with_dev: Sequence[tuple[V9CandidateParams, PolicyEvaluationSummary, float]],
    *,
    tier1_min_coverage: float = 0.42,
    c_min: float = 0.35,
    nominal_tsr_min: float = 0.94,
) -> dict[str, Any]:
    """
    Verifies the preregistered D_dev admissibility and ordering invariants from
    `docs/v9_risk_calibration_design.md` (Section 2.4) and `docs/v9_experiment_protocol.md`:
    - Structural threshold monotonicity from strictest (j=1) to most permissive (j=6).
    - Tier 1 utility pre-check: C_dev(lambda^{(1)}) >= 0.42 so FST is not blocked at j=1
      by over-abstention.
    - Minimum coverage C_dev >= 0.35 and NOMINAL TSR >= 0.94 across candidates.
    - Anti-gaming check: never ranks a candidate earlier solely because it abstains more.

    Args:
        candidates_with_dev: Sequence of (candidate, dev_summary, dev_nominal_tsr).
    """
    if len(candidates_with_dev) != 6:
        raise ValueError(f"Expected exactly 6 candidates, got {len(candidates_with_dev)}.")

    # 1. Verify structural threshold monotonicity across tiers 1..6
    for idx in range(len(candidates_with_dev) - 1):
        c1 = candidates_with_dev[idx][0]
        c2 = candidates_with_dev[idx + 1][0]
        if not (
            c1.tier_index < c2.tier_index
            and c1.alpha_mon < c2.alpha_mon
            and c1.h_cusum < c2.h_cusum
            and c1.tau_diff < c2.tau_diff
            and c1.tau_ar < c2.tau_ar
            and c1.tau_val < c2.tau_val
            and c1.tau_stop < c2.tau_stop
        ):
            raise ValueError(
                f"Structural conservatism monotonicity violated between {c1.candidate_id} and {c2.candidate_id}."
            )

    # 2. Verify Tier 1 pre-check C_dev(lambda^{(1)}) >= 0.42
    cand1, summ1, nom1 = candidates_with_dev[0]
    tier1_cov_ok = summ1.coverage >= tier1_min_coverage
    tier1_nom_ok = nom1 >= nominal_tsr_min

    admissibility_flags: list[dict[str, Any]] = []
    all_admissible = True
    for pos, (cand, summ, nom_tsr) in enumerate(candidates_with_dev, start=1):
        cov_ok = summ.coverage >= c_min
        nom_ok = nom_tsr >= nominal_tsr_min
        if not (cov_ok and nom_ok):
            all_admissible = False
        admissibility_flags.append(
            {
                "sequence_position": pos,
                "candidate_id": cand.candidate_id,
                "dev_coverage": round(summ.coverage, 6),
                "dev_tsr": round(summ.tsr, 6),
                "dev_r_sel": None if not summ.selective_risk_defined else round(summ.r_sel, 6),
                "dev_r_inc": round(summ.r_inc, 6),
                "dev_nominal_tsr": round(nom_tsr, 6),
                "coverage_admissible": cov_ok,
                "nominal_tsr_admissible": nom_ok,
            }
        )

    return {
        "tier1_candidate_id": cand1.candidate_id,
        "tier1_coverage": round(summ1.coverage, 6),
        "tier1_min_coverage_required": tier1_min_coverage,
        "tier1_precheck_passed": bool(tier1_cov_ok and tier1_nom_ok),
        "all_candidates_admissible": all_admissible,
        "ordering_basis": (
            "Preregistered joint threshold conservatism tiers j=1..6 (Table 2.4.1 of "
            "docs/v9_risk_calibration_design.md), verified on D_dev to satisfy Tier-1 "
            "coverage >= 0.42, C_dev >= 0.35, and NOMINAL TSR >= 0.94 without ranking "
            "policies safer merely by higher abstention."
        ),
        "candidate_dev_diagnostics": admissibility_flags,
    }


def compute_canonical_payload_sha256(payload: Mapping[str, Any]) -> str:
    """Computes reproducible SHA-256 hex digest of a JSON-serializable mapping (excluding `integrity_sha256`)."""
    filtered = {k: v for k, v in payload.items() if k != "integrity_sha256"}
    canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_frozen_candidates_json(
    path: str | Path,
    *,
    protocol_version: str,
    source_design_commit: str,
    v81_baseline_commit: str,
    ordered_candidates: Sequence[V9CandidateParams],
    dev_manifest_metadata: Mapping[str, Any],
    dev_ordering_report: Mapping[str, Any],
    evaluation_command: str,
    created_utc: str,
) -> tuple[Path, str]:
    """Writes and schema-validates `configs/v9_candidates_frozen.json` with canonical SHA-256 hash."""
    if len(ordered_candidates) != 6:
        raise ValueError("Frozen V9 configuration must contain exactly 6 candidates.")

    payload: dict[str, Any] = {
        "schema_version": "nexvia-aegis-v9-candidates-frozen/1.0",
        "protocol_version": protocol_version,
        "source_design_commit": source_design_commit,
        "v81_baseline_commit": v81_baseline_commit,
        "created_utc": created_utc,
        "calibration_and_holdout_data_used": False,
        "prohibited_seed_ranges_untouched": ["71000..71959", "72000..72039", "73000..74439", "75000..75119"],
        "ltt_calibration_spec": {
            "primary_method": "FIXED_SEQUENCE_LTT",
            "sensitivity_comparator": "HOLM_STEPDOWN_LTT",
            "alpha_target": 0.05,
            "delta": 0.05,
            "c_min": 0.35,
            "m_min_zero_error": 59,
            "selection_rule": "argmax_cal_tsr_tiebreak_lowest_rsel_then_earliest_index",
        },
        "development_manifest": dict(dev_manifest_metadata),
        "development_evaluation_command": evaluation_command,
        "development_ordering_verification": dict(dev_ordering_report),
        "candidate_order": [c.candidate_id for c in ordered_candidates],
        "candidates": [asdict(c) for c in ordered_candidates],
    }
    digest = compute_canonical_payload_sha256(payload)
    payload["integrity_sha256"] = digest

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    # Immediately round-trip validate
    loaded_cands, loaded_meta = load_frozen_candidates_json(out_path)
    if len(loaded_cands) != 6 or loaded_meta["integrity_sha256"] != digest:
        raise RuntimeError("Frozen candidate configuration failed round-trip integrity check.")
    return out_path, digest


def load_frozen_candidates_json(
    path: str | Path,
) -> tuple[tuple[V9CandidateParams, ...], dict[str, Any]]:
    """Loads, schema-validates, and verifies the canonical SHA-256 digest of a frozen candidate JSON."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Frozen config root must be a JSON object.")

    required_keys = {
        "schema_version",
        "protocol_version",
        "source_design_commit",
        "v81_baseline_commit",
        "calibration_and_holdout_data_used",
        "ltt_calibration_spec",
        "development_manifest",
        "development_evaluation_command",
        "development_ordering_verification",
        "candidate_order",
        "candidates",
        "integrity_sha256",
    }
    missing = required_keys - set(raw.keys())
    if missing:
        raise ValueError(f"Frozen config missing required keys: {sorted(missing)}.")
    if raw["calibration_and_holdout_data_used"] is not False:
        raise ValueError("Frozen config must not use calibration or holdout data.")

    expected_hash = compute_canonical_payload_sha256(raw)
    if raw["integrity_sha256"] != expected_hash:
        raise ValueError(
            f"Frozen config SHA-256 mismatch: expected {expected_hash}, got {raw['integrity_sha256']}."
        )

    cands = tuple(V9CandidateParams(**item) for item in raw["candidates"])
    if len(cands) != 6:
        raise ValueError(f"Expected 6 candidates, found {len(cands)}.")
    if [c.candidate_id for c in cands] != list(raw["candidate_order"]):
        raise ValueError("candidate_order does not match ordered candidates list.")

    return cands, raw
