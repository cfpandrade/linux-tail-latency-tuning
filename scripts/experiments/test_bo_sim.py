"""Unit tests for the simulator, its output handling, the analytic ground truth used by
bo_budget.py, and a small reproducible BO-vs-random check. The latency model is SYNTHETIC.
Run: python3 -m unittest scripts.experiments.test_bo_sim -v   (from the project root)
"""
import contextlib
import io
import json
import math
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
from scripts.experiments import bo_budget as B
from scripts.experiments import bo_sim as S

TUNED = dict(isolated_cores=4, irq_affinity=1, nohz_full=1, preempt_rt=1,
             governor_performance=1, numa_pinned=1, rt_priority=50, irq_coalesce_us=20)


def mean_p999(cfg, seeds=range(5), n=100_000):
    return float(np.mean([S.measure(cfg, n=n, seed=s)["p999"] for s in seeds]))


class SimulatorTests(unittest.TestCase):
    def test_deterministic_given_seed(self):
        self.assertEqual(S.measure(S.DEFAULT, seed=3), S.measure(S.DEFAULT, seed=3))

    def test_default_matches_pilot_scale(self):
        m = S.measure(S.DEFAULT, n=200_000, seed=1)
        self.assertTrue(4.0 < m["p50"] < 8.0, m)
        self.assertTrue(300 < m["p999"] < 1500, m)

    def test_tuned_beats_default_by_10x_at_p999(self):
        self.assertLess(mean_p999(TUNED) * 10, mean_p999(S.DEFAULT))

    def test_irq_steering_without_isolation_hurts(self):
        steered = dict(S.DEFAULT, irq_affinity=1)
        self.assertGreater(S.model_factors(steered)[1], S.model_factors(S.DEFAULT)[1])

    def test_nohz_needs_isolated_cores(self):
        self.assertEqual(S.model_factors(dict(S.DEFAULT, nohz_full=1)), S.model_factors(S.DEFAULT))
        iso = dict(S.DEFAULT, isolated_cores=2)
        self.assertLess(S.model_factors(dict(iso, nohz_full=1))[1], S.model_factors(iso)[1])

    def test_preempt_rt_trades_body_for_tail(self):
        b0, _, s0 = S.model_factors(S.DEFAULT)
        b1, _, s1 = S.model_factors(dict(S.DEFAULT, preempt_rt=1))
        self.assertGreater(b1, b0)
        self.assertLess(s1, s0)

    def test_over_isolation_is_penalised(self):
        ok = dict(S.DEFAULT, isolated_cores=4, irq_affinity=1)
        over = dict(ok, isolated_cores=8)
        self.assertGreater(S.model_factors(over)[1], S.model_factors(ok)[1])

    def test_space_matches_names_and_defaults_in_bounds(self):
        sp = S.space()
        self.assertEqual([d.name for d in sp], S.NAMES)
        for d in sp:
            self.assertIn(S.DEFAULT[d.name], d)


