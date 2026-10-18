"""Simulated Bayesian optimisation of kernel tuning for tail latency.

IMPORTANT: the latency model below is SYNTHETIC. Its effect sizes are assumptions chosen
to resemble qualitative findings (isolation helps, IRQ steering without isolation hurts,
tickless needs isolated cores, PREEMPT_RT trades body latency for tail). The experiment
validates the optimisation methodology (BO vs random search under noisy evaluations),
not any real kernel result. Replace `simulate_latencies` with real measurements to reuse it.

Run:
  python3 scripts/experiments/bo_sim.py --n 1000000 --label n1e6
      -> data/bo_sim_runs/<YYYYmmdd-HHMM>_n1e6/{trials.csv, results.json, run_config.json, *.png}
  python3 scripts/experiments/bo_sim.py --out data/bo_sim_runs/my_run [--seeds 12 --evals 40 --n 1000000]
  python3 scripts/experiments/bo_sim.py            (legacy: n=20000, writes data/bo_sim_trials.csv,
                                                    data/bo_sim_results.json, figures/bo_sim_*.png)

Samples per evaluation (`--n`) matter: p99.9 of n samples rests on only ~n/1000 tail samples,
so with n=20000 the "best observed" configuration is largely the luckiest draw. Use n=1e6.
"""
import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# One BLAS/OpenMP thread per process, set BEFORE numpy loads OpenBLAS. Otherwise every pool
# worker spawns one BLAS thread per logical CPU and the GP fits oversubscribe the machine
# (observed: 11 workers x 12 threads, load ~100, >10x slowdown). Override via the environment.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
NAMES = ["isolated_cores", "irq_affinity", "nohz_full", "preempt_rt",
         "governor_performance", "numa_pinned", "rt_priority", "irq_coalesce_us"]
DEFAULT = dict(isolated_cores=0, irq_affinity=0, nohz_full=0, preempt_rt=0,
               governor_performance=0, numa_pinned=0, rt_priority=1, irq_coalesce_us=0)
BASE_MEDIAN_US = 5.4      # same order as the local pilot p50
BASE_EVENT_P = 0.004      # probability a request is hit by a stall
BASE_STALL_US = 320.0     # Pareto scale of a stall
ALPHA = 1.6               # Pareto shape (heavy tail)
BODY_SIGMA = 0.25         # lognormal sigma of the body (no-stall) latency
LEGACY_N = 20_000         # samples per evaluation used by the original (pre --n) runs
RUNS_DIR = ROOT / "data" / "bo_sim_runs"

# Every hand-chosen coefficient of the SYNTHETIC model, by name. `model_factors`,
# `simulate_latencies` and `measure` accept an optional override dict (a subset of these keys);
# None or {} reproduces the original model bit for bit. Used by bo_sensitivity.py.
COEF_DEFAULTS = dict(
    base_median_us=BASE_MEDIAN_US,   # body median (us)
    base_event_p=BASE_EVENT_P,       # stall probability, untuned
    base_stall_us=BASE_STALL_US,     # Pareto minimum of a stall (us)
    alpha=ALPHA,                     # Pareto shape
    body_sigma=BODY_SIGMA,           # lognormal sigma of the body
    iso_decay=0.55,                  # p *= exp(-iso_decay * min(isolated_cores, iso_cap))
    iso_cap=4,                       # isolation stops helping beyond this many cores
    irq_noiso_p=1.6,                 # p factor: irq_affinity without isolation
    irq_iso_p=0.7,                   # p factor: irq_affinity with isolation
    irq_over_p=1.8,                  # p factor: irq_affinity with isolated_cores >= irq_over_min_iso
    irq_over_min_iso=7,              # structural threshold (not perturbed by the sensitivity sweep)
    nohz_p=0.6,                      # p factor: nohz_full with >= 1 isolated core
    rt_scale=0.45,                   # stall-scale factor: PREEMPT_RT
    rt_body=1.08,                    # body factor: PREEMPT_RT
    gov_p=0.8,                       # p factor: performance governor
    gov_body=0.97,                   # body factor: performance governor
    numa_p=0.7,                      # p factor: NUMA pinning
    numa_body=0.9,                   # body factor: NUMA pinning
    rtprio_scale_gain=0.3,           # no isolation: scale *= 1 - gain * ln(rt)/ln(99)
    rt_high_p=1.3,                   # p factor: rt_priority >= rt_high_min
    rt_high_min=95,                  # structural threshold (not perturbed by the sensitivity sweep)
    coalesce_gain=0.3,               # p *= 1 - gain * min(irq_coalesce_us, sat)/sat
    coalesce_sat_us=50,              # coalescing saturates at this many us
    coalesce_body=0.04,              # body += coalesce_body * irq_coalesce_us (us per us)
)


