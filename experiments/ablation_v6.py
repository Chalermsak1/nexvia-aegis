"""
NEXVIA AEGIS V6.0 — Ablation Study Runner.

Evaluates isolated component contributions:
- Ablation A: Remove Multi-Hypothesis Diagnosis (single-bias baseline)
- Ablation B: Remove Active Planning (fixed orthogonal baseline)
- Ablation C: Remove FIM Observability Gate
- Ablation D: Remove Hypothesis-Discriminative Planning (generic FIM only)
- Ablation E: Remove Recovery Validation Gate
- Ablation F: Remove Risk Constraints
- Ablation G: Replace Adaptive with Random Safe Probing
"""

from __future__ import annotations

import csv
from pathlib import Path
import time
import numpy as np

from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.env.world import AegisPhysicalWorld
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig
from aegis.v6.recovery_controller import AegisV6RecoveryController
from aegis.v6.trajectory_planner import ProbingStrategy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from research_benchmark_v6 import build_v6_scenarios, wilson_score_interval


def run_v6_ablations(
    episodes_per_ablation: int = 50,
    seed_base: int = 58000,
    results_dir: str = "results/v6",
) -> None:
    res_path = Path(results_dir)
    res_path.mkdir(parents=True, exist_ok=True)
    summary_csv = res_path / "v6_ablation_summary.csv"

    # Focus on the most diagnostic stress scenarios
    target_scenarios = [
        "PRIMARY_BIAS",
        "OUTLIER_BURSTS",
        "FAULTY_REFERENCE_SENSOR",
        "LOW_OBSERVABILITY",
        "CORRELATED_BIAS",
    ]
    all_scenarios = {s.name: s for s in build_v6_scenarios()}
    scenarios = [all_scenarios[name] for name in target_scenarios]

    ablation_configs = [
        ("V6_FULL_DISCRIMINATIVE", ProbingStrategy.STRATEGY_F_DISCRIMINATIVE, True, True, True, True),
        ("ABLATION_A_NO_MULTI_HYPOTHESIS", ProbingStrategy.STRATEGY_F_DISCRIMINATIVE, False, True, True, True),
        ("ABLATION_B_FIXED_PROBING", ProbingStrategy.STRATEGY_A_FIXED_ORTHOGONAL, True, True, True, True),
        ("ABLATION_C_NO_FIM_GATE", ProbingStrategy.STRATEGY_F_DISCRIMINATIVE, True, False, True, True),
        ("ABLATION_D_FIM_ONLY_NO_DISCRIM", ProbingStrategy.STRATEGY_E_FIM_GUIDED, True, True, True, True),
        ("ABLATION_E_NO_VALIDATION_GATE", ProbingStrategy.STRATEGY_F_DISCRIMINATIVE, True, True, False, True),
        ("ABLATION_F_NO_RISK_CONSTRAINTS", ProbingStrategy.STRATEGY_F_DISCRIMINATIVE, True, True, True, False),
        ("ABLATION_G_RANDOM_PROBING", ProbingStrategy.STRATEGY_D_RANDOM_SAFE, True, True, True, True),
    ]

    print("=" * 80)
    print("NEXVIA AEGIS V6.0 ABLATION BENCHMARK")
    print(f"Scenarios: {len(scenarios)} | Configurations: {len(ablation_configs)} | Episodes: {episodes_per_ablation}")
    print("=" * 80)

    summary_rows: list[dict] = []
    t_start = time.time()

    for sc_idx, scen in enumerate(scenarios, 1):
        print(f"[{sc_idx}/{len(scenarios)}] Ablation on Scenario: {scen.name}")

        for cfg_name, strat, en_mh, en_fim, en_val, en_risk in ablation_configs:
            ts_count = 0
            fs_count = 0
            abs_count = 0
            cal_count = 0
            bias_errs = []
            steps_list = []
            final_dists = []

            for ep_idx in range(episodes_per_ablation):
                ep_seed = seed_base + ep_idx
                rng_env = np.random.default_rng(ep_seed)
                world = AegisPhysicalWorld()
                world.reset(rng_env)

                sensor_a = FaultInjectableSensor(scen.sensor_a)
                sensor_b = FaultInjectableSensor(scen.sensor_b)
                range_sensor = RangeSensor(
                    noise_sigma=scen.range_sensor_noise,
                    dropout_probability=scen.range_dropout_prob,
                )
                verifier = VerificationController()

                ctrl = AegisV6RecoveryController(
                    strategy=strat,
                    enable_multi_hypothesis=en_mh,
                    enforce_observability_gate=en_fim,
                    enforce_validation_gate=en_val,
                    enforce_risk_constraints=en_risk,
                )

                rng_ep = np.random.default_rng(ep_seed)
                decisions: dict[str, int] = {}
                cal_occurred = False
                final_b = np.zeros(2)

                for step in range(world.config.max_steps):
                    st = world.state()
                    true_delta = st["target_pos"] - st["robot_pos"]

                    read_a = sensor_a.measure(true_delta, rng_ep, step=st["step"])
                    read_b = sensor_b.measure(true_delta, rng_ep, step=st["step"])
                    true_range_val = float(st["distance"]) + scen.range_sensor_bias
                    read_r = range_sensor.measure(true_range_val, rng_ep)

                    verif = verifier.verify([read_a, read_b], read_r)
                    action, dec_type, diag_rep, cal_vec = ctrl.update(
                        read_a, read_b, read_r, verif.status, st["step"], rng=rng_ep
                    )

                    decisions[dec_type] = decisions.get(dec_type, 0) + 1
                    if ctrl.state.last_calibration and ctrl.state.last_calibration.status == "CALIBRATED":
                        cal_occurred = True
                        final_b = ctrl.state.active_bias.copy()

                    if dec_type in ("STOP", "ABSTAIN"):
                        break

                    if scen.collinear_constraint:
                        action[1] = 0.0

                    w_st = world.step(action, rng_ep)
                    if w_st["terminated"] or w_st["truncated"]:
                        break

                final_st = world.state()
                final_dist = float(final_st["distance"])
                world.close()

                stopped = ("STOP" in decisions and decisions["STOP"] > 0)
                abstained = ("ABSTAIN" in decisions and decisions["ABSTAIN"] > 0)
                if not stopped and not abstained:
                    if final_dist <= 0.45:
                        stopped = True
                    else:
                        abstained = True

                true_success = stopped and (final_dist <= 0.45)
                false_success = stopped and (final_dist > 0.45)
                abstain = abstained or (not stopped and not true_success)

                if true_success:
                    ts_count += 1
                if false_success:
                    fs_count += 1
                if abstain:
                    abs_count += 1
                if cal_occurred:
                    cal_count += 1
                    base_b = np.array(scen.sensor_a.bias, dtype=np.float64)
                    bias_errs.append(float(np.linalg.norm(final_b - base_b)))

                steps_list.append(final_st["step"])
                final_dists.append(final_dist)

            n = episodes_per_ablation
            ts_rate = ts_count / n
            fs_rate = fs_count / n
            abs_rate = abs_count / n
            cov_rate = (ts_count + fs_count) / n
            covered_decisions = ts_count + fs_count
            cov_risk = (fs_count / covered_decisions) if covered_decisions > 0 else "N/A"
            ts_ci = wilson_score_interval(ts_count, n)
            fs_ci = wilson_score_interval(fs_count, n)
            mean_b_err = float(np.mean(bias_errs)) if bias_errs else "N/A"

            summary_rows.append({
                "scenario": scen.name,
                "ablation_configuration": cfg_name,
                "episodes": n,
                "true_success_count": ts_count,
                "true_success_rate": round(ts_rate, 4),
                "true_success_ci_low": round(ts_ci[0], 4),
                "true_success_ci_high": round(ts_ci[1], 4),
                "false_success_count": fs_count,
                "false_success_rate": round(fs_rate, 4),
                "false_success_ci_low": round(fs_ci[0], 4),
                "false_success_ci_high": round(fs_ci[1], 4),
                "abstain_count": abs_count,
                "abstain_rate": round(abs_rate, 4),
                "coverage_rate": round(cov_rate, 4),
                "covered_risk": round(cov_risk, 4) if isinstance(cov_risk, float) else cov_risk,
                "calibrated_count": cal_count,
                "calibrated_rate": round(cal_count / n, 4),
                "mean_bias_error": round(mean_b_err, 4) if isinstance(mean_b_err, float) else mean_b_err,
                "avg_steps": round(float(np.mean(steps_list)), 2),
                "avg_final_true_distance": round(float(np.mean(final_dists)), 4),
            })

    t_elapsed = time.time() - t_start
    print(f"Ablation benchmark finished in {t_elapsed:.2f} seconds.")

    sum_fields = list(summary_rows[0].keys())
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sum_fields)
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Saved ablation summary -> {summary_csv}")


if __name__ == "__main__":
    run_v6_ablations()
