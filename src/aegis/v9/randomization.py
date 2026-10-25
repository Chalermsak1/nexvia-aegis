"""
NEXVIA AEGIS V9-M2R1 — Randomization Architecture & Decoupled Seed Sequences.

Eliminates the cross-stream RNG coupling identified in V9-M2:
1. Replaces identical `rng_env` / `rng_ep` initializations with independent child streams
   spawned via `numpy.random.SeedSequence`.
2. Decouples physical environment / target generation (`rng_env`) from measurement
   noise / dropout / outlier processes (`rng_sensors`).
3. Provides reproducible, hierarchical manifest generation with explicit entropy
   and spawn keys for complete cryptographic provenance.
4. Formulates the simulation probability law P_12 explicitly:
   - Scenario S_k ~ Uniform({1..12})
   - Initial target p_target ~ Uniform([-3, 3]^2) via rng_env
   - Robot start p_0 = (-2, -2, 0.25), v_0 = (0, 0)
   - Sensor noise eps ~ N(0, sigma^2) via rng_sensors
   - Dropout / outlier indicators ~ Bernoulli via rng_sensors
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any
import numpy as np

from aegis.v9.scenarios import build_v9_s12_scenarios


@dataclass(frozen=True)
class DecoupledEpisodeRNG:
    """Holds decoupled, mathematically independent random generators for one episode."""
    manifest_id: int
    scenario_index: int
    scenario_name: str
    rng_env: np.random.Generator
    rng_sensors: np.random.Generator
    spawn_key: tuple[int, ...]
    env_spawn_key: tuple[int, ...]
    sensor_spawn_key: tuple[int, ...]


def create_decoupled_rng_pair(
    seed_or_ss: int | np.random.SeedSequence,
) -> tuple[np.random.Generator, np.random.Generator]:
    """
    Creates two strictly independent NumPy PCG64 generators from a seed or SeedSequence.
    Guarantees that rng_env and rng_sensors are initialized with different internal keys.
    """
    if isinstance(seed_or_ss, int):
        ss = np.random.SeedSequence(seed_or_ss)
    else:
        ss = seed_or_ss
    env_ss, sens_ss = ss.spawn(2)
    rng_env = np.random.default_rng(env_ss)
    rng_sensors = np.random.default_rng(sens_ss)
    return rng_env, rng_sensors


PARTITION_BRANCH_DEV: int = 1
PARTITION_BRANCH_CALIBRATION: int = 2
PARTITION_BRANCH_VALIDATION: int = 3
PARTITION_BRANCH_TEST_MIXTURE: int = 4
PARTITION_BRANCH_TEST_SCENARIO: int = 5
PARTITION_BRANCH_DIAGNOSTIC_TESTS: int = 6


class V9HierarchicalManifestGenerator:
    """
    Hierarchical SeedSequence manifest generator for NEXVIA AEGIS V9-M2R1/R2.
    Supports partition-aware child branch derivation to guarantee mathematical
    stream disjointness across development, calibration, validation, and holdout suites.
    """

    def __init__(self, master_entropy: int = 20261025):
        self.master_entropy = master_entropy
        self.master_ss = np.random.SeedSequence(master_entropy)

    def generate_manifest(
        self,
        *,
        partition_name: str,
        manifest_id_start: int,
        count: int,
        partition_index: int | None = None,
    ) -> dict[str, Any]:
        """
        Generates an auditable manifest payload pairing manifest IDs with uniform scenario draws
        and decoupled SeedSequence child streams.
        When partition_index is provided (e.g. 2 for calibration_r2), derives streams from a dedicated
        partition child branch, guaranteeing zero stream collision with any other partition.
        """
        scenarios = build_v9_s12_scenarios()
        n_scen = len(scenarios)
        if n_scen != 12:
            raise RuntimeError(f"Expected 12 scenarios, found {n_scen}")

        if partition_index is not None:
            part_ss = np.random.SeedSequence(self.master_entropy, spawn_key=(partition_index,))
            branch_scen_ss, branch_eps_ss = part_ss.spawn(2)
        else:
            # Historical unbranched derivation (preserved for r1 provenance verification)
            master_ss = np.random.SeedSequence(self.master_entropy)
            branch_scen_ss, branch_eps_ss = master_ss.spawn(2)

        scen_rng = np.random.default_rng(branch_scen_ss)
        scen_indices = scen_rng.integers(0, n_scen, size=count)

        ep_sequences = branch_eps_ss.spawn(count)

        episodes: list[dict[str, Any]] = []
        counts: dict[str, int] = {s.name: 0 for s in scenarios}
        pairs_for_hash: list[tuple[str, int, int]] = []

        for idx in range(count):
            m_id = manifest_id_start + idx
            sc_idx = int(scen_indices[idx])
            scen_name = scenarios[sc_idx].name
            counts[scen_name] += 1

            ep_ss = ep_sequences[idx]
            env_ss, sens_ss = ep_ss.spawn(2)

            ep_item: dict[str, Any] = {
                "episode_index": idx,
                "manifest_id": m_id,
                "scenario_index": sc_idx,
                "scenario": scen_name,
                "suite": "S_12",
                "entropy": int(self.master_entropy),
                "spawn_key": list(ep_ss.spawn_key),
                "env_spawn_key": list(env_ss.spawn_key),
                "sensor_spawn_key": list(sens_ss.spawn_key),
            }
            if partition_index is not None:
                ep_item["partition_index"] = partition_index
            episodes.append(ep_item)
            pairs_for_hash.append((scen_name, m_id, sc_idx))

        raw_ep_bytes = json.dumps(pairs_for_hash, sort_keys=True).encode("utf-8")
        episodes_sha256 = hashlib.sha256(raw_ep_bytes).hexdigest()

        payload: dict[str, Any] = {
            "schema_version": "nexvia-aegis-v9-manifest/2.0-decoupled-rng",
            "protocol_version": "v9.0-preregistered-2026-10-amendment-r1",
            "partition": partition_name,
            "master_entropy": int(self.master_entropy),
            "manifest_id_start": manifest_id_start,
            "manifest_id_stop_exclusive": manifest_id_start + count,
            "planned_episodes": count,
            "num_scenarios": n_scen,
            "target_mixture_weights_rational": {s.name: "1/12" for s in scenarios},
            "realized_scenario_counts": counts,
            "episodes_sha256": episodes_sha256,
            "episodes": episodes,
        }

        canon_bytes = json.dumps(
            {k: v for k, v in payload.items() if k != "integrity_sha256"},
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        payload["integrity_sha256"] = hashlib.sha256(canon_bytes).hexdigest()
        return payload

    def generate_stratified_manifest(
        self,
        *,
        partition_name: str,
        seed_start: int,
        seeds_per_scenario: int,
        partition_index: int = PARTITION_BRANCH_VALIDATION,
    ) -> dict[str, Any]:
        """
        Generates an auditable stratified manifest for deterministic grids
        [(scenario, seed) for scenario in S_12 for seed in range(seed_start, seed_start + seeds_per_scenario)].
        Uses partition-branched SeedSequence derivation (spawn_key=(partition_index,)) to guarantee
        zero stream collision with any other partition.
        """
        scenarios = build_v9_s12_scenarios()
        n_scen = len(scenarios)
        if n_scen != 12:
            raise RuntimeError(f"Expected 12 scenarios, found {n_scen}")

        total_episodes = n_scen * seeds_per_scenario
        part_ss = np.random.SeedSequence(self.master_entropy, spawn_key=(partition_index,))
        branch_scen_ss, branch_eps_ss = part_ss.spawn(2)
        ep_sequences = branch_eps_ss.spawn(total_episodes)

        episodes: list[dict[str, Any]] = []
        counts: dict[str, int] = {s.name: 0 for s in scenarios}
        pairs_for_hash: list[tuple[str, int, int, int]] = []

        ep_idx = 0
        for sc_idx, scen in enumerate(scenarios):
            for s_offset in range(seeds_per_scenario):
                m_id = seed_start + s_offset
                scen_name = scen.name
                counts[scen_name] += 1

                ep_ss = ep_sequences[ep_idx]
                env_ss, sens_ss = ep_ss.spawn(2)

                ep_item: dict[str, Any] = {
                    "episode_index": ep_idx,
                    "seed": m_id,
                    "manifest_id": m_id,
                    "scenario_index": sc_idx,
                    "scenario": scen_name,
                    "suite": scen.suite,
                    "entropy": int(self.master_entropy),
                    "partition_index": partition_index,
                    "spawn_key": list(ep_ss.spawn_key),
                    "env_spawn_key": list(env_ss.spawn_key),
                    "sensor_spawn_key": list(sens_ss.spawn_key),
                }
                episodes.append(ep_item)
                pairs_for_hash.append((scen_name, m_id, sc_idx, ep_idx))
                ep_idx += 1

        raw_ep_bytes = json.dumps(pairs_for_hash, sort_keys=True).encode("utf-8")
        episodes_sha256 = hashlib.sha256(raw_ep_bytes).hexdigest()

        payload: dict[str, Any] = {
            "schema_version": "nexvia-aegis-v9-manifest/2.0-decoupled-rng",
            "protocol_version": "v9.0-preregistered-2026-10-amendment-r2",
            "source_commit": "150629aba9059fe627ca395d49489f139fb017db",
            "v9_m1_commit": "6c87f66a9ea602c96d4fe8bfc97728d0513b157f",
            "v81_baseline_commit": "4d891c7500cfb4c8110f276038455bc62765ef3b",
            "partition": partition_name,
            "sampling_design": "stratified_deterministic_grid",
            "master_entropy": int(self.master_entropy),
            "partition_index": partition_index,
            "seed_start": seed_start,
            "seed_stop_exclusive": seed_start + seeds_per_scenario,
            "seeds_per_scenario": seeds_per_scenario,
            "planned_episodes": total_episodes,
            "num_scenarios": n_scen,
            "scenario_catalog": [s.name for s in scenarios],
            "target_mixture_weights_rational": {s.name: "1/12" for s in scenarios},
            "target_mixture_weights_float": {s.name: 1.0 / 12.0 for s in scenarios},
            "realized_scenario_counts": counts,
            "episodes_sha256": episodes_sha256,
            "episodes": episodes,
        }

        canon_bytes = json.dumps(
            {k: v for k, v in payload.items() if k != "integrity_sha256"},
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        payload["integrity_sha256"] = hashlib.sha256(canon_bytes).hexdigest()
        return payload

    def instantiate_episode_rngs(
        self,
        ep_index: int,
        count: int,
        manifest_id_start: int,
        scen_index: int,
        scen_name: str,
        partition_index: int | None = None,
    ) -> DecoupledEpisodeRNG:
        """Instantiates the exact decoupled generators for episode ep_index."""
        if partition_index is not None:
            part_ss = np.random.SeedSequence(self.master_entropy, spawn_key=(partition_index,))
            _branch_scen_ss, branch_eps_ss = part_ss.spawn(2)
        else:
            master = np.random.SeedSequence(self.master_entropy)
            _branch_scen_ss, branch_eps_ss = master.spawn(2)
        ep_sequences = branch_eps_ss.spawn(count)
        ep_ss = ep_sequences[ep_index]
        env_ss, sens_ss = ep_ss.spawn(2)
        return DecoupledEpisodeRNG(
            manifest_id=manifest_id_start + ep_index,
            scenario_index=scen_index,
            scenario_name=scen_name,
            rng_env=np.random.default_rng(env_ss),
            rng_sensors=np.random.default_rng(sens_ss),
            spawn_key=ep_ss.spawn_key,
            env_spawn_key=env_ss.spawn_key,
            sensor_spawn_key=sens_ss.spawn_key,
        )


def instantiate_episode_rngs_from_manifest_item(item: dict[str, Any]) -> DecoupledEpisodeRNG:
    """
    Direct O(1) instantiation of DecoupledEpisodeRNG from an auditable manifest item dict.
    Uses master entropy and child spawn_keys recorded in the manifest.
    """
    entropy = int(item["entropy"])
    env_key = tuple(item["env_spawn_key"])
    sens_key = tuple(item["sensor_spawn_key"])
    ep_key = tuple(item.get("spawn_key", ()))
    env_ss = np.random.SeedSequence(entropy, spawn_key=env_key)
    sens_ss = np.random.SeedSequence(entropy, spawn_key=sens_key)
    return DecoupledEpisodeRNG(
        manifest_id=int(item["manifest_id"]),
        scenario_index=int(item["scenario_index"]),
        scenario_name=str(item["scenario"]),
        rng_env=np.random.default_rng(env_ss),
        rng_sensors=np.random.default_rng(sens_ss),
        spawn_key=ep_key,
        env_spawn_key=env_key,
        sensor_spawn_key=sens_key,
    )
