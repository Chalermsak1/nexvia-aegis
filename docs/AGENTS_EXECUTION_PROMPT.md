# NEXVIA-AEGIS: Autonomous Engineering Directive for Agent Team
## High-Performance Embedded Safety Core, Dynamic Obstacle Extension & 6-DOF Flight Bridge

```yaml
Mission: Advance NEXVIA-AEGIS from TRL 4 (Lab Verification) toward TRL 5/6 (Sim2Real Flight Readiness)
Repository: Chalermsak1/nexvia-aegis
Baseline: Commit 3f33d01 | 884 Tests Passing (100%)
Primary Governance: GATE_B_NOT_AUTHORIZED (Strict Holdout Isolation - Do NOT sign Gate B)
Target Architecture: C++20 Header-Only Microkernel + ROS 2 / Autoware / PX4 Offboard Bridge
```

---

### EXECUTIVE INSTRUCTION FOR THE AGENT TEAM

Execute the next engineering development phase across 4 concrete pillars. Ensure zero regression across all existing 884 unit and system tests, maintain zero dynamic memory allocation in the steady-state control loop, and compile all shared libraries for ARM64 / Apple Silicon / Linux x86_64.

---

### PILLAR 1: C++20 Microkernel Acceleration Backend in `AegisSafetyBox`

**Context:**  
We have a compiled standalone C++20 microkernel at `build/libaegis_kernel.dylib` (and `.so` on Linux), running at `< 0.04 ms` solve time with zero heap allocation. However, `src/aegis/bridge/aegis_safety_box.py` currently computes the barrier projection in pure Python.

**Deliverables:**
1. Update `src/aegis/bridge/aegis_safety_box.py`:
   - Implement automatic runtime detection and dynamic loading (`ctypes.CDLL`) of `build/libaegis_kernel.dylib` (macOS) or `build/libaegis_kernel.so` (Linux/Jetson).
   - Route `process_command()` through `aegis_micro_kernel_solve()` when the library is present.
   - Maintain seamless, graceful fallback to the pure-Python solver if the compiled shared library is not found.
   - Expose an attribute `box.backend_type` returning `"CPP20_MICROKERNEL"` or `"PURE_PYTHON_FALLBACK"`.
2. Add comprehensive unit tests in `tests/test_safety_box_bridge.py`:
   - Test both backends produce consistent numerical acceleration outputs ($\Delta < 10^{-3}$).
   - Benchmark execution time to guarantee `< 100 \mu\text{s}` for the C++ backend.

---

### PILLAR 2: Dynamic Moving Obstacle Avoidance in C++ Microkernel & Python Interface

**Context:**  
Currently, `include/aegis/robust_tube_clbf.hpp` and `AegisCObstacle` only account for static obstacle centers $(cx, cy, cz)$. Real-world industrial environments contain moving threats (other UAVs in a swarm, dynamic cranes, ground vehicles, pedestrians).

**Deliverables:**
1. In `include/aegis/robust_tube_clbf.hpp`:
   - Extend `struct Obstacle3D` and `struct AegisCObstacle`:
     ```cpp
     struct AegisCObstacle {
         double cx, cy, cz;      // Position center
         double radius;         // Static geometric radius
         double vx, vy, vz;      // Linear velocity vector
     };
     ```
   - In `RobustTubeCLBFKernel::solve()`, compute the true relative velocity:
     $$\mathbf{v}_{\text{rel}} = \mathbf{v}_{\text{proj}} - \mathbf{v}_{\text{obs}}$$
     $$\dot{h} = \mathbf{v}_{\text{rel}} \cdot \mathbf{n}, \quad \text{where } \mathbf{n} = \frac{\mathbf{p}_{\text{proj}} - \mathbf{p}_{\text{obs}}}{\|\mathbf{p}_{\text{proj}} - \mathbf{p}_{\text{obs}}\|}$$
   - High-order barrier condition becomes:
     $$\psi = \ddot{h} + \alpha_1 \dot{h} + \alpha_2 h \ge 0 \implies \mathbf{a}_{\text{opt}} \cdot \mathbf{n} \ge - \alpha_1 \dot{h} - \alpha_2 h$$
2. In `src/aegis/csrc/aegis_kernel.cpp`:
   - Pass obstacle velocities through the C-ABI function `aegis_micro_kernel_solve`.
3. Recompile `build/libaegis_kernel.dylib` (`clang++ -O3 -std=c++20 -shared -fPIC -Iinclude src/aegis/csrc/aegis_kernel.cpp -o build/libaegis_kernel.dylib`).
4. Update `tests/test_cpp_micro_kernel.py`:
   - Add test case `test_cpp_micro_kernel_dynamic_moving_obstacle()` verifying collision avoidance against an incoming head-on moving obstacle ($\mathbf{v}_{\text{obs}} = [-1.0, 0, 0]$).

---

### PILLAR 3: SE(3) Differential Flatness Converter for Quadrotors (`quadrotor_flatness.py`)

**Context:**  
The safety microkernel outputs a 3D certified acceleration vector $\mathbf{a}_{\text{safe}} \in \mathbb{R}^3$. However, real quadrotors are underactuated rigid bodies in $\text{SE}(3)$ that cannot generate direct lateral force without tilting (roll $\phi$, pitch $\theta$). We need an exact differential flatness mapping to attitude and collective thrust setpoints for Pixhawk / PX4 Offboard control.

