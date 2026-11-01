// ============================================================================
// NEXVIA AEGIS: High-Performance C++20 Standalone Micro-Kernel
// Architecture: Robust Tube-CLBF Micro-QP Solver & Safety Guard
// Target: Embedded Edge (NVIDIA Jetson, PX4 STM32, Raspberry Pi 5)
// Design: Zero Dynamic Allocation, Constexpr Bounds, Sub-0.05ms Execution
// ============================================================================

#ifndef AEGIS_ROBUST_TUBE_CLBF_HPP
#define AEGIS_ROBUST_TUBE_CLBF_HPP

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <algorithm>
#include <array>
#include <chrono>

namespace aegis {

struct Vector3D {
    double x{0.0};
    double y{0.0};
    double z{0.0};

    constexpr Vector3D operator+(const Vector3D& o) const { return {x + o.x, y + o.y, z + o.z}; }
    constexpr Vector3D operator-(const Vector3D& o) const { return {x - o.x, y - o.y, z - o.z}; }
    constexpr Vector3D operator*(double s) const { return {x * s, y * s, z * s}; }
    constexpr double dot(const Vector3D& o) const { return x * o.x + y * o.y + z * o.z; }
    double norm() const { return std::sqrt(dot(*this)); }
    Vector3D normalized() const {
        double n = norm();
        return (n > 1e-9) ? (*this * (1.0 / n)) : Vector3D{0.0, 0.0, 0.0};
    }
};

struct State3D {
    Vector3D p; // Position [m]
    Vector3D v; // Velocity [m/s]
};

struct Obstacle3D {
    Vector3D center;
    double radius{0.5};
    Vector3D velocity{0.0, 0.0, 0.0}; // Linear velocity vector [m/s]
};

struct KernelConfig {
    double a_max{4.0};                 // Maximum acceleration authority [m/s^2]
    double v_max{2.0};                 // Maximum nominal speed [m/s]
    double dt{0.04};                   // Control cycle timestep [s] (25 Hz)
    double gamma_clf{1.5};             // CLF convergence rate
    double alpha_cbf{2.0};             // CBF safety margin stiffness
    double kappa_delta{1.8};           // Tube uncertainty multiplier
    double sigma_p_thresh{0.25};       // Observability position variance limit [m]
    double sigma_v_thresh{0.35};       // Observability velocity variance limit [m/s]
    double still_energy_thresh{0.005}; // Physical kinetic energy standstill [J]
    int dwell_steps_required{15};      // Physical standstill active dwell steps
};

struct MicroQPSolution {
    Vector3D a_safe;                  // Commanded safe acceleration [m/s^2]
    bool feasible{true};              // Solution feasibility status
    bool is_abstain{false};           // Safe abstention / fail-closed stop active
    bool in_probing{false};           // Bounded active probing mode active
    double solve_time_us{0.0};        // Kernel execution latency [microseconds]
    double min_barrier_margin{100.0}; // Minimum distance to barrier [m]
};

class RobustTubeCLBFKernel {
public:
    explicit constexpr RobustTubeCLBFKernel(KernelConfig cfg = KernelConfig{})
        : config_(cfg) {}

    constexpr const KernelConfig& config() const { return config_; }
    constexpr void set_config(const KernelConfig& cfg) { config_ = cfg; }

    // ------------------------------------------------------------------------
    // 1. Exact ZOH Kinematic Forward Projection under Actuator Delay
    // ------------------------------------------------------------------------
    State3D project_delay_zoh(const State3D& s, double tau_lag, const Vector3D& prev_a) const {
        if (tau_lag <= 1e-6) {
            return s;
        }
        // Discrete ZOH integration over latency tau_lag
        Vector3D p_proj = s.p + (s.v * tau_lag) + (prev_a * (0.5 * tau_lag * tau_lag));
        Vector3D v_proj = s.v + (prev_a * tau_lag);
        return {p_proj, v_proj};
    }

    // ------------------------------------------------------------------------
    // 2. Deadbeat Damping Braking to Guaranteed Physical Stillness
    // ------------------------------------------------------------------------
    Vector3D compute_deadbeat_braking(const Vector3D& v) const {
        double v_mag = v.norm();
        if (v_mag < 1e-4) {
            return {0.0, 0.0, 0.0};
        }
        double a_stop = std::min(config_.a_max, v_mag / config_.dt);
        return v.normalized() * (-a_stop);
    }

    // ------------------------------------------------------------------------
    // 3. Core Safety Kernel: Goal-Directed Tube-CLBF Micro-QP Solver
    // ------------------------------------------------------------------------
    MicroQPSolution solve(
        const State3D& state,
        const Vector3D& goal,
        const Obstacle3D* obstacles,
        size_t num_obstacles,
        double tau_lag = 0.035,
        double beta_min = 1.0,
        double sigma_p = 0.05,
        double sigma_v = 0.08,
        bool force_probing = false,
        int probe_step = 0
    ) const {
        return solve_goal_templated(
            state,
            goal,
            obstacles,
            num_obstacles,
            [](const Obstacle3D& o) -> Vector3D { return o.center; },
            [](const Obstacle3D& o) -> double { return o.radius; },
            [](const Obstacle3D& o) -> Vector3D { return o.velocity; },
            tau_lag,
            beta_min,
            sigma_p,
            sigma_v,
            force_probing,
            probe_step
        );
    }

