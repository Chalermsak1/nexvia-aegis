"""
NEXVIA AEGIS V7.0 — Component Ablation Benchmark Suite.

Evaluates 8 distinct architectural configurations across 5 critical stress scenarios:
1. `V7_FULL_ON_DEMAND`: Full V7 Architecture (MPC + Discriminative + On-Demand Anchor + Gates)
2. `ABLATION_A_NO_MPC`: Replace MPC with V6 open-loop probing + damping
3. `ABLATION_B_NO_TERMINAL_BRAKING`: MPC with w_terminal_velocity = 0.0 (Overshoot test)
4. `ABLATION_C_GENERIC_FIM`: MPC with FIM-only objective (No hypothesis discrimination)
5. `ABLATION_D_NO_ANCHOR`: V7 MPC without 3rd sensor modality (Assessing unresolvable H4)
6. `ABLATION_E_UNCONDITIONAL_ANCHOR`: Always-on anchor queries on every step
7. `ABLATION_F_NO_ANCHOR_GATE`: Anchor validation gate disabled (Evaluating corrupted anchor vulnerability)
8. `ABLATION_H_FIXED_PROBE`: Fixed orthogonal probing trajectory with MPC & On-Demand Anchor

Scale: 5 scenarios x 8 configurations x 50 episodes = 2,000 ablation evaluations.
Output: results/v7/v7_ablation_summary.csv
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


@dataclass
class AblationScenarioConfig:
    name: str
    description: str
    ground_truth_fault_label: str
    sensor_a: SensorConfig
    sensor_b: SensorConfig
    range_sensor_noise: float = 0.05
    range_sensor_bias: float = 0.0
    anchor_corrupted: bool = False


def build_ablation_scenarios() -> list[AblationScenarioConfig]:
    return [
        AblationScenarioConfig(
            name="PRIMARY_BIAS",
            description="Static bias (+0.8, -0.6) on primary vector sensor",
            ground_truth_fault_label="H1_VECTOR_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.8, -0.6)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
        ),
        AblationScenarioConfig(
            name="CORRELATED_BIAS",
            description="Common-mode correlated bias (+0.7, +0.7) on both vector sensors",
            ground_truth_fault_label="H4_CORRELATED_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
        ),
        AblationScenarioConfig(
            name="SENSOR_DRIFT",
            description="Progressive non-stationary drift (0.003*t, 0.0015*t)",
            ground_truth_fault_label="H2_VECTOR_DRIFT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, drift_rate=(0.003, 0.0015)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
        ),
        AblationScenarioConfig(
            name="FAULTY_REFERENCE_SENSOR",
            description="Correlated vector bias (+0.7, +0.7) AND range corrupted (+1.0m bias)",
            ground_truth_fault_label="H3_REFERENCE_FAULT",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_bias=1.0,
        ),
        AblationScenarioConfig(
            name="CORRUPTED_ANCHOR_STRESS",
            description="Correlated vector bias (+0.7, +0.7) AND corrupted anchor (+1.2m bias)",
            ground_truth_fault_label="H4_CORRELATED_BIAS",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            anchor_corrupted=True,
        ),
    ]


def run_v7_ablation(
    episodes_per_scenario: int = 50,
    seed_base: int = 58000,
    results_dir: str = "results/v7",
) -> None:
    res_path = Path(results_dir)
    res_path.mkdir(parents=True, exist_ok=True)
    summary_csv = res_path / "v7_ablation_summary.csv"

    scenarios = build_ablation_scenarios()

    config_keys = [
        "V7_FULL_ON_DEMAND",
        "ABLATION_A_NO_MPC",
        "ABLATION_B_NO_TERMINAL_BRAKING",
        "ABLATION_C_GENERIC_FIM",
        "ABLATION_D_NO_ANCHOR",
        "ABLATION_E_UNCONDITIONAL_ANCHOR",
        "ABLATION_F_NO_ANCHOR_GATE",
        "ABLATION_H_FIXED_PROBE",
    ]

    print("=" * 80)
    print("NEXVIA AEGIS V7.0 COMPONENT ABLATION BENCHMARK")
    print(f"Scenarios: {len(scenarios)} | Configurations: {len(config_keys)} | Matched Episodes: {episodes_per_scenario}")
    print(f"Total Evaluations: {len(scenarios) * len(config_keys) * episodes_per_scenario}")
    print("=" * 80)

    ablation_records: list[dict] = []
    t_start = time.time()

    for scen_idx, scen in enumerate(scenarios, 1):
        print(f"[{scen_idx}/{len(scenarios)}] Ablating Scenario: {scen.name}")

        for ep_idx in range(episodes_per_scenario):
            ep_seed = seed_base + ep_idx

            for cfg_key in config_keys:
                rng_env = np.random.default_rng(ep_seed)
                world = AegisPhysicalWorld()
                world.reset(rng_env)

                sensor_a = FaultInjectableSensor(scen.sensor_a)
                sensor_b = FaultInjectableSensor(scen.sensor_b)
                range_sensor = RangeSensor(
                    noise_sigma=scen.range_sensor_noise,
                )
                anchor_sensor = AnchorSensor(
                    AnchorSensorConfig(
                        query_cost=0.05,
                        noise_sigma=0.04,
                        is_corrupted=scen.anchor_corrupted,
                        corrupted_bias=(1.2, -1.0),
                    )
                )
                verifier = VerificationController()

                # Configure ablation controller
                if cfg_key == "V7_FULL_ON_DEMAND":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=False,
                        enforce_terminal_braking=True,
                    )
                    is_v7 = True
                elif cfg_key == "ABLATION_A_NO_MPC":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=False,
                        use_anchor=True,
                        unconditional_anchor=False,
                    )
                    is_v7 = True
                elif cfg_key == "ABLATION_B_NO_TERMINAL_BRAKING":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=False,
                        enforce_terminal_braking=False,
                    )
                    is_v7 = True
                elif cfg_key == "ABLATION_C_GENERIC_FIM":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=False,
                        generic_fim_only=True,
                    )
                    is_v7 = True
                elif cfg_key == "ABLATION_D_NO_ANCHOR":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=False,
                    )
                    is_v7 = True
                elif cfg_key == "ABLATION_E_UNCONDITIONAL_ANCHOR":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=True,
                    )
                    is_v7 = True
                elif cfg_key == "ABLATION_F_NO_ANCHOR_GATE":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=False,
                    )
                    # Artificially disable gate tolerance check so bad anchors get accepted
                    ctrl.anchor_gate.consistency_tolerance = 100.0
                    is_v7 = True
                elif cfg_key == "ABLATION_H_FIXED_PROBE":
                    ctrl = AegisV7RecoveryController(
                        use_mpc=True,
                        use_anchor=True,
                        unconditional_anchor=False,
                        fixed_probe_only=True,
                    )
                    is_v7 = True
                else:
                    raise ValueError(f"Unknown config {cfg_key}")

                # Episode loop
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
                    read_anchor = anchor_sensor.measure(true_delta, rng_ep, query=query_anchor)

                    action, dec_type, diag_rep, cal_vec, query_anchor = ctrl.update(
                        read_a, read_b, read_r, read_anchor, verif.status, st["step"], rng=rng_ep
                    )
                    if diag_rep is not None:
                        last_report = diag_rep

                    decisions[dec_type] = decisions.get(dec_type, 0) + 1
                    if dec_type == "PROBE":
                        probing_count += 1

                    if ctrl.state.last_calibration and ctrl.state.last_calibration.status == "CALIBRATED":
                        calibrated_occurred = True
                        final_bias_est = ctrl.state.active_bias.copy()

                    if ctrl.state.anchor_resolved_bias:
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

                base_b = np.array(scen.sensor_a.bias, dtype=np.float64)
                bias_error = float(np.linalg.norm(final_bias_est - base_b)) if calibrated_occurred else None

                ablation_records.append({
                    "scenario": scen.name,
                    "configuration": cfg_key,
                    "seed": ep_seed,
                    "true_success": int(true_success),
                    "false_success": int(false_success),
                    "abstain": int(abstain),
                    "calibrated": int(calibrated_occurred),
                    "bias_error": bias_error,
                    "steps": final_st["step"],
                    "anchor_queries": anchor_sensor.total_queries,
                    "anchor_cost": anchor_sensor.total_cost,
                    "max_overshoot": max_overshoot,
                })

    # Summary aggregations
    summary_rows: list[dict] = []
    for scen in scenarios:
        for cfg_key in config_keys:
            subset = [r for r in ablation_records if r["scenario"] == scen.name and r["configuration"] == cfg_key]
            n_ep = len(subset)

            ts_count = sum(r["true_success"] for r in subset)
            fs_count = sum(r["false_success"] for r in subset)
            abs_count = sum(r["abstain"] for r in subset)
            cal_count = sum(r["calibrated"] for r in subset)

            cov_count = ts_count + fs_count
            cov_rate = cov_count / n_ep
            ts_rate = ts_count / n_ep
            fs_rate = fs_count / n_ep
            abs_rate = abs_count / n_ep

            covered_risk = fs_count / cov_count if cov_count > 0 else "N/A"

            steps_list = [r["steps"] for r in subset]
            queries_list = [r["anchor_queries"] for r in subset]
            cost_list = [r["anchor_cost"] for r in subset]
            overshoot_list = [r["max_overshoot"] for r in subset]
            bias_errs = [r["bias_error"] for r in subset if r["bias_error"] is not None]

            summary_rows.append({
                "scenario": scen.name,
                "configuration": cfg_key,
                "episodes": n_ep,
                "true_success_count": ts_count,
                "true_success_rate": round(ts_rate, 4),
                "task_coverage_rate": round(cov_rate, 4),
                "false_success_count": fs_count,
                "false_success_rate": round(fs_rate, 4),
                "covered_risk": round(covered_risk, 4) if isinstance(covered_risk, float) else "N/A",
                "abstention_rate": round(abs_rate, 4),
                "calibration_rate": round(cal_count / n_ep, 4),
                "mean_bias_error": round(float(np.mean(bias_errs)), 4) if bias_errs else "N/A",
                "mean_steps": round(float(np.mean(steps_list)), 1),
                "mean_anchor_queries": round(float(np.mean(queries_list)), 2),
                "mean_anchor_cost": round(float(np.mean(cost_list)), 4),
                "mean_max_overshoot": round(float(np.mean(overshoot_list)), 4),
            })

    print(f"Writing ablation summary ({len(summary_rows)} rows) to {summary_csv}...")
    with open(summary_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    elapsed = time.time() - t_start
    print(f"\nV7 Component Ablation Suite Complete in {elapsed:.2f} seconds.")


if __name__ == "__main__":
    run_v7_ablation()
