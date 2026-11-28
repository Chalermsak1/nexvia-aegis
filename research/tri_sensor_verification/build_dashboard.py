"""
Interactive Multi-Tab HTML Dashboard Generator for My Tri-Sensor Maze Research.

Builds a self-contained, theme-aware, 5-tab interactive HTML dashboard from
the saved experiment logs so you can inspect:
  Tab 1: Overview & KPIs (Naive vs 2-Sensor vs Your Tri-Sensor Verifier)
  Tab 2: Interactive Maze Exploration Replay (Play / Pause / Step Scrubber)
  Tab 3: 3-Sensor Drift & Page CUSUM Curves (with Quarantine Exclusion Zone)
  Tab 4: Full 20-Scenario x 3-Sensor Fault Matrix & Heatmap
  Tab 5: Separated Quarantine Audit Log (proving faulty values never display)
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, List


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>NEXVIA Tri-Sensor Maze Research — Interactive Dashboard</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    .tab-btn { transition: all 0.15s ease; }
    .tab-btn.active {
      background-color: var(--primary);
      color: var(--primary-foreground);
      border-color: var(--primary);
    }
    canvas { display: block; width: 100%; height: auto; }
  </style>
</head>
<body class="bg-[var(--background)] text-[var(--foreground)] antialiased p-4 md:p-6">
  <div class="max-w-7xl mx-auto space-y-5">
    <!-- Header -->
    <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 shadow-sm flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div>
        <div class="flex items-center gap-2 mb-1">
          <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
            TRI-SENSOR VERIFICATION BENCHMARK · 60 MAZE RUNS
          </span>
          <span id="run-badge" class="text-xs text-[var(--muted-foreground)] font-mono"></span>
        </div>
        <h1 class="text-xl font-bold tracking-tight">Tri-Sensor Self-Verification &amp; Fault Isolation Benchmark</h1>
        <p class="text-sm text-[var(--muted-foreground)] mt-1">
          การประเมินระบบตรวจสอบความสอดคล้องของเซ็นเซอร์อิสระ 3 ช่องสัญญาณ (S1_VIO, S2_LIDAR, S3_UWB) และการคัดแยกค่าผิดพลาดในแผนที่เขาวงกต 3 มิติ
        </p>
      </div>
      <div class="flex flex-wrap gap-2 text-xs">
        <div class="px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
          <div class="text-[var(--muted-foreground)]">Scenarios</div>
          <div class="font-bold text-base">20 × 3 Arms</div>
        </div>
        <div class="px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
          <div class="text-[var(--muted-foreground)]">Mean Tri-RMSE</div>
          <div id="hdr-rmse" class="font-bold text-base text-emerald-500">—</div>
        </div>
        <div class="px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
          <div class="text-[var(--muted-foreground)]">Audit Events</div>
          <div id="hdr-audit" class="font-bold text-base text-amber-500">—</div>
        </div>
      </div>
    </div>

    <!-- Navigation Tabs -->
    <div class="flex flex-wrap gap-2 border-b border-[var(--border)] pb-3">
      <button class="tab-btn active px-4 py-2 rounded-lg border border-[var(--border)] text-sm font-medium cursor-pointer" data-tab="overview">
        1. ภาพรวม (Overview)
      </button>
      <button class="tab-btn px-4 py-2 rounded-lg border border-[var(--border)] text-sm font-medium cursor-pointer bg-[var(--card)]" data-tab="maze">
        2. สำรวจเขาวงกต (Maze Replay)
      </button>
      <button class="tab-btn px-4 py-2 rounded-lg border border-[var(--border)] text-sm font-medium cursor-pointer bg-[var(--card)]" data-tab="curves">
        3. กราฟดริฟ &amp; Page CUSUM
      </button>
      <button class="tab-btn px-4 py-2 rounded-lg border border-[var(--border)] text-sm font-medium cursor-pointer bg-[var(--card)]" data-tab="matrix">
        4. ตารางครบ 20 เคส (Matrix)
      </button>
      <button class="tab-btn px-4 py-2 rounded-lg border border-[var(--border)] text-sm font-medium cursor-pointer bg-[var(--card)]" data-tab="audit">
        5. บันทึกกักกันค่าเสีย (Audit Log)
      </button>
    </div>

    <!-- TAB 1: OVERVIEW -->
    <section id="tab-overview" class="tab-panel space-y-5">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4" id="kpi-cards"></div>

      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 shadow-sm">
        <h2 class="text-base font-semibold mb-1">เปรียบเทียบค่าความคลาดเคลื่อน Display Position RMSE (m) ครบทั้ง 20 สถานการณ์</h2>
        <p class="text-xs text-[var(--muted-foreground)] mb-4">
          สีแดง = Naive Average Baseline · สีส้ม = Two-Sensor Min-Sigma Baseline · สีเขียว = Tri-Sensor Verifier (Proposed) — ค่ายิ่งต่ำยิ่งแม่นยำ
        </p>
        <canvas id="overview-rmse-canvas" width="1100" height="360"></canvas>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 shadow-sm space-y-2">
          <h3 class="text-sm font-semibold">สรุปผลการทดลองสำคัญ (Key Findings)</h3>
          <ul class="text-sm text-[var(--muted-foreground)] space-y-2 list-disc pl-5">
            <li><strong class="text-[var(--foreground)]">การแก้ไขข้อจำกัดของ Two-Sensor Min-Sigma:</strong> เมื่อ <code class="text-xs">S1_VIO</code> (ช่องที่มี nominal sigma ต่ำสุด) เกิด Heavy Drift หรือ Freeze ระบบ 2 เซ็นเซอร์จะอ้างอิงช่องที่ผิดพลาดจนค่าคลาดเคลื่อนสูงถึง <strong class="text-rose-500">3.28 m – 4.41 m</strong> ขณะที่ Tri-Sensor Verifier ควบคุม RMSE ให้อยู่ที่ <strong class="text-emerald-500">0.043 m – 0.049 m</strong></li>
            <li><strong class="text-[var(--foreground)]">การตรวจจับ Retimestamped Freeze:</strong> ตรวจจับและกักกันเซ็นเซอร์ที่ค่าคงที่แต่ส่ง timestamp ใหม่ได้อย่างแม่นยำภายใน <strong class="text-emerald-500">1 step</strong> ครอบคลุมทุกช่องสัญญาณ (S1, S2, S3)</li>
            <li><strong class="text-[var(--foreground)]">Fail-Closed Safety ภายใต้ความผิดพลาดคู่:</strong> ในกรณีทดสอบขีดจำกัด <code class="text-xs">DUAL_S1_DRIFT_S2_FREEZE</code> ระบบเข้าสู่สถานะ <code class="text-xs">ABSTAIN_SAFE_STOP</code> โดยไม่ส่งค่าที่ขาดความเชื่อมั่นเข้าสู่ Display และ Control</li>
          </ul>
        </div>
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 shadow-sm space-y-2">
          <h3 class="text-sm font-semibold">ขอบเขตและระเบียบวิธีทดลอง (Experimental Protocol)</h3>
          <ul class="text-sm text-[var(--muted-foreground)] space-y-2 list-disc pl-5">
            <li><strong class="text-[var(--foreground)]">สภาพแวดล้อมจำลอง:</strong> แผนที่เขาวงกต 3 มิติขนาด 10 × 10 × 2.5 m (5 สิ่งกีดขวางหลัก, Voxel 0.25 m, 45 steps/episode, deterministic seeds)</li>
            <li><strong class="text-[var(--foreground)]">ชุดเซ็นเซอร์อิสระ 3 ช่อง:</strong> <code class="text-xs">S1_VIO</code> (σ = 0.030 m), <code class="text-xs">S2_LIDAR</code> (σ = 0.035 m), และ <code class="text-xs">S3_UWB</code> (σ = 0.045 m)</li>
            <li><strong class="text-[var(--foreground)]">กลไกตรวจสอบ:</strong> Physical Bounds Guard + Retimestamped-Freeze Detector + Pairwise Normalized Disagreement &amp; Deterministic Page CUSUM (k = 1.65, h = 4.0; ไม่ใช่ Ville-anytime-valid) + Majority Quarantine</li>
            <li><strong class="text-[var(--foreground)]">สถานะหลักฐาน:</strong> Simulation-only evaluation (ยังไม่ใช่การรับรองบนฮาร์ดแวร์จริง)</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- TAB 2: MAZE REPLAY -->
    <section id="tab-maze" class="tab-panel hidden space-y-4">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm flex flex-wrap items-center gap-3 justify-between">
        <div class="flex flex-wrap items-center gap-3">
          <label class="text-sm font-medium">เลือกสถานการณ์:</label>
          <select id="maze-scenario-select" class="px-3 py-1.5 rounded-lg text-sm bg-[var(--background)] border border-[var(--border)] text-[var(--foreground)]"></select>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-play" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white cursor-pointer">▶ Play</button>
          <button id="btn-pause" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] cursor-pointer">⏸ Pause</button>
          <input id="step-slider" type="range" min="0" max="44" value="44" class="w-40 accent-emerald-500 cursor-pointer" />
          <span id="step-label" class="text-xs font-mono w-20">Step 44/44</span>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div class="lg:col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
          <h3 class="text-sm font-semibold mb-2">แผนที่เขาวงกต 3 มิติ (Top-Down XY + 5 เสาสิ่งกีดขวาง)</h3>
          <canvas id="maze-canvas" width="680" height="520"></canvas>
        </div>
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm space-y-3">
          <h3 class="text-sm font-semibold border-b border-[var(--border)] pb-2">สถานะสด ณ Step ปัจจุบัน</h3>
          <div id="maze-live-panel" class="space-y-2.5 text-xs"></div>
        </div>
      </div>
    </section>

    <!-- TAB 3: DRIFT & CUSUM CURVES -->
    <section id="tab-curves" class="tab-panel hidden space-y-4">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm flex flex-wrap items-center gap-3 justify-between">
        <div class="flex items-center gap-3">
          <label class="text-sm font-medium">เลือกสถานการณ์:</label>
          <select id="curves-scenario-select" class="px-3 py-1.5 rounded-lg text-sm bg-[var(--background)] border border-[var(--border)] text-[var(--foreground)]"></select>
        </div>
        <div class="flex items-center gap-2 text-xs">
          <label class="font-medium">แกนที่แสดง:</label>
          <button id="axis-x-btn" class="px-3 py-1 rounded-md border border-[var(--border)] bg-emerald-600 text-white cursor-pointer">แกน X (m)</button>
          <button id="axis-y-btn" class="px-3 py-1 rounded-md border border-[var(--border)] bg-[var(--background)] cursor-pointer">แกน Y (m)</button>
        </div>
      </div>

      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
        <h3 class="text-sm font-semibold mb-1">สัญญาณเซ็นเซอร์ 3 ตัว vs ค่าจริง vs Trusted Display Output</h3>
        <p class="text-xs text-[var(--muted-foreground)] mb-3">
          พื้นที่แรเงาสีแดง = ช่วงที่เซ็นเซอร์เสียถูกกักกัน (Quarantined) และตัดออกจาก Display/Control โดยสมบูรณ์
        </p>
        <canvas id="sensor-curves-canvas" width="1100" height="310"></canvas>
      </div>

      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
        <h3 class="text-sm font-semibold mb-1">ค่าสถิติ Pairwise Deterministic Page CUSUM (Threshold h = 4.0)</h3>
        <p class="text-xs text-[var(--muted-foreground)] mb-3">
          เมื่อเซ็นเซอร์ตัวใดดริฟ คู่ที่มีตัวนั้นทั้ง 2 คู่จะพุ่งทะลุเส้นประ h=4.0 ขณะที่คู่เซ็นเซอร์ดีอีก 1 คู่ยังอยู่ที่ 0.0
        </p>
        <canvas id="cusum-curves-canvas" width="1100" height="250"></canvas>
      </div>
    </section>

    <!-- TAB 4: FULL 20-SCENARIO MATRIX -->
    <section id="tab-matrix" class="tab-panel hidden space-y-4">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
        <h3 class="text-sm font-semibold mb-3">Heatmap: Tri-Sensor Verifier ครบทั้ง 3 เซ็นเซอร์ × 6 ประเภทอุบัติเหตุ</h3>
        <div id="heatmap-grid" class="overflow-x-auto"></div>
      </div>

      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h3 class="text-sm font-semibold">ตารางผลลัพธ์ละเอียดครบทุก 20 สถานการณ์</h3>
          <div class="flex items-center gap-2 text-xs">
            <label>กรองตามเซ็นเซอร์:</label>
            <select id="matrix-filter-sensor" class="px-2.5 py-1 rounded-md bg-[var(--background)] border border-[var(--border)]">
              <option value="ALL">ทั้งหมด (All)</option>
              <option value="S1_VIO">S1_VIO</option>
              <option value="S2_LIDAR">S2_LIDAR</option>
              <option value="S3_UWB">S3_UWB</option>
              <option value="NONE">NOMINAL</option>
              <option value="DUAL_S1_S2">DUAL_S1_S2</option>
            </select>
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-xs text-left border-collapse">
            <thead>
              <tr class="border-b border-[var(--border)] text-[var(--muted-foreground)]">
                <th class="py-2 px-2">Scenario</th>
                <th class="py-2 px-2">Target</th>
                <th class="py-2 px-2 text-right">Naive RMSE</th>
                <th class="py-2 px-2 text-right">2-Sens RMSE</th>
                <th class="py-2 px-2 text-right text-emerald-500">Tri RMSE</th>
                <th class="py-2 px-2 text-right">Est / Abst</th>
                <th class="py-2 px-2 text-right">Isolation %</th>
                <th class="py-2 px-2 text-right">Latency</th>
                <th class="py-2 px-2 text-right">False Alarm</th>
                <th class="py-2 px-2 text-right">Sim Coll Ticks</th>
                <th class="py-2 px-2 text-right">Maze Cov %</th>
              </tr>
            </thead>
            <tbody id="matrix-tbody" class="divide-y divide-[var(--border)] font-mono"></tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- TAB 5: AUDIT LOG -->
    <section id="tab-audit" class="tab-panel hidden space-y-4">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 class="text-sm font-semibold">Quarantine Audit Log (แยกออกจาก Display/Control โดยเด็ดขาด)</h3>
            <p class="text-xs text-[var(--muted-foreground)]">แสดงรายการเหตุการณ์กักกัน/ตัดค่าเสียทิ้งที่บันทึกไว้ใน <code class="text-xs">audit_quarantine_events.jsonl</code></p>
          </div>
          <select id="audit-filter" class="px-2.5 py-1 rounded-md text-xs bg-[var(--background)] border border-[var(--border)]">
            <option value="ALL">ทุกเหตุการณ์ (All Events)</option>
            <option value="QUARANTINE_ISOLATED">QUARANTINE_ISOLATED</option>
            <option value="FREEZE_DETECTED">FREEZE_DETECTED</option>
            <option value="PHYSICAL_REJECT">PHYSICAL_REJECT</option>
            <option value="FAIL_CLOSED_ABSTAIN">FAIL_CLOSED_ABSTAIN</option>
            <option value="SENSOR_RECOVERED">SENSOR_RECOVERED</option>
          </select>
        </div>
        <div class="overflow-x-auto max-h-[500px] overflow-y-auto">
          <table class="w-full text-xs text-left border-collapse">
            <thead class="sticky top-0 bg-[var(--card)] border-b border-[var(--border)] text-[var(--muted-foreground)]">
              <tr>
                <th class="py-2 px-2">Scenario</th>
                <th class="py-2 px-2">Step</th>
                <th class="py-2 px-2">Event</th>
                <th class="py-2 px-2">Sensor</th>
                <th class="py-2 px-2">Reason</th>
                <th class="py-2 px-2">Excluded Raw Value (Never Displayed)</th>
              </tr>
            </thead>
            <tbody id="audit-tbody" class="divide-y divide-[var(--border)] font-mono"></tbody>
          </table>
        </div>
      </div>
    </section>
  </div>

  <script>
    // Apply clean standalone dark theme only when opened directly in Edge/Chrome (outside Antigravity host)
    (function ensureThemeTokens() {
      const cs = getComputedStyle(document.documentElement);
      if (!cs.getPropertyValue('--background').trim()) {
        const s = document.documentElement.style;
        s.setProperty('--background', '#0f172a');
        s.setProperty('--card', '#1e293b');
        s.setProperty('--foreground', '#f1f5f9');
        s.setProperty('--muted-foreground', '#94a3b8');
        s.setProperty('--border', '#334155');
        s.setProperty('--primary', '#10b981');
        s.setProperty('--primary-foreground', '#ffffff');
      }
    })();

    const DATA = __PAYLOAD_JSON__;

    function isLight() {
      return document.documentElement.classList.contains('light');
    }
    function themeColors() {
      const light = isLight();
      return {
        text: light ? '#1e293b' : '#e2e8f0',
        muted: light ? '#64748b' : '#94a3b8',
        grid: light ? 'rgba(15,23,42,0.10)' : 'rgba(226,232,240,0.12)',
        axis: light ? 'rgba(15,23,42,0.35)' : 'rgba(226,232,240,0.35)',
        bg: light ? '#ffffff' : '#0f172a',
        pillar: light ? '#475569' : '#64748b',
      };
    }

    // Header metrics
    const triRows = DATA.summaries.filter(r => r.arm === 'TRI_SENSOR_VERIFIER');
    const naiveRows = DATA.summaries.filter(r => r.arm === 'NAIVE_AVG');
    const twoRows = DATA.summaries.filter(r => r.arm === 'TWO_SENSOR_MIN_SIGMA');
    const isNum = v => typeof v === 'number' && Number.isFinite(v);
    const fmtRmse = (v, digits = 3) => isNum(v) ? v.toFixed(digits) + ' m' : 'Unavailable';
    const avg = arr => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
    const sum = arr => arr.reduce((a, b) => a + b, 0);
    const armRmseStats = rows => {
      const vals = rows.map(r => r.position_rmse_m).filter(isNum);
      const estTotal = sum(rows.map(r => r.estimate_count ?? (r.steps - (r.abstain_steps || 0))));
      const abstTotal = sum(rows.map(r => r.abstain_steps || 0));
      const collTicks = sum(rows.map(r => r.simulation_collision_ticks ?? r.collisions ?? 0));
      return {
        mean: vals.length ? avg(vals) : null,
        worst: vals.length ? Math.max(...vals) : null,
        estTotal,
        abstTotal,
        collTicks,
      };
    };

    const sNaive = armRmseStats(naiveRows);
    const sTwo = armRmseStats(twoRows);
    const sTri = armRmseStats(triRows);

    document.getElementById('run-badge').textContent = `Run: ${DATA.run_name} (${DATA.elapsed_seconds}s)`;
    document.getElementById('hdr-rmse').textContent = fmtRmse(sTri.mean, 3);
    document.getElementById('hdr-audit').textContent = DATA.total_audit_events + ' events';

    // KPI Cards
    const kpis = [
      {
        title: 'Naive Average Baseline',
        stats: sNaive,
        color: 'text-rose-500',
        note: `Est: ${sNaive.estTotal} · Abstain: ${sNaive.abstTotal} · Sim Collision Ticks: ${sNaive.collTicks}`
      },
      {
        title: 'Two-Sensor Min-Sigma Baseline',
        stats: sTwo,
        color: 'text-amber-500',
        note: `Est: ${sTwo.estTotal} · Abstain: ${sTwo.abstTotal} · Sim Collision Ticks: ${sTwo.collTicks}`
      },
      {
        title: 'Tri-Sensor Verifier (Proposed)',
        stats: sTri,
        color: 'text-emerald-500',
        note: `Est: ${sTri.estTotal} · Abstain: ${sTri.abstTotal} · Sim Collision Ticks: ${sTri.collTicks} · Mean Iso ${avg(triRows.map(r => r.isolation_accuracy_pct)).toFixed(1)}%`
      }
    ];
    document.getElementById('kpi-cards').innerHTML = kpis.map(k => `
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-[var(--muted-foreground)]">${k.title}</div>
        <div class="mt-2 flex items-baseline gap-3">
          <span class="text-2xl font-bold ${k.color}">${fmtRmse(k.stats.mean, 3)}</span>
          <span class="text-xs text-[var(--muted-foreground)]">Mean RMSE (Worst: ${fmtRmse(k.stats.worst, 2)})</span>
        </div>
        <div class="mt-2 text-xs text-[var(--muted-foreground)]">${k.note}</div>
      </div>
    `).join('');

    // Tab switching
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');
    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.tab;
        tabBtns.forEach(b => {
          b.classList.toggle('active', b === btn);
          if (b !== btn) b.classList.add('bg-[var(--card)]');
          else b.classList.remove('bg-[var(--card)]');
        });
        tabPanels.forEach(p => p.classList.toggle('hidden', p.id !== 'tab-' + target));
        if (target === 'overview') drawOverviewRmse();
        if (target === 'maze') drawMaze();
        if (target === 'curves') drawCurves();
      });
    });

    // ---------------- TAB 1: Overview Bar Chart ----------------
    function drawOverviewRmse() {
      const c = document.getElementById('overview-rmse-canvas');
      const ctx = c.getContext('2d');
      const tc = themeColors();
      const W = c.width, H = c.height;
      ctx.clearRect(0, 0, W, H);

      const pad = { l: 55, r: 20, t: 25, b: 115 };
      const plotW = W - pad.l - pad.r;
      const plotH = H - pad.t - pad.b;

      const scenIds = [...new Set(DATA.summaries.map(r => r.scenario_id))];
      const maxVal = 4.6;

      // Grid
      ctx.strokeStyle = tc.grid;
      ctx.fillStyle = tc.muted;
      ctx.font = '12px sans-serif';
      for (let v = 0; v <= 4.5; v += 0.5) {
        const y = pad.t + plotH - (v / maxVal) * plotH;
        ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
        if (Math.abs(v % 1) < 0.01) {
          ctx.fillText(v.toFixed(1) + 'm', 8, y + 4);
        }
      }

      const groupW = plotW / scenIds.length;
      const barW = Math.max(4, (groupW - 8) / 3);
      const colors = ['#ef4444', '#f59e0b', '#10b981'];
      const arms = ['NAIVE_AVG', 'TWO_SENSOR_MIN_SIGMA', 'TRI_SENSOR_VERIFIER'];

      scenIds.forEach((sid, i) => {
        const gx = pad.l + i * groupW + 4;
        arms.forEach((arm, j) => {
          const row = DATA.summaries.find(r => r.scenario_id === sid && r.arm === arm);
          const rawVal = row ? row.position_rmse_m : null;
          const val = isNum(rawVal) ? Math.min(maxVal, rawVal) : 0;
          const bh = (val / maxVal) * plotH;
          const x = gx + j * barW;
          const y = pad.t + plotH - bh;
          ctx.fillStyle = colors[j];
          ctx.fillRect(x, y, barW - 1, bh);
        });
        ctx.save();
        ctx.translate(gx + groupW * 0.45, pad.t + plotH + 10);
        ctx.rotate(Math.PI / 4.2);
        ctx.fillStyle = tc.text;
        ctx.font = '11px monospace';
        ctx.fillText(sid.slice(3), 0, 0);
        ctx.restore();
      });
    }

    // ---------------- TAB 2: Interactive Maze Replay ----------------
    const showcaseKeys = Object.keys(DATA.showcase);
    const mazeSel = document.getElementById('maze-scenario-select');
    const curvesSel = document.getElementById('curves-scenario-select');
    showcaseKeys.forEach(k => {
      const opt1 = document.createElement('option'); opt1.value = k; opt1.textContent = k; mazeSel.appendChild(opt1);
      const opt2 = document.createElement('option'); opt2.value = k; opt2.textContent = k; curvesSel.appendChild(opt2);
    });
    mazeSel.value = '04_S1_VIO_HEAVY_DRIFT';
    curvesSel.value = '04_S1_VIO_HEAVY_DRIFT';

    let replayStep = 44;
    let playTimer = null;
    const slider = document.getElementById('step-slider');
    const stepLbl = document.getElementById('step-label');

    function setStep(s) {
      replayStep = Math.max(0, Math.min(44, s));
      slider.value = replayStep;
      stepLbl.textContent = `Step ${replayStep}/44`;
      drawMaze();
    }
    slider.addEventListener('input', e => setStep(parseInt(e.target.value, 10)));
    mazeSel.addEventListener('change', () => drawMaze());
    document.getElementById('btn-play').addEventListener('click', () => {
      if (playTimer) clearInterval(playTimer);
      if (replayStep >= 44) setStep(0);
      playTimer = setInterval(() => {
        if (replayStep >= 44) { clearInterval(playTimer); playTimer = null; return; }
        setStep(replayStep + 1);
      }, 180);
    });
    document.getElementById('btn-pause').addEventListener('click', () => {
      if (playTimer) { clearInterval(playTimer); playTimer = null; }
    });

    function drawMaze() {
      const c = document.getElementById('maze-canvas');
      const ctx = c.getContext('2d');
      const tc = themeColors();
      const W = c.width, H = c.height;
      ctx.clearRect(0, 0, W, H);

      const sid = mazeSel.value;
      const tri = DATA.showcase[sid].TRI_SENSOR_VERIFIER;
      const naive = DATA.showcase[sid].NAIVE_AVG;
      const pad = 42;
      const size = Math.min(W - pad * 2, H - pad * 2);
      const ox = (W - size) / 2;
      const oy = (H - size) / 2;
      const mapX = x => ox + ((x + 5) / 10) * size;
      const mapY = y => oy + size - ((y + 5) / 10) * size;

      // Arena box & grid
      ctx.strokeStyle = tc.grid;
      for (let g = -5; g <= 5; g++) {
        ctx.beginPath(); ctx.moveTo(mapX(g), mapY(-5)); ctx.lineTo(mapX(g), mapY(5)); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(mapX(-5), mapY(g)); ctx.lineTo(mapX(5), mapY(g)); ctx.stroke();
      }
      ctx.strokeStyle = tc.axis;
      ctx.lineWidth = 2;
      ctx.strokeRect(ox, oy, size, size);

      // 5 Pillars
      DATA.pillars.forEach(([px, py, pr]) => {
        ctx.beginPath();
        ctx.arc(mapX(px), mapY(py), (pr / 10) * size, 0, Math.PI * 2);
        ctx.fillStyle = tc.pillar;
        ctx.fill();
      });

      // Naive Path (red dashed)
      ctx.beginPath();
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      naive.slice(0, replayStep + 1).forEach((r, i) => {
        if (i === 0) ctx.moveTo(mapX(r.tx), mapY(r.ty));
        else ctx.lineTo(mapX(r.tx), mapY(r.ty));
      });
      ctx.stroke();
      ctx.setLineDash([]);

      // Tri-Verifier True Path (blue solid)
      ctx.beginPath();
      ctx.strokeStyle = '#0ea5e9';
      ctx.lineWidth = 3;
      tri.slice(0, replayStep + 1).forEach((r, i) => {
        if (i === 0) ctx.moveTo(mapX(r.tx), mapY(r.ty));
        else ctx.lineTo(mapX(r.tx), mapY(r.ty));
      });
      ctx.stroke();

      // Trusted Display dots (green)
      tri.slice(0, replayStep + 1).forEach(r => {
        if (r.dx !== null) {
          ctx.beginPath();
          ctx.arc(mapX(r.dx), mapY(r.dy), 3.5, 0, Math.PI * 2);
          ctx.fillStyle = '#10b981';
          ctx.fill();
        }
      });

      // Current step robot & raw 3 sensors
      const cur = tri[replayStep];
      // Draw raw S1, S2, S3 markers at current step
      const rawSensors = [
        { id: 'S1_VIO', x: cur.s1x, y: cur.s1y, col: '#f43f5e' },
        { id: 'S2_LIDAR', x: cur.s2x, y: cur.s2y, col: '#a855f7' },
        { id: 'S3_UWB', x: cur.s3x, y: cur.s3y, col: '#eab308' },
      ];
      rawSensors.forEach(s => {
        if (s.x !== null && s.y !== null) {
          const cx = Math.max(ox, Math.min(ox + size, mapX(s.x)));
          const cy = Math.max(oy, Math.min(oy + size, mapY(s.y)));
          ctx.beginPath();
          ctx.arc(cx, cy, 5, 0, Math.PI * 2);
          ctx.strokeStyle = s.col;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      });

      // Robot true position
      ctx.beginPath();
      ctx.arc(mapX(cur.tx), mapY(cur.ty), 7, 0, Math.PI * 2);
      ctx.fillStyle = '#0ea5e9';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Legend
      ctx.font = '12px sans-serif';
      ctx.fillStyle = tc.text;
      ctx.fillText('● True Path (Tri-Verifier)   ● Trusted Display   -- Naive Path (No Check)   ○ Raw S1/S2/S3', ox, oy - 12);

      // Update Live Side Panel
      const qList = cur.q ? cur.q.split('|') : [];
      const uList = cur.u ? cur.u.split('|') : [];
      document.getElementById('maze-live-panel').innerHTML = `
        <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
          <div class="text-[var(--muted-foreground)]">Mode / Action</div>
          <div class="font-bold text-sm mt-0.5 ${cur.tr ? 'text-emerald-500' : 'text-rose-500'}">${cur.m} (${cur.a})</div>
        </div>
        <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)] space-y-1 font-mono">
          <div><span class="text-[var(--muted-foreground)]">Ground Truth:</span> (${cur.tx.toFixed(2)}, ${cur.ty.toFixed(2)})</div>
          <div><span class="text-emerald-500">Trusted Display:</span> ${cur.dx !== null ? `(${cur.dx.toFixed(2)}, ${cur.dy.toFixed(2)})` : '<span class="text-rose-500">BLOCKED (ABSTAIN)</span>'}</div>
          <div><span class="text-[var(--muted-foreground)]">Display Error:</span> ${cur.err !== null ? cur.err.toFixed(3) + ' m' : 'N/A (Safe Stop)'}</div>
          <div><span class="text-[var(--muted-foreground)]">Maze Coverage:</span> ${cur.cov.toFixed(1)}%</div>
        </div>
        <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)] space-y-1">
          <div class="font-semibold text-emerald-500">Active Trusted Sensors (${uList.length})</div>
          <div class="font-mono">${uList.length ? uList.join(', ') : 'None (Fail-Closed)'}</div>
        </div>
        <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)] space-y-1">
          <div class="font-semibold text-rose-500">Quarantined &amp; Excluded (${qList.length})</div>
          <div class="font-mono text-rose-400">${qList.length ? qList.join('<br>') : 'None — All Healthy'}</div>
        </div>
        <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)] space-y-1 font-mono">
          <div class="text-[var(--muted-foreground)] font-sans font-semibold">Page CUSUM (Alarm &gt; 4.0)</div>
          <div>S1 vs S2: <strong>${cur.c12}</strong></div>
          <div>S2 vs S3: <strong>${cur.c23}</strong></div>
          <div>S1 vs S3: <strong>${cur.c13}</strong></div>
        </div>
      `;
    }

    // ---------------- TAB 3: Drift & Page CUSUM Curves ----------------
    let selectedAxis = 'x';
    document.getElementById('axis-x-btn').addEventListener('click', () => {
      selectedAxis = 'x';
      document.getElementById('axis-x-btn').className = 'px-3 py-1 rounded-md border border-[var(--border)] bg-emerald-600 text-white cursor-pointer';
      document.getElementById('axis-y-btn').className = 'px-3 py-1 rounded-md border border-[var(--border)] bg-[var(--background)] cursor-pointer';
      drawCurves();
    });
    document.getElementById('axis-y-btn').addEventListener('click', () => {
      selectedAxis = 'y';
      document.getElementById('axis-y-btn').className = 'px-3 py-1 rounded-md border border-[var(--border)] bg-emerald-600 text-white cursor-pointer';
      document.getElementById('axis-x-btn').className = 'px-3 py-1 rounded-md border border-[var(--border)] bg-[var(--background)] cursor-pointer';
      drawCurves();
    });
    curvesSel.addEventListener('change', () => drawCurves());

    function drawLinePlot(canvasId, seriesList, yRange, opts = {}) {
      const c = document.getElementById(canvasId);
      const ctx = c.getContext('2d');
      const tc = themeColors();
      const W = c.width, H = c.height;
      ctx.clearRect(0, 0, W, H);
      const pad = { l: 58, r: 24, t: 28, b: 36 };
      const plotW = W - pad.l - pad.r;
      const plotH = H - pad.t - pad.b;
      const N = seriesList[0].vals.length;
      const mx = i => pad.l + (i / Math.max(1, N - 1)) * plotW;
      const my = v => pad.t + plotH - ((v - yRange[0]) / Math.max(1e-6, yRange[1] - yRange[0])) * plotH;

      // Quarantine shaded region
      if (opts.quarStart !== null && opts.quarStart !== undefined) {
        ctx.fillStyle = 'rgba(239, 68, 68, 0.12)';
        const qx = mx(opts.quarStart);
        ctx.fillRect(qx, pad.t, W - pad.r - qx, plotH);
      }

      // Grid
      ctx.strokeStyle = tc.grid;
      ctx.fillStyle = tc.muted;
      ctx.font = '12px sans-serif';
      for (let k = 0; k <= 4; k++) {
        const v = yRange[0] + (k / 4) * (yRange[1] - yRange[0]);
        const y = my(v);
        ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
        ctx.fillText(v.toFixed(1), 8, y + 4);
      }
      for (let s = 0; s < N; s += 5) {
        const x = mx(s);
        ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, pad.t + plotH); ctx.stroke();
        ctx.fillText('' + s, x - 6, H - 12);
      }

      // Optional horizontal threshold
      if (opts.hLine !== undefined) {
        ctx.strokeStyle = tc.axis;
        ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(pad.l, my(opts.hLine)); ctx.lineTo(W - pad.r, my(opts.hLine)); ctx.stroke();
        ctx.setLineDash([]);
      }
      // Fault onset vertical line at step 12
      if (opts.faultStart >= 0) {
        ctx.strokeStyle = '#f59e0b';
        ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(mx(opts.faultStart), pad.t); ctx.lineTo(mx(opts.faultStart), pad.t + plotH); ctx.stroke();
        ctx.setLineDash([]);
      }

      // Series
      seriesList.forEach(ser => {
        ctx.beginPath();
        ctx.strokeStyle = ser.color;
        ctx.lineWidth = ser.width || 2;
        if (ser.dash) ctx.setLineDash(ser.dash);
        let started = false;
        ser.vals.forEach((v, i) => {
          if (v === null || v === undefined || Number.isNaN(v)) { started = false; return; }
          const cv = Math.max(yRange[0], Math.min(yRange[1], v));
          if (!started) { ctx.moveTo(mx(i), my(cv)); started = true; }
          else ctx.lineTo(mx(i), my(cv));
        });
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // Legend
      let lx = pad.l;
      ctx.font = '12px sans-serif';
      seriesList.forEach(ser => {
        ctx.fillStyle = ser.color;
        ctx.fillRect(lx, 8, 12, 4);
        ctx.fillStyle = tc.text;
        ctx.fillText(ser.label, lx + 16, 14);
        lx += ctx.measureText(ser.label).width + 36;
      });
    }

    function drawCurves() {
      const sid = curvesSel.value;
      const rows = DATA.showcase[sid].TRI_SENSOR_VERIFIER;
      const kT = selectedAxis === 'x' ? 'tx' : 'ty';
      const k1 = selectedAxis === 'x' ? 's1x' : 's1y';
      const k2 = selectedAxis === 'x' ? 's2x' : 's2y';
      const k3 = selectedAxis === 'x' ? 's3x' : 's3y';
      const kD = selectedAxis === 'x' ? 'dx' : 'dy';

      const qRow = rows.find(r => r.q && r.q.length > 0);
      const quarStart = qRow ? qRow.step : null;
      const allVals = rows.flatMap(r => [r[kT], r[k1], r[k2], r[k3], r[kD]]).filter(v => v !== null && !Number.isNaN(v));
      const yMin = Math.max(-7, Math.min(...allVals) - 0.5);
      const yMax = Math.min(8, Math.max(...allVals) + 0.5);

      drawLinePlot('sensor-curves-canvas', [
        { label: 'Ground Truth', vals: rows.map(r => r[kT]), color: isLight() ? '#0f172a' : '#f8fafc', width: 2.8 },
        { label: 'S1_VIO', vals: rows.map(r => r[k1]), color: '#ef4444', width: 1.6, dash: [5, 3] },
        { label: 'S2_LIDAR', vals: rows.map(r => r[k2]), color: '#3b82f6', width: 1.6 },
        { label: 'S3_UWB', vals: rows.map(r => r[k3]), color: '#a855f7', width: 1.6 },
        { label: 'Trusted Display Output', vals: rows.map(r => r[kD]), color: '#10b981', width: 2.8, dash: [8, 3] },
      ], [yMin, yMax], { quarStart, faultStart: sid.startsWith('00_') ? -1 : 12 });

      drawLinePlot('cusum-curves-canvas', [
        { label: 'CUSUM (S1 vs S2)', vals: rows.map(r => r.c12), color: '#ef4444', width: 2.2 },
        { label: 'CUSUM (S1 vs S3)', vals: rows.map(r => r.c13), color: '#f97316', width: 2.2, dash: [6, 3] },
        { label: 'CUSUM (S2 vs S3)', vals: rows.map(r => r.c23), color: '#10b981', width: 2.4 },
      ], [0, 42], { quarStart, faultStart: sid.startsWith('00_') ? -1 : 12, hLine: 4.0 });
    }

    // ---------------- TAB 4: Matrix & Heatmap ----------------
    function renderMatrix() {
      const sensors = ['S1_VIO', 'S2_LIDAR', 'S3_UWB'];
      const faults = ['GRADUAL_DRIFT', 'HEAVY_DRIFT', 'SUDDEN_BIAS', 'OUTLIER_BURSTS', 'RETIMESTAMPED_FREEZE', 'SENSOR_BLACKOUT'];

      let hm = `<table class="w-full text-xs border-collapse text-center"><thead><tr class="border-b border-[var(--border)]"><th class="py-2 px-2 text-left">Sensor</th>`;
      faults.forEach(f => { hm += `<th class="py-2 px-2">${f}</th>`; });
      hm += `</tr></thead><tbody>`;
      sensors.forEach(s => {
        hm += `<tr class="border-b border-[var(--border)]"><td class="py-2 px-2 text-left font-bold font-mono">${s}</td>`;
        faults.forEach(f => {
          const r = triRows.find(x => x.target_sensor === s && x.fault_category === f);
          const lat = r.detection_latency_steps !== null ? r.detection_latency_steps + 's' : '-';
          const est = r.estimate_count ?? (r.steps - (r.abstain_steps || 0));
          hm += `<td class="py-2 px-2"><div class="rounded-md py-1.5 px-2 bg-emerald-500/15 border border-emerald-500/30 font-mono">
            <div class="font-bold text-emerald-500">${fmtRmse(r.position_rmse_m, 3)}</div>
            <div class="text-[var(--muted-foreground)]">Est ${est}/${r.steps} · Iso ${r.isolation_accuracy_pct}% · Lat ${lat}</div>
          </div></td>`;
        });
        hm += `</tr>`;
      });
      hm += `</tbody></table>`;
      document.getElementById('heatmap-grid').innerHTML = hm;

      const filterVal = document.getElementById('matrix-filter-sensor').value;
      const scenIds = [...new Set(DATA.summaries.map(r => r.scenario_id))];
      const tbody = document.getElementById('matrix-tbody');
      tbody.innerHTML = scenIds.map(sid => {
        const rn = DATA.summaries.find(r => r.scenario_id === sid && r.arm === 'NAIVE_AVG');
        const r2 = DATA.summaries.find(r => r.scenario_id === sid && r.arm === 'TWO_SENSOR_MIN_SIGMA');
        const r3 = DATA.summaries.find(r => r.scenario_id === sid && r.arm === 'TRI_SENSOR_VERIFIER');
        if (filterVal !== 'ALL' && r3.target_sensor !== filterVal) return '';
        const est3 = r3.estimate_count ?? (r3.steps - (r3.abstain_steps || 0));
        const abst3 = r3.abstain_steps || 0;
        const coll3 = r3.simulation_collision_ticks ?? r3.collisions ?? 0;
        return `<tr class="hover:bg-[var(--background)]">
          <td class="py-2 px-2">${sid}</td>
          <td class="py-2 px-2">${r3.target_sensor}</td>
          <td class="py-2 px-2 text-right ${isNum(rn.position_rmse_m) && rn.position_rmse_m > 0.2 ? 'text-rose-500 font-bold' : ''}">${fmtRmse(rn.position_rmse_m, 3)}</td>
          <td class="py-2 px-2 text-right ${isNum(r2.position_rmse_m) && r2.position_rmse_m > 0.2 ? 'text-amber-500 font-bold' : ''}">${fmtRmse(r2.position_rmse_m, 3)}</td>
          <td class="py-2 px-2 text-right text-emerald-500 font-bold">${fmtRmse(r3.position_rmse_m, 3)}</td>
          <td class="py-2 px-2 text-right">${est3} / ${abst3}</td>
          <td class="py-2 px-2 text-right">${r3.isolation_accuracy_pct.toFixed(1)}%</td>
          <td class="py-2 px-2 text-right">${r3.detection_latency_steps !== null ? r3.detection_latency_steps + ' step' : '-'}</td>
          <td class="py-2 px-2 text-right">${r3.false_alarm_rate_pct.toFixed(1)}%</td>
          <td class="py-2 px-2 text-right">${coll3}</td>
          <td class="py-2 px-2 text-right">${r3.true_maze_coverage_pct.toFixed(1)}%</td>
        </tr>`;
      }).join('');
    }
    document.getElementById('matrix-filter-sensor').addEventListener('change', renderMatrix);

    // ---------------- TAB 5: Audit Log ----------------
    function renderAudit() {
      const f = document.getElementById('audit-filter').value;
      const rows = DATA.audit_sample.filter(e => f === 'ALL' || e.event === f);
      document.getElementById('audit-tbody').innerHTML = rows.map(e => `
        <tr class="hover:bg-[var(--background)]">
          <td class="py-1.5 px-2">${e.scenario_id}</td>
          <td class="py-1.5 px-2">${e.step}</td>
          <td class="py-1.5 px-2 font-semibold ${e.event.includes('ABSTAIN') ? 'text-amber-500' : 'text-rose-500'}">${e.event}</td>
          <td class="py-1.5 px-2">${e.sensor_id || 'ALL'}</td>
          <td class="py-1.5 px-2">${e.reason || e.previous_reason || ''}</td>
          <td class="py-1.5 px-2 text-[var(--muted-foreground)]">${JSON.stringify(e.excluded_raw_values || {})}</td>
        </tr>
      `).join('');
    }
    document.getElementById('audit-filter').addEventListener('change', renderAudit);

    // Initial render
    drawOverviewRmse();
    renderMatrix();
    renderAudit();
  </script>
</body>
</html>
"""


