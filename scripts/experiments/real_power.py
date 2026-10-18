"""Post hoc precision and power of the real-host search comparison (Section 6.3).

Reads the re-evaluated picks of Phase C from <run>/summary.json (written by real_pilot_analyse.py)
and reports, for the per-pick median p99.9 of each method:
  - difference in medians with a 95% bootstrap interval (resampling picks within each method),
  - the one-sided Mann-Whitney U test and the Vargha-Delaney A12,
  - the minimum detectable effect (MDE) at 80% power and one-sided alpha 0.05 for the observed
    spread, computed on log10 p99.9 with a two-sample t approximation (the Mann-Whitney test has
    asymptotic relative efficiency 0.955 against it, so the MDE is a slight understatement),
  - the number of seeds per method at which the observed ratio of geometric means would be detectable.

Run:  python3 scripts/experiments/real_power.py --run data/real_pilot/run1
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]


def mde_log10(sd, n, alpha=0.05, power=0.8):
    df = 2 * n - 2
    return (stats.t.ppf(1 - alpha, df) + stats.t.ppf(power, df)) * sd * np.sqrt(2 / n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="data/real_pilot/run1")
    ap.add_argument("--B", type=int, default=20000)
    a = ap.parse_args()
    S = json.loads((ROOT / a.run / "summary.json").read_text())
    bo = np.array(S["bo_vs_random"]["bo_pick_p999"], float)
    rs = np.array(S["bo_vs_random"]["random_pick_p999"], float)
    n = len(bo)
    rng = np.random.default_rng(0)
    diffs = np.array([np.median(rng.choice(rs, n)) - np.median(rng.choice(bo, n)) for _ in range(a.B)])
    u = stats.mannwhitneyu(bo, rs, alternative="less")
    a12 = float(((bo[:, None] < rs[None, :]).sum() + 0.5 * (bo[:, None] == rs[None, :]).sum()) / (n * len(rs)))
    lb, lr = np.log10(bo), np.log10(rs)
    sd = float(np.sqrt((lb.var(ddof=1) + lr.var(ddof=1)) / 2))
    obs = float(lr.mean() - lb.mean())
    n_needed = next(k for k in range(2, 500) if mde_log10(sd, k) <= obs)
    out = dict(n_per_method=n, bo_median=float(np.median(bo)), random_median=float(np.median(rs)),
               diff_of_medians=float(np.median(rs) - np.median(bo)),
               diff_ci95=[float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
               mannwhitney_one_sided_p=float(u.pvalue), a12_bo_better=a12,
               pooled_sd_log10=sd, observed_ratio_of_geometric_means=float(10 ** obs),
               mde_factor_at_n={k: float(10 ** mde_log10(sd, k)) for k in (n, 8, 10, 20)},
               seeds_per_method_to_detect_observed_ratio=n_needed)
    (ROOT / a.run / "power.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