def coefs(override=None):
    """Full coefficient dict of the SYNTHETIC model: COEF_DEFAULTS updated with `override`."""
    k = dict(COEF_DEFAULTS)
    if override:
        bad = set(override) - set(k)
        if bad:
            raise KeyError(f"unknown model coefficient(s): {sorted(bad)}")
        k.update(override)
    return k


def space():
    from skopt.space import Categorical, Integer
    return [Integer(0, 8, name="isolated_cores"), Categorical([0, 1], name="irq_affinity"),
            Categorical([0, 1], name="nohz_full"), Categorical([0, 1], name="preempt_rt"),
            Categorical([0, 1], name="governor_performance"), Categorical([0, 1], name="numa_pinned"),
            Integer(1, 99, name="rt_priority"), Integer(0, 100, name="irq_coalesce_us")]


def to_cfg(x):
    return dict(zip(NAMES, (int(v) for v in x)))


def model_factors(c, coef=None):
    """Deterministic part of the SYNTHETIC model: (body median us, stall probability, stall scale us).

    `coef` optionally overrides coefficients (keys of COEF_DEFAULTS); None/{} is the original model."""
    k = coefs(coef)
    iso = min(c["isolated_cores"], k["iso_cap"])
    p = k["base_event_p"] * np.exp(-k["iso_decay"] * iso)
    scale = k["base_stall_us"]
    body = k["base_median_us"]
    if c["irq_affinity"]:
        # steering IRQs to few housekeeping cores concentrates them; only pays off with isolation
        p *= k["irq_noiso_p"] if c["isolated_cores"] == 0 else k["irq_iso_p"]
        if c["isolated_cores"] >= k["irq_over_min_iso"]:
            p *= k["irq_over_p"]   # too few housekeeping cores left
    if c["nohz_full"] and c["isolated_cores"] >= 1:
        p *= k["nohz_p"]
    if c["preempt_rt"]:
        scale *= k["rt_scale"]
        body *= k["rt_body"]
    if c["governor_performance"]:
        p *= k["gov_p"]
        body *= k["gov_body"]
    if c["numa_pinned"]:
        p *= k["numa_p"]
        body *= k["numa_body"]
    if c["isolated_cores"] == 0:
        scale *= 1.0 - k["rtprio_scale_gain"] * np.log(c["rt_priority"]) / np.log(99)
    if c["rt_priority"] >= k["rt_high_min"]:
        p *= k["rt_high_p"]   # competes with migration and ksoftirqd threads
    c_eff = min(c["irq_coalesce_us"], k["coalesce_sat_us"]) / k["coalesce_sat_us"]
    p *= 1.0 - k["coalesce_gain"] * c_eff
    body += k["coalesce_body"] * c["irq_coalesce_us"]
    return body, p, scale


def simulate_latencies(c, n, rng, coef=None):
    """n SYNTHETIC latencies: lognormal body, plus a shifted-Pareto stall on a Binomial(n, p) subset."""
    k = coefs(coef)
    body, p, scale = model_factors(c, coef)
    lat = body * rng.lognormal(0.0, k["body_sigma"], n)
    n_stall = rng.binomial(n, min(p, 0.5))
    idx = rng.choice(n, n_stall, replace=False)
    lat[idx] += scale * (1.0 + rng.pareto(k["alpha"], n_stall))
    return lat


def percentiles(lat):
    p50, p99, p999 = np.percentile(lat, [50, 99, 99.9])
    return dict(p50=float(p50), p99=float(p99), p999=float(p999))


def measure(c, n=LEGACY_N, seed=0, coef=None):
    """One noisy evaluation of the SYNTHETIC model: percentiles of n simulated samples."""
    return percentiles(simulate_latencies(c, n, np.random.default_rng(seed), coef))


