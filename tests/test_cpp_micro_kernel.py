import ctypes
import os
import pytest
import numpy as np

class AegisCState(ctypes.Structure):
    _fields_ = [
        ("px", ctypes.c_double), ("py", ctypes.c_double), ("pz", ctypes.c_double),
        ("vx", ctypes.c_double), ("vy", ctypes.c_double), ("vz", ctypes.c_double)
    ]

class AegisCObstacle(ctypes.Structure):
    _fields_ = [
        ("cx", ctypes.c_double), ("cy", ctypes.c_double), ("cz", ctypes.c_double),
        ("radius", ctypes.c_double)
    ]

class AegisCResult(ctypes.Structure):
    _fields_ = [
        ("ax", ctypes.c_double), ("ay", ctypes.c_double), ("az", ctypes.c_double),
        ("feasible", ctypes.c_int),
        ("is_abstain", ctypes.c_int),
        ("in_probing", ctypes.c_int),
        ("solve_time_us", ctypes.c_double),
        ("min_margin", ctypes.c_double)
    ]

LIB_PATH = os.path.join(os.path.dirname(__file__), "..", "build", "libaegis_kernel.dylib")

@pytest.fixture(scope="module")
def aegis_c_lib():
    if not os.path.exists(LIB_PATH):
        # Auto-compile if not present
        cmd = f"clang++ -O3 -std=c++20 -shared -fPIC -Iinclude src/aegis/csrc/aegis_kernel.cpp -o {LIB_PATH}"
        os.system(cmd)
    
    assert os.path.exists(LIB_PATH), f"Library {LIB_PATH} does not exist"
    lib = ctypes.CDLL(LIB_PATH)
    lib.aegis_micro_kernel_solve.argtypes = [
        AegisCState,
        ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.POINTER(AegisCObstacle), ctypes.c_int,
        ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ctypes.c_int, ctypes.c_int
    ]
    lib.aegis_micro_kernel_solve.restype = AegisCResult
    return lib

def test_cpp_micro_kernel_nominal_tracking(aegis_c_lib):
    """Test nominal goal-directed tracking in open space."""
    state = AegisCState(px=0.0, py=0.0, pz=1.0, vx=0.0, vy=0.0, vz=0.0)
    res = aegis_c_lib.aegis_micro_kernel_solve(
        state,
        2.0, 0.0, 1.0, # Goal at (2, 0, 1)
        None, 0,       # No obstacles
        0.035, 1.0, 0.05, 0.05, 0, 0
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
        0.035, 1.0, 0.05, 0.05, 0, 0
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
        0.035, 1.0, 0.40, 0.05, 0, 0
    )
    assert res.is_abstain == 1
    # Braking command opposite to velocity
    assert res.ax < -0.5
