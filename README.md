# NEXVIA AEGIS

**A research prototype for evidence-aware decisions in uncertain physical environments.**

NEXVIA AEGIS combines sensor checks, uncertainty monitoring, active verification, and control constraints to study when an autonomous agent should act, stop, or abstain. The repository contains simulated environments, controller implementations, benchmarks, and research records.

> **สรุปภาษาไทย:** โครงการนี้ศึกษาการตัดสินใจของระบบอัตโนมัติเมื่อข้อมูลเซนเซอร์อาจผิดพลาด มีงานจำลองตั้งแต่ระบบ 2 มิติไปจนถึงหุ่นยนต์ 3 มิติและระบบหลายตัว ผลที่แสดงในโครงการเป็นหลักฐานจากการทดลองตามขอบเขตที่ระบุในแต่ละรายงาน ยังไม่ใช่การยืนยันความปลอดภัยบนหุ่นยนต์จริง

## Research status

**Research prototype · simulation-focused · not a safety-certified deployment.**

- The repository includes V9 calibration and validation work, a published V9-M4 Holdout report, and subsequent 3D, swarm, vehicle, and software-in-the-loop experiments.
- The [V9-M4 source audit](docs/reports/v9_m4_release_remediation/V9_M4_POSTEXECUTION_SOURCE_AUDIT_2026-10-29.md) records discrepancies between the published certification claim and some authorization, protocol, and execution evidence at the audited snapshot. Later code changes require independent reconciliation before relying on a confirmatory claim. See also the [published Holdout report](V9_M4_GATE_B_CONFIRMATORY_REPORT.md).
- The [V9-M5 development status](docs/reports/v9_m5/V9_M5_DEVELOPMENT_CURRENT_STATUS_2026-10-29.md) describes an earlier 3D development snapshot and its safety-versus-coverage tradeoff. Later work adds a [3D-aware controller](src/aegis/v9/controller_3d.py); see the [Phase 2 report](docs/reports/v9_m5/V9_PHASE2_CONTINUOUS_3D_PHYSICAL_AI_REPORT.md) for its reported simulation results.
- The repository includes ROS 2/PX4 integration code and a [software-in-the-loop benchmark](experiments/benchmark_sim2real_hardware.py). Their presence does not establish physical robot validation. No real-robot evaluation is claimed here.

Results are specific to their scenarios, code, and data. Zero observed failures in a simulation does not establish zero risk or prove a safety guarantee.

## How the system is organized

```text
Sensor observations
       ↓
Cross-sensor checks and uncertainty monitoring
       ↓
Optional sensing, probing, and verification
       ↓
Controller decision: act / stop / abstain
       ↓
Control constraints and simulated environment
       ↓
Outcome and evidence recording
```

The codebase explores several related directions:

| Area | Starting point |
|---|---|
| V9 decision and monitoring | [`src/aegis/v9/`](src/aegis/v9/) |
| 3D simulation and control barriers | [`src/aegis/env/mujoco_3d_cbf.py`](src/aegis/env/mujoco_3d_cbf.py) and [`src/aegis/v9/controller_3d.py`](src/aegis/v9/controller_3d.py) |
| Swarm coordination | [`src/aegis/multiagent/`](src/aegis/multiagent/) |
| Vision, learning, planning, and vehicles | [`src/aegis/vision/`](src/aegis/vision/), [`rl/`](src/aegis/rl/), [`nmpc/`](src/aegis/nmpc/), and [`av/`](src/aegis/av/) |
| ROS 2/PX4 research integration | [`src/aegis/sim2real/`](src/aegis/sim2real/) |
| Benchmarks and tests | [`experiments/`](experiments/) and [`tests/`](tests/) |
| Reports and recorded outputs | [`docs/reports/`](docs/reports/) and [`results/`](results/) |

## Quick start

Requirements: Python **3.12 or newer**, [uv](https://docs.astral.sh/uv/), and a platform supported by the locked dependencies, including MuJoCo. Commands below are run from the repository root.

```bash
git clone https://github.com/Chalermsak1/nexvia-aegis.git
cd nexvia-aegis
uv sync --locked
```

Run a short 3D simulation smoke test:

```bash
PYTHONPATH=src uv run python experiments/benchmark_physical_3d_cbf.py \
  --n-seeds 1 --max-steps 5 --include-3d-aware
```

This checks that the benchmark starts and runs each configured policy. Five steps are too few to assess research performance; the output is **not** a confirmatory result.

Run the test suite:

```bash
uv run pytest -q
```

For a longer exploratory run, use `--n-seeds` and `--max-steps` to set the workload. The benchmark also supports range bias, dropout, latency, and vector-bias options:

```bash
PYTHONPATH=src uv run python experiments/benchmark_physical_3d_cbf.py --help
```

To retain episode-level output, add `--output` with a **new** file path. The tool refuses to overwrite an existing output file. Keep development results separate from any controlled evaluation artifacts.

## Research records

- [Preregistered V9 experiment protocol](docs/v9_experiment_protocol.md)
- [V9-M4 source audit and outstanding questions](docs/reports/v9_m4_release_remediation/V9_M4_POSTEXECUTION_SOURCE_AUDIT_2026-10-29.md)
- [Draft V9-M5 sim-to-real research protocol](docs/reports/v9_m4_release_remediation/V9_M5_SIM_TO_REAL_RESEARCH_PROTOCOL_DRAFT.md)
- [V9-M5 3D development results and limitations](docs/reports/v9_m5/V9_M5_DEVELOPMENT_CURRENT_STATUS_2026-10-29.md)
- [Phase 3 swarm coordination report](docs/reports/v9_m5/V9_PHASE3_SWARM_COORDINATION_REPORT.md)
- [Research manuscript (PDF)](paper/aegis_ieee_preprint.pdf) and [LaTeX source](paper/main.tex)

These documents reflect their respective snapshots and may use different status terminology. Check the underlying protocol, code, and evidence before treating a reported result as a formal claim.

## Reproducibility and scope

Record the commit, dependency environment, scenario settings, seed schedule, and raw outputs for each experiment. The repository's 3D benchmark supports explicit output paths and records runtime and source hashes. Do not reuse development results as a fresh confirmatory set. Physical testing requires a separately reviewed platform, ground-truth measurements, and a safety procedure.

Earlier experiments, including the original 2D benchmark, remain available in [`experiments/final_benchmark.py`](experiments/final_benchmark.py). Their metrics and assumptions should be read in the context of those experiments rather than applied to the newer 3D system.

## Author

Chalermsak Sinsrok · NEXVIA Core — Physical AI Research
