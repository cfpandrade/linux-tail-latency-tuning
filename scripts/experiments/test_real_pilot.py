"""Tests for the real-measurement pilot.
Run: .venv/bin/python -m unittest scripts.experiments.test_real_pilot -v   (from the project root)
The smoke test runs two 3 s measurements on this machine (needs cyclictest, stress-ng and RLIMIT_RTPRIO>0).
"""
import os
import resource
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.experiments import real_pilot as R


class PureTests(unittest.TestCase):
    def test_normalise_drops_irrelevant_knobs(self):
        self.assertEqual(R.normalise(dict(policy=0, rt_priority=77, cpu=-1, isolate=1, sibling_free=1)), R.DEFAULT)
        c = R.normalise(dict(policy=1, rt_priority=77, cpu=3, isolate=0, sibling_free=1))
        self.assertEqual((c["rt_priority"], c["sibling_free"]), (77, 0))

    def test_load_cpus(self):
        all_cpus = list(range(R.NCPU))
        self.assertEqual(R.load_cpus(R.normalise(dict(policy=1, rt_priority=80, cpu=3, isolate=0, sibling_free=0))), all_cpus)
        iso = R.load_cpus(R.normalise(dict(policy=1, rt_priority=80, cpu=3, isolate=1, sibling_free=0)))
        self.assertNotIn(3, iso)
        self.assertEqual(len(iso), R.NCPU - 1)
        sib = R.load_cpus(R.normalise(dict(policy=1, rt_priority=80, cpu=3, isolate=1, sibling_free=1)))
        self.assertTrue(R.siblings(3).isdisjoint(sib))
        self.assertEqual(len(sib), R.NCPU - len(R.siblings(3)))

    def test_commands(self):
        stress, cyc = R.commands(dict(policy=1, rt_priority=80, cpu=3, isolate=1, sibling_free=0), 10, "/tmp/h")
        self.assertIn("-p", cyc)
        self.assertEqual(cyc[cyc.index("-p") + 1], "80")
        self.assertEqual(cyc[cyc.index("-a") + 1], "3")
        self.assertNotIn("3", stress[2].split(","))
        # Parameters the methodology chapter relies on: 200 us interval, 20 ms histogram, duration,
        # one matrix-multiplication worker per permitted CPU, two 256 MiB memory workers.
        self.assertEqual(cyc[cyc.index("-i") + 1], "200")
        self.assertEqual(cyc[cyc.index("-h") + 1], "20000")
        self.assertEqual(cyc[cyc.index("-D") + 1], "10")
        self.assertEqual(cyc[cyc.index("-t") + 1], "1")
        self.assertEqual(stress[stress.index("--cpu") + 1], str(len(stress[2].split(","))))
        self.assertEqual(stress[stress.index("--cpu-method") + 1], "matrixprod")
        self.assertEqual(stress[stress.index("--vm") + 1], "2")
        self.assertEqual(stress[stress.index("--vm-bytes") + 1], "256M")
        _, cyc0 = R.commands(R.DEFAULT, 10, "/tmp/h")
        self.assertNotIn("-p", cyc0)
        self.assertNotIn("-a", cyc0)

    def test_percentiles_from_histogram(self):
        bins = {10: 990, 50: 9, 300: 1}
        p = R.percentiles(bins, 0)
        self.assertEqual((p["p50"], p["p99"], p["p999"], p["max"], p["n"]), (10, 10, 50, 300, 1000))
        p = R.percentiles({10: 998}, 2)  # overflow is right-censored at HIST_MAX_US
        self.assertEqual(p["p999"], R.HIST_MAX_US)
        self.assertEqual(p["overflow"], 2)
        # Floating-point rank guard: 99.9 * 41000 / 100 evaluates to 40959.00000000001, so an unguarded
        # ceil() gives rank 40960 and selects the next bin (300) instead of the correct one (10).
        p = R.percentiles({10: 40959, 300: 41}, 0)
        self.assertEqual(p["p999"], 10)

    def test_parse_hist(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("# header\n000000 000000\n000003 000005\n000004 000001\n# Histogram Overflows: 00002\n")
        try:
            self.assertEqual(R.parse_hist(f.name), ({3: 5, 4: 1}, 2))
        finally:
            os.unlink(f.name)

    def test_space_matches_names(self):
        self.assertEqual([d.name for d in R.space()], R.NAMES)


@unittest.skipUnless(shutil.which("cyclictest") and shutil.which("stress-ng"), "tools missing")
class SmokeTests(unittest.TestCase):
    def test_real_measurements(self):
        self.assertGreater(resource.getrlimit(resource.RLIMIT_RTPRIO)[0], 0, "RLIMIT_RTPRIO must be raised")
        fifo = R.measure(dict(policy=1, rt_priority=80, cpu=5, isolate=1, sibling_free=1), 3)
        other = R.measure(R.DEFAULT, 3)
        for m in (fifo, other):
            self.assertGreater(m["n"], 10000)
            self.assertTrue(0 < m["p50"] <= m["p99"] <= m["p999"] <= m["max"])
        os.system("pgrep -x stress-ng >/dev/null && echo 'stress-ng still running' >&2")
        self.assertEqual(os.system("pgrep -x stress-ng >/dev/null"), 256, "stress-ng must be cleaned up")

    def test_store_resumes(self):
        with tempfile.TemporaryDirectory() as td:
            st = R.Store(td)
            a = st.get_or_run("k1", R.DEFAULT, 2)
            st2 = R.Store(td)
            self.assertEqual(st2.get_or_run("k1", R.DEFAULT, 2)["ts"], a["ts"])
            self.assertEqual(len(Path(td, "evals.jsonl").read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