class MeasurementAndOutputTests(unittest.TestCase):
    def test_measure_default_n_is_legacy(self):
        self.assertEqual(S.measure(S.DEFAULT, seed=5), S.measure(S.DEFAULT, n=S.LEGACY_N, seed=5))

    def test_larger_n_reduces_p999_noise(self):
        small = [S.measure(TUNED, n=20_000, seed=s)["p999"] for s in range(12)]
        large = [S.measure(TUNED, n=1_000_000, seed=s)["p999"] for s in range(12)]
        self.assertLess(np.std(np.log(large)), np.std(np.log(small)))

    def test_run_search_accepts_n(self):
        trials, _, best = S.run_search(("random", 0, 5, 1000))
        self.assertEqual(len(trials), 5)
        self.assertEqual(best["p999"], min(t["p999"] for t in trials))
        self.assertEqual(S.run_search(("random", 0, 5))[2], S.run_search(("random", 0, 5, S.LEGACY_N))[2])

    def test_output_paths_legacy_and_run_dir(self):
        legacy = S.output_paths(None)
        self.assertEqual(legacy["trials"], S.ROOT / "data/bo_sim_trials.csv")
        self.assertEqual(legacy["prefix"], "bo_sim_")
        p = S.output_paths("/tmp/x")
        self.assertEqual(p["trials"], Path("/tmp/x/trials.csv"))
        self.assertEqual(p["figs"], Path("/tmp/x"))

    def test_new_run_dir_is_unique_and_stamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = S.new_run_dir("my label", base=tmp, now=0)
            b = S.new_run_dir("my label", base=tmp, now=0)
            self.assertNotEqual(a, b)
            self.assertTrue(a.is_dir() and b.is_dir())
            self.assertRegex(a.name, r"^\d{8}-\d{4}_my_label$")

    def test_main_with_out_writes_only_there(self):
        legacy = [S.ROOT / "data/bo_sim_trials.csv", S.ROOT / "data/bo_sim_results.json"]
        before = {p: p.stat().st_mtime_ns for p in legacy if p.exists()}
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                S.main(["--out", tmp, "--seeds", "1", "--evals", "11", "--n", "2000", "--workers", "2"])
            names = {p.name for p in Path(tmp).iterdir()}
            for f in ("trials.csv", "results.json", "run_config.json", "convergence.png",
                      "tail_ccdf.png", "param_importance.png"):
                self.assertIn(f, names)
            self.assertEqual(json.loads((Path(tmp) / "results.json").read_text())["samples_per_eval"], 2000)
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in legacy if p.exists()})


class GroundTruthTests(unittest.TestCase):
    def test_analytic_matches_scipy_quad(self):
        for c in (S.DEFAULT, TUNED, dict(S.DEFAULT, irq_affinity=1, rt_priority=60)):
            self.assertAlmostEqual(B.true_p999(c) / B.true_p999_quad(c), 1.0, delta=1e-5)

    def test_analytic_matches_monte_carlo(self):
        rng = np.random.default_rng(1)
        n = 4_000_000
        for c in (S.DEFAULT, TUNED):
            q = B.true_p999(c)
            f = float((S.simulate_latencies(c, n, rng) <= q).mean())
            z = (f - B.Q) / math.sqrt(B.Q * (1 - B.Q) / n)
            self.assertLess(abs(z), 4.5, (c, q, f, z))

    def test_no_stall_case_is_lognormal_quantile(self):
        from scipy.stats import norm
        q = B.quantile_from_factors(5.0, 0.0, 100.0)[0]
        self.assertAlmostEqual(q, 5.0 * math.exp(S.BODY_SIGMA * norm.ppf(B.Q)), places=6)

    def test_reduced_space_covers_rt_and_coalesce_structure(self):
        # among all rt values, only 1, 94, 99 (no isolation) are non-dominated for p99.9
        base = dict(TUNED, isolated_cores=0)
        vals = {rt: B.true_p999(dict(base, rt_priority=rt), m=1001) for rt in range(1, 100)}
        best_lo = min(vals[r] for r in range(1, 95))
        self.assertAlmostEqual(best_lo, vals[94], places=9)
        # coalescing beyond 50 us is strictly worse than 50 us
        self.assertGreater(B.true_p999(dict(TUNED, irq_coalesce_us=60)), B.true_p999(dict(TUNED, irq_coalesce_us=50)))


class BudgetHelperTests(unittest.TestCase):
    def test_a12(self):
        self.assertEqual(B.a12([1, 2], [3, 4]), 1.0)
        self.assertEqual(B.a12([3, 4], [1, 2]), 0.0)
        self.assertEqual(B.a12([1], [1]), 0.5)

    def test_checkpoint_load_skips_truncated_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            ck = Path(tmp) / "checkpoint.jsonl"
            ck.write_text(json.dumps(dict(key="10|bo|0", x=1)) + "\n" + '{"key": "10|bo|1", "x"')
            self.assertEqual(list(B.load_done(ck)), ["10|bo|0"])

    def test_run_job_records_true_regret(self):
        opt = 1.0
        r = B.run_job((10, "random", 0, 2000, opt))
        self.assertAlmostEqual(r["true_p999"], B.true_p999(r["picked_cfg"]))
        self.assertAlmostEqual(r["regret"], r["true_p999"] / opt - 1)
        self.assertEqual(len(r["trials"]), 10)


