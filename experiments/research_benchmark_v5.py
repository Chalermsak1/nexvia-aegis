from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from aegis.calibration import CalibrationResult
from aegis.v3.control.verification_controller import VerificationController
from aegis.v3.env.world import AegisPhysicalWorld, WorldConfig
from aegis.v3.sensors.cross_modal import RangeReading, RangeSensor
from aegis.v3.sensors.sensors import (
    FaultInjectableSensor,
    SensorConfig,
    SensorReading,
)
from aegis.v5.recovery_controller import SafeRecoveryController
from experiments.research_benchmark_v4 import (
    AegisFullPolicy,
    ScenarioConfig,
    wilson_score_interval,
)


# ---------------------------------------------------------------------------
# V5 Extended Scenario Suite
# ---------------------------------------------------------------------------


def get_v5_scenarios() -> list[ScenarioConfig]:
    return [
        ScenarioConfig(
            name="NOMINAL",
            description="Nominal zero-mean Gaussian noise on all sensors",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="PRIMARY_BIAS",
            description="Independent spatial bias on primary sensor A (+0.7, +0.7)",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="INDEPENDENT_BIAS",
            description="Independent distinct biases on sensor A (+0.6, +0.4) and B (-0.5, +0.5)",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, bias=(0.6, 0.4)
            ),
            sensor_b=SensorConfig(
                name="vec_b", noise_sigma=0.05, bias=(-0.5, 0.5)
            ),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="CORRELATED_BIAS",
            description="Common-mode correlated bias (+0.7, +0.7) on both vector sensors",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)
            ),
            sensor_b=SensorConfig(
                name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)
            ),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="SENSOR_DRIFT",
            description="Progressive sensor drift on sensor A (0.003 * step, 0.0015 * step)",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, drift_rate=(0.003, 0.0015)
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="OUTLIER_BURSTS",
            description="15% heavy-tail outlier bursts (scale=6.0) on vector sensor A",
            sensor_a=SensorConfig(
                name="vec_a",
                noise_sigma=0.05,
                outlier_probability=0.15,
                outlier_scale=6.0,
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="SENSOR_DROPOUT",
            description="20% intermittent packet dropout on vector sensors",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, dropout_probability=0.20
            ),
            sensor_b=SensorConfig(
                name="vec_b", noise_sigma=0.05, dropout_probability=0.20
            ),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="COMPOUND_HOLDOUT",
            description="Held-out compound fault: correlated bias (+0.5, +0.5) + drift + outliers",
            sensor_a=SensorConfig(
                name="vec_a",
                noise_sigma=0.05,
                bias=(0.5, 0.5),
                drift_rate=(0.002, 0.001),
                outlier_probability=0.10,
                outlier_scale=4.0,
            ),
            sensor_b=SensorConfig(
                name="vec_b",
                noise_sigma=0.05,
                bias=(0.5, 0.5),
            ),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="FAULTY_REFERENCE_SENSOR",
            description="Stress test: correlated bias on vectors (+0.7, +0.7) AND range sensor corrupted (+1.0m bias)",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)
            ),
            sensor_b=SensorConfig(
                name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)
            ),
            range_sensor_noise=0.05,
        ),
        ScenarioConfig(
            name="LOW_OBSERVABILITY",
            description="Collinear 1D trajectory constraint under correlated bias (+0.7, +0.7) - tests observability qualification gate",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)
            ),
            sensor_b=SensorConfig(
                name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)
            ),
            range_sensor_noise=0.05,
        ),
    ]


# ---------------------------------------------------------------------------
# Policy Implementations
# ---------------------------------------------------------------------------


class V5PolicyBase:
    name: str

    def reset(self) -> None:
        pass

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        verification_status: str,
        step: int,
        ground_truth_bias: np.ndarray | None = None,
    ) -> tuple[np.ndarray, str, CalibrationResult | None, np.ndarray]:
        raise NotImplementedError


class V4FullReferencePolicy(V5PolicyBase):
    """
    Reference V4 Policy: Multi-modal verification with conservative abstention.
    Does not perform online recalibration.
    """

    name = "AEGIS_V4_FULL"

    def __init__(self, target_tolerance: float = 0.18):
        self._policy = AegisFullPolicy(target_tolerance=target_tolerance)

    def reset(self) -> None:
        self._policy.reset()

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        verification_status: str,
        step: int,
        ground_truth_bias: np.ndarray | None = None,
    ) -> tuple[np.ndarray, str, CalibrationResult | None, np.ndarray]:
        force, dec = self._policy.decide(
            reading_a, reading_b, range_reading, step
        )
        # Raw estimate for reporting
        est = reading_a.estimate if reading_a.valid else np.zeros(2)
        return force, dec, None, est


