#!/usr/bin/env python3
"""NEXVIA AEGIS — Plot Publication Confirmatory Holdout Certification Figures.

Generates 4-panel publication-grade figures (300 DPI) in results/plots/holdout_h1_h5_certification.png:
  1. H1 Selective Risk Control & Coverage Floor (Mixture Holdout, N=1,440).
  2. H2 & H4 False Success Elimination vs Baselines (Mixture & Compound Scenarios).
  3. H3 Operational Utility & TSR Noninferiority vs V8.1 and V7.
  4. H5 Worst-Case Scenario Safety via Berger IUT across all 12 Stratified Scenarios.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

import matplotlib.pyplot as plt
import numpy as np

plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams.update({
    "font.sans-serif": "DejaVu Sans",
    "font.family": "sans-serif",
    "figure.titlesize": 16,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 10,
    "figure.dpi": 300,
})

out_dir = _REPO_ROOT / "results" / "plots"
out_dir.mkdir(parents=True, exist_ok=True)

fig, axs = plt.subplots(2, 2, figsize=(15, 12))

# -----------------------------------------------------------------------------
# Panel 1: H1 Selective Risk Control & Coverage
# -----------------------------------------------------------------------------
ax1 = axs[0, 0]
categories = ["Nominal Upper Bound", "CP 95% UCB (Observed)", "Observed Point Estimate"]
values = [0.05, 0.003418, 0.0]
colors = ["#e74c3c", "#3498db", "#2ecc71"]

bars = ax1.bar(categories, values, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
ax1.axhline(0.05, color="#e74c3c", linestyle="--", linewidth=1.8, label=r"Preregistered Risk Ceiling $\alpha=0.05$")
ax1.set_ylabel(r"Selective Risk $\hat{R}_{\mathrm{sel}}$")
ax1.set_title(r"$\mathbf{H_1}$: Selective Risk Control on Mixture Holdout ($N=1{,}440$)", fontweight="bold")
ax1.set_ylim(-0.002, 0.06)

for bar, val in zip(bars, values):
    height = bar.get_height()
    label = f"{val*100:.3f}%" if val > 0 else "0.00% (0 / 875)"
    ax1.annotate(
        label,
        xy=(bar.get_x() + bar.get_width() / 2, height),
        xytext=(0, 6),
        textcoords="offset points",
        ha="center", va="bottom",
        fontweight="bold", fontsize=10,
    )

ax1.annotate(
    r"Coverage $\hat{C} = 60.76\% \geq 35.0\%$ Floor" "\n"
    r"CP UCB$_{95} = 0.342\% \ll 5.000\%$" "\n"
    r"$\mathbf{VERDICT: CONFIRMATORY\_PASS}$",
    xy=(0.55, 0.60), xycoords="axes fraction",
    bbox=dict(boxstyle="round,pad=0.6", facecolor="#e8f8f5", edgecolor="#2ecc71", linewidth=1.5),
    fontsize=10, fontweight="bold",
)
ax1.legend(loc="upper left")

# -----------------------------------------------------------------------------
# Panel 2: H2 & H4 False Success Elimination vs Baselines
# -----------------------------------------------------------------------------
ax2 = axs[0, 1]
x_pos = np.arange(2)
width = 0.25

v9_fs = [0, 0]
v8_fs = [12, 12]
v7_fs = [40, 30]

rects1 = ax2.bar(x_pos - width, v9_fs, width, label="V9 Certified Policy", color="#2ecc71", edgecolor="black")
rects2 = ax2.bar(x_pos, v8_fs, width, label="V8.1 Martingale Baseline", color="#f39c12", edgecolor="black")
rects3 = ax2.bar(x_pos + width, v7_fs, width, label="V7 MPC Baseline", color="#e74c3c", edgecolor="black")

ax2.set_ylabel("False Success Arrivals (Count)")
ax2.set_title(r"$\mathbf{H_2}$ & $\mathbf{H_4}$: Unconditional False Success Elimination", fontweight="bold")
ax2.set_xticks(x_pos)
ax2.set_xticklabels([r"Mixture Holdout $\mathcal{D}_{\mathrm{test}}^{\mathrm{mix}}$ ($N=1{,}440$)", r"4 Compound Scenarios ($N=480$)"])
ax2.legend(loc="upper right")

for bar in rects1:
    ax2.annotate("0", xy=(bar.get_x() + bar.get_width() / 2, 0), xytext=(0, 5),
                 textcoords="offset points", ha="center", va="bottom", fontweight="bold")
for bar, val in zip(rects2, v8_fs):
    ax2.annotate(f"{val}", xy=(bar.get_x() + bar.get_width() / 2, val), xytext=(0, 5),
                 textcoords="offset points", ha="center", va="bottom", fontweight="bold")
for bar, val in zip(rects3, v7_fs):
    ax2.annotate(f"{val}", xy=(bar.get_x() + bar.get_width() / 2, val), xytext=(0, 5),
                 textcoords="offset points", ha="center", va="bottom", fontweight="bold")

ax2.annotate(
    r"Mixture vs V8.1: $p = 4.88 \times 10^{-4}$" "\n"
    r"Mixture vs V7: $p = 1.82 \times 10^{-12}$" "\n"
    r"Compound vs V8.1: $p = 4.88 \times 10^{-4}$" "\n"
    r"$\mathbf{100\% \ Zero\ False\ Success\ Invariant}$",
    xy=(0.04, 0.62), xycoords="axes fraction",
    bbox=dict(boxstyle="round,pad=0.5", facecolor="#fef9e7", edgecolor="#f39c12", linewidth=1.5),
    fontsize=9.5, fontweight="bold",
)

# -----------------------------------------------------------------------------
# Panel 3: H3 Operational Utility & TSR Noninferiority
# -----------------------------------------------------------------------------
ax3 = axs[1, 0]
baselines = ["vs V8.1 Martingale", "vs V7 MPC Baseline"]
mean_deltas = [11.3333, 10.0833]
lcb_wald = [9.2585, 8.0814]
lcb_newcombe = [9.2529, 8.0773]

y_pos = np.arange(len(baselines))
ax3.barh(y_pos - 0.15, mean_deltas, height=0.28, color="#3498db", edgecolor="black", label=r"Mean Paired $\Delta \mathrm{TSR}$ (%)")
ax3.barh(y_pos + 0.15, lcb_wald, height=0.28, color="#2ecc71", edgecolor="black", label=r"Student-t Wald $\mathrm{LCB}_{95}$ (%)")

ax3.axvline(-5.0, color="#e74c3c", linestyle="--", linewidth=1.8, label=r"Noninferiority Margin ($-5.0\%$)")
ax3.axvline(0.0, color="gray", linestyle=":", linewidth=1.2, label=r"Parity ($0.0\%$)")
ax3.set_xlabel(r"Task Success Rate Improvement $\Delta \mathrm{TSR}$ (%)")
ax3.set_title(r"$\mathbf{H_3}$: Operational Utility & TSR Noninferiority ($N=1{,}200$ in $S_{10}$)", fontweight="bold")
ax3.set_yticks(y_pos)
ax3.set_yticklabels(baselines, fontweight="bold")
ax3.legend(loc="lower right")

for i, (m, l) in enumerate(zip(mean_deltas, lcb_wald)):
    ax3.annotate(f"+{m:.2f}% (LCB: +{l:.2f}%)", xy=(m, i - 0.15), xytext=(6, 0),
                 textcoords="offset points", ha="left", va="center", fontweight="bold", fontsize=9.5)

ax3.annotate(
    r"Nominal TSR $= 100.0\% \geq 94.0\%$ Target" "\n"
    r"Strict Superiority over V8.1: $+11.33\%$ ($p < 10^{-20}$)" "\n"
    r"Strict Superiority over V7: $+10.08\%$ ($p < 10^{-18}$)" "\n"
    r"$\mathbf{VERDICT: CONFIRMATORY\_PASS}$",
    xy=(0.04, 0.15), xycoords="axes fraction",
    bbox=dict(boxstyle="round,pad=0.5", facecolor="#ebf5fb", edgecolor="#3498db", linewidth=1.5),
    fontsize=9.5, fontweight="bold",
)

# -----------------------------------------------------------------------------
# Panel 4: H5 Worst-Case Scenario Safety via Berger IUT
# -----------------------------------------------------------------------------
ax4 = axs[1, 1]
scen_labels = [
    "01_NOM", "02_PRI_B", "03_IND_B", "04_COR_B", "05_DRIFT", "06_OUTL",
    "07_DROP", "08_FAULT", "09_CORR_A", "10_EXTR", "11_DR_DP", "12_ANTIP"
]
p_values = [0.002122] * 12

x_scen = np.arange(len(scen_labels))
bars4 = ax4.bar(x_scen, p_values, color="#9b59b6", edgecolor="black", width=0.6)
ax4.axhline(0.05, color="#e74c3c", linestyle="--", linewidth=1.8, label=r"IUT Safety Threshold $\alpha=0.05$")
ax4.set_ylabel(r"Exact Binomial $p$-value ($H_0: p \geq 0.05$)")
ax4.set_title(r"$\mathbf{H_5}$: Worst-Case Safety via Berger IUT across 12 Scenarios", fontweight="bold")
ax4.set_xticks(x_scen)
ax4.set_xticklabels(scen_labels, rotation=45, ha="right", fontsize=8.5)
ax4.set_ylim(0, 0.065)
ax4.legend(loc="upper right")

for bar in bars4:
    ax4.annotate("0.002", xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                 xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)

ax4.annotate(
    r"Berger IUT Estimand: $\max_{s}(p_s) = 0.002122 \leq 0.05$" "\n"
    r"Holm-Šidák Step-Down: 12 / 12 Rejected ($\alpha=0.05$)" "\n"
    r"Zero False Successes across all 12 Scenarios" "\n"
    r"$\mathbf{VERDICT: CONFIRMATORY\_PASS\_IUT}$",
    xy=(0.04, 0.65), xycoords="axes fraction",
    bbox=dict(boxstyle="round,pad=0.5", facecolor="#f4ecf7", edgecolor="#9b59b6", linewidth=1.5),
    fontsize=9.5, fontweight="bold",
)

plt.tight_layout()
out_fig_path = out_dir / "holdout_h1_h5_certification.png"
fig.savefig(out_fig_path, dpi=300)
plt.close(fig)

print(f"[PLOT] Confirmatory Holdout Certification figure saved to: {out_fig_path}")