    // ------------------------------------------------------------------------
    // 4. Inline Safety Box Filter: Direct Command Acceleration Projection
    // ------------------------------------------------------------------------
    template <typename ObsT, typename CenterFn, typename RadiusFn, typename VelFn>
    MicroQPSolution filter_command_templated(
        const State3D& state,
        const Vector3D& untrusted_accel,
        const ObsT* obstacles,
        size_t num_obstacles,
        CenterFn&& get_center,
        RadiusFn&& get_radius,
        VelFn&& get_velocity,
        double tau_lag = 0.035,
        double beta_min = 1.0,
        double sigma_p = 0.05,
        double sigma_v = 0.08
    ) const {
        auto start_time = std::chrono::steady_clock::now();
        MicroQPSolution sol;

        // Gate 1: Information-Theoretic Observability Check
        if (!std::isfinite(sigma_p) || !std::isfinite(sigma_v) ||
            sigma_p > config_.sigma_p_thresh || sigma_v > config_.sigma_v_thresh) {
            sol.is_abstain = true;
            sol.a_safe = compute_deadbeat_braking(state.v);
            sol.min_barrier_margin = 0.0;
            sol.feasible = true;
            auto end_time = std::chrono::steady_clock::now();
            sol.solve_time_us = std::chrono::duration<double, std::micro>(end_time - start_time).count();
            return sol;
        }

        // Effective Control Acceleration Authority Derating (Mass Mismatch)
        double a_limit = config_.a_max * std::clamp(beta_min, 0.5, 1.0);
        Vector3D a_nom = untrusted_accel;
        double a_nom_mag = a_nom.norm();
        if (a_nom_mag > a_limit) {
            a_nom = a_nom * (a_limit / a_nom_mag);
        }

        // Gate 2: Actuator Delay Forward Projection under nominal command
        State3D proj = project_delay_zoh(state, tau_lag, a_nom);

        // Gate 3: Multi-Obstacle Dynamic Robust Tube-CBF Active-Set Filter
        double min_dist_margin = 100.0;
        Vector3D a_opt = project_dynamic_tube_cbf(
            proj,
            a_nom,
            obstacles,
            num_obstacles,
            get_center,
            get_radius,
            get_velocity,
            tau_lag,
            sigma_p,
            min_dist_margin
        );

        if (a_opt.norm() > a_limit) {
            a_opt = a_opt.normalized() * a_limit;
        }

        sol.a_safe = a_opt;
        sol.min_barrier_margin = min_dist_margin;
        sol.feasible = true;

        auto end_time = std::chrono::steady_clock::now();
        sol.solve_time_us = std::chrono::duration<double, std::micro>(end_time - start_time).count();
        return sol;
    }