class V5ControllerPolicy(V5PolicyBase):
    """
    AEGIS V5 Policy with configurable estimation and gating settings.
    """

    def __init__(
        self,
        name: str,
        estimation_method: str = "HUBER",
        enforce_observability: bool = True,
        enforce_validation: bool = True,
        target_tolerance: float = 0.18,
    ):
        self.name = name
        self.controller = SafeRecoveryController(
            estimation_method=estimation_method,
            enforce_observability=enforce_observability,
            enforce_validation=enforce_validation,
            target_tolerance=target_tolerance,
        )

    def reset(self) -> None:
        self.controller.reset()

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        verification_status: str,
        step: int,
        ground_truth_bias: np.ndarray | None = None,
    ) -> tuple[np.ndarray, str, CalibrationResult | None, np.ndarray]:
        return self.controller.update(
            reading_a=reading_a,
            reading_b=reading_b,
            range_reading=range_reading,
            verification_status=verification_status,
            step=step,
        )


class OracleCalibrationPolicy(V5PolicyBase):
    """
    Diagnostic Upper-Bound Policy: Uses injected ground-truth bias directly.
    Non-deployable; provides theoretical performance ceiling.
    """

    name = "ORACLE_CALIB_UPPER_BOUND"

    def __init__(self, target_tolerance: float = 0.22):
        self.target_tolerance = target_tolerance

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        verification_status: str,
        step: int,
        ground_truth_bias: np.ndarray | None = None,
    ) -> tuple[np.ndarray, str, CalibrationResult | None, np.ndarray]:
        if not (reading_a.valid or reading_b.valid):
            return np.zeros(2, dtype=np.float64), "VERIFY", None, np.zeros(2)

        bias = (
            ground_truth_bias
            if ground_truth_bias is not None
            else np.zeros(2, dtype=np.float64)
        )
        if reading_a.valid:
            cal_vec = reading_a.estimate - bias
        else:
            cal_vec = reading_b.estimate - bias

        dist = float(np.linalg.norm(cal_vec))
        if dist <= self.target_tolerance:
            if range_reading.valid and range_reading.distance > 0.45:
                return np.zeros(2, dtype=np.float64), "VERIFY", None, cal_vec
            return np.zeros(2, dtype=np.float64), "STOP", None, cal_vec

        direction = cal_vec / max(dist, 1e-8)
        return direction, "ACT", None, cal_vec


# ---------------------------------------------------------------------------
# Episode & Evaluation Runner
# ---------------------------------------------------------------------------


@dataclass
class V5EpisodeResult:
    scenario: str
    policy: str
    seed: int
    episode_idx: int
    true_success: bool
    declared_success: bool
    false_success: bool
    abstained: bool
    steps: int
    initial_true_distance: float
    final_true_distance: float
    final_estimated_distance: float
    bias_estimation_error: float | None
    calibrated_applied: bool
    calibration_status: str
    decision_summary: str


