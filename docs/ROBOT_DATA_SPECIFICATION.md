# NEXVIA-AEGIS: เอกสารข้อกำหนดข้อมูลของหุ่นยนต์ (Robot Data Specification & Data Dictionary)

เอกสารนี้ระบุรายละเอียดโครงสร้างข้อมูลทั้งหมดที่ระบบหุ่นยนต์โดรน (6-DOF Quadrotor) และระบบฝูงบิน (Multi-Agent Swarm) ในโครงการ **NEXVIA-AEGIS** นำเข้ามาประมวลผล เพื่อใช้เป็นเอกสารอ้างอิงกลางสำหรับการพัฒนาฮาร์ดแวร์ ซอฟต์แวร์ และโมเดล AI

---

## 1. ผังการไหลของข้อมูลภาพรวม (System Data Flow)

```
[Sensors: IMU, RTK-GPS, Camera, LiDAR]
                 │
                 ▼
     [State Estimation & Perception]
     ├─ Robot State (p, v, R, omega)
     ├─ Sensor Uncertainty (sigma_p, sigma_v, M_t)
     └─ Obstacle & Corridor (ESDF, Polytopes)
                 │
                 ├───► [Byzantine Swarm Consensus (BRMC)]
                 │         (แชร์ข้อมูลระหว่างโดรนเพื่อนในฝูง)
                 │
                 ├───► [Safe RL Policy (Actor-Critic)]
                 │         (แปลงเป็น Observation Vector 20 มิติ)
                 │
                 ▼
     [High-Speed NMPC-HOCBF C++20 Core]
                 │  (คำนวณแรงขับที่ปลอดภัย F_safe)
                 ▼
        [Actuators / Motors]
```

---

## 2. พจนานุกรมข้อมูลหลัก (Core Data Dictionary)

| ตัวแปร (Variable) | ชนิดและมิติข้อมูล (Type & Shape) | หน่วย (Unit) | แหล่งที่มา (Source) | โมดูลที่นำไปใช้ (Consumer) | เหตุผลทางฟิสิกส์และความปลอดภัย (Why Needed) |
|---|---|---|---|---|---|
| `pos` ($\mathbf{p}$) | `float64[3]` | เมตร ($m$) | GPS / UWB / VIO | NMPC, CBF, RL | ระบุพิกัดในโลก ($x, y, z$) เพื่อนำทางและวัดระยะถึงสิ่งกีดขวาง |
| `vel` ($\mathbf{v}$) | `float64[3]` | $m/s$ | EKF / Optical Flow | NMPC, CBF, RL | ประเมินพลังงานจลน์ คำนวณระยะเบรกหยุดนิ่ง (Deadbeat Braking) |
| `rot` ($R$) / `quat` ($\mathbf{q}$) | `float64[3,3]` / `float64[4]` | ไร้หน่วย | IMU / AHRS | SE(3) Controller | คำนวณเวกเตอร์แกน $Z$ ของลำตัว เพื่อคุมทิศทางแรงยก |
| `omega` ($\boldsymbol{\omega}$) | `float64[3]` | $rad/s$ | Gyroscope (IMU) | Inner Loop, RL | ควบคุมความเร็วการหมุน ป้องกันการหมุนควงสว่าน (Instability) |
| `tilt_angle` ($\theta$) | `float64` | เรเดียน / องศา | คำนวณจาก $R$ | NMPC, HOCBF | จำกัดมุมเอียงไม่เกิน 35° เพื่อไม่ให้แรงยกในแนวดิ่งสูญเสียจนตก |
| `sigma_p`, `sigma_v` | `float64` | $m$, $m/s$ | EKF Covariance | Robust Tube-CBF | ขยายรัศมีเกราะกันชนตามความเบลอของเซนเซอร์ ($\kappa_\delta \sigma$) |
| `martingale_wealth` ($M_t$) | `float64` | ไร้หน่วย ($\ge 0$) | Ville e-Process | Observability Gate | ตรวจจับการถูกหลอกพิกัด (Sensor Spoofing) ถ้าเกินค่าจำกัดจะตัดเบรกฉุกเฉิน |
| `obs_pos` ($\mathbf{c}_{\text{obs}}$) | `float64[3]` | $m$ | Depth Cam / LiDAR | NMPC, HOCBF | จุดศูนย์กลางสิ่งกีดขวาง เพื่อสร้างระนาบหลบหลีก |
| `obs_radius` ($r_{\text{obs}}$) | `float64` | $m$ | Object Tracker | NMPC, HOCBF | ขนาดของสิ่งกีดขวาง กำหนดขอบเขตพื้นที่ห้ามเข้า |
| `obs_vel` ($\mathbf{v}_{\text{obs}}$) | `float64[3]` | $m/s$ | Kalman Filter | Dynamic CBF | ความเร็วสิ่งกีดขวาง เพื่อให้โดรนหลบวัตถุที่พุ่งเข้ามาทัน |
| `point_cloud` | `float64[N, 3]` | $m$ | 3D LiDAR / Depth | Local 3D ESDF | กลุ่มจุดผิวสัมผัส เพื่อสร้างระยะห่างแบบกริดสำหรับช่องแคบ |
| `corridor_planes` | `list[(n, d)]` | $n$: เวกเตอร์, $d$: $m$ | Convex Decomp | Polytope Barrier | ระนาบผนัง $\mathbf{n}^\top \mathbf{p} \le d$ สำหรับบินผ่านประตูแคบ/มุมตึก |
| `battery_soc` | `float64` | ช่วง $[0.0, 1.0]$ | Battery BMS | Safe RL Policy | ระดับพลังงานคงเหลือ ป้องกันแบตเตอรี่หมดกลางอากาศ |

