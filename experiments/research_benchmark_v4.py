from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from aegis.v3.control.verification_controller import (
    UnifiedVerification,
    VerificationController,
)
from aegis.v3.env.world import AegisPhysicalWorld, WorldConfig
from aegis.v3.policies.policy import AegisDecision, AegisPolicyV3
from aegis.v3.sensors.cross_modal import RangeReading, RangeSensor
from aegis.v3.sensors.sensors import (
    FaultInjectableSensor,
    SensorConfig,
    SensorReading,
)
from aegis.v3.sensors.verification import SensorVerifier


# ---------------------------------------------------------------------------
# Scenario Definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    description: str
    sensor_a: SensorConfig
    sensor_b: SensorConfig
    range_sensor_noise: float = 0.05
    range_dropout_prob: float = 0.0


def get_scenarios() -> list[ScenarioConfig]:
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
    ]


# ---------------------------------------------------------------------------
# Policy Implementations
# ---------------------------------------------------------------------------


class BaseBenchmarkPolicy:
    name: str

    def reset(self) -> None:
        pass

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        step: int,
    ) -> tuple[np.ndarray, str]:
        """
        Returns:
            action_vector: 2D force vector in [-1, 1]^2
            decision_type: "ACT", "VERIFY", "ABSTAIN", "RECOVER", or "STOP"
        """
        raise NotImplementedError


class AlwaysActPolicy(BaseBenchmarkPolicy):
    name = "ALWAYS_ACT"

    def __init__(self, target_tolerance: float = 0.18):
        self.target_tolerance = target_tolerance

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        step: int,
    ) -> tuple[np.ndarray, str]:
        est = reading_a.estimate
        dist = float(np.linalg.norm(est))
        if dist <= self.target_tolerance:
            return np.zeros(2, dtype=np.float64), "STOP"
        direction = est / max(dist, 1e-8)
        return direction, "ACT"


class FusionOnlyPolicy(BaseBenchmarkPolicy):
    name = "FUSION_ONLY"

    def __init__(self, target_tolerance: float = 0.18):
        self.target_tolerance = target_tolerance

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        step: int,
    ) -> tuple[np.ndarray, str]:
        # Inverse variance fusion of both vector readings
        if not reading_a.valid and not reading_b.valid:
            return np.zeros(2, dtype=np.float64), "STOP"
        elif not reading_a.valid:
            fused = reading_b.estimate
        elif not reading_b.valid:
            fused = reading_a.estimate
        else:
            w_a = 1.0 / max(reading_a.sigma**2, 1e-8)
            w_b = 1.0 / max(reading_b.sigma**2, 1e-8)
            fused = (w_a * reading_a.estimate + w_b * reading_b.estimate) / (
                w_a + w_b
            )

        dist = float(np.linalg.norm(fused))
        if dist <= self.target_tolerance:
            return np.zeros(2, dtype=np.float64), "STOP"
        direction = fused / max(dist, 1e-8)
        return direction, "ACT"


class AegisNoCrossModalPolicy(BaseBenchmarkPolicy):
    """
    Ablation: Uses vector arbitration only, without the independent RangeSensor.
    """

    name = "AEGIS_NO_CROSS_MODAL"

    def __init__(
        self,
        disagreement_threshold: float = 0.35,
        target_tolerance: float = 0.18,
    ):
        self.verifier = SensorVerifier(
            disagreement_threshold=disagreement_threshold
        )
        self.target_tolerance = target_tolerance

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        step: int,
    ) -> tuple[np.ndarray, str]:
        res = self.verifier.verify([reading_a, reading_b])

        if res.status in ("MISMATCH", "NO_SIGNAL"):
            return np.zeros(2, dtype=np.float64), "ABSTAIN"

        dist = float(np.linalg.norm(res.estimate))
        if dist <= self.target_tolerance:
            return np.zeros(2, dtype=np.float64), "STOP"

        direction = res.estimate / max(dist, 1e-8)
        return direction, "ACT"


class AegisNoAbstainPolicy(BaseBenchmarkPolicy):
    """
    Ablation: Has full cross-modal verification, but cannot abstain (forced action).
    """

    name = "AEGIS_NO_ABSTAIN"

    def __init__(self, target_tolerance: float = 0.18):
        self.controller = VerificationController()
        self.target_tolerance = target_tolerance

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        step: int,
    ) -> tuple[np.ndarray, str]:
        ver = self.controller.verify([reading_a, reading_b], range_reading)
        dist = float(np.linalg.norm(ver.estimate))
        if dist <= self.target_tolerance:
            return np.zeros(2, dtype=np.float64), "STOP"

        direction = ver.estimate / max(dist, 1e-8)
        return direction, "ACT"


