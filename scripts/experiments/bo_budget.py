"""Budget curve for BO vs random search, scored by regret against the TRUE optimum.

IMPORTANT: this uses the SYNTHETIC latency model in `bo_sim.py`. Nothing here is a real kernel
measurement; it tests the optimisation methodology only.

How it works
------------
1. Ground truth (`truth.json`). The model is a two-component mixture per request:
       L = b * exp(sigma*Z)                         with prob 1-p   (body only)
       L = b * exp(sigma*Z) + S,  S ~ Pareto(xm=scale, alpha)   with prob p   (body + stall)
   (numpy's `pareto` is Lomax, so scale*(1+pareto) is a classic Pareto with minimum `scale`).
   Hence F(x) = (1-p) Phi(ln(x/b)/sigma) + p E_Z[F_S(x - b e^{sigma Z})], and the true p99.9 is
   the root of F(x) = 0.999, found by bisection in log x with the expectation done by quadrature
   over Z. `true_p999` is exact up to quadrature/bisection tolerance (checked against scipy.quad
   and against large Monte Carlo samples).
   The optimum is found by enumerating a reduced space that exploits the model's monotone
   structure (p99.9 increases in b, p and scale):
     * rt_priority only acts via scale when isolated_cores == 0 (decreasing in rt) and via the
       p*1.3 penalty at rt >= 95, so rt in {1, 94, 99} covers every non-dominated choice;
     * irq_coalesce_us above 50 only adds body latency, so only 0..50 can be optimal.
   This is then VERIFIED by an exhaustive evaluation over every distinct (b, p, scale) triple of
   the full 2.88M-point search space.
2. Search runs. Jobs are (budget, method, seed); each runs `bo_sim.run_search` with n samples per
   evaluation, picks the best observed configuration and records its TRUE p99.9 and the simple
   regret true_p999(picked)/true_p999(opt) - 1 (log-regret = log10 of that ratio).
   Jobs append to `checkpoint.jsonl` in the run directory; restarts skip completed jobs, and a
   wall-clock budget (--max-seconds) stops submitting new jobs so each call fits a time limit.
3. Summary (`summary.json`, `trials.csv`, `runs.csv`, `regret_vs_budget.png`) once all jobs are done.

Run (first call creates the run dir; then repeat with --out until it prints "all jobs done").
Each call stays within --max-seconds (default 200 s, chosen because the tool runner kills calls
at ~230 s; any job killed mid-run is simply redone on the next call):
  python3 scripts/experiments/bo_budget.py --label budget_n1e6
  python3 scripts/experiments/bo_budget.py --out data/bo_sim_runs/<dir>
"""
import argparse
import json
import math
import os
import sys
import time
import warnings
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):   # see bo_sim.py
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.experiments import bo_sim as S  # noqa: E402

Q = 0.999
BUDGETS = (10, 20, 40, 80, 150)
METHODS = ("bo", "random")


# ---------------------------------------------------------------- analytic ground truth
def _z_grid(m):
    """Trapezoid nodes/weights for E[f(Z)], Z ~ N(0,1), truncated at |z| <= 8.5."""
    z = np.linspace(-8.5, 8.5, m)
    w = np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi) * (z[1] - z[0])
    w[[0, -1]] *= 0.5
    return z, w


def mixture_cdf(x, b, p, scale, z, w, sigma=S.BODY_SIGMA, alpha=S.ALPHA):
    """CDF of the synthetic latency at x (all arrays broadcast over configs; z/w over the last axis)."""
    from scipy.special import ndtr
    x, b, p, scale = (np.asarray(v, float)[..., None] for v in (x, b, p, scale))
    body_cdf = ndtr(np.log(x / b) / sigma)[..., 0]
    s = x - b * np.exp(sigma * z)                       # stall needed to stay below x
    fs = np.where(s >= scale, 1.0 - (scale / np.maximum(s, scale)) ** alpha, 0.0)
    stall_cdf = (fs * w).sum(-1)
    return (1 - p[..., 0]) * body_cdf + p[..., 0] * stall_cdf


