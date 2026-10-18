"""Sensitivity of the BO-vs-random conclusions to the hand-chosen coefficients of the SYNTHETIC model.

IMPORTANT: everything here runs on the SYNTHETIC latency model of `bo_sim.py` (coefficients in
`bo_sim.COEF_DEFAULTS`). It tests whether the methodological conclusions (BO beats random search;
isolated_cores is the most important parameter) survive changes to the assumed effect sizes. It
says nothing about a real kernel.

Design
------
* Perturbed coefficients (22): every continuous coefficient of `model_factors` plus the body sigma,
  Pareto shape and the isolation cap. The structural thresholds irq_over_min_iso (7) and
  rt_high_min (95) are held fixed. Perturbation by a multiplier f:
    - magnitude coefficients (SCALE_KIND): value * f  (iso_cap rounded to an integer);
    - multiplicative factors (FACTOR_KIND, e.g. preempt_rt body x1.08, governor p x0.8): the
      EFFECT is scaled on the log scale, value ** f. This keeps every factor positive and on its
      side of 1 (x0.5 of 0.97 would otherwise become 0.485, x2 of 1.08 a 2.16x body penalty, i.e. a
      different model rather than a different effect size). E.g. 0.45 -> 0.67 (f=0.5) / 0.20 (f=2).
  then clamped (CLAMPS) so probabilities stay in (0, 0.5] and gains below 1.
* Models: "base" (empty override; must reproduce the base budget run exactly), one-at-a-time
  (OAT) models for every coefficient at f in {0.5, 2, 0.75, 1.5} (extremes first), then a global
  joint sweep: scrambled Sobol points, every multiplier log-uniform in [0.5, 2].
* Per model, ground truth by EXHAUSTIVE evaluation of the full 2,879,712-point search space (no
  structural shortcuts, so it stays valid under any perturbation): all distinct (body, p, scale)
  triples are solved on a 201-node quadrature, everything within 0.5% of the minimum is re-solved
  on the 4001-node grid used by bo_budget.true_p999, and the optimum value is finally recomputed
  with the scalar bo_budget.true_p999. The same exhaustive table gives exact variance-based
  (Sobol first-order and total-effect) importances of log10 true p99.9 under the uniform
  distribution on the search space (which is what random search samples).
* Searches, identical to bo_budget.py (1e6 samples per noisy evaluation, best-observed pick,
  regret against the analytic optimum, the same 30 seeds for every model):
    - BO: one 150-evaluation gp_minimize-equivalent chain per seed; budgets 10/20/40/80 are its
      prefixes. This is exact: gp_minimize's proposals do not depend on n_calls (verified on all
      30 seeds x 4 budgets of the base run, and by the base-model reproduction check). The chain
      is the gp_minimize loop written out (same Optimizer construction and RNG use) so that its
      state can be pickled and resumed across tool calls.
    - random: one job per (budget, seed), exactly bo_sim.run_search.
* Checkpointing: results append to checkpoint.jsonl; BO chains in progress keep a pickled state
  under state/ (removed when the chain completes). Each call stops starting work at --max-seconds.

Run (repeat the second command until it prints "all jobs done"; it then writes the analysis):
  python3 scripts/experiments/bo_sensitivity.py --label sensitivity
  python3 scripts/experiments/bo_sensitivity.py --out data/bo_sim_runs/<dir>
  python3 scripts/experiments/bo_sensitivity.py --out data/bo_sim_runs/<dir> --analyse   (partial)
"""
import argparse
import json
import math
import os
import pickle
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
from scripts.experiments import bo_budget as B  # noqa: E402
from scripts.experiments import bo_sim as S  # noqa: E402

GRID = (0.5, 2.0, 0.75, 1.5)            # OAT multipliers, extremes first
SCALE_KIND = ["base_median_us", "base_event_p", "base_stall_us", "alpha", "body_sigma", "iso_decay",
              "iso_cap", "rtprio_scale_gain", "coalesce_gain", "coalesce_sat_us", "coalesce_body"]
FACTOR_KIND = ["irq_noiso_p", "irq_iso_p", "irq_over_p", "nohz_p", "rt_scale", "rt_body", "gov_p",
               "gov_body", "numa_p", "numa_body", "rt_high_p"]
PERTURBED = SCALE_KIND + FACTOR_KIND
CLAMPS = dict(base_event_p=(1e-7, 0.5), rtprio_scale_gain=(0.0, 0.95), coalesce_gain=(0.0, 0.95),
              iso_cap=(1, 8), coalesce_sat_us=(1.0, 100.0), body_sigma=(0.01, 2.0), alpha=(0.2, 20.0))
MAX_BUDGET = max(B.BUDGETS)
GRID_SHAPE = (9, 2, 2, 2, 2, 2, 99, 101)   # full search space, axes in S.NAMES order
SOBOL_SEED = 20261014


# ---------------------------------------------------------------- design
def perturbed_coef(mult):
    """Coefficient override for multipliers {name: f} (see module docstring for the two kinds)."""
    out = {}
    for name, f in mult.items():
        base = S.COEF_DEFAULTS[name]
        if name not in PERTURBED:
            raise KeyError(f"{name} is not a perturbed coefficient")
        if f <= 0:
            raise ValueError(f"multiplier for {name} must be positive")
        v = base ** f if name in FACTOR_KIND else base * f
        lo, hi = CLAMPS.get(name, (-math.inf, math.inf))
        v = min(max(v, lo), hi)
        out[name] = int(round(v)) if name == "iso_cap" else float(v)
    if "iso_cap" in out:
        out["iso_cap"] = int(min(max(out["iso_cap"], CLAMPS["iso_cap"][0]), CLAMPS["iso_cap"][1]))
    return out


def design(n_global=128, sobol_seed=SOBOL_SEED):
    """Ordered model list: base, OAT (level-major, extremes first), then global Sobol points."""
    from scipy.stats import qmc
    models = [dict(model_id="base", kind="base", mult={})]
    for level in GRID:
        for name in PERTURBED:
            models.append(dict(model_id=f"oat|{name}|x{level:g}", kind="oat", param=name, level=level,
                               mult={name: level}))
    if n_global:
        u = qmc.Sobol(d=len(PERTURBED), scramble=True, seed=sobol_seed).random(n_global)
        for j, row in enumerate(u):
            models.append(dict(model_id=f"glob|{j:03d}", kind="global", index=j,
                               mult={nm: float(2.0 ** (2.0 * x - 1.0)) for nm, x in zip(PERTURBED, row)}))
    for m in models:
        m["coef"] = perturbed_coef(m["mult"])
    return models


