import numpy as np
import pytest
from aegis.v9.velocity_freshness_candidate import VelocityFreshness, TimedVelocity, FreshVelocityStopCandidate
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from experiments.benchmark_physical_3d_cbf import run_3d_episode


def sample(seq, time, vector=(0., 0., 0.)):
    return TimedVelocity(vector, seq, time)


def test_accept_fresh_reject_duplicate_reorder_stale_and_future():
    gate = VelocityFreshness(max_age_seconds=0.1)
    assert gate.accept(sample(10, 1.0), 1.0) is not None
    assert gate.accept(sample(10, 1.0), 1.01) is None and gate.reason == "REPLAY_OR_REORDER"
    assert gate.accept(sample(9, 1.02), 1.02) is None and gate.reason == "REPLAY_OR_REORDER"
    assert gate.accept(sample(11, 0.9), 1.03) is None and gate.reason == "FUTURE_OR_STALE"
    assert gate.accept(sample(11, 1.2), 1.04) is None and gate.reason == "FUTURE_OR_STALE"
    assert gate.accept(sample(11, 1.05), 1.05) is not None


@pytest.mark.parametrize("reading", [None, sample(-1, 1), sample(True, 1), sample(1, float('nan')),
                                   sample(1, 1, (float('nan'), 0, 0)), sample(1, 1, (0, 0))])
def test_invalid_reading_rejected_without_advancing_sequence(reading):
    gate = VelocityFreshness()
    assert gate.accept(reading, 1.0) is None
    assert gate.last_sequence is None


def test_clock_rollback_and_reset():
    gate = VelocityFreshness()
    gate.accept(sample(0, 1.0), 1.0)
    assert gate.accept(sample(1, 0.9), 0.9) is None
    assert gate.reason == "NON_MONOTONIC_CLOCK"
    gate.reset()
    assert gate.accept(sample(0, 0.9), 0.9) is not None


def test_replayed_velocity_cannot_extend_low_speed_dwell():
    c = FreshVelocityStopCandidate(success_radius=0.25)
    c.base.update = lambda *args, **kwargs: (np.zeros(3), "STOP", np.zeros(3), False)
    c.update(None, None, None, velocity_reading=sample(0, 0), now_seconds=0)
    c.update(None, None, None, velocity_reading=sample(1, .02), now_seconds=.02)
    assert c.low_speed_samples == 1
    result = c.update(None, None, None, velocity_reading=sample(1, .02), now_seconds=.04)
    assert result[1] == "VERIFY" and not result[3]
    assert c.low_speed_samples == 0 and c.velocity_gate.reason == "FUTURE_OR_STALE"


def test_freshness_does_not_validate_truth_of_a_plausible_spoof():
    # Metadata validation cannot detect a forged value or timestamp.
    gate = VelocityFreshness()
    assert np.array_equal(gate.accept(sample(0, 0, (0, 0, 0)), 0), np.zeros(3))


def test_simulated_latency_is_delivered_with_original_timestamp_and_rejected():
    env = AegisMuJoCo3DEnvironment()
    trace = []
    row = run_3d_episode(env, "AEGIS_3D_FRESH_VELOCITY", 2243000, np.zeros(3),
                         max_steps=30, velocity_latency_steps=2, trace=trace)
    delayed = [x for x in trace if x["velocity_observation"] is not None]
    assert delayed and all(x["velocity_gate_reason"] == "FUTURE_OR_STALE" for x in delayed)
    assert all(x["step"] - x["velocity_sequence"] == 2 for x in delayed)
    assert row["velocity_gate_rejections"] == len(trace)
