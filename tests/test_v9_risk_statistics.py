"""
NEXVIA AEGIS V9.0 — Unit Tests for Selective-Risk p-Values, Exact Confidence Bounds,
and Learn-Then-Test (LTT) Multiplicity Control.

Tests verify statistical outputs against independent closed-form combinatorial sums
(`math.comb(m, j) * p**j * (1-p)**(m-j)`) rather than calling implementation helpers.
"""

from __future__ import annotations

import math
from pathlib import Path
import numpy as np
import pytest

from aegis.v9.risk_statistics import (
    PREREGISTERED_CANDIDATE_FAMILY,
    clopper_pearson_one_sided_ucb,
    clopper_pearson_two_sided_ci,
    compute_policy_summary,
    fixed_sequence_ltt_select,
    holm_stepdown_ltt,
    load_frozen_candidates_json,
    minimum_zero_error_acceptances,
    selective_risk_pvalue,
    verify_preregistered_dev_ordering,
    write_frozen_candidates_json,
)


def _independent_binomial_lower_tail(k: int, m: int, alpha: float) -> float:
    """Independent exact combinatorial lower-tail sum without scipy."""
    return sum(math.comb(m, j) * (alpha**j) * ((1.0 - alpha) ** (m - j)) for j in range(k + 1))


def test_exact_small_count_and_boundary_binomial_pvalues():
    """Checks `selective_risk_pvalue` against independent closed-form sums on small & boundary counts."""
    alpha = 0.05
    # Small counts with m_min = 3
    assert selective_risk_pvalue(0, 2, alpha_target=alpha, m_min=3) == 1.0
    assert selective_risk_pvalue(0, 5, alpha_target=alpha, m_min=3) == pytest.approx(
        0.95**5, abs=1e-15
    )
    assert selective_risk_pvalue(2, 5, alpha_target=alpha, m_min=3) == pytest.approx(
        _independent_binomial_lower_tail(2, 5, alpha), abs=1e-15
    )

    # Zero errors: m = 59 passes delta = 0.05; m = 58 does NOT!
    assert minimum_zero_error_acceptances(0.05, 0.05) == 59
    p_59 = selective_risk_pvalue(0, 59, alpha_target=0.05, m_min=59)
    p_58_raw = selective_risk_pvalue(0, 58, alpha_target=0.05, m_min=1)
    p_58_gated = selective_risk_pvalue(0, 58, alpha_target=0.05, m_min=59)

    assert p_59 == pytest.approx(0.95**59, abs=1e-15)
    assert p_59 <= 0.05
    assert p_58_raw == pytest.approx(0.95**58, abs=1e-15)
    assert p_58_raw > 0.05
    assert p_58_gated == 1.0

    # Nonzero errors: k = 1 requires m >= 93 at delta = 0.05 (m >= 59 is NOT universal!)
    p_k1_m59 = selective_risk_pvalue(1, 59, alpha_target=0.05, m_min=59)
    p_k1_m92 = selective_risk_pvalue(1, 92, alpha_target=0.05, m_min=59)
    p_k1_m93 = selective_risk_pvalue(1, 93, alpha_target=0.05, m_min=59)
    assert p_k1_m59 == pytest.approx(_independent_binomial_lower_tail(1, 59, 0.05), abs=1e-14)
    assert p_k1_m59 > 0.19  # ~0.1991, far above 0.05 despite m >= 59!
    assert p_k1_m92 > 0.05
    assert p_k1_m93 == pytest.approx(_independent_binomial_lower_tail(1, 93, 0.05), abs=1e-14)
    assert p_k1_m93 <= 0.05


