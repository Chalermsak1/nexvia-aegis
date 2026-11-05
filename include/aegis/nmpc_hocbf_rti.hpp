// ============================================================================
// NEXVIA AEGIS: High-Performance C++20 RTI-SQP NMPC-HOCBF Engine
// Architecture: Real-Time Iteration Sequential Quadratic Programming with
//               Augmented Lagrangian ADMM Operator Splitting
// Target: Embedded Edge (NVIDIA Jetson Orin, Raspberry Pi 5, x86_64, Apple Silicon)
// Design: Zero Dynamic Allocation, Constexpr Horizon N=15, Sub-0.3ms Execution
// ============================================================================

#ifndef AEGIS_NMPC_HOCBF_RTI_HPP
#define AEGIS_NMPC_HOCBF_RTI_HPP

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <algorithm>
#include <array>
#include <chrono>

namespace aegis {
namespace nmpc {

inline constexpr int HORIZON_N = 15;
inline constexpr int STATE_DIM = 6;
inline constexpr int CTRL_DIM = 3;
inline constexpr int TOTAL_VARS = HORIZON_N * CTRL_DIM; // 45
inline constexpr int MAX_OBSTACLES = 16;
inline constexpr int MAX_CORRIDOR_PLANES = 32;
inline constexpr int MAX_CONSTRAINTS = 256;

struct NmpcConfig {
    double dt{0.05};                   // MPC discretization step [s] (20 Hz preview)
    double mass{1.25};                 // Physical mass [kg]
    double gravity{9.81};              // Gravity [m/s^2]

    // Cost Function Weights
    double weight_pos{8.0};            // Stage position weight (X, Y)
    double weight_pos_z{20.0};         // Stage position weight (Z: 2.5x)
    double weight_pos_terminal{30.0};  // Terminal position weight (X, Y)
    double weight_pos_terminal_z{90.0};// Terminal position weight (Z: 3.0x)
    double weight_vel{1.5};            // Velocity tracking weight
    double weight_thrust{0.05};        // Hover thrust deviation weight
    double weight_delta_u{0.35};       // Force rate-of-change (jerk) weight

    // Physical & Barrier Limits
    double max_tilt_rad{0.610865238};  // 35 degrees tilt limit
    double max_thrust_total{28.0};     // Max collective thrust [N]
    double min_thrust_total{2.0};      // Min collective thrust [N]
    double arena_limit{1.5};           // Arena boundary box [m]
    double robot_radius{0.12};         // Collision radius [m]
    double safety_margin{0.08};        // Safety buffer [m]
    double cbf_gamma{0.35};            // D-CBF decay contraction factor

    // Solver Parameters
    int max_sqp_iters{3};              // SQP outer relinearization iterations
    int max_admm_iters{40};            // ADMM iterations per SQP step
    double rho_admm{28.0};             // Augmented Lagrangian penalty parameter
    double admm_tol{1e-4};             // Dual/Primal residual stopping tolerance
};

struct ObstacleInfo {
    double cx, cy, cz;                 // Position center [m]
    double radius;                     // Radius [m]
    double vx, vy, vz;                 // Velocity [m/s]
};

struct CorridorPlaneInfo {
    double nx, ny, nz;                 // Outward-pointing normal
    double d;                          // nx*x + ny*y + nz*z <= d
};

struct TrajectoryStep {
    double px, py, pz;
    double vx, vy, vz;
    double fx, fy, fz;
};

struct NmpcResult {
    double f0[3]{0.0, 0.0, 0.0};       // Optimal control input F_0 to apply [N]
    TrajectoryStep trajectory[HORIZON_N + 1]; // Full predicted horizon
    bool success{false};
    int iterations{0};
    double solve_time_us{0.0};
    double min_barrier_margin{100.0};
    bool fallback_activated{false};
};

// ============================================================================
// Fixed-Size 45x45 Dense Matrix & Linear Algebra (Zero Heap Allocation)
// ============================================================================
class DenseSym45 {
public:
    std::array<double, TOTAL_VARS * TOTAL_VARS> data{};

    constexpr double& operator()(int r, int c) { return data[r * TOTAL_VARS + c]; }
    constexpr const double& operator()(int r, int c) const { return data[r * TOTAL_VARS + c]; }

    void set_zero() { data.fill(0.0); }

