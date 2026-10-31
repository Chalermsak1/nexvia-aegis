"""
NEXVIA AEGIS — Statistical Uncertainty & Calibration Agent.

Specialist agent responsible for evaluating statistical power, Clopper-Pearson exact
confidence intervals, sample independence, and Selective Risk vs Coverage Pareto frontier.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence
from scipy.stats import beta

from src.aegis.agents.agent_contract import AgentRole, AgentSignOff, VerdictStatus


def clopper_pearson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Computes exact Clopper-Pearson binomial confidence interval."""
    if n <= 0:
        return (0.0, 1.0)
    if k <= 0:
        lower = 0.0
    else:
        lower = float(beta.ppf(alpha / 2.0, k, n - k + 1))
    if k >= n:
        upper = 1.0
    else:
        upper = float(beta.ppf(1.0 - alpha / 2.0, k + 1, n - k))
    return (round(lower, 4), round(upper, 4))


class StatisticalAuditorAgent:
    """Audits statistical validity, confidence intervals, and hypothesis metrics."""

    def __init__(self, agent_id: str = "agent-stats-calibration-02") -> None:
        self.agent_id = agent_id
        self.role = AgentRole.STATISTICAL_AUDITOR_AGENT

    def evaluate_study_evidence(
        self,
        episodes_or_summaries: Sequence[Mapping[str, Any] | Any],
        *,
        max_acceptable_false_arrival_rate: float = 0.05,
    ) -> AgentSignOff:
        """Audits statistical distributions, confidence bounds, and sample independence."""
        findings: list[str] = []
        blockers: list[str] = []
        caveats: list[str] = []

        total_runs = len(episodes_or_summaries)
        if total_runs == 0:
            return AgentSignOff(
                role=self.role,
                agent_id=self.agent_id,
                verdict=VerdictStatus.INSUFFICIENT_EVIDENCE,
                findings=["ไม่มีข้อมูลสำหรับวิเคราะห์ทางสถิติ"],
                metrics={"total_samples": 0},
                blockers=["No statistical samples available"],
            )

        seeds_seen: set[Any] = set()
        true_success_count = 0
        false_arrival_count = 0
        abstain_count = 0
        timeout_count = 0

        for item in episodes_or_summaries:
            if hasattr(item, "to_dict"):
                item_dict = item.to_dict()
            else:
                item_dict = dict(item)

            seed = item_dict.get("seed")
            if seed is not None:
                seeds_seen.add(seed)

            # Determine category
            if item_dict.get("true_success") or item_dict.get("decision_is_true_success"):
                true_success_count += 1
            elif item_dict.get("false_arrival"):
                false_arrival_count += 1
            elif item_dict.get("abstained") or item_dict.get("decision") == "ABSTAIN":
                abstain_count += 1
            elif item_dict.get("timeout") or item_dict.get("decision") == "TIMEOUT":
                timeout_count += 1
            elif item_dict.get("decision") == "STOP":
                # Fallback check
                if item_dict.get("decision_dist_to_goal", 999.0) <= 0.25:
                    true_success_count += 1
                else:
                    false_arrival_count += 1

        # Check sample size & pseudo-replication
        unique_seeds_count = len(seeds_seen)
        if unique_seeds_count < total_runs and unique_seeds_count > 0:
            caveats.append(
                f"ตรวจพบการใช้ seed ซ้ำในการประเมินสถิติ ({total_runs} ตัวอย่าง จาก {unique_seeds_count} independent seeds) "
                f"— อาจส่งผลต่อสมมติฐานความอิสระของตัวอย่าง (Pseudo-replication risk)"
            )

        if total_runs < 30:
            caveats.append(
                f"ขนาดกลุ่มตัวอย่าง (n={total_runs}) ยังอยู่ในระดับเบื้องต้น (Exploratory Prototype) "
                f"ช่วงความเชื่อมั่น Clopper-Pearson จะมีความกว้างสูง"
            )

        # Clopper-Pearson 95% CIs
        ts_rate = true_success_count / total_runs
        fa_rate = false_arrival_count / total_runs
        abs_rate = abstain_count / total_runs

        ts_ci = clopper_pearson_ci(true_success_count, total_runs)
        fa_ci = clopper_pearson_ci(false_arrival_count, total_runs)
        abs_ci = clopper_pearson_ci(abstain_count, total_runs)

        # Selective Risk among accepted missions (STOP decisions)
        accepted_count = true_success_count + false_arrival_count
        if accepted_count > 0:
            selective_risk = false_arrival_count / accepted_count
            selective_risk_ci = clopper_pearson_ci(false_arrival_count, accepted_count)
        else:
            selective_risk = 0.0
            selective_risk_ci = (0.0, 0.0)

        findings.append(
            f"การประเมินสถิติบนกลุ่มตัวอย่าง n={total_runs}: "
            f"True Arrival={true_success_count} ({ts_rate*100:.1f}%, 95% CI {ts_ci}), "
            f"False Arrival={false_arrival_count} ({fa_rate*100:.1f}%, 95% CI {fa_ci}), "
            f"Abstention={abstain_count} ({abs_rate*100:.1f}%, 95% CI {abs_ci})"
        )

        findings.append(
            f"Selective Risk (ความเสี่ยงเมื่อตัดสินใจยอมรับภารกิจ): "
            f"{false_arrival_count}/{accepted_count} ({selective_risk*100:.1f}%, 95% CI {selective_risk_ci})"
        )

        if fa_rate > max_acceptable_false_arrival_rate:
            blockers.append(
                f"อัตราการตัดสินใจถึงเป้าหมายผิดพลาด (False Arrival Rate = {fa_rate*100:.1f}%) "
                f"สูงเกินเกณฑ์ความปลอดภัยที่กำหนด ({max_acceptable_false_arrival_rate*100:.1f}%)"
            )

        if blockers:
            verdict = VerdictStatus.REJECTED
        elif caveats:
            verdict = VerdictStatus.APPROVED_WITH_CAVEATS
        else:
            verdict = VerdictStatus.APPROVED

        metrics = {
            "total_samples": total_runs,
            "unique_seeds": unique_seeds_count,
            "true_success_count": true_success_count,
            "true_success_rate": round(ts_rate, 4),
            "true_success_95_ci": list(ts_ci),
            "false_arrival_count": false_arrival_count,
            "false_arrival_rate": round(fa_rate, 4),
            "false_arrival_95_ci": list(fa_ci),
            "abstain_count": abstain_count,
            "abstain_rate": round(abs_rate, 4),
            "abstain_95_ci": list(abs_ci),
            "timeout_count": timeout_count,
            "accepted_count": accepted_count,
            "selective_risk": round(selective_risk, 4),
            "selective_risk_95_ci": list(selective_risk_ci),
        }

        return AgentSignOff(
            role=self.role,
            agent_id=self.agent_id,
            verdict=verdict,
            findings=findings,
            metrics=metrics,
            blockers=blockers,
            caveats=caveats,
        )
