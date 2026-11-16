"""
NEXVIA AEGIS — Unit Tests for Multi-Drone Narrow Passage Cooperative Handover.

Verifies:
1. Sequential Right-of-Way Token Arbitration: Closest agent acquires token first.
2. FIFO Clearance: Token transfers sequentially as each drone crosses the exit threshold.
3. Asymmetric CBF Responsibility Allocation: Transiting drone has mu = 0.0, waiting drones have mu = 1.0.
4. Byzantine Revocation: If token holder is quarantined by BRMC, token is revoked immediately.
5. Watchdog Timeout Revocation: Stalled drone loses token after max_transit_steps.
6. 6-DOF Physical Swarm Execution: Drones queue and transit doorway without deadlock or collision.
"""

import math
import numpy as np
import mujoco
import pytest

from aegis.multiagent.passage_handover import (
    PassageHandoverCoordinator,
    PassageSpecification,
    PassageTokenState,
)
from aegis.multiagent.swarm_6dof import (
    AegisMuJoCoSwarm6DOFEnvironment,
    Swarm6DOFConfig,
)


def test_passage_handover_token_queue_and_fifo():
    """Validates sequential queueing and FIFO token transfer."""
    spec = PassageSpecification(
        passage_id=1,
        center=np.array([1.5, 0.0, 1.0]),
        axis=np.array([1.0, 0.0, 0.0]),
        width_m=0.60,
        height_m=1.80,
        length_m=0.80,
        standoff_dist_m=1.0,
    )
    coord = PassageHandoverCoordinator(spec)

    # 3 agents at varying distances along X
    # Agent 0 at X = 0.8 (closest to entrance at X = 1.1)
    # Agent 1 at X = 0.2
    # Agent 2 at X = -0.5
    positions = [
        np.array([0.8, 0.0, 1.0]),
        np.array([0.2, 0.0, 1.0]),
        np.array([-0.5, 0.0, 1.0]),
    ]
    velocities = [np.zeros(3) for _ in range(3)]

    # Step 1: Initial coordination
    coord.update_coordination(positions, velocities, current_step=1)

    assert coord.token_holder == 0, "Agent 0 (closest) must acquire token first"
    assert coord.token_state == PassageTokenState.IN_TRANSIT

    # Guidance check
    target = np.array([3.0, 0.0, 1.0])
    guidance_0, mu_0, in_passage_0 = coord.get_agent_guidance(0, positions[0], target)
    guidance_1, mu_1, in_passage_1 = coord.get_agent_guidance(1, positions[1], target)

    assert in_passage_0 is True, "Agent 0 should be marked in transit"
    assert mu_0 == 0.0, "Transiting agent must have mu = 0.0 (full right-of-way)"
    assert in_passage_1 is False, "Agent 1 should be waiting"
    assert mu_1 == 1.0, "Waiting agent must have mu = 1.0 (yielding)"
    assert guidance_1[0] < spec.center[0], "Agent 1 loitering target must be behind entrance"

    # Step 2: Agent 0 flies through and clears exit (exit is at X = 1.9, so X = 2.1 clears)
    positions[0] = np.array([2.15, 0.0, 1.0])
    coord.update_coordination(positions, velocities, current_step=10)

    assert 0 in coord.cleared_agents, "Agent 0 must be marked cleared"
    assert coord.token_holder == 1, "Token must transfer to Agent 1"

    # Step 3: Agent 1 clears exit
    positions[1] = np.array([2.20, 0.0, 1.0])
    coord.update_coordination(positions, velocities, current_step=20)

    assert 1 in coord.cleared_agents
    assert coord.token_holder == 2, "Token must transfer to Agent 2"


