"""
NEXVIA AEGIS V9.0 — Risk-Calibrated Runtime Assurance and Compound-Fault Recovery.
"""

from __future__ import annotations

from aegis.v9.anchor_range_gate import (
    AnchorRangeGateResult,
    AnchorRangeStatus,
    SymmetricAnchorRangeGate,
)
from aegis.v9.controller import AegisV9Controller, AegisV9Telemetry
from aegis.v9.controller_3d import Aegis3DAwareController
from aegis.v9.cusum_monitor import (
    CusumChannelSpec,
    CusumStepResult,
    MultiChannelCusumMonitor,
)
from aegis.v9.randomization import (
    DecoupledEpisodeRNG,
    V9HierarchicalManifestGenerator,
    create_decoupled_rng_pair,
    instantiate_episode_rngs_from_manifest_item,
)
from aegis.v9.risk_statistics import (
    PREREGISTERED_CANDIDATE_FAMILY,
    CandidateTestRecord,
    FixedSequenceLTTResult,
    PolicyEvaluationSummary,
    V9CandidateParams,
    clopper_pearson_one_sided_ucb,
    clopper_pearson_two_sided_ci,
    compute_canonical_payload_sha256,
    compute_policy_summary,
    fixed_sequence_ltt_select,
    holm_stepdown_ltt,
    load_frozen_candidates_json,
    minimum_zero_error_acceptances,
    selective_risk_pvalue,
    verify_preregistered_dev_ordering,
    write_frozen_candidates_json,
)
from aegis.v9.scenarios import (
    V9ScenarioSpec,
    build_v9_s12_scenarios,
)
from aegis.v9.sensor_calibration import (
    CalibratedFusionResult,
    DisjointPerSensorCalibrator,
    PerSensorCalibrationState,
    SensorCalStatus,
)
from aegis.v9.ville_monitor import (
    MultiChannelVilleMonitor,
    VilleChannelSpec,
    VilleStepResult,
)

__all__ = [
    "Aegis3DAwareController",
    "AegisV9Controller",
    "AegisV9Telemetry",
    "AnchorRangeGateResult",
    "AnchorRangeStatus",
    "CalibratedFusionResult",
    "CandidateTestRecord",
    "CusumChannelSpec",
    "CusumStepResult",
    "DecoupledEpisodeRNG",
    "DisjointPerSensorCalibrator",
    "FixedSequenceLTTResult",
    "MultiChannelCusumMonitor",
    "MultiChannelVilleMonitor",
    "PREREGISTERED_CANDIDATE_FAMILY",
    "PerSensorCalibrationState",
    "PolicyEvaluationSummary",
    "SensorCalStatus",
    "SymmetricAnchorRangeGate",
    "V9CandidateParams",
    "V9HierarchicalManifestGenerator",
    "V9ScenarioSpec",
    "VilleChannelSpec",
    "VilleStepResult",
    "build_v9_s12_scenarios",
    "clopper_pearson_one_sided_ucb",
    "clopper_pearson_two_sided_ci",
    "compute_canonical_payload_sha256",
    "compute_policy_summary",
    "create_decoupled_rng_pair",
    "fixed_sequence_ltt_select",
    "holm_stepdown_ltt",
    "instantiate_episode_rngs_from_manifest_item",
    "load_frozen_candidates_json",
    "minimum_zero_error_acceptances",
    "selective_risk_pvalue",
    "verify_preregistered_dev_ordering",
    "write_frozen_candidates_json",
]