def job_keys(model_id, seeds):
    """All job keys of one model: truth, one BO chain per seed, one random job per (budget, seed)."""
    keys = [f"{model_id}#truth"] + [f"{model_id}#bo#{s}" for s in range(seeds)]
    keys += [f"{model_id}#random#{b}#{s}" for b in sorted(B.BUDGETS, reverse=True) for s in range(seeds)]
    return keys


# ---------------------------------------------------------------- exhaustive ground truth
def factors_grid(coef=None):
    """(body, p, scale) of the SYNTHETIC model on the full search space, arrays of GRID_SHAPE.
    Mirrors bo_sim.model_factors operation by operation (checked against it in the tests)."""
    k = S.coefs(coef)

    def ax(v, i):
        shp = [1] * 8
        shp[i] = -1
        return np.asarray(v).reshape(shp)
    iso, irq, nohz, prt, gov, numa = (ax(np.arange(9), 0), ax([0, 1], 1), ax([0, 1], 2), ax([0, 1], 3),
                                      ax([0, 1], 4), ax([0, 1], 5))
    rt, co = ax(np.arange(1, 100), 6), ax(np.arange(101), 7)
    one = 1.0
    p = k["base_event_p"] * np.exp(-k["iso_decay"] * np.minimum(iso, k["iso_cap"]))
    p = p * np.where(irq == 1, np.where(iso == 0, k["irq_noiso_p"], k["irq_iso_p"]), one)
    p = p * np.where((irq == 1) & (iso >= k["irq_over_min_iso"]), k["irq_over_p"], one)
    p = p * np.where((nohz == 1) & (iso >= 1), k["nohz_p"], one)
    scale = k["base_stall_us"] * np.where(prt == 1, k["rt_scale"], one)
    body = k["base_median_us"] * np.where(prt == 1, k["rt_body"], one)
    p = p * np.where(gov == 1, k["gov_p"], one)
    body = body * np.where(gov == 1, k["gov_body"], one)
    p = p * np.where(numa == 1, k["numa_p"], one)
    body = body * np.where(numa == 1, k["numa_body"], one)
    scale = scale * np.where(iso == 0, 1.0 - k["rtprio_scale_gain"] * np.log(rt) / np.log(99), one)
    p = p * np.where(rt >= k["rt_high_min"], k["rt_high_p"], one)
    p = p * (1.0 - k["coalesce_gain"] * (np.minimum(co, k["coalesce_sat_us"]) / k["coalesce_sat_us"]))
    body = body + k["coalesce_body"] * co
    return tuple(np.broadcast_to(a, GRID_SHAPE).astype(float) for a in (body, p, scale))


def grid_cfg(flat_index):
    """Configuration dict of a flat index into GRID_SHAPE."""
    idx = np.unravel_index(int(flat_index), GRID_SHAPE)
    vals = list(idx)
    vals[6] += 1   # rt_priority starts at 1
    return dict(zip(S.NAMES, (int(v) for v in vals)))


def _quantiles(f, sigma, alpha, m, iters, chunk=4000):
    out = np.empty(len(f))
    for i in range(0, len(f), chunk):
        c = f[i:i + chunk]
        out[i:i + chunk] = B.quantile_from_factors(c[:, 0], c[:, 1], c[:, 2], m=m, iters=iters,
                                                   sigma=sigma, alpha=alpha)
    return out


def sobol_indices(Y):
    """Exact first-order and total-effect Sobol indices of Y over a uniform full-factorial grid."""
    V = Y.var()
    s1, st = {}, {}
    for i, name in enumerate(S.NAMES):
        others = tuple(j for j in range(Y.ndim) if j != i)
        s1[name] = float(Y.mean(axis=others).var() / V)
        st[name] = float(Y.var(axis=i).mean() / V)
    return s1, st


def ranks_of(d):
    order = sorted(d, key=lambda k: -d[k])
    return {k: order.index(k) + 1 for k in d}


def truth_job(model, screen_m=201, screen_iters=40, window=0.005):
    """Worker: exhaustive optimum, default p99.9 and exact Sobol importances for one model."""
    S.limit_threads()
    t0 = time.time()
    coef = model["coef"]
    k = S.coefs(coef)
    body, p, scale = factors_grid(coef)
    trip = np.stack([body.ravel(), p.ravel(), scale.ravel()], axis=1)
    uniq, inv = np.unique(trip, axis=0, return_inverse=True)
    inv = inv.ravel()
    q = _quantiles(uniq, k["body_sigma"], k["alpha"], screen_m, screen_iters)
    near = np.flatnonzero(q <= q.min() * (1 + window))
    qn = _quantiles(uniq[near], k["body_sigma"], k["alpha"], 4001, 60)
    best_fine = qn.min()
    tie_trip = set(near[qn <= best_fine * (1 + 1e-9)].tolist())
    tie_flat = np.flatnonzero(np.isin(inv, list(tie_trip)))
    opt_cfg = grid_cfg(tie_flat[0])                       # first in enumeration order
    opt_val = B.true_p999(opt_cfg, coef=coef)              # scalar path, as in bo_budget
    # quadrature check of the screening grid on a random sample of triples + all near-optimal ones
    rs = np.random.default_rng(0).choice(len(uniq), min(300, len(uniq)), replace=False)
    qs = _quantiles(uniq[rs], k["body_sigma"], k["alpha"], 4001, 60)
    # consistency of the vectorised grid with the scalar model at the optimum and 200 random configs
    fl = np.random.default_rng(1).integers(0, trip.shape[0], 200).tolist() + [int(tie_flat[0])]
    mf_err = max(abs(a / b - 1) for i in fl
                 for a, b in zip(S.model_factors(grid_cfg(i), coef), trip[i]) if b != 0)
    reduced_ok = bool(any(opt_cfg_r["rt_priority"] in (1, 94, 99) and opt_cfg_r["irq_coalesce_us"] <= 50
                          for opt_cfg_r in (grid_cfg(i) for i in tie_flat[:5000])))
    Y = np.log10(q[inv]).reshape(GRID_SHAPE)
    s1, st = sobol_indices(Y)
    return dict(
        key=f"{model['model_id']}#truth", model_id=model["model_id"], kind="truth",
        optimum_cfg=opt_cfg, optimum_p999_us=opt_val, n_optimum_ties_full_space=int(len(tie_flat)),
        default_p999_us=B.true_p999(S.DEFAULT, coef=coef),
        verification=dict(method="exhaustive over all distinct factor triples of the full space",
                          full_space_size=int(trip.shape[0]), distinct_factor_triples=int(len(uniq)),
                          n_rechecked_fine=int(len(near)), screen_m=screen_m,
                          screen_vs_fine_max_rel_err_sample=float(np.max(np.abs(q[rs] / qs - 1))),
                          screen_vs_fine_max_rel_err_near=float(np.max(np.abs(q[near] / qn - 1))),
                          fine_vs_scalar_opt_rel=float(best_fine / opt_val - 1),
                          grid_vs_scalar_factors_max_rel=float(mf_err),
                          base_reduced_space_contains_optimum=reduced_ok),
        log10_p999_space=dict(mean=float(Y.mean()), sd=float(Y.std()), min=float(Y.min()), max=float(Y.max())),
        sobol_first=s1, sobol_total=st, rank_total=ranks_of(st), rank_first=ranks_of(s1),
        seconds=round(time.time() - t0, 2))


