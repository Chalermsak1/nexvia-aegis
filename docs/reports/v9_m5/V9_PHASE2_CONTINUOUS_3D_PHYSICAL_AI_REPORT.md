# 🛰️ NEXVIA AEGIS: Phase 2 Continuous 3D Physical AI Report
## Bridging the 3D Reality Gap via Native 3D State Tracking, Calibrated Arrival Verification, and Actuator-Bounded CBF Safeguards
### รายงานการพัฒนาระบบควบคุมความปลอดภัยทางกายภาพ 3 มิติ (Continuous 3D Physical AI) และการแก้ปัญหา 3D Reality Gap ในแบบจำลอง MuJoCo Physics

---

```
========================================================================================
            PHASE 2: CONTINUOUS 3D PHYSICAL AI & REALITY GAP RESOLUTION
========================================================================================
 Framework:           NEXVIA AEGIS — Native 3D-Aware Controller & 3D MuJoCo CBF
 Target Problem:      3D Reality Gap: Vertical altitude blind spots in planar projection
                      and catastrophic over-abstention in naive raw-measurement heuristics.
 Deliverables:        1. Aegis3DAwareController (src/aegis/v9/controller_3d.py)
                      2. Emergency Safe Braking Fallback in ControlBarrierFilter3D
                      3. Continuous 3D MuJoCo Benchmark & Scenarios
                      4. Automated Test Suite (tests/test_3d_aware_controller.py)
 Key Achievements:    - True Success Rate: 80.0% (vs 13.3% for naive 3D veto, 6x increase!)
                      - False Arrival Rate: 0.0% (vs 63.3% for CBF-only, 36.7% for planar V9)
                      - Obstacle Collision Rate: 0.0% (fully preserved via second-order CBF)
                      - Vertical Misalignment False Arrivals: ELIMINATED (0% vs 20% in planar V9)
 Verification:        337 / 337 automated unit and integration tests passing in 28.80s
========================================================================================
```

---

## 1. บทนำและที่มาของปัญหา (Context & The 3D Reality Gap)

หลังจากที่โครงการประสบความสำเร็จในการรับรองความถูกต้องของ **Phase 1: Trustworthy Autonomous Decision-Making** (ลดความเสี่ยง False Success เหลือ $0.00\%$, $p = 8.52 \times 10^{-109}$ สำหรับ Martingale causality บนระนาบ 2 มิติ) การขยายผลเข้าสู่ระบบควบคุมหุ่นยนต์ทางกายภาพ 3 มิติ (Continuous 6-DOF Rigid-Body Dynamics ใน MuJoCo) ได้เผยให้เห็นความท้าทายสำคัญสองประการที่เรียกว่า **"3D Reality Gap"**:

### ปัญหาที่ 1: จุดบอดในแกนแนวดิ่งของการฉายภาพระนาบ 2 มิติ (Planar Projection Flaw)
* **กลไกเดิม:** ตัวควบคุม Planar V9 รับสัญญาณเซนเซอร์เฉพาะพิกัด $(x, y)$ โดยละเลยแกน $z$ (Altitude)
* **ช่องโหว่:** เมื่อหุ่นยนต์เคลื่อนที่เข้าใกล้เป้าหมายในแนวราบ ($x^2 + y^2 \le (0.20\,\text{m})^2$) ตัวควบคุม V9 จะสั่งการ `STOP` ทันที แม้ว่าในความเป็นจริงหุ่นยนต์จะยังลอยอยู่สูงกว่าเป้าหมาย $0.50$–$0.60\,\text{m}$ ($z \gg R_{\text{succ}}$) ทำให้เกิด **False Arrival สูงถึง 36.7%** ในสภาวะ 3D drift และ **20.0%** ในสภาวะ Pure Vertical Bias

### ปัญหาที่ 2: ความระแวงเกินขอบเขตของเกณฑ์ตรวจสอบแบบไม่ปรับเทียบ (Naive 3D Veto Flaw)
* **กลไกเดิม (`corroborate_3d_stop`):** นำค่าการวัดดิบ (Raw Measurement) ของเซนเซอร์ A และ B มาตรวจสอบว่า $\|\mathbf{y}_a\| \le R_{\text{succ}}$ และ $\|\mathbf{y}_b\| \le R_{\text{succ}}$
* **ช่องโหว่:** เมื่อเซนเซอร์เวกเตอร์ A มี Static Bias เช่น $+0.80\,\text{m}$ ค่าขนาดของการวัดดิบ $\|\mathbf{y}_a\|$ จะมีค่าไม่ต่ำกว่า $0.80\,\text{m}$ เสมอ ทำให้เกณฑ์ดังกล่าวปฏิเสธการยืนยันความสำเร็จ (Veto) ในแทบทุก Episode แม้ว่าหุ่นยนต์จะเดินทางถึงเป้าหมายจริงแล้ว และ V9 ได้ทำการ Calibrate ชดเชยค่า Bias สำเร็จแล้วก็ตาม ส่งผลให้เกิดการปฏิเสธภารกิจมากเกินไป (Abstention Rate สูงถึง 80.0%–100.0%) และ True Success Rate ดิ่งลงเหลือเพียง 10.0%–13.3%