def quantile_from_factors(b, p, scale, q=Q, m=4001, iters=60, sigma=None, alpha=None):
    """Vectorised true quantile for arrays of model factors (bisection on log x).
    sigma/alpha default to the SYNTHETIC model's BODY_SIGMA/ALPHA (override for sensitivity runs)."""
    sigma = S.BODY_SIGMA if sigma is None else sigma
    alpha = S.ALPHA if alpha is None else alpha
    b, p, scale = (np.atleast_1d(np.asarray(v, float)) for v in (b, p, scale))
    p = np.minimum(p, 0.5)                              # same clip as simulate_latencies
    z, w = _z_grid(m)
    lo = np.log(b) - 9 * sigma                          # F(lo) ~ 0
    hi = np.log(b * math.exp(9 * sigma) + scale * (1e-9) ** (-1 / alpha))  # F(hi) ~ 1
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        below = mixture_cdf(np.exp(mid), b, p, scale, z, w, sigma=sigma, alpha=alpha) < q
        lo, hi = np.where(below, mid, lo), np.where(below, hi, mid)
    return np.exp(0.5 * (lo + hi))


def true_p999(cfg, m=4001, coef=None):
    """Exact (to quadrature tolerance) p99.9 of a configuration under the SYNTHETIC model
    (optionally with a coefficient override, see bo_sim.COEF_DEFAULTS)."""
    k = S.coefs(coef)
    return float(quantile_from_factors(*S.model_factors(cfg, coef), m=m,
                                       sigma=k["body_sigma"], alpha=k["alpha"])[0])


def true_p999_quad(cfg):
    """Independent check of true_p999 using adaptive scipy.quad and brentq (slow, scalar)."""
    from scipy.integrate import quad
    from scipy.optimize import brentq
    from scipy.stats import norm
    b, p, scale = S.model_factors(cfg)
    p, sg, a = min(p, 0.5), S.BODY_SIGMA, S.ALPHA

    def cdf(x):
        zmax = (math.log(x - scale) - math.log(b)) / sg if x > scale else -np.inf
        stall = 0.0
        if zmax > -12:
            stall = quad(lambda zz: norm.pdf(zz) * (1 - (scale / (x - b * math.exp(sg * zz))) ** a),
                         -12, min(zmax, 12), limit=200, epsabs=1e-13)[0]
        return (1 - p) * norm.cdf(math.log(x / b) / sg) + p * stall

    return brentq(lambda x: cdf(x) - Q, b * math.exp(-9 * sg), b * math.exp(9 * sg) + scale * 1e6,
                  xtol=1e-10, rtol=1e-12)


def _factor_table(cfg_iter):
    rows = [(*S.model_factors(c),) for c in cfg_iter]
    return np.array(rows, float)


def reduced_configs():
    """Candidate set that contains every potentially optimal config (see module docstring)."""
    import itertools
    for iso in range(9):
        for bits in itertools.product((0, 1), repeat=5):
            for rt in (1, 94, 99):
                for co in range(51):
                    yield dict(zip(S.NAMES, (iso, *bits, rt, co)))


def full_configs():
    import itertools
    for iso in range(9):
        for bits in itertools.product((0, 1), repeat=5):
            for rt in range(1, 100):
                for co in range(101):
                    yield dict(zip(S.NAMES, (iso, *bits, rt, co)))


def _q_chunk(args):
    S.limit_threads()
    f, m = args
    return quantile_from_factors(f[:, 0], f[:, 1], f[:, 2], m=m)


def _quantiles_parallel(f, workers, m):
    """True p99.9 for each row (b, p, scale) of f, split across processes."""
    with ProcessPoolExecutor(workers) as ex:
        return np.concatenate(list(ex.map(_q_chunk, [(c, m) for c in np.array_split(f, workers * 4)])))


def truth_optimum(workers, log=print):
    """Stage 1: optimum over the reduced space (fine grid), then exhaustive verification over every
    distinct (b, p, scale) triple of the full space (coarser grid, then fine re-check near the top)."""
    t0 = time.time()
    red = list(reduced_configs())
    fr = _factor_table(red)
    qr = _quantiles_parallel(fr, workers, 4001)
    i = int(np.argmin(qr))
    opt_cfg, opt_val = red[i], float(qr[i])
    ties = [red[j] for j in np.flatnonzero(qr <= opt_val * (1 + 1e-9))]
    log(f"reduced space: {len(red)} configs, optimum {opt_val:.4f} us ({time.time() - t0:.0f}s)")

    t1 = time.time()
    ff = _factor_table(full_configs())
    uniq = np.unique(ff, axis=0)
    qu = _quantiles_parallel(uniq, workers, 1001)   # 1001-node grid agrees with 4001 to ~1e-8
    near = np.flatnonzero(qu <= opt_val * 1.001)     # anything within 0.1% is re-done on the fine grid
    near_fine = quantile_from_factors(uniq[near, 0], uniq[near, 1], uniq[near, 2], m=4001)
    full_min = float(min(near_fine.min(), qu.min()))
    verify = dict(full_space_size=int(len(ff)), distinct_factor_triples=int(len(uniq)),
                  full_min_p999_us=full_min, n_within_0p1pct_rechecked=int(len(near)),
                  reduced_optimum_is_global=bool(full_min >= opt_val * (1 - 1e-9)),
                  seconds=round(time.time() - t1, 1))
    log(f"exhaustive check: {verify}")
    return dict(note="Synthetic latency model; ground truth computed analytically from model_factors.",
                quantile=Q, optimum_cfg=opt_cfg, optimum_p999_us=opt_val, n_optimum_ties=len(ties),
                optimum_ties=ties[:50], default_p999_us=true_p999(S.DEFAULT), verification=verify,
                seconds=round(time.time() - t0, 1))


