"""
NEXVIA AEGIS V7.0 — Empirical Research Benchmark Suite.

Evaluates 6 competing policy architectures across 10 simulation scenarios:
1. AEGIS_V6_BASELINE: V6 Discriminative Probing (No Anchor)
2. AEGIS_V7_MPC_NO_ANCHOR: Risk-Constrained MPC (No Anchor)
3. AEGIS_V7_MPC_ON_DEMAND: V7 Full (Risk-Constrained MPC + On-Demand Anchor)
4. AEGIS_V7_MPC_ALWAYS_ON: Risk-Constrained MPC + Unconditional Anchor
5. AEGIS_V7_MPC_GENERIC_FIM: Risk-Constrained MPC with Generic FIM Objective
6. AEGIS_V7_MPC_FIXED_PROBE: Risk-Constrained MPC with Fixed Orthogonal Probing

Scale: 10 scenarios x 6 policies x 50 matched episodes = 3,000 policy-episodes.
Outputs:
  - results/v7/v7_benchmark_episodes.csv
  - results/v7/v7_benchmark_summary.csv
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import time
import numpy as np

from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.env.world import AegisPhysicalWorld
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig
from aegis.v6.recovery_controller import AegisV6RecoveryController
from aegis.v6.trajectory_planner import ProbingStrategy
from aegis.v7.anchor_sensor import AnchorSensor, AnchorSensorConfig
from aegis.v7.recovery_controller import AegisV7RecoveryController


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
class V7ScenarioConfig:
    name: str
    description: str
    ground_truth_fault_label: str
    sensor_a: SensorConfig
    sensor_b: SensorConfig
    range_sensor_noise: float = 0.05
    range_dropout_prob: float = 0.0
    range_sensor_bias: float = 0.0
    anchor_corrupted: bool = False
    collinear_constraint: bool = False


def build_v7_scenarios() -> list[V7ScenarioConfig]:
    return [
        V7ScenarioConfig(
            name="NOMINAL",
            description="Baseline operation under nominal Gaussian sensor noise",
            ground_truth_fault_label="H0_NOMINAL",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V7ScenarioConfig(
            name="PRIMARY_BIAS",
            description="Static spatial bias on primary sensor A (+0.8, -0.6)",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.8, -0.6)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V7ScenarioConfig(
            name="INDEPENDENT_BIAS",
            description="Independent distinct biases on sensor A (+0.6, +0.4) and B (-0.5, +0.5)",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.6, 0.4)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.5, 0.5)),
            range_sensor_noise=0.05,
        ),
        V7ScenarioConfig(
            name="CORRELATED_BIAS",
            description="Common-mode correlated bias (+0.7, +0.7) on both vector sensors",
            ground_truth_fault_label="H4_CORRELATED_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
        ),
        V7ScenarioConfig(
            name="SENSOR_DRIFT",
            description="Progressive sensor drift on sensor A (0.003*t, 0.0015*t)",
            ground_truth_fault_label="H2_VECTOR_DRIFT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, drift_rate=(0.003, 0.0015)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V7ScenarioConfig(
            name="OUTLIER_BURSTS",
            description="15% heavy-tail outlier bursts (scale=6.0) on vector sensor A",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, outlier_probability=0.15, outlier_scale=6.0),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V7ScenarioConfig(
            name="SENSOR_DROPOUT",
            description="20% intermittent packet dropout on vector sensors",
            ground_truth_fault_label="H5_SENSOR_DROPOUT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, dropout_probability=0.20),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, dropout_probability=0.20),
            range_sensor_noise=0.05,
        ),
        V7ScenarioConfig(
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
        V7ScenarioConfig(
            name="FAULTY_REFERENCE_SENSOR",
            description="Correlated bias on vectors (+0.7, +0.7) AND range sensor corrupted (+1.0m bias)",
            ground_truth_fault_label="H3_REFERENCE_FAULT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            range_sensor_bias=1.0,
        ),
        V7ScenarioConfig(
            name="CORRUPTED_ANCHOR_STRESS",
            description="Correlated bias on vectors (+0.7, +0.7) AND corrupted anchor (+1.2m bias)",
            ground_truth_fault_label="H4_CORRELATED_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            anchor_corrupted=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Benchmark Runner
# ---------------------------------------------------------------------------
def run_v7_benchmark(
    episodes_per_scenario: int = 50,
    seed_base: int = 57000,
    results_dir: str = "results/v7",
) -> None:
    res_path = Path(results_dir)
    res_path.mkdir(parents=True, exist_ok=True)
    episodes_csv = res_path / "v7_benchmark_episodes.csv"
    summary_csv = res_path / "v7_benchmark_summary.csv"

    scenarios = build_v7_scenarios()

    policy_keys = [
        "AEGIS_V6_BASELINE",
        "AEGIS_V7_MPC_NO_ANCHOR",
        "AEGIS_V7_MPC_ON_DEMAND",
        "AEGIS_V7_MPC_ALWAYS_ON",
        "AEGIS_V7_MPC_GENERIC_FIM",
        "AEGIS_V7_MPC_FIXED_PROBE",
    ]

    print("=" * 80)
    print("NEXVIA AEGIS V7.0 BENCHMARK: RISK-CONSTRAINED MPC & INDEPENDENT ANCHORING")
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
                rng_env = np.random.default_rng(ep_seed)
                world = AegisPhysicalWorld()
                world.reset(rng_env)

                sensor_a = FaultInjectableSensor(scen.sensor_a)
                sensor_b = FaultInjectableSensor(scen.sensor_b)
                range_sensor = RangeSensor(
                    noise_sigma=scen.range_sensor_noise,
                    dropout_probability=scen.range_dropout_prob,
                )
                anchor_cfg = AnchorSensorConfig(
                    query_cost=0.05,
                    noise_sigma=0.04,
                    is_corrupted=scen.anchor_corrupted,
                    corrupted_bias=(1.2, -1.0),
                )
                anchor_sensor = AnchorSensor(anchor_cfg)
                verifier = VerificationController()

                # Configure policy
                if pol_key == "AEGIS_V6_BASELINE":
                    ctrl = AegisV6RecoveryController(
                        strategy=ProbingStrategy.STRATEGY_F_DISCRIMINATIVE,
                        enable_multi_hypothesis=True,
                    )
                    is_v7 = False
                elif pol_key == "AEGIS_V7_MPC_NO_ANCHOR":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=False,
                    )
                    is_v7 = True
                elif pol_key == "AEGIS_V7_MPC_ON_DEMAND":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=False,
                    )
                    is_v7 = True
                elif pol_key == "AEGIS_V7_MPC_ALWAYS_ON":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=True,
                    )
                    is_v7 = True
                elif pol_key == "AEGIS_V7_MPC_GENERIC_FIM":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=False,
                        generic_fim_only=True,
                    )
                    is_v7 = True
                elif pol_key == "AEGIS_V7_MPC_FIXED_PROBE":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=False,
                        fixed_probe_only=True,
                    )
                    is_v7 = True
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
                max_overshoot = 0.0
                min_dist_reached = float("inf")
                last_report = None
                query_anchor = False

                for step in range(world.config.max_steps):
                    st = world.state()
                    true_delta = st["target_pos"] - st["robot_pos"]

                    read_a = sensor_a.measure(true_delta, rng_ep, step=st["step"])
                    read_b = sensor_b.measure(true_delta, rng_ep, step=st["step"])

                    true_range_val = float(st["distance"]) + scen.range_sensor_bias
                    read_r = range_sensor.measure(true_range_val, rng_ep)

                    verif = verifier.verify([read_a, read_b], read_r)

                    if is_v7:
                        read_anchor = anchor_sensor.measure(true_delta, rng_ep, query=query_anchor)
                        action, dec_type, diag_rep, cal_vec, query_anchor = ctrl.update(
                            read_a, read_b, read_r, read_anchor, verif.status, st["step"], rng=rng_ep
                        )
                        if diag_rep is not None:
                            last_report = diag_rep
                    else:
                        action, dec_type, diag_rep, cal_vec = ctrl.update(
                            read_a, read_b, read_r, verif.status, st["step"], rng=rng_ep
                        )
                        if diag_rep is not None:
                            last_report = diag_rep

                    decisions[dec_type] = decisions.get(dec_type, 0) + 1
                    if dec_type == "PROBE":
                        probing_count += 1

                    if ctrl.state.last_calibration and ctrl.state.last_calibration.status == "CALIBRATED":
                        calibrated_occurred = True
                        final_bias_est = ctrl.state.active_bias.copy()

                    if is_v7 and ctrl.state.anchor_resolved_bias:
                        calibrated_occurred = True
                        final_bias_est = ctrl.state.active_bias.copy()

                    if dec_type in ("STOP", "ABSTAIN"):
                        break

                    w_st = world.step(action, rng_ep)
                    curr_pos = w_st["robot_pos"].copy()
                    dist_traveled += float(np.linalg.norm(curr_pos - prev_pos))
                    prev_pos = curr_pos

                    cur_dist = float(w_st["distance"])
                    if cur_dist < min_dist_reached:
                        min_dist_reached = cur_dist
                    elif min_dist_reached <= 0.50:
                        bounce = cur_dist - min_dist_reached
                        max_overshoot = max(max_overshoot, bounce)

                    if w_st["terminated"] or w_st["truncated"]:
                        break

                final_st = world.state()
                final_dist = float(final_st["distance"])
                world.close()

                # Outcome determination
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

                # Ground truth bias error
                base_b = np.array(scen.sensor_a.bias, dtype=np.float64)
                bias_error = float(np.linalg.norm(final_bias_est - base_b)) if calibrated_occurred else None

                if last_report is not None:
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
                    "anchor_queries": anchor_sensor.total_queries,
                    "anchor_cost": round(anchor_sensor.total_cost, 4),
                    "max_overshoot": round(max_overshoot, 4),
                    "reason_code": reason,
                })

    # Write episode-level CSV
    print(f"\nWriting {len(episode_records)} episode records to {episodes_csv}...")
    with open(episodes_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(episode_records[0].keys()))
        writer.writeheader()
        writer.writerows(episode_records)

    # Compute Summary Aggregations
    summary_rows: list[dict] = []
    for scen in scenarios:
        for pol_key in policy_keys:
            subset = [r for r in episode_records if r["scenario"] == scen.name and r["policy"] == pol_key]
            n_ep = len(subset)

            ts_count = sum(r["true_success"] for r in subset)
            fs_count = sum(r["false_success"] for r in subset)
            abs_count = sum(r["abstain"] for r in subset)
            cal_count = sum(r["calibrated"] for r in subset)
            h_corr_count = sum(1 for r in subset if r["hypothesis_correct"])

            cov_count = ts_count + fs_count
            cov_rate = cov_count / n_ep
            ts_rate = ts_count / n_ep
            fs_rate = fs_count / n_ep
            abs_rate = abs_count / n_ep

            ts_ci_low, ts_ci_high = wilson_score_interval(ts_count, n_ep)
            cov_ci_low, cov_ci_high = wilson_score_interval(cov_count, n_ep)

            # Covered Risk = False Success / (True Success + False Success)
            if cov_count > 0:
                covered_risk = fs_count / cov_count
                risk_ci_low, risk_ci_high = wilson_score_interval(fs_count, cov_count)
                risk_ci_str = f"[{round(risk_ci_low, 3)}, {round(risk_ci_high, 3)}]"
            else:
                covered_risk = "N/A"
                risk_ci_str = "N/A"

            # Continuous metrics
            steps_list = [r["steps"] for r in subset]
            dist_list = [r["distance_traveled"] for r in subset]
            queries_list = [r["anchor_queries"] for r in subset]
            cost_list = [r["anchor_cost"] for r in subset]
            overshoot_list = [r["max_overshoot"] for r in subset]
            bias_errs = [r["bias_error"] for r in subset if r["bias_error"] != "N/A"]

            summary_rows.append({
                "scenario": scen.name,
                "policy": pol_key,
                "episodes": n_ep,
                "true_success_count": ts_count,
                "true_success_rate": round(ts_rate, 4),
                "true_success_ci95": f"[{round(ts_ci_low, 3)}, {round(ts_ci_high, 3)}]",
                "task_coverage_rate": round(cov_rate, 4),
                "task_coverage_ci95": f"[{round(cov_ci_low, 3)}, {round(cov_ci_high, 3)}]",
                "false_success_count": fs_count,
                "false_success_rate": round(fs_rate, 4),
                "covered_risk": round(covered_risk, 4) if isinstance(covered_risk, float) else "N/A",
                "covered_risk_ci95": risk_ci_str,
                "abstention_rate": round(abs_rate, 4),
                "calibration_rate": round(cal_count / n_ep, 4),
                "hypothesis_accuracy": round(h_corr_count / n_ep, 4),
                "mean_bias_error": round(float(np.mean(bias_errs)), 4) if bias_errs else "N/A",
                "mean_steps": round(float(np.mean(steps_list)), 1),
                "mean_distance_traveled": round(float(np.mean(dist_list)), 2),
                "mean_anchor_queries": round(float(np.mean(queries_list)), 2),
                "mean_anchor_cost": round(float(np.mean(cost_list)), 4),
                "mean_max_overshoot": round(float(np.mean(overshoot_list)), 4),
            })

    print(f"Writing aggregated summary ({len(summary_rows)} rows) to {summary_csv}...")
    with open(summary_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    elapsed = time.time() - t_start
    print(f"\nV7 Main Benchmark Execution Complete in {elapsed:.2f} seconds.")


if __name__ == "__main__":
    run_v7_benchmark()