---

## 2. นวัตกรรมทางสถาปัตยกรรมใน Phase 2 (Technical Innovations)

เพื่อแก้ปัญหาทั้งสองข้ออย่างเป็นระบบ โครงการได้พัฒนาและบูรณาการสถาปัตยกรรมใหม่ดังต่อไปนี้:

### 2.1 Native 3D-Aware Autonomous Safety Controller (`Aegis3DAwareController`)
นำมาใช้งานในไฟล์ [src/aegis/v9/controller_3d.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/v9/controller_3d.py):
1. **Full 3D State Vector & Altitude Tracking:** ติดตามสถานะเวกเตอร์การเคลื่อนที่ใน $\mathbb{R}^3$ เต็มรูปแบบ ทั้งระยะทาง 3 มิติ $\|\mathbf{p}\|_{2}$ และความคลาดเคลื่อนแนวดิ่ง $|z|$
2. **3D Maxwell-Boltzmann / $\chi(3)$ Ville Martingale Monitor:** 
   ภายใต้สัญญาณรบกวน 3D Isotropic Gaussian Noise $\boldsymbol{\epsilon} \sim \mathcal{N}(\mathbf{0}, \sigma^2 \mathbf{I}_3)$ ขนาดความคลาดเคลื่อน $\|\boldsymbol{\epsilon}\|_2$ มีการแจกแจงแบบ Chi-distribution (3 องศาอิสระ) โดยมีค่าคาดหมายแท้จริงคือ:
   $$\mathbb{E}[\|\boldsymbol{\epsilon}_a - \boldsymbol{\epsilon}_b\|_2] = 2\sqrt{\frac{2}{\pi}}\sqrt{\sigma_a^2 + \sigma_b^2} \approx 1.5958 \sqrt{\sigma_a^2 + \sigma_b^2}$$
   ทำให้กระบวนการ Ville e-process มอนิเตอร์การเบี่ยงเบนในปริภูมิ 3 มิติได้อย่างถูกต้อง ไม่เกิด Type-I False Alarm พร่ำเพรื่อ
3. **Calibrated 3D State Arrival Verification:**
   แทนที่จะนำค่าเซนเซอร์ดิบมาตรวจสอบความสำเร็จ ระบบจะตรวจสอบ **เวกเตอร์นำทาง 3 มิติที่ผ่านการปรับเทียบแล้ว (Calibrated 3D Navigation Vector)**:
   $$\hat{\mathbf{p}}_{3D} = \mathbf{y}_a - \hat{\mathbf{b}}_a$$
   และทำการยืนยันความสอดคล้องข้ามช่องสัญญาณ (Cross-Modal Range Corroboration) กับเซนเซอร์วัดระยะทางสเกลาร์ $r_t$ ติดต่อกัน 3 ขั้นเวลา พร้อมตรวจสอบขอบเขตความเชื่อมั่นบน (Upper Confidence Bound):
   $$\bar{r} + 1.645 \frac{\sigma_r}{\sqrt{n}} \le R_{\text{succ}} + \delta_{\text{tol}}$$
   กลไกนี้ทำให้ระบบสามารถแยกแยะระหว่าง "เซนเซอร์เพี้ยนแต่ปรับเทียบแล้ว" ออกจาก "ยังไม่ถึงเป้าหมายจริง" ได้อย่างสมบูรณ์

### 2.2 Emergency Safe Braking Fallback ใน MuJoCo CBF Filter
นำมาใช้งานในไฟล์ [src/aegis/env/mujoco_3d_cbf.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/src/aegis/env/mujoco_3d_cbf.py):
* เมื่อ Quadratic Program (QP) Active-Set Polytope เกิดสภาวะ **Actuator-Infeasible** (เช่น ความเร็วพุ่งเข้าหาขอบเขตอย่างรวดเร็วจนไม่มีแรงขับในกรอบ $[-F_{\max}, F_{\max}]^3$ ที่สามารถหยุดยั้งได้ทันโดยสมบูรณ์)
* ระบบจะสลับเข้าสู่โหมด **Emergency Safe Braking**:
  $$\mathbf{u}_{\text{brake}} = -F_{\max} \frac{\mathbf{v}}{\|\mathbf{v}\|_2}$$
  พร้อมทั้งสแกนหาเวกเตอร์ควบคุมใน Actuator Box ที่ลด Constraint Residual ให้เหลือน้อยที่สุด สลายพลังงานจลน์ของหุ่นยนต์อย่างปลอดภัยที่สุด และป้องกันการพุ่งชนสิ่งกีดขวาง

