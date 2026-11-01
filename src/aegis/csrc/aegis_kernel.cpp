// ============================================================================
// NEXVIA AEGIS: C++ Micro-Kernel Shared Library Implementation
// Zero Dynamic Allocation C-ABI Entrypoint
// ============================================================================

#include "aegis/robust_tube_clbf.hpp"

namespace {

thread_local aegis::KernelConfig g_filter_config{
    4.0,   // a_max
    3.0,   // v_max
    0.04,  // dt
    1.5,   // gamma_clf
    2.0,   // alpha_cbf
    2.5,   // kappa_delta
    0.25,  // sigma_p_thresh
    0.40,  // sigma_v_thresh
    0.005, // still_energy_thresh
    15     // dwell_steps_required
};

} // namespace

extern "C" {

void aegis_micro_kernel_configure(
    double a_max,
    double v_max,
    double dt,
    double alpha_cbf,
    double kappa_delta,
    double sigma_p_thresh,
    double sigma_v_thresh
) {
    g_filter_config.a_max = a_max;
    g_filter_config.v_max = v_max;
    g_filter_config.dt = dt;
    g_filter_config.alpha_cbf = alpha_cbf;
    g_filter_config.kappa_delta = kappa_delta;
    g_filter_config.sigma_p_thresh = sigma_p_thresh;
    g_filter_config.sigma_v_thresh = sigma_v_thresh;
}

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
    const aegis::State3D s{
        {state.px, state.py, state.pz},
        {state.vx, state.vy, state.vz}
    };
    const aegis::Vector3D target_or_cmd{gx, gy, gz};
    const size_t n_obs = (obs_arr != nullptr && num_obs > 0)
        ? static_cast<size_t>(num_obs)
        : 0u;

    auto get_center = [](const AegisCObstacle& o) -> aegis::Vector3D {
        return {o.cx, o.cy, o.cz};
    };
    auto get_radius = [](const AegisCObstacle& o) -> double {
        return o.radius;
    };
    auto get_velocity = [](const AegisCObstacle& o) -> aegis::Vector3D {
        return {o.vx, o.vy, o.vz};
    };

    aegis::MicroQPSolution sol;
    if (force_probe < 0) {
        // Direct inline command filter mode (AegisSafetyBox)
        const aegis::RobustTubeCLBFKernel filter_kernel(g_filter_config);
        sol = filter_kernel.filter_command_templated(
            s,
            target_or_cmd,
            (n_obs > 0) ? obs_arr : nullptr,
            n_obs,
            get_center,
            get_radius,
            get_velocity,
            tau_lag,
            beta_min,
            sigma_p,
            sigma_v
        );
    } else {
        // Standalone goal-directed CLF + Dynamic Tube-CBF mode
        static constexpr aegis::RobustTubeCLBFKernel goal_kernel{};
        sol = goal_kernel.solve_goal_templated(
            s,
            target_or_cmd,
            (n_obs > 0) ? obs_arr : nullptr,
            n_obs,
            get_center,
            get_radius,
            get_velocity,
            tau_lag,
            beta_min,
            sigma_p,
            sigma_v,
            force_probe != 0,
            probe_step
        );
    }

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