def test_zero_accepted_decisions_undefined_semantics():
    """When M = 0, selective risk MUST be UNDEFINED (NaN) and p_sel == 1.0, never 0.0."""
    assert selective_risk_pvalue(0, 0, alpha_target=0.05, m_min=59) == 1.0
    assert math.isnan(clopper_pearson_one_sided_ucb(0, 0, delta=0.05))
    lo, hi = clopper_pearson_two_sided_ci(0, 0, delta=0.05)
    assert math.isnan(lo) and math.isnan(hi)

    abstain_only_eps = [
        {
            "true_success": 0,
            "false_success": 0,
            "accepted": 0,
            "abstain_explicit": 1,
            "timeout": 0,
            "abstain": 1,
            "steps": 40,
        }
        for _ in range(100)
    ]
    summ = compute_policy_summary("ALWAYS_ABSTAIN", abstain_only_eps)
    assert summ.m_accepted == 0
    assert not summ.selective_risk_defined
    assert summ.r_sel_status == "UNDEFINED"
    assert math.isnan(summ.r_sel)
    assert math.isnan(summ.r_sel_ucb95)
    assert summ.p_sel_iid == 1.0
    # Unconditional incidence IS defined and equals 0/100
    assert summ.r_inc == 0.0
    assert summ.r_inc_ucb95 == pytest.approx(1.0 - (0.05 ** (1.0 / 100.0)), abs=1e-12)


def _synth_summary(policy_id: str, n_total: int, m_acc: int, k_fs: int) -> object:
    eps = []
    ts = m_acc - k_fs
    for i in range(n_total):
        if i < ts:
            eps.append({"true_success": 1, "false_success": 0, "abstain": 0, "steps": 150})
        elif i < m_acc:
            eps.append({"true_success": 0, "false_success": 1, "abstain": 0, "steps": 150})
        else:
            eps.append({"true_success": 0, "false_success": 0, "abstain": 1, "steps": 45})
    return compute_policy_summary(policy_id, eps)


def test_fixed_sequence_ltt_stopping_rule_and_holm_comparator():
    """
    Verifies Fixed-Sequence LTT:
    - Stops IMMEDIATELY at the first failing candidate (j=2), refusing to certify j=3..6
      even when j=3 has 0/500 false successes!
    - Selects highest-TSR candidate among certified prefix {1, ..., j*-1}.
    - Returns V9_CALIBRATION_UNCERTIFIED when j=1 fails (either high risk or C < C_min).
    """
    cands = PREREGISTERED_CANDIDATE_FAMILY
    n_cal = 960  # c_min=0.35 -> m_min_eff = ceil(0.35 * 960) = 336

    # Candidate 1 passes (2 / 420 -> p = 0.00018 <= 0.05)
    # Candidate 2 FAILS (22 / 430 -> R_sel = 5.12% -> p > 0.50)
    # Candidate 3 would have had 0 / 500, MUST NOT be certified by FST after stop at j=2!
    summaries = [
        (cands[0], _synth_summary(cands[0].candidate_id, n_cal, 420, 2)),
        (cands[1], _synth_summary(cands[1].candidate_id, n_cal, 430, 22)),
        (cands[2], _synth_summary(cands[2].candidate_id, n_cal, 500, 0)),
        (cands[3], _synth_summary(cands[3].candidate_id, n_cal, 510, 1)),
        (cands[4], _synth_summary(cands[4].candidate_id, n_cal, 520, 30)),
        (cands[5], _synth_summary(cands[5].candidate_id, n_cal, 540, 35)),
    ]
    fst_res = fixed_sequence_ltt_select(summaries, alpha_target=0.05, delta=0.05, c_min=0.35)
    assert fst_res.certified
    assert fst_res.m_min_effective == 336
    assert fst_res.stopped_at_position == 2
    assert fst_res.certified_candidate_ids == (cands[0].candidate_id,)
    assert fst_res.selected_candidate == cands[0]

    # Holm comparator does not require sequence order, so it rejects cands[2], cands[3], cands[0]
    holm_ids = holm_stepdown_ltt(summaries, alpha_target=0.05, delta=0.05, c_min=0.35)
    assert cands[2].candidate_id in holm_ids
    assert cands[1].candidate_id not in holm_ids

    # If Candidate 1 has low coverage (300 / 960 < 336), FST stops at j=1 -> UNCERTIFIED
    low_cov = [(cands[0], _synth_summary(cands[0].candidate_id, n_cal, 300, 0))] + summaries[1:]
    fst_uncert = fixed_sequence_ltt_select(low_cov, alpha_target=0.05, delta=0.05, c_min=0.35)
    assert not fst_uncert.certified
    assert fst_uncert.status == "V9_CALIBRATION_UNCERTIFIED"
    assert fst_uncert.selected_candidate is None
    assert fst_uncert.stopped_at_position == 1