# ---------------------------------------------------------------- searches
def _compact(trials):
    return [[int(t[k]) for k in S.NAMES] + [float(t["p999"])] for t in trials]


def _pick_record(trials, coef):
    """Best observed trial (first minimum, as bo_sim.run_search) and its TRUE p99.9."""
    best = min(trials, key=lambda t: t["p999"])
    cfg = {k: int(best[k]) for k in S.NAMES}
    return dict(picked_cfg=cfg, observed_p999=float(best["p999"]), true_p999=B.true_p999(cfg, coef=coef),
                n_distinct_cfgs=len({tuple(t[k] for k in S.NAMES) for t in trials}))


def _new_bo_state(seed):
    """Optimizer exactly as skopt.gp_minimize(..., n_initial_points=10, acq_func='EI',
    noise='gaussian', random_state=seed) builds it (skopt 0.10 defaults otherwise)."""
    from sklearn.utils import check_random_state   # what skopt.optimizer.gp uses
    from skopt import Optimizer
    from skopt.utils import cook_estimator, normalize_dimensions
    rng = check_random_state(seed)
    space = normalize_dimensions(S.space())
    est = cook_estimator("GP", space=space, random_state=rng.randint(0, np.iinfo(np.int32).max),
                         noise="gaussian")
    opt = Optimizer(space, est, n_initial_points=10, initial_point_generator="random", n_jobs=1,
                    acq_func="EI", acq_optimizer="auto", random_state=rng, model_queue_size=None,
                    space_constraint=None,
                    acq_optimizer_kwargs=dict(n_points=10000, n_restarts_optimizer=5, n_jobs=1),
                    acq_func_kwargs=dict(xi=0.01, kappa=1.96))
    return dict(opt=opt, noise_rng=np.random.default_rng(10_000 * seed + 7), trials=[], seconds=0.0)


def _save_state(path, st):
    tmp = Path(str(path) + ".tmp")
    with tmp.open("wb") as fh:
        pickle.dump(st, fh)
    os.replace(tmp, path)


def bo_chain(args):
    """Worker: advance one BO chain (model, seed) until `deadline` or MAX_BUDGET evaluations.
    Returns ("partial", n_evals) or ("final", record with one pick per budget)."""
    S.limit_threads()
    warnings.filterwarnings("ignore", category=UserWarning)
    model_id, coef, seed, n, deadline, state_path, max_budget = args
    sp = Path(state_path)
    st = pickle.loads(sp.read_bytes()) if sp.exists() else _new_bo_state(seed)
    opt, nrng, trials = st["opt"], st["noise_rng"], st["trials"]
    t_start, last, since_save = time.time(), 0.0, 0
    while len(trials) < max_budget:
        if time.time() + 2.0 * last + 2.0 > deadline:
            st["seconds"] += time.time() - t_start
            _save_state(sp, st)
            return ("partial", dict(key=f"{model_id}#bo#{seed}", n_evals=len(trials)))
        t = time.time()
        x = opt.ask()
        m = S.measure(S.to_cfg(x), n=n, seed=int(nrng.integers(2**31)), coef=coef)
        trials.append(dict(method="bo", seed=seed, i=len(trials), **S.to_cfg(x), **m))
        if len(trials) < max_budget:      # the final tell only refits a GP nobody uses
            opt.tell(x, float(np.log10(m["p999"])))
            del opt.models[:-1]           # older GPs are never reused (ask needs the latest); small state
        last = time.time() - t
        since_save += 1
        if since_save >= 10 and len(trials) < max_budget:
            st["seconds"] += time.time() - t_start
            t_start, since_save = time.time(), 0
            _save_state(sp, st)
    st["seconds"] += time.time() - t_start
    picks = {str(b): _pick_record(trials[:b], coef) for b in B.BUDGETS if b <= max_budget}
    return ("final", dict(key=f"{model_id}#bo#{seed}", model_id=model_id, kind="bo", method="bo", seed=seed,
                          samples_per_eval=n, picks=picks, trials=_compact(trials),
                          seconds=round(st["seconds"], 2)))


def random_job(args):
    """Worker: one random-search run (exactly bo_sim.run_search) on a perturbed model."""
    S.limit_threads()
    model_id, coef, budget, seed, n = args
    t = time.time()
    trials, _, _ = S.run_search(("random", seed, budget, n, coef))
    rec = dict(key=f"{model_id}#random#{budget}#{seed}", model_id=model_id, kind="random", method="random",
               budget=budget, seed=seed, samples_per_eval=n, **_pick_record(trials, coef),
               seconds=round(time.time() - t, 2))
    if budget == MAX_BUDGET:
        rec["trials"] = _compact(trials)
    return rec


# ---------------------------------------------------------------- scheduler
def random_cost(b):
    return 0.06 * b + 1.0           # s per job at n=1e6 (bo_budget.py estimate; measured 0.44..6.6 s)


TRUTH_COST = 75.0                   # s, generous (measured ~50-55 s with 6 busy workers)
MIN_CHAIN_SLOT = 20.0               # do not start/advance a BO chain with less time than this


def pending_work(models, done, state_dir, seeds):
    """Ordered pending work: BO chains already in progress first, then model by model
    (truth, BO chains, random jobs)."""
    in_prog, rest = [], []
    for mi, m in enumerate(models):
        for key in job_keys(m["model_id"], seeds):
            if key in done:
                continue
            parts = key.split("#")
            if parts[1] == "bo":
                item = ("bo", mi, int(parts[2]))
                (in_prog if (state_dir / state_name(key)).exists() else rest).append(item)
            elif parts[1] == "truth":
                rest.append(("truth", mi))
            else:
                rest.append(("random", mi, int(parts[2]), int(parts[3])))
    return in_prog + rest


def state_name(key):
    return key.replace("|", "_").replace("#", "__") + ".pkl"


