"""
NEXVIA AEGIS — Unit Tests for Multi-Agent 6-DOF Quadrotor Swarm Physics & BRMC.

Verifies:
1. Multi-Robot 6-DOF Hover Equilibrium: All 5 quadrotors balance gravity concurrently.
2. Head-On Mutual Collision Avoidance: Reciprocal HOCBF prevents collision between two 6-DOF drones.
3. Tilt Angle Constraints: Saturated at <= 35 deg under aggressive formation maneuvers.
4. Byzantine Resilience (BRMC) on 6-DOF Dynamics: Isolates F=2 colluding adversarial drones.
"""

import math
import mujoco
import numpy as np
import pytest

from aegis.multiagent.brmc_engine import (
    AgentMessage,
    ByzantineResilientMartingaleConsensus,
)
from aegis.multiagent.swarm_6dof import (
    AegisMuJoCoSwarm6DOFEnvironment,
    ReciprocalUnderactuatedCBF6DOF,
    Swarm6DOFConfig,
)


def test_swarm_6dof_hover_equilibrium():
    """
    Verifies that all 5 quadrotors in the swarm maintain stable hover equilibrium concurrently.
    """
    cfg = Swarm6DOFConfig(num_robots=5, mass=1.2)
    env = AegisMuJoCoSwarm6DOFEnvironment(cfg)
    st = env.reset()

    hover_f = np.array([0.0, 0.0, cfg.mass * cfg.gravity])
    hover_commands = [hover_f.copy() for _ in range(cfg.num_robots)]

    # Step for 1.0 second (50 outer steps)
    for _ in range(50):
        st, _ = env.step_outer(hover_commands, shield_with_cbf=False)

    # Check that all 5 drones remain airborne near their initial altitude with near-zero vz
    for i in range(cfg.num_robots):
        pos = st["positions"][i]
        vel = st["velocities"][i]
        assert abs(vel[2]) < 0.15, f"Robot {i} vertical velocity drift: {vel[2]}"
        assert pos[2] > 0.35, f"Robot {i} altitude too low: {pos[2]}"


def test_swarm_6dof_reciprocal_inter_agent_avoidance():
    """
    Head-on collision stress test:
    Two 6-DOF quadrotors start facing each other and are commanded to fly straight into each other.
    - Unshielded: They collide physically!
    - Reciprocal HOCBF: Both drones bank/tilt away, keeping mutual distance >= 2 * r_quad!
    """
    cfg = Swarm6DOFConfig(num_robots=2, mass=1.2, inter_agent_margin=0.18)
    env = AegisMuJoCoSwarm6DOFEnvironment(cfg)
    env.reset()

    # Place robot 0 at (-1.0, 0.0, 1.0) and robot 1 at (1.0, 0.0, 1.0)
    env.data.qpos[0:3] = [-1.0, 0.0, 1.0]
    env.data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    env.data.qpos[7:10] = [1.0, 0.0, 1.0]
    env.data.qpos[10:14] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(env.model, env.data)

    min_dist_observed = 999.0
    cbf_engaged_count = 0

    for step in range(50):
        st = env.get_state()
        pos0 = st["positions"][0]
        pos1 = st["positions"][1]
        vel0 = st["velocities"][0]
        vel1 = st["velocities"][1]

        d_mutual = float(np.linalg.norm(pos0 - pos1))
        min_dist_observed = min(min_dist_observed, d_mutual)

        # Robot 0 commands forward force towards +X, Robot 1 commands forward force towards -X
        f0 = np.array([2.5, 0.0, cfg.mass * cfg.gravity]) - 0.8 * vel0
        f1 = np.array([-2.5, 0.0, cfg.mass * cfg.gravity]) - 0.8 * vel1

        st, actives = env.step_outer([f0, f1], shield_with_cbf=True)
        if any(actives):
            cbf_engaged_count += 1

    # Both robots must not have collided (distance must remain >= 2 * r_quad)
    collision_boundary = 2.0 * cfg.robot_collision_radius  # 2 * 0.28 = 0.56m
    assert min_dist_observed >= collision_boundary - 0.02, (
        f"Inter-agent collision occurred! Min dist: {min_dist_observed:.3f}m < {collision_boundary:.3f}m"
    )
    assert cbf_engaged_count > 0, "Reciprocal HOCBF should have engaged to avert head-on collision"


