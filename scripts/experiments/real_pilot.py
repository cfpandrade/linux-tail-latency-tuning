"""Real-measurement pilot on the local workstation (Intel i7-8700, 6C/12T, 1 NUMA node, generic kernel).

Unlike bo_sim.py, every evaluation here is a REAL measurement: cyclictest wakes a thread every 200 us
on the chosen CPU while stress-ng loads the machine, and we read the wake-up latency histogram.

Tunable knobs (all applicable without root, given RLIMIT_RTPRIO=99 on the launching process):
  policy        0 = SCHED_OTHER, 1 = SCHED_FIFO
  rt_priority   1..99 (only used with SCHED_FIFO)
  cpu           -1 = not pinned, else the CPU the measured thread is pinned to (0..11)
  isolate       1 = keep the background load off the measured CPU (user-space isolation via affinity)
  sibling_free  1 = also keep the load off the SMT sibling of the measured CPU
Out of scope here (future work): isolcpus/nohz_full, PREEMPT_RT, IRQ affinity, C-state control, AWS/PHC.

Phases (all checkpointed to <out>/evals.jsonl, safe to resume with the same --out):
  A  baseline   untuned default, repeated
  B  search     BO (GP, EI) and random search, interleaved evaluation by evaluation, several seeds
  C  reeval     default and every method's pick, repeated, in shuffled order
  D  factorial  2^3 x 2 cpus design (policy, isolate, sibling_free, cpu in {0, 5}) for clean effect estimates

Run:  python3 scripts/experiments/real_pilot.py --out data/real_pilot/run1 [--duration 30 --seeds 5 --evals 30]
"""
import argparse
import json
import os
import random
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
NCPU = os.cpu_count() or 12
NAMES = ["policy", "rt_priority", "cpu", "isolate", "sibling_free"]
DEFAULT = dict(policy=0, rt_priority=1, cpu=-1, isolate=0, sibling_free=0)
INTERVAL_US = 200
HIST_MAX_US = 20000


def siblings(cpu):
    txt = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list").read_text().strip()
    out = set()
    for part in txt.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def normalise(c):
    c = {k: int(c[k]) for k in NAMES}
    if c["policy"] == 0:
        c["rt_priority"] = 1          # irrelevant without SCHED_FIFO
    if c["cpu"] < 0:
        c["isolate"] = 0              # cannot keep load off an unpinned thread
        c["sibling_free"] = 0
    if not c["isolate"]:
        c["sibling_free"] = 0
    return c


def load_cpus(c):
    cpus = set(range(NCPU))
    if c["cpu"] >= 0 and c["isolate"]:
        cpus.discard(c["cpu"])
        if c["sibling_free"]:
            cpus -= siblings(c["cpu"])
    return sorted(cpus)


def commands(c, duration, histfile):
    c = normalise(c)
    lc = load_cpus(c)
    stress = ["taskset", "-c", ",".join(map(str, lc)), "stress-ng", "--cpu", str(len(lc)),
              "--cpu-method", "matrixprod", "--vm", "2", "--vm-bytes", "256M",
              "--timeout", f"{duration + 6}s", "--quiet"]
    cyc = ["cyclictest", "-q", "-D", str(duration), "-t", "1", "-i", str(INTERVAL_US),
           "-h", str(HIST_MAX_US), f"--histfile={histfile}"]
    if c["cpu"] >= 0:
        cyc += ["-a", str(c["cpu"])]
    if c["policy"] == 1:
        cyc += ["-p", str(c["rt_priority"])]
    return stress, cyc


def parse_hist(path):
    bins, overflow = {}, 0
    for line in Path(path).read_text().splitlines():
        if line.startswith("# Histogram Overflows:"):
            overflow = int(line.split(":")[1].split()[0])
        elif line and not line.startswith("#"):
            us, n = line.split()[:2]
            if int(n):
                bins[int(us)] = int(n)
    return bins, overflow


