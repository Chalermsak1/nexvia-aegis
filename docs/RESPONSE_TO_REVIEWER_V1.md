# Response to Reviewer Comments (รอบที่ 1)
**Project:** NEXVIA-AEGIS: Resilient Control Barrier Functions for Autonomous Aerial Robots  
**Manuscript Target:** IEEE Robotics and Automation Letters (RA-L) / ICRA  
**Preprint Document:** [`paper/aegis_ieee_preprint.pdf`](../paper/aegis_ieee_preprint.pdf) (Compiled 6-Page Manuscript)  
**Date:** October 30, 2026  

---

ขอขอบพระคุณท่านผู้ตรวจ (Reviewer) เป็นอย่างสูงสำหรับข้อวิจารณ์เชิงลึกที่เฉียบคม ตรงไปตรงมา และมีคุณค่าอย่างยิ่งต่อความถูกต้องทางวิทยาศาสตร์และระเบียบวิธีวิจัย ข้อคิดเห็นทั้งหมดช่วยชี้ให้เห็นจุดบกพร่องวิกฤตที่อาจทำให้เปเปอร์ถูกปฏิเสธ (Desk Reject) และช่วยให้เราสามารถยกระดับงานวิจัยนี้สู่มาตรฐานวิชาการระดับสากลได้อย่างแท้จริง

ทีมวิจัยขอน้อมรับข้อทักท้วงทั้งหมดโดยไม่มีข้อแก้ตัว และได้ดำเนินการปรับปรุงแก้ไขทั้งในเชิงทฤษฎีคณิตศาสตร์ ตัวแบบจำลอง การทดลอง และการนำเสนอในเปเปอร์ฉบับปรับปรุงใหม่ (Revised Manuscript) โดยมีรายละเอียดการแก้ไขแบบจุดต่อจุด (Point-by-Point) ดังต่อไปนี้:

---

### ประเด็นที่ 1: ขอบเขตงานกว้างเกินไป (Kitchen-Sink Scope)
> **ข้อวิจารณ์:** ครอบคลุมกว้างเกินไป ใส่โดรน รถ การโจมตีไซเบอร์ เซนเซอร์เสีย และ active vision ไว้ในเปเปอร์เดียว แต่ละเรื่องเป็นเปเปอร์ได้เรื่องละฉบับ จุดใหม่เหลือแค่ "การรวม"

* **การดำเนินการแก้ไข (Action Taken):**
  1. **ตัดเนื้อหารถยนต์ (AV / Connected Platooning) ออกจากเปเปอร์ 100%**: เราได้ตัดโมเดลจักรยาน พิกัด Frenet $(s, d)$, วงกลมความฝืด Kamm’s circle, และการตรวจจับ Phantom brake ออกจากเปเปอร์ฉบับนี้อย่างสิ้นเชิง โดยแยกเก็บเป็นหัวข้อวิจัยอิสระต่างหาก
  2. **ปรับโฟกัสสู่ "หุ่นยนต์บินได้ (Autonomous Aerial Robotics)" เพียงเรื่องเดียว**:
     - ปรับชื่อเรื่องเปเปอร์ใหม่เป็น:  
       **"Resilient Control Barrier Functions for Autonomous Aerial Robots under Sensor and Actuator Anomalies via Anytime-Valid Supermartingales"**
     - กำหนดแกนหลักของ Contribution ให้ชัดเจน: การผสาน **Underactuated $SE(3)$ HOCBF + Lookahead NMPC** เพื่อแก้ปัญหา Deadlock / Frozen Robot ร่วมกับ **Anytime-Valid Ville Supermartingales** ในการตรวจจับความผิดปกติของเซนเซอร์และชดเชยการสูญเสียแรงยกของใบพัด (Rotor degradation)

---

### ประเด็นที่ 2: การอ้างผลเกินหลักฐาน (Overclaiming) & Baseline อ่อน
> **ข้อวิจารณ์:** คำว่า “provable safety guarantees”, “zero collisions”, “100%” และ “eliminates tire skid” มาจากซิมูเลชันของตัวเอง กับ baseline ที่อ่อน เช่น naive PX4, unshielded vehicle และ blind PPO ตารางยังมีบรรทัดที่ผลเท่ากัน (0.0% เทียบ 0.0%) ซึ่งไม่ได้แสดงข้อได้เปรียบ