def run_pending(out, models, n, seeds, workers, max_seconds, slack=1.3, log=print):
    t0 = time.time()
    hard = t0 + max_seconds
    ckpt, state_dir = out / "checkpoint.jsonl", out / "state"
    state_dir.mkdir(exist_ok=True)
    done = B.load_done(ckpt)
    work = pending_work(models, done, state_dir, seeds)
    log(f"{len(done)} done, {len(work)} pending ({sum(1 for w in work if w[0] == 'bo')} BO chains)", flush=True)
    new_final, partial = 0, 0
    with ProcessPoolExecutor(workers, initializer=S.limit_threads) as ex, ckpt.open("a") as fh:
        running = {}
        while work or running:
            while work and len(running) < workers:
                left = hard - time.time()
                fit = None
                for w in work:
                    need = (MIN_CHAIN_SLOT if w[0] == "bo" else
                            slack * TRUTH_COST if w[0] == "truth" else slack * random_cost(w[2]))
                    if need <= left:
                        fit = w
                        break
                if fit is None:
                    work = []
                    break
                work.remove(fit)
                m = models[fit[1]]
                if fit[0] == "truth":
                    fut = ex.submit(truth_job, m)
                elif fit[0] == "bo":
                    key = f"{m['model_id']}#bo#{fit[2]}"
                    fut = ex.submit(bo_chain, (m["model_id"], m["coef"], fit[2], n, hard - 4.0,
                                               str(state_dir / state_name(key)), MAX_BUDGET))
                else:
                    fut = ex.submit(random_job, (m["model_id"], m["coef"], fit[2], fit[3], n))
                running[fut] = fit
            if not running:
                break
            fin, _ = wait(running, return_when=FIRST_COMPLETED)
            for f in fin:
                w = running.pop(f)
                r = f.result()
                if w[0] == "bo":
                    status, r = r
                    if status == "partial":
                        partial += 1
                        continue
                    sp = state_dir / state_name(r["key"])
                fh.write(json.dumps(r) + "\n")
                fh.flush()
                if w[0] == "bo" and sp.exists():
                    sp.unlink()
                new_final += 1
    total = len(models) * len(job_keys("x", seeds))
    done = B.load_done(ckpt)
    remaining = total - len(done)
    n_models_done = sum(all(k in done for k in job_keys(m["model_id"], seeds)) for m in models)
    log(f"call: {new_final} jobs finished, {partial} BO chains paused, {time.time() - t0:.0f}s; "
        f"{remaining}/{total} jobs remaining; {n_models_done}/{len(models)} models complete")
    return remaining


# ---------------------------------------------------------------- analysis
def _mw_p(x, y):
    from scipy.stats import mannwhitneyu
    x, y = np.asarray(x), np.asarray(y)
    if np.all(np.concatenate([x, y]) == x[0]):
        return 1.0                       # all identical: no evidence either way
    return float(mannwhitneyu(x, y, alternative="less").pvalue)


def model_tables(models, done, seeds):
    """Per-model truth records and per (model, budget) metrics for COMPLETE models only."""
    import pandas as pd
    rows, truths = [], {}
    for m in models:
        mid = m["model_id"]
        keys = job_keys(mid, seeds)
        if not all(k in done for k in keys):
            continue
        tr = done[f"{mid}#truth"]
        truths[mid] = tr
        opt = tr["optimum_p999_us"]
        for b in B.BUDGETS:
            rb = np.array([done[f"{mid}#bo#{s}"]["picks"][str(b)]["true_p999"] / opt - 1 for s in range(seeds)])
            rr = np.array([done[f"{mid}#random#{b}#{s}"]["true_p999"] / opt - 1 for s in range(seeds)])
            rows.append(dict(model_id=mid, kind=m["kind"], param=m.get("param"), level=m.get("level"), budget=b,
                             bo_median=float(np.median(rb)), bo_q25=float(np.percentile(rb, 25)),
                             bo_q75=float(np.percentile(rb, 75)), rnd_median=float(np.median(rr)),
                             rnd_q25=float(np.percentile(rr, 25)), rnd_q75=float(np.percentile(rr, 75)),
                             bo_within5=float((rb <= 0.05).mean()), rnd_within5=float((rr <= 0.05).mean()),
                             bo_exact=float((rb <= 1e-9).mean()),
                             diff_median=float(np.median(rb) - np.median(rr)),
                             diff_median_log10=float(np.median(np.log10(1 + rb)) - np.median(np.log10(1 + rr))),
                             mw_p=_mw_p(rb, rr), A12=B.a12(rb, rr),
                             optimum_p999_us=opt, default_p999_us=tr["default_p999_us"],
                             default_regret=tr["default_p999_us"] / opt - 1))
    return pd.DataFrame(rows), truths


def base_reproduction(done, base_run, seeds):
    """Compare the 'base' model with the original budget run: identical picks and true p99.9?"""
    ck = Path(base_run) / "checkpoint.jsonl"
    if not ck.exists() or f"base#truth" not in done:
        return dict(available=False)
    old = B.load_done(ck)
    truth = json.loads((Path(base_run) / "truth.json").read_text())
    same_cfg, max_rel, n = 0, 0.0, 0
    for b in B.BUDGETS:
        for s in range(seeds):
            for meth in ("bo", "random"):
                o = old.get(B.job_key(b, meth, s))
                new = (done.get(f"base#bo#{s}", {}).get("picks", {}).get(str(b)) if meth == "bo"
                       else done.get(f"base#random#{b}#{s}"))
                if o is None or new is None:
                    continue
                n += 1
                same_cfg += int(o["picked_cfg"] == new["picked_cfg"])
                max_rel = max(max_rel, abs(new["true_p999"] / o["true_p999"] - 1))
    tr = done["base#truth"]
    return dict(available=True, n_compared=n, n_identical_picks=same_cfg, max_rel_diff_true_p999=max_rel,
                optimum_base_run=truth["optimum_p999_us"], optimum_here=tr["optimum_p999_us"],
                optimum_cfg_identical=truth["optimum_cfg"] == tr["optimum_cfg"],
                default_base_run=truth["default_p999_us"], default_here=tr["default_p999_us"])


def shap_job(args):
    """Worker: RF (200 trees) + TreeSHAP importance on the random-search trials (budget 150, all
    seeds) of one model; cheap proxy of what a practitioner would compute from random trials."""
    S.limit_threads()
    model_id, X, y = args
    import shap
    from sklearn.ensemble import RandomForestRegressor
    X, y = np.asarray(X, float), np.asarray(y, float)
    rf = RandomForestRegressor(200, random_state=0, n_jobs=1, min_samples_leaf=2).fit(X, y)
    sub = np.random.default_rng(0).choice(len(X), min(1500, len(X)), replace=False)
    imp = np.abs(shap.TreeExplainer(rf).shap_values(X[sub])).mean(0)
    d = {nm: float(v) for nm, v in zip(S.NAMES, imp)}
    return dict(model_id=model_id, shap=d, rank=ranks_of(d))


