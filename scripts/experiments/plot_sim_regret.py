"""Regret of each search method's pick against the exact optimum, by budget (budget study).

Run:  python3 scripts/experiments/plot_sim_regret.py data/bo_sim_runs/20261014-1628_budget_n1e6
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
run = Path(sys.argv[1])
df = pd.read_csv(run / "runs.csv")
budgets = sorted(df.budget.unique())
fig, ax = plt.subplots(figsize=(6.4, 3.8))
for off, (m, label, col) in zip((-0.025, 0.025), [("bo", "Bayesian optimisation (GP, EI)", "#1f6fb4"),
                                                 ("random", "Random search", "#d17a12")]):
    q = [np.percentile(df[(df.method == m) & (df.budget == b)].regret * 100, [25, 50, 75]) for b in budgets]
    q = np.array(q)
    x = np.log10(budgets) + off
    ax.errorbar(10 ** x, q[:, 1], yerr=[q[:, 1] - q[:, 0], q[:, 2] - q[:, 1]], fmt="o-", color=col,
                capsize=3, label=label)
ax.axhline(5, color="0.5", ls=":", lw=1, label="5% of the optimum")
ax.set_xscale("log")
ax.set_xticks(budgets)
ax.set_xticklabels([str(b) for b in budgets])
ax.minorticks_off()
ax.set_xlabel("Evaluation budget")
ax.set_ylabel("Regret of the pick (% above optimum)")
ax.set_title("Regret against the exact optimum (median and IQR, 30 seeds)", fontsize=10)
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(ROOT / "figures" / "sim_regret_vs_budget.png", dpi=200)
print("wrote figures/sim_regret_vs_budget.png")