def run_v5_episode(
    world_config: WorldConfig,
    scenario: ScenarioConfig,
    policy: V5PolicyBase,
    seed: int,
    episode_idx: int,
) -> V5EpisodeResult:
    world_rng = np.random.default_rng(seed)
    world = AegisPhysicalWorld(world_config)
    initial_state = world.reset(world_rng)
    initial_dist = float(initial_state["distance"])

    sensor_rng = np.random.default_rng(seed + 1000)
    sensor_a = FaultInjectableSensor(scenario.sensor_a)
    sensor_b = FaultInjectableSensor(scenario.sensor_b)

    range_sensor = RangeSensor(
        noise_sigma=scenario.range_sensor_noise,
        dropout_probability=scenario.range_dropout_prob,
    )

    verifier = VerificationController()
    policy.reset()

    decision_counts: dict[str, int] = {}
    declared_success = False
    abstained = False
    calibrated_applied = False
    final_est_dist = 0.0
    final_cal_res: CalibrationResult | None = None

    # Calculate actual ground truth bias for offline evaluation only
    gt_bias = np.asarray(scenario.sensor_a.bias, dtype=np.float64)

    for step in range(world_config.max_steps):
        state = world.state()
        true_delta = state["target_pos"] - state["robot_pos"]
        true_dist = float(state["distance"])

        read_a = sensor_a.measure(true_delta, sensor_rng, step=step)
        read_b = sensor_b.measure(true_delta, sensor_rng, step=step)

        # In FAULTY_REFERENCE_SENSOR, inject +1.0m systematic error on range
        if scenario.name == "FAULTY_REFERENCE_SENSOR":
            corrupted_dist = true_dist + 1.0
            read_r = range_sensor.measure(corrupted_dist, sensor_rng)
        else:
            read_r = range_sensor.measure(true_dist, sensor_rng)

        # Verification status
        verification = verifier.verify([read_a, read_b], read_r)

        force_action, decision_type, cal_res, cal_vector = policy.decide(
            reading_a=read_a,
            reading_b=read_b,
            range_reading=read_r,
            verification_status=verification.status,
            step=step,
            ground_truth_bias=gt_bias,
        )

        decision_counts[decision_type] = (
            decision_counts.get(decision_type, 0) + 1
        )
        final_est_dist = float(np.linalg.norm(cal_vector))

        if cal_res is not None:
            final_cal_res = cal_res
            if cal_res.status == "CALIBRATED":
                calibrated_applied = True

        if decision_type == "STOP":
            declared_success = True
            break
        elif decision_type == "ABSTAIN":
            abstained = True
            break

        if scenario.name == "LOW_OBSERVABILITY":
            # Force robot motion to be purely 1D collinear along diagonal line-of-sight
            radial_dir = np.array([1.0, 1.0]) / np.sqrt(2.0)
            proj = float(np.dot(force_action, radial_dir))
            force_action = proj * radial_dir

        world_state = world.step(force_action, world_rng)
        if world_state["terminated"] or world_state["truncated"]:
            break

    final_state = world.state()
    final_true_dist = float(final_state["distance"])
    world.close()

    true_success = final_true_dist <= world_config.success_radius
    false_success = declared_success and not true_success

    # Compute bias estimation RMSE against injected ground truth (evaluation only)
    bias_error: float | None = None
    if final_cal_res is not None and final_cal_res.status == "CALIBRATED":
        bias_error = float(np.linalg.norm(final_cal_res.bias - gt_bias))

    cal_status_str = (
        final_cal_res.status if final_cal_res is not None else "NOT_ATTEMPTED"
    )
    dec_summary = ";".join(f"{k}:{v}" for k, v in decision_counts.items())

    return V5EpisodeResult(
        scenario=scenario.name,
        policy=policy.name,
        seed=seed,
        episode_idx=episode_idx,
        true_success=true_success,
        declared_success=declared_success,
        false_success=false_success,
        abstained=abstained,
        steps=final_state["step"],
        initial_true_distance=initial_dist,
        final_true_distance=final_true_dist,
        final_estimated_distance=final_est_dist,
        bias_estimation_error=bias_error,
        calibrated_applied=calibrated_applied,
        calibration_status=cal_status_str,
        decision_summary=dec_summary,
    )


# ---------------------------------------------------------------------------
# Benchmark Suite Runner
# ---------------------------------------------------------------------------


