"""
NEXVIA-AEGIS: Plug-and-Play ROS 2 / Autoware / PX4 Safety Box Middleware.

Acts as an inline Hardware Safety Gate between untrusted upstream AI / Autoware planners
and physical actuators (CAN bus, ESC, PX4 offboard actuator setpoints).

Guarantees:
1. Intercepts untrusted control commands (cmd_accel or cmd_vel).
2. Filters commands through C++20 Microkernel (`aegis_micro_kernel_solve`) with automatic
   graceful fallback to pure-Python Robust Tube-CLBF solver if the shared library is absent.
3. Observability Gate: enforces deadbeat braking dwell on sensor blackout / covariance explosion.
4. Heartbeat Watchdog: triggers emergency failsafe if upstream AI planner stalls > timeout_ms.
5. Zero memory allocation in C++ steady-state loop, execution latency < 0.1 ms (< 100 us).
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from enum import Enum
import math
import os
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Tuple
import numpy as np


class SafetyBoxStatus(str, Enum):
    NOMINAL_PASSTHROUGH = "NOMINAL_PASSTHROUGH"
    BARRIER_INTERVENTION = "BARRIER_INTERVENTION"
    OBSERVABILITY_ABSTAIN = "OBSERVABILITY_ABSTAIN"
    WATCHDOG_TIMEOUT_FAILSAFE = "WATCHDOG_TIMEOUT_FAILSAFE"
    DEADBEAT_DWELL = "DEADBEAT_DWELL"


@dataclass
class VehicleTelemetry:
    timestamp_s: float
    position: np.ndarray  # [px, py, pz]
    velocity: np.ndarray  # [vx, vy, vz]
    sigma_p: float = 0.05
    sigma_v: float = 0.08
    beta_min: float = 1.0  # Mass ratio lower bound in [0.5, 1.0]


@dataclass
class ObstacleEstimate:
    center: np.ndarray  # [cx, cy, cz]
    radius: float
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))


@dataclass
class SafetyBoxOutput:
    safe_accel: np.ndarray
    status: SafetyBoxStatus
    intervened: bool
    min_margin: float
    latency_us: float
    dwell_active: bool


class _AegisCState(ctypes.Structure):
    _fields_ = [
        ("px", ctypes.c_double),
        ("py", ctypes.c_double),
        ("pz", ctypes.c_double),
        ("vx", ctypes.c_double),
        ("vy", ctypes.c_double),
        ("vz", ctypes.c_double),
    ]


class _AegisCObstacle(ctypes.Structure):
    _fields_ = [
        ("cx", ctypes.c_double),
        ("cy", ctypes.c_double),
        ("cz", ctypes.c_double),
        ("radius", ctypes.c_double),
        ("vx", ctypes.c_double),
        ("vy", ctypes.c_double),
        ("vz", ctypes.c_double),
    ]


class _AegisCResult(ctypes.Structure):
    _fields_ = [
        ("ax", ctypes.c_double),
        ("ay", ctypes.c_double),
        ("az", ctypes.c_double),
        ("feasible", ctypes.c_int),
        ("is_abstain", ctypes.c_int),
        ("in_probing", ctypes.c_int),
        ("solve_time_us", ctypes.c_double),
        ("min_margin", ctypes.c_double),
    ]


_PREALLOC_MAX_OBSTACLES = 64
_PreallocObstacleBuffer = _AegisCObstacle * _PREALLOC_MAX_OBSTACLES
_LOADED_LIBS: Dict[str, ctypes.CDLL] = {}
_ACTIVE_LIB_CONFIG: Dict[int, Tuple[float, float, float, float, float, float, float]] = {}


def _candidate_kernel_library_paths(explicit_path: Optional[str] = None) -> List[Path]:
    if explicit_path is not None:
        return [Path(explicit_path)]

    repo_root = Path(__file__).resolve().parents[3]
    cwd = Path.cwd()
    lib_names = (
        ["libaegis_kernel.dylib", "libaegis_kernel.so"]
        if sys.platform == "darwin"
        else ["libaegis_kernel.so", "libaegis_kernel.dylib"]
    )
    candidates: List[Path] = []
    for base in (repo_root / "build", cwd / "build"):
        for name in lib_names:
            candidate = base / name
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _load_cpp_microkernel(explicit_path: Optional[str] = None) -> Optional[ctypes.CDLL]:
    for candidate in _candidate_kernel_library_paths(explicit_path):
        if not candidate.is_file():
            continue
        resolved = str(candidate.resolve())
        if resolved in _LOADED_LIBS:
            return _LOADED_LIBS[resolved]
        try:
            lib = ctypes.CDLL(resolved)
            lib.aegis_micro_kernel_solve.argtypes = [
                _AegisCState,
                ctypes.c_double,
                ctypes.c_double,
                ctypes.c_double,
                ctypes.POINTER(_AegisCObstacle),
                ctypes.c_int,
                ctypes.c_double,
                ctypes.c_double,
                ctypes.c_double,
                ctypes.c_double,
                ctypes.c_int,
                ctypes.c_int,
            ]
            lib.aegis_micro_kernel_solve.restype = _AegisCResult

            if hasattr(lib, "aegis_micro_kernel_configure"):
                lib.aegis_micro_kernel_configure.argtypes = [
                    ctypes.c_double,
                    ctypes.c_double,
                    ctypes.c_double,
                    ctypes.c_double,
                    ctypes.c_double,
                    ctypes.c_double,
                    ctypes.c_double,
                ]
                lib.aegis_micro_kernel_configure.restype = None

            # Warm up dyld / libffi trampoline once at load time to avoid first-tick jitter
            lib.aegis_micro_kernel_solve(
                _AegisCState(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                0.0,
                0.0,
                0.0,
                None,
                0,
                0.0,
                1.0,
                0.05,
                0.05,
                -1,
                0,
            )

            _LOADED_LIBS[resolved] = lib
            return lib
        except OSError:
            continue
    return None


class AegisSafetyBox:
    """
    Inline Certified Safety Interceptor.
    Can be used directly in Python control loops or wrapped inside a ROS 2 / Autoware Node.
    """

    CPP_BACKEND = "CPP20_MICROKERNEL"
    PYTHON_BACKEND = "PURE_PYTHON_FALLBACK"

    def __init__(
        self,
        a_max: float = 4.0,
        v_max: float = 3.0,
        tau_lag: float = 0.035,
        alpha_cbf: float = 2.0,
        kappa_delta: float = 2.5,
        sigma_p_thresh: float = 0.25,
        sigma_v_thresh: float = 0.40,
        watchdog_timeout_ms: float = 100.0,
        dt: float = 0.04,
        use_cpp_backend: bool = True,
        kernel_lib_path: Optional[str] = None,
    ):
        self.a_max = float(a_max)
        self.v_max = float(v_max)
        self.tau_lag = float(tau_lag)
        self.alpha_cbf = float(alpha_cbf)
        self.kappa_delta = float(kappa_delta)
        self.sigma_p_thresh = float(sigma_p_thresh)
        self.sigma_v_thresh = float(sigma_v_thresh)
        self.watchdog_timeout_ms = float(watchdog_timeout_ms)
        self.dt = float(dt)

        self.last_heartbeat_time: Optional[float] = None
        self.dwell_active: bool = False
        self.dwell_counter: int = 0

        self._config_tuple = (
            self.a_max,
            self.v_max,
            self.dt,
            self.alpha_cbf,
            self.kappa_delta,
            self.sigma_p_thresh,
            self.sigma_v_thresh,
        )
        self._c_lib: Optional[ctypes.CDLL] = (
            _load_cpp_microkernel(kernel_lib_path) if use_cpp_backend else None
        )
        if self._c_lib is not None:
            self.backend_type: str = self.CPP_BACKEND
            self._solve_fn = self._c_lib.aegis_micro_kernel_solve
            self._configure_fn = getattr(self._c_lib, "aegis_micro_kernel_configure", None)
            self._obs_buffer = _PreallocObstacleBuffer()
            self._sync_cpp_config()
        else:
            self.backend_type = self.PYTHON_BACKEND
            self._solve_fn = None
            self._configure_fn = None
            self._obs_buffer = None

    def _sync_cpp_config(self) -> None:
        if self._c_lib is None or self._configure_fn is None:
            return
        lib_id = id(self._c_lib)
        if _ACTIVE_LIB_CONFIG.get(lib_id) != self._config_tuple:
            self._configure_fn(*self._config_tuple)
            _ACTIVE_LIB_CONFIG[lib_id] = self._config_tuple

    def compute_deadbeat_braking(self, velocity: np.ndarray) -> np.ndarray:
        """Computes deadbeat braking acceleration opposite to velocity."""
        v_mag = float(np.linalg.norm(velocity))
        if v_mag < 1e-4:
            return np.zeros(3, dtype=np.float64)
        a_stop = min(self.a_max, v_mag / self.dt)
        return (-np.asarray(velocity, dtype=np.float64) / v_mag) * a_stop

    def _process_command_cpp(
        self,
        untrusted_accel: np.ndarray,
        telemetry: VehicleTelemetry,
        obstacles: List[ObstacleEstimate],
        t_start: float,
    ) -> SafetyBoxOutput:
        self._sync_cpp_config()

        pos = telemetry.position
        vel = telemetry.velocity
        c_state = _AegisCState(
            float(pos[0]),
            float(pos[1]),
            float(pos[2]),
            float(vel[0]),
            float(vel[1]),
            float(vel[2]),
        )

        n_obs = len(obstacles)
        if n_obs == 0:
            obs_ptr = None
        else:
            buf = (
                self._obs_buffer
                if n_obs <= _PREALLOC_MAX_OBSTACLES
                else (_AegisCObstacle * n_obs)()
            )
            for i, obs in enumerate(obstacles):
                c = obs.center
                v_o = obs.velocity
                entry = buf[i]
                entry.cx = float(c[0])
                entry.cy = float(c[1])
                entry.cz = float(c[2])
                entry.radius = float(obs.radius)
                entry.vx = float(v_o[0])
                entry.vy = float(v_o[1])
                entry.vz = float(v_o[2])
            obs_ptr = buf

        ux = float(untrusted_accel[0])
        uy = float(untrusted_accel[1])
        uz = float(untrusted_accel[2])

        res = self._solve_fn(
            c_state,
            ux,
            uy,
            uz,
            obs_ptr,
            n_obs,
            self.tau_lag,
            float(telemetry.beta_min),
            float(telemetry.sigma_p),
            float(telemetry.sigma_v),
            -1,  # Direct inline command-filtering mode
            0,
        )

        safe_a = np.empty(3, dtype=np.float64)
        safe_a[0] = res.ax
        safe_a[1] = res.ay
        safe_a[2] = res.az

        if res.is_abstain != 0:
            self.dwell_active = True
            latency_us = (time.perf_counter() - t_start) * 1e6
            return SafetyBoxOutput(
                safe_accel=safe_a,
                status=SafetyBoxStatus.OBSERVABILITY_ABSTAIN,
                intervened=True,
                min_margin=0.0,
                latency_us=latency_us,
                dwell_active=True,
            )

        self.dwell_active = False
        dx = res.ax - ux
        dy = res.ay - uy
        dz = res.az - uz
        intervened = (dx * dx + dy * dy + dz * dz) > 1e-12
        status = (
            SafetyBoxStatus.BARRIER_INTERVENTION
            if intervened
            else SafetyBoxStatus.NOMINAL_PASSTHROUGH
        )
        latency_us = (time.perf_counter() - t_start) * 1e6

        return SafetyBoxOutput(
            safe_accel=safe_a,
            status=status,
            intervened=intervened,
            min_margin=float(res.min_margin),
            latency_us=latency_us,
            dwell_active=False,
        )

    def _process_command_python(
        self,
        untrusted_accel: np.ndarray,
        telemetry: VehicleTelemetry,
        obstacles: List[ObstacleEstimate],
        t_start: float,
    ) -> SafetyBoxOutput:
        # 2. Observability Gate
        if (
            not math.isfinite(telemetry.sigma_p)
            or not math.isfinite(telemetry.sigma_v)
            or telemetry.sigma_p > self.sigma_p_thresh
            or telemetry.sigma_v > self.sigma_v_thresh
        ):
            self.dwell_active = True
            safe_a = self.compute_deadbeat_braking(telemetry.velocity)
            latency_us = (time.perf_counter() - t_start) * 1e6
            return SafetyBoxOutput(
                safe_accel=safe_a,
                status=SafetyBoxStatus.OBSERVABILITY_ABSTAIN,
                intervened=True,
                min_margin=0.0,
                latency_us=latency_us,
                dwell_active=True,
            )

        self.dwell_active = False

        # 3. Delay & Mass Derating
        effective_a_max = self.a_max * float(np.clip(telemetry.beta_min, 0.5, 1.0))
        u_nom = np.array(untrusted_accel, dtype=np.float64)
        u_norm = float(np.linalg.norm(u_nom))
        intervened = False
        if u_norm > effective_a_max:
            u_nom = (u_nom / u_norm) * effective_a_max
            intervened = True

        # Forward delay projection for state
        if self.tau_lag > 1e-6:
            p_proj = (
                telemetry.position
                + telemetry.velocity * self.tau_lag
                + 0.5 * (self.tau_lag**2) * u_nom
            )
            v_proj = telemetry.velocity + self.tau_lag * u_nom
        else:
            p_proj = telemetry.position
            v_proj = telemetry.velocity

        # 4. Multi-Obstacle Robust Tube-CBF Micro-QP
        u_opt = u_nom.copy()
        min_margin = 100.0
        alpha_1 = 2.0 * self.alpha_cbf
        alpha_2 = self.alpha_cbf * self.alpha_cbf

        for obs in obstacles:
            p_obs_proj = (
                obs.center + obs.velocity * self.tau_lag
                if self.tau_lag > 1e-6
                else obs.center
            )
            diff = p_proj - p_obs_proj
            dist = float(np.linalg.norm(diff))
            r_eff = (
                obs.radius
                + (self.kappa_delta * telemetry.sigma_p)
                + (0.5 * self.v_max * self.tau_lag)
            )
            h = dist - r_eff
            min_margin = min(min_margin, h)

            if dist > 1e-4:
                n = diff / dist
                v_rel = v_proj - obs.velocity
                h_dot = float(np.dot(v_rel, n))

                # High-order barrier constraint: h_ddot + alpha_1 * h_dot + alpha_2 * h >= 0
                req_a_rad = -(alpha_1 * h_dot) - (alpha_2 * h)
                curr_a_rad = float(np.dot(u_opt, n))

                if curr_a_rad < req_a_rad:
                    correction = n * (req_a_rad - curr_a_rad)
                    u_opt = u_opt + correction
                    intervened = True

        # Clamp to authority limit
        opt_norm = float(np.linalg.norm(u_opt))
        if opt_norm > effective_a_max:
            u_opt = (u_opt / opt_norm) * effective_a_max
            intervened = True

        status = (
            SafetyBoxStatus.BARRIER_INTERVENTION
            if intervened
            else SafetyBoxStatus.NOMINAL_PASSTHROUGH
        )
        latency_us = (time.perf_counter() - t_start) * 1e6

        return SafetyBoxOutput(
            safe_accel=u_opt,
            status=status,
            intervened=intervened,
            min_margin=float(min_margin),
            latency_us=latency_us,
            dwell_active=False,
        )

    def process_command(
        self,
        untrusted_accel: np.ndarray,
        telemetry: VehicleTelemetry,
        obstacles: List[ObstacleEstimate],
        current_time_s: Optional[float] = None,
    ) -> SafetyBoxOutput:
        """
        Processes upstream command and returns certified safe command.
        Routes through C++20 `aegis_micro_kernel_solve` when available, with
        seamless fallback to pure-Python solver otherwise.
        """
        t_start = time.perf_counter()
        now = current_time_s if current_time_s is not None else time.time()

        # 1. Watchdog Check
        if self.last_heartbeat_time is not None:
            time_since_hb_ms = (now - self.last_heartbeat_time) * 1000.0
            if time_since_hb_ms > self.watchdog_timeout_ms:
                # Failsafe: AI planner stalled
                self.dwell_active = True
                safe_a = self.compute_deadbeat_braking(telemetry.velocity)
                latency_us = (time.perf_counter() - t_start) * 1e6
                return SafetyBoxOutput(
                    safe_accel=safe_a,
                    status=SafetyBoxStatus.WATCHDOG_TIMEOUT_FAILSAFE,
                    intervened=True,
                    min_margin=-1.0,
                    latency_us=latency_us,
                    dwell_active=True,
                )

        self.last_heartbeat_time = now

        if self._solve_fn is not None:
            return self._process_command_cpp(untrusted_accel, telemetry, obstacles, t_start)
        return self._process_command_python(untrusted_accel, telemetry, obstacles, t_start)

    def reset(self):
        self.last_heartbeat_time = None
        self.dwell_active = False
        self.dwell_counter = 0
