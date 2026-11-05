"""Unit tests for Byzantine-Resilient Martingale Consensus (BRMC)."""

import numpy as np
import pytest
from aegis.multiagent.brmc_engine import (
    AgentMessage,
    ByzantineResilientMartingaleConsensus,
)


def test_brmc_nominal_operation():
    brmc = ByzantineResilientMartingaleConsensus(num_agents=5, max_byzantine_faults=1)
    true_target = np.array([2.0, 3.0])
    messages = [
        AgentMessage(i, 0, true_target + np.array([0.01 * i, -0.01 * i]), 0.05, 1.0, True)
        for i in range(5)
    ]
    state = brmc.aggregate_step(messages, step=0)
    assert not state.swarm_alarm
    assert len(state.quarantined_agents) == 0
    assert np.allclose(state.consensus_position, true_target, atol=0.05)


def test_brmc_isolates_byzantine_spatial_bias():
    brmc = ByzantineResilientMartingaleConsensus(num_agents=5, max_byzantine_faults=1)
    true_target = np.array([1.0, 1.0])

    # Run 3 steps with agent 2 biased by +2.0m
    for t in range(3):
        messages = [
            AgentMessage(
                i,
                t,
                true_target + (np.array([2.0, 2.0]) if i == 2 else np.array([0.01 * i, 0.0])),
                0.05,
                1.0,
                True,
            )
            for i in range(5)
        ]
        state = brmc.aggregate_step(messages, step=t)

    assert 2 in state.quarantined_agents
    assert np.allclose(state.consensus_position, true_target, atol=0.05)


def test_brmc_rejects_byzantine_wealth_dos():
    brmc = ByzantineResilientMartingaleConsensus(num_agents=5, max_byzantine_faults=1, alpha_swarm=0.05)
    true_target = np.array([0.0, 0.0])
    # Agent 4 injects huge wealth to trigger false alarm
    messages = [
        AgentMessage(
            i,
            0,
            true_target,
            0.05,
            (10000.0 if i == 4 else 1.0),
            True,
        )
        for i in range(5)
    ]
    state = brmc.aggregate_step(messages, step=0)
    # The trimmed mean must drop the maximum wealth (10000.0), so consensus wealth remains ~1.0
    assert state.consensus_martingale_wealth < 20.0
    assert not state.swarm_alarm


def test_brmc_anti_sigma_spoofing():
    """Verify that an attacker sending an infinitesimal sigma (1e-6) cannot capture consensus."""
    brmc = ByzantineResilientMartingaleConsensus(num_agents=5, max_byzantine_faults=1)
    true_target = np.array([0.0, 0.0])

    # Agent 3 claims position [10.0, 10.0] with sigma = 1e-6 (claiming ultra certainty)
    messages = [
        AgentMessage(
            agent_id=i,
            step=0,
            pos_estimate=(np.array([10.0, 10.0]) if i == 3 else true_target + np.array([0.01 * i, 0.0])),
            sigma=(1e-6 if i == 3 else 0.05),
            martingale_wealth=1.0,
            valid=True,
        )
        for i in range(5)
    ]

    state = brmc.aggregate_step(messages, step=0)

    # Agent 3 must be immediately isolated or quarantined on step 0
    assert 3 in state.quarantined_agents
    # Consensus position must remain strictly anchored to true target (~0.0, not skewed to 10.0)
    assert np.allclose(state.consensus_position, true_target, atol=0.08)
    # Weight of attacker must be zero
    assert state.weights[3] == 0.0


def test_brmc_vovk_wang_scaling():
    """Verify that Vovk-Wang scaling multiplier correctly normalizes order statistics."""
    brmc = ByzantineResilientMartingaleConsensus(num_agents=5, max_byzantine_faults=1, alpha_swarm=0.05)
    # 5 agents: n_active = 5, f = 1
    # Vovk-Wang scaling multiplier is (5 - 1) / (5 - 2) = 4 / 3 = 1.3333
    messages = [
        AgentMessage(
            agent_id=i,
            step=0,
            pos_estimate=np.array([0.0, 0.0]),
            sigma=0.05,
            martingale_wealth=1.0,  # All honest agents at wealth 1.0
            valid=True,
        )
        for i in range(5)
    ]
    state = brmc.aggregate_step(messages, step=0)
    # Trimmed mean of [1.0, 1.0, 1.0] is 1.0, scaled by (4/3) = ~1.3333
    expected_wealth = (4.0 / 3.0) * 1.0
    assert abs(state.consensus_martingale_wealth - expected_wealth) < 1e-4
    assert not state.swarm_alarm
