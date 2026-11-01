// ============================================================================
// NEXVIA AEGIS: C++ Micro-Kernel Shared Library Implementation
// ============================================================================

#include "aegis/robust_tube_clbf.hpp"
#include <vector>

extern "C" {

AegisCResult aegis_micro_kernel_solve(
    AegisCState state,
    double gx, double gy, double gz,
    const AegisCObstacle* obs_arr,
    int num_obs,
    double tau_lag,
    double beta_min,
    double sigma_p,
    double sigma_v,
    int force_probe,
    int probe_step
) {
    static const aegis::RobustTubeCLBFKernel kernel;

    aegis::State3D s{
        {state.px, state.py, state.pz},
        {state.vx, state.vy, state.vz}
    };
    aegis::Vector3D goal{gx, gy, gz};

    std::vector<aegis::Obstacle3D> obstacles;
    if (obs_arr != nullptr && num_obs > 0) {
        obstacles.reserve(num_obs);
        for (int i = 0; i < num_obs; ++i) {
            obstacles.push_back({
                {obs_arr[i].cx, obs_arr[i].cy, obs_arr[i].cz},
                obs_arr[i].radius
            });
        }
    }

    aegis::MicroQPSolution sol = kernel.solve(
        s,
        goal,
        obstacles.empty() ? nullptr : obstacles.data(),
        obstacles.size(),
        tau_lag,
        beta_min,
        sigma_p,
        sigma_v,
        force_probe != 0,
        probe_step
    );

    AegisCResult res;
    res.ax = sol.a_safe.x;
    res.ay = sol.a_safe.y;
    res.az = sol.a_safe.z;
    res.feasible = sol.feasible ? 1 : 0;
    res.is_abstain = sol.is_abstain ? 1 : 0;
    res.in_probing = sol.in_probing ? 1 : 0;
    res.solve_time_us = sol.solve_time_us;
    res.min_margin = sol.min_barrier_margin;

    return res;
}

} // extern "C"