def run_search(args):
    """One search run on the SYNTHETIC model. args = (method, seed, evals[, n[, coef]]); n defaults
    to LEGACY_N for compatibility, coef (coefficient override dict) to the original model.

    Returns (trials, bo_recommended_cfg_or_None, best_observed_trial).
    """
    method, seed, evals = args[:3]
    n = args[3] if len(args) > 3 else LEGACY_N
    coef = args[4] if len(args) > 4 else None
    from skopt import gp_minimize
    from skopt.space import Space
    sp = space()
    rng = np.random.default_rng(10_000 * seed + 7)   # per-run stream of evaluation-noise seeds
    trials = []

    def objective(x):
        m = measure(to_cfg(x), n=n, seed=int(rng.integers(2**31)), coef=coef)
        trials.append(dict(method=method, seed=seed, i=len(trials), **to_cfg(x), **m))
        return float(np.log10(m["p999"]))

    if method == "bo":
        res = gp_minimize(objective, sp, n_calls=evals, n_initial_points=min(10, evals), acq_func="EI",
                          noise="gaussian", random_state=seed)
        best_x = res.x
    elif method == "random":
        # plain random search (skopt.dummy_minimize is broken with recent scikit-learn)
        for x in Space(sp).rvs(evals, random_state=seed):
            objective(x)
        best_x = None
    else:
        raise ValueError(f"unknown method {method!r}")
    # best by observed noisy p99.9 (what a practitioner would pick)
    best = min(trials, key=lambda t: t["p999"])
    return trials, (to_cfg(best_x) if best_x is not None else None), best


def reevaluate(c, reps=20, n=200_000, seed0=900_000):
    vals = [measure(c, n=n, seed=seed0 + r)["p999"] for r in range(reps)]
    return float(np.mean(vals)), float(np.std(vals, ddof=1))


def limit_threads():
    """Belt and braces for pool workers: cap already-loaded BLAS/OpenMP pools at one thread
    (the env vars at the top of this module are what normally does it)."""
    try:
        import scipy.linalg  # noqa: F401  (make sure the BLAS library is loaded so it can be limited)
        from threadpoolctl import threadpool_limits
        threadpool_limits(1)
    except ImportError:
        pass


def new_run_dir(label, base=RUNS_DIR, now=None):
    """Create and return a fresh run directory base/<YYYYmmdd-HHMM>_<label> (suffixed if it exists)."""
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime(now))
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in label) or "run"
    d = Path(base) / f"{stamp}_{safe}"
    k = 1
    while d.exists():
        k += 1
        d = Path(base) / f"{stamp}_{safe}-{k}"
    d.mkdir(parents=True)
    return d


def output_paths(out_dir=None):
    """Where a run writes. Legacy (out_dir=None): data/bo_sim_* and figures/bo_sim_*.
    With out_dir: everything (CSV, JSON, figures) goes into that directory."""
    if out_dir is None:
        return dict(trials=ROOT / "data/bo_sim_trials.csv", results=ROOT / "data/bo_sim_results.json",
                    figs=ROOT / "figures", prefix="bo_sim_")
    out = Path(out_dir)
    return dict(trials=out / "trials.csv", results=out / "results.json", figs=out, prefix="")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--evals", type=int, default=40)
    ap.add_argument("--n", type=int, default=LEGACY_N, help="samples per evaluation (use 1000000)")
    ap.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    ap.add_argument("--out", help="run directory; all outputs go here")
    ap.add_argument("--label", help="create data/bo_sim_runs/<YYYYmmdd-HHMM>_<label>/ as the run directory")
    a = ap.parse_args(argv)

    out_dir = a.out if a.out else (new_run_dir(a.label) if a.label else None)
    paths = output_paths(out_dir)
    if out_dir is not None:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "run_config.json").write_text(json.dumps(
            dict(vars(a), out=str(out_dir), started=time.strftime("%Y-%m-%dT%H:%M:%S")), indent=2))

    import pandas as pd
    t0 = time.time()
    jobs = [(m, s, a.evals, a.n) for s in range(a.seeds) for m in ("bo", "random")]
    with ProcessPoolExecutor(a.workers, initializer=limit_threads) as ex:
        out = list(ex.map(run_search, jobs))
    rows, final = [], []
    for (m, s, _, _), (trials, _, best) in zip(jobs, out):
        rows += trials
        cfg = {k: best[k] for k in NAMES}
        mean, sd = reevaluate(cfg)
        final.append(dict(method=m, seed=s, best_cfg=cfg, reeval_p999_mean=mean, reeval_p999_sd=sd))
    df = pd.DataFrame(rows)
    paths["trials"].parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(paths["trials"], index=False)

    d_mean, d_sd = reevaluate(DEFAULT)
    from scipy.stats import mannwhitneyu
    bo = np.array([f["reeval_p999_mean"] for f in final if f["method"] == "bo"])
    rnd = np.array([f["reeval_p999_mean"] for f in final if f["method"] == "random"])
    u = mannwhitneyu(bo, rnd, alternative="less")
    summary = dict(
        note="Synthetic latency model; validates methodology only.",
        seeds=a.seeds, evals=a.evals, samples_per_eval=a.n,
        default_p999_us=dict(mean=d_mean, sd=d_sd),
        bo_p999_us=dict(median=float(np.median(bo)), mean=float(bo.mean()), min=float(bo.min()), max=float(bo.max())),
        random_p999_us=dict(median=float(np.median(rnd)), mean=float(rnd.mean()), min=float(rnd.min()), max=float(rnd.max())),
        reduction_vs_default_bo=float(1 - np.median(bo) / d_mean),
        reduction_vs_default_random=float(1 - np.median(rnd) / d_mean),
        mannwhitney_bo_less_than_random=dict(U=float(u.statistic), p=float(u.pvalue)),
        search_runtime_s=round(time.time() - t0, 1),
        runs=final,
    )
    paths["results"].write_text(json.dumps(summary, indent=2))
    make_figures(df, final, summary, paths)
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=2))
    if out_dir is not None:
        print(f"outputs in {out_dir}")


