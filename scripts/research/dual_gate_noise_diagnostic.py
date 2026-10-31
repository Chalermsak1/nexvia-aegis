#!/usr/bin/env python3
"""Analytical toy model of consecutive dual-sensor low-speed observations.

This models independent stationary samples; it is not an episode success or
safety probability. No simulator or V9-M4 Holdout data is accessed.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def stationary_vector_probability(threshold, sigma):
    """P(||X|| <= threshold) for X ~ N(0, sigma² I_3)."""
    if not math.isfinite(threshold) or not math.isfinite(sigma) or threshold <= 0 or sigma <= 0:
        raise ValueError("threshold and sigma must be finite and positive")
    z = threshold / sigma
    return math.erf(z / math.sqrt(2)) - math.sqrt(2 / math.pi) * z * math.exp(-z * z / 2)


def probability_run_within_horizon(probability, run_length, horizon):
    """Exact chance of at least one run under independent Bernoulli draws."""
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("probability must be in [0,1]")
    if type(run_length) is not int or run_length <= 0 or type(horizon) is not int or horizon < 0:
        raise ValueError("run_length must be positive and horizon nonnegative")
    # State j is probability of no completed run and j trailing successes.
    states = [1.0] + [0.0] * (run_length - 1)
    for _ in range(horizon):
        next_states = [sum(states) * (1 - probability)] + [states[j - 1] * probability for j in range(1, run_length)]
        states = next_states
    return min(1.0, max(0.0, 1.0 - sum(states)))


def run_diagnostic(threshold, sigma, run_length, horizon, dropout):
    if not math.isfinite(dropout) or not 0 <= dropout <= 1:
        raise ValueError("dropout must be in [0,1]")
    single = stationary_vector_probability(threshold, sigma)
    joint = (single * (1 - dropout)) ** 2
    return {"assumptions": {"true_velocity": [0, 0, 0], "sigma_per_axis": sigma,
            "threshold": threshold, "sources": 2, "independent_axes_sources_and_time": True,
            "per_source_dropout": dropout, "dropout_independent_of_noise": True,
            "consecutive_fresh_samples": run_length, "horizon_samples": horizon},
            "single_source_probability": single, "joint_step_probability": joint,
            "one_fixed_window_probability": joint ** run_length,
            "at_least_one_run_in_horizon": probability_run_within_horizon(joint, run_length, horizon)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    payload = {"classification": "EXPLORATORY_ANALYTICAL_TOY_MODEL", "not_episode_success_probability": True,
               "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "conditions": [run_diagnostic(.05, .02, 20, 220, d) for d in (0., .1)]}
    with a.output.open("x", encoding="utf-8") as out:
        json.dump(payload, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
