"""
NEXVIA AEGIS-Next (V8) — Master Benchmark Suite.

Evaluates 8 competing policy architectures across 10 scenarios:
1. UNSHIELDED_ALWAYS_ACT: Naive inverse-variance vector pursuit (no verifier)
2. CHISQUARE_NIS_GATING: Classical Normalized Innovation Squared chi-square test
3. EKF_CONSISTENCY_MONITOR: EKF with range innovation consistency checking
4. AEGIS_V4_PASSIVE_VERIFY: Passive cross-modal geometric verification (no recalibration)
5. AEGIS_V5_HUBER_CALIBRATE: Online Huber M-estimation with fixed orthogonal probing
6. AEGIS_V6_DISCRIMINATIVE: 7-hypothesis Bayesian engine with active probing
7. AEGIS_V7_MPC_BASELINE: Risk-constrained pseudo-MPC with on-demand anchor
8. AEGIS_NEXT_MARTINGALE: Anytime-valid sequential martingale monitor + velocity controller

Scale: 10 scenarios x 8 policies x 50 matched episodes = 4,000 policy-episodes.
Outputs:
  - results/next/benchmark_episodes.csv
  - results/next/benchmark_summary.csv
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import time
import numpy as np

from aegis.next.agent_next import AegisNextController
from aegis.next.baselines import (
    AegisV4PassiveController,
    AegisV5HuberController,
    AegisV6DiscriminativeController,
    AegisV7MPCBaselineController,
    ChiSquareNISGatingController,
    EKFConsistencyController,
    UnshieldedAlwaysActController,
)
from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.env.world import AegisPhysicalWorld
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig
from aegis.v7.anchor_sensor import AnchorSensor, AnchorSensorConfig


def wilson_score_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    """Calculates asymmetric Wilson score confidence interval for binomial events."""
    if trials == 0:
        return 0.0, 0.0
    z = 1.95996  # 95% confidence
    p = successes / trials
    denom = 1.0 + (z**2) / trials
    center = (p + (z**2) / (2.0 * trials)) / denom
    margin = (z * np.sqrt((p * (1.0 - p) / trials) + (z**2) / (4.0 * (trials**2)))) / denom
    return max(0.0, float(center - margin)), min(1.0, float(center + margin))


@dataclass
class NextScenarioConfig:
    name: str
    description: str
    ground_truth_fault_label: str
    sensor_a: SensorConfig
    sensor_b: SensorConfig
    range_sensor_noise: float = 0.05
    range_dropout_prob: float = 0.0
    range_sensor_bias: float = 0.0
    anchor_corrupted: bool = False
    is_heavy_tailed: bool = False


def build_next_scenarios() -> list[NextScenarioConfig]:
    return [
        NextScenarioConfig(
            name="NOMINAL",
            description="Baseline operation under nominal Gaussian sensor noise",
            ground_truth_fault_label="H0_NOMINAL",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        NextScenarioConfig(
            name="PRIMARY_BIAS",
            description="Static spatial bias on primary sensor A (+0.8, -0.6)",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.8, -0.6)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        NextScenarioConfig(
            name="INDEPENDENT_BIAS",
            description="Independent non-identical biases on vector A (+0.6, +0.4) and B (-0.5, +0.5)",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.6, 0.4)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.5, 0.5)),
            range_sensor_noise=0.05,
        ),
        NextScenarioConfig(
            name="CORRELATED_BIAS",
            description="Common-mode correlated bias (+0.7, +0.7) on both vector sensors",
            ground_truth_fault_label="H4_CORRELATED_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
        ),
        NextScenarioConfig(
            name="SENSOR_DRIFT",
            description="Non-stationary dynamic drift on sensor A (0.003*t, 0.0015*t)",
            ground_truth_fault_label="H2_VECTOR_DRIFT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, drift_rate=(0.003, 0.0015)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        NextScenarioConfig(
            name="OUTLIER_BURSTS",
            description="Heavy-tailed outlier bursts (p=0.12, 4.5x scale)",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, outlier_probability=0.12, outlier_scale=4.5
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        NextScenarioConfig(
            name="SENSOR_DROPOUT",
            description="Intermittent packet loss (p=0.40) on sensor A",
            ground_truth_fault_label="H5_SENSOR_DROPOUT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, dropout_probability=0.40),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        NextScenarioConfig(
            name="FAULTY_REFERENCE_SENSOR",
            description="Correlated vector bias (+0.7, +0.7) AND range corrupted (+1.0m bias)",
            ground_truth_fault_label="H3_REFERENCE_FAULT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            range_sensor_bias=1.0,
        ),
        NextScenarioConfig(
            name="CORRUPTED_ANCHOR_STRESS",
            description="Correlated vector bias (+0.7, +0.7) AND anchor corrupted (+1.2m bias)",
            ground_truth_fault_label="H4_CORRELATED_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            anchor_corrupted=True,
        ),
        NextScenarioConfig(
            name="COMPOUND_HOLDOUT_EXTREME",
            description="Held-out compound stress: vector drift + common bias + range shift (-0.4m)",
            ground_truth_fault_label="H4_CORRELATED_BIAS",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.06, bias=(0.5, 0.5), drift_rate=(0.002, 0.002)
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.06, bias=(0.5, 0.5)),
            range_sensor_noise=0.06,
            range_sensor_bias=-0.40,
        ),
    ]


def run_next_benchmark(
    episodes_per_scenario: int = 50,
    seed_base: int = 60000,
    results_dir: str = "results/next",
) -> None:
    res_path = Path(results_dir)
    res_path.mkdir(parents=True, exist_ok=True)
    episodes_csv = res_path / "benchmark_episodes.csv"
    summary_csv = res_path / "benchmark_summary.csv"

    scenarios = build_next_scenarios()

    policy_keys = [
        "UNSHIELDED_ALWAYS_ACT",
        "CHISQUARE_NIS_GATING",
        "EKF_CONSISTENCY_MONITOR",
        "AEGIS_V4_PASSIVE_VERIFY",
        "AEGIS_V5_HUBER_CALIBRATE",
        "AEGIS_V6_DISCRIMINATIVE",
        "AEGIS_V7_MPC_BASELINE",
        "AEGIS_NEXT_MARTINGALE",
    ]

    print("=" * 80)
    print("NEXVIA AEGIS-NEXT (V8) RESEARCH BENCHMARK: SEQUENTIAL RISK CALIBRATION & RECOVERY")
    print(f"Scenarios: {len(scenarios)} | Policies: {len(policy_keys)} | Matched Episodes: {episodes_per_scenario}")
    print(f"Total Policy-Episodes: {len(scenarios) * len(policy_keys) * episodes_per_scenario}")
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

                # Initialize policy
                if pol_key == "UNSHIELDED_ALWAYS_ACT":
                    ctrl = UnshieldedAlwaysActController()
                elif pol_key == "CHISQUARE_NIS_GATING":
                    ctrl = ChiSquareNISGatingController()
                elif pol_key == "EKF_CONSISTENCY_MONITOR":
                    ctrl = EKFConsistencyController()
                elif pol_key == "AEGIS_V4_PASSIVE_VERIFY":
                    ctrl = AegisV4PassiveController()
                elif pol_key == "AEGIS_V5_HUBER_CALIBRATE":
                    ctrl = AegisV5HuberController()
                elif pol_key == "AEGIS_V6_DISCRIMINATIVE":
                    ctrl = AegisV6DiscriminativeController()
                elif pol_key == "AEGIS_V7_MPC_BASELINE":
                    ctrl = AegisV7MPCBaselineController()
                elif pol_key == "AEGIS_NEXT_MARTINGALE":
                    ctrl = AegisNextController()
                else:
                    raise ValueError(f"Unknown policy {pol_key}")

                # Run closed-loop episode
                rng_ep = np.random.default_rng(ep_seed)
                decisions: dict[str, int] = {}
                query_anchor = False
                min_dist_reached = float("inf")
                max_overshoot = 0.0
                dist_traveled = 0.0
                prev_pos = world.state()["robot_pos"].copy()

                for step in range(world.config.max_steps):
                    st = world.state()
                    true_delta = st["target_pos"] - st["robot_pos"]

                    read_a = sensor_a.measure(true_delta, rng_ep, step=st["step"])
                    read_b = sensor_b.measure(true_delta, rng_ep, step=st["step"])

                    true_range_val = float(st["distance"]) + scen.range_sensor_bias
                    read_r = range_sensor.measure(true_range_val, rng_ep)
                    read_anchor = anchor_sensor.measure(true_delta, rng_ep, query=query_anchor)

                    action, dec_type, cal_vec, query_anchor = ctrl.update(
                        read_a, read_b, read_r, read_anchor, step=st["step"]
                    )
                    decisions[dec_type] = decisions.get(dec_type, 0) + 1

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
                        overshoot = cur_dist - min_dist_reached
                        max_overshoot = max(max_overshoot, overshoot)

                    if w_st["truncated"]:
                        break

                final_st = world.state()
                final_dist = float(final_st["distance"])
                world.close()

                # Deliberate decision evaluation (Zero ground-truth termination leak)
                stopped = ("STOP" in decisions and decisions["STOP"] > 0)
                abstained = ("ABSTAIN" in decisions and decisions["ABSTAIN"] > 0)

                true_success = stopped and (final_dist <= 0.45)
                false_success = stopped and (final_dist > 0.45)
                abstain = abstained or (not stopped and not true_success)

                episode_records.append({
                    "scenario": scen.name,
                    "policy": pol_key,
                    "seed": ep_seed,
                    "true_success": int(true_success),
                    "false_success": int(false_success),
                    "abstain": int(abstain),
                    "final_distance": round(final_dist, 4),
                    "steps": final_st["step"],
                    "distance_traveled": round(dist_traveled, 4),
                    "anchor_queries": anchor_sensor.total_queries,
                    "anchor_cost": round(anchor_sensor.total_cost, 4),
                    "max_overshoot": round(max_overshoot, 4),
                })

    # Write episode-level CSV
    fieldnames = list(episode_records[0].keys())
    with open(episodes_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(episode_records)

    # Compute scenario summary statistics
    summary_rows: list[dict] = []
    for scen in scenarios:
        for pol_key in policy_keys:
            subset = [r for r in episode_records if r["scenario"] == scen.name and r["policy"] == pol_key]
            n_ep = len(subset)

            ts_count = sum(r["true_success"] for r in subset)
            fs_count = sum(r["false_success"] for r in subset)
            abs_count = sum(r["abstain"] for r in subset)

            ts_rate = ts_count / n_ep
            fs_rate = fs_count / n_ep
            cov_rate = (ts_count + fs_count) / n_ep
            abs_rate = abs_count / n_ep

            ts_ci = wilson_score_interval(ts_count, n_ep)
            cov_ci = wilson_score_interval(ts_count + fs_count, n_ep)

            # Covered risk = FS / (TS + FS)
            covered_decisions = ts_count + fs_count
            if covered_decisions > 0:
                cov_risk = fs_count / covered_decisions
                cov_risk_ci = wilson_score_interval(fs_count, covered_decisions)
            else:
                cov_risk = 0.0
                cov_risk_ci = (0.0, 0.0)

            mean_steps = float(np.mean([r["steps"] for r in subset]))
            mean_dist = float(np.mean([r["distance_traveled"] for r in subset]))
            mean_anchor_q = float(np.mean([r["anchor_queries"] for r in subset]))
            mean_anchor_c = float(np.mean([r["anchor_cost"] for r in subset]))
            mean_overshoot = float(np.mean([r["max_overshoot"] for r in subset]))

            summary_rows.append({
                "scenario": scen.name,
                "policy": pol_key,
                "episodes": n_ep,
                "true_success_count": ts_count,
                "true_success_rate": round(ts_rate, 4),
                "true_success_ci95": f"[{ts_ci[0]:.3f}, {ts_ci[1]:.3f}]",
                "task_coverage_rate": round(cov_rate, 4),
                "task_coverage_ci95": f"[{cov_ci[0]:.3f}, {cov_ci[1]:.3f}]",
                "false_success_count": fs_count,
                "false_success_rate": round(fs_rate, 4),
                "covered_risk": round(cov_risk, 4),
                "covered_risk_ci95": f"[{cov_risk_ci[0]:.3f}, {cov_risk_ci[1]:.3f}]",
                "abstention_rate": round(abs_rate, 4),
                "mean_steps": round(mean_steps, 2),
                "mean_distance_traveled": round(mean_dist, 2),
                "mean_anchor_queries": round(mean_anchor_q, 2),
                "mean_anchor_cost": round(mean_anchor_c, 4),
                "mean_max_overshoot": round(mean_overshoot, 4),
            })

    sum_fieldnames = list(summary_rows[0].keys())
    with open(summary_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sum_fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    elapsed = time.time() - t_start
    print("=" * 80)
    print(f"BENCHMARK COMPLETE in {elapsed:.2f}s!")
    print(f"Episode data written to: {episodes_csv}")
    print(f"Summary metrics written to: {summary_csv}")
    print("=" * 80)


if __name__ == "__main__":
    run_next_benchmark()
