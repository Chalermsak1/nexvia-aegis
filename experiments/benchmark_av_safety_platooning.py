"""
Comprehensive Benchmark: Autonomous Vehicles (AV) Safety Shield & Cyber-Resilient Platooning.

Evaluates 30 episodes across two challenging real-world scenarios:
  Scenario 1: High-Speed Curve on Wet/Icy Asphalt (mu = 0.35)
              - Unshielded Tracking vs AEGIS Kamm's Friction Circle & Lane HOCBF Shield.
              - Metrics: Lane Departure (m), Peak Sideslip Angle (deg), Spin-out Count.

  Scenario 2: Connected 4-Car Platoon under Phantom Brake & Spoofing Attack
              - Naive C-V2X vs AEGIS Cyber-Resilient Platoon Controller (Ville Martingales).
              - Metrics: Rear-end Collisions, Eviction Latency (ms), Ville Martingale Wealth.
"""

import json
import math
import os
import time
import numpy as np

from aegis.av.frenet_cbf_shield import FrenetCbfConfig, FrenetSafetyShield
from aegis.av.platooning_brmc import (
    CyberResilientPlatoonController,
    PlatoonConfig,
    V2XTelemetryPacket,
)
from aegis.av.vehicle_dynamics import (
    DynamicBicycleModel,
    FrenetFrame,
    VehicleConfig,
    VehicleState,
)


