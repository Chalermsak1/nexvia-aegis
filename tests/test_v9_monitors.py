"""
NEXVIA AEGIS V9.0 — Unit Tests for Channel A (Ville e-Process) and Channel B (Page CUSUM).

Note: Analytical assertions verify exact algebraic identities directly; controlled
Monte Carlo simulations are supporting finite-sample sanity checks, not proofs of theorems.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from aegis.v9.cusum_monitor import CusumChannelSpec, MultiChannelCusumMonitor
from aegis.v9.ville_monitor import MultiChannelVilleMonitor, VilleChannelSpec


def test_ville_exact_single_channel_update_algebra():
    """Verifies exact step-by-step gamma=1.0 update algebra against closed-form hand calculation."""
    spec = VilleChannelSpec(
        name="ab",
        mu0=0.10,
        vmax=0.40,
        x_max=3.50,
        lambda_max=0.85,
        window_lambda=14,
        eps_lambda=1e-2,
    )
    mon = MultiChannelVilleMonitor([spec], alpha=0.05)

    # Step 1: lambda_1 MUST be 0.0 (F_0 measurable), so m_1 = 1.0 and wealth remains 1.0
    r1 = mon.update({"ab": (0.50, True)})
    assert r1.subchannel_lambdas["ab"] == 0.0
    assert r1.subchannel_multipliers["ab"] == 1.0
    assert r1.wealth == pytest.approx(1.0, abs=1e-15)
    assert r1.log_wealth_mixture == pytest.approx(0.0, abs=1e-15)
    assert not r1.is_alarm

    # Step 2: x_1 = (0.50 - 0.10) / 0.40 = 1.0; var([1.0]) = 0.0
    # lambda_2 = min(0.85, 0.90*0.40/0.10=3.60, 1.0 / (0 + 1.0^2 + 0.01)) = 1.0 / 1.01
    expected_lam2 = min(0.85, 1.0 / 1.01)  # 0.85
    # With e_2 = 0.90 -> x_2 = (0.90 - 0.10) / 0.40 = 2.0
    # m_2 = 1 + 0.85 * 2.0 = 2.70
    r2 = mon.update({"ab": (0.90, True)})
    assert r2.subchannel_lambdas["ab"] == pytest.approx(expected_lam2, abs=1e-12)
    assert r2.subchannel_multipliers["ab"] == pytest.approx(2.70, abs=1e-12)
    assert r2.wealth == pytest.approx(2.70, abs=1e-12)
    assert r2.log_wealth_mixture == pytest.approx(math.log(2.70), abs=1e-12)


def test_ville_nonnegative_multiplier_extreme_zero_residual():
    """
    Verifies strict multiplier positivity m_{c,t} >= 0.10 > 0 even when past residuals
    maximized lambda_{c,t} = bar_lambda_c and current residual drops to e_{c,t} = 0.0.
    """
    # Choose large mu0 relative to vmax so bar_lambda_c = 0.90 * vmax / mu0 < lambda_max
    spec = VilleChannelSpec(name="vr_a", mu0=0.50, vmax=0.40, lambda_max=0.85)
    assert spec.predictable_lambda_cap == pytest.approx(0.90 * 0.40 / 0.50, abs=1e-12)

    mon = MultiChannelVilleMonitor([spec], alpha=0.05)
    for _ in range(10):
        mon.update({"vr_a": (2.50, True)})

    # Now feed worst-case e_t = 0.0 -> x_t = -0.50 / 0.40 = -1.25
    res = mon.update({"vr_a": (0.0, True)})
    assert res.subchannel_multipliers["vr_a"] >= 0.10 - 1e-12
    assert res.wealth > 0.0


def test_ville_strict_predictability_no_current_step_leakage():
    """
    Verifies that lambda_{c,t} depends ONLY on F_{t-1} and is invariant to step-t residual e_{c,t}.
    """
    spec = VilleChannelSpec.inter_sensor_ab(0.05, 0.05)
    mon_low = MultiChannelVilleMonitor([spec], alpha=0.05)
    mon_high = MultiChannelVilleMonitor([spec], alpha=0.05)

    history_seq = [0.12, 0.18, 0.09, 0.22, 0.15]
    for val in history_seq:
        mon_low.update({"ab": (val, True)})
        mon_high.update({"ab": (val, True)})

    res_low = mon_low.update({"ab": (0.0, True)})
    res_high = mon_high.update({"ab": (10.0, True)})
    assert res_low.subchannel_lambdas["ab"] == pytest.approx(
        res_high.subchannel_lambdas["ab"], abs=1e-15
    )


def test_ville_equal_weight_convex_mixture_algebra():
    """Verifies E_t^{Ville} = (1/|C|) * sum_{c in C} E_t^{(c)} across 3 subchannels."""
    specs = [
        VilleChannelSpec.inter_sensor_ab(0.05, 0.05, name="ab"),
        VilleChannelSpec.vector_range("vr_a", 0.05, 0.05),
        VilleChannelSpec.vector_range("vr_b", 0.05, 0.05),
    ]
    mon = MultiChannelVilleMonitor(specs, alpha=0.05)

    inputs = [
        {"ab": (0.40, True), "vr_a": (0.35, True), "vr_b": (0.02, True)},
        {"ab": (0.45, True), "vr_a": (0.30, True), "vr_b": (0.03, True)},
        {"ab": (0.50, True), "vr_a": (0.02, False), "vr_b": (0.04, True)},
    ]
    last = None
    for obs in inputs:
        last = mon.update(obs)

    assert last is not None
    expected_mix = (
        last.subchannel_wealths["ab"]
        + last.subchannel_wealths["vr_a"]
        + last.subchannel_wealths["vr_b"]
    ) / 3.0
    assert last.wealth == pytest.approx(expected_mix, rel=1e-12)
    # Log-wealth is strictly ln(wealth), distinct from wealth itself
    assert last.log_wealth_mixture == pytest.approx(math.log(expected_mix), rel=1e-12)


def test_ville_long_run_numerical_stability_no_floor_no_cap():
    """
    Verifies 12,000-step numerical stability WITHOUT V8's reflecting lower floor (1e-6)
    or upper wealth cap (1e6).
    """
    spec = VilleChannelSpec(name="ab", mu0=0.10, vmax=0.40, window_lambda=14)
    mon = MultiChannelVilleMonitor([spec], alpha=0.05)

    # Every 15-step cycle: feed e=1.50 (x=+3.50) precisely when hist has 14 zeros (so lambda_t==0
    # and m_t==1.0), followed by 14 zero steps (where 13 steps have x_bar = +0.25/14 > 0 -> m_t < 1).
    # Over 800 cycles (12,000 steps), log-wealth drops below -45 (wealth < 1e-19 << 1e-6 V8 floor).
    res = None
    for step_idx in range(12000):
        val = 1.50 if (step_idx % 15 == 0) else 0.0
        res = mon.update({"ab": (val, True)})

    assert res is not None
    # If a 1e-6 floor existed (as in V8), log_wealth could never drop below ln(1e-6) ~= -13.8155
    assert res.log_wealth_mixture < -40.0
    assert math.isfinite(res.log_wealth_mixture)
    assert res.max_wealth == pytest.approx(1.0, abs=1e-12)
    assert not res.is_alarm

    # Conversely, 12,000 extreme fault steps must never NaN, overflow-crash, or cap at 1e6
    mon.reset()
    for _ in range(12000):
        res_fault = mon.update({"ab": (5.0, True)})
    assert res_fault.log_wealth_mixture > math.log(1e6) + 500.0
    assert res_fault.is_alarm
    assert res_fault.anytime_p_value == pytest.approx(0.0, abs=1e-15)


def test_ville_missing_and_invalid_residual_handling():
    """Verifies packet dropout (is_valid=False) is a strict no-op while NaN/Inf/negative fails closed."""
    spec = VilleChannelSpec.inter_sensor_ab(0.05, 0.05)
    mon = MultiChannelVilleMonitor([spec], alpha=0.05)
    mon.update({"ab": (0.30, True)})
    r_before = mon.update({"ab": (0.35, True)})

    # Dropped packet with NaN payload must NOT corrupt state when is_valid == False
    r_drop = mon.update({"ab": (float("nan"), False)})
    assert not r_drop.invalid_input_detected
    assert r_drop.wealth == pytest.approx(r_before.wealth, rel=1e-15)

    # Valid-flagged NaN, Inf, or negative residual MUST fail closed immediately
    for bad_val in (float("nan"), float("inf"), -0.05):
        m_bad = MultiChannelVilleMonitor([spec], alpha=0.05)
        res_bad = m_bad.update({"ab": (bad_val, True)})
        assert res_bad.invalid_input_detected
        assert res_bad.is_alarm


def test_ville_exact_threshold_boundary_and_nominal_supermartingale_sanity():
    """
    Verifies exact threshold boundary (wealth == 1/alpha alarms; below does not) and
    supporting Monte Carlo sanity check under nominal Gaussian noise over 300 and 5,000 steps.
    """
    spec = VilleChannelSpec(name="ab", mu0=0.10, vmax=0.40, x_max=10.0, lambda_max=0.80)
    # Choose alpha = 0.50 -> threshold = 2.0
    mon = MultiChannelVilleMonitor([spec], alpha=0.50)
    mon.update({"ab": (0.50, True)})  # x_1 = 1.0 -> lam_2 = min(0.80, 1/1.01) = 0.80
    # Need m_2 = 1 + 0.80 * x_2 = 2.0 -> x_2 = 1.25 -> e_2 = 0.10 + 0.40 * 1.25 = 0.60
    r_below = mon.update({"ab": (0.60 - 1e-6, True)})
    assert not r_below.is_alarm

    mon.reset()
    mon.update({"ab": (0.50, True)})
    r_exact = mon.update({"ab": (0.60, True)})
    assert r_exact.wealth == pytest.approx(2.0, rel=1e-12)
    assert r_exact.is_alarm

    # Supporting synthetic nominal check (300-step and 5,000-step horizons)
    rng = np.random.default_rng(202609)
    specs_3 = [
        VilleChannelSpec.inter_sensor_ab(0.05, 0.05, name="ab"),
        VilleChannelSpec.vector_range("vr_a", 0.05, 0.05),
        VilleChannelSpec.vector_range("vr_b", 0.05, 0.05),
    ]
    alarms_300 = 0
    final_wealths = []
    d_true = np.array([2.0, -1.5])
    for _ in range(200):
        m_sim = MultiChannelVilleMonitor(specs_3, alpha=0.05)
        ever = False
        for _ in range(300):
            za = d_true + rng.normal(0.0, 0.05, size=2)
            zb = d_true + rng.normal(0.0, 0.05, size=2)
            rt = max(0.0, float(np.linalg.norm(d_true)) + float(rng.normal(0.0, 0.05)))
            step_r = m_sim.update(
                {
                    "ab": (float(np.linalg.norm(za - zb)), True),
                    "vr_a": (abs(float(np.linalg.norm(za)) - rt), True),
                    "vr_b": (abs(float(np.linalg.norm(zb)) - rt), True),
                }
            )
            if step_r.is_alarm:
                ever = True
        if ever:
            alarms_300 += 1
        final_wealths.append(m_sim.wealth)

    assert float(np.mean(final_wealths)) <= 1.05
    assert (alarms_300 / 200.0) <= 0.05

    # Long 5,000-step nominal run check (30 trajectories)
    alarms_5000 = 0
    for _ in range(30):
        m_long = MultiChannelVilleMonitor(specs_3, alpha=0.05)
        ever = False
        for _ in range(5000):
            za = d_true + rng.normal(0.0, 0.05, size=2)
            zb = d_true + rng.normal(0.0, 0.05, size=2)
            rt = max(0.0, float(np.linalg.norm(d_true)) + float(rng.normal(0.0, 0.05)))
            if m_long.update(
                {
                    "ab": (float(np.linalg.norm(za - zb)), True),
                    "vr_a": (abs(float(np.linalg.norm(za)) - rt), True),
                    "vr_b": (abs(float(np.linalg.norm(zb)) - rt), True),
                }
            ).is_alarm:
                ever = True
                break
        if ever:
            alarms_5000 += 1
    assert (alarms_5000 / 30.0) <= 0.10


def test_cusum_init_accumulation_reset_and_persistent_vs_isolated():
    """
    Verifies CUSUM initialization, zero-reflection reset, bounded single-spike immunity,
    and fast detection of late-onset persistent drift after prolonged nominal operation.
    """
    spec = CusumChannelSpec.inter_sensor_ab(0.05, 0.05, name="ab", kappa_drift=1.80, z_max=6.0)
    cusum = MultiChannelCusumMonitor([spec], threshold_h=6.0)
    assert cusum.max_cusum == 0.0

    # 200 nominal small residuals -> stays reflected at 0.0
    for _ in range(200):
        r_nom = cusum.update({"ab": (0.05, True)})
        assert r_nom.max_cusum == 0.0
        assert not r_nom.is_alarm

    # Single extreme 100.0m burst is clipped to z_max = 6.0 -> S = 6.0 - 1.80 = 4.20 < 6.0 (no alarm!)
    r_spike = cusum.update({"ab": (100.0, True)})
    assert r_spike.max_cusum == pytest.approx(4.20, abs=1e-12)
    assert not r_spike.is_alarm

    # Subsequent quiet steps decay S back to 0.0 cleanly
    for _ in range(5):
        r_decay = cusum.update({"ab": (0.0, True)})
    assert r_decay.max_cusum == 0.0

    # Persistent moderate drift (e = 0.25m -> z = 0.25 / 0.070710678 = 3.5355 -> +1.7355/step)
    # Trips h = 6.0 in ceil(6.0 / 1.7355) = 4 steps even after 200 nominal steps!
    steps_to_alarm = 0
    for s in range(1, 10):
        r_drift = cusum.update({"ab": (0.25, True)})
        if r_drift.is_alarm:
            steps_to_alarm = s
            break
    assert steps_to_alarm == 4
    assert r_drift.triggered_channels == ("ab",)


def test_cusum_missing_invalid_and_exact_boundary():
    """Verifies CUSUM dropout no-op, NaN/Inf/negative fail-closed, and exact threshold boundary."""
    spec = CusumChannelSpec(name="vr_a", sigma_scale=0.10, kappa_drift=1.50, z_max=6.0)
    cusum = MultiChannelCusumMonitor([spec], threshold_h=3.0)

    # e = 0.45 -> z = 4.5 -> S = 3.0 - eps vs exact 3.0
    r_below = cusum.update({"vr_a": (0.45 - 1e-9, True)})
    assert not r_below.is_alarm

    # Dropout leaves S unchanged
    r_drop = cusum.update({"vr_a": (float("nan"), False)})
    assert not r_drop.invalid_input_detected
    assert r_drop.max_cusum == pytest.approx(r_below.max_cusum, abs=1e-15)

    cusum.reset()
    assert cusum.max_cusum == 0.0
    r_exact = cusum.update({"vr_a": (0.45, True)})
    assert r_exact.max_cusum == pytest.approx(3.0, abs=1e-12)
    assert r_exact.is_alarm

    for bad in (float("nan"), float("inf"), -1.0):
        c_bad = MultiChannelCusumMonitor([spec], threshold_h=3.0)
        res = c_bad.update({"vr_a": (bad, True)})
        assert res.invalid_input_detected
        assert res.is_alarm