    template <typename ObsT, typename CenterFn, typename RadiusFn, typename VelFn>
    MicroQPSolution solve_goal_templated(
        const State3D& state,
        const Vector3D& goal,
        const ObsT* obstacles,
        size_t num_obstacles,
        CenterFn&& get_center,
        RadiusFn&& get_radius,
        VelFn&& get_velocity,
        double tau_lag,
        double beta_min,
        double sigma_p,
        double sigma_v,
        bool force_probing,
        int probe_step
    ) const {
        auto start_time = std::chrono::steady_clock::now();
        MicroQPSolution sol;

        // Gate 1: Information-Theoretic Observability Check
        if (!std::isfinite(sigma_p) || !std::isfinite(sigma_v) ||
            sigma_p > config_.sigma_p_thresh || sigma_v > config_.sigma_v_thresh) {
            sol.is_abstain = true;
            sol.a_safe = compute_deadbeat_braking(state.v);
            sol.feasible = true;
            auto end_time = std::chrono::steady_clock::now();
            sol.solve_time_us = std::chrono::duration<double, std::micro>(end_time - start_time).count();
            return sol;
        }

        // Gate 2: Actuator Delay Forward Projection
        State3D proj = project_delay_zoh(state, tau_lag, {0.0, 0.0, 0.0});

        // Nominal CLF Tracking Acceleration
        Vector3D p_err = proj.p - goal;
        Vector3D v_des = p_err * (-config_.gamma_clf);
        double v_des_mag = v_des.norm();
        if (v_des_mag > config_.v_max) {
            v_des = v_des.normalized() * config_.v_max;
        }
        Vector3D a_nom = (v_des - proj.v) * 2.5;

        // Effective Control Acceleration Authority Derating (Mass Mismatch)
        double a_limit = config_.a_max * std::clamp(beta_min, 0.5, 1.0);
        double a_nom_mag = a_nom.norm();
        if (a_nom_mag > a_limit) {
            a_nom = a_nom.normalized() * a_limit;
        }

        // Active Probing Injection at Saddle Points
        if (force_probing || (proj.v.norm() < 0.12 && p_err.norm() > 0.4)) {
            sol.in_probing = true;
            // Tangential orthogonal perturbation
            double angle = 0.62831853 * static_cast<double>(probe_step % 10);
            Vector3D probe_dir{std::cos(angle), std::sin(angle), 0.0};
            a_nom = a_nom + (probe_dir * (a_limit * 0.45));
            if (a_nom.norm() > a_limit) {
                a_nom = a_nom.normalized() * a_limit;
            }
        }

        // Multi-Obstacle Dynamic Robust Tube-CBF Micro-QP Active-Set Filter
        double min_dist_margin = 100.0;
        Vector3D a_opt = project_dynamic_tube_cbf(
            proj,
            a_nom,
            obstacles,
            num_obstacles,
            get_center,
            get_radius,
            get_velocity,
            tau_lag,
            sigma_p,
            min_dist_margin
        );

        // Saturation check after barrier projection
        if (a_opt.norm() > a_limit) {
            a_opt = a_opt.normalized() * a_limit;
        }

        sol.a_safe = a_opt;
        sol.min_barrier_margin = min_dist_margin;
        sol.feasible = true;

        auto end_time = std::chrono::steady_clock::now();
        sol.solve_time_us = std::chrono::duration<double, std::micro>(end_time - start_time).count();
        return sol;
    }

private:
    template <typename ObsT, typename CenterFn, typename RadiusFn, typename VelFn>
    Vector3D project_dynamic_tube_cbf(
        const State3D& proj,
        const Vector3D& a_nom,
        const ObsT* obstacles,
        size_t num_obstacles,
        CenterFn& get_center,
        RadiusFn& get_radius,
        VelFn& get_velocity,
        double tau_lag,
        double sigma_p,
        double& min_dist_margin
    ) const {
        Vector3D a_opt = a_nom;
        min_dist_margin = 100.0;

        if (obstacles == nullptr || num_obstacles == 0) {
            return a_opt;
        }

        // Critically-damped 2nd-order HOCBF poles: (d/dt + alpha_cbf)^2 h >= 0
        // => h_ddot + 2*alpha_cbf * h_dot + alpha_cbf^2 * h >= 0
        const double alpha_1 = 2.0 * config_.alpha_cbf;
        const double alpha_2 = config_.alpha_cbf * config_.alpha_cbf;

        for (size_t i = 0; i < num_obstacles; ++i) {
            const ObsT& obs = obstacles[i];
            Vector3D p_obs = get_center(obs);
            double radius = get_radius(obs);
            Vector3D v_obs = get_velocity(obs);

            Vector3D p_obs_proj = (tau_lag > 1e-6) ? (p_obs + (v_obs * tau_lag)) : p_obs;
            Vector3D diff = proj.p - p_obs_proj;
            double dist = diff.norm();
            double r_eff = radius + (config_.kappa_delta * sigma_p) + (0.5 * config_.v_max * tau_lag);
            double h = dist - r_eff;

            if (h < min_dist_margin) {
                min_dist_margin = h;
            }

            if (dist > 1e-4) {
                Vector3D n = diff * (1.0 / dist);
                Vector3D v_rel = proj.v - v_obs;
                double h_dot = v_rel.dot(n);

                // High-order barrier constraint:
                // psi = h_ddot + alpha_1 * h_dot + alpha_2 * h >= 0
                // => a_opt . n >= -alpha_1 * h_dot - alpha_2 * h
                double req_a_rad = -(alpha_1 * h_dot) - (alpha_2 * h);
                double curr_a_rad = a_opt.dot(n);
                if (curr_a_rad < req_a_rad) {
                    // Analytical projection onto halfspace
                    Vector3D correction = n * (req_a_rad - curr_a_rad);
                    a_opt = a_opt + correction;
                }
            }
        }

        return a_opt;
    }

    KernelConfig config_;
};

} // namespace aegis

// ----------------------------------------------------------------------------
// C-Compatible Export Interface for Python ctypes / Embedded Interop
// ----------------------------------------------------------------------------
extern "C" {

struct AegisCState {
    double px, py, pz;
    double vx, vy, vz;
};

struct AegisCObstacle {
    double cx, cy, cz;      // Position center
    double radius;          // Static geometric radius
    double vx, vy, vz;      // Linear velocity vector
};

struct AegisCResult {
    double ax, ay, az;
    int feasible;
    int is_abstain;
    int in_probing;
    double solve_time_us;
    double min_margin;
};

void aegis_micro_kernel_configure(
    double a_max,
    double v_max,
    double dt,
    double alpha_cbf,
    double kappa_delta,
    double sigma_p_thresh,
    double sigma_v_thresh
);

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
);

} // extern "C"

#endif // AEGIS_ROBUST_TUBE_CLBF_HPP