def test_fixed_sequence_fwer_under_nonmonotone_correlated_candidates():
    """
    Supporting Monte Carlo check verifying FWER <= 0.05 across J=6 positively dependent
    candidates with non-monotone true selective risks:
      r_true = [0.015, 0.060 (unsafe!), 0.010, 0.055 (unsafe!), 0.020, 0.080 (unsafe!)].
    """
    rng = np.random.default_rng(90901)
    cands = PREREGISTERED_CANDIDATE_FAMILY
    true_covs = [0.46, 0.48, 0.50, 0.52, 0.54, 0.56]
    true_risks = [0.015, 0.060, 0.010, 0.055, 0.020, 0.080]
    unsafe_ids = {cands[1].candidate_id, cands[3].candidate_id, cands[5].candidate_id}

    n_trials = 1500
    n_cal = 400
    false_certifications = 0

    for _ in range(n_trials):
        # Shared uniform latent draws across j=1..6 induce strong positive dependence!
        u_acc = rng.random(n_cal)
        u_err = rng.random(n_cal)

        trial_pairs = []
        for j in range(6):
            acc = u_acc < true_covs[j]
            m_j = int(np.sum(acc))
            k_j = int(np.sum(acc & (u_err < true_risks[j])))
            # Build lightweight summary via exact binomial statistics
            p_j = selective_risk_pvalue(
                k_j, m_j, alpha_target=0.05, m_min=max(59, math.ceil(0.35 * n_cal))
            )
            _ = p_j
            summ_j = compute_policy_summary(
                cands[j].candidate_id,
                [{"true_success": m_j - k_j, "false_success": k_j, "accepted": m_j, "abstain": n_cal - m_j, "steps": 1}]
                + [{"true_success": 0, "false_success": 0, "accepted": 0, "abstain": 0, "steps": 1}] * (n_cal - 1),
            )
            trial_pairs.append((cands[j], summ_j))

        res = fixed_sequence_ltt_select(trial_pairs, alpha_target=0.05, delta=0.05, c_min=0.35)
        if set(res.certified_candidate_ids) & unsafe_ids:
            false_certifications += 1

    fwer = false_certifications / n_trials
    assert fwer <= 0.055  # Theoretical FWER <= 0.05


def test_frozen_config_json_roundtrip_and_tamper_detection(tmp_path: Path):
    """Verifies candidate ordering validation, JSON serialization, and SHA-256 tamper rejection."""
    cands = PREREGISTERED_CANDIDATE_FAMILY
    dev_pairs = [
        (c, _synth_summary(c.candidate_id, 360, 180 + 5 * i, i % 2), 0.9667)
        for i, c in enumerate(cands)
    ]
    report = verify_preregistered_dev_ordering(dev_pairs)
    assert report["tier1_precheck_passed"]
    assert report["all_candidates_admissible"]

    cfg_file = tmp_path / "v9_candidates_frozen.json"
    written_path, sha = write_frozen_candidates_json(
        cfg_file,
        protocol_version="v9.0-preregistered",
        source_design_commit="891c13e7bbd60e36c416c9bada8407e51233e663",
        v81_baseline_commit="4d891c7500cfb4c8110f276038455bc62765ef3b",
        ordered_candidates=cands,
        dev_manifest_metadata={"split": "D_dev", "seeds": "70000..70029", "episodes": 360},
        dev_ordering_report=report,
        evaluation_command="PYTHONPATH=src uv run python experiments/v9_evaluate_dev.py",
        created_utc="2026-10-24T00:00:00Z",
    )
    loaded_cands, meta = load_frozen_candidates_json(written_path)
    assert loaded_cands == cands
    assert meta["integrity_sha256"] == sha

    # Tampering with any parameter invalidates SHA-256 verification
    tampered_text = written_path.read_text(encoding="utf-8").replace('"tau_stop": 0.36', '"tau_stop": 0.49')
    written_path.write_text(tampered_text, encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_frozen_candidates_json(written_path)
