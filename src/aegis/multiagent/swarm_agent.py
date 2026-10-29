"""
NEXVIA AEGIS — Phase 3: Decentralized 3D Multi-Agent Swarm Safety Agent (AegisDecentralizedSwarmAgent).

Key Capabilities:
1. True Decentralization: Each robot operates autonomously with its own onboard
   sensors, local 3D-aware controller, and independent BRMC consensus instance.
2. Byzantine-Resilient Peer Fusion: Fuses peer messages over lossy wireless mesh
   while isolating colluding or DoS Byzantine peers via Trimmed Martingale Consensus.
3. Reciprocal High-Order Control Barrier Functions (HOCBF): Enforces collision-free
   forward dynamic invariance against obstacles, arena boundaries, and all peers
   (including unpredictable quarantined peers).
4. Dual Epistemic & Physical Safety Guarantees:
   - Epistemic: Zero false arrivals via multi-agent calibrated range corroboration.
   - Physical: Zero physical collisions via second-order active-set CBF projection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
import numpy as np

from aegis.env.mujoco_3d_cbf import Obstacle3D
if TYPE_CHECKING:
    from aegis.env.mujoco_swarm_3d import Swarm3DConfig, SwarmCBF3DFilter
from aegis.multiagent.brmc_engine import (
    AgentMessage,
    ByzantineResilientMartingaleConsensus,
    SwarmConsensusState,
)
from aegis.v3.sensors.cross_modal import RangeReading
from aegis.v3.sensors.sensors import SensorReading
from aegis.v7.anchor_sensor import AnchorReading
from aegis.v9.controller_3d import Aegis3DAwareController


@dataclass
class SwarmAgentTelemetry:
    agent_id: int
    step: int
    local_position: np.ndarray
    consensus_target: np.ndarray
    local_wealth: float
    consensus_wealth: float
    quarantined_peers: list[int]
    decision_type: str
    barrier_active: bool
    safe_control: np.ndarray


class AegisDecentralizedSwarmAgent:
    """
    Decentralized Autonomous Aerial Robot in a 3D Collaborative Swarm.
    """

    def __init__(
        self,
        agent_id: int,
        num_swarm_agents: int = 7,
        max_byzantine_faults: int = 2,
        alpha_swarm: float = 0.05,
        packet_drop_prob: float = 0.0,
        config: Any = None,
    ) -> None:
        from aegis.env.mujoco_swarm_3d import Swarm3DConfig, SwarmCBF3DFilter

        self.agent_id = agent_id
        self.num_swarm_agents = num_swarm_agents
        self.max_byzantine_faults = max_byzantine_faults
        self.packet_drop_prob = float(packet_drop_prob)
        self.cfg: Swarm3DConfig = config or Swarm3DConfig(num_robots=num_swarm_agents)

        # 1. Local 3D Epistemic Controller (Native 3D Ville + Calibrated Arrival)
        self.local_controller = Aegis3DAwareController(
            success_radius=self.cfg.target_arrival_radius,
            cbf_force_limit=self.cfg.control_force_limit,
            alpha_risk=alpha_swarm,
        )

        # 2. Local Byzantine-Resilient Martingale Consensus Engine
        self.local_brmc = ByzantineResilientMartingaleConsensus(
            num_agents=num_swarm_agents,
            max_byzantine_faults=max_byzantine_faults,
            alpha_swarm=alpha_swarm,
            byzantine_isolation_threshold=3.5,
        )

        # 3. Local High-Order CBF Filter for Swarms
        self.cbf_filter = SwarmCBF3DFilter(self.cfg)

        self.last_consensus_target = np.zeros(3, dtype=np.float64)
        self.last_decision = "NAVIGATE"
        self.step_count = 0

    def reset(self) -> None:
        self.local_controller.reset()
        self.local_brmc = ByzantineResilientMartingaleConsensus(
            num_agents=self.num_swarm_agents,
            max_byzantine_faults=self.max_byzantine_faults,
            alpha_swarm=self.local_brmc.alpha_swarm,
            byzantine_isolation_threshold=3.5,
        )
        self.last_consensus_target = np.zeros(3, dtype=np.float64)
        self.last_decision = "NAVIGATE"
        self.step_count = 0

    def receive_and_fuse_peer_messages(
        self,
        peer_messages: list[AgentMessage],
        step: int,
        rng: np.random.Generator | None = None,
    ) -> SwarmConsensusState:
        """
        Receives messages broadcast over the wireless network, applies packet loss,
        and executes robust trimmed supermartingale consensus.
        """
        received: list[AgentMessage] = []
        for msg in peer_messages:
            # Own message is always received reliably
            if msg.agent_id == self.agent_id:
                received.append(msg)
            else:
                if rng is not None and self.packet_drop_prob > 0.0:
                    if rng.random() < self.packet_drop_prob:
                        continue  # Packet dropped
                received.append(msg)

        consensus_state = self.local_brmc.aggregate_step(received, step=step)
        self.last_consensus_target = consensus_state.consensus_position.copy()
        return consensus_state

    def step_control(
        self,
        local_pos: np.ndarray,
        local_vel: np.ndarray,
        peer_positions: list[np.ndarray],
        peer_velocities: list[np.ndarray],
        obstacles: list[Obstacle3D],
        formation_offset: np.ndarray,
        reading_a: SensorReading | np.ndarray,
        reading_b: SensorReading | np.ndarray,
        range_reading: RangeReading | float | None,
        anchor_reading: AnchorReading | np.ndarray | None = None,
        wind_velocity: np.ndarray | None = None,
        step: int = 0,
    ) -> tuple[np.ndarray, SwarmAgentTelemetry, bool]:
        """
        Executes one full decentralized agent update cycle:
        1. Local epistemic sensor update & Ville e-process
        2. Target formation guidance around consensus target
        3. Multi-agent HOCBF safety filtering against obstacles & peers
        Returns: (safe_control_force, telemetry, query_anchor_next)
        """
        self.step_count = step

        # 1. Local 3D Epistemic Update
        u_local_des, dec_type, nav_3d, query_anchor = self.local_controller.update(
            reading_a=reading_a,
            reading_b=reading_b,
            range_reading=range_reading,
            anchor_reading=anchor_reading,
            step=step,
        )
        self.last_decision = dec_type

        # 2. Desired Formation Control Command
        # Target position for this agent: consensus target + assigned formation offset
        target_des_i = self.last_consensus_target + formation_offset
        delta_p = target_des_i - local_pos
        v_rel = local_vel - (wind_velocity if wind_velocity is not None else np.zeros(3))

        # PD trajectory control: K_p = 2.2, K_d = 2.5
        kp = 2.2
        kd = 2.5
        u_des_i = kp * delta_p - kd * v_rel

        if dec_type in ("VERIFY", "STOP", "ABSTAIN"):
            # Dissipative braking force
            speed = float(np.linalg.norm(local_vel))
            u_des_i = -1.8 * local_vel if speed > 1e-4 else np.zeros(3)

        # 3. High-Order CBF Safety Shielding
        # Construct full swarm state lists with agent i at its actual index
        all_positions = list(peer_positions)
        all_velocities = list(peer_velocities)
        all_positions[self.agent_id] = local_pos
        all_velocities[self.agent_id] = local_vel

        all_desired = [np.zeros(3) for _ in range(self.num_swarm_agents)]
        all_desired[self.agent_id] = u_des_i

        safe_controls, barriers_active = self.cbf_filter.compute_safe_swarm_controls(
            positions=all_positions,
            velocities=all_velocities,
            desired_controls=all_desired,
            obstacles=obstacles,
            quarantined_mask=[p in self.local_brmc.quarantine_registry for p in range(self.num_swarm_agents)],
        )

        safe_u_i = safe_controls[self.agent_id]
        active_barrier_i = barriers_active[self.agent_id]

        # Extract local e-process wealth
        local_wealth = 1.0
        if self.local_controller.ville_monitor is not None:
            local_wealth = float(np.exp(min(self.local_controller.ville_monitor.log_wealth_mixture, 50.0)))

        telemetry = SwarmAgentTelemetry(
            agent_id=self.agent_id,
            step=step,
            local_position=local_pos.copy(),
            consensus_target=self.last_consensus_target.copy(),
            local_wealth=local_wealth,
            consensus_wealth=1.0,
            quarantined_peers=sorted(list(self.local_brmc.quarantine_registry)),
            decision_type=dec_type,
            barrier_active=active_barrier_i,
            safe_control=safe_u_i.copy(),
        )

        return safe_u_i, telemetry, query_anchor

    def create_broadcast_message(
        self,
        local_pos: np.ndarray,
        step: int,
        sigma: float = 0.08,
    ) -> AgentMessage:
        """
        Creates an outgoing cryptographic AgentMessage to broadcast to peers.
        """
        # Local estimated target position relative to global origin
        target_est = local_pos + self.local_controller.last_nav_vector_3d
        local_wealth = 1.0
        if self.local_controller.ville_monitor is not None:
            local_wealth = float(np.exp(min(self.local_controller.ville_monitor.log_wealth_mixture, 50.0)))

        return AgentMessage(
            agent_id=self.agent_id,
            step=step,
            pos_estimate=target_est.copy(),
            sigma=float(sigma),
            martingale_wealth=local_wealth,
            valid=True,
        )