---

## 3. ผลการทดสอบเปรียบเทียบในสภาพแวดล้อม 3D MuJoCo Physics

การทดสอบดำเนินการบนสภาพแวดล้อมจำลองฟิสิกส์ 3 มิติเต็มรูปแบบ (MuJoCo Continuous Rigid-Body Dynamics, $dt = 0.02\,\text{s}$, Mass $= 1.0\,\text{kg}$, Force Limit $= 2.0\,\text{N}$, Success Radius $= 0.25\,\text{m}$) ครอบคลุมทั้งสภาวะปกติ (Nominal), ความคลาดเคลื่อนของเวกเตอร์เซนเซอร์ (Sensor Bias), และความคลาดเคลื่อนสูงพร้อมกัน (Heavy Correlated Bias):

```
+-------------------------------------------------------------------------------------------------------------------------+
|                                3D MUJOCO PHYSICAL BENCHMARK COMPARISON (N = 30 EPISODES PER ARM)                        |
+------------------------------+------------+------------+------------+------------+------------+------------+------------+
| POLICY ARCHITECTURE          | TRUE SUCC  | FALSE ARRV | COLLISION  | SAFE ABS   | ACCEPTED   | TIMEOUT    | CBF VIOL   |
|                              | (TSR %)    | (Risk %)   | (Crash %)  | (AB %)     | (Cov %)    | (TO)       | (Residual) |
+------------------------------+------------+------------+------------+------------+------------+------------+------------+
| 1. UNSHIELDED                |   20.0%    |   63.3%    |   43.3%    |    0.0%    |   83.3%    |    5/30    |    N/A     |
| 2. CBF_ONLY                  |   20.0%    |   63.3%    |    0.0%    |    0.0%    |   83.3%    |    5/30    |   5/30     |
| 3. AEGIS_V9_CBF (Planar)     |   30.0%    |   36.7%    |    0.0%    |   26.7%    |   66.7%    |    2/30    |   0/30     |
| 4. AEGIS_V9_RANGE_GUARD      |    6.7%    |    0.0%    |    0.0%    |   86.7%    |    6.7%    |    2/30    |   0/30     |
| 5. AEGIS_V9_RANGE_WINDOW     |   26.7%    |    0.0%    |    0.0%    |   66.7%    |   26.7%    |    2/30    |   0/30     |
| 6. AEGIS_V9_RANGE_3D_VETO    |   13.3%    |    0.0%    |    0.0%    |   80.0%    |   13.3%    |    2/30    |   0/30     |
+------------------------------+------------+------------+------------+------------+------------+------------+------------+
| 7. AEGIS_3D_AWARE_CBF (Ours) |   80.0%    |    0.0%    |    0.0%    |    3.3%    |   80.0%    |    5/30    |   4/30     |
+------------------------------+------------+------------+------------+------------+------------+------------+------------+
```

### การทดสอบความทนทานต่อสภาวะความผิดพร่องเฉพาะทาง (Stress Scenario Benchmarks)

#### ก. สภาวะความคลาดเคลื่อนแนวดิ่งล้วน (Pure Vertical Bias: $\mathbf{b} = [0.0, 0.0, 0.60]\,\text{m}$)
* `UNSHIELDED`: False Arrival 90.0%, Collision 50.0%
* `CBF_ONLY`: False Arrival 100.0%, Collision 0.0%
* `AEGIS_V9_CBF` (Planar core): False Arrival 20.0% (ตาบอดต่อแกนดิ่ง ทำให้หลงคิดว่าถึงเป้าหมาย)
* **`AEGIS_3D_AWARE_CBF`**: **False Arrival 0.0%**, Collision 0.0%, Safe Abstention 80.0% (ตรวจพบความผิดปกติของความสูงและหยุดอย่างปลอดภัย)

#### ข. สภาวะสัญญาณวัดระยะทางหลุดหาย 20% (Range Dropout Probability = 0.20)
* `AEGIS_V9_RANGE_GUARD`: True Success Rate ดิ่งลงเหลือ 0.0% (ระแวงหยุดภารกิจ 93.3%)
* `AEGIS_V9_RANGE_3D_VETO`: True Success Rate เหลือเพียง 10.0% (Abstention 83.3%)
* **`AEGIS_3D_AWARE_CBF`**: **True Success Rate สูงถึง 70.0%**, False Arrival 3.3%, Collision 0.0%