def run_shap(out, models, done, seeds, workers, max_seconds, log=print):
    path = out / "shap.jsonl"
    have = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    have[r["model_id"]] = r
                except json.JSONDecodeError:
                    pass
    t0 = time.time()
    todo = []
    for m in models:
        mid = m["model_id"]
        keys = [f"{mid}#random#{MAX_BUDGET}#{s}" for s in range(seeds)]
        if mid in have or not all(k in done for k in keys):
            continue
        rows = [t for k in keys for t in done[k]["trials"]]
        arr = np.array(rows, float)
        todo.append((mid, arr[:, :8].tolist(), np.log10(arr[:, 8]).tolist()))
    if todo:
        with ProcessPoolExecutor(workers, initializer=S.limit_threads) as ex, path.open("a") as fh:
            running = set()
            while todo or running:
                while todo and len(running) < workers and time.time() - t0 < max_seconds - 25:
                    running.add(ex.submit(shap_job, todo.pop(0)))
                if not running:
                    break
                fin, running = wait(running, return_when=FIRST_COMPLETED)
                for f in fin:
                    r = f.result()
                    have[r["model_id"]] = r
                    fh.write(json.dumps(r) + "\n")
                    fh.flush()
    log(f"SHAP: {len(have)} models done, {len(todo)} left")
    return have, len(todo)


def _ols(y, X, names):
    """OLS with intercept: coefficients, standard errors, two-sided p-values, R^2."""
    from scipy.stats import t as tdist
    Xd = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    res = y - Xd @ beta
    dof = len(y) - Xd.shape[1]
    s2 = res @ res / dof
    cov = s2 * np.linalg.pinv(Xd.T @ Xd)
    se = np.sqrt(np.diag(cov))
    pv = 2 * tdist.sf(np.abs(beta / se), dof)
    r2 = 1 - (res @ res) / ((y - y.mean()) @ (y - y.mean()))
    return dict(r2=float(r2), dof=int(dof), intercept=float(beta[0]),
                coef={nm: dict(beta=float(b), se=float(e), p=float(p))
                      for nm, b, e, p in zip(names, beta[1:], se[1:], pv[1:])})


def _partial_spearman(y, X, names):
    """Partial Spearman correlation of y with each column of X, controlling for the others."""
    from scipy.stats import rankdata
    R = np.column_stack([rankdata(c) for c in X.T])
    ry = rankdata(y)
    out = {}
    for i, nm in enumerate(names):
        Z = np.column_stack([np.ones(len(y)), np.delete(R, i, axis=1)])
        ey = ry - Z @ np.linalg.lstsq(Z, ry, rcond=None)[0]
        ex = R[:, i] - Z @ np.linalg.lstsq(Z, R[:, i], rcond=None)[0]
        out[nm] = float(ey @ ex / math.sqrt((ey @ ey) * (ex @ ex))) if (ey @ ey) > 0 and (ex @ ex) > 0 else float("nan")
    return out


def _pct(a, q):
    return float(np.percentile(a, q)) if len(a) else float("nan")


