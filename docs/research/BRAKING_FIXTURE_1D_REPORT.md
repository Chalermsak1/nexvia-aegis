# NEXVIA AEGIS — 1D Braking & Fallback Control Study Report

> **Scope Notice:** Exploratory 1D simulation fixture and fault-injection study only. **Release BLOCKED · `GATE_B_NOT_AUTHORIZED`.** Results in this report verify physical kinematics inside a declared 1D simulation model and do not constitute hardware validation or operational safety certification.

## 1. Architecture & Integrity Contract

This study implements a minimal closed-loop 1D simulation and fallback braking fixture in [braking_fixture_1d.py](../../src/aegis/development/braking_fixture_1d.py), reusing the repository's existing `DelayedSlewBrake` actuator model from [dynamic_braking.py](../../src/aegis/development/dynamic_braking.py).

Two strict integrity rules are enforced in code and verified by unit tests ([test_braking_fixture_1d.py](../../tests/test_braking_fixture_1d.py)):

1. **No Hidden-State Leakage to the Controller:** `FallbackBrakeController` receives only `SensorObservation` (`tick`, `timestamp_s`, `measured_position_m`, `measured_velocity_m_s`, `obstacle_position_m`). It has no access to plant true state, actual actuator force, power-loss status, backup availability, or external disturbance.
2. **Physical Outcome Verification Only:** Issuing a brake command never counts as a safe stop. An episode is labeled `SAFE_PHYSICAL_STOP` only if:
   - `min_clearance_m > 0` across all timesteps **including analytical inter-sample extrema** ($p(t) = p_0 + v_0 t + \frac{1}{2} a t^2$), and
   - the plant physically reaches rest (`|v| <= 1e-3 m/s`) with available braking force at least equal to the opposing disturbance.

## 2. Model Assumptions & Limitations

### Declared Assumptions
- **1D Point-Mass Kinematics:** Motion is constrained to the positive $+x$ axis with fixed mass $m = 10\,\text{kg}$, initial velocity $v_0 = 5.0\,\text{m/s}$, initial position $x_0 = 0.0\,\text{m}$, and a static obstacle at $x_{\text{obs}} = 10.0\,\text{m}$.
- **Discrete Integration Step:** Fixed sample interval $\Delta t = 0.02\,\text{s}$ (`max_ticks = 250`, 5.0 s horizon), with exact constant-acceleration integration and analytical zero-crossing/apex detection inside each step.
- **Actuator Model (`DelayedSlewBrake`):**
  - Pure FIFO tick delay (`delay_ticks` $\times \Delta t$).
  - Linear force slew-rate limit (`slew_n_s` in N/s) and symmetric force saturation (`cap_n` in N).
  - Power loss immediately drops primary brake force to `0 N` and flushes queued commands.
- **Backup Actuator Handoff:** When configured and `backup_available=True`, the independent backup `DelayedSlewBrake` begins accepting brake requests upon primary power loss, subject to its own delay, slew rate, and force cap.
- **Static Braking Hold:** Braking force opposes forward motion and cannot accelerate the vehicle backward; once stopped, it holds rest if and only if $|F_{\text{brake}}| \ge F_{\text{disturbance}}$.

### Known Limitations (Not Modeled Here)
- **No 3D / Contact / Tire-Road Physics:** No friction-circle saturation, wheel slip, pitch/load transfer, or MuJoCo multibody contact dynamics.
- **Constant Disturbance Only:** External disturbance $F_{\text{disturbance}}$ is modeled as a constant forward force per episode, not time-varying gusts or grade profiles.
- **No Sensor Staleness / Packet Drop in This Sweep:** Although `SensorObservation` supports additive position/velocity bias, this baseline sweep isolates actuator/power/disturbance faults (sensor-staleness and frozen-sensor faults remain separate active research items).
- **One-Way Latched Fallback:** Once `FallbackBrakeController` latches braking (`assumed_decel = 2.5 m/s^2`, `trigger_margin = 1.5 m`), it does not implement return-to-nominal reauthorization.

## 3. Experimental Results (Raw Evidence)

All 14 scenarios were executed via [run_braking_study_1d.py](../../scripts/research/run_braking_study_1d.py). Immutable raw per-step CSV traces and JSON summaries are stored in [`results/research_development/braking_fixture_1d/run_01/`](../../results/research_development/braking_fixture_1d/run_01/).

Summary from [`campaign_summary.json`](../../results/research_development/braking_fixture_1d/run_01/campaign_summary.json) (**8 `SAFE_PHYSICAL_STOP`, 6 `COLLISION`**):