def probe_configs(opt_cfg):
    from skopt.space import Space
    probe = [("default", dict(S.DEFAULT)), ("optimum", dict(opt_cfg)),
             ("tuned_example", dict(isolated_cores=4, irq_affinity=1, nohz_full=1, preempt_rt=1,
                                    governor_performance=1, numa_pinned=1, rt_priority=50, irq_coalesce_us=20)),
             ("irq_no_iso", dict(S.DEFAULT, irq_affinity=1, rt_priority=60))]
    return probe + [(f"random_{j}", S.to_cfg(x)) for j, x in enumerate(Space(S.space()).rvs(3, random_state=11))]


def _check_one(args):
    """Stage 2 worker: analytic vs scipy.quad vs Monte Carlo for one configuration."""
    S.limit_threads()
    j, name, c = args
    a = true_p999(c)
    return dict(name=name, cfg=c, analytic=a, quad=true_p999_quad(c),
                **_mc_check(c, a, np.random.default_rng(2026 + j)))


def truth_checks(opt_cfg, workers, log=print):
    probe = probe_configs(opt_cfg)
    with ProcessPoolExecutor(min(workers, len(probe))) as ex:
        checks = list(ex.map(_check_one, [(j, n, c) for j, (n, c) in enumerate(probe)]))
    for ck in checks:
        log(f"  {ck['name']}: analytic {ck['analytic']:.4f} quad {ck['quad']:.4f} MC {ck['mc_p999']:.4f} "
            f"F_MC(analytic)={ck['mc_cdf_at_analytic']:.6f} z={ck['z_score']:+.2f}")
    return checks


