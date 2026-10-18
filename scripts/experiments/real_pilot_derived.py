"""Derived statistics quoted in Chapter 6 that are not in data/real_pilot/run1/summary.json.

Run from the project root: .venv/bin/python -m scripts.experiments.real_pilot_derived
Reads data/real_pilot/run1/evals.jsonl only; writes nothing.

Reported: counts and extremes per scheduling class; budget use of each search method after the
eight random initial points of Bayesian optimisation (measurements 9 to 30 of every seed, for both
methods); median best observed p99.9 after 5, 10 and 30 measurements; the observational pinning
comparison; the lack-of-fit tests of the factorial main-effects model; per-isolation-level medians;
the one-sided Mann-Whitney test on the re-measured picks; and the improvement factors used for H1.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import f as fdist
from scipy.stats import mannwhitneyu

LOG = Path("data/real_pilot/run1/evals.jsonl")
N_INIT = 8


def load():
    return [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]


def main():
    recs = load()
    fifo = [r for r in recs if r["cfg"]["policy"] == 1]
    other = [r for r in recs if r["cfg"]["policy"] == 0]
    print(f"measurements: {len(recs)}  FIFO {len(fifo)} (max p99.9 {max(r['p999'] for r in fifo):.0f})"
          f"  OTHER {len(other)} (min p99.9 {min(r['p999'] for r in other):.0f})")
    print(f"load average median over all measurements: {np.median([r['loadavg_before'] for r in recs]):.1f}")

    # Phase B: budget use and convergence
    by = defaultdict(list)
    for r in recs:
        if r["phase"] != "B":
            continue
        m = re.match(r"B#(\w+)#(\d+)#(\d+)", r["key"])
        by[(m.group(1), int(m.group(2)))].append((int(m.group(3)), r))
    for meth in ("bo", "random"):
        post, best_at = [], defaultdict(list)
        for (mm, s), lst in sorted(by.items()):
            if mm != meth:
                continue
            lst.sort()
            vals = [r["p999"] for _, r in lst]
            post += [r for i, r in lst if i >= N_INIT]
            for k in (5, 10, 30):
                best_at[k].append(min(vals[:k]))
        fifo_share = np.mean([r["cfg"]["policy"] for r in post])
        print(f"{meth}: after initialisation SCHED_FIFO share {100 * fifo_share:.1f} per cent, "
              f"median p99.9 of all measurements {np.median([r['p999'] for r in post]):.1f}; "
              f"median best observed after 5/10/30: "
              + ", ".join(f"{np.median(best_at[k]):.0f}" for k in (5, 10, 30)))

    # Pinning, observational (Phases B and C, SCHED_FIFO, core not isolated)
    bc = [r for r in recs if r["phase"] in ("B", "C") and r["cfg"]["policy"] == 1 and r["cfg"]["isolate"] == 0]
    un = [r["p999"] for r in bc if r["cfg"]["cpu"] < 0]
    pi = [r["p999"] for r in bc if r["cfg"]["cpu"] >= 0]
    print(f"pinning: unpinned n={len(un)} median {np.median(un):.0f}; pinned n={len(pi)} median {np.median(pi):.1f}; "
          f"two-sided Mann-Whitney p={mannwhitneyu(un, pi, alternative='two-sided').pvalue:.3f}")

    # Factorial: lack of fit of the main-effects model on log10 of the per-run percentile
    D = [r for r in recs if r["phase"] == "D"]

    def lof(col):
        X, y, g = [], [], []
        for r in D:
            c = r["cfg"]
            X.append([1, c["policy"], c["isolate"], c["sibling_free"], 1 if c["cpu"] == 5 else 0])
            y.append(np.log10(max(r[col], 1)))
            g.append((c["policy"], c["isolate"], c["sibling_free"], c["cpu"]))
        X, y = np.array(X, float), np.array(y)
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        sse = ((y - X @ beta) ** 2).sum()
        groups = defaultdict(list)
        for gi, yi in zip(g, y):
            groups[gi].append(yi)
        sspe = sum(((np.array(v) - np.mean(v)) ** 2).sum() for v in groups.values())
        df1, df2 = len(groups) - X.shape[1], len(y) - len(groups)
        F = ((sse - sspe) / df1) / (sspe / df2)
        return F, df1, df2, 1 - fdist.cdf(F, df1, df2)

    for col in ("p999", "p99"):
        F, df1, df2, p = lof(col)
        print(f"lack of fit {col}: F({df1}, {df2}) = {F:.2f}, p = {p:.3g}")

    def med(pol, iso, sib, col):
        return np.median([r[col] for r in D if r["cfg"]["policy"] == pol and r["cfg"]["isolate"] == iso
                          and r["cfg"]["sibling_free"] == sib])

    for iso, sib in ((0, 0), (1, 0), (1, 1)):
        print(f"isolation {iso}/{sib}: OTHER p99 {med(0, iso, sib, 'p99'):.0f}, FIFO p99 {med(1, iso, sib, 'p99'):.1f}, "
              f"p99 ratio {med(0, iso, sib, 'p99') / med(1, iso, sib, 'p99'):.1f}, "
              f"p99.9 ratio {med(0, iso, sib, 'p999') / med(1, iso, sib, 'p999'):.1f}")

    # Phase C: picks against the default
    C = [r for r in recs if r["phase"] == "C"]
    picks = defaultdict(list)
    for r in C:
        picks[r["key"].rsplit("#", 1)[0]].append(r)
    default_key = [k for k in picks if "default" in k.lower()]
    med_p999 = {k: np.median([r["p999"] for r in v]) for k, v in picks.items()}
    bo = sorted(float(v) for k, v in med_p999.items() if "#bo#" in k)
    rn = sorted(float(v) for k, v in med_p999.items() if "#random#" in k)
    print(f"re-measured median p99.9 per pick: BO {bo}, random {rn}")
    print(f"Mann-Whitney BO < random: one-sided p={mannwhitneyu(bo, rn, alternative='less').pvalue:.3f}, "
          f"two-sided p={mannwhitneyu(bo, rn, alternative='two-sided').pvalue:.3f}")
    if default_key:
        print(f"default key(s) in Phase C: {default_key}; pooled values are in summary.json")


if __name__ == "__main__":
    main()