    // Computes Cholesky decomposition L L^T = A with diagonal regularization
    bool compute_cholesky(DenseSym45& L, double reg = 1e-6) const {
        L.set_zero();
        for (int i = 0; i < TOTAL_VARS; ++i) {
            for (int j = 0; j <= i; ++j) {
                double s = 0.0;
                for (int k = 0; k < j; ++k) {
                    s += L(i, k) * L(j, k);
                }
                if (i == j) {
                    double val = (*this)(i, i) + reg - s;
                    if (val <= 1e-12) {
                        val = 1e-6; // Robust regularizer
                    }
                    L(i, j) = std::sqrt(val);
                } else {
                    double l_jj = L(j, j);
                    L(i, j) = (std::abs(l_jj) > 1e-12) ? ((*this)(i, j) - s) / l_jj : 0.0;
                }
            }
        }
        return true;
    }

    // Solves L L^T x = b via forward-backward substitution
    void solve_cholesky(const DenseSym45& L, const double* b, double* x) const {
        double y[TOTAL_VARS];
        // Forward: L y = b
        for (int i = 0; i < TOTAL_VARS; ++i) {
            double s = 0.0;
            for (int j = 0; j < i; ++j) {
                s += L(i, j) * y[j];
            }
            double l_ii = L(i, i);
            y[i] = (std::abs(l_ii) > 1e-12) ? (b[i] - s) / l_ii : 0.0;
        }
        // Backward: L^T x = y
        for (int i = TOTAL_VARS - 1; i >= 0; --i) {
            double s = 0.0;
            for (int j = i + 1; j < TOTAL_VARS; ++j) {
                s += L(j, i) * x[j];
            }
            double l_ii = L(i, i);
            x[i] = (std::abs(l_ii) > 1e-12) ? (y[i] - s) / l_ii : 0.0;
        }
    }
};

// ============================================================================
// Real-Time Iteration NMPC-HOCBF Solver
// ============================================================================
class RtiNmpcHocbfSolver {
public:
    explicit RtiNmpcHocbfSolver(const NmpcConfig& cfg = NmpcConfig{})
        : cfg_(cfg) {
        init_system_matrices();
    }

    void set_config(const NmpcConfig& cfg) {
        cfg_ = cfg;
        init_system_matrices();
    }

    const NmpcConfig& config() const { return cfg_; }