def analyse(out, models, seeds, workers, max_seconds, base_run, log=print):
    import pandas as pd
    t0 = time.time()
    done = B.load_done(out / "checkpoint.jsonl")
    df, truths = model_tables(models, done, seeds)
    if df.empty:
        log("no complete model yet")
        return None
    df.to_csv(out / "model_metrics.csv", index=False)
    shap_have, shap_left = run_shap(out, models, done, seeds, workers, max(30.0, max_seconds - (time.time() - t0)), log)
    by_id = {m["model_id"]: m for m in models}
    mrows = []
    for mid, tr in truths.items():
        m = by_id[mid]
        row = dict(model_id=mid, kind=m["kind"], param=m.get("param"), level=m.get("level"),
                   optimum_p999_us=tr["optimum_p999_us"], default_p999_us=tr["default_p999_us"],
                   **{f"opt_{k}": v for k, v in tr["optimum_cfg"].items()},
                   **{f"mult_{k}": m["mult"].get(k, 1.0) for k in PERTURBED},
                   **{f"coef_{k}": S.coefs(m["coef"])[k] for k in PERTURBED},
                   **{f"ST_{k}": tr["sobol_total"][k] for k in S.NAMES},
                   **{f"S1_{k}": tr["sobol_first"][k] for k in S.NAMES},
                   **{f"rankST_{k}": tr["rank_total"][k] for k in S.NAMES},
                   **{f"rankS1_{k}": tr["rank_first"][k] for k in S.NAMES},
                   verified=tr["verification"]["fine_vs_scalar_opt_rel"])
        if mid in shap_have:
            row.update({f"rankSHAP_{k}": shap_have[mid]["rank"][k] for k in S.NAMES})
            row.update({f"SHAP_{k}": shap_have[mid]["shap"][k] for k in S.NAMES})
        mrows.append(row)
    mdf = pd.DataFrame(mrows)
    mdf.to_csv(out / "models.csv", index=False)

    # (a) robustness across all models, per budget
    per_budget = {}
    for b in B.BUDGETS:
        g = df[df.budget == b]
        d = {}
        for kind, gg in (("all", g), ("oat", g[g.kind.isin(["oat", "base"])]), ("global", g[g.kind == "global"])):
            if gg.empty:
                continue
            d[kind] = dict(n_models=int(len(gg)),
                           A12=dict(median=_pct(gg.A12, 50), p5=_pct(gg.A12, 5), p95=_pct(gg.A12, 95), min=float(gg.A12.min())),
                           bo_minus_random_median_regret=dict(median=_pct(gg.diff_median, 50), p5=_pct(gg.diff_median, 5),
                                                              p95=_pct(gg.diff_median, 95), max=float(gg.diff_median.max())),
                           bo_median_regret=dict(median=_pct(gg.bo_median, 50), p95=_pct(gg.bo_median, 95)),
                           random_median_regret=dict(median=_pct(gg.rnd_median, 50), p5=_pct(gg.rnd_median, 5)),
                           frac_models_bo_significant_p05=float((gg.mw_p < 0.05).mean()),
                           frac_models_A12_ge_0p71=float((gg.A12 >= 0.71).mean()),
                           frac_models_A12_lt_0p6=float((gg.A12 < 0.6).mean()),
                           frac_models_random_better_A12_lt_0p5=float((gg.A12 < 0.5).mean()),
                           bo_within5_median=_pct(gg.bo_within5, 50), rnd_within5_median=_pct(gg.rnd_within5, 50))
        per_budget[str(b)] = d

    # (b) where random is competitive (budget >= 20)
    comp = df[(df.budget >= 20) & ((df.A12 < 0.6) | (df.mw_p > 0.05))]
    competitive = [dict(model_id=r.model_id, budget=int(r.budget), A12=float(r.A12), p=float(r.mw_p),
                        bo_median=float(r.bo_median), rnd_median=float(r.rnd_median),
                        mult={k: v for k, v in by_id[r.model_id]["mult"].items()} if by_id[r.model_id]["kind"] == "oat" else None)
                   for r in comp.itertuples()]
    oat = df[df.kind == "oat"]
    oat_table = {}
    for b in B.BUDGETS:
        t = oat[oat.budget == b].pivot_table(index="param", columns="level", values="A12")
        oat_table[str(b)] = {p: {f"x{c:g}": float(t.loc[p, c]) for c in t.columns if not np.isnan(t.loc[p, c])}
                             for p in t.index}
    glob = df[df.kind == "global"]
    regression = {}
    for b in B.BUDGETS:
        g = glob[glob.budget == b]
        if len(g) > len(PERTURBED) + 5:
            X = np.array([[math.log2(by_id[mid]["mult"][k]) for k in PERTURBED] for mid in g.model_id])
            regression[str(b)] = dict(
                n_models=int(len(g)),
                ols_A12_on_log2_multipliers=_ols(g.A12.to_numpy(), X, PERTURBED),
                ols_diff_log10_regret_on_log2_multipliers=_ols(g.diff_median_log10.to_numpy(), X, PERTURBED),
                partial_spearman_A12=_partial_spearman(g.A12.to_numpy(), X, PERTURBED))
    # model-level drivers that are not coefficients: does the ease of the problem explain A12?
    ease = {}
    for b in B.BUDGETS:
        g = df[df.budget == b]
        if len(g) > 5:
            from scipy.stats import spearmanr
            ease[str(b)] = dict(
                spearman_A12_vs_log_default_regret=float(spearmanr(g.A12, np.log10(1 + g.default_regret))[0]),
                spearman_A12_vs_random_median_regret=float(spearmanr(g.A12, g.rnd_median)[0]))

    # (c) importance stability
    imp = {}
    for src, pre in (("sobol_total", "rankST_"), ("sobol_first", "rankS1_"), ("rf_shap_random_trials", "rankSHAP_")):
        cols = [pre + k for k in S.NAMES]
        if not all(c in mdf.columns for c in cols):
            continue
        sub = mdf.dropna(subset=cols)
        imp[src] = dict(
            n_models=int(len(sub)),
            frac_isolated_cores_first=float((sub[pre + "isolated_cores"] == 1).mean()),
            rank_distribution={k: {str(r): float((sub[pre + k] == r).mean()) for r in range(1, 9)} for k in S.NAMES},
            median_rank={k: float(sub[pre + k].median()) for k in S.NAMES},
            models_where_isolated_cores_not_first=sub.loc[sub[pre + "isolated_cores"] != 1, "model_id"].tolist()[:200])
    base_ver = base_reproduction(done, base_run, seeds)
    ver = dict(max_fine_vs_scalar_opt_rel=float(max(abs(t["verification"]["fine_vs_scalar_opt_rel"]) for t in truths.values())),
               max_screen_err_sample=float(max(t["verification"]["screen_vs_fine_max_rel_err_sample"] for t in truths.values())),
               max_screen_err_near=float(max(t["verification"]["screen_vs_fine_max_rel_err_near"] for t in truths.values())),
               max_grid_vs_scalar_factors=float(max(t["verification"]["grid_vs_scalar_factors_max_rel"] for t in truths.values())),
               frac_models_base_reduced_space_would_contain_optimum=float(np.mean(
                   [t["verification"]["base_reduced_space_contains_optimum"] for t in truths.values()])))
    n_kind = {k: int(sum(1 for mid in truths if by_id[mid]["kind"] == k)) for k in ("base", "oat", "global")}
    designed = {k: int(sum(1 for m in models if m["kind"] == k)) for k in ("base", "oat", "global")}
    summary = dict(
        note="SYNTHETIC latency model (bo_sim.py); sensitivity of methodological conclusions to its hand-chosen "
             "coefficients. Validates the method, not any real kernel.",
        seeds=seeds, budgets=list(B.BUDGETS), samples_per_eval=int(json.loads((out / "run_config.json").read_text())["n"]),
        models_complete=n_kind, models_designed=designed, shap_models_pending=shap_left,
        perturbed_coefficients=PERTURBED, scale_kind=SCALE_KIND, factor_kind=FACTOR_KIND, clamps=CLAMPS,
        base_reproduction=base_ver, ground_truth_checks=ver,
        optimum_p999_us=dict(min=float(mdf.optimum_p999_us.min()), median=float(mdf.optimum_p999_us.median()),
                             max=float(mdf.optimum_p999_us.max())),
        default_over_optimum=dict(min=float((mdf.default_p999_us / mdf.optimum_p999_us).min()),
                                  median=float((mdf.default_p999_us / mdf.optimum_p999_us).median()),
                                  max=float((mdf.default_p999_us / mdf.optimum_p999_us).max())),
        per_budget=per_budget,
        random_competitive_budget_ge_20=dict(rule="A12 < 0.6 or one-sided Mann-Whitney p > 0.05", n=len(competitive),
                                             cases=competitive),
        oat_A12_by_param_and_level=oat_table, global_regression=regression, problem_ease=ease,
        importance=imp, total_job_cpu_seconds=float(sum(r.get("seconds", 0) for r in done.values())))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    make_figures(out, df, mdf, summary, by_id)
    log(f"analysis written ({len(truths)} complete models)")
    return summary


