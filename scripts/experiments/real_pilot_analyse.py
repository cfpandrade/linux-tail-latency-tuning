"""Analysis of the real-measurement pilot (scripts/experiments/real_pilot.py).

Statistical unit = one 30 s measurement (one cyclictest histogram). Percentiles of a configuration are
reported both as the median over its repetitions and from the pooled histogram of all its repetitions.
Bootstrap CIs resample repetitions (not samples), because samples within a run are not independent.

Run:  python3 scripts/experiments/real_pilot_analyse.py --run data/real_pilot/run1
Outputs: <run>/summary.json, <run>/tables.md, figures/real_*.png
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HMAX = 20000
QS = (50, 99, 99.9, 99.99)


def load(run):
    recs = []
    for line in (run / "evals.jsonl").read_text().splitlines():
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return recs


def hist_array(rec):
    h = np.zeros(HMAX + 1)
    for k, v in rec["hist"].items():
        h[min(int(k), HMAX)] += v
    h[HMAX] += rec.get("overflow", 0)
    return h


def pct(h, q):
    cum = np.cumsum(h)
    rank = np.ceil(q * cum[-1] / 100 - 1e-9)
    return float(np.searchsorted(cum, rank, side="left"))


def pooled(recs):
    return sum(hist_array(r) for r in recs)


def boot_ci(recs, q=99.9, B=5000, seed=0):
    rng = np.random.default_rng(seed)
    H = np.array([hist_array(r) for r in recs])
    vals = [pct(H[rng.integers(0, len(H), len(H))].sum(0), q) for _ in range(B)]
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def cliffs_delta(hx, hy):
    """P(X > Y) - P(X < Y) from two 1 us histograms (X = treatment, Y = reference)."""
    cy = np.cumsum(hy)
    nx, ny = hx.sum(), hy.sum()
    less = np.concatenate([[0], cy[:-1]])          # #Y strictly below each bin
    greater = ny - cy                               # #Y strictly above each bin
    return float(((hx * less).sum() - (hx * greater).sum()) / (nx * ny))


def a12(x, y):
    """Vargha-Delaney A12: probability that a value from x is smaller than one from y (lower is better)."""
    x, y = np.asarray(x), np.asarray(y)
    return float(((x[:, None] < y[None, :]).sum() + 0.5 * (x[:, None] == y[None, :]).sum()) / (len(x) * len(y)))


def describe(recs):
    h = pooled(recs)
    p999 = [r["p999"] for r in recs]
    return dict(n_runs=len(recs), samples=int(h.sum()),
                pooled={f"p{q:g}": pct(h, q) for q in QS} | {"max": float(np.nonzero(h)[0].max())},
                median_of_runs={k: float(np.median([r[k] for r in recs])) for k in ("p50", "p99", "p999", "max")},
                p999_runs=p999, p999_ci95=boot_ci(recs) if len(recs) > 1 else None)


def cfg_label(c):
    if c["policy"] == 0 and c["cpu"] < 0:
        return "untuned default"
    parts = ["FIFO p%d" % c["rt_priority"] if c["policy"] else "OTHER"]
    parts.append("unpinned" if c["cpu"] < 0 else f"cpu{c['cpu']}")
    if c["isolate"]:
        parts.append("isolated" + (" + sibling free" if c["sibling_free"] else ""))
    return ", ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="data/real_pilot/run1")
    a = ap.parse_args()
    run = ROOT / a.run
    recs = load(run)
    by_phase = defaultdict(list)
    for r in recs:
        by_phase[r["phase"]].append(r)
    S = {"n_evaluations": len(recs), "duration_s": recs[0]["duration"] if recs else None}

    # Phase A
    A = by_phase["A"]
    S["baseline"] = describe(A)

    # Phase C: re-evaluation of picks
    C = defaultdict(list)
    for r in by_phase["C"]:
        C[r["target"]].append(r)
    ref = pooled(C["default"]) if C.get("default") else pooled(A)
    S["reeval"] = {}
    for t, rs in sorted(C.items()):
        d = describe(rs)
        d["cfg"] = rs[0]["cfg"]
        d["label"] = cfg_label(rs[0]["cfg"])
        d["cliffs_delta_vs_default"] = cliffs_delta(pooled(rs), ref) if t != "default" else 0.0
        S["reeval"][t] = d
    picks = {m: [S["reeval"][t]["median_of_runs"]["p999"] for t in S["reeval"] if t.startswith(m + "#")] for m in ("bo", "random")}
    if picks["bo"] and picks["random"]:
        from scipy.stats import mannwhitneyu
        u = mannwhitneyu(picks["bo"], picks["random"], alternative="two-sided")
        dflt = S["reeval"]["default"]["median_of_runs"]["p999"]
        S["bo_vs_random"] = dict(bo_pick_p999=picks["bo"], random_pick_p999=picks["random"],
                                 a12_bo_better=a12(picks["bo"], picks["random"]), mannwhitney_p=float(u.pvalue),
                                 reduction_factor_bo_median=dflt / float(np.median(picks["bo"])),
                                 reduction_factor_random_median=dflt / float(np.median(picks["random"])))

    # Phase B: search traces
    B = defaultdict(lambda: defaultdict(list))
    for r in by_phase["B"]:
        B[r["method"]][r["seed"]].append(r)
    S["search"] = {}
    for m, seeds in B.items():
        curves = []
        for s, rs in seeds.items():
            rs.sort(key=lambda r: r["i"])
            curves.append(np.minimum.accumulate([r["p999"] for r in rs]).tolist())
        evals_to_best = [int(np.argmin([r["p999"] for r in sorted(rs, key=lambda r: r["i"])])) + 1 for rs in seeds.values()]
        fifo_frac = float(np.mean([r["cfg"]["policy"] for rs in seeds.values() for r in rs]))
        S["search"][m] = dict(curves=curves, evals_to_best=evals_to_best, fraction_fifo_proposals=fifo_frac)

    # Phase D: factorial
    D = defaultdict(list)
    for r in by_phase["D"]:
        c = r["cfg"]
        D[(c["policy"], c["isolate"], c["sibling_free"], c["cpu"])].append(r)
    S["factorial"] = []
    rows = []
    for key, rs in sorted(D.items()):
        d = describe(rs)
        d["cfg"] = rs[0]["cfg"]
        d["label"] = cfg_label(rs[0]["cfg"])
        d["loc_rate_hz"] = float(np.median([r["loc_rate_measured_cpu"] for r in rs if r.get("loc_rate_measured_cpu") is not None] or [np.nan]))
        d["irq_rate_hz"] = float(np.median([r["irq_rate_measured_cpu"] for r in rs if r.get("irq_rate_measured_cpu") is not None] or [np.nan]))
        S["factorial"].append(d)
        for r in rs:
            rows.append((key, np.log10(max(r["p999"], 1)), np.log10(max(r["p99"], 1))))
    if rows:
        # main-effect model on log10 p99.9: intercept, FIFO, isolate, sibling_free (given isolate), cpu5
        X = np.array([[1, k[0], k[1], k[2], 1 if k[3] == 5 else 0] for k, _, _ in rows], float)
        for name, col in (("p999", 1), ("p99", 2)):
            y = np.array([r[col] for r in rows])
            beta, res, *_ = np.linalg.lstsq(X, y, rcond=None)
            dof = len(y) - X.shape[1]
            sigma2 = float(((y - X @ beta) ** 2).sum() / max(dof, 1))
            se = np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
            S[f"factorial_effects_log10_{name}"] = {
                n: dict(coef=float(b), se=float(s), factor=float(10 ** b))
                for n, b, s in zip(["intercept", "fifo", "isolate", "sibling_free", "cpu5_vs_cpu0"], beta, se)}
        # interaction check: FIFO effect with and without isolation
        def med(sel):
            v = [r[1] for r in rows if sel(r[0])]
            return float(np.median(v)) if v else float("nan")
        S["fifo_effect_by_isolation"] = {
            "not_isolated": 10 ** (med(lambda k: k[0] == 0 and k[1] == 0) - med(lambda k: k[0] == 1 and k[1] == 0)),
            "isolated": 10 ** (med(lambda k: k[0] == 0 and k[1] == 1) - med(lambda k: k[0] == 1 and k[1] == 1))}

    # baseline environment
    S["loadavg_before_median"] = float(np.median([r["loadavg_before"] for r in recs]))
    (run / "summary.json").write_text(json.dumps(S, indent=2))
    write_tables(run, S)
    figures(run, S, A, C, ref)
    print(json.dumps({k: S[k] for k in S if k in ("n_evaluations", "bo_vs_random", "fifo_effect_by_isolation")}, indent=2))


def write_tables(run, S):
    L = ["Table: baseline and re-evaluated configurations (us). Median of runs; pooled p99.9 with 95% bootstrap CI.", "",
         "| Configuration | Runs | p50 | p99 | p99.9 | p99.9 pooled [95% CI] | max | Cliff's delta |",
         "|---|---|---|---|---|---|---|---|"]
    for t, d in S["reeval"].items():
        m, p = d["median_of_runs"], d["pooled"]
        ci = d["p999_ci95"] or [float("nan")] * 2
        L.append(f"| {t}: {d['label']} | {d['n_runs']} | {m['p50']:.0f} | {m['p99']:.0f} | {m['p999']:.0f} | "
                 f"{p['p99.9']:.0f} [{ci[0]:.0f}, {ci[1]:.0f}] | {p['max']:.0f} | {d['cliffs_delta_vs_default']:.3f} |")
    L += ["", "Table: factorial phase (us).", "",
          "| Configuration | Runs | p50 | p99 | p99.9 | p99.9 pooled [95% CI] | max | LOC Hz | IRQ Hz |", "|---|---|---|---|---|---|---|---|---|"]
    for d in S["factorial"]:
        m, p = d["median_of_runs"], d["pooled"]
        ci = d["p999_ci95"] or [float("nan")] * 2
        L.append(f"| {d['label']} | {d['n_runs']} | {m['p50']:.0f} | {m['p99']:.0f} | {m['p999']:.0f} | "
                 f"{p['p99.9']:.0f} [{ci[0]:.0f}, {ci[1]:.0f}] | {p['max']:.0f} | {d['loc_rate_hz']:.0f} | {d['irq_rate_hz']:.0f} |")
    for name in ("p999", "p99"):
        k = f"factorial_effects_log10_{name}"
        if k in S:
            L += ["", f"Table: main effects on log10 {name} (multiplicative factor = 10^coef).", "",
                  "| Term | coef | se | factor |", "|---|---|---|---|"]
            for n, e in S[k].items():
                L.append(f"| {n} | {e['coef']:.3f} | {e['se']:.3f} | {e['factor']:.3f} |")
    (run / "tables.md").write_text("\n".join(L) + "\n")


def figures(run, S, A, C, ref):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figs = ROOT / "figures"
    col = {"bo": "#1f6fb4", "random": "#d17b0f", "default": "#555555", "fifo": "#2a9d55"}

    # convergence (real)
    if S.get("search"):
        fig, ax = plt.subplots(figsize=(6.4, 4))
        for m, lab in (("bo", "Bayesian optimisation (GP, EI)"), ("random", "Random search")):
            if m not in S["search"]:
                continue
            cv = np.array(S["search"][m]["curves"])
            x = np.arange(1, cv.shape[1] + 1)
            ax.plot(x, np.median(cv, 0), color=col[m], label=lab)
            ax.fill_between(x, cv.min(0), cv.max(0), color=col[m], alpha=0.2, step=None)
        ax.axhline(S["baseline"]["median_of_runs"]["p999"], color=col["default"], ls="--", label="Untuned default (median)")
        ax.set_yscale("log"); ax.set_xlabel("Measurements (30 s each)"); ax.set_ylabel("Best observed p99.9 (µs)")
        ax.set_title("Search convergence on the real workstation"); ax.legend(frameon=False)
        fig.tight_layout(); fig.savefig(figs / "real_convergence.png", dpi=200); plt.close(fig)

    # CCDF pooled: default vs best BO pick vs best random pick
    fig, ax = plt.subplots(figsize=(6.4, 4))
    curves = [("Untuned default", ref, col["default"])]
    for m in ("bo", "random"):
        ts = [t for t in S["reeval"] if t.startswith(m + "#")]
        if ts:
            best = min(ts, key=lambda t: S["reeval"][t]["median_of_runs"]["p999"])
            curves.append((f"Best {'BO' if m == 'bo' else 'random-search'} pick: {S['reeval'][best]['label']}",
                           pooled(C[best]), col[m]))
    for name, h, c in curves:
        cum = np.cumsum(h) / h.sum()
        x = np.arange(len(h))
        keep = (1 - cum) > 0
        ax.loglog(np.maximum(x[keep], 1), (1 - cum)[keep], color=c, label=name, drawstyle="steps-post")
    ax.axhline(1e-3, color="#999999", lw=0.8, ls=":")
    ax.set_xlabel("Wake-up latency (µs)"); ax.set_ylabel("P(latency > x)")
    ax.set_title("Measured latency tail (pooled runs)"); ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(figs / "real_tail_ccdf.png", dpi=200); plt.close(fig)

    # factorial dot plot
    if S["factorial"]:
        fig, ax = plt.subplots(figsize=(6.4, 4.4))
        fs = sorted(S["factorial"], key=lambda d: d["median_of_runs"]["p999"])
        for i, d in enumerate(fs):
            c = col["fifo"] if d["cfg"]["policy"] else col["default"]
            ax.scatter(d["p999_runs"], [i] * len(d["p999_runs"]), color=c, s=18, alpha=0.7)
            ax.plot([d["median_of_runs"]["p999"]] * 2, [i - 0.3, i + 0.3], color=c, lw=2)
        ax.set_yticks(range(len(fs))); ax.set_yticklabels([d["label"] for d in fs], fontsize=7)
        ax.set_xscale("log"); ax.set_xlabel("p99.9 wake-up latency per 30 s run (µs)")
        ax.set_title("Factorial phase: every run (bar = median)")
        fig.tight_layout(); fig.savefig(figs / "real_factorial.png", dpi=200); plt.close(fig)


if __name__ == "__main__":
    main()