class CoefficientOverrideTests(unittest.TestCase):
    """Coefficient overrides of the SYNTHETIC model (used by bo_sensitivity.py)."""

    def test_empty_override_reproduces_base_model(self):
        from skopt.space import Space
        for x in Space(S.space()).rvs(300, random_state=4) + [list(S.DEFAULT.values()), list(TUNED.values())]:
            c = S.to_cfg(x)
            self.assertEqual(S.model_factors(c, {}), S.model_factors(c))
            self.assertEqual(S.model_factors(c, None), S.model_factors(c))
        self.assertEqual(S.measure(TUNED, n=5000, seed=2, coef={}), S.measure(TUNED, n=5000, seed=2))
        self.assertEqual(S.run_search(("random", 1, 5, 2000, {}))[2], S.run_search(("random", 1, 5, 2000))[2])

    def test_empty_override_reproduces_base_run_truth(self):
        opt = dict(isolated_cores=4, irq_affinity=1, nohz_full=1, preempt_rt=0, governor_performance=1,
                   numa_pinned=1, rt_priority=1, irq_coalesce_us=0)
        self.assertEqual(B.true_p999(opt, coef={}), B.true_p999(opt))
        self.assertAlmostEqual(B.true_p999(opt, coef={}), 10.29096879303496, places=9)
        self.assertAlmostEqual(B.true_p999(S.DEFAULT, coef={}), 766.6673934436056, places=7)

    def test_unknown_coefficient_rejected(self):
        with self.assertRaises(KeyError):
            S.model_factors(S.DEFAULT, {"no_such_coef": 1.0})

    def test_override_changes_model(self):
        self.assertGreater(S.model_factors(S.DEFAULT, {"base_event_p": 0.008})[1], S.model_factors(S.DEFAULT)[1])
        # DEFAULT's p99.9 lies in the stall tail (p > 1e-3), so a heavier tail must raise it
        self.assertGreater(B.true_p999(S.DEFAULT, coef={"alpha": 0.8}), B.true_p999(S.DEFAULT))
        self.assertGreater(B.true_p999(TUNED, coef={"body_sigma": 0.5}), B.true_p999(TUNED))


