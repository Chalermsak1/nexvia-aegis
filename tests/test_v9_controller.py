"""
NEXVIA AEGIS V9.0 — Unit & Integration Tests for `AegisV9Controller` Interface,
Fail-Closed Behavior, Zero Ground-Truth Leakage, and Historical Reproduction.
"""

from __future__ import annotations

import inspect
from pathlib import Path
import numpy as np
import pytest

from aegis.next.agent_next import AegisNextController
from aegis.v3.env.world import AegisPhysicalWorld
from aegis.v3.sensors.cross_modal import RangeReading, RangeSensor
from aegis.v3.sensors.sensors import FaultInjectableSensor, SensorConfig, SensorReading
from aegis.v7.anchor_sensor import AnchorReading, AnchorSensor, AnchorSensorConfig
from aegis.v9.controller import AegisV9Controller
from aegis.v9.risk_statistics import PREREGISTERED_CANDIDATE_FAMILY, load_frozen_candidates_json


class _TrapGroundTruthSensorReading:
    """
    Proxy around SensorReading that raises AssertionError if runtime code ever reads
    ground-truth `.bias`, `.drift`, `.anomaly`, or `.dropped`.
    """

    def __init__(self, estimate: np.ndarray, sigma: float = 0.05, valid: bool = True) -> None:
        self.estimate = np.asarray(estimate, dtype=np.float64)
        self.sigma = float(sigma)
        self.valid = bool(valid)

    @property
    def bias(self) -> np.ndarray:
        raise AssertionError("Ground-truth `.bias` accessed inside online controller!")

    @property
    def drift(self) -> np.ndarray:
        raise AssertionError("Ground-truth `.drift` accessed inside online controller!")

    @property
    def anomaly(self) -> bool:
        raise AssertionError("Ground-truth `.anomaly` accessed inside online controller!")

    @property
    def dropped(self) -> bool:
        raise AssertionError("Ground-truth `.dropped` accessed inside online controller!")


def test_exact_four_input_signature_parity_and_zero_ground_truth_access():
    """
    Verifies exact 4-input signature parity `(reading_a, reading_b, range_reading, anchor_reading=None, step=0)`
    and confirms zero access to hidden ground-truth fields across all controller modes.
    """
    sig_v8 = inspect.signature(AegisNextController.update)
    sig_v9 = inspect.signature(AegisV9Controller.update)
    assert list(sig_v9.parameters.keys()) == list(sig_v8.parameters.keys())
    assert sig_v9.parameters["anchor_reading"].default is None
    assert sig_v9.parameters["step"].default == 0

    ctrl = AegisV9Controller()
    ctrl.reset()

    # Step through NOMINAL -> ACTIVE_PROBING -> CALIBRATED using trap proxy objects
    for step in range(45):
        d = np.array([1.5 - 0.01 * step, 0.4])
        # Inject discrepancy on vec_a to exercise NOMINAL -> ACTIVE_PROBING -> CALIBRATED
        ra = _TrapGroundTruthSensorReading(d + np.array([0.7, -0.5]), sigma=0.05, valid=True)
        rb = _TrapGroundTruthSensorReading(d, sigma=0.05, valid=True)
        rr = RangeReading(distance=float(np.linalg.norm(d)), sigma=0.05, valid=True)
        anc = AnchorReading(
            estimate=d,
            sigma=0.04,
            valid=(step in (5, 15)),
            queried=(step in (5, 15)),
            cost_accrued=0.05 if (step in (5, 15)) else 0.0,
        )

        act, dec, cal_vec, query_next = ctrl.update(ra, rb, rr, anc, step=step)  # type: ignore[arg-type]
        assert isinstance(act, np.ndarray) and act.shape == (2,)
        assert np.all(act >= -1.0) and np.all(act <= 1.0)
        assert dec in ("ACT", "PROBE", "STOP", "ABSTAIN", "VERIFY")
        assert isinstance(cal_vec, np.ndarray) and cal_vec.shape == (2,)
        assert isinstance(query_next, bool)
        assert ctrl.last_telemetry is not None


def test_no_nominal_to_probing_fallthrough_and_no_invalid_range_arrival_bypass():
    """
    Regression test for V8 Audit Bugs #1 and #2:
    1. Triggering probing when perceived vector norm <= 0.22 m MUST return "PROBE", never "STOP".
    2. Dropped/invalid range (`valid=False`) at arrival MUST NEVER return "STOP" in NOMINAL
       or CALIBRATED mode, and transitions to "ABSTAIN" if range remains persistently invalid.
    """
    ctrl = AegisV9Controller()
    ctrl.reset()

    # 1. Suppose biased sensors report near-zero vector [0.10, 0.0] while true range is 1.50 m!
    ra = SensorReading(
        estimate=np.array([0.10, 0.0]), sigma=0.05, valid=True, anomaly=False,
        dropped=False, bias=np.zeros(2), drift=np.zeros(2),
    )
    rb = SensorReading(
        estimate=np.array([0.10, 0.0]), sigma=0.05, valid=True, anomaly=False,
        dropped=False, bias=np.zeros(2), drift=np.zeros(2),
    )
    rr_far = RangeReading(distance=1.50, sigma=0.05, valid=True)

    _, dec, _, _ = ctrl.update(ra, rb, rr_far, None, step=0)
    assert dec != "STOP"
    assert ctrl.mode == "ACTIVE_PROBING" or dec in ("PROBE", "VERIFY")

    # 2. Invalid/dropped range at arrival in NOMINAL mode: NEVER accepts "STOP"!
    ctrl.reset()
    rr_invalid = RangeReading(distance=0.0, sigma=0.05, valid=False, dropped=True)
    decisions = []
    for s in range(8):
        _, d_s, _, _ = ctrl.update(ra, rb, rr_invalid, None, step=s)
        decisions.append(d_s)
    assert "STOP" not in decisions
    assert decisions[-1] == "ABSTAIN"