def make_figures(out, df, mdf, summary, by_id):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    col = {"bo": "#1f6fb4", "random": "#d17b0f", "oat": "#1f6fb4", "global": "#7a5195", "base": "#222222"}
    budgets = list(B.BUDGETS)
    rng = np.random.default_rng(0)

    def strip(ax, field, ylab, ref=None, logy=False):
        for i, b in enumerate(budgets):
            g = df[df.budget == b]
            ax.boxplot(g[field], positions=[i], widths=0.55, showfliers=False,
                       medianprops=dict(color="#222222"), boxprops=dict(color="#888888"),
                       whiskerprops=dict(color="#888888"), capprops=dict(color="#888888"))
            for kind in ("oat", "global", "base"):
                gg = g[g.kind == kind]
                if gg.empty:
                    continue
                ax.scatter(i + rng.uniform(-0.18, 0.18, len(gg)), gg[field], s=7 if kind != "base" else 30,
                           color=col[kind], alpha=0.55 if kind != "base" else 1, lw=0,
                           label={"oat": "One-at-a-time", "global": "Global (Sobol)", "base": "Base model"}[kind] if i == 0 else None,
                           marker="o" if kind != "base" else "D", zorder=3)
        if ref is not None:
            for r, ls in ref:
                ax.axhline(r, color="#999999", ls=ls, lw=0.8,
                           label={0.5: "No difference (0.5)", 0.71: "Large effect (0.71)"}.get(r) if field == "A12" else None)
        ax.set_xticks(range(len(budgets)))
        ax.set_xticklabels([str(b) for b in budgets])
        ax.set_xlabel("Evaluation budget")
        ax.set_ylabel(ylab)
        if logy:
            ax.set_yscale("symlog", linthresh=1e-3)

    fig, ax = plt.subplots(figsize=(6.4, 4))
    strip(ax, "A12", "A12 (P[BO regret < random regret])", ref=[(0.5, "--"), (0.71, ":")])
    ax.set_ylim(0, 1.02)
    ax.set_title("BO vs random across perturbed models (synthetic model)", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(out / "a12_by_budget.png", dpi=200); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 4))
    strip(ax, "diff_median", "Median regret BO minus median regret random", ref=[(0.0, "--")], logy=True)
    ax.set_title("Regret difference across perturbed models (negative = BO better)", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(out / "regret_diff_by_budget.png", dpi=200); plt.close(fig)

    # regret envelope: per budget, distribution over models of the median regret, per method
    fig, ax = plt.subplots(figsize=(6.4, 4))
    for k, (m, f) in enumerate((("bo", "bo_median"), ("random", "rnd_median"))):
        q = np.array([[np.percentile(1 + df[df.budget == b][f], p) for p in (5, 50, 95)] for b in budgets])
        xs = np.array(budgets) * (0.97 if k == 0 else 1.03)
        ax.plot(xs, q[:, 1], "o-", color=col[m], label={"bo": "BO (GP, EI)", "random": "Random search"}[m])
        ax.fill_between(xs, q[:, 0], q[:, 2], color=col[m], alpha=0.18, lw=0)
    ax.axhline(1.05, color="#999999", ls=":", lw=0.8, label="Within 5% of optimum")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks(budgets); ax.set_xticklabels([str(b) for b in budgets])
    ax.set_xlabel("Evaluation budget"); ax.set_ylabel("Median over seeds of 1 + regret")
    ax.set_title("Median regret across models: median and 5-95% band (synthetic model)", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(out / "regret_envelope.png", dpi=200); plt.close(fig)

    # OAT heatmap of A12 for budgets 10 / 20 / 40
    oat = df[df.kind == "oat"]
    if not oat.empty:
        levels = sorted(GRID)
        fig, axes = plt.subplots(1, 3, figsize=(9.6, 6.4), sharey=True)
        for ax, b in zip(axes, (10, 20, 40)):
            t = oat[oat.budget == b].pivot_table(index="param", columns="level", values="A12")
            t = t.reindex(index=PERTURBED, columns=levels)
            im = ax.imshow(t.to_numpy(), vmin=0.3, vmax=1.0, cmap="RdBu", aspect="auto")
            for (i, j), v in np.ndenumerate(t.to_numpy()):
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6,
                            color="white" if v > 0.85 or v < 0.45 else "black")
            ax.set_xticks(range(len(levels))); ax.set_xticklabels([f"x{v:g}" for v in levels], fontsize=7)
            ax.set_yticks(range(len(PERTURBED))); ax.set_yticklabels(PERTURBED, fontsize=7)
            ax.set_title(f"budget {b}", fontsize=9)
        fig.colorbar(im, ax=axes, shrink=0.6, label="A12 (BO better)")
        fig.suptitle("One-at-a-time perturbations: A12 of BO vs random (synthetic model)", fontsize=10)
        fig.savefig(out / "oat_a12_heatmap.png", dpi=200, bbox_inches="tight"); plt.close(fig)

    reg = summary["global_regression"]
    if reg:
        fig, axes = plt.subplots(1, 2, figsize=(9.6, 5.2), sharey=True)
        for ax, b in zip(axes, ("20", "40")):
            if b not in reg:
                continue
            c = reg[b]["ols_A12_on_log2_multipliers"]["coef"]
            beta = np.array([c[k]["beta"] for k in PERTURBED])
            se = np.array([c[k]["se"] for k in PERTURBED])
            y = np.arange(len(PERTURBED))
            ax.errorbar(beta, y, xerr=1.96 * se, fmt="o", color=col["global"], ms=3, lw=0.8)
            ax.axvline(0, color="#999999", lw=0.8)
            ax.set_yticks(y); ax.set_yticklabels(PERTURBED, fontsize=7)
            ax.set_xlabel("Change in A12 per doubling of the coefficient")
            ax.set_title(f"budget {b} (R$^2$ = {reg[b]['ols_A12_on_log2_multipliers']['r2']:.2f})", fontsize=9)
        fig.suptitle("Global sweep: OLS of A12 on log2 multipliers, 95% CI (synthetic model)", fontsize=10)
        fig.tight_layout(); fig.savefig(out / "global_a12_regression.png", dpi=200); plt.close(fig)

    imp = summary["importance"]
    srcs = [s for s in ("sobol_total", "rf_shap_random_trials") if s in imp]
    if srcs:
        fig, axes = plt.subplots(1, len(srcs), figsize=(4.8 * len(srcs), 4), sharey=True, squeeze=False)
        # one row order for every panel: the panels share the y axis, so per-panel orders would mislabel rows
        rd0 = imp[srcs[0]]["rank_distribution"]
        order = sorted(S.NAMES, key=lambda k: (imp[srcs[0]]["median_rank"][k],
                                               sum(int(r) * p for r, p in rd0[k].items())))
        for ax, s in zip(axes[0], srcs):
            rd = imp[s]["rank_distribution"]
            mat = np.array([[rd[k][str(r)] for r in range(1, 9)] for k in order])
            im = ax.imshow(mat, vmin=0, vmax=1, cmap="Blues", aspect="auto")
            for (i, j), v in np.ndenumerate(mat):
                if v > 0:
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6, color="white" if v > 0.6 else "black")
            ax.set_xticks(range(8)); ax.set_xticklabels([str(r) for r in range(1, 9)])
            ax.set_yticks(range(8)); ax.set_yticklabels(order, fontsize=8)
            ax.set_xlabel("Importance rank (1 = most important)")
            ax.set_title({"sobol_total": "True total-effect Sobol index",
                          "rf_shap_random_trials": "RF-SHAP on random-search trials"}[s] + f" (n={imp[s]['n_models']})",
                         fontsize=9)
        fig.colorbar(im, ax=axes[0].tolist(), shrink=0.7, label="Fraction of models")
        fig.suptitle("Stability of the parameter-importance ranking (synthetic model)", fontsize=10)
        fig.savefig(out / "importance_rank_stability.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def write_readme(out, summary, args, runtime_note=""):
    if summary is None:
        return
    pb = summary["per_budget"]
    lines = [
        "# Sensitivity analysis of the BO-vs-random budget study (SYNTHETIC model)",
        "",
        "All numbers come from the synthetic latency model in `scripts/experiments/bo_sim.py`; they test whether the",
        "methodological conclusions survive changes to its hand-chosen coefficients, not anything about a real kernel.",
        "",
        "Produced by `scripts/experiments/bo_sensitivity.py` (see its docstring for the full design).",
        "",
        "## What was run",
        f"- Models complete: {summary['models_complete']} (designed: {summary['models_designed']}).",
        f"- Perturbed coefficients ({len(PERTURBED)}): magnitudes scaled by f ({', '.join(SCALE_KIND)});",
        f"  multiplicative factors with the log-effect scaled, value**f ({', '.join(FACTOR_KIND)}). Clamps: {CLAMPS}.",
        "- OAT grid f in {0.5, 0.75, 1.5, 2}; global sweep: scrambled Sobol (seed "
        f"{SOBOL_SEED}), each multiplier log-uniform in [0.5, 2].",
        f"- Per model: budgets {list(B.BUDGETS)} x {{BO, random}} x {summary['seeds']} seeds (seeds shared across models),",
        f"  {summary['samples_per_eval']:,} samples per noisy evaluation; BO budgets are prefixes of one 150-evaluation chain",
        "  (exactly equivalent to separate gp_minimize runs).",
        "- Ground truth per model: exhaustive over the full 2,879,712-point space; regret = true p99.9(pick)/optimum - 1.",
        "- True importance: exact first-order and total-effect Sobol indices of log10 true p99.9 under the uniform",
        "  distribution on the search space; RF-SHAP on the random-search trials (budget 150, all seeds) for comparison.",
        "",
        "## Headline (all complete models)",
        "| budget | median A12 | A12 p5-p95 | median (BO - random) regret | p5-p95 | frac p<0.05 |",
        "|---|---|---|---|---|---|",
    ]
    for b in B.BUDGETS:
        a = pb[str(b)]["all"]
        lines.append(f"| {b} | {a['A12']['median']:.3f} | {a['A12']['p5']:.3f}-{a['A12']['p95']:.3f} | "
                     f"{a['bo_minus_random_median_regret']['median']:.4f} | "
                     f"{a['bo_minus_random_median_regret']['p5']:.4f}-{a['bo_minus_random_median_regret']['p95']:.4f} | "
                     f"{a['frac_models_bo_significant_p05']:.3f} |")
    imp = summary["importance"].get("sobol_total")
    if imp:
        lines += ["", f"isolated_cores is the top parameter (total-effect Sobol) in {imp['frac_isolated_cores_first']:.1%} "
                      f"of {imp['n_models']} models."]
    rb = summary["base_reproduction"]
    if rb.get("available"):
        lines += ["", f"Base-model reproduction: {rb['n_identical_picks']}/{rb['n_compared']} identical picks vs the "
                      f"base run, max relative difference of true p99.9 {rb['max_rel_diff_true_p999']:.2e}; optimum "
                      f"{rb['optimum_here']:.4f} us (base run {rb['optimum_base_run']:.4f}), default "
                      f"{rb['default_here']:.2f} us."]
    lines += ["", "## Files",
              "- `models.json` design (multipliers and coefficient overrides); `run_config.json` settings.",
              "- `checkpoint.jsonl` one line per finished job (truth / BO chain / random run; trials kept for BO chains",
              "  and random budget-150 runs); `shap.jsonl` RF-SHAP per model.",
              "- `model_metrics.csv` per (model, budget) metrics; `models.csv` per-model truth, importance and ranks.",
              "- `summary.json` aggregates; figures `a12_by_budget.png`, `regret_diff_by_budget.png`, `regret_envelope.png`,",
              "  `oat_a12_heatmap.png`, `global_a12_regression.png`, `importance_rank_stability.png`.",
              "", runtime_note]
    (out / "README.md").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="run directory (reuse to resume)")
    ap.add_argument("--label", default="sensitivity")
    ap.add_argument("--n", type=int, default=1_000_000, help="samples per noisy evaluation")
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--n-global", type=int, default=128, help="Sobol points (a power of 2)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-seconds", type=float, default=200)
    ap.add_argument("--analyse", action="store_true", help="only (re)write the analysis of complete models")
    ap.add_argument("--base-run", default=str(S.RUNS_DIR / "20261014-1628_budget_n1e6"))
    a = ap.parse_args(argv)
    t0 = time.time()
    if a.workers > 6:
        sys.exit("at most 6 workers")
    out = Path(a.out) if a.out else S.new_run_dir(a.label)
    out.mkdir(parents=True, exist_ok=True)
    print(f"run dir: {out}")
    cfg_path, design_path = out / "run_config.json", out / "models.json"
    if cfg_path.exists():
        old = json.loads(cfg_path.read_text())
        if (old["n"], old["seeds"], old["n_global"]) != (a.n, a.seeds, a.n_global):
            sys.exit(f"run dir was created with n={old['n']} seeds={old['seeds']} n_global={old['n_global']}")
        models = json.loads(design_path.read_text())
    else:
        models = design(a.n_global)
        design_path.write_text(json.dumps(models, indent=1))
        cfg_path.write_text(json.dumps(dict(n=a.n, seeds=a.seeds, n_global=a.n_global, budgets=B.BUDGETS,
                                            grid=GRID, sobol_seed=SOBOL_SEED, workers=a.workers,
                                            started=time.strftime("%Y-%m-%dT%H:%M:%S"),
                                            note="SYNTHETIC model sensitivity sweep"), indent=2))
    left = None
    lock = out / "run.lock"
    if lock.exists():   # a previous call that outlived the tool timeout must not run concurrently
        try:
            pid = int(lock.read_text())
            os.kill(pid, 0)
            sys.exit(f"another call (pid {pid}) is still running; retry shortly")
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    lock.write_text(str(os.getpid()))
    try:
        if not a.analyse:
            left = run_pending(out, models, a.n, a.seeds, a.workers, a.max_seconds - (time.time() - t0))
    finally:
        lock.unlink(missing_ok=True)
        print(f"wall {time.time() - t0:.0f}s")
    if a.analyse or left == 0:
        s = analyse(out, models, a.seeds, a.workers, a.max_seconds - (time.time() - t0), a.base_run)
        write_readme(out, s, a)
        if left == 0:
            print("all jobs done")


if __name__ == "__main__":
    main()
