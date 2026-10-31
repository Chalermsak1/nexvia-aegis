#!/usr/bin/env python3
"""
NEXVIA AEGIS — Multi-Agent Research Team Diagnostic Study Runner.

Executes an exploratory diagnostic study on fresh development worlds (seeds 2256000, 2256001)
with durable IncrementalPhysicsLedger, followed by an autonomous multi-agent audit
conducted by the 4 specialist research agents under strict GATE_B_NOT_AUTHORIZED boundary.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import mujoco
from aegis.env.mujoco_3d_cbf import AegisMuJoCo3DEnvironment
from experiments.benchmark_physical_3d_cbf import run_3d_episode
from src.aegis.agents import (
    AgentRole,
    ForensicEvidenceAgent,
    PhysicalControlAgent,
    ResearchTeamCoordinator,
    StatisticalAuditorAgent,
)
from src.aegis.evidence import (
    IncrementalPhysicsLedger,
    STAGE_MAIN_TRANSIT,
    STAGE_POST_ABSTAIN_COAST,
    STAGE_POST_STOP_DWELL,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[2256000, 2256001], help="Fresh development seeds")
    parser.add_argument("--max-steps", type=int, default=150, help="Per-episode step limit")
    parser.add_argument("--post-stop-steps", type=int, default=30, help="Dwell observation window")
    parser.add_argument("--output-ledger", type=Path, default=ROOT / "results/research_development/dev/agent_team_pilot_study_v1.jsonl")
    parser.add_argument("--output-report", type=Path, default=ROOT / "docs/research/AGENT_TEAM_AUDIT_REPORT_2026-10-31.md")
    parser.add_argument("--output-dossier-json", type=Path, default=ROOT / "results/research_development/dev/agent_team_dossier_2026-10-31.json")
    args = parser.parse_args()

    # Pre-flight Governance Verification
    print("=" * 80)
    print("NEXVIA AEGIS — MULTI-AGENT RESEARCH TEAM DIAGNOSTIC STUDY")
    print("Protocol Authority: GATE_B_NOT_AUTHORIZED (Strict Holdout Quarantine)")
    print("=" * 80)

    # 1. Prepare Factorial Diagnostic Matrix on Fresh Dev Worlds
    cases = [
        {"name": "nominal", "range_bias_m": 0.0, "range_dropout_probability": 0.0},
        {"name": "biased_range", "range_bias_m": -0.08, "range_dropout_probability": 0.0},
    ]
    biases = [[0.0, 0.0, 0.0], [0.8, 0.8, -0.3]]
    controllers = ["AEGIS_3D_ANCHOR_RECOVERY", "AEGIS_3D_RECOVERY_MONITOR"]

    assignments = []
    for c in cases:
        for s in args.seeds:
            for b in biases:
                for ctrl in controllers:
                    aid = f"{c['name']}:{s}:{b[0]}:{ctrl}"
                    assignments.append({
                        "id": aid,
                        "case": c,
                        "seed": s,
                        "bias_xyz": b,
                        "controller": ctrl,
                        "max_steps": args.max_steps,
                        "post_stop_steps": args.post_stop_steps,
                    })

    print(f"[*] Prepared {len(assignments)} diagnostic assignments across seeds {args.seeds}")
    args.output_ledger.parent.mkdir(parents=True, exist_ok=True)
    if args.output_ledger.exists():
        args.output_ledger.unlink()

    # 2. Execute with IncrementalPhysicsLedger
    env = AegisMuJoCo3DEnvironment()
    episode_results = []

    with IncrementalPhysicsLedger.create(
        args.output_ledger,
        study="V9-M5 Agent Team Exploratory Diagnostic Study",
        assignments=assignments,
        success_radius=env.config.success_radius,
        rest_speed_threshold=0.05,
    ) as phys_ledger:

        for i, a in enumerate(assignments, 1):
            aid = a["id"]
            print(f"[{i:02d}/{len(assignments):02d}] Running assignment: {aid} ...", end=" ", flush=True)
            phys_ledger.start_assignment(aid)

            def step_tracer(trace_event: dict):
                # Records pre-physics decision moment to incremental ledger
                phys_ledger.record_step(
                    assignment_id=aid,
                    stage=STAGE_MAIN_TRANSIT,
                    decision_step=trace_event.get("step", 0),
                    true_pos=trace_event.get("position", [0, 0, 0]),
                    true_vel=trace_event.get("velocity", [0, 0, 0]),
                    dist_to_goal=trace_event.get("true_distance", 999.0),
                    decision=trace_event.get("effective_decision", "NAVIGATE"),
                    applied_force=trace_event.get("action", [0, 0, 0]),
                    sensor_fault_active=trace_event.get("vector_fault_injected", False),
                )

            trace_buffer: list[dict] = []
            try:
                res = run_3d_episode(
                    env=env,
                    controller_type=a["controller"],
                    seed=a["seed"],
                    sensor_bias=np.asarray(a["bias_xyz"]),
                    max_steps=a["max_steps"],
                    range_bias_m=a["case"]["range_bias_m"],
                    range_dropout_probability=a["case"]["range_dropout_probability"],
                    post_stop_steps=a["post_stop_steps"],
                    trace=trace_buffer,
                    on_trace=step_tracer,
                )

                # Record post-stop dwell steps if observed
                post_stop_data = res.get("post_stop")
                if isinstance(post_stop_data, dict) and post_stop_data.get("steps"):
                    for step_idx, p_step in enumerate(post_stop_data["steps"], 1):
                        phys_ledger.record_step(
                            assignment_id=aid,
                            stage=STAGE_POST_STOP_DWELL,
                            decision_step=res.get("steps", 0),
                            true_pos=env.get_state()["robot_position"],
                            true_vel=env.get_state()["robot_velocity"],
                            dist_to_goal=p_step.get("distance", 999.0),
                            decision="STOP",
                            applied_force=[0.0, 0.0, 9.81],
                            collision=p_step.get("collision", False),
                        )

                # Determine terminal decision
                if res.get("true_success") or res.get("false_arrival"):
                    dec = "STOP"
                    reason = "GOAL_CONFIRMED"
                elif res.get("abstained"):
                    dec = "ABSTAIN"
                    reason = "RECOVERY_LIMIT_OR_UNCERTAINTY"
                else:
                    dec = "TIMEOUT"
                    reason = "BUDGET_EXHAUSTED"

                summary = phys_ledger.complete_assignment(
                    aid,
                    status="COMPLETED",
                    final_decision=dec,
                    terminal_reason=reason,
                    seed=a["seed"],
                    extra_details={"episode": res},
                )
                episode_results.append(summary)
                print(f"DONE -> Decision={dec}, TrueSuccess={res.get('true_success')}, FalseArrival={res.get('false_arrival')}, Abstained={res.get('abstained')}")

            except Exception as exc:
                import traceback
                print(f"FAILED -> {exc}")
                traceback.print_exc()
                phys_ledger.complete_assignment(
                    aid,
                    status="ERROR",
                    final_decision="ERROR",
                    terminal_reason=str(exc),
                )

        phys_ledger.finalize()

    print("[*] Completed all assignments. Ledger safely closed and finalized.")

    # 3. Convene Multi-Agent Research Team Audit
    print("\n" + "=" * 80)
    print("CONVENING AEGIS AI RESEARCH AGENT TEAM")
    print("=" * 80)

    coordinator = ResearchTeamCoordinator()
    dossier = coordinator.audit_study(
        study_id="STUDY-V9M5-AGENT-TEAM-2026-10-31",
        ledger_path=args.output_ledger,
        episodes_or_summaries=episode_results,
        title_th="รายงานผลการทดลองเชิงวินิจฉัยและตรวจสอบความปลอดภัยทางฟิสิกส์โดยทีมเอเจนต์ AEGIS",
        title_en="NEXVIA AEGIS Multi-Agent Exploratory Diagnostic Research Report",
    )

    # 4. Save Dossier JSON and Markdown Report
    args.output_dossier_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_dossier_json, "w", encoding="utf-8") as f:
        json.dump(dossier.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"[*] Saved Team Dossier JSON to: {args.output_dossier_json}")

    report_md = coordinator.generate_markdown_report(dossier)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report_md, encoding="utf-8")
    print(f"[*] Saved Comprehensive Audit Report to: {args.output_report}")

    print("\n" + "=" * 80)
    print("TEAM CONSENSUS VERDICT:", dossier.consensus.value)
    print("=" * 80)
    for role, so in dossier.agent_signoffs.items():
        print(f" - [{role}] {so.agent_id}: {so.verdict.value} (SHA-256: {so.signature_sha256[:16]}...)")
    print("=" * 80)


if __name__ == "__main__":
    main()