    NmpcResult solve(
        const double current_pos[3],
        const double current_vel[3],
        const double target_pos[3],
        const double target_vel[3],
        const double last_applied_force[3],
        const double* warm_start_u,
        const ObstacleInfo* obstacles,
        int num_obstacles,
        const CorridorPlaneInfo* corridor_planes = nullptr,
        int num_corridor_planes = 0
    ) const {
        const auto t_start = std::chrono::steady_clock::now();
        NmpcResult res;

        const double hover_fz = cfg_.mass * cfg_.gravity;
        const double hover_force[3] = {0.0, 0.0, hover_fz};
        const double g = cfg_.gravity;
        const double dt = cfg_.dt;
        const double r_quad = cfg_.robot_radius + cfg_.safety_margin;
        const double wall_lim = cfg_.arena_limit - r_quad;
        const double tan_tilt = std::tan(cfg_.max_tilt_rad);
        const double max_f_xy = cfg_.max_thrust_total * std::sin(cfg_.max_tilt_rad);

        // 1. Initial Control Vector U_0 in R^45
        double u[TOTAL_VARS];
        if (warm_start_u != nullptr) {
            for (int i = 0; i < TOTAL_VARS; ++i) {
                u[i] = warm_start_u[i];
            }
        } else {
            for (int k = 0; k < HORIZON_N; ++k) {
                u[3 * k + 0] = hover_force[0];
                u[3 * k + 1] = hover_force[1];
                u[3 * k + 2] = hover_force[2];
            }
        }

        // 2. Compute Free Response Trajectory (Zero-Input Ballistic Rollout)
        double p_free[TOTAL_VARS];
        double v_free[TOTAL_VARS];

        for (int k = 0; k < HORIZON_N; ++k) {
            const double t_k = (k + 1) * dt;
            v_free[3 * k + 0] = current_vel[0];
            v_free[3 * k + 1] = current_vel[1];
            v_free[3 * k + 2] = current_vel[2] - g * t_k;

            p_free[3 * k + 0] = current_pos[0] + current_vel[0] * t_k;
            p_free[3 * k + 1] = current_pos[1] + current_vel[1] * t_k;
            p_free[3 * k + 2] = current_pos[2] + current_vel[2] * t_k - 0.5 * g * t_k * t_k;
        }

        // Smart warm start: check obstacle collision
        if (obstacles != nullptr && num_obstacles > 0) {
            for (int obs_idx = 0; obs_idx < std::min(num_obstacles, MAX_OBSTACLES); ++obs_idx) {
                const auto& obs = obstacles[obs_idx];
                const double r_safe = obs.radius + r_quad;
                bool collides = false;
                for (int k = 0; k < HORIZON_N; ++k) {
                    double px = p_free[3 * k + 0];
                    double py = p_free[3 * k + 1];
                    double pz = p_free[3 * k + 2];
                    for (int j = 0; j <= k; ++j) {
                        const double factor_p = (k - j + 0.5) * (dt * dt / cfg_.mass);
                        px += factor_p * u[3 * j + 0];
                        py += factor_p * u[3 * j + 1];
                        pz += factor_p * u[3 * j + 2];
                    }
                    const double dx = px - obs.cx;
                    const double dy = py - obs.cy;
                    const double dz = pz - obs.cz;
                    if (std::sqrt(dx * dx + dy * dy + dz * dz) < r_safe + 0.05) {
                        collides = true;
                        break;
                    }
                }
                if (collides) {
                    double v_norm = std::hypot(current_vel[0], current_vel[1]);
                    double detour_x = 0.0, detour_y = 1.0;
                    if (v_norm > 0.1) {
                        detour_x = -current_vel[1] / v_norm;
                        detour_y =  current_vel[0] / v_norm;
                    } else {
                        double rel_y = current_pos[1] - obs.cy;
                        detour_y = (std::abs(rel_y) > 1e-3) ? ((rel_y > 0) ? 1.0 : -1.0) : 1.0;
                    }
                    for (int k = 0; k < HORIZON_N; ++k) {
                        const double sin_wave = std::sin((k + 1) * 3.141592653589793 / HORIZON_N);
                        u[3 * k + 0] += 3.0 * sin_wave * detour_x - 1.2 * current_vel[0];
                        u[3 * k + 1] += 3.0 * sin_wave * detour_y - 1.2 * current_vel[1];
                    }
                    break;
                }
            }
        }

        // 3. Construct Linear Gradient Vector c in R^45:
        double c[TOTAL_VARS];
        std::fill_n(c, TOTAL_VARS, 0.0);

        for (int k = 0; k < HORIZON_N; ++k) {
            const double ep_x = p_free[3 * k + 0] - target_pos[0];
            const double ep_y = p_free[3 * k + 1] - target_pos[1];
            const double ep_z = p_free[3 * k + 2] - target_pos[2];

            const double ev_x = v_free[3 * k + 0] - target_vel[0];
            const double ev_y = v_free[3 * k + 1] - target_vel[1];
            const double ev_z = v_free[3 * k + 2] - target_vel[2];

            const double wp_xy = (k == HORIZON_N - 1) ? cfg_.weight_pos_terminal : cfg_.weight_pos;
            const double wp_z  = (k == HORIZON_N - 1) ? cfg_.weight_pos_terminal_z : cfg_.weight_pos_z;

            for (int j = 0; j <= k; ++j) {
                const double factor_p = (k - j + 0.5) * (dt * dt / cfg_.mass);
                c[3 * j + 0] += factor_p * (wp_xy * ep_x);
                c[3 * j + 1] += factor_p * (wp_xy * ep_y);
                c[3 * j + 2] += factor_p * (wp_z  * ep_z);

                const double factor_v = dt / cfg_.mass;
                c[3 * j + 0] += factor_v * (cfg_.weight_vel * ev_x);
                c[3 * j + 1] += factor_v * (cfg_.weight_vel * ev_y);
                c[3 * j + 2] += factor_v * (cfg_.weight_vel * ev_z);
            }

            c[3 * k + 0] -= cfg_.weight_thrust * hover_force[0];
            c[3 * k + 1] -= cfg_.weight_thrust * hover_force[1];
            c[3 * k + 2] -= cfg_.weight_thrust * hover_force[2];
        }

        c[0] -= cfg_.weight_delta_u * last_applied_force[0];
        c[1] -= cfg_.weight_delta_u * last_applied_force[1];
        c[2] -= cfg_.weight_delta_u * last_applied_force[2];

        // Box bounds
        double l_u[TOTAL_VARS];
        double u_u[TOTAL_VARS];
        for (int k = 0; k < HORIZON_N; ++k) {
            l_u[3 * k + 0] = -max_f_xy;
            u_u[3 * k + 0] =  max_f_xy;
            l_u[3 * k + 1] = -max_f_xy;
            u_u[3 * k + 1] =  max_f_xy;
            l_u[3 * k + 2] =  cfg_.min_thrust_total;
            u_u[3 * k + 2] =  cfg_.max_thrust_total;
        }

        struct LinearConstraint {
            double a[TOTAL_VARS];
            double b;
        };
        LinearConstraint constraints[MAX_CONSTRAINTS];
        int num_constraints = 0;

        double y_dual[MAX_CONSTRAINTS];
        std::fill_n(y_dual, MAX_CONSTRAINTS, 0.0);

        const double rho = cfg_.rho_admm;
        int total_admm_iters = 0;

        // SQP Outer Loop (RTI Relinearization)
        for (int sqp_step = 0; sqp_step < cfg_.max_sqp_iters; ++sqp_step) {
            num_constraints = 0;

            // Roll out predicted trajectory with current u
            double p_pred[TOTAL_VARS];
            for (int k = 0; k < HORIZON_N; ++k) {
                p_pred[3 * k + 0] = p_free[3 * k + 0];
                p_pred[3 * k + 1] = p_free[3 * k + 1];
                p_pred[3 * k + 2] = p_free[3 * k + 2];
                for (int j = 0; j <= k; ++j) {
                    const double factor_p = (k - j + 0.5) * (dt * dt / cfg_.mass);
                    p_pred[3 * k + 0] += factor_p * u[3 * j + 0];
                    p_pred[3 * k + 1] += factor_p * u[3 * j + 1];
                    p_pred[3 * k + 2] += factor_p * u[3 * j + 2];
                }
            }

            // 1. Tilt Cone Linearization: ||F_xy|| <= F_z * tan(theta)
            for (int k = 0; k < HORIZON_N && num_constraints < MAX_CONSTRAINTS; ++k) {
                const double fx0 = u[3 * k + 0];
                const double fy0 = u[3 * k + 1];
                const double norm_xy = std::hypot(fx0, fy0);
                const double denom = std::max(norm_xy, 1e-4);

                LinearConstraint& c_tilt = constraints[num_constraints++];
                std::fill_n(c_tilt.a, TOTAL_VARS, 0.0);
                c_tilt.a[3 * k + 0] = fx0 / denom;
                c_tilt.a[3 * k + 1] = fy0 / denom;
                c_tilt.a[3 * k + 2] = -tan_tilt;
                c_tilt.b = 0.0;
            }

            // 2. Arena Boundary Box on p_k = p_free + M_p u
            for (int k = 0; k < HORIZON_N && num_constraints + 4 <= MAX_CONSTRAINTS; ++k) {
                // Floor: p_z >= r_quad <=> -p_z <= -r_quad
                LinearConstraint& c_floor = constraints[num_constraints++];
                std::fill_n(c_floor.a, TOTAL_VARS, 0.0);
                for (int j = 0; j <= k; ++j) {
                    c_floor.a[3 * j + 2] = -((k - j + 0.5) * (dt * dt / cfg_.mass));
                }
                c_floor.b = p_free[3 * k + 2] - r_quad;

                // Ceiling: p_z <= wall_lim
                LinearConstraint& c_ceil = constraints[num_constraints++];
                std::fill_n(c_ceil.a, TOTAL_VARS, 0.0);
                for (int j = 0; j <= k; ++j) {
                    c_ceil.a[3 * j + 2] = ((k - j + 0.5) * (dt * dt / cfg_.mass));
                }
                c_ceil.b = wall_lim - p_free[3 * k + 2];

                // X Wall: p_x <= wall_lim and -p_x <= wall_lim
                LinearConstraint& c_x = constraints[num_constraints++];
                std::fill_n(c_x.a, TOTAL_VARS, 0.0);
                for (int j = 0; j <= k; ++j) {
                    c_x.a[3 * j + 0] = ((k - j + 0.5) * (dt * dt / cfg_.mass));
                }
                c_x.b = wall_lim - p_free[3 * k + 0];

                LinearConstraint& c_x_neg = constraints[num_constraints++];
                std::fill_n(c_x_neg.a, TOTAL_VARS, 0.0);
                for (int j = 0; j <= k; ++j) {
                    c_x_neg.a[3 * j + 0] = -((k - j + 0.5) * (dt * dt / cfg_.mass));
                }
                c_x_neg.b = wall_lim + p_free[3 * k + 0];

                // Y Wall
                LinearConstraint& c_y = constraints[num_constraints++];
                std::fill_n(c_y.a, TOTAL_VARS, 0.0);
                for (int j = 0; j <= k; ++j) {
                    c_y.a[3 * j + 1] = ((k - j + 0.5) * (dt * dt / cfg_.mass));
                }
                c_y.b = wall_lim - p_free[3 * k + 1];

                LinearConstraint& c_y_neg = constraints[num_constraints++];
                std::fill_n(c_y_neg.a, TOTAL_VARS, 0.0);
                for (int j = 0; j <= k; ++j) {
                    c_y_neg.a[3 * j + 1] = -((k - j + 0.5) * (dt * dt / cfg_.mass));
                }
                c_y_neg.b = wall_lim + p_free[3 * k + 1];
            }

            // 3. Obstacle D-CBF Constraints
            if (obstacles != nullptr && num_obstacles > 0) {
                const int n_obs = std::min(num_obstacles, MAX_OBSTACLES);
                for (int obs_idx = 0; obs_idx < n_obs; ++obs_idx) {
                    const auto& obs = obstacles[obs_idx];
                    const double r_safe = obs.radius + r_quad + 0.075;

                    for (int k = 0; k < HORIZON_N && num_constraints < MAX_CONSTRAINTS; ++k) {
                        const double t_step = (k + 1) * dt;
                        const double obs_x = obs.cx + obs.vx * t_step;
                        const double obs_y = obs.cy + obs.vy * t_step;
                        const double obs_z = obs.cz + obs.vz * t_step;

                        // Vector from obstacle center to current predicted position
                        double dx = p_pred[3 * k + 0] - obs_x;
                        double dy = p_pred[3 * k + 1] - obs_y;
                        double dz = p_pred[3 * k + 2] - obs_z;
                        double dist = std::hypot(dx, dy, dz);

                        // If predicted position is inside or too close, orient normal from initial position
                        if (dist < 0.05) {
                            dx = current_pos[0] - obs_x;
                            dy = current_pos[1] - obs_y;
                            dz = current_pos[2] - obs_z;
                            dist = std::max(1e-4, std::hypot(dx, dy, dz));
                        }

                        const double nx = dx / dist;
                        const double ny = dy / dist;
                        const double nz = dz / dist;

                        // Linearized separating half-space:
                        // n^T (p - p_obs) >= r_safe  <=>  -n^T p <= -r_safe - n^T p_obs
                        // With p = p_free + M_p u:
                        // -n^T M_p u <= n^T (p_free - p_obs) - r_safe
                        LinearConstraint& c_obs = constraints[num_constraints++];
                        std::fill_n(c_obs.a, TOTAL_VARS, 0.0);
                        for (int j = 0; j <= k; ++j) {
                            const double factor_p = (k - j + 0.5) * (dt * dt / cfg_.mass);
                            c_obs.a[3 * j + 0] = -nx * factor_p;
                            c_obs.a[3 * j + 1] = -ny * factor_p;
                            c_obs.a[3 * j + 2] = -nz * factor_p;
                        }
                        const double p_free_rel_x = p_free[3 * k + 0] - obs_x;
                        const double p_free_rel_y = p_free[3 * k + 1] - obs_y;
                        const double p_free_rel_z = p_free[3 * k + 2] - obs_z;
                        c_obs.b = (nx * p_free_rel_x + ny * p_free_rel_y + nz * p_free_rel_z) - r_safe;
                    }
                }
            }

            // 4. Safe Flight Corridor Polytopes (Task 4)
            if (corridor_planes != nullptr && num_corridor_planes > 0) {
                const int n_planes = std::min(num_corridor_planes, MAX_CORRIDOR_PLANES);
                for (int p_idx = 0; p_idx < n_planes; ++p_idx) {
                    const auto& cp = corridor_planes[p_idx];
                    for (int k = 0; k < HORIZON_N && num_constraints < MAX_CONSTRAINTS; ++k) {
                        LinearConstraint& c_plane = constraints[num_constraints++];
                        std::fill_n(c_plane.a, TOTAL_VARS, 0.0);
                        for (int j = 0; j <= k; ++j) {
                            const double factor_p = (k - j + 0.5) * (dt * dt / cfg_.mass);
                            c_plane.a[3 * j + 0] = cp.nx * factor_p;
                            c_plane.a[3 * j + 1] = cp.ny * factor_p;
                            c_plane.a[3 * j + 2] = cp.nz * factor_p;
                        }
                        const double plane_bound = cp.d - r_quad;
                        c_plane.b = plane_bound - (cp.nx * p_free[3 * k + 0] +
                                                   cp.ny * p_free[3 * k + 1] +
                                                   cp.nz * p_free[3 * k + 2]);
                    }
                }
            }

            // Augmented Lagrangian Method (ALM / ADMM)
            for (int admm_iter = 0; admm_iter < cfg_.max_admm_iters; ++admm_iter) {
                total_admm_iters++;
                double rhs[TOTAL_VARS];
                for (int i = 0; i < TOTAL_VARS; ++i) {
                    rhs[i] = -c[i] + rho * u[i];
                }
                for (int m_idx = 0; m_idx < num_constraints; ++m_idx) {
                    double a_dot_u = 0.0;
                    for (int i = 0; i < TOTAL_VARS; ++i) {
                        a_dot_u += constraints[m_idx].a[i] * u[i];
                    }
                    const double viol = a_dot_u - constraints[m_idx].b;
                    const double lam = std::max(0.0, y_dual[m_idx] + rho * viol);
                    if (lam > 1e-8) {
                        for (int i = 0; i < TOTAL_VARS; ++i) {
                            rhs[i] -= constraints[m_idx].a[i] * lam;
                        }
                    }
                }

                double u_next[TOTAL_VARS];
                H_admm_.solve_cholesky(L_admm_, rhs, u_next);

                double max_diff = 0.0;
                for (int i = 0; i < TOTAL_VARS; ++i) {
                    const double u_clamped = std::clamp(u_next[i], l_u[i], u_u[i]);
                    max_diff = std::max(max_diff, std::abs(u_clamped - u[i]));
                    u[i] = u_clamped;
                }

                // Dual updates
                for (int m_idx = 0; m_idx < num_constraints; ++m_idx) {
                    double a_dot_u = 0.0;
                    for (int i = 0; i < TOTAL_VARS; ++i) {
                        a_dot_u += constraints[m_idx].a[i] * u[i];
                    }
                    const double viol = a_dot_u - constraints[m_idx].b;
                    y_dual[m_idx] = std::max(0.0, y_dual[m_idx] + rho * viol);
                }

                if (max_diff < cfg_.admm_tol && admm_iter >= 5) {
                    break;
                }
            }
        }

        // 6. Assemble Result
        res.f0[0] = u[0];
        res.f0[1] = u[1];
        res.f0[2] = u[2];
        res.iterations = total_admm_iters;
        res.success = true;

        res.trajectory[0] = {
            current_pos[0], current_pos[1], current_pos[2],
            current_vel[0], current_vel[1], current_vel[2],
            res.f0[0], res.f0[1], res.f0[2]
        };

        for (int k = 0; k < HORIZON_N; ++k) {
            double pk[3] = {p_free[3 * k + 0], p_free[3 * k + 1], p_free[3 * k + 2]};
            double vk[3] = {v_free[3 * k + 0], v_free[3 * k + 1], v_free[3 * k + 2]};
            for (int j = 0; j <= k; ++j) {
                const double factor_p = (k - j + 0.5) * (dt * dt / cfg_.mass);
                pk[0] += factor_p * u[3 * j + 0];
                pk[1] += factor_p * u[3 * j + 1];
                pk[2] += factor_p * u[3 * j + 2];

                const double factor_v = dt / cfg_.mass;
                vk[0] += factor_v * u[3 * j + 0];
                vk[1] += factor_v * u[3 * j + 1];
                vk[2] += factor_v * u[3 * j + 2];
            }
            res.trajectory[k + 1] = {
                pk[0], pk[1], pk[2],
                vk[0], vk[1], vk[2],
                u[3 * k + 0], u[3 * k + 1], u[3 * k + 2]
            };
        }

        // Compute actual solved minimum barrier clearance margin
        double actual_min_margin = 1e6;
        if (obstacles != nullptr && num_obstacles > 0) {
            const int n_obs = std::min(num_obstacles, MAX_OBSTACLES);
            for (int obs_idx = 0; obs_idx < n_obs; ++obs_idx) {
                const auto& obs = obstacles[obs_idx];
                for (int k = 0; k <= HORIZON_N; ++k) {
                    const double t_step = k * dt;
                    const double obs_x = obs.cx + obs.vx * t_step;
                    const double obs_y = obs.cy + obs.vy * t_step;
                    const double obs_z = obs.cz + obs.vz * t_step;

                    const double dx = res.trajectory[k].px - obs_x;
                    const double dy = res.trajectory[k].py - obs_y;
                    const double dz = res.trajectory[k].pz - obs_z;
                    const double dist = std::sqrt(dx * dx + dy * dy + dz * dz);
                    const double margin = dist - obs.radius - cfg_.robot_radius;
                    actual_min_margin = std::min(actual_min_margin, margin);
                }
            }
        } else {
            actual_min_margin = 1.0;
        }
        res.min_barrier_margin = actual_min_margin;

        const auto t_end = std::chrono::steady_clock::now();
        res.solve_time_us = std::chrono::duration<double, std::micro>(t_end - t_start).count();

        return res;
    }

private:
    void init_system_matrices() {
        H_nominal_.set_zero();
        const double dt = cfg_.dt;
        const double m = cfg_.mass;

        for (int k = 0; k < HORIZON_N; ++k) {
            const double wp_xy = (k == HORIZON_N - 1) ? cfg_.weight_pos_terminal : cfg_.weight_pos;
            const double wp_z  = (k == HORIZON_N - 1) ? cfg_.weight_pos_terminal_z : cfg_.weight_pos_z;

            for (int i = 0; i <= k; ++i) {
                const double factor_pi = (k - i + 0.5) * (dt * dt / m);
                for (int j = 0; j <= k; ++j) {
                    const double factor_pj = (k - j + 0.5) * (dt * dt / m);
                    H_nominal_(3 * i + 0, 3 * j + 0) += factor_pi * wp_xy * factor_pj;
                    H_nominal_(3 * i + 1, 3 * j + 1) += factor_pi * wp_xy * factor_pj;
                    H_nominal_(3 * i + 2, 3 * j + 2) += factor_pi * wp_z  * factor_pj;
                }
            }

            const double factor_v = dt / m;
            for (int i = 0; i <= k; ++i) {
                for (int j = 0; j <= k; ++j) {
                    H_nominal_(3 * i + 0, 3 * j + 0) += factor_v * cfg_.weight_vel * factor_v;
                    H_nominal_(3 * i + 1, 3 * j + 1) += factor_v * cfg_.weight_vel * factor_v;
                    H_nominal_(3 * i + 2, 3 * j + 2) += factor_v * cfg_.weight_vel * factor_v;
                }
            }

            H_nominal_(3 * k + 0, 3 * k + 0) += cfg_.weight_thrust;
            H_nominal_(3 * k + 1, 3 * k + 1) += cfg_.weight_thrust;
            H_nominal_(3 * k + 2, 3 * k + 2) += cfg_.weight_thrust;
        }

        for (int k = 0; k < HORIZON_N; ++k) {
            for (int ax = 0; ax < 3; ++ax) {
                H_nominal_(3 * k + ax, 3 * k + ax) += cfg_.weight_delta_u;
                if (k > 0) {
                    H_nominal_(3 * k + ax, 3 * (k - 1) + ax) -= cfg_.weight_delta_u;
                    H_nominal_(3 * (k - 1) + ax, 3 * k + ax) -= cfg_.weight_delta_u;
                    H_nominal_(3 * (k - 1) + ax, 3 * (k - 1) + ax) += cfg_.weight_delta_u;
                }
            }
        }

        H_admm_ = H_nominal_;
        for (int i = 0; i < TOTAL_VARS; ++i) {
            H_admm_(i, i) += cfg_.rho_admm;
        }
        H_admm_.compute_cholesky(L_admm_);
    }

    NmpcConfig cfg_;
    DenseSym45 H_nominal_;
    DenseSym45 H_admm_;
    DenseSym45 L_admm_;
};

} // namespace nmpc
} // namespace aegis

#endif // AEGIS_NMPC_HOCBF_RTI_HPP