class AegisFullPolicy(BaseBenchmarkPolicy):
    """
    Full Architecture: Intra-modal arbitration + Cross-modal range verification
    + Risk-aware Decision (ACT / VERIFY / ABSTAIN / RECOVER).
    """

    name = "AEGIS_FULL"

    def __init__(
        self,
        target_tolerance: float = 0.18,
        act_confidence: float = 0.75,
        verify_confidence: float = 0.50,
        recovery_after: int = 3,
    ):
        self.controller = VerificationController()
        self.policy = AegisPolicyV3(
            act_confidence=act_confidence,
            verify_confidence=verify_confidence,
            target_tolerance=target_tolerance,
            recovery_after=recovery_after,
        )
        self.target_tolerance = target_tolerance
        self.previous_dist: float | None = None

    def reset(self) -> None:
        self.policy.reset()
        self.previous_dist = None

    def decide(
        self,
        reading_a: SensorReading,
        reading_b: SensorReading,
        range_reading: RangeReading,
        step: int,
    ) -> tuple[np.ndarray, str]:
        ver = self.controller.verify([reading_a, reading_b], range_reading)
        dec: AegisDecision = self.policy.decide(ver)

        est_dist = float(np.linalg.norm(ver.estimate))

        if dec.action == "ACT":
            if est_dist <= self.target_tolerance and ver.status == "VERIFIED":
                return np.zeros(2, dtype=np.float64), "STOP"
            direction = ver.estimate / max(est_dist, 1e-8)
            return direction, "ACT"

        elif dec.action == "VERIFY":
            return np.zeros(2, dtype=np.float64), "VERIFY"

        elif dec.action == "ABSTAIN":
            return np.zeros(2, dtype=np.float64), "ABSTAIN"

        else:  # RECOVER
            direction = ver.estimate / max(est_dist, 1e-8)
            return -0.35 * direction, "RECOVER"


# ---------------------------------------------------------------------------
# Episode & Evaluation Runner
# ---------------------------------------------------------------------------


@dataclass
class EpisodeResult:
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
    decision_summary: str


def run_episode(
    world_config: WorldConfig,
    scenario: ScenarioConfig,
    policy: BaseBenchmarkPolicy,
    seed: int,
    episode_idx: int,
) -> EpisodeResult:
    # 1. Deterministic world initialization for this matched seed
    world_rng = np.random.default_rng(seed)
    world = AegisPhysicalWorld(world_config)
    initial_state = world.reset(world_rng)
    initial_dist = float(initial_state["distance"])

    # 2. Deterministic sensors for this episode
    sensor_rng = np.random.default_rng(seed + 1000)
    sensor_a = FaultInjectableSensor(scenario.sensor_a)
    sensor_b = FaultInjectableSensor(scenario.sensor_b)
    range_sensor = RangeSensor(
        noise_sigma=scenario.range_sensor_noise,
        dropout_probability=scenario.range_dropout_prob,
    )

    policy.reset()

    decision_counts: dict[str, int] = {}
    declared_success = False
    abstained = False
    final_est_dist = 0.0

    for step in range(world_config.max_steps):
        state = world.state()
        true_delta = state["target_pos"] - state["robot_pos"]
        true_dist = float(state["distance"])

        # Sensor readings
        read_a = sensor_a.measure(true_delta, sensor_rng, step=step)
        read_b = sensor_b.measure(true_delta, sensor_rng, step=step)
        read_r = range_sensor.measure(true_dist, sensor_rng)

        # Policy decision
        force_action, decision_type = policy.decide(
            read_a, read_b, read_r, step
        )
        decision_counts[decision_type] = (
            decision_counts.get(decision_type, 0) + 1
        )

        final_est_dist = float(np.linalg.norm(read_a.estimate))

        if decision_type == "STOP":
            declared_success = True
            break
        elif decision_type == "ABSTAIN":
            abstained = True
            # In physical hold, policy chooses to stop acting
            break

        # Step physics
        next_state = world.step(force_action, world_rng)
        if next_state["terminated"] or next_state["truncated"]:
            break

    final_state = world.state()
    final_true_dist = float(final_state["distance"])
    world.close()

    true_success = final_true_dist <= world_config.success_radius
    false_success = declared_success and not true_success

    dec_summary = ";".join(f"{k}:{v}" for k, v in decision_counts.items())

    return EpisodeResult(
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
        decision_summary=dec_summary,
    )