def _compact_showcase(showcase: Dict[str, Dict[str, List[Dict[str, Any]]]]) -> Dict[str, Any]:
    """Compress telemetry keys so the self-contained HTML dashboard stays lightweight."""
    def num(v: Any) -> Any:
        if v == "" or v is None or v == "NaN":
            return None
        try:
            f = float(v)
            return None if (f != f) else round(f, 3)
        except Exception:
            return None

    out: Dict[str, Any] = {}
    for sid, arm_map in showcase.items():
        out[sid] = {}
        for arm in ("NAIVE_AVG", "TRI_SENSOR_VERIFIER"):
            rows = arm_map.get(arm, [])
            compact = []
            for r in rows:
                compact.append({
                    "step": r["step"],
                    "tx": num(r["true_x"]), "ty": num(r["true_y"]),
                    "s1x": num(r["s1_x"]), "s1y": num(r["s1_y"]),
                    "s2x": num(r["s2_x"]), "s2y": num(r["s2_y"]),
                    "s3x": num(r["s3_x"]), "s3y": num(r["s3_y"]),
                    "dx": num(r["display_x"]), "dy": num(r["display_y"]),
                    "tr": bool(r["trusted"]),
                    "m": r["mode"], "a": r["action"],
                    "u": r["used_sensors"], "q": r["quarantined_sensors"],
                    "err": num(r["display_error_m"]),
                    "c12": num(r["cusum_s1_s2"]) or 0,
                    "c23": num(r["cusum_s2_s3"]) or 0,
                    "c13": num(r["cusum_s1_s3"]) or 0,
                    "cov": num(r["true_maze_coverage_pct"]) or 0,
                })
            out[sid][arm] = compact
    return out


def build_dashboard(run_dir: str | None = None) -> Path:
    root = Path(run_dir) if run_dir else Path(Path("research/tri_sensor_verification/logs/LATEST_RUN.txt").read_text(encoding="utf-8").strip())
    raw = json.loads((root / "dashboard_payload.json").read_text(encoding="utf-8"))
    compact_payload = {
        "run_name": raw["run_name"],
        "elapsed_seconds": raw["elapsed_seconds"],
        "pillars": raw["pillars"],
        "bounds": raw["bounds"],
        "summaries": raw["summaries"],
        "showcase": _compact_showcase(raw["showcase"]),
        "audit_sample": raw["audit_sample"][:100],
        "total_audit_events": raw["total_audit_events"],
    }
    html = HTML_TEMPLATE.replace("__PAYLOAD_JSON__", json.dumps(compact_payload))
    out_path = root / "dashboard.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Built interactive multi-tab dashboard ({len(html)/1024:.1f} KB): {out_path}")
    return out_path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    build_dashboard(arg)