def percentiles(bins, overflow, qs=(50, 99, 99.9, 99.99)):
    """Percentiles from a 1 us histogram; overflowed samples count as HIST_MAX_US (right-censored)."""
    keys = sorted(bins)
    counts = np.array([bins[k] for k in keys] + [overflow], dtype=float)
    vals = np.array(keys + [HIST_MAX_US], dtype=float)
    cum = np.cumsum(counts)
    n = cum[-1]
    out = {}
    for q in qs:
        rank = np.ceil(q * n / 100 - 1e-9)  # nearest-rank, robust to float error (99.9/100*1000 > 999)
        idx = int(np.searchsorted(cum, rank, side="left"))
        out[f"p{q:g}".replace(".", "")] = float(vals[min(idx, len(vals) - 1)])
    out["max"] = float(vals[counts > 0][-1]) if n else float("nan")
    out["n"] = int(n)
    out["overflow"] = int(overflow)
    return out


def irq_counts():
    """Per-CPU interrupt totals and local-timer (LOC) counts from /proc/interrupts (no root needed)."""
    lines = Path("/proc/interrupts").read_text().splitlines()
    ncols = len(lines[0].split())
    total, loc = np.zeros(ncols, dtype=np.int64), np.zeros(ncols, dtype=np.int64)
    for line in lines[1:]:
        name, _, rest = line.partition(":")
        vals = rest.split()[:ncols]
        if len(vals) < ncols or not all(v.isdigit() for v in vals):
            continue
        v = np.array([int(x) for x in vals], dtype=np.int64)
        total += v
        if name.strip() == "LOC":
            loc += v
    return total, loc