def _mc_check(c, analytic, rng, n_cdf=100_000_000, n_q=20_000_000, chunk=10_000_000):
    """MC agreement: empirical CDF at the analytic p99.9 (1e8 samples; should be 0.999 within
    binomial error, reported as a z-score) and the empirical p99.9 of a 2e7 sample."""
    hits = 0
    for _ in range(n_cdf // chunk):
        hits += int((S.simulate_latencies(c, chunk, rng) <= analytic).sum())
    f = hits / n_cdf
    z = (f - Q) / math.sqrt(Q * (1 - Q) / n_cdf)
    emp = float(np.percentile(S.simulate_latencies(c, n_q, rng), 99.9))
    return dict(mc_n_cdf=n_cdf, mc_cdf_at_analytic=f, z_score=z, mc_n_quantile=n_q,
                mc_p999=emp, mc_rel_diff=emp / analytic - 1)


# ---------------------------------------------------------------- resumable search jobs
def job_key(budget, method, seed):
    return f"{budget}|{method}|{seed}"


def run_job(args):
    """Worker: one (budget, method, seed) search; returns its record with the TRUE p99.9 of the pick."""
    S.limit_threads()
    warnings.filterwarnings("ignore", category=UserWarning)   # skopt "point evaluated before" notices
    budget, method, seed, n, opt_val = args
    t = time.time()
    trials, _, best = S.run_search((method, seed, budget, n))
    cfg = {k: int(best[k]) for k in S.NAMES}
    tp = true_p999(cfg)
    return dict(key=job_key(budget, method, seed), budget=budget, method=method, seed=seed,
                samples_per_eval=n, picked_cfg=cfg, observed_p999=best["p999"], true_p999=tp,
                regret=tp / opt_val - 1, log10_regret=math.log10(tp / opt_val),
                n_distinct_cfgs=len({tuple(t[k] for k in S.NAMES) for t in trials}),
                seconds=round(time.time() - t, 2), trials=trials)


def load_done(ckpt):
    done = {}
    if ckpt.exists():
        for line in ckpt.read_text().splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    done[r["key"]] = r
                except json.JSONDecodeError:
                    pass   # a line truncated by an interrupted write is simply redone
    return done


def run_pending(out, n, seeds, workers, max_seconds, opt_val, slack=1.3, log=print):
    """Run not-yet-done jobs until the wall-clock budget; append each result to checkpoint.jsonl."""
    t0 = time.time()
    ckpt = out / "checkpoint.jsonl"
    done = load_done(ckpt)
    jobs = [(b, m, s) for b in sorted(BUDGETS, reverse=True) for m in METHODS for s in range(seeds)
            if job_key(b, m, s) not in done]
    # expected cost (s, single thread) used to avoid starting a job that cannot finish in time
    # (measured at n=1e6 with single-threaded BLAS: BO 40 evals ~12.5 s/job with <= 6 workers on the
    # 6-core/12-thread i7-8700, ~18 s/job with 11 workers because of hyper-threading contention)
    contention = 1.0 if workers <= 6 else 1.5
    cost = lambda b, m: contention * ((0.0055 * b * b + 0.12 * b + 1) if m == "bo" else 0.06 * b + 1)  # noqa: E731
    log(f"{len(done)} done, {len(jobs)} pending", flush=True)
    new = 0
    with ProcessPoolExecutor(workers) as ex, ckpt.open("a") as fh:
        running = {}
        while jobs or running:
            while jobs and len(running) < workers:
                # first pending job that still fits the remaining time (cheaper ones can fill the tail)
                left = max_seconds - (time.time() - t0)
                fit = next((j for j in jobs if slack * cost(j[0], j[1]) <= left), None)
                if fit is None:
                    if not running and new == 0:
                        log("WARNING: no pending job fits --max-seconds; use fewer workers or a larger budget")
                    jobs = []   # out of time for new work in this call
                    break
                jobs.remove(fit)
                b, m, s = fit
                running[ex.submit(run_job, (b, m, s, n, opt_val))] = (b, m, s)
            if not running:
                break
            fin, _ = wait(running, return_when=FIRST_COMPLETED)
            for f in fin:
                b, m, s = running.pop(f)
                r = f.result()
                fh.write(json.dumps(r) + "\n")
                fh.flush()
                new += 1
                log(f"  done {b:>3} {m:<6} seed {s:>2}: regret {r['regret']:.4f} ({r['seconds']:.0f}s)", flush=True)
    remaining = len(BUDGETS) * len(METHODS) * seeds - len(load_done(ckpt))
    log(f"finished {new} jobs this call in {time.time() - t0:.0f}s; {remaining} remaining")
    return remaining


# ---------------------------------------------------------------- summary and figure
def a12(x, y):
    """Vargha-Delaney A12 = P(X < Y) + 0.5 P(X = Y): probability BO's regret is LOWER than random's."""
    x, y = np.asarray(x)[:, None], np.asarray(y)[None, :]
    return float(((x < y).sum() + 0.5 * (x == y).sum()) / (x.size * y.size))


def summarise(out, truth, seeds):
    import pandas as pd
    from scipy.stats import mannwhitneyu
    recs = list(load_done(out / "checkpoint.jsonl").values())
    trials = [dict(budget=r["budget"], **t) for r in recs for t in r["trials"]]
    pd.DataFrame(trials).sort_values(["budget", "method", "seed", "i"]).to_csv(out / "trials.csv", index=False)
    runs = pd.DataFrame([{k: v for k, v in r.items() if k not in ("trials", "picked_cfg")} | r["picked_cfg"]
                         for r in recs]).sort_values(["budget", "method", "seed"])
    runs.to_csv(out / "runs.csv", index=False)
    per = {}
    for b in BUDGETS:
        d = {}
        for m in METHODS:
            r = runs[(runs.budget == b) & (runs.method == m)]["regret"].to_numpy()
            if len(r) == 0:
                continue
            lr = np.log10(1 + r)
            d[m] = dict(n_runs=int(len(r)), median_regret=float(np.median(r)),
                        q25_regret=float(np.percentile(r, 25)), q75_regret=float(np.percentile(r, 75)),
                        mean_log10_regret=float(lr.mean()), median_log10_regret=float(np.median(lr)),
                        frac_within_5pct=float((r <= 0.05).mean()), frac_exact_optimum=float((r <= 1e-9).mean()))
        if "bo" in d and "random" in d:
            rb = runs[(runs.budget == b) & (runs.method == "bo")]["regret"].to_numpy()
            rr = runs[(runs.budget == b) & (runs.method == "random")]["regret"].to_numpy()
            u = mannwhitneyu(rb, rr, alternative="less")
            d["mannwhitney_bo_less_than_random"] = dict(U=float(u.statistic), p=float(u.pvalue))
            d["A12_bo_better"] = a12(rb, rr)
        per[str(b)] = d
    summary = dict(note="Synthetic latency model; validates methodology only. Regret is against the "
                        "analytic true optimum; picks are best-observed (noisy) configurations.",
                   quantile=Q, seeds=seeds, budgets=list(BUDGETS),
                   samples_per_eval=int(runs["samples_per_eval"].iloc[0]),
                   optimum_cfg=truth["optimum_cfg"], optimum_p999_us=truth["optimum_p999_us"],
                   default_p999_us=truth["default_p999_us"],
                   default_regret=truth["default_p999_us"] / truth["optimum_p999_us"] - 1,
                   total_job_seconds=float(runs["seconds"].sum()), per_budget=per)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    make_figure(runs, summary, out)
    return summary


def make_figure(runs, summary, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    col = {"bo": "#1f6fb4", "random": "#d17b0f"}
    lab = {"bo": "Bayesian optimisation (GP, EI)", "random": "Random search"}
    fig, ax = plt.subplots(figsize=(6.4, 4))
    for k, m in enumerate(METHODS):
        g = runs[runs.method == m].groupby("budget")["regret"]
        b = np.array(sorted(g.groups))
        ratio = lambda q: np.array([1 + np.percentile(g.get_group(x), q) for x in b])  # noqa: E731
        xs = b * (0.97 if k == 0 else 1.03)   # small dodge so bands do not hide each other
        ax.plot(xs, ratio(50), "o-", color=col[m], label=f"{lab[m]} (median)")
        ax.fill_between(xs, ratio(25), ratio(75), color=col[m], alpha=0.2, lw=0)
    ax.axhline(1 + summary["default_regret"], color="#555555", ls="--", label="Untuned default")
    ax.axhline(1.05, color="#999999", ls=":", lw=0.8, label="Within 5% of optimum")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks(list(BUDGETS)); ax.set_xticklabels([str(x) for x in BUDGETS])
    ax.set_xlabel("Evaluation budget")
    ax.set_ylabel("True p99.9 of pick / optimum p99.9  (1 + regret)")
    ax.set_title(f"Regret vs budget, median and IQR over {summary['seeds']} seeds (synthetic model)", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(out / "regret_vs_budget.png", dpi=200); plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="run directory (created if missing); reuse it to resume")
    ap.add_argument("--label", default="budget", help="new run dir data/bo_sim_runs/<stamp>_<label> if no --out")
    ap.add_argument("--n", type=int, default=1_000_000, help="samples per evaluation")
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--max-seconds", type=float, default=200,
                    help="wall-clock budget of this call; jobs that would not finish in it are not started")
    ap.add_argument("--slack", type=float, default=1.3, help="safety factor on the per-job cost estimate")
    a = ap.parse_args(argv)
    t0 = time.time()
    out = Path(a.out) if a.out else S.new_run_dir(a.label)
    out.mkdir(parents=True, exist_ok=True)
    print(f"run dir: {out}")
    cfg_path = out / "run_config.json"
    if cfg_path.exists():   # a resumed run must keep its original settings
        old = json.loads(cfg_path.read_text())
        if (old["n"], old["seeds"]) != (a.n, a.seeds):
            sys.exit(f"run dir was created with n={old['n']} seeds={old['seeds']}; refusing to mix")
    else:
        cfg_path.write_text(json.dumps(dict(n=a.n, seeds=a.seeds, budgets=BUDGETS, methods=METHODS,
                                            started=time.strftime("%Y-%m-%dT%H:%M:%S")), indent=2))
    # ground truth in two resumable stages so no single call runs long
    truth_path = out / "truth.json"
    if not truth_path.exists():
        truth_path.write_text(json.dumps(truth_optimum(a.workers), indent=2))
        print("truth stage 1 (optimum) done; re-run to continue")
        return
    truth = json.loads(truth_path.read_text())
    if "checks" not in truth:
        truth["checks"] = truth_checks(truth["optimum_cfg"], a.workers)
        truth_path.write_text(json.dumps(truth, indent=2))
        print("truth stage 2 (MC cross-checks) done; re-run to start the search jobs")
        return
    left = run_pending(out, a.n, a.seeds, a.workers, a.max_seconds - (time.time() - t0),
                       truth["optimum_p999_us"], slack=a.slack)
    if left == 0:
        s = summarise(out, truth, a.seeds)
        print(json.dumps({k: v for k, v in s.items() if k != "per_budget"}, indent=2))
        print("all jobs done")


if __name__ == "__main__":
    main()