class SensitivitySweepTests(unittest.TestCase):
    """Bookkeeping of the SYNTHETIC-model sensitivity sweep (bo_sensitivity.py)."""

    @classmethod
    def setUpClass(cls):
        from scripts.experiments import bo_sensitivity as X
        cls.X = X

    def test_perturbation_kinds_and_clamps(self):
        X = self.X
        for name in X.FACTOR_KIND:
            base = S.COEF_DEFAULTS[name]
            for f in (0.5, 2.0):
                v = X.perturbed_coef({name: f})[name]
                self.assertGreater(v, 0)
                self.assertEqual(v > 1, base > 1, (name, f, v))      # effect keeps its direction
        self.assertAlmostEqual(X.perturbed_coef({"rt_scale": 2.0})["rt_scale"], 0.45 ** 2)
        self.assertAlmostEqual(X.perturbed_coef({"base_stall_us": 0.5})["base_stall_us"], 160.0)
        self.assertEqual(X.perturbed_coef({"base_event_p": 1000})["base_event_p"], 0.5)
        self.assertEqual(X.perturbed_coef({"coalesce_gain": 10})["coalesce_gain"], 0.95)
        self.assertEqual(X.perturbed_coef({"iso_cap": 0.75})["iso_cap"], 3)
        self.assertIsInstance(X.perturbed_coef({"iso_cap": 1.37})["iso_cap"], int)
        with self.assertRaises(KeyError):
            X.perturbed_coef({"rt_high_min": 2.0})                   # structural threshold: fixed

    def test_design_ids_and_order(self):
        X = self.X
        ms = X.design(16)
        ids = [m["model_id"] for m in ms]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ms), 1 + 4 * len(X.PERTURBED) + 16)
        self.assertEqual(ms[0]["coef"], {})
        self.assertEqual([m["kind"] for m in ms[1:1 + 4 * len(X.PERTURBED)]], ["oat"] * (4 * len(X.PERTURBED)))
        self.assertEqual(ms[1]["level"], 0.5)                        # extremes first
        g = [m for m in ms if m["kind"] == "global"]
        self.assertTrue(all(0.5 <= f <= 2.0 for m in g for f in m["mult"].values()))
        self.assertEqual(X.design(16)[-1]["mult"], ms[-1]["mult"])   # deterministic

    def test_job_keys_and_resume_skip(self):
        X = self.X
        keys = X.job_keys("oat|alpha|x2", 30)
        self.assertEqual(len(keys), 1 + 30 + len(B.BUDGETS) * 30)
        self.assertEqual(len(set(keys)), len(keys))
        ms = X.design(0)[:2]
        with tempfile.TemporaryDirectory() as tmp:
            sd = Path(tmp)
            done = {k: {} for k in X.job_keys(ms[0]["model_id"], 3)}
            done.pop("base#bo#1")
            (sd / X.state_name(f"{ms[1]['model_id']}#bo#2")).write_bytes(b"x")
            work = X.pending_work(ms, done, sd, 3)
            self.assertEqual(work[0], ("bo", 1, 2))                  # chain in progress first
            self.assertEqual(work[1], ("bo", 0, 1))                  # then the unfinished model
            self.assertEqual(len(work), 1 + len(X.job_keys("m", 3)))

    def test_factors_grid_matches_scalar_model(self):
        X = self.X
        rng = np.random.default_rng(0)
        for m in X.design(4)[::23]:
            grid = X.factors_grid(m["coef"])
            for i in rng.integers(0, grid[0].size, 200):
                c = X.grid_cfg(i)
                for a, g in zip(S.model_factors(c, m["coef"]), grid):
                    self.assertAlmostEqual(a / g.ravel()[i], 1.0, delta=1e-13)

    def test_sobol_indices_of_additive_function(self):
        a = np.arange(3.0)[:, None] + 2 * np.array([0.0, 1.0])[None, :]
        Y = np.broadcast_to(a.reshape(3, 2, 1, 1, 1, 1, 1, 1), (3, 2, 1, 1, 1, 1, 1, 1))
        s1, st = self.X.sobol_indices(np.asarray(Y, float))
        self.assertAlmostEqual(sum(s1.values()), 1.0)
        for k in s1:
            self.assertAlmostEqual(s1[k], st[k])

    def test_bo_chain_split_equals_unsplit(self):
        X = self.X
        import time as _t
        with tempfile.TemporaryDirectory() as tmp:
            whole = X.bo_chain(("base", {}, 2, 2000, _t.time() + 600, str(Path(tmp) / "a.pkl"), 13))
            r, segs = ("partial",), 0
            # bo_chain keeps a 2 s safety margin before its deadline: 2.3 s still allows the first step of every segment
            while r[0] == "partial":
                r = X.bo_chain(("base", {}, 2, 2000, _t.time() + 2.3, str(Path(tmp) / "b.pkl"), 13))
                segs += 1
                self.assertLess(segs, 200, "chain makes no progress between segments")
            self.assertEqual(whole[0], "final")
            self.assertEqual(r[1]["trials"], whole[1]["trials"])
            self.assertGreater(segs, 1)
            # the chain is gp_minimize: same trials as bo_sim.run_search
            trials, _, _ = S.run_search(("bo", 2, 13, 2000))
            self.assertEqual(whole[1]["trials"], [[t[k] for k in S.NAMES] + [t["p999"]] for t in trials])


class SearchTests(unittest.TestCase):
    def test_bo_not_worse_than_random_on_fixed_seeds(self):
        res = {}
        for m in ("bo", "random"):
            vals = []
            for seed in range(4):
                _, _, best = S.run_search((m, seed, 25))
                vals.append(S.reevaluate({k: best[k] for k in S.NAMES}, reps=5, n=100_000)[0])
            res[m] = float(np.median(vals))
        self.assertLessEqual(res["bo"], res["random"] * 1.25, res)
        self.assertLess(res["bo"], S.reevaluate(S.DEFAULT, reps=5, n=100_000)[0] / 3, res)


if __name__ == "__main__":
    unittest.main()