**Deliverables:**
1. Create `src/aegis/bridge/quadrotor_flatness.py`:
   - Class `QuadrotorFlatnessConverter`:
     - Inputs: $\mathbf{a}_{\text{safe}} \in \mathbb{R}^3$, desired heading $\psi_{\text{des}}$, vehicle mass $m$, gravitational acceleration $\mathbf{g} = [0, 0, -9.81]^T$, max allowable tilt angle $\theta_{\max} = 35^\circ$.
     - Computes:
       - Apparent acceleration vector: $\mathbf{a}_{\text{app}} = \mathbf{a}_{\text{safe}} - \mathbf{g}$
       - Collective rotor thrust: $T = m \|\mathbf{a}_{\text{app}}\|$
       - Normalized body $z$-axis: $\mathbf{z}_B = \frac{\mathbf{a}_{\text{app}}}{\|\mathbf{a}_{\text{app}}\|}$
       - Intermediate vector: $\mathbf{x}_C = [\cos\psi_{\text{des}}, \sin\psi_{\text{des}}, 0]^T$
       - Body $y$-axis: $\mathbf{y}_B = \frac{\mathbf{z}_B \times \mathbf{x}_C}{\|\mathbf{z}_B \times \mathbf{x}_C\|}$
       - Body $x$-axis: $\mathbf{x}_B = \mathbf{y}_B \times \mathbf{z}_B$
       - Rotation matrix $R_{\text{des}} = [\mathbf{x}_B, \mathbf{y}_B, \mathbf{z}_B] \in \text{SO}(3)$
       - Unit quaternion $\mathbf{q}_{\text{des}} = [w, x, y, z]$
       - Euler angles: Roll $\phi_{\text{des}}$, Pitch $\theta_{\text{des}}$, Yaw $\psi_{\text{des}}$
     - Enforces tilt angle clamping so tilt cannot exceed $\theta_{\max}$ (maintaining aerodynamic stability).
2. Create unit tests in `tests/test_quadrotor_flatness.py`:
   - Hover test: $\mathbf{a}_{\text{safe}} = [0, 0, 0] \implies \phi = 0^\circ, \theta = 0^\circ, T = mg$.
   - Forward acceleration: $\mathbf{a}_{\text{safe}} = [2.0, 0, 0] \implies$ pure pitch tilt forward.
   - Lateral acceleration: $\mathbf{a}_{\text{safe}} = [0, 2.0, 0] \implies$ pure roll tilt.
   - Max tilt angle clamping test: extreme acceleration $\mathbf{a}_{\text{safe}} = [20.0, 0, 0]$ clamped to $\le 35^\circ$.

---

### PILLAR 4: PX4 MAVLink SITL Bridge (`pixhawk_mavlink_bridge.py`)

**Context:**  
To test in software-in-the-loop (SITL) with PX4 and QGroundControl before physical flight on the Pixhawk 6X, we need a lightweight POSIX MAVLink socket bridge.

**Deliverables:**
1. Create `src/aegis/bridge/pixhawk_mavlink_bridge.py`:
   - Class `PX4MavlinkBridge`:
     - Configurable UDP endpoint (default `127.0.0.1:14540` / `14550` for PX4 SITL).
     - Decodes `HEARTBEAT` and `LOCAL_POSITION_NED` / `ODOMETRY` messages.
     - Feeds telemetry into `AegisSafetyBox`.
     - Translates certified safe command through `QuadrotorFlatnessConverter`.
     - Formats outbound `SET_ATTITUDE_TARGET` or `SET_POSITION_TARGET_LOCAL_NED` MAVLink frames.
     - Implements autonomous fail-safe disconnect detector (> 100 ms heartbeat timeout).
2. Create unit tests in `tests/test_pixhawk_mavlink_bridge.py` using mock UDP sockets.

---

### ACCEPTANCE CRITERIA & VERIFICATION COMMANDS

```bash
# 1. Compile C++ Microkernel shared library
clang++ -O3 -std=c++20 -shared -fPIC -Iinclude src/aegis/csrc/aegis_kernel.cpp -o build/libaegis_kernel.dylib

# 2. Run new feature test suite
PYTHONPATH=.:src uv run pytest tests/test_cpp_micro_kernel.py tests/test_safety_box_bridge.py tests/test_quadrotor_flatness.py tests/test_pixhawk_mavlink_bridge.py -v

# 3. Full repository regression check (Must be 100% passing across all 884+ tests)
PYTHONPATH=.:src uv run pytest -q

# 4. Check git status and commit
git status
```

---

### STRICT BOUNDARIES & CONSTRAINTS

1. **HOLDEN REPOSITORY INTEGRITY:** Do NOT modify holdout evaluation datasets or sign Gate B ticket (`GATE_B_NOT_AUTHORIZED` must remain preserved).
2. **ZERO MEMORY ALLOCATION:** No dynamic heap allocation in the C++ inner solve loop.
3. **FAILSAFE COMPLIANCE:** Always maintain deadbeat braking fallback whenever observability threshold $\sigma_p > 0.25\text{ m}$ is violated.