| Scenario | Delay (ticks / s) | Slew (N/s) | Cap (N) | Power Loss / Backup | Disturb (N) | Cmd Time (s) | Engage Time (s) | Stop Dist (m) | Max Brake (N) | Min Clearance (m) | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `01_nominal_ideal` | 0 / 0.00 | 5000 | 50 | None | 0 | 0.70 | 0.70 | 2.50 | 50.0 | +4.00 | **SAFE_PHYSICAL_STOP** |
| `02_delay_100ms` | 5 / 0.10 | 5000 | 50 | None | 0 | 0.70 | 0.80 | 3.00 | 50.0 | +3.50 | **SAFE_PHYSICAL_STOP** |
| `03_delay_300ms` | 15 / 0.30 | 5000 | 50 | None | 0 | 0.70 | 1.00 | 4.00 | 50.0 | +2.50 | **SAFE_PHYSICAL_STOP** |
| `04_delay_600ms_fail` | 30 / 0.60 | 5000 | 50 | None | 0 | 0.70 | 1.30 | 5.50 | 50.0 | +1.00 | **SAFE_PHYSICAL_STOP** |
| `05_ramp_100n_s` | 0 / 0.00 | 100 | 50 | None | 0 | 0.70 | 0.70 | 3.65 | 50.0 | +2.85 | **SAFE_PHYSICAL_STOP** |
| `06_ramp_40n_s` | 0 / 0.00 | 40 | 50 | None | 0 | 0.70 | 0.70 | 5.25 | 50.0 | +1.25 | **SAFE_PHYSICAL_STOP** |
| `07_ramp_15n_s_fail` | 0 / 0.00 | 15 | 50 | None | 0 | 0.70 | 0.70 | — | 21.9 | -0.01 | **COLLISION** (`v=3.38 m/s`) |
| `08_power_loss_backup_ok` | 0 / 0.00 | 2000 | 50 | tick 30 / 35N backup | 0 | 0.70 | 0.76 | 4.00 | 35.0 | +2.50 | **SAFE_PHYSICAL_STOP** |
| `09_power_loss_backup_weak_fail` | 0 / 0.00 | 2000 | 50 | tick 30 / 12N backup | 0 | 0.70 | 0.90 | — | 12.0 | -0.06 | **COLLISION** (`v=3.50 m/s`) |
| `10_power_loss_no_backup_fail` | 0 / 0.00 | 2000 | 50 | tick 30 / unavailable | 0 | 0.70 | — | — | 0.0 | -0.10 | **COLLISION** (`v=5.00 m/s`) |
| `11_disturbance_15n_cap_50n` | 0 / 0.00 | 2000 | 50 | None | 15 | 0.42 | 0.42 | 4.56 | 50.0 | +3.21 | **SAFE_PHYSICAL_STOP** |
| `12_disturbance_30n_cap_25n_fail` | 0 / 0.00 | 2000 | 25 | None | 30 | 0.30 | 0.30 | — | 25.0 | -0.12 | **COLLISION** (`v=6.58 m/s`) |
| `13_combined_moderate_ok` | 3 / 0.06 | 150 | 45 | tick 40 / 35N backup | 8 | 0.52 | 0.58 | — | 35.0 | -0.003 | **COLLISION** (`v=1.88 m/s`) |
| `14_combined_severe_fail` | 8 / 0.16 | 60 | 40 | tick 40 / 25N backup | 15 | 0.42 | 0.58 | — | 25.0 | -0.05 | **COLLISION** (`v=6.16 m/s`) |

## 4. Pass / Fail Boundary Analysis

### Where the System Succeeds (8/14)
- **Nominal & Bounded Delay (`01`–`04`):** Because the fallback controller triggers conservatively at $t = 0.70\,\text{s}$ ($6.50\,\text{m}$ remaining clearance) using `assumed_decel = 2.5 m/s^2` while the actual actuator delivers $5.0\,\text{m/s}^2$, it absorbs up to `600 ms` of pure delay (`04_delay_600ms_fail` still stopped with `+1.00 m` clearance). Each additional `100 ms` of delay adds exactly `0.50 m` of coasting distance ($v_0 \cdot \Delta \tau$).
- **Moderate Force Ramping (`05`–`06`):** Slew rates of `100 N/s` and `40 N/s` extend stopping distance from `2.50 m` to `3.65 m` and `5.25 m`, respectively, while still stopping safely before the obstacle.
- **Power Loss with Capable Backup (`08`):** Losing primary power at tick 30 (before braking starts) is survivable when an independent `35 N` backup engages with `60 ms` delay (`+2.50 m` clearance).
- **Sub-Cap Disturbance (`11`):** Under a constant `+15 N` forward disturbance, the vehicle accelerates earlier, causing the observation-only controller to trigger braking earlier (`t = 0.42 s`) and stop safely with `+3.21 m` clearance because net deceleration ($-3.5\,\text{m/s}^2$) remains strictly negative.

### Where the System Fails (6/14)
- **Severe Force Ramp Limit (`07`):** At `15 N/s`, braking force only reaches `21.9 N` before impact; the vehicle collides at `3.38 m/s`.
- **Weak or Unavailable Backup on Power Loss (`09`, `10`):** A `12 N` delayed backup (`09`) cannot decelerate the vehicle in time (`v = 3.50 m/s` at impact), and missing backup (`10`) results in an unbraked impact at `5.00 m/s` even though the controller issued a valid brake command at `t = 0.70 s`.
- **Disturbance Exceeding Actuator Cap (`12`):** When forward disturbance (`30 N`) exceeds the saturated actuator cap (`25 N`), net force remains positive (`+5 N`) and the vehicle accelerates into the obstacle (`v = 6.58 m/s`).
- **Combined Moderate Faults (`13`, `14`) — Key Counterexample:** Even though `13_combined_moderate_ok` was initially expected to pass (only `60 ms` delay, `150 N/s` ramp, `8 N` disturbance, and a `35 N` backup), **combining all four faults** causes a collision at `1.88 m/s`. Losing primary force at tick 40 (`t = 0.80 s`) mid-braking, waiting for backup delay, and ramping backup force against an `8 N` forward disturbance exhausts the remaining clearance. This confirms that **passing single-fault tests independently does not establish joint-fault safety**.

## 5. Reproduction Commands

Run the verification test suite:
```powershell
$env:PYTHONDONTWRITEBYTECODE="1"; $env:PYTHONPATH="src;."
python -m pytest -v -p no:cacheprovider tests/test_braking_fixture_1d.py
```

Generate a fresh immutable raw-evidence campaign (choose a new output directory):
```powershell
$env:PYTHONDONTWRITEBYTECODE="1"; $env:PYTHONPATH="src;."
python -m scripts.research.run_braking_study_1d --output-dir results/research_development/braking_fixture_1d/run_02
```