def test_swarm_6dof_byzantine_isolation_brmc():
    """
    Verifies that BRMC isolates F=2 Byzantine / spoofed drones while flying in 6-DOF physics.
    """
    cfg = Swarm6DOFConfig(num_robots=5, mass=1.2)
    env = AegisMuJoCoSwarm6DOFEnvironment(cfg)
    st = env.reset()

    brmc = ByzantineResilientMartingaleConsensus(
        num_agents=5,
        max_byzantine_faults=2,
        alpha_swarm=0.05,
    )

    # Agent 3 and 4 are Byzantine spoofers broadcasting false positions (+3.0m offset)
    quarantined_agents = set()
    for step in range(40):
        positions = st["positions"]
        msgs = []
        for i in range(5):
            if i in (3, 4):
                # Byzantine attack: deceptive target offset
                target_est = env.target_pos + np.array([2.5, -2.5, 0.5])
                wealth = 25.0 + step * 2.0  # high betting error
            else:
                target_est = env.target_pos + np.random.normal(0, 0.03, 3)
                wealth = 1.0

            msgs.append(AgentMessage(
                agent_id=i,
                step=step,
                pos_estimate=target_est,
                sigma=0.05,
                martingale_wealth=wealth,
                valid=True,
            ))

        consensus_st = brmc.aggregate_step(msgs, step)
        quarantined_agents.update(consensus_st.quarantined_agents)

        # Outer formation guidance toward target
        forces = []
        for i in range(5):
            delta = env.target_pos - positions[i]
            f = 1.5 * delta - 1.0 * st["velocities"][i]
            f[2] += cfg.mass * cfg.gravity
            forces.append(f)

        mask = [i in quarantined_agents for i in range(5)]
        st, _ = env.step_outer(forces, shield_with_cbf=True, quarantined_mask=mask)

    # Both Byzantine agents 3 and 4 must be quarantined by BRMC
    assert 3 in quarantined_agents, "Byzantine agent 3 must be quarantined"
    assert 4 in quarantined_agents, "Byzantine agent 4 must be quarantined"
    # Honest agents (0, 1, 2) must NOT be falsely quarantined
    assert 0 not in quarantined_agents
    assert 1 not in quarantined_agents
    assert 2 not in quarantined_agents
    # Zero inter-agent collisions
    assert st["inter_agent_collisions"] == 0, "No inter-agent collisions in 6-DOF swarm"


def test_swarm_6dof_wind_turbulence_robustness():
    """
    Verifies that under continuous stochastic Ornstein-Uhlenbeck wind gusts,
    the 6-DOF swarm controllers maintain attitude stability and zero floor/obstacle crashes.
    """
    cfg = Swarm6DOFConfig(num_robots=5, mass=1.2, wind_enabled=True, wind_sigma=0.25)
    env = AegisMuJoCoSwarm6DOFEnvironment(cfg)
    rng = np.random.default_rng(42)
    st = env.reset(rng)

    hover_f = np.array([0.0, 0.0, cfg.mass * cfg.gravity])
    hover_cmds = [hover_f.copy() for _ in range(5)]

    for _ in range(60):
        st, _ = env.step_outer(hover_cmds, shield_with_cbf=True, rng=rng)

    # Check stability under wind gusts
    assert st["inter_agent_collisions"] == 0, "No collisions despite turbulent wind"
    assert not any(st["obstacle_collisions"]), "No ground or obstacle collisions under wind"
    # Check that wind velocity dynamically fluctuated
    assert np.linalg.norm(st["wind"]) > 0.05


def test_swarm_6dof_formation_flight_and_tilt():
    """
    Verifies that when flying in formation across the arena, all 5 quadrotors:
    1. Physically tilt on SO(3) (> 5 deg) to achieve horizontal flight.
    2. Respect the maximum allowable tilt limit (<= 35 deg).
    3. Maintain mutual separation without inter-agent collisions.
    """
    cfg = Swarm6DOFConfig(num_robots=5, mass=1.2)
    env = AegisMuJoCoSwarm6DOFEnvironment(cfg)
    st = env.reset()

    # Define formation offsets relative to target: V-formation
    offsets = [
        np.array([0.0, 0.0, 0.0]),
        np.array([-0.6, -0.6, 0.1]),
        np.array([0.6, -0.6, -0.1]),
        np.array([-1.2, -1.2, 0.2]),
        np.array([1.2, -1.2, -0.2]),
    ]

    all_tilts = []
    min_inter_dist = 999.0

    for step in range(50):
        positions = st["positions"]
        velocities = st["velocities"]

        # Track pairwise distance
        for i in range(5):
            for j in range(i + 1, 5):
                d = float(np.linalg.norm(positions[i] - positions[j]))
                min_inter_dist = min(min_inter_dist, d)

        forces = []
        for i in range(5):
            goal_i = env.target_pos + offsets[i]
            delta = goal_i - positions[i]
            f = 1.8 * delta - 1.2 * velocities[i]
            f[2] += cfg.mass * cfg.gravity
            forces.append(f)

        st, _ = env.step_outer(forces, shield_with_cbf=True)
        all_tilts.extend(st["tilts_deg"])

    # Physical tilt must be observed for lateral translation
    assert max(all_tilts) > 5.0, f"Expected physical roll/pitch tilt, got max {max(all_tilts):.1f} deg"
    # Must not violate maximum tilt saturation bound (35 deg + small margin for numerical integration)
    assert max(all_tilts) <= cfg.max_tilt_angle_deg + 1.0, f"Tilt exceeded safety limit: {max(all_tilts):.1f} deg"
    # Inter-agent separation preserved
    assert st["inter_agent_collisions"] == 0
    assert min_inter_dist >= (2.0 * cfg.robot_collision_radius - 0.02)

