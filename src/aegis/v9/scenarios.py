"""
NEXVIA AEGIS V9 — 12-Scenario Specification Suite (S_12 = S_10 U S_ext).

Defines the prespecified evaluation scenarios registered in:
`docs/v9_experiment_protocol.md` (Table 3.1.2)
and amended in `docs/v9_m2r1_protocol_amendment.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

from aegis.v3.sensors.sensors import SensorConfig


@dataclass(frozen=True)
class V9ScenarioSpec:
    """Frozen scenario definition in the 12-scenario suite S_12."""

    index: int
    name: str
    suite: str
    description: str
    sensor_a: SensorConfig
    sensor_b: SensorConfig
    range_sensor_noise: float = 0.05
    range_sensor_bias: float = 0.0
    range_dropout_prob: float = 0.0
    anchor_corrupted: bool = False


def build_v9_s12_scenarios() -> tuple[V9ScenarioSpec, ...]:
    """
    Constructs the exact 12-scenario suite S_12 = S_10 U S_ext defined in
    `docs/v9_experiment_protocol.md` Table 3.1.2 (preserving S_10 bit-identically
    with `experiments/benchmark_next.py:71-160`).
    """
    return (
        V9ScenarioSpec(
            index=1,
            name="NOMINAL",
            suite="S_10",
            description="Baseline operation under nominal Gaussian sensor noise",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=2,
            name="PRIMARY_BIAS",
            suite="S_10",
            description="Static spatial bias on primary sensor A (+0.8, -0.6)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.8, -0.6)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=3,
            name="INDEPENDENT_BIAS",
            suite="S_10",
            description="Independent non-identical biases on vector A (+0.6, +0.4) and B (-0.5, +0.5)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.6, 0.4)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.5, 0.5)),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=4,
            name="CORRELATED_BIAS",
            suite="S_10",
            description="Common-mode correlated bias (+0.7, +0.7) on both vector sensors",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=5,
            name="SENSOR_DRIFT",
            suite="S_10",
            description="Non-stationary dynamic drift on sensor A (0.003*t, 0.0015*t)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, drift_rate=(0.003, 0.0015)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=6,
            name="OUTLIER_BURSTS",
            suite="S_10",
            description="Heavy-tailed outlier bursts (p=0.12, 4.5x scale)",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.05, outlier_probability=0.12, outlier_scale=4.5
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=7,
            name="SENSOR_DROPOUT",
            suite="S_10",
            description="Intermittent packet loss (p=0.40) on sensor A",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, dropout_probability=0.40),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05),
            range_sensor_noise=0.05,
        ),
        V9ScenarioSpec(
            index=8,
            name="FAULTY_REFERENCE_SENSOR",
            suite="S_10",
            description="Correlated vector bias (+0.7, +0.7) AND range corrupted (+1.0m bias)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            range_sensor_bias=1.0,
        ),
        V9ScenarioSpec(
            index=9,
            name="CORRUPTED_ANCHOR_STRESS",
            suite="S_10",
            description="Correlated vector bias (+0.7, +0.7) AND anchor corrupted (+1.2, -1.0m bias)",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.7, 0.7)),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(0.7, 0.7)),
            range_sensor_noise=0.05,
            anchor_corrupted=True,
        ),
        V9ScenarioSpec(
            index=10,
            name="COMPOUND_HOLDOUT_EXTREME",
            suite="S_10",
            description="Held-out compound stress: vector drift + common bias + range shift (-0.40m)",
            sensor_a=SensorConfig(
                name="vec_a", noise_sigma=0.06, bias=(0.5, 0.5), drift_rate=(0.002, 0.002)
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.06, bias=(0.5, 0.5)),
            range_sensor_noise=0.06,
            range_sensor_bias=-0.40,
        ),
        V9ScenarioSpec(
            index=11,
            name="COMPOUND_DRIFT_DROPOUT",
            suite="S_ext",
            description="Asymmetric drift + 30% vec_a dropout + 10% range dropout",
            sensor_a=SensorConfig(
                name="vec_a",
                noise_sigma=0.05,
                bias=(0.0, 0.0),
                drift_rate=(0.0025, -0.0020),
                dropout_probability=0.30,
            ),
            sensor_b=SensorConfig(name="vec_b", noise_sigma=0.05, bias=(-0.45, 0.35)),
            range_sensor_noise=0.05,
            range_sensor_bias=0.0,
            range_dropout_prob=0.10,
        ),
        V9ScenarioSpec(
            index=12,
            name="COMPOUND_ANTIPODAL_RANGE_SHIFT",
            suite="S_ext",
            description="Near-canceling antipodal biases + 35% vec_b dropout jumps + -0.30m range shift",
            sensor_a=SensorConfig(name="vec_a", noise_sigma=0.05, bias=(0.55, 0.40)),
            sensor_b=SensorConfig(
                name="vec_b",
                noise_sigma=0.05,
                bias=(-0.45, -0.35),
                dropout_probability=0.35,
            ),
            range_sensor_noise=0.05,
            range_sensor_bias=-0.30,
        ),
    )


# Canonical alias
build_v9_evaluation_scenarios = build_v9_s12_scenarios