def measure(c, duration):
    c = normalise(c)
    with tempfile.TemporaryDirectory() as td:
        hf = os.path.join(td, "hist.txt")
        stress, cyc = commands(c, duration, hf)
        load0 = os.getloadavg()[0]
        sp = subprocess.Popen(stress, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            time.sleep(2)  # let the load ramp up
            irq0, loc0, t_irq = *irq_counts(), time.time()
            r = subprocess.run(cyc, capture_output=True, text=True, timeout=duration + 30)
            irq1, loc1 = irq_counts()
            dt = time.time() - t_irq
        finally:
            try:
                os.killpg(sp.pid, 15)
            except ProcessLookupError:
                pass
            sp.wait(timeout=20)
        if r.returncode != 0 or not os.path.exists(hf):
            raise RuntimeError(f"cyclictest failed rc={r.returncode}: {r.stderr[-500:]}")
        bins, overflow = parse_hist(hf)
    cpu = c["cpu"] if c["cpu"] >= 0 else None
    irq_rate = ((irq1 - irq0) / dt).tolist()
    loc_rate = ((loc1 - loc0) / dt).tolist()
    return dict(**percentiles(bins, overflow), loadavg_before=load0, hist=bins,
                irq_rate_per_cpu=irq_rate, loc_rate_per_cpu=loc_rate,
                irq_rate_measured_cpu=irq_rate[cpu] if cpu is not None else None,
                loc_rate_measured_cpu=loc_rate[cpu] if cpu is not None else None)


# ------------------------------------------------------------------ orchestration
class Store:
    def __init__(self, out):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.file = self.out / "evals.jsonl"
        self.done = {}
        if self.file.exists():
            for line in self.file.read_text().splitlines():
                try:
                    r = json.loads(line)
                    self.done[r["key"]] = r
                except (json.JSONDecodeError, KeyError):
                    pass

    def get_or_run(self, key, cfg, duration, meta=None):
        if key in self.done:
            return self.done[key]
        m = measure(cfg, duration)
        rec = dict(key=key, ts=time.strftime("%Y-%m-%dT%H:%M:%S"), cfg=normalise(cfg), duration=duration,
                   **(meta or {}), **m)
        with open(self.file, "a") as f:
            f.write(json.dumps(rec) + "\n")
        self.done[key] = rec
        p = {k: rec[k] for k in ("p50", "p99", "p999", "max")}
        print(f"[{rec['ts']}] {key} {rec['cfg']} -> {p}", flush=True)
        return rec


def space():
    from skopt.space import Categorical, Integer
    return [Categorical([0, 1], name="policy"), Integer(1, 99, name="rt_priority"),
            Integer(-1, NCPU - 1, name="cpu"), Categorical([0, 1], name="isolate"),
            Categorical([0, 1], name="sibling_free")]


def to_cfg(x):
    return normalise(dict(zip(NAMES, (int(v) for v in x))))


def objective_value(rec):
    return float(np.log10(max(rec["p999"], 1.0)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=int, default=30, help="seconds per measurement")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--evals", type=int, default=30)
    ap.add_argument("--baseline-reps", type=int, default=10)
    ap.add_argument("--reeval-reps", type=int, default=5)
    ap.add_argument("--factorial-reps", type=int, default=3)
    a = ap.parse_args()
    st = Store(ROOT / a.out if not os.path.isabs(a.out) else a.out)
    (st.out / "run_config.json").write_text(json.dumps(dict(vars(a), ncpu=NCPU, interval_us=INTERVAL_US,
                                                            hist_max_us=HIST_MAX_US, default=DEFAULT), indent=2))
    D = a.duration
    t0 = time.time()

    # A baseline
    for r in range(a.baseline_reps):
        st.get_or_run(f"A#default#{r}", DEFAULT, D, dict(phase="A"))

    # B search: BO and random interleaved per seed
    from skopt import Optimizer
    from skopt.space import Space
    picks = {}
    for seed in range(a.seeds):
        opt = Optimizer(space(), base_estimator="GP", acq_func="EI", n_initial_points=8, random_state=seed)
        rnd = Space(space()).rvs(a.evals, random_state=1000 + seed)
        hist = {"bo": [], "random": []}
        for i in range(a.evals):
            x = opt.ask()
            rec = st.get_or_run(f"B#bo#{seed}#{i}", to_cfg(x), D, dict(phase="B", method="bo", seed=seed, i=i))
            opt.tell(x, objective_value(rec))
            hist["bo"].append(rec)
            rec = st.get_or_run(f"B#random#{seed}#{i}", to_cfg(rnd[i]), D, dict(phase="B", method="random", seed=seed, i=i))
            hist["random"].append(rec)
        for m, recs in hist.items():
            picks[f"{m}#{seed}"] = min(recs, key=lambda r: r["p999"])["cfg"]
    (st.out / "picks.json").write_text(json.dumps(picks, indent=2))

    # C re-evaluation, shuffled
    jobs = [(f"C#default#{r}", DEFAULT, dict(phase="C", target="default")) for r in range(a.reeval_reps)]
    for name, cfg in picks.items():
        jobs += [(f"C#{name}#{r}", cfg, dict(phase="C", target=name)) for r in range(a.reeval_reps)]
    random.Random(7).shuffle(jobs)
    for key, cfg, meta in jobs:
        st.get_or_run(key, cfg, D, meta)

    # D factorial, shuffled
    jobs = []
    for pol in (0, 1):
        for iso in (0, 1):
            for sib in (0, 1):
                if sib and not iso:
                    continue
                for cpu in (0, 5):
                    cfg = dict(policy=pol, rt_priority=80, cpu=cpu, isolate=iso, sibling_free=sib)
                    for r in range(a.factorial_reps):
                        jobs.append((f"D#{pol}{iso}{sib}c{cpu}#{r}", cfg, dict(phase="D")))
    random.Random(11).shuffle(jobs)
    for key, cfg, meta in jobs:
        st.get_or_run(key, cfg, D, meta)

    print(f"DONE in {(time.time() - t0) / 3600:.2f} h, {len(st.done)} evaluations", flush=True)


if __name__ == "__main__":
    main()
