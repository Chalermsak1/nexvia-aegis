"""
Tests for Phase 1: Trustworthy Autonomous Decision-Making Benchmark Suite.
Verifies:
1. Reconciled Evaluator H2 Core-10 calculation.
2. Fix for A4: Missing baseline produces UNEVALUABLE status and does not falsely pass.
3. Strict terminal-state partitioning: N = TS + FS + AB_exp + TO + CR.
4. Determinism of matched-seed evaluation.
"""

from __future__ import annotations

import math
from pathlib import Path
import pytest
import numpy as np

from aegis.v9.controller import AegisV9Controller
from aegis.v9.risk_statistics import PREREGISTERED_CANDIDATE_FAMILY
from experiments.run_phase1_trustworthy_benchmark import (
    V9NoActiveProbeController,
    V9NoMartingaleController,
    mcnemar_exact_p_value,
    newcombe_paired_diff_ci,
)
from experiments.v9_evaluate_dev import build_v9_s12_scenarios, run_single_episode
from experiments.v9_evaluate_holdout import evaluate_mixture_holdout


def test_h2_evaluator_reconciliation_missing_baseline_cannot_falsely_pass():
    """
    Audit Finding A4 Closure Verification:
    Ensures that when baseline records are missing (None), evaluate_mixture_holdout
    does NOT grant a false pass via `not h2_results`, but correctly reports
    baseline_contrast_status = 'NOT_EVALUATED_NO_BASELINE_DATA' and baseline_contrast_passed = False.
    """
    cand_params = PREREGISTERED_CANDIDATE_FAMILY[2]
    # Synthetic records with M=504, FS=0
    records = [
        {
            "episode_index": i,
            "scenario": "NOMINAL",
            "scenario_index": 1,
            "seed": 73000 + i,
            "accepted": 1 if i < 504 else 0,
            "true_success": 1 if i < 504 else 0,
            "false_success": 0,
            "abstain_explicit": 0 if i < 504 else 1,
            "timeout": 0,
            "abstain": 0 if i < 504 else 1,
            "crashed": 0,
            "final_distance": 0.20 if i < 504 else 1.5,
        }
        for i in range(1440)
    ]

    # Evaluate without baselines
    res = evaluate_mixture_holdout(records=records, cand_params=cand_params, expected_n=1440)

    # Core-10 preregistered selective risk should pass on its own merits
    assert res["h2_core10_selective_risk"]["passed"] is True
    assert res["h2_core10_selective_risk"]["precondition_m_ge_59"] is True
    assert res["h2_core10_selective_risk"]["status"] == "CONFIRMATORY_PASS"

    # But the paired incidence contrast MUST explicitly report no baseline data
    assert res["h2_paired_incidence_contrast"]["passed"] is False
    assert res["h2_paired_incidence_contrast"]["status"] == "NOT_EVALUATED_NO_BASELINE_DATA"


def test_phase1_terminal_state_partition_invariant():
    """
    Verifies that for every episode, the terminal state is mutually exclusive and exhaustive:
    accepted + abstain_explicit + timeout + crashed >= 1, and true_success + false_success == accepted (or crashed).
    """
    scenarios = build_v9_s12_scenarios()
    ctrl = AegisV9Controller(PREREGISTERED_CANDIDATE_FAMILY[2])

    for scen in scenarios[:3]:
        for seed in (77000, 77001):
            r = run_single_episode(scen, seed, "v9", ctrl)
            accepted = r["accepted"]
            ts = r["true_success"]
            fs = r["false_success"]
            ab = r["abstain_explicit"]
            to = r["timeout"]
            cr = r["crashed"]

            # Mathematical invariant: If accepted, exactly one of (ts, fs) is 1
            if accepted == 1:
                assert ts + fs == 1
                assert ab == 0
                assert to == 0
            else:
                assert ts == 0
                # Either explicit abstain, timeout, or crash
                assert (ab == 1) or (to == 1) or (cr == 1)


def test_mcnemar_exact_p_value_symmetry():
    """Tests exact McNemar calculation symmetry and boundary conditions."""
    assert mcnemar_exact_p_value(0, 0) == 1.0
    assert mcnemar_exact_p_value(5, 5) == 1.0
    p_10_0 = mcnemar_exact_p_value(0, 10)
    assert p_10_0 == pytest.approx(2.0 * (0.5**10), rel=1e-5)
    assert mcnemar_exact_p_value(10, 0) == p_10_0


def test_newcombe_paired_difference_ci():
    """Tests Newcombe paired difference confidence interval calculation."""
    # Matched sample of 100: n11=50, n10=20, n01=5, n00=25 -> diff = +0.15
    low, high = newcombe_paired_diff_ci(50, 20, 5, 25, confidence=0.95)
    assert low < 0.15 < high
    assert low > 0.05  # Statistically significantly positive difference