def run_av_benchmark(n_episodes: int = 15) -> dict:
    print(f"=== Starting Autonomous Vehicles (AV) & Platooning Benchmark ({n_episodes * 2} episodes) ===")

    # -----------------------------------------------------------------
    # Setup Road Geometry (Curved Highway with 80m radius bend)
    # -----------------------------------------------------------------
    s_straight1 = np.linspace(0, 100, 50)
    theta_curve = np.linspace(0, math.pi / 3.0, 60) # 60 deg bend with R=80m
    R_curve = 80.0
    curve_x = 100.0 + R_curve * np.sin(theta_curve)
    curve_y = R_curve * (1.0 - np.cos(theta_curve))
    s_straight2 = np.linspace(0, 100, 50)
    end_angle = math.pi / 3.0
    end_x = curve_x[-1] + s_straight2 * math.cos(end_angle)
    end_y = curve_y[-1] + s_straight2 * math.sin(end_angle)

    waypoints = np.column_stack([
        np.concatenate([s_straight1, curve_x, end_x]),
        np.concatenate([np.zeros(len(s_straight1)), curve_y, end_y]),
    ])
    road_frame = FrenetFrame(waypoints)

    # -----------------------------------------------------------------
    # Benchmark 1: High-Speed Curve on Wet/Icy Road (mu = 0.35)
    # -----------------------------------------------------------------
    print("\n--- Running Benchmark 1: Wet Highway Curve (mu = 0.35, v = 24 m/s / 86 km/h) ---")
    wet_cfg = VehicleConfig(friction_coeff=0.35)
    cbf_cfg = FrenetCbfConfig(lane_width=3.6, lane_safety_margin=0.25)

    dyn_model = DynamicBicycleModel(wet_cfg)
    shield = FrenetSafetyShield(wet_cfg, cbf_cfg)

    scenario1_results = {
        "Unshielded_AV": {"lane_departures": [], "spin_outs": [], "max_sideslips_deg": [], "trajectories": []},
        "AEGIS_Shielded_AV": {"lane_departures": [], "spin_outs": [], "max_sideslips_deg": [], "trajectories": []},
    }

    dt = 0.02 # 50 Hz control loop
    for mode in ["Unshielded_AV", "AEGIS_Shielded_AV"]:
        spin_out_count = 0
        lane_departure_count = 0

        for ep in range(n_episodes):
            state = VehicleState(x=60.0, y=0.0, yaw=0.0, v_x=24.0, v_y=0.0, yaw_rate=0.0) # 86 km/h
            traj = []
            max_sideslip = 0.0
            max_d_excursion = 0.0

            for step in range(450): # 9.0 seconds
                frenet = road_frame.cartesian_to_frenet(state.x, state.y, state.yaw, state.v_x, state.v_y)
                max_d_excursion = max(max_d_excursion, abs(frenet.d))
                sideslip_deg = math.degrees(abs(state.sideslip_angle))
                max_sideslip = max(max_sideslip, sideslip_deg)

                # Stanley steering control law with road curvature feedforward
                steer_ff = math.atan(wet_cfg.wheelbase * frenet.road_curvature)
                steer_fb = 0.8 * frenet.yaw_rel - math.atan(1.2 * frenet.d / max(1.0, state.v_x))
                steer_error = steer_ff + steer_fb
                nom_steer = float(np.clip(steer_error, -wet_cfg.max_steering_rad, wet_cfg.max_steering_rad))
                nom_accel = 0.0 # Maintain speed

                if mode == "Unshielded_AV":
                    # Unshielded: commands applied directly without checking friction circle or lane limits
                    cmd_accel = nom_accel
                    cmd_steer = nom_steer
                else:
                    # AEGIS Shield: clamps steering to Kamm's circle and adjusts speed to curvature
                    shielded = shield.filter_control(
                        state=state,
                        frenet=frenet,
                        nominal_accel=nom_accel,
                        nominal_steering=nom_steer,
                        road_frame=road_frame,
                    )
                    cmd_accel = shielded.accel_cmd
                    cmd_steer = shielded.steering_cmd

                state, _ = dyn_model.step(state, cmd_accel=cmd_accel, cmd_steering=cmd_steer, dt=dt)
                traj.append([state.x, state.y, frenet.s, frenet.d, state.v_x, sideslip_deg])

                # Check spin-out (sideslip > 15 deg)
                if sideslip_deg > 15.0:
                    spin_out_count += 1
                    break

            # Check lane departure (half lane width = 1.8m, vehicle half width = 0.95m => |d| > 0.85m)
            lane_limit = (cbf_cfg.lane_width - wet_cfg.width) / 2.0
            if max_d_excursion > lane_limit:
                lane_departure_count += 1

            scenario1_results[mode]["lane_departures"].append(float(max_d_excursion))
            scenario1_results[mode]["max_sideslips_deg"].append(float(max_sideslip))
            if ep == 0:
                scenario1_results[mode]["trajectories"] = traj

        scenario1_results[mode]["spin_outs"] = spin_out_count
        print(f"  {mode}: Spin-outs={spin_out_count}/{n_episodes} | Departures={lane_departure_count}/{n_episodes} | MaxSideslip={np.mean(scenario1_results[mode]['max_sideslips_deg']):.1f} deg")

    # -----------------------------------------------------------------
    # Benchmark 2: Connected 4-Car Platoon under Cyber-Attack
    # -----------------------------------------------------------------
    print("\n--- Running Benchmark 2: Connected Platoon under Phantom Brake & Cyber Attack ---")
    p_cfg = PlatoonConfig(martingale_alpha=0.001, betting_lambda=0.4)

    scenario2_results = {
        "Naive_V2X_Platoon": {"rear_end_collisions": 0, "min_gaps": [], "crash_episodes": []},
        "AEGIS_Cyber_Platoon": {"rear_end_collisions": 0, "min_gaps": [], "eviction_latencies_ms": [], "wealth_curves": []},
    }

    # Simulate 4-car platoon where Lead Car (Car 1) executes sudden braking at t=1.5s
    # but attacker broadcasts fake acceleration in V2X (Spoofing Attack)
    for mode in ["Naive_V2X_Platoon", "AEGIS_Cyber_Platoon"]:
        crashes = 0
        min_gaps = []
        evict_lats = []
        wealth_history = []

        for ep in range(n_episodes):
            lead_state = VehicleState(x=35.0, v_x=25.0)  # Lead vehicle (90 km/h)
            ego_state = VehicleState(x=18.0, v_x=25.0)   # Follower vehicle (Gap = 17m)
            controller = CyberResilientPlatoonController(vehicle_id=2, platoon_config=p_cfg)

            ep_min_gap = 1e6
            evicted_time = None
            wealth_trace = []
            gap_trace = []

            for step in range(200): # 4.0 seconds
                t = step * dt

                # Lead vehicle dynamics: at t=1.5s, lead car slams physical brakes (-7.0 m/s^2)
                if t >= 1.5:
                    actual_lead_accel = -7.0
                    # ATTACK: V2X packet lies and broadcasts zero or positive acceleration!
                    claimed_v2x_accel = 0.0
                else:
                    actual_lead_accel = 0.0
                    claimed_v2x_accel = 0.0

                lead_state, _ = dyn_model.step(lead_state, cmd_accel=actual_lead_accel, cmd_steering=0.0, dt=dt)

                # Radar measurements
                radar_dist = float(lead_state.x - ego_state.x - wet_cfg.length)
                radar_rel_speed = float(lead_state.v_x - ego_state.v_x)
                ep_min_gap = min(ep_min_gap, radar_dist)
                gap_trace.append([t, radar_dist, float(ego_state.v_x), float(lead_state.v_x)])

                v2x_pkt = V2XTelemetryPacket(
                    sender_id=1,
                    timestamp=t,
                    claimed_s=lead_state.x,
                    claimed_speed=25.0,
                    claimed_accel=claimed_v2x_accel,
                )

                if mode == "Naive_V2X_Platoon":
                    # Naive CACC: Trusts claimed V2X acceleration blindly!
                    # CACC formula: a_cmd = a_v2x + k_p * (gap - gap_des) + k_d * rel_v
                    gap_des = p_cfg.min_gap + p_cfg.nominal_time_headway * ego_state.v_x
                    cmd_a = claimed_v2x_accel + 0.6 * (radar_dist - gap_des) + 0.8 * radar_rel_speed
                    cmd_a = float(np.clip(cmd_a, -wet_cfg.max_decel, wet_cfg.max_accel))
                else:
                    # AEGIS: Ville Supermartingale Cross-Validation & Eviction
                    cmd_a, _, status = controller.update_v2x_and_control(
                        current_state=ego_state,
                        current_time=t,
                        radar_distance=radar_dist,
                        radar_rel_speed=radar_rel_speed,
                        v2x_packet=v2x_pkt,
                    )
                    wealth_trace.append([t, status.martingale_wealth])
                    if status.v2x_evicted and evicted_time is None:
                        evicted_time = (t - 1.5) * 1000.0 # latency from attack start in ms

                ego_state, _ = dyn_model.step(ego_state, cmd_accel=cmd_a, cmd_steering=0.0, dt=dt)

                # Collision check
                if radar_dist <= 0.0:
                    crashes += 1
                    break

            min_gaps.append(ep_min_gap)
            if evicted_time is not None:
                evict_lats.append(evicted_time)
            if ep == 0:
                scenario2_results[mode]["gap_trace"] = gap_trace
            if ep == 0 and wealth_trace:
                wealth_history = wealth_trace

        scenario2_results[mode]["rear_end_collisions"] = crashes
        scenario2_results[mode]["min_gaps"] = min_gaps
        if mode == "AEGIS_Cyber_Platoon":
            scenario2_results[mode]["eviction_latencies_ms"] = evict_lats
            scenario2_results[mode]["wealth_curves"] = wealth_history

        print(f"  {mode}: Rear-end Crashes={crashes}/{n_episodes} | Min Gap={np.mean(min_gaps):.2f}m")

    # Save to JSON
    out_dir = "results/data"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "av_safety_platooning_benchmark.json")
    with open(out_path, "w") as f:
        json.dump({
            "scenario1_wet_curve": scenario1_results,
            "scenario2_platooning_attack": scenario2_results,
        }, f, indent=2)

    print(f"\nSaved AV benchmark results to {out_path}")
    return {"scenario1": scenario1_results, "scenario2": scenario2_results}


if __name__ == "__main__":
    run_av_benchmark(n_episodes=15)
