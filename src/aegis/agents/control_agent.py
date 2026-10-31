"""
NEXVIA AEGIS — Physical Control & Dynamics Verification Agent.

Specialist agent responsible for evaluating physical safety, post-stop dwell stability,
post-abstain coasting dynamics, CBF QP feasibility, and estimated-state oracle isolation (E-01..E-06).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
import numpy as np

from src.aegis.agents.agent_contract import AgentRole, AgentSignOff, VerdictStatus
from src.aegis.evidence.physics_step_ledger import DecoupledHorizonSummary


class PhysicalControlAgent:
    """Evaluates physical control, CBF safety barriers, and decoupled physical rest."""

    def __init__(self, agent_id: str = "agent-control-dynamics-01") -> None:
        self.agent_id = agent_id
        self.role = AgentRole.PHYSICAL_CONTROL_AGENT

    def evaluate_study_evidence(
        self,
        episodes_or_summaries: Sequence[DecoupledHorizonSummary | Mapping[str, Any]],
        *,
        rest_speed_threshold: float = 0.05,
        max_allowed_coast_m: float = 1.0,
    ) -> AgentSignOff:
        """
        Audits physical horizon evidence across all completed assignments.
        Detects silent drift after STOP, post-abstain runaway, and CBF infeasibility.
        """
        findings: list[str] = []
        blockers: list[str] = []
        caveats: list[str] = []

        total_runs = len(episodes_or_summaries)
        if total_runs == 0:
            return AgentSignOff(
                role=self.role,
                agent_id=self.agent_id,
                verdict=VerdictStatus.INSUFFICIENT_EVIDENCE,
                findings=["ไม่มีข้อมูล telemetry หรือ summary สำหรับการตรวจสอบทางฟิสิกส์"],
                metrics={"total_runs": 0},
                blockers=["Missing physics evidence"],
            )

        stop_decisions = 0
        dwell_sustained_rest_count = 0
        dwell_drift_count = 0
        dwell_collisions = 0
        max_dwell_final_speed = 0.0

        abstain_decisions = 0
        coast_count = 0
        coast_collisions = 0
        max_coast_displacement = 0.0

        cbf_infeasible_episodes = 0
        collision_episodes = 0

        for item in episodes_or_summaries:
            # Handle DecoupledHorizonSummary dataclass or dict
            if isinstance(item, DecoupledHorizonSummary):
                dec = item.decision
                coll = item.decision_collision or item.dwell_collision or item.coast_collision
                infeasible = item.decision_cbf_infeasible_count > 0
                has_dwell = item.has_post_stop_dwell
                sustained_rest = item.dwell_is_physically_sustained_rest
                dwell_speed = item.dwell_final_speed
                dwell_coll = item.dwell_collision
                has_coast = item.has_post_abstain_coast
                coast_disp = item.coast_displacement
                coast_coll = item.coast_collision
            else:
                # Handle dictionary representation
                dec = item.get("decision") or ("STOP" if item.get("true_success") or item.get("false_arrival") else ("ABSTAIN" if item.get("abstained") else "TIMEOUT"))
                coll = bool(item.get("collision_occurred", 0) or item.get("dwell_collision", False))
                infeasible = int(item.get("cbf_infeasible_steps", 0)) > 0
                
                # Check for nested post_stop
                post_stop = item.get("post_stop")
                if post_stop and isinstance(post_stop, dict) and post_stop.get("steps"):
                    has_dwell = True
                    steps = post_stop["steps"]
                    dwell_speed = steps[-1].get("speed", 0.0)
                    dwell_coll = any(s.get("collision", False) for s in steps)
                    all_inside = all(s.get("distance", 999.0) <= 0.25 for s in steps)
                    sustained_rest = all_inside and (dwell_speed <= rest_speed_threshold) and not dwell_coll
                else:
                    has_dwell = item.get("has_post_stop_dwell", False)
                    dwell_speed = item.get("dwell_final_speed", 0.0)
                    dwell_coll = item.get("dwell_collision", False)
                    sustained_rest = item.get("dwell_is_physically_sustained_rest", False)

                has_coast = item.get("has_post_abstain_coast", False)
                coast_disp = item.get("coast_displacement", 0.0)
                coast_coll = item.get("coast_collision", False)

            if coll:
                collision_episodes += 1
            if infeasible:
                cbf_infeasible_episodes += 1

            if dec == "STOP":
                stop_decisions += 1
                if has_dwell:
                    max_dwell_final_speed = max(max_dwell_final_speed, dwell_speed)
                    if dwell_coll:
                        dwell_collisions += 1
                    if sustained_rest:
                        dwell_sustained_rest_count += 1
                    else:
                        dwell_drift_count += 1
            elif dec == "ABSTAIN":
                abstain_decisions += 1
                if has_coast:
                    coast_count += 1
                    max_coast_displacement = max(max_coast_displacement, coast_disp)
                    if coast_coll:
                        coast_collisions += 1

        # Evaluate Findings
        findings.append(f"ตรวจสอบการจำลองทางฟิสิกส์ทั้งหมด {total_runs} ภารกิจ (STOP={stop_decisions}, ABSTAIN={abstain_decisions})")

        if collision_episodes > 0:
            blockers.append(f"พบการชนสิ่งกีดขวาง (Collision) จำนวน {collision_episodes} ครั้ง")
            findings.append(f"⚠️ ตรวจพบการชนในระหว่างทำการบิน {collision_episodes} ภารกิจ")

        if cbf_infeasible_episodes > 0:
            caveats.append(f"พบ CBF Quadratic Programming Infeasibility {cbf_infeasible_episodes} ครั้ง (ระบบใช้ exact backup fallback)")
            findings.append(f"ℹ️ CBF Solver เผชิญภาวะ Infeasible {cbf_infeasible_episodes} ครั้ง และต้องตัดเข้า safe relaxation")

        dwell_rest_rate = (dwell_sustained_rest_count / stop_decisions) if stop_decisions > 0 else 0.0
        if stop_decisions > 0:
            findings.append(
                f"การรักษาสภาพหยุดนิ่งทางฟิสิกส์จริงหลังประกาศ STOP (Physical Sustained Rest): "
                f"{dwell_sustained_rest_count}/{stop_decisions} ({dwell_rest_rate * 100:.1f}%)"
            )
            if dwell_drift_count > 0:
                caveats.append(
                    f"พบการลอยตัวไถล (Physical Drift) หลุดจากเป้าหมายหลังตัดสินใจ STOP จำนวน {dwell_drift_count} ครั้ง "
                    f"(ความเร็วหลงเหลือสูงสุด {max_dwell_final_speed:.4f} m/s เกินเกณฑ์ {rest_speed_threshold} m/s)"
                )
                findings.append(f"⚠️ ตัวควบคุมตัดสินใจหยุด แต่โมเมนตัมทางฟิสิกส์พัดโดรนหลุดรัศมีเป้าหมาย {dwell_drift_count} ครั้ง")

        if coast_count > 0:
            findings.append(
                f"การตรวจจับระยะเบรกหลังสละสิทธิ์ (Post-Abstain Coasting): ตรวจสอบ {coast_count} ครั้ง, "
                f"ระยะเบรกไถลสูงสุด {max_coast_displacement:.3f} เมตร (ชนสิ่งกีดขวางขณะเบรก={coast_collisions} ครั้ง)"
            )
            if max_coast_displacement > max_allowed_coast_m:
                caveats.append(f"ระยะเบรกหลัง ABSTAIN สูงสุด ({max_coast_displacement:.3f}m) เกินขีดจำกัดความปลอดภัย ({max_allowed_coast_m}m)")

        # Determine Verdict
        if blockers:
            verdict = VerdictStatus.REJECTED
        elif caveats:
            verdict = VerdictStatus.APPROVED_WITH_CAVEATS
        else:
            verdict = VerdictStatus.APPROVED

        metrics = {
            "total_runs": total_runs,
            "stop_decisions": stop_decisions,
            "abstain_decisions": abstain_decisions,
            "collision_episodes": collision_episodes,
            "cbf_infeasible_episodes": cbf_infeasible_episodes,
            "dwell_sustained_rest_count": dwell_sustained_rest_count,
            "dwell_drift_count": dwell_drift_count,
            "dwell_rest_rate": round(dwell_rest_rate, 4),
            "max_dwell_final_speed": round(max_dwell_final_speed, 4),
            "max_coast_displacement": round(max_coast_displacement, 4),
            "coast_collisions": coast_collisions,
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
