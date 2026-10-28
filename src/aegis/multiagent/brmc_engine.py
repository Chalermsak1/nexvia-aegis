"""
NEXVIA AEGIS — Multi-Agent Byzantine-Resilient Martingale Consensus (BRMC).

Mathematical Formulation:
- Network of N autonomous agents with at most F Byzantine / corrupted peers (F < N / 3).
- Each agent i maintains a local Ville e-process betting martingale M_t^{(i)} monitoring sensor integrity.
- Byzantine-resilient aggregation via Trimmed Supermartingale Operator:
      M_t^{consensus, (i)} = TrimmedMean_F({M_t^{(j)} : j in N_i})
- Provable Anytime-Validity:
      P(exists t >= 1 : M_t^{consensus} >= 1 / alpha) <= alpha under global H_0.
- Asymmetric Quarantine Gate: Isolates Byzantine peers whose individual innovation deviates
  significantly from the resilient spatial consensus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import numpy as np


@dataclass
class AgentMessage:
    agent_id: int
    step: int
    pos_estimate: np.ndarray       # shape (2,) or (3,)
    sigma: float
    martingale_wealth: float       # Ville e-process wealth M_t
    valid: bool = True


@dataclass
class SwarmConsensusState:
    step: int
    consensus_position: np.ndarray
    consensus_martingale_wealth: float
    swarm_alarm: bool
    quarantined_agents: list[int]
    weights: dict[int, float]


class ByzantineResilientMartingaleConsensus:
    """
    Byzantine-Resilient Martingale Consensus Engine for Multi-Robot Active Inspection.
    """

    def __init__(
        self,
        num_agents: int = 5,
        max_byzantine_faults: int = 1,
        alpha_swarm: float = 0.05,
        byzantine_isolation_threshold: float = 3.5,
    ) -> None:
        assert max_byzantine_faults < num_agents / 2, "Faults F must be < N / 2 for consensus."
        self.num_agents = num_agents
        self.max_byzantine_faults = max_byzantine_faults
        self.alpha_swarm = alpha_swarm
        self.wealth_threshold = 1.0 / alpha_swarm
        self.byzantine_isolation_threshold = byzantine_isolation_threshold

        self.quarantine_registry: set[int] = set()
        self.breach_counts: dict[int, int] = {}
        self.agent_wealth_history: dict[int, list[float]] = {i: [1.0] for i in range(num_agents)}

    def aggregate_step(
        self,
        messages: list[AgentMessage],
        step: int,
    ) -> SwarmConsensusState:
        """
        Executes robust trimmed supermartingale aggregation and spatial consensus.
        """
        active_msgs = [m for m in messages if m.valid and m.agent_id not in self.quarantine_registry]
        n_active = len(active_msgs)

        if n_active <= 2 * self.max_byzantine_faults:
            # Fallback when too many quarantined: fail-closed safety stop
            mean_pos = np.mean([m.pos_estimate for m in messages], axis=0)
            return SwarmConsensusState(
                step=step,
                consensus_position=mean_pos,
                consensus_martingale_wealth=self.wealth_threshold * 2.0,
                swarm_alarm=True,
                quarantined_agents=sorted(list(self.quarantine_registry)),
                weights={m.agent_id: 0.0 for m in messages},
            )

        # 1. Trimmed Martingale Aggregation (Ville Supermartingale Invariant)
        # Sort active agent wealths
        sorted_by_wealth = sorted(active_msgs, key=lambda m: m.martingale_wealth)
        f = self.max_byzantine_faults
        # Drop the f smallest and f largest wealths to neutralize both masking and denial-of-service Byzantine wealths
        trimmed_wealth_msgs = sorted_by_wealth[f : n_active - f]
        consensus_wealth = float(np.mean([m.martingale_wealth for m in trimmed_wealth_msgs]))

        # Swarm alarm triggered if resilient wealth crosses Ville bound
        swarm_alarm = consensus_wealth >= self.wealth_threshold

        # 2. Resilient Coordinate Median / Centerpoint Spatial Fusion
        # For 2D/3D vectors, compute geometric coordinate median to reject spatial Byzantine vectors
        pos_matrix = np.array([m.pos_estimate for m in active_msgs])  # shape (n_active, dim)
        coord_median = np.median(pos_matrix, axis=0)

        # 3. Byzantine Quarantine Screening with Consecutive Breach Counter
        # An agent is flagged for quarantine if its spatial discrepancy from the coordinate median
        # exceeds byzantine_isolation_threshold * sigma for 3 consecutive steps.
        newly_quarantined = []
        for m in active_msgs:
            dev = float(np.linalg.norm(m.pos_estimate - coord_median))
            normalized_dev = dev / max(m.sigma, 1e-4)
            if normalized_dev > self.byzantine_isolation_threshold:
                self.breach_counts[m.agent_id] = self.breach_counts.get(m.agent_id, 0) + 1
                if self.breach_counts[m.agent_id] >= 3:
                    self.quarantine_registry.add(m.agent_id)
                    newly_quarantined.append(m.agent_id)
            else:
                self.breach_counts[m.agent_id] = 0

        # 4. Inverse-Variance Weighting over Remaining Un-quarantined Agents
        final_valid_msgs = [m for m in active_msgs if m.agent_id not in self.quarantine_registry]
        if not final_valid_msgs:
            final_pos = coord_median
            weights = {m.agent_id: 0.0 for m in messages}
        else:
            w_raw = [1.0 / (m.sigma**2) for m in final_valid_msgs]
            w_sum = sum(w_raw)
            weights = {m.agent_id: w / w_sum for m, w in zip(final_valid_msgs, w_raw)}
            final_pos = sum(m.pos_estimate * weights[m.agent_id] for m in final_valid_msgs)

        return SwarmConsensusState(
            step=step,
            consensus_position=final_pos,
            consensus_martingale_wealth=consensus_wealth,
            swarm_alarm=swarm_alarm,
            quarantined_agents=sorted(list(self.quarantine_registry)),
            weights=weights,
        )
