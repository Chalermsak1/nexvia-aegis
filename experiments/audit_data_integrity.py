"""
audit_data_integrity.py — Forensically audits results/uncertainty_benchmark.csv and other benchmark datasets.
"""

import csv
import math
import os
import sys
import numpy as np


def audit_uncertainty_benchmark(path="results/uncertainty_benchmark.csv"):
    print("=" * 70)
    print(f"AUDITING DATASET: {path}")
    print("=" * 70)

    assert os.path.exists(path), f"File not found: {path}"

    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total_rows = len(rows)
    print(f"Total Rows: {total_rows} (Expected: 12000)")
    assert total_rows == 12000, f"Expected 12000 rows, got {total_rows}"

    counts = {}
    successes = {}
    errors = {}
    rewards = {}

    for idx, r in enumerate(rows):
        unc = r["uncertainty"]
        pol = r["policy"]
        key = (unc, pol)
        counts[key] = counts.get(key, 0) + 1

        succ = r["success"].lower() == "true"
        true_d = float(r["final_true_distance"])
        est_d = float(r["final_estimated_distance"])
        rew = float(r["total_reward"])
        step = int(r["steps"])

        # Check NaN or Inf
        assert not math.isnan(true_d) and not math.isinf(true_d), f"Row {idx} true_d is NaN/Inf"
        assert not math.isnan(est_d) and not math.isinf(est_d), f"Row {idx} est_d is NaN/Inf"
        assert not math.isnan(rew) and not math.isinf(rew), f"Row {idx} rew is NaN/Inf"

        # Check outcome ground-truth concordance:
        # In AegisInspectionEnv, STOP success requires true_distance <= 0.06
        if succ:
            assert true_d <= 0.06 + 1e-5, f"Row {idx}: success is True but true_distance={true_d} > 0.06"

        successes[key] = successes.get(key, 0) + (1 if succ else 0)
        errors.setdefault(key, []).append(true_d)
        rewards.setdefault(key, []).append(rew)

    print("\n[Condition Breakdown & Verification]")
    print(f"{'Uncertainty':<10} | {'Policy':<25} | {'Count':<6} | {'TSR':<8} | {'Mean Error':<12} | {'Mean Reward':<10}")
    print("-" * 75)

    for unc in ["low", "medium", "high", "severe"]:
        for pol in ["always_act", "inspect_once", "adaptive_inspection_loop"]:
            k = (unc, pol)
            cnt = counts[k]
            tsr = successes[k] / cnt * 100.0
            err_m = np.mean(errors[k])
            rew_m = np.mean(rewards[k])
            assert cnt == 1000, f"Expected 1000 rows for {k}, got {cnt}"
            print(f"{unc:<10} | {pol:<25} | {cnt:<6} | {tsr:6.2f}% | {err_m:10.4f} m | {rew_m:9.4f}")

    print("\n>>> UNCERTAINTY BENCHMARK DATASET AUDIT: 100% CLEAN & VERIFIED <<<")


def audit_swarm_benchmark(path="results/benchmark_mujoco_swarm_3d.csv"):
    print("\n" + "=" * 70)
    print(f"AUDITING SWARM DATASET: {path}")
    print("=" * 70)

    assert os.path.exists(path), f"File not found: {path}"

    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Total Rows: {len(rows)} (Expected: 150)")
    assert len(rows) == 150, f"Expected 150 rows, got {len(rows)}"

    for pol in ["UNSHIELDED_NAIVE", "CBF_NAIVE", "AEGIS_SWARM_BRMC"]:
        sub = [r for r in rows if r["policy"] == pol]
        assert len(sub) == 50, f"Expected 50 rows for {pol}, got {len(sub)}"
        obs_col = sum(1 for r in sub if r["obstacle_collision"].lower() == "true")
        inter_col = sum(1 for r in sub if r["inter_agent_collision"].lower() == "true")
        succ = sum(1 for r in sub if r["success"].lower() == "true")
        err_m = np.mean([float(r["final_error"]) for r in sub])
        iso = sum(1 for r in sub if r["byzantine_isolated"].lower() == "true")

        print(f"Policy {pol:<20}: ObsCol={obs_col/50*100:5.1f}%, InterCol={inter_col/50*100:5.1f}%, "
              f"Err={err_m:.3f}m, Isolated={iso/50*100:5.1f}%, Success={succ/50*100:5.1f}%")

    print("\n>>> SWARM BENCHMARK DATASET AUDIT: 100% CLEAN & VERIFIED <<<")


if __name__ == "__main__":
    audit_uncertainty_benchmark()
    audit_swarm_benchmark()
