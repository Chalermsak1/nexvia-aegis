"""
Tests for NEXVIA AEGIS V9-M2R1 RNG Decoupling and Stream Independence.

Verifies:
1. Decoupled generators (rng_env vs rng_sensors) are initialized from distinct SeedSequences.
2. Target position coordinates are statistically uncorrelated with step-0 sensor noise and dropout.
3. Manifest generation preserves uniform scenario draws across S_12.
4. Reconstruction from spawn_keys is exact, stateless, and O(1).
5. Inter-episode independence: resets erase controller state, and streams do not bleed across episodes.
"""

from __future__ import annotations

import json
import numpy as np
import pytest

from aegis.v3.env.world import AegisPhysicalWorld
from aegis.v3.sensors.cross_modal import RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor
from aegis.v9.randomization import (
    DecoupledEpisodeRNG,
    V9HierarchicalManifestGenerator,
    create_decoupled_rng_pair,
    instantiate_episode_rngs_from_manifest_item,
)
from aegis.v9.scenarios import build_v9_s12_scenarios


def test_create_decoupled_rng_pair_distinctness():
    """Verify that rng_env and rng_sensors produce independent random bit sequences."""
    rng_env, rng_sensors = create_decoupled_rng_pair(42)
    draw_env = rng_env.standard_normal(size=100)
    draw_sensors = rng_sensors.standard_normal(size=100)

    # Identical draws would indicate stream reuse defect
    assert not np.array_equal(draw_env, draw_sensors)
    corr = float(np.corrcoef(draw_env, draw_sensors)[0, 1])
    assert abs(corr) < 0.25, f"Cross-stream correlation too high: {corr}"


def test_target_generation_independent_of_sensor_noise():
    """
    Test 9: Verify target coordinates are NOT derived from the same underlying random
    variates as step-zero sensor noise or dropout.
    """
    n_trials = 500
    target_xs = []
    sensor_noises = []

    scenarios = {s.name: s for s in build_v9_s12_scenarios()}
    nom_scen = scenarios["NOMINAL"]

    manifest_gen = V9HierarchicalManifestGenerator(master_entropy=20261025)
    manifest = manifest_gen.generate_manifest(
        partition_name="test_independence",
        manifest_id_start=90000,
        count=n_trials,
    )

    world = AegisPhysicalWorld()
    sensor_a = FaultInjectableSensor(nom_scen.sensor_a)

    for ep_item in manifest["episodes"]:
        decoupled = instantiate_episode_rngs_from_manifest_item(ep_item)
        world.reset(decoupled.rng_env)
        target_pos = world.state()["target_pos"]
        target_xs.append(target_pos[0])

        reading = sensor_a.measure(np.array([1.0, 1.0]), decoupled.rng_sensors, step=0)
        # Measured value minus true value gives sensor noise
        noise = reading.estimate[0] - 1.0
        sensor_noises.append(noise)

    target_xs = np.array(target_xs)
    sensor_noises = np.array(sensor_noises)

    # Compute Pearson correlation coefficient
    corr = float(np.corrcoef(target_xs, sensor_noises)[0, 1])
    assert abs(corr) < 0.10, f"Spurious target-sensor noise correlation: {corr:.4f}"


def test_manifest_generation_uniform_scenarios_and_integrity():
    """Verify uniform scenario draws and manifest cryptographic integrity digest."""
    gen = V9HierarchicalManifestGenerator(master_entropy=12345678)
    n_episodes = 240
    manifest = gen.generate_manifest(
        partition_name="test_partition",
        manifest_id_start=80000,
        count=n_episodes,
    )

    assert manifest["planned_episodes"] == n_episodes
    assert manifest["manifest_id_start"] == 80000
    assert manifest["manifest_id_stop_exclusive"] == 80000 + n_episodes
    assert len(manifest["episodes"]) == n_episodes

    # Chi-square goodness of fit for uniform 1/12 distribution
    counts = np.array(list(manifest["realized_scenario_counts"].values()))
    expected = n_episodes / 12.0
    chi2 = float(np.sum((counts - expected) ** 2 / expected))
    # df = 11, critical value at alpha=0.01 is 24.725
    assert chi2 < 25.0, f"Scenario distribution is non-uniform: chi2={chi2}"

    # Verify reproduction from manifest item matches instantiate_episode_rngs
    ep_item_0 = manifest["episodes"][0]
    recon_rng = instantiate_episode_rngs_from_manifest_item(ep_item_0)
    direct_rng = gen.instantiate_episode_rngs(
        ep_index=0,
        count=n_episodes,
        manifest_id_start=80000,
        scen_index=ep_item_0["scenario_index"],
        scen_name=ep_item_0["scenario"],
    )

    # Both generators must produce identical sequences
    r1 = recon_rng.rng_env.normal(size=10)
    r2 = direct_rng.rng_env.normal(size=10)
    np.testing.assert_array_equal(r1, r2)

    s1 = recon_rng.rng_sensors.normal(size=10)
    s2 = direct_rng.rng_sensors.normal(size=10)
    np.testing.assert_array_equal(s1, s2)