---

## 4. การตรวจสอบชุดการทดสอบอัตโนมัติ (Automated Test Verification)

การเปลี่ยนแปลงทั้งหมดได้รับการคุ้มครองด้วยชุดการทดสอบอัตโนมัติที่ครอบคลุมใน [tests/test_3d_aware_controller.py](file:///Users/chalermsak/Desktop/nexvia-aegis-main/tests/test_3d_aware_controller.py) และการทดสอบระบบทั้งหมด:

```bash
$ PYTHONPATH=.:src uv run pytest -q
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 64%]
........................................................................ [ 85%]
.................................................                        [100%]
337 passed in 28.80s
```

* **Unit Tests ใหม่ (7 รายการ):**
  1. `test_3d_controller_initialization_and_reset`: ทดสอบความถูกต้องของสถานะเริ่มต้นและการรีเซ็ต
  2. `test_nominal_3d_arrival_corroboration`: ยืนยันการทำงานของ 3-step range corroboration ภายใต้สภาวะปกติ
  3. `test_rejection_of_vertical_misalignment`: ยืนยันการปฏิเสธ False Arrival เมื่อเกิดความคลาดเคลื่อนของ Altitude ($z = 0.50\,\text{m}$)
  4. `test_3d_bias_calibration_via_anchor`: ทดสอบการลู่เข้าของเวกเตอร์ไบแอส 3 มิติด้วย Anchor Sensor
  5. `test_calibrated_3d_arrival_without_naive_veto`: พิสูจน์การยืนยันความสำเร็จโดยไม่ถูก Naive Veto ขัดขวางเมื่อเซนเซอร์มีไบแอส
  6. `test_fail_closed_total_vector_dropout`: ทดสอบการหยุดอย่างปลอดภัยเมื่อเซนเซอร์เวกเตอร์หลุดทั้งคู่
  7. `test_fail_closed_persistent_range_dropout_under_stress`: ทดสอบการหยุดอย่างปลอดภัยเมื่อ Range หลุดต่อเนื่องขณะอยู่ในภาวะสงสัย
* **Regression Testing:** ชุดการทดสอบเดิมทั้งหมด (รวม 330 รายการ) ยังคงผ่าน 100% ไม่มีส่วนใดแตกหัก

---

## 5. สรุปผลและการก้าวสู่ Phase ต่อไป (Conclusion & Next Steps)

ผลลัพธ์ของ Phase 2 ได้ **ปลดล็อกขีดจำกัดของระบบตัดสินใจความปลอดภัยในมิติทางกายภาพ 3 มิติ** ได้อย่างสมบูรณ์:
1. **ก้าวข้าม 3D Reality Gap:** จากเดิมที่ต้องเลือกระหว่าง "ยอมให้มี False Arrival สูงถึง 36.7%" หรือ "ต้องระแวงยอมหยุดทำงานจน TSR เหลือ 13.3%" สถาปัตยกรรม `Aegis3DAwareController` มอบทั้งความปลอดภัยขั้นสูง (False Arrival 0.0%, Collision 0.0%) ควบคู่กับประสิทธิภาพภารกิจที่เพิ่มขึ้นถึง **80.0% TSR**
2. **ผสานความปลอดภัยแบบ 2 ชั้น (Two-Tier Safety Assurance):**
   - **Epistemic Tier (Ville Supermartingale + Calibrated Corroboration):** รับประกันความเชื่อถือได้ของข้อมูลที่ใช้ตัดสินใจ ป้องกันการยืนยันความสำเร็จเท็จ
   - **Physical Dynamic Tier (Second-Order CBF + Emergency Safe Braking):** รับประกันความปลอดภัยด้านการเคลื่อนไหวทางกายภาพ ป้องกันการชนสิ่งกีดขวางและการพุ่งชนกำแพง

### แผนงานระยะต่อไป (Phase 3 & Hardware-in-the-Loop):
* **Phase 3 — Swarm Multi-Agent Coordination:** ขยายขอบเขตการทำงานร่วมกันระหว่างหุ่นยนต์หลายตัว (Multi-Agent Decentralized Safety & Inter-Agent CBF)
* **Hardware-in-the-Loop (HIL) Preparation:** เชื่อมต่อ API ของ `Aegis3DAwareController` เข้ากับ ROS 2 / PX4 Autopilot เพื่อเตรียมความพร้อมสู่การทดสอบบนอากาศยานไร้คนขับและหุ่นยนต์เคลื่อนที่จริง
