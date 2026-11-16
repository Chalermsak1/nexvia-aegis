import ctypes
import math
import os
import subprocess
import sys
import pytest
import numpy as np


class AegisCState(ctypes.Structure):
    _fields_ = [
        ("px", ctypes.c_double), ("py", ctypes.c_double), ("pz", ctypes.c_double),
        ("vx", ctypes.c_double), ("vy", ctypes.c_double), ("vz", ctypes.c_double),
    ]


class AegisCObstacle(ctypes.Structure):
    _fields_ = [
        ("cx", ctypes.c_double), ("cy", ctypes.c_double), ("cz", ctypes.c_double),
        ("radius", ctypes.c_double),
        ("vx", ctypes.c_double), ("vy", ctypes.c_double), ("vz", ctypes.c_double),
    ]


class AegisCResult(ctypes.Structure):
    _fields_ = [
        ("ax", ctypes.c_double), ("ay", ctypes.c_double), ("az", ctypes.c_double),
        ("feasible", ctypes.c_int),
        ("is_abstain", ctypes.c_int),
        ("in_probing", ctypes.c_int),
        ("solve_time_us", ctypes.c_double),
        ("min_margin", ctypes.c_double),
    ]


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB_EXT = "dylib" if sys.platform == "darwin" else "so"
LIB_PATH = os.path.join(REPO_ROOT, "build", f"libaegis_kernel.{LIB_EXT}")


@pytest.fixture(scope="module")
def aegis_c_lib():
    os.makedirs(os.path.dirname(LIB_PATH), exist_ok=True)
    if not os.path.exists(LIB_PATH):
        # Auto-compile if not present
        compiler = "clang++" if sys.platform == "darwin" else "c++"
        subprocess.run(
            [
                compiler,
                "-O3",
                "-std=c++20",
                "-shared",
                "-fPIC",
                f"-I{os.path.join(REPO_ROOT, 'include')}",
                os.path.join(REPO_ROOT, "src", "aegis", "csrc", "aegis_kernel.cpp"),
                "-o",
                LIB_PATH,
            ],
            check=True,
        )

    assert os.path.exists(LIB_PATH), f"Library {LIB_PATH} does not exist"
    lib = ctypes.CDLL(LIB_PATH)
    lib.aegis_micro_kernel_solve.argtypes = [
        AegisCState,
        ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.POINTER(AegisCObstacle), ctypes.c_int,
        ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.c_int, ctypes.c_int,
    ]
    lib.aegis_micro_kernel_solve.restype = AegisCResult
    return lib


def test_cpp_micro_kernel_nominal_tracking(aegis_c_lib):
    """Test nominal goal-directed tracking in open space."""
    state = AegisCState(px=0.0, py=0.0, pz=1.0, vx=0.0, vy=0.0, vz=0.0)
    res = aegis_c_lib.aegis_micro_kernel_solve(
        state,
        2.0, 0.0, 1.0,  # Goal at (2, 0, 1)
        None, 0,        # No obstacles
        0.035, 1.0, 0.05, 0.05, 0, 0,
    )
    assert res.feasible == 1
    assert res.is_abstain == 0
    assert res.ax > 0.5  # Moving toward x = 2.0
    assert res.solve_time_us < 100.0  # Ultra-fast sub-0.1ms


def test_cpp_micro_kernel_barrier_repulsion(aegis_c_lib):
    """Test barrier repulsion when headed toward an obstacle."""
    state = AegisCState(px=0.0, py=0.0, pz=1.0, vx=1.5, vy=0.0, vz=0.0)
    obs = (AegisCObstacle * 1)(AegisCObstacle(cx=1.2, cy=0.0, cz=1.0, radius=0.5))

    res = aegis_c_lib.aegis_micro_kernel_solve(
        state,
        3.0, 0.0, 1.0,
        obs, 1,
        0.035, 1.0, 0.05, 0.05, 0, 0,
    )
    assert res.feasible == 1
    # Must decelerate in x direction to avoid collision
    assert res.ax < 0.0