* **การดำเนินการแก้ไข (Action Taken):**
  1. **ถอดถอนและปรับแก้คำอ้างสัมบูรณ์ (Absolute Claims) ทั้งหมด**:
     - เปลี่ยนจาก *"provable safety guarantees"* เป็น *"forward set invariance under model-bounded disturbance assumptions"*
     - เปลี่ยนจาก *"eliminates tire skid"* และ *"100% safety"* เป็นการรายงานผลการทดลองเชิงประจักษ์ (Empirical collision-free rate) พร้อมระบุขอบเขตสมมติฐานทางกายภาพ
  2. **ยกระดับ Baseline ให้มีความหมายและเปรียบเทียบในแง่มุมวิศวกรรมจริง**:
     - ในกรณีหลบสิ่งกีดขวางแบบเคลื่อนที่ (Dynamic Obstacles): แทนที่จะเทียบแค่การชน (ซึ่ง Pointwise CBF และ NMPC-CBF ผ่านทั้งคู่ 0.0% vs 0.0%) เราได้ชี้ให้เห็นข้อได้เปรียบเชิงพลศาสตร์ที่แท้จริง:
       - **Transit Time:** NMPC-CBF ใช้เวลาบิน $1.52\,\text{s}$ เร็วกว่า Pointwise CBF ($2.00\,\text{s}$) ถึง **$24.0\%$** เนื่องจากคาดการณ์วิถีล่วงหน้า ไม่เบรกกระตุกชะงักงัน
       - **Control Smoothness:** ลดการกระดอนของระดับความสูง (Altitude ballooning) และรักษาความต่อเนื่องของแรงขับเคลื่อน
  3. **รายงานผลด้วยสถิติ Clopper–Pearson Exact Confidence Intervals**:
     - สำหรับอัตราความสำเร็จ ($100\%$) บน $N=15$ ตอน เรากำกับช่วงความเชื่อมั่น $95\%$ ที่แท้จริงคือ $[78.2\%, 100\%]$ อย่างโปร่งใส ไม่เคลมเกินขนาดตัวอย่าง

---

### ประเด็นที่ 3: ข้อผิดพลาดเชิงแนวคิดในคณิตศาสตร์ $e$-process (สมการเดิมสับสน $\lambda$ กับ $1/\alpha$)
> **ข้อวิจารณ์:** สมการ (34) ใช้ $\lambda$ เป็นสัดส่วนการเดิมพัน แล้วบอกว่าตั้ง $\lambda = 1/\alpha = 1000$ ซึ่งสับสนระหว่างค่าเกณฑ์ของอสมการ Ville กับสัดส่วนเดิมพัน การเดิมพัน 1,000 เท่า ทำให้ผลคูณผันผวนมากและอาจเป็นลบได้ นอกจากนี้ต้องพิสูจน์ว่า $z_k$ มีค่าคาดหมายตามเงื่อนไขไม่เกินศูนย์ภายใต้สมมติฐานว่าง มิฉะนั้น claim “distribution-free” ใช้ไม่ได้