---

## 3. รายละเอียดเชิงลึกรายหมวดหมู่

### 3.1 ข้อมูลสภาพทางกายภาพของตัวโดรน (Kinematics & Dynamics)
* **Underactuated Constraints:** โดรนมีมอเตอร์ขับเคลื่อน 4 ตัว แต่มีอิสระการเคลื่อนที่ 6 ทิศทาง ($x, y, z, \text{roll}, \text{pitch}, \text{yaw}$)
* การจะเปลี่ยนทิศทางในแนวราบ **จำเป็นต้องเอียงตัว** ข้อมูลความเร็วเชิงมุม ($\boldsymbol{\omega}$) และมุมเอียง ($\theta$) จึงเป็นตัวตัดสินว่าโดรนจะทรงตัวอยู่ได้หรือไม่

### 3.2 ข้อมูลความเชื่อถือได้และการป้องกันการโจมตี (Sensor Integrity & Epistemic Safety)
* **ปัญหาโลกจริง:** เซนเซอร์หลุด สัญญาณ GPS สะท้อน (Multipath) หรือโดนคลื่นรบกวน
* **ข้อมูลที่ใช้:**
  1. `sigma_p`, `sigma_v`: ค่าเบี่ยงเบนมาตรฐานของตำแหน่งและความเร็ว
  2. `martingale_wealth`: ค่าวัดทางสถิติ Ville Martingale ตามสมการ:
     $$\mathbb{P}_{\mathcal{H}_0}\left(\exists t \ge 1 : M_t \ge \frac{1}{\alpha}\right) \le \alpha$$
     ถ้าค่า $M_t \ge 1/\alpha$ แสดงว่าเกิดความผิดปกติในระบบเซนเซอร์แน่นอน 100% หุ่นยนต์จะหยุดการบินทันที (Fail-Closed Stop)

### 3.3 ข้อมูลสิ่งกีดขวางและช่องทางบิน (Perception & Safe Flight Corridors)
* **ทรงกลม vs ช่องทางจริง:**
  * ทรงกลมธรรมดา: เหมาะกับเสาเดี่ยว หรือโดรนตัวอื่น
  * Convex Polytope ($\mathbf{a}_k^\top \mathbf{x} \le b_k$): สร้างจากพอยต์คลาวด์และฟิลด์ ESDF จำเป็นมากสำหรับ **"บินลอดประตู หน้าต่าง หรือซอกกำแพง"** ที่โมเดลทรงกลมบินผ่านไม่ได้

### 3.4 ข้อมูลสื่อสารในฝูง (Swarm Communication Packet: `AgentMessage`)
โดรนแต่ละตัวจะกระจายแพ็กเกจข้อมูลขนาดเล็ก (Payload ต่ำ) ผ่าน WiFi / ROS 2 / Zenoh:
```python
@dataclass
class AgentMessage:
    agent_id: int              # รหัสประจำตัวโดรน (0, 1, 2, ...)
    step: int                  # หมายเลขสเต็ปเวลา (Timestamp index)
    pos_estimate: np.ndarray   # พิกัดตำแหน่งที่วัดได้ [x, y, z] (3 มิติ)
    sigma: float               # ความแปรปรวนของตำแหน่งที่วัดได้
    martingale_wealth: float   # ค่าความมั่งคั่งมาร์ติงเกลของตัวเอง
    valid: bool = True         # สถานะความพร้อมทำงาน
```
* **Anti-Sigma-Spoofing:** ป้องกันไม่ให้โดรนที่โดนแฮกส่งค่า `sigma` เล็กผิดปกติเพื่อแย่งน้ำหนักการตัดสินใจของฝูง

### 3.5 ชุดข้อมูล Observation 20 มิติของโมเดล AI (Safe RL / PPO)
โมเดล Actor-Critic รับเวกเตอร์ขนาด $1 \times 20$ (Normalized ในช่วง $[-5.0, 5.0]$):
```
Index 00-02 : เวกเตอร์ระยะทางถึงเป้าหมาย (target_pos - drone_pos)
Index 03-05 : เวกเตอร์ความเร็วของโดรน (drone_vel)
Index 06-08 : เวกเตอร์แกน Z ของลำตัวโดรนในพิกัดโลก (บ่งบอกทิศทางการเอียง)
Index 09-11 : ความเร็วเชิงมุมรอบแกนลำตัว (angular_velocity)
Index 12-14 : เวกเตอร์ชี้ไปยังสิ่งกีดขวางที่ใกล้ที่สุด (obstacle_relative_pos)
Index 15-17 : ความเร็วสัมพัทธ์เทียบกับสิ่งกีดขวาง (obstacle_relative_vel)
Index 18    : สถานะแบตเตอรี่คงเหลือ (Battery State-of-Charge [0, 1])
Index 19    : มุมเอียงรวมของลำตัว (Normalized Tilt Angle [0, 1])
```