def run_v5_benchmark(
    episodes_per_scenario: int = 50,
    base_seed: int = 52000,
    output_dir: Path | None = None,
) -> tuple[list[V5EpisodeResult], list[dict[str, Any]]]:

    if output_dir is None:
        output_dir = Path("results/v5")
    output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = get_v5_scenarios()
    world_config = WorldConfig(max_steps=300, success_radius=0.25)

    policy_factories = [
        lambda: V4FullReferencePolicy(),
        lambda: V5ControllerPolicy(
            name="AEGIS_V5_OLS",
            estimation_method="OLS",
            enforce_observability=True,
            enforce_validation=True,
        ),
        lambda: V5ControllerPolicy(
            name="AEGIS_V5_ROBUST",
            estimation_method="HUBER",
            enforce_observability=True,
            enforce_validation=True,
        ),
        lambda: V5ControllerPolicy(
            name="AEGIS_V5_NO_OBS_GATE",
            estimation_method="HUBER",
            enforce_observability=False,
            enforce_validation=True,
        ),
        lambda: V5ControllerPolicy(
            name="AEGIS_V5_NO_VALIDATION",
            estimation_method="HUBER",
            enforce_observability=True,
            enforce_validation=False,
        ),
        lambda: OracleCalibrationPolicy(),
    ]

    all_results: list[V5EpisodeResult] = []
    summary_rows: list[dict[str, Any]] = []

    total_runs = len(scenarios) * len(policy_factories) * episodes_per_scenario
    print("=" * 80)
    print("NEXVIA AEGIS — RESEARCH BENCHMARK V5.0 (ONLINE RECALIBRATION)")
    print(f"Scenarios: {len(scenarios)} | Policies: {len(policy_factories)}")
    print(
        f"Episodes per scenario/policy: {episodes_per_scenario} | Total runs: {total_runs}"
    )
    print(f"Base Seed: {base_seed} | Success Radius: 0.25m")
    print("=" * 80)

    start_time = time.time()
    run_idx = 0

    for sc in scenarios:
        print(f"\n>>> Scenario: {sc.name:<24} [{sc.description}]")

        for p_factory in policy_factories:
            policy_inst = p_factory()
            p_name = policy_inst.name

            sc_policy_results: list[V5EpisodeResult] = []

            for ep_idx in range(episodes_per_scenario):
                seed = base_seed + ep_idx * 19
                res = run_v5_episode(
                    world_config=world_config,
                    scenario=sc,
                    policy=policy_inst,
                    seed=seed,
                    episode_idx=ep_idx,
                )
                sc_policy_results.append(res)
                all_results.append(res)
                run_idx += 1

            n = len(sc_policy_results)
            n_success = sum(1 for r in sc_policy_results if r.true_success)
            n_false = sum(1 for r in sc_policy_results if r.false_success)
            n_abstain = sum(1 for r in sc_policy_results if r.abstained)
            n_covered = n - n_abstain
            n_calibrated = sum(
                1 for r in sc_policy_results if r.calibrated_applied
            )

            # Strict denominator rule: covered_risk is undefined if coverage == 0
            covered_risk_str = (
                f"{(n_false / n_covered) * 100:.1f}%"
                if n_covered > 0
                else "N/A (0 coverage)"
            )
            covered_risk_val = (n_false / n_covered) if n_covered > 0 else None

            success_ci = wilson_score_interval(n_success, n)
            false_ci = wilson_score_interval(n_false, n)

            avg_steps = float(np.mean([r.steps for r in sc_policy_results]))
            avg_final_dist = float(
                np.mean([r.final_true_distance for r in sc_policy_results])
            )

            # Bias errors for calibrated episodes
            errors = [
                r.bias_estimation_error
                for r in sc_policy_results
                if r.bias_estimation_error is not None
            ]
            mean_bias_error = (
                float(np.mean(errors)) if errors else None
            )

            summary_row = {
                "scenario": sc.name,
                "policy": p_name,
                "episodes": n,
                "true_success_count": n_success,
                "true_success_rate": round(n_success / n, 4),
                "true_success_ci_low": round(success_ci[0], 4),
                "true_success_ci_high": round(success_ci[1], 4),
                "false_success_count": n_false,
                "false_success_rate": round(n_false / n, 4),
                "false_success_ci_low": round(false_ci[0], 4),
                "false_success_ci_high": round(false_ci[1], 4),
                "abstain_count": n_abstain,
                "abstain_rate": round(n_abstain / n, 4),
                "coverage_rate": round(n_covered / n, 4),
                "covered_risk": (
                    round(covered_risk_val, 4)
                    if covered_risk_val is not None
                    else "N/A"
                ),
                "calibrated_count": n_calibrated,
                "calibrated_rate": round(n_calibrated / n, 4),
                "mean_bias_error": (
                    round(mean_bias_error, 4)
                    if mean_bias_error is not None
                    else "N/A"
                ),
                "avg_steps": round(avg_steps, 2),
                "avg_final_true_distance": round(avg_final_dist, 4),
            }
            summary_rows.append(summary_row)

            print(
                f"  {p_name:<26} | "
                f"TrueSuccess: {summary_row['true_success_rate']*100:5.1f}% | "
                f"FalseSuccess: {summary_row['false_success_rate']*100:5.1f}% | "
                f"Coverage: {summary_row['coverage_rate']*100:5.1f}% | "
                f"Calibrated: {summary_row['calibrated_rate']*100:5.1f}% | "
                f"Steps: {avg_steps:5.1f}"
            )

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"Benchmark V5 completed in {elapsed:.2f} seconds ({run_idx} runs).")

    # Save detailed episode-level CSV
    episodes_file = output_dir / "v5_benchmark_episodes.csv"
    with open(episodes_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scenario",
                "policy",
                "seed",
                "episode_idx",
                "true_success",
                "declared_success",
                "false_success",
                "abstained",
                "steps",
                "initial_true_distance",
                "final_true_distance",
                "final_estimated_distance",
                "bias_estimation_error",
                "calibrated_applied",
                "calibration_status",
                "decision_summary",
            ],
        )
        writer.writeheader()
        for r in all_results:
            writer.writerow(r.__dict__)
    print(f"Episode-level data saved to: {episodes_file}")

    # Save aggregate summary CSV
    summary_file = output_dir / "v5_benchmark_summary.csv"
    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Summary metrics saved to:      {summary_file}")

    return all_results, summary_rows


def main():
    parser = argparse.ArgumentParser(
        description="NEXVIA AEGIS Research Benchmark V5.0"
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run 2 episodes per scenario to rapidly verify code paths",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=50,
        help="Number of matched episodes per scenario per policy (default: 50)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=52000,
        help="Base random seed (default: 52000)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results/v5",
        help="Output directory (default: results/v5)",
    )

    args = parser.parse_args()
    eps = 2 if args.smoke_test else args.episodes
    run_v5_benchmark(
        episodes_per_scenario=eps,
        base_seed=args.seed,
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()
