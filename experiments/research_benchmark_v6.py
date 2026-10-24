"""
NEXVIA AEGIS V6.0 — Empirical Research Benchmark Suite.

Evaluates 6 competing policy architectures across 10 simulation scenarios:
1. AEGIS_V5_ROBUST (V5 Full Baseline: Fixed Orthogonal, Single Hypothesis)
2. AEGIS_V6_FIXED_PROBE (Multi-Hypothesis + Strategy A: Fixed Orthogonal)
3. AEGIS_V6_CIRCULAR (Multi-Hypothesis + Strategy B: Circular Orbit)
4. AEGIS_V6_FIGURE_EIGHT (Multi-Hypothesis + Strategy C: Figure-Eight)
5. AEGIS_V6_FIM_GUIDED (Multi-Hypothesis + Strategy E: FIM-Guided)
6. AEGIS_V6_FULL_DISCRIMINATIVE (Multi-Hypothesis + Strategy F: Discriminative Probing)

Scale: 10 scenarios x 6 policies x 50 matched episodes = 3,000 policy-episodes.
Outputs:
  - results/v6/v6_benchmark_episodes.csv
  - results/v6/v6_benchmark_summary.csv
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import time
import numpy as np

from aegis.calibration import OnlineBiasEstimator
from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.env.world import AegisPhysicalWorld, WorldConfig
from aegis.v3.sensors.cross_modal import RangeReading, RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig, SensorReading
from aegis.v5.recovery_controller import SafeRecoveryController
from aegis.v6.recovery_controller import AegisV6RecoveryController
from aegis.v6.trajectory_planner import ProbingStrategy


# ---------------------------------------------------------------------------
# Statistical Utility: Wilson Score Confidence Interval
# ---------------------------------------------------------------------------
def wilson_score_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    if trials == 0:
        return 0.0, 0.0
    z = 1.95996  # 95% confidence
    p = successes / trials
    denom = 1.0 + (z**2) / trials
    center = (p + (z**2) / (2.0 * trials)) / denom
    margin = (z * np.sqrt((p * (1.0 - p) / trials) + (z**2) / (4.0 * (trials**2)))) / denom
    return max(0.0, float(center - margin)), min(1.0, float(center + margin))


# ---------------------------------------------------------------------------
# Scenario Definitions
# ---------------------------------------------------------------------------
@dataclass
class ScenarioConfig:
    name: str
    description: str
    ground_truth_fault_label: str
    sensor_a: SensorConfig
    sensor_b: SensorConfig
    range_sensor_noise: float = 0.05
    range_dropout_prob: float = 0.0
    range_sensor_bias: float = 0.0
    collinear_constraint: bool = False


def build_v6_scenarios() -> list[ScenarioConfig]:
    return [
        ScenarioConfig(
            name="NOMINAL",
            description="Baseline operation under nominal Gaussian sensor noise",
            ground_truth_fault_label="H0_NOMINAL",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="PRIMARY_BIAS",
            description="Static spatial bias on primary sensor A (+0.8, -0.6)",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.8, -0.6)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="INDEPENDENT_BIAS",
            description="Independent distinct biases on sensor A (+0.6, +0.4) and B (-0.5, +0.5)",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.6, 0.4)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.5, 0.5)),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="CORRELATED_BIAS",
            description="Common-mode correlated bias (+0.7, +0.7) on both vector sensors",
            ground_truth_fault_label="H4_CORRELATED_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="SENSOR_DRIFT",
            description="Progressive sensor drift on sensor A (0.003*t, 0.0015*t)",
            ground_truth_fault_label="H2_VECTOR_DRIFT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, drift_rate=(0.003, 0.0015)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="OUTLIER_BURSTS",
            description="15% heavy-tail outlier bursts (scale=6.0) on vector sensor A",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, outlier_probability=0.15, outlier_scale=6.0),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="SENSOR_DROPOUT",
            description="20% intermittent packet dropout on vector sensors",
            ground_truth_fault_label="H5_SENSOR_DROPOUT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, dropout_probability=0.20),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, dropout_probability=0.20),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="COMPOUND_HOLDOUT",
            description="Compound fault: correlated bias (+0.5, +0.5) + drift + outliers",
            ground_truth_fault_label="H4_CORRELATED_BIAS",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, bias=(0.5, 0.5),
                drift_rate=(0.002, 0.001), outlier_probability=0.10, outlier_scale=4.0
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.5, 0.5)),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="FAULTY_REFERENCE_SENSOR",
            description="Correlated bias on vectors (+0.7, +0.7) AND range sensor corrupted (+1.0m bias)",
            ground_truth_fault_label="H3_REFERENCE_FAULT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            range_sensor_bias=1.0,
        ),
        ScenarioConfig(
            name="LOW_OBSERVABILITY",
            description="Collinear 1D trajectory constraint under correlated bias (+0.7, +0.7)",
            ground_truth_fault_label="H6_AMBIGUOUS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            collinear_constraint=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Benchmark Runner
# ---------------------------------------------------------------------------
def run_v6_benchmark(
    episodes_per_scenario: int = 50,
    seed_base: int = 56000,
    results_dir: str = "results/v6",
) -> None:
    res_path = Path(results_dir)
    res_path.mkdir(parents=True, exist_ok=True)
    episodes_csv = res_path / "v6_benchmark_episodes.csv"
    summary_csv = res_path / "v6_benchmark_summary.csv"

    scenarios = build_v6_scenarios()

    policy_keys = [
        "AEGIS_V5_ROBUST",
        "AEGIS_V6_FIXED_PROBE",
        "AEGIS_V6_CIRCULAR",
        "AEGIS_V6_FIGURE_EIGHT",
        "AEGIS_V6_FIM_GUIDED",
        "AEGIS_V6_FULL_DISCRIMINATIVE",
    ]

    print("=" * 80)
    print("NEXVIA AEGIS V6.0 BENCHMARK: ACTIVE RECOVERY & MULTI-HYPOTHESIS DIAGNOSIS")
    print(f"Scenarios: {len(scenarios)} | Policies: {len(policy_keys)} | Matched Episodes: {episodes_per_scenario}")
    print(f"Total Evaluations: {len(scenarios) * len(policy_keys) * episodes_per_scenario}")
    print("=" * 80)

    episode_records: list[dict] = []
    t_start = time.time()

    for scen_idx, scen in enumerate(scenarios, 1):
        print(f"[{scen_idx}/{len(scenarios)}] Executing Scenario: {scen.name}")

        for ep_idx in range(episodes_per_scenario):
            ep_seed = seed_base + ep_idx

            for pol_key in policy_keys:
                # Instantiate environment with matched seed
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

                # Configure policy
                if pol_key == "AEGIS_V5_ROBUST":
                    ctrl = SafeRecoveryController(
                        estimation_method="HUBER",
                        enforce_observability=True,
                        enforce_validation=True,
                    )
                    is_v6 = False
                elif pol_key == "AEGIS_V6_FIXED_PROBE":
                    ctrl = AegisV6RecoveryController(
                        strategy=ProbingStrategy.STRATEGY_A_FIXED_ORTHOGONAL,
                        enable_multi_hypothesis=True,
                    )
                    is_v6 = True
                elif pol_key == "AEGIS_V6_CIRCULAR":
                    ctrl = AegisV6RecoveryController(
                        strategy=ProbingStrategy.STRATEGY_B_CIRCULAR_ORBIT,
                        enable_multi_hypothesis=True,
                    )
                    is_v6 = True
                elif pol_key == "AEGIS_V6_FIGURE_EIGHT":
                    ctrl = AegisV6RecoveryController(
                        strategy=ProbingStrategy.STRATEGY_C_FIGURE_EIGHT,
                        enable_multi_hypothesis=True,
                    )
                    is_v6 = True
                elif pol_key == "AEGIS_V6_FIM_GUIDED":
                    ctrl = AegisV6RecoveryController(
                        strategy=ProbingStrategy.STRATEGY_E_FIM_GUIDED,
                        enable_multi_hypothesis=True,
                    )
                    is_v6 = True
                elif pol_key == "AEGIS_V6_FULL_DISCRIMINATIVE":
                    ctrl = AegisV6RecoveryController(
                        strategy=ProbingStrategy.STRATEGY_F_DISCRIMINATIVE,
                        enable_multi_hypothesis=True,
                    )
                    is_v6 = True
                else:
                    raise ValueError(f"Unknown policy {pol_key}")

                # Episode execution loop
                rng_ep = np.random.default_rng(ep_seed)
                decisions: dict[str, int] = {}
                calibrated_occurred = False
                final_bias_est = np.zeros(2)
                probing_count = 0
                prev_pos = world.state()["robot_pos"].copy()
                dist_traveled = 0.0
                last_report = None

                for step in range(world.config.max_steps):
                    st = world.state()
                    true_delta = st["target_pos"] - st["robot_pos"]

                    read_a = sensor_a.measure(true_delta, rng_ep, step=st["step"])
                    read_b = sensor_b.measure(true_delta, rng_ep, step=st["step"])

                    true_range_val = float(st["distance"]) + scen.range_sensor_bias
                    read_r = range_sensor.measure(true_range_val, rng_ep)

                    verif = verifier.verify([read_a, read_b], read_r)

                    if is_v6:
                        action, dec_type, diag_rep, cal_vec = ctrl.update(
                            read_a, read_b, read_r, verif.status, st["step"], rng=rng_ep
                        )
                        if diag_rep is not None:
                            last_report = diag_rep
                    else:
                        action, dec_type, cal_res, cal_vec = ctrl.update(
                            read_a, read_b, read_r, verif.status, st["step"]
                        )
                        if cal_res and cal_res.status == "CALIBRATED":
                            calibrated_occurred = True
                            final_bias_est = cal_res.bias.copy()

                    decisions[dec_type] = decisions.get(dec_type, 0) + 1
                    if dec_type == "PROBE":
                        probing_count += 1

                    if is_v6 and ctrl.state.last_calibration and ctrl.state.last_calibration.status == "CALIBRATED":
                        calibrated_occurred = True
                        final_bias_est = ctrl.state.active_bias.copy()

                    if dec_type in ("STOP", "ABSTAIN"):
                        break

                    # Collinear constraint scenario
                    if scen.collinear_constraint:
                        action[1] = 0.0

                    w_st = world.step(action, rng_ep)
                    curr_pos = w_st["robot_pos"].copy()
                    dist_traveled += float(np.linalg.norm(curr_pos - prev_pos))
                    prev_pos = curr_pos

                    if w_st["terminated"] or w_st["truncated"]:
                        break

                final_st = world.state()
                final_dist = float(final_st["distance"])
                world.close()

                # Determine True / False / Abstain outcome
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

                # Ground-truth bias evaluation
                base_b = np.array(scen.sensor_a.bias, dtype=np.float64)
                bias_error = float(np.linalg.norm(final_bias_est - base_b)) if calibrated_occurred else None

                # Diagnostic metrics
                if is_v6 and last_report is not None:
                    lead_h = last_report.leading_hypothesis.value
                    entropy = last_report.entropy
                    reason = last_report.reason_code
                    h_correct = (lead_h == scen.ground_truth_fault_label)
                else:
                    lead_h = "N/A"
                    entropy = 0.0
                    reason = "N/A"
                    h_correct = False

                episode_records.append({
                    "episode_id": f"{scen.name}_{pol_key}_{ep_seed}",
                    "scenario": scen.name,
                    "policy": pol_key,
                    "seed": ep_seed,
                    "ground_truth_fault_label": scen.ground_truth_fault_label,
                    "leading_hypothesis": lead_h,
                    "diagnostic_entropy": round(entropy, 4),
                    "hypothesis_correct": h_correct,
                    "true_success": int(true_success),
                    "false_success": int(false_success),
                    "abstain": int(abstain),
                    "calibrated": int(calibrated_occurred),
                    "bias_error": round(bias_error, 4) if bias_error is not None else "N/A",
                    "steps": final_st["step"],
                    "final_distance": round(final_dist, 4),
                    "distance_traveled": round(dist_traveled, 4),
                    "probing_actions_count": probing_count,
                    "reason_code": reason,
                })

    t_elapsed = time.time() - t_start
    print(f"Benchmark completed 3,000 runs in {t_elapsed:.2f} seconds.")

    # -------------------------------------------------------------
    # Write Episode-Level CSV
    # -------------------------------------------------------------
    ep_fields = list(episode_records[0].keys())
    with open(episodes_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ep_fields)
        writer.writeheader()
        writer.writerows(episode_records)
    print(f"Saved episode records -> {episodes_csv}")

    # -------------------------------------------------------------
    # Aggregate Summary CSV
    # -------------------------------------------------------------
    summary_rows: list[dict] = []
    for scen in scenarios:
        for pol_key in policy_keys:
            subset = [r for r in episode_records if r["scenario"] == scen.name and r["policy"] == pol_key]
            n = len(subset)
            ts_count = sum(r["true_success"] for r in subset)
            fs_count = sum(r["false_success"] for r in subset)
            abs_count = sum(r["abstain"] for r in subset)
            cal_count = sum(r["calibrated"] for r in subset)

            ts_rate = ts_count / n
            fs_rate = fs_count / n
            abs_rate = abs_count / n
            cov_rate = (ts_count + fs_count) / n

            ts_ci = wilson_score_interval(ts_count, n)
            fs_ci = wilson_score_interval(fs_count, n)

            covered_decisions = ts_count + fs_count
            cov_risk = (fs_count / covered_decisions) if covered_decisions > 0 else "N/A"

            # Bias errors for calibrated runs
            cal_errs = [float(r["bias_error"]) for r in subset if r["bias_error"] != "N/A"]
            mean_bias_err = float(np.mean(cal_errs)) if cal_errs else "N/A"

            # Diagnostic metrics
            v6_sub = [r for r in subset if r["leading_hypothesis"] != "N/A"]
            if v6_sub:
                diag_acc = sum(1 for r in v6_sub if r["hypothesis_correct"]) / len(v6_sub)
                mean_ent = float(np.mean([r["diagnostic_entropy"] for r in v6_sub]))
            else:
                diag_acc = "N/A"
                mean_ent = "N/A"

            avg_steps = float(np.mean([r["steps"] for r in subset]))
            avg_final_dist = float(np.mean([r["final_distance"] for r in subset]))
            avg_dist_traveled = float(np.mean([r["distance_traveled"] for r in subset]))
            avg_probing = float(np.mean([r["probing_actions_count"] for r in subset]))

            summary_rows.append({
                "scenario": scen.name,
                "policy": pol_key,
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
                "diagnostic_accuracy": round(diag_acc, 4) if isinstance(diag_acc, float) else diag_acc,
                "mean_diagnostic_entropy": round(mean_ent, 4) if isinstance(mean_ent, float) else mean_ent,
                "mean_bias_error": round(mean_bias_err, 4) if isinstance(mean_bias_err, float) else mean_bias_err,
                "avg_steps": round(avg_steps, 2),
                "avg_final_true_distance": round(avg_final_dist, 4),
                "avg_distance_traveled": round(avg_dist_traveled, 4),
                "avg_probing_actions": round(avg_probing, 2),
            })

    sum_fields = list(summary_rows[0].keys())
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sum_fields)
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Saved aggregate summary -> {summary_csv}")


if __name__ == "__main__":
    run_v6_benchmark()