def test_deterministic_replay_and_closed_loop_fault_safety():
    """
    Verifies bit-identical determinism on repeated runs and safe closed-loop execution in
    `AegisPhysicalWorld` under NOMINAL, INDEPENDENT_BIAS, and COMPOUND_HOLDOUT_EXTREME.
    """
    cand = PREREGISTERED_CANDIDATE_FAMILY[2]  # Tier 3

    def _run_ep(scen_cfg: dict, seed: int) -> tuple[str, float, list[str]]:
        rng_env = np.random.default_rng(seed)
        world = AegisPhysicalWorld()
        world.reset(rng_env)
        sa = FaultInjectableSensor(scen_cfg["sa"])
        sb = FaultInjectableSensor(scen_cfg["sb"])
        sr = RangeSensor(noise_sigma=scen_cfg["sig_r"], dropout_probability=0.0)
        anc = AnchorSensor(AnchorSensorConfig(is_corrupted=scen_cfg.get("anc_corrupt", False)))

        ctrl = AegisV9Controller(cand)
        ctrl.reset()
        rng_ep = np.random.default_rng(seed)
        query = False
        trace: list[str] = []

        for _ in range(world.config.max_steps):
            st = world.state()
            td = st["target_pos"] - st["robot_pos"]
            ra = sa.measure(td, rng_ep, step=st["step"])
            rb = sb.measure(td, rng_ep, step=st["step"])
            rr = sr.measure(float(st["distance"]) + scen_cfg.get("b_r", 0.0), rng_ep)
            r_anc = anc.measure(td, rng_ep, query=query)
            act, dec, _, query = ctrl.update(ra, rb, rr, r_anc, step=st["step"])
            trace.append(dec)
            if dec in ("STOP", "ABSTAIN"):
                break
            if world.step(act, rng_ep)["truncated"]:
                break

        final_d = float(world.state()["distance"])
        world.close()
        return trace[-1], final_d, trace

    # Exact deterministic replay
    indep_cfg = {
        "sa": SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.6, 0.4)),
        "sb": SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.5, 0.5)),
        "sig_r": 0.05,
    }
    term1, dist1, tr1 = _run_ep(indep_cfg, 70001)
    term2, dist2, tr2 = _run_ep(indep_cfg, 70001)
    assert tr1 == tr2 and dist1 == dist2
    # Must recover and dock safely in INDEPENDENT_BIAS
    assert term1 == "STOP" and dist1 <= 0.45

    # COMPOUND_HOLDOUT_EXTREME (-0.40m range shift + drift + common bias): must NOT commit false success!
    comp_cfg = {
        "sa": SensorConfig(name="vec_a", noise_sigma=0.06, bias=(0.5, 0.5), drift_rate=(0.002, 0.002)),
        "sb": SensorConfig(name="vec_b", noise_sigma=0.06, bias=(0.5, 0.5)),
        "sig_r": 0.06,
        "b_r": -0.40,
    }
    term_c, dist_c, _ = _run_ep(comp_cfg, 70002)
    assert not (term_c == "STOP" and dist_c > 0.45)


