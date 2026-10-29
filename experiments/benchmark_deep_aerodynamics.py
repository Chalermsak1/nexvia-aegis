"""
NEXVIA AEGIS — Deep Aerodynamics & Electromechanical Physics Benchmark.

Runs 4 comprehensive physical benchmark experiments:
1. Regime A: In-Ground-Effect (IGE) Altitude Profiling (Cheeseman-Bennett Lift Amplification vs Altitude z).
2. Regime B: Gyroscopic Precession Cross-Moments during Agile Slalom Banking Maneuvers.
3. Regime C: 4S LiPo Battery Voltage Sag and Maximum Thrust Derating over Flight Duration.
4. Regime D: Multi-Agent 6-DOF Swarm Closed-Loop Flight under Full Aerodynamic Stress.

Saves benchmark data to results/data/deep_aerodynamics_benchmark.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from aegis.env.deep_aerodynamics import DeepAerodynamicsConfig, DeepAerodynamicsEngine
from aegis.env.quadrotor_6dof import (
    AegisQuadrotor6DOFEnvironment,
    QuadrotorConfig,
    quaternion_to_rotation_matrix,
)
from aegis.multiagent.swarm_6dof import (
    AegisMuJoCoSwarm6DOFEnvironment,
    Swarm6DOFConfig,
)


def run_ige_altitude_sweep() -> dict[str, Any]:
    """Sweeps altitude from ground level (z=0.03m) to OGE (z=1.20m)."""
    cfg = DeepAerodynamicsConfig(rotor_radius=0.09, max_ige_ratio=1.50, ige_enabled=True)
    engine = DeepAerodynamicsEngine(cfg)

    altitudes = np.linspace(0.04, 1.0, 50)
    base_thrust = np.array([3.0, 3.0, 3.0, 3.0], dtype=np.float64) # hover thrust
    R_level = np.eye(3, dtype=np.float64)

    measured_ratios = []
    theoretical_ratios = []

    for z in altitudes:
        pos = np.array([0.0, 0.0, z], dtype=np.float64)
        thrusts, ratios = engine.compute_ige_thrust(
            base_motor_thrusts=base_thrust,
            pos_world=pos,
            rotation_matrix=R_level,
            arm_length=0.22,
            floor_z=0.0,
        )
        z_rotor = z + 0.02
        z_eff = max(z_rotor, 0.45 * 0.09)
        denom = 1.0 - (0.09 / (4.0 * z_eff))**2
        ratio_theory = min(1.50, 1.0 / max(0.15, denom)) if z_rotor <= 4.0 * 0.09 else 1.0

        measured_ratios.append(float(np.mean(ratios)))
        theoretical_ratios.append(float(ratio_theory))

    return {
        "altitudes_m": [float(z) for z in altitudes],
        "measured_ige_ratios": measured_ratios,
        "theoretical_ige_ratios": theoretical_ratios,
    }


def run_gyroscopic_slalom_benchmark() -> dict[str, Any]:
    """Evaluates cross-axis gyroscopic reaction torques during rapid slalom banking."""
    cfg = QuadrotorConfig(
        enable_deep_aerodynamics=True,
        deep_aero_config=DeepAerodynamicsConfig(
            gyroscopic_enabled=True,
            ige_enabled=False,
            battery_enabled=False,
        ),
    )
    env = AegisQuadrotor6DOFEnvironment(cfg)
    env.reset()

    # Maneuver waypoints for aggressive S-curve slalom
    waypoints = [
        np.array([-1.2, -0.6, 1.0], dtype=np.float64),
        np.array([-0.4,  0.8, 1.2], dtype=np.float64),
        np.array([ 0.6, -0.7, 1.0], dtype=np.float64),
        np.array([ 1.5,  1.2, 1.1], dtype=np.float64),
    ]

    time_history = []
    omega_pitch_hist = []
    omega_roll_hist = []
    tau_gyro_x_hist = []
    tau_gyro_y_hist = []
    tilt_deg_hist = []

    wp_idx = 0
    k_p = 5.0
    k_d = 2.2

    for step in range(120): # 2.4s simulation
        t = step * cfg.outer_dt
        state = env.get_state()
        pos = state["pos"]
        vel = state["vel"]
        w_body = state["omega_body"]

        target = waypoints[wp_idx]
        if float(np.linalg.norm(pos - target)) < 0.45 and wp_idx < len(waypoints) - 1:
            wp_idx += 1

        f_des = k_p * (target - pos) - k_d * vel
        f_des[2] += cfg.mass * cfg.gravity

        state, _ = env.step_outer(desired_force_world=f_des, shield_with_cbf=True)

        deep = state["deep_aero"]
        time_history.append(t)
        omega_pitch_hist.append(float(w_body[1]))
        omega_roll_hist.append(float(w_body[0]))
        tau_gyro_x_hist.append(float(deep["tau_gyro"][0]))
        tau_gyro_y_hist.append(float(deep["tau_gyro"][1]))
        tilt_deg_hist.append(float(state["tilt_deg"]))

    return {
        "time_s": time_history,
        "omega_pitch_rad_s": omega_pitch_hist,
        "omega_roll_rad_s": omega_roll_hist,
        "tau_gyro_roll_nm": tau_gyro_x_hist,
        "tau_gyro_pitch_nm": tau_gyro_y_hist,
        "tilt_deg": tilt_deg_hist,
    }


def run_battery_sag_discharge_benchmark() -> dict[str, Any]:
    """Simulates 4S LiPo discharge and voltage sag over an extended high-thrust mission."""
    cfg = DeepAerodynamicsConfig(
        nominal_voltage=14.8,
        full_voltage=16.8,
        cutoff_voltage=12.8,
        battery_capacity_ah=0.5, # accelerated 500mAh test cell to observe discharge curve
        internal_resistance=0.045, # 45 mOhm
        avionics_current=0.65,
        battery_enabled=True,
    )
    engine = DeepAerodynamicsEngine(cfg)
    engine.reset(initial_soc=1.0)

    time_s = []
    v_ocv_hist = []
    v_term_hist = []
    current_hist = []
    soc_hist = []
    derate_hist = []
    t_max_hist = []

    dt = 0.05
    # Simulate variable thrust demand: hover (3N) -> punch-out (6.5N) -> cruise (3.5N)
    for step in range(400): # 20 seconds
        t = step * dt
        # Pulse thrusts
        if 4.0 <= t <= 7.0 or 12.0 <= t <= 15.0:
            thrust = 6.2 # heavy throttle punch-out
        else:
            thrust = 3.2 # nominal hover/cruise

        thrusts = np.full(4, thrust, dtype=np.float64)
        v_term, derate, eff_max = engine.step_battery_dynamics(thrusts, dt=dt, nominal_max_thrust=8.5)

        time_s.append(t)
        v_ocv_hist.append(float(engine.state.v_ocv))
        v_term_hist.append(float(v_term))
        current_hist.append(float(engine.state.load_current))
        soc_hist.append(float(engine.state.soc * 100.0))
        derate_hist.append(float(derate))
        t_max_hist.append(float(eff_max))

    return {
        "time_s": time_s,
        "v_ocv_v": v_ocv_hist,
        "v_terminal_v": v_term_hist,
        "current_a": current_hist,
        "soc_pct": soc_hist,
        "derate_factor": derate_hist,
        "max_thrust_n": t_max_hist,
    }


def run_swarm_deep_aero_benchmark() -> dict[str, Any]:
    """Runs 5-drone multi-agent swarm under full deep aerodynamics."""
    cfg = Swarm6DOFConfig(
        num_robots=5,
        enable_deep_aerodynamics=True,
        deep_aero_config=DeepAerodynamicsConfig(
            ige_enabled=True,
            gyroscopic_enabled=True,
            battery_enabled=True,
            nominal_voltage=14.8,
            full_voltage=16.8,
            cutoff_voltage=12.8,
            battery_capacity_ah=1.5,
            internal_resistance=0.035,
        ),
        wind_enabled=True,
    )
    env = AegisMuJoCoSwarm6DOFEnvironment(cfg)
    rng = np.random.default_rng(101)
    state = env.reset(rng=rng, initial_soc=0.92)

    trajectories = [[] for _ in range(5)]
    soc_trajectories = [[] for _ in range(5)]
    ige_mean_hist = [[] for _ in range(5)]
    k_p = 3.2
    k_d = 1.9

    for step in range(80): # 1.6s simulation
        forces = []
        for i in range(cfg.num_robots):
            pos_i = state["positions"][i]
            vel_i = state["velocities"][i]
            f_i = k_p * (env.target_pos - pos_i) - k_d * vel_i
            f_i[2] += cfg.mass * cfg.gravity
            forces.append(f_i)

            trajectories[i].append([float(pos_i[0]), float(pos_i[1]), float(pos_i[2])])
            soc_trajectories[i].append(float(state["deep_aero"][i]["soc"] * 100.0))
            ige_mean_hist[i].append(float(np.mean(state["deep_aero"][i]["ige_ratios"])))

        state, _ = env.step_outer(desired_forces=forces, shield_with_cbf=True, rng=rng)

    final_distances = [float(d) for d in state["distances"]]
    return {
        "num_robots": cfg.num_robots,
        "trajectories": trajectories,
        "soc_trajectories": soc_trajectories,
        "ige_mean_hist": ige_mean_hist,
        "final_distances_to_target": final_distances,
        "inter_agent_collisions": state["inter_agent_collisions"],
        "target_pos": [float(x) for x in env.target_pos],
    }


def main() -> None:
    print("=" * 70)
    print("NEXVIA AEGIS — Deep Aerodynamics & Electromechanical Benchmark")
    print("=" * 70)

    print("\n[1/4] Running Cheeseman-Bennett IGE Altitude Profiling...")
    ige_data = run_ige_altitude_sweep()
    print(f"  Max IGE Boost: {max(ige_data['measured_ige_ratios']):.3f}x at low altitude")

    print("\n[2/4] Running Gyroscopic Precession Slalom Banking Benchmark...")
    gyro_data = run_gyroscopic_slalom_benchmark()
    max_tau_x = max(abs(x) for x in gyro_data["tau_gyro_roll_nm"])
    max_tau_y = max(abs(y) for y in gyro_data["tau_gyro_pitch_nm"])
    print(f"  Peak Gyroscopic Torques: Roll={max_tau_x:.4f} N*m, Pitch={max_tau_y:.4f} N*m")

    print("\n[3/4] Running 4S LiPo Battery Voltage Sag & Thrust Derate Benchmark...")
    bat_data = run_battery_sag_discharge_benchmark()
    min_v = min(bat_data["v_terminal_v"])
    max_amp = max(bat_data["current_a"])
    min_thrust = min(bat_data["max_thrust_n"])
    print(f"  Max Current Draw: {max_amp:.1f} A, Lowest Terminal Voltage: {min_v:.2f} V")
    print(f"  Thrust Derating: 8.50 N -> {min_thrust:.2f} N")

    print("\n[4/4] Running Multi-Agent 6-DOF Swarm under Full Deep Aerodynamics...")
    swarm_data = run_swarm_deep_aero_benchmark()
    print(f"  Swarm Drones: {swarm_data['num_robots']}, Inter-agent collisions: {swarm_data['inter_agent_collisions']}")
    print(f"  Final Mean Distance to Target: {np.mean(swarm_data['final_distances_to_target']):.3f} m")

    benchmark_payload = {
        "ige_profile": ige_data,
        "gyroscopic_slalom": gyro_data,
        "battery_sag": bat_data,
        "swarm_flight": swarm_data,
    }

    out_path = Path("results/data/deep_aerodynamics_benchmark.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(benchmark_payload, f, indent=2)

    print(f"\n[DONE] Benchmark results saved to: {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