def test_cpp_micro_kernel_observability_abstain(aegis_c_lib):
    """Test that severe sensor degradation/blackout triggers safe deadbeat abstention."""
    state = AegisCState(px=0.0, py=0.0, pz=1.0, vx=1.0, vy=0.0, vz=0.0)
    # sigma_p = 0.40 > 0.25 threshold
    res = aegis_c_lib.aegis_micro_kernel_solve(
        state,
        3.0, 0.0, 1.0,
        None, 0,
        0.035, 1.0, 0.40, 0.05, 0, 0,
    )
    assert res.is_abstain == 1
    # Braking command opposite to velocity
    assert res.ax < -0.5


def test_cpp_micro_kernel_dynamic_moving_obstacle(aegis_c_lib):
    """Verify collision avoidance against an incoming head-on moving obstacle (v_obs = [-1.0, 0, 0])."""
    # 1. Instantaneous barrier sensitivity: hovering drone facing static vs head-on incoming obstacle
    hover_state = AegisCState(px=0.0, py=0.0, pz=1.0, vx=0.2, vy=0.0, vz=0.0)
    obs_static = (AegisCObstacle * 1)(
        AegisCObstacle(cx=1.05, cy=0.0, cz=1.0, radius=0.45, vx=0.0, vy=0.0, vz=0.0)
    )
    obs_moving = (AegisCObstacle * 1)(
        AegisCObstacle(cx=1.05, cy=0.0, cz=1.0, radius=0.45, vx=-1.0, vy=0.0, vz=0.0)
    )

    res_static = aegis_c_lib.aegis_micro_kernel_solve(
        hover_state, 3.0, 0.0, 1.0, obs_static, 1, 0.035, 1.0, 0.05, 0.05, 0, 0
    )
    res_moving = aegis_c_lib.aegis_micro_kernel_solve(
        hover_state, 3.0, 0.0, 1.0, obs_moving, 1, 0.035, 1.0, 0.05, 0.05, 0, 0
    )

    assert res_moving.feasible == 1
    assert res_moving.ax < res_static.ax, "Incoming obstacle must induce stronger backward repulsion"
    assert res_moving.ax < 0.0
    assert res_moving.solve_time_us < 100.0

    # 2. Closed-loop multi-step rollout against head-on moving obstacle v_obs = [-1.0, 0, 0]
    dt = 0.04
    pos = np.array([0.0, 0.05, 1.0], dtype=np.float64)
    vel = np.array([0.8, 0.0, 0.0], dtype=np.float64)
    obs_pos = np.array([2.5, 0.0, 1.0], dtype=np.float64)
    obs_vel = np.array([-1.0, 0.0, 0.0], dtype=np.float64)
    obs_radius = 0.45

    min_surface_clearance = float("inf")
    for step in range(90):
        c_state = AegisCState(
            px=float(pos[0]), py=float(pos[1]), pz=float(pos[2]),
            vx=float(vel[0]), vy=float(vel[1]), vz=float(vel[2]),
        )
        c_obs = (AegisCObstacle * 1)(
            AegisCObstacle(
                cx=float(obs_pos[0]), cy=float(obs_pos[1]), cz=float(obs_pos[2]),
                radius=obs_radius,
                vx=float(obs_vel[0]), vy=float(obs_vel[1]), vz=float(obs_vel[2]),
            )
        )
        res = aegis_c_lib.aegis_micro_kernel_solve(
            c_state,
            3.5, 0.0, 1.0,
            c_obs, 1,
            0.035, 1.0, 0.05, 0.05, 0, step,
        )
        assert res.feasible == 1
        assert res.solve_time_us < 100.0

        accel = np.array([res.ax, res.ay, res.az], dtype=np.float64)
        pos = pos + vel * dt + 0.5 * accel * (dt * dt)
        vel = vel + accel * dt
        obs_pos = obs_pos + obs_vel * dt

        clearance = float(np.linalg.norm(pos - obs_pos)) - obs_radius
        min_surface_clearance = min(min_surface_clearance, clearance)

    assert min_surface_clearance > 0.0, (
        f"Dynamic moving obstacle collision detected: min_clearance={min_surface_clearance:.4f}m"
    )