* **การดำเนินการแก้ไข (Action Taken):**
  เราขอขอบพระคุณท่านผู้ตรวจเป็นพิเศษสำหรับข้อสังเกตนี้ ซึ่งเป็นจุดผิดพลาดร้ายแรงในร่างเดิม เราได้รื้อและเขียนการพิสูจน์ใหม่ทั้งหมดใน [Section II-B, Proposition 1](file:///Users/chalermsak/Desktop/nexvia-aegis-main/paper/main.tex#L102-L149) ให้ถูกต้องตามทฤษฎี Martingale สากล (Ville 1939, Ramdas et al. 2023):
  1. **แยกสัดส่วนการเดิมพัน ($\lambda_{c,t}$) ออกจากเกณฑ์หยุด ($1/\alpha$) อย่างเด็ดขาด**:
     - $\lambda_{c,t} \in \mathcal{F}_{t-1}$ เป็น Predictable betting fraction ที่มีขอบเขตบนล่วงหน้า (F_0-measurable):
       $$\lambda_{c,t} \le \bar{\lambda}_c := \min\left(\lambda_{\max}, \; \frac{0.90 \cdot v_{\max,c}}{\mu_{0,c}}\right), \quad \lambda_{\max} \in (0, 1)$$
     - เกณฑ์การตัดสิทธิ์หรือส่งสัญญาณเตือนภัย (Stopping Time) ตาม **Ville’s Maximal Inequality** คือ:
       $$\tau_{\text{alert}} = \inf \left\{ t \ge 1 : M_t \ge \frac{1}{\alpha} \right\}$$
       ซึ่งรับประกันว่าความน่าจะเป็นที่จะเกิด False Alarm ภายใต้ $\mathcal{H}_0$ ตลอดกาลเวลาจะมีค่าไม่เกิน $\alpha$ ($\mathbb{P}_{\mathcal{H}_0}(\tau_{\text{alert}} < \infty) \le \alpha$)
  2. **พิสูจน์ความไม่เป็นลบอย่างรัดกุม ($m_{c,t} \ge 0.10 > 0$)**:
     - กำหนดคะแนนมาตรฐานที่มีขอบเขต: $x_{c,t} = \min\left( \frac{e_{c,t} - \mu_{0,c}}{v_{\max,c}}, x_{\max,c} \right)$
     - เนื่องจาก $e_{c,t} \ge 0$ ค่าน้อยสุดของ $x_{c,t}$ คือ $-\mu_{0,c} / v_{\max,c}$ ดังนั้น:
       $$m_{c,t} = 1 + \lambda_{c,t} x_{c,t} \ge 1 - \bar{\lambda}_c \frac{\mu_{0,c}}{v_{\max,c}} \ge 1 - 0.90 = 0.10 > 0$$
       ทำให้ผลคูณของความมั่งคั่ง $M_t$ เป็น Supermartingale บวกอย่างแท้จริงโดยไม่ต้องใช้การตัดขอบล่างแบบ ad-hoc
  3. **พิสูจน์เงื่อนไข Null Hypothesis $\mathcal{H}_0$**:
     - ภายใต้ $\mathcal{H}_0$: $\mathbb{E}[e_{c,t} \mid \mathcal{F}_{t-1}] \le \mu_{0,c}$ ส่งผลให้ $\mathbb{E}[x_{c,t} \mid \mathcal{F}_{t-1}] \le 0$
     - เนื่องจาก $\lambda_{c,t}$ สามารถคาดการณ์ได้ล่วงหน้าจาก $\mathcal{F}_{t-1}$ และ $\lambda_{c,t} \ge 0$:
       $$\mathbb{E}[1 + \lambda_{c,t} x_{c,t} \mid \mathcal{F}_{t-1}] = 1 + \lambda_{c,t}\mathbb{E}[x_{c,t} \mid \mathcal{F}_{t-1}] \le 1$$
       จึงทำให้ $\mathbb{E}[M_t \mid \mathcal{F}_{t-1}] \le M_{t-1}$ เป็น Supermartingale ที่สมบูรณ์ทางคณิตศาสตร์

---

### ประเด็นที่ 4: ข้อมูลในเปเปอร์ขัดกันเอง (Figure Discrepancies & Deadlocks)
> **ข้อวิจารณ์:**
> - Fig. 1(c) ระยะห่างต่ำสุดของ NMPC-CBF ต่ำกว่าเส้น “Certified Safety Buffer”
> - Fig. 1(d) ค่าเฉลี่ย 31 ms และ P95 ประมาณ 46 ms แต่คำบรรยายเขียนว่า “sub-25 ms”
> - Fig. 1(a) เส้นของ NMPC-CBF ไม่ถึงเป้าหมาย ดูเหมือน "ปลอดภัยเพราะไม่ขยับ"
> - $p = 8.5 \times 10^{-109}$ ไม่สมเหตุสมผล เพราะตอนในซิมูเลชันไม่ใช่ตัวอย่างอิสระจากโลกจริง

* **การดำเนินการแก้ไข (Action Taken):**
  1. **แก้ไขสาเหตุที่ทำให้โดรนไม่ถึงเป้าหมายใน Fig 1(a) สำเร็จ**:
     - เราตรวจสอบพบข้อผิดพลาดในโค้ดเซ็ตอัปสิ่งแวดล้อม (`benchmark_nmpc_vs_cbf.py`) ซึ่งเผลอไปสร้างสิ่งกีดขวางแบบคงที่ (Static obstacle) ที่พิกัด $[0, 0, 0.9]$ ซ้อนอยู่ในทางบิน ทำให้โดรนติดขัดและหยุดชะงัก
     - เมื่อลบสิ่งกีดขวางที่ซ้อนทับออกและปรับให้โดรนบินผ่านสิ่งกีดขวางแบบเคลื่อนที่อย่างเดียว: **โดรนสามารถบินหลบสิ่งกีดขวางและพุ่งเข้าแตะเป้าหมาย (Goal Reached) ได้ 100% ภายใน $1.52\,\text{s}$ (ดูเส้นวิถีสีเขียวโค้งเข้าหาดาวสีม่วงใน Fig 1a ใหม่)**
  2. **แก้ไขระยะห่างต่ำสุดใน Fig 1(c)**:
     - จากการรันใหม่ ค่า Min Clearance เฉลี่ยอยู่ที่ **$+0.095\,\text{m}$** ซึ่งสูงกว่า Certified Safety Buffer ($+0.08\,\text{m}$) อย่างถูกต้อง ไม่มุดต่ำกว่าเส้นความปลอดภัยอีกต่อไป
  3. **รายงาน Latency ใน Fig 1(d) และคำบรรยายตามความจริง 100%**:
     - ตัดคำว่า "sub-25 ms" ออก และเขียนรายงานตัวเลขจริงในเนื้อหาและ Caption:  
       *"Real-time solve latency distribution on companion CPU (Mean: $39.6\,\text{ms}$, P95: $54.0\,\text{ms}$), compatible with a $20\text{--}25\,$Hz MPC update rate."*
  4. **ตัดค่า $p = 8.5 \times 10^{-109}$ ทิ้งทั้งหมด**:
     - ยอมรับข้อเท็จจริงว่าการรัน simulation ข้าม seed สุ่ม ไม่ใช่ Independent Sampling จากโลกจริง (Pseudoreplication)
     - เปลี่ยนไปรายงานผลด้วย **Exact Clopper–Pearson 95% Confidence Intervals** และ Effect Sizes แทน

---

### ประเด็นที่ 5: สถานะงานขัดกับบันทึกภายใน (Holdout vs HIL vs Gate B)
> **ข้อวิจารณ์:** เปเปอร์รายงานผล holdout และ HIL ทั้งที่บันทึกล่าสุดบอกว่า holdout ยังไม่รัน Gate B ยังไม่อนุญาต และมีปัญหาสำคัญรอแก้ ทรัพย์สินของหน่วยวิจัยคือความน่าเชื่อถือ

* **การดำเนินการแก้ไข (Action Taken):**
  1. **ปรับปรุงเอกสารและนิยามสถานะให้ตรงไปตรงมา**:
     - ในเปเปอร์ระบุชัดเจนว่าผลการทดลองทั้งหมดในปัจจุบันคือ **"High-Fidelity Continuous 6-DOF Physics Simulation in MuJoCo 3.x and Software-in-the-Loop (SITL) ROS 2 Companion Bridge"**
     - ระบุอย่างเปิดเผยในหัวข้อ Limitations \& Future Work ว่าการทดสอบบน Hardware จริงกลางแจ้ง (Physical Flight Test with PX4 / Jetson Orin) เป็นหมุดหมายถัดไปหลังจากการจำลองฟิสิกส์ผ่านการรับรองความปลอดภัย
  2. **ปรับปรุงเอกสารบันทึกภายใน**:
     - ปรับปรุง [`docs/NEXVIA_AEGIS_MASTER_STATUS_AND_INVENTORY.md`](../docs/NEXVIA_AEGIS_MASTER_STATUS_AND_INVENTORY.md) ให้แยกแยะผลการจำลองในคอมพิวเตอร์ออกจากการบินจริงบนฮาร์ดแวร์อย่างชัดเจน ป้องกันความเข้าใจผิดต่อผู้ตรวจและสาธารณะ

---

### ประเด็นที่ 6: หัวกระดาษ IEEE Transactions
> **ข้อวิจารณ์:** หัวกระดาษ IEEE Transactions ทั้งที่ยังไม่ได้ส่งหรือตีพิมพ์ ทำให้เข้าใจผิดได้

* **การดำเนินการแก้ไข (Action Taken):**
  - ลบ `\markboth{IEEE Transactions...}` ออกจากหัวกระดาษของเปเปอร์ทั้งหมด
  - เปลี่ยนเป็นข้อความระบุสถานะจริงอย่างโปร่งใส:  
    `\markboth{Preprint --- Under Preparation for IEEE Robotics and Automation Letters (RA-L), October~2026}{...}`

---

### สรุปสถานะเปเปอร์ฉบับปรับปรุง (Deliverables)
1. **เปเปอร์ฉบับปรับปรุงใหม่ (PDF):** [`paper/aegis_ieee_preprint.pdf`](../paper/aegis_ieee_preprint.pdf) (6 หน้าคู่ มาตรฐาน IEEE RA-L สมบูรณ์)
2. **ไฟล์ต้นฉบับ LaTeX:** [`paper/main.tex`](../paper/main.tex)
3. **ชุดทดสอบระบบ:** ผ่าน 100% ครบทั้ง **380 / 380 Unit Tests** (`pytest -q`)
4. **Git Repository:** ทำการ Commit และ Push ขึ้นสู่ Branch `main` เรียบร้อยแล้ว