def test_passage_handover_byzantine_and_timeout_revocation():
    """Validates immediate revocation upon BRMC quarantine or timeout."""
    spec = PassageSpecification(
        passage_id=1,
        center=np.array([1.5, 0.0, 1.0]),
        axis=np.array([1.0, 0.0, 0.0]),
        width_m=0.60,
        height_m=1.80,
        length_m=0.80,
        standoff_dist_m=1.0,
    )
    coord = PassageHandoverCoordinator(spec, max_transit_steps=20)

    positions = [np.array([1.0, 0.0, 1.0]), np.array([0.0, 0.0, 1.0])]
    velocities = [np.zeros(3), np.zeros(3)]

    # Agent 0 acquires token
    coord.update_coordination(positions, velocities, current_step=1)
    assert coord.token_holder == 0

    # Case A: Agent 0 becomes Byzantine and is quarantined by BRMC
    quarantined = [True, False]
    coord.update_coordination(positions, velocities, quarantined_mask=quarantined, current_step=2)

    assert coord.token_holder != 0, "Token must be revoked from Byzantine agent"
    assert coord.token_holder == 1, "Token must immediately transfer to honest Agent 1"

    # Case B: Timeout revocation test with fresh coordinator
    coord2 = PassageHandoverCoordinator(spec, max_transit_steps=15)
    coord2.update_coordination(positions, velocities, current_step=1)
    assert coord2.token_holder == 0

    # Step past timeout (1 + 16 = 17 > 15) without clearing exit
    coord2.update_coordination(positions, velocities, current_step=18)
    assert coord2.token_holder == 1, "Token must be revoked upon watchdog timeout"


def test_swarm_6dof_doorway_queueing_traversal():
    """
    Validates that multiple 6-DOF quadrotors sequentially queue and pass through
    a narrow passage with zero inter-agent collisions.
    """
    cfg = Swarm6DOFConfig(num_robots=2, mass=1.2, inter_agent_margin=0.15)
    env = AegisMuJoCoSwarm6DOFEnvironment(cfg)
    env.reset()

    spec = PassageSpecification(
        passage_id=1,
        center=np.array([0.0, 1.2, 1.0]),
        axis=np.array([0.0, 1.0, 0.0]),
        width_m=0.60,
        height_m=1.80,
        length_m=0.40,
        standoff_dist_m=0.6,
    )
    coord = PassageHandoverCoordinator(spec)

    # Place robot 0 at (0, 0.6, 1) and robot 1 at (0, -0.2, 1)
    env.data.qpos[0:3] = [0.0, 0.6, 1.0]
    env.data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    env.data.qpos[7:10] = [0.0, -0.2, 1.0]
    env.data.qpos[10:14] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(env.model, env.data)

    nominal_target = np.array([0.0, 2.2, 1.0])
    min_dist_observed = float("inf")

    # Step through simulation for 80 outer steps
    for step in range(80):
        st = env.get_state()
        pos0 = st["positions"][0]
        pos1 = st["positions"][1]
        vel0 = st["velocities"][0]
        vel1 = st["velocities"][1]

        d_mutual = float(np.linalg.norm(pos0 - pos1))
        min_dist_observed = min(min_dist_observed, d_mutual)

        # Update handover coordination
        coord.update_coordination([pos0, pos1], [vel0, vel1], current_step=step)

        t0, mu0, in_p0 = coord.get_agent_guidance(0, pos0, nominal_target)
        t1, mu1, in_p1 = coord.get_agent_guidance(1, pos1, nominal_target)

        # Compute forces
        f0 = 4.0 * (t0 - pos0) - 1.5 * vel0
        f0[2] += cfg.mass * cfg.gravity
        f1 = 2.0 * (t1 - pos1) - 1.2 * vel1
        f1[2] += cfg.mass * cfg.gravity

        st, _ = env.step_outer([f0, f1], shield_with_cbf=True)

    # Collision boundary check
    collision_boundary = 2.0 * cfg.robot_collision_radius  # 2 * 0.28 = 0.56m
    assert min_dist_observed >= collision_boundary - 0.02, (
        f"Inter-agent collision observed during passage transit: {min_dist_observed:.3f}m"
    )
    # Robot 0 must have cleared the doorway
    assert 0 in coord.cleared_agents, "Robot 0 must successfully traverse the doorway"