# ---------------------------------------------------------------------------
# Statistical Helpers
# ---------------------------------------------------------------------------


def wilson_score_interval(
    k: int, n: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Computes the 95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.95996  # 95% two-sided normal quantile
    p = k / n
    denom = 1.0 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


# ---------------------------------------------------------------------------
# Main Benchmark Pipeline
# ---------------------------------------------------------------------------


def run_benchmark(
    episodes_per_scenario: int = 50,
    base_seed: int = 42000,
    output_dir: Path | None = None,
) -> tuple[list[EpisodeResult], list[dict[str, Any]]]:

    if output_dir is None:
        output_dir = Path("results/v4")
    output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = get_scenarios()
    world_config = WorldConfig(max_steps=300, success_radius=0.25)

    policy_factories = [
        lambda: AlwaysActPolicy(),
        lambda: FusionOnlyPolicy(),
        lambda: AegisNoCrossModalPolicy(),
        lambda: AegisNoAbstainPolicy(),
        lambda: AegisFullPolicy(),
    ]

    all_results: list[EpisodeResult] = []
    summary_rows: list[dict[str, Any]] = []

    total_runs = (
        len(scenarios) * len(policy_factories) * episodes_per_scenario
    )
    print("=" * 80)
    print("NEXVIA AEGIS — RESEARCH BENCHMARK V4.0 (PHYSICAL SIMULATION)")
    print(f"Scenarios: {len(scenarios)} | Policies: {len(policy_factories)}")
    print(
        f"Episodes per scenario/policy: {episodes_per_scenario} | Total runs: {total_runs}"
    )
    print(f"Base Seed: {base_seed} | Success Radius: 0.25m")
    print("=" * 80)

    start_time = time.time()
    run_idx = 0

    for sc in scenarios:
        print(f"\n>>> Scenario: {sc.name:<18} [{sc.description}]")

        for p_factory in policy_factories:
            policy_inst = p_factory()
            p_name = policy_inst.name

            sc_policy_results: list[EpisodeResult] = []

            for ep_idx in range(episodes_per_scenario):
                # Matched episode seed
                seed = base_seed + ep_idx * 17
                res = run_episode(
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
            covered_risk = (n_false / n_covered) if n_covered > 0 else 0.0

            success_ci = wilson_score_interval(n_success, n)
            false_ci = wilson_score_interval(n_false, n)

            avg_steps = float(np.mean([r.steps for r in sc_policy_results]))
            avg_final_dist = float(
                np.mean([r.final_true_distance for r in sc_policy_results])
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
                "covered_risk": round(covered_risk, 4),
                "avg_steps": round(avg_steps, 2),
                "avg_final_true_distance": round(avg_final_dist, 4),
            }
            summary_rows.append(summary_row)

            print(
                f"  {p_name:<22} | "
                f"TrueSuccess: {summary_row['true_success_rate']*100:5.1f}% | "
                f"FalseSuccess: {summary_row['false_success_rate']*100:5.1f}% | "
                f"Abstain: {summary_row['abstain_rate']*100:5.1f}% | "
                f"Steps: {avg_steps:5.1f} | FinalDist: {avg_final_dist:.3f}m"
            )

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"Benchmark completed in {elapsed:.2f} seconds ({run_idx} runs).")

    # Save detailed episode-level CSV
    episodes_file = output_dir / "v4_benchmark_episodes.csv"
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
                "decision_summary",
            ],
        )
        writer.writeheader()
        for r in all_results:
            writer.writerow(r.__dict__)
    print(f"Episode-level data saved to: {episodes_file}")

    # Save aggregate summary CSV
    summary_file = output_dir / "v4_benchmark_summary.csv"
    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Summary metrics saved to:      {summary_file}")

    return all_results, summary_rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="NEXVIA AEGIS Research Benchmark V4.0"
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
        default=42000,
        help="Base random seed (default: 42000)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results/v4",
        help="Output directory (default: results/v4)",
    )

    args = parser.parse_args()
    eps = 2 if args.smoke_test else args.episodes
    run_benchmark(
        episodes_per_scenario=eps,
        base_seed=args.seed,
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()