---

## 4. โค้ดโครงสร้างข้อมูลอ้างอิงในภาษา Python (Reference Data Schemas)

ทีมงานสามารถนำ dataclass ชุดนี้ไปใช้งานในการเชื่อมต่อระหว่างระบบได้ทันที:

```python
"""
aegis_data_schemas.py — แหล่งรวมโครงสร้างข้อมูลกลางสำหรับระบบ AEGIS
"""

from dataclasses import dataclass, field
import numpy as np


@dataclass
class DroneKinematicState:
    """ข้อมูลสถานะการเคลื่อนที่ของโดรนเดี่ยว"""
    timestamp_s: float
    position: np.ndarray      # Shape (3,) [x, y, z] เมตร
    velocity: np.ndarray      # Shape (3,) [vx, vy, vz] เมตร/วินาที
    rotation_matrix: np.ndarray # Shape (3, 3) SO(3)
    angular_velocity: np.ndarray # Shape (3,) [wx, wy, wz] เรเดียน/วินาที
    tilt_angle_rad: float     # มุมเอียงของลำตัว
    sigma_pos: float = 0.05   # ความไม่แน่นอนตำแหน่ง (m)
    sigma_vel: float = 0.08   # ความไม่แน่นอนความเร็ว (m/s)
    battery_soc: float = 1.0  # พลังงานคงเหลือ 0.0 - 1.0


@dataclass
class ObstacleTarget:
    """ข้อมูลสิ่งกีดขวางที่ตรวจจับได้"""
    obstacle_id: int
    center: np.ndarray        # Shape (3,) [x, y, z] เมตร
    radius: float             # รัศมีสิ่งกีดขวาง (m)
    velocity: np.ndarray      # Shape (3,) [vx, vy, vz] เมตร/วินาที


@dataclass
class CorridorPlane:
    """ระนาบขอบเขตของช่องทางบินปลอดภัย (Convex Flight Corridor)"""
    normal: np.ndarray        # เวกเตอร์แนวฉากชี้ออกนอกช่องทาง Shape (3,)
    distance: float           # ค่าคงที่ระนาบ (normal . p <= distance)


@dataclass
class NmpcControlInput:
    """คำสั่งแรงขับที่ส่งไปยังมอเตอร์หลังผ่านเกราะความปลอดภัย"""
    thrust_vector_world: np.ndarray # Shape (3,) [Fx, Fy, Fz] หน่วย นิวตัน (N)
    solve_time_ms: float            # เวลาที่ใช้คำนวณ (< 1.0 ms)
    is_safe: bool                   # สถานะผ่านเกราะความปลอดภัยหรือไม่
```

---

## 5. การจัดวางหน่วยความจำใน C++20 Microkernel (C-ABI Memory Layout)

สำหรับเคอร์เนล C++20 ความเร็วสูง (`libaegis_kernel.dylib` / `.so`) ที่รันในระดับ `< 0.1 ms` โครงสร้างข้อมูลจะถูกจัดวางเป็น C-struct แบบ Zero-Allocation ดังนี้:

```cpp
struct AegisCState {
    double px, py, pz;    // พิกัดตำแหน่งในโลก [m]
    double vx, vy, vz;    // เวกเตอร์ความเร็ว [m/s]
};

struct AegisCObstacle {
    double cx, cy, cz;    // พิกัดจุดศูนย์กลางสิ่งกีดขวาง [m]
    double radius;        // รัศมีทรงกลม [m]
    double vx, vy, vz;    // ความเร็วการเคลื่อนที่ [m/s]
};

struct AegisNmpcCorridorPlane {
    double nx, ny, nz;    // เวกเตอร์แนวฉากระนาบช่องทางบิน
    double d;             // ค่าระยะระนาบ: nx*x + ny*y + nz*z <= d
};

struct AegisNmpcResult {
    double f0_x, f0_y, f0_z;       // แรงขับสเต็ปแรกที่จะสั่งการมอเตอร์ [N]
    double traj_p[16][3];          // พิกัดวิถีการบินพรีวิว 15 สเต็ปข้างหน้า
    double traj_v[16][3];          // ความเร็วพรีวิว 15 สเต็ปข้างหน้า
    double traj_f[15][3];          // แรงขับพรีวิว 15 สเต็ปข้างหน้า
    int success;                   // สถานะความสำเร็จของตัวแก้สมการ (1=สำเร็จ)
    int iterations;                // จำนวนรอบคำนวณ (ADMM / SQP)
    double solve_time_us;          // เวลาคำนวณระดับไมโครวินาที
    double min_barrier_margin;     // ระยะห่างที่ใกล้สิ่งกีดขวางที่สุด [m]
    int fallback_activated;        // มีการตัดเข้าสู่ระบบสำรองฉุกเฉินหรือไม่
};
```