def test_historical_v8_bit_level_reproduction():
    """
    Confirms historical `AegisNextController` remains 100% unmodified and reproduces the exact
    recorded `results/next/benchmark_episodes.csv` outcomes on `NOMINAL` (seed=60000) and
    `INDEPENDENT_BIAS` (seeds 60001 and 60002).
    """
    cases = (
        (
            "NOMINAL",
            60000,
            SensorConfig(name="vec_a", noise_sigma=0.05),
            SensorConfig(name="vec_b", noise_sigma=0.05),
            1,  # true_success
            0,  # false_success
            0,  # abstain
            0.2271,
            173,
            0,
        ),
        (
            "INDEPENDENT_BIAS",
            60001,
            SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.6, 0.4)),
            SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.5, 0.5)),
            1,
            0,
            0,
            0.2390,
            131,
            1,
        ),
        (
            "INDEPENDENT_BIAS",
            60002,
            SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.6, 0.4)),
            SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.5, 0.5)),
            0,
            1,
            0,
            0.4613,
            173,
            0,
        ),
    )
    for (
        _scen_name,
        seed,
        sa_cfg,
        sb_cfg,
        exp_ts,
        exp_fs,
        exp_ab,
        exp_dist,
        exp_steps,
        exp_queries,
    ) in cases:
        rng_env = np.random.default_rng(seed)
        world = AegisPhysicalWorld()
        world.reset(rng_env)
        sa = FaultInjectableSensor(sa_cfg)
        sb = FaultInjectableSensor(sb_cfg)
        sr = RangeSensor(noise_sigma=0.05)
        anc = AnchorSensor(AnchorSensorConfig())
        ctrl = AegisNextController()
        rng_ep = np.random.default_rng(seed)
        q = False
        stopped = False
        abstained = False
        for _ in range(world.config.max_steps):
            st = world.state()
            td = st["target_pos"] - st["robot_pos"]
            act, dec, _, q = ctrl.update(
                sa.measure(td, rng_ep, step=st["step"]),
                sb.measure(td, rng_ep, step=st["step"]),
                sr.measure(float(st["distance"]), rng_ep),
                anc.measure(td, rng_ep, query=q),
                step=st["step"],
            )
            if dec == "STOP":
                stopped = True
                break
            if dec == "ABSTAIN":
                abstained = True
                break
            if world.step(act, rng_ep)["truncated"]:
                break
        final_st = world.state()
        final_d = float(final_st["distance"])
        world.close()

        ts = int(stopped and final_d <= 0.45)
        fs = int(stopped and final_d > 0.45)
        ab = int(abstained or (not stopped and not bool(ts)))
        assert ts == exp_ts
        assert fs == exp_fs
        assert ab == exp_ab
        assert round(final_d, 4) == exp_dist
        assert final_st["step"] == exp_steps
        assert anc.total_queries == exp_queries


def test_frozen_candidates_config_loads_and_instantiates_all_six_policies():
    """
    Loads `configs/v9_candidates_frozen.json`, verifies its canonical SHA-256 digest,
    commit provenance, D_dev-only metadata, and instantiates all 6 candidate controllers.
    """
    repo_root = Path(__file__).resolve().parents[1]
    cfg_path = repo_root / "configs" / "v9_candidates_frozen.json"
    assert cfg_path.exists(), f"Missing frozen config at {cfg_path}"

    candidates, meta = load_frozen_candidates_json(cfg_path)
    assert len(candidates) == 6
    assert meta["source_design_commit"] == "891c13e7bbd60e36c416c9bada8407e51233e663"
    assert meta["v81_baseline_commit"] == "4d891c7500cfb4c8110f276038455bc62765ef3b"
    assert meta["calibration_and_holdout_data_used"] is False
    assert meta["development_manifest"]["seed_start"] == 70000
    assert meta["development_manifest"]["seed_end_inclusive"] == 70029
    assert meta["development_ordering_verification"]["tier1_precheck_passed"] is True
    assert meta["development_ordering_verification"]["all_candidates_admissible"] is True

    for expected, loaded in zip(PREREGISTERED_CANDIDATE_FAMILY, candidates, strict=True):
        assert loaded == expected
        ctrl = AegisV9Controller(loaded)
        ctrl.reset()
        assert ctrl.params == expected


def test_dev_runner_seed_and_crash_accounting_guardrails():
    """
    Verifies D_dev seed/output isolation guards and fail-unsafe runtime crash accounting
    (`crashed == 1 -> false_success == 1, accepted == 0`).
    """
    import importlib.util
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "v9_evaluate_dev", repo_root / "experiments" / "v9_evaluate_dev.py"
    )
    assert spec is not None and spec.loader is not None
    dev_mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = dev_mod
    spec.loader.exec_module(dev_mod)

    # Prohibited seeds (D_hist, D_cal, D_val, D_test^mix, D_test^scen) MUST raise ValueError
    for bad_seed in (60000, 70030, 71000, 72000, 73000, 75000):
        with pytest.raises(ValueError, match="PROHIBITED SEED ACCESS BLOCKED"):
            dev_mod.enforce_dev_only_seeds([bad_seed])

    # Prohibited output directories MUST raise ValueError
    for bad_dir in ("results/next", "results/v8_audit", "results/v9/cal", "results/v9/test_mix"):
        with pytest.raises(ValueError):
            dev_mod.enforce_dev_output_directory(bad_dir)

    # Fail-unsafe crash accounting: unhandled exception inside controller.update -> crashed=1, FS=1
    class _CrashingController:
        def reset(self) -> None:
            pass

        def update(self, *args, **kwargs):
            raise RuntimeError("Simulated controller failure")

    nom_scen = dev_mod.build_v9_s12_scenarios()[0]
    rec = dev_mod.run_single_episode(nom_scen, 70000, "CRASH_TEST", _CrashingController())
    assert rec["crashed"] == 1
    assert rec["false_success"] == 1
    assert rec["true_success"] == 0
    assert rec["accepted"] == 0
    assert "Simulated controller failure" in rec["crash_error"]