def make_figures(df, final, summary, paths=None):
    paths = paths or output_paths(None)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.ensemble import RandomForestRegressor
    figs, pre = Path(paths["figs"]), paths["prefix"]
    figs.mkdir(parents=True, exist_ok=True)
    col = {"bo": "#1f6fb4", "random": "#d17b0f", "default": "#555555"}
    lab = {"bo": "Bayesian optimisation (GP, EI)", "random": "Random search"}

    # 1. convergence: best observed so far, mean +- 95% CI over seeds, log scale
    fig, ax = plt.subplots(figsize=(6.4, 4))
    for m in ("bo", "random"):
        mat = np.array([np.minimum.accumulate(g.sort_values("i")["p999"].to_numpy())
                        for _, g in df[df.method == m].groupby("seed")])
        lm = np.log10(mat)
        mean, se = lm.mean(0), lm.std(0, ddof=1) / np.sqrt(len(lm))
        x = np.arange(1, mat.shape[1] + 1)
        ax.plot(x, 10**mean, color=col[m], label=lab[m])
        ax.fill_between(x, 10**(mean - 1.96 * se), 10**(mean + 1.96 * se), color=col[m], alpha=0.2)
    ax.axhline(summary["default_p999_us"]["mean"], color=col["default"], ls="--", label="Untuned default")
    ax.set_yscale("log"); ax.set_xlabel("Evaluations"); ax.set_ylabel("Best observed p99.9 latency (us)")
    ax.set_title("Convergence of the search (synthetic model)"); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(figs / f"{pre}convergence.png", dpi=200); plt.close(fig)

    # 2. complementary CDF: default vs best BO configuration (seed 0)
    best = next(f for f in final if f["method"] == "bo" and f["seed"] == 0)["best_cfg"]
    fig, ax = plt.subplots(figsize=(6.4, 4))
    for name, c, colr in (("Untuned default", DEFAULT, col["default"]), ("Best BO configuration", best, col["bo"])):
        lat = np.sort(simulate_latencies(c, 1_000_000, np.random.default_rng(42)))
        ccdf = 1 - np.arange(1, len(lat) + 1) / len(lat)
        keep = ccdf > 0
        ax.loglog(lat[keep][::50], ccdf[keep][::50], color=colr, label=name)
    ax.axhline(1e-3, color="#999999", lw=0.8, ls=":"); ax.text(ax.get_xlim()[0] * 1.1, 1.3e-3, "p99.9", color="#666666")
    ax.set_xlabel("Latency (us)"); ax.set_ylabel("P(latency > x)")
    ax.set_title("Tail of the latency distribution (synthetic model)"); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(figs / f"{pre}tail_ccdf.png", dpi=200); plt.close(fig)

    # 3. parameter importance: SHAP on a random-forest surrogate fitted to all BO trials
    import shap
    bo_df = df[df.method == "bo"]
    X, y = bo_df[NAMES], np.log10(bo_df["p999"])
    rf = RandomForestRegressor(300, random_state=0, n_jobs=-1).fit(X, y)
    sv = shap.TreeExplainer(rf).shap_values(X)
    imp = np.abs(sv).mean(0)
    order = np.argsort(imp)
    fig, ax = plt.subplots(figsize=(6.4, 4))
    ax.barh([NAMES[i] for i in order], imp[order], color=col["bo"])
    ax.set_xlabel("Mean |SHAP| on log10 p99.9"); ax.set_title("Parameter importance (RF surrogate, BO trials)")
    fig.tight_layout(); fig.savefig(figs / f"{pre}param_importance.png", dpi=200); plt.close(fig)
    summary["importance"] = {NAMES[i]: float(imp[i]) for i in order[::-1]}
    Path(paths["results"]).write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
