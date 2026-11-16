"""
NEXVIA AEGIS — Multi-Agent Narrow Passage Cooperative Handover & Queueing Protocol.

Solves the Multi-Robot Aperture Deadlock Problem:
When multiple 6-DOF quadrotors must traverse a narrow doorway, slit, or corridor
where simultaneous two-way or multi-drone flight is geometrically impossible (w < 2 * r_quad):
1. Decentralized Right-of-Way Token Arbitration:
   - Grants exclusive passage right-of-way to the nearest agent.
   - Asymmetric CBF Responsibility: Active transiting agent has mu = 0.0 (full right-of-way);
     all waiting agents have mu = 1.0 (100% yielding responsibility).
2. Epistemic Holding Pattern / Loitering Orbit:
   - Waiting drones automatically loiter at staggered, collision-free standoff positions
     outside the passage entrance.
3. Byzantine Fault Isolation:
   - If an agent holding the token stalls, crashes, or is quarantined by BRMC,
     the token is autonomously revoked after a bounded watchdog horizon.
4. Smooth FIFO Handover:
   - As soon as the active drone crosses the exit threshold plane, the token transfers
     to the next agent in queue with zero deadlocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Dict, List, Optional, Set, Tuple
import numpy as np


class PassageTokenState(str, Enum):
    FREE = "FREE"
    IN_TRANSIT = "IN_TRANSIT"
    CLEARED = "CLEARED"
    REVOKED = "REVOKED"


@dataclass
class PassageSpecification:
    """Geometric definition of a narrow passage / doorway."""
    passage_id: int
    center: np.ndarray             # Center of doorway in R^3
    axis: np.ndarray               # Unit vector along passage traversal direction (+X, +Y, etc.)
    width_m: float                 # Aperture width (m)
    height_m: float                # Aperture height (m)
    length_m: float                # Corridor length (m)
    standoff_dist_m: float = 1.2   # Standoff radius for loitering orbit outside entrance


@dataclass
class QueueRequest:
    agent_id: int
    dist_to_entrance: float
    request_step: int


class PassageHandoverCoordinator:
    """
    Decentralized Priority & Queueing Coordinator for Multi-Drone Narrow Passages.
    """

    def __init__(
        self,
        passage_spec: PassageSpecification,
        max_transit_steps: int = 80,       # Max steps allowed inside passage before watchdog revokes
        robot_radius: float = 0.28,
        safety_margin: float = 0.15,
    ) -> None:
        self.spec = passage_spec
        self.max_transit_steps = max_transit_steps
        self.robot_radius = robot_radius
        self.safety_margin = safety_margin

        # Normal and entrance/exit positions
        axis = self.spec.axis / max(1e-6, float(np.linalg.norm(self.spec.axis)))
        self.axis = axis
        self.entrance_pos = self.spec.center - 0.5 * self.spec.length_m * axis
        self.exit_pos = self.spec.center + 0.5 * self.spec.length_m * axis

        # Token state
        self.token_holder: Optional[int] = None
        self.token_state: PassageTokenState = PassageTokenState.FREE
        self.transit_start_step: int = 0
        self.cleared_agents: Set[int] = set()
        self.penalized_agents: Dict[int, int] = {}  # agent_id -> penalty_until_step

        # Queue of waiting agents [QueueRequest]
        self.waiting_queue: List[QueueRequest] = []

    def update_coordination(
        self,
        agent_positions: List[np.ndarray],
        agent_velocities: List[np.ndarray],
        quarantined_mask: Optional[List[bool]] = None,
        current_step: int = 0,
    ) -> None:
        """
        Updates token state, detects entry/exit, isolates Byzantine agents,
        and advances the queue.
        """
        n = len(agent_positions)
        if quarantined_mask is None:
            quarantined_mask = [False] * n

        # 1. Check active token holder
        if self.token_holder is not None:
            holder = self.token_holder
            # Check if holder is quarantined by BRMC (Byzantine fault)
            if holder < len(quarantined_mask) and quarantined_mask[holder]:
                # Revoke token from Byzantine agent
                self.penalized_agents[holder] = current_step + 999999
                self.token_holder = None
                self.token_state = PassageTokenState.REVOKED
            # Check watchdog timeout
            elif (current_step - self.transit_start_step) > self.max_transit_steps:
                # Token timeout (stalled agent): penalty pushes to back of queue
                self.penalized_agents[holder] = current_step + 50
                self.token_holder = None
                self.token_state = PassageTokenState.REVOKED
            else:
                # Check if holder has successfully crossed the exit plane
                pos = agent_positions[holder]
                proj_exit = float(np.dot(pos - self.exit_pos, self.axis))
                if proj_exit > 0.05:  # Cleared exit
                    self.cleared_agents.add(holder)
                    self.token_holder = None
                    self.token_state = PassageTokenState.CLEARED

        # 2. Build or update queue from active agents that haven't cleared yet
        active_requests: List[QueueRequest] = []
        penalized_requests: List[QueueRequest] = []

        for i in range(n):
            if i in self.cleared_agents:
                continue
            if i < len(quarantined_mask) and quarantined_mask[i]:
                continue  # Exclude quarantined peers from queue

            pos = agent_positions[i]
            d_entrance = float(np.linalg.norm(pos - self.entrance_pos))
            req = QueueRequest(
                agent_id=i,
                dist_to_entrance=d_entrance,
                request_step=current_step,
            )
            if self.penalized_agents.get(i, 0) > current_step:
                penalized_requests.append(req)
            else:
                active_requests.append(req)

        # Sort active queue by distance to entrance (closest agent gets next priority)
        active_requests.sort(key=lambda r: r.dist_to_entrance)
        # Append penalized/timed-out agents at the tail
        self.waiting_queue = active_requests + penalized_requests

        # 3. Grant token to top of queue if passage is free
        if self.token_holder is None and len(self.waiting_queue) > 0:
            top_agent = self.waiting_queue[0].agent_id
            self.token_holder = top_agent
            self.token_state = PassageTokenState.IN_TRANSIT
            self.transit_start_step = current_step

    def get_agent_guidance(
        self,
        agent_id: int,
        current_pos: np.ndarray,
        nominal_target: np.ndarray,
    ) -> Tuple[np.ndarray, float, bool]:
        """
        Returns:
            (effective_target, responsibility_mu, is_in_passage)
        """
        # If agent already cleared the passage, proceed freely to nominal target
        if agent_id in self.cleared_agents:
            return nominal_target, 0.5, False

        # If agent holds the passage token: fly smoothly through centerline entrance -> center -> exit -> nominal target
        if agent_id == self.token_holder:
            proj_along_axis = float(np.dot(current_pos - self.spec.center, self.axis))
            half_len = 0.5 * self.spec.length_m

            if proj_along_axis < -half_len:
                # Approaching entrance: align laterally to passage axis at entrance
                eff_target = self.entrance_pos + 0.2 * self.axis
            elif proj_along_axis < half_len:
                # Inside passage: pull cleanly through past the exit plane along axis
                eff_target = self.exit_pos + 0.5 * self.axis
            else:
                # Past exit: proceed to nominal target
                eff_target = nominal_target

            # Active transiting agent takes right-of-way (mu = 0.0)
            return eff_target, 0.0, True

        # If agent is waiting in queue: loiter at collision-free standoff positions
        # Find rank in queue
        rank = 0
        for idx, req in enumerate(self.waiting_queue):
            if req.agent_id == agent_id:
                rank = idx
                break

        # Compute loitering standoff point
        # Stagger waiting drones in a fan/arc behind entrance
        standoff_d = self.spec.standoff_dist_m + rank * 0.55
        angle_spread = (rank - 1) * 0.45 if rank > 0 else 0.0

        # Orthogonal horizontal vector
        ortho = np.array([-self.axis[1], self.axis[0], 0.0], dtype=np.float64)
        norm_ortho = float(np.linalg.norm(ortho))
        if norm_ortho > 1e-4:
            ortho = ortho / norm_ortho
        else:
            ortho = np.array([0.0, 1.0, 0.0])

        loiter_pos = self.entrance_pos - standoff_d * self.axis + (0.6 * rank * math.sin(angle_spread)) * ortho
        loiter_pos[2] = self.spec.center[2] + (0.15 * (rank % 2))  # Slight vertical stagger

        # Waiting agents take 100% evasive responsibility (mu = 1.0)
        return loiter_pos, 1.0, False
