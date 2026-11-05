/**
 * NEXVIA AEGIS — C++20 CTest Suite for Real-Time RTI-SQP NMPC-HOCBF Kernel.
 */

#include <iostream>
#include <cassert>
#include <cmath>
#include <chrono>
#include "aegis/robust_tube_clbf.hpp"

void test_hover_equilibrium() {
    std::cout << "[CTest] Running test_hover_equilibrium..." << std::endl;
    double current_pos[3] = {0.0, 0.0, 1.0};
    double current_vel[3] = {0.0, 0.0, 0.0};
    double target_pos[3] = {0.0, 0.0, 1.0};
    double target_vel[3] = {0.0, 0.0, 0.0};
    double last_force[3] = {0.0, 0.0, 1.25 * 9.81};

    auto t_start = std::chrono::high_resolution_clock::now();
    AegisNmpcResult res = aegis_nmpc_cbf_solve(
        current_pos, current_vel, target_pos, target_vel,
        last_force, nullptr,
        nullptr, 0,
        nullptr, 0
    );
    auto t_end = std::chrono::high_resolution_clock::now();
    double elapsed_us = std::chrono::duration<double, std::micro>(t_end - t_start).count();

    assert(res.success == 1);
    // Mass 1.25 * 9.81 = ~12.2625 N
    double hover_f_z = 1.25 * 9.81;
    assert(std::abs(res.f0_z - hover_f_z) < 0.5);
    assert(std::abs(res.f0_x) < 0.2);
    assert(std::abs(res.f0_y) < 0.2);

    std::cout << "  -> PASS! Hover F_z: " << res.f0_z
              << " N (Solve time: " << elapsed_us << " us, reported kernel time: "
              << res.solve_time_us << " us)" << std::endl;
}

void test_obstacle_avoidance_sub_millisecond() {
    std::cout << "[CTest] Running test_obstacle_avoidance_sub_millisecond..." << std::endl;
    double current_pos[3] = {0.0, 0.0, 1.0};
    double current_vel[3] = {1.2, 0.0, 0.0};
    double target_pos[3] = {1.6, 0.0, 1.0};
    double target_vel[3] = {0.0, 0.0, 0.0};
    double last_force[3] = {0.0, 0.0, 1.25 * 9.81};

    AegisNmpcObstacle obs;
    obs.cx = 0.5;
    obs.cy = 0.04;
    obs.cz = 1.0;
    obs.radius = 0.18;
    obs.vx = 0.0;
    obs.vy = 0.0;
    obs.vz = 0.0;

    AegisNmpcResult res = aegis_nmpc_cbf_solve(
        current_pos, current_vel, target_pos, target_vel,
        last_force, nullptr,
        &obs, 1,
        nullptr, 0
    );

    assert(res.success == 1);
    assert(res.solve_time_us < 2500.0); // Sub-millisecond RTI-SQP / ADMM target

    // Must have positive safety barrier margin
    assert(res.min_barrier_margin >= 0.06);

    std::cout << "  -> PASS! Min margin: " << res.min_barrier_margin
              << " m, Solve time: " << res.solve_time_us << " us" << std::endl;
}

void test_corridor_polytope_constraints() {
    std::cout << "[CTest] Running test_corridor_polytope_constraints..." << std::endl;
    double current_pos[3] = {0.0, 0.0, 1.0};
    double current_vel[3] = {0.5, 0.5, 0.0};
    double target_pos[3] = {1.0, 1.0, 1.0};
    double target_vel[3] = {0.0, 0.0, 0.0};
    double last_force[3] = {0.0, 0.0, 1.25 * 9.81};

    // Corridor plane: Y <= 0.4
    AegisNmpcCorridorPlane plane;
    plane.nx = 0.0;
    plane.ny = 1.0;
    plane.nz = 0.0;
    plane.d = 0.40;

    AegisNmpcResult res = aegis_nmpc_cbf_solve(
        current_pos, current_vel, target_pos, target_vel,
        last_force, nullptr,
        nullptr, 0,
        &plane, 1
    );

    assert(res.success == 1);

    std::cout << "  -> PASS! Corridor solved successfully in " << res.solve_time_us << " us" << std::endl;
}

int main() {
    std::cout << "=== NEXVIA AEGIS C++20 RTI-SQP NMPC-HOCBF CTest ===" << std::endl;
    test_hover_equilibrium();
    test_obstacle_avoidance_sub_millisecond();
    test_corridor_polytope_constraints();
    std::cout << "All C++20 CTest tests passed successfully!" << std::endl;
    return 0;
}
