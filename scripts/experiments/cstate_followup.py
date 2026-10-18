"""Follow-up to real_pilot.py: does an isolated core lose latency because it falls into deep C-states?

Without root, cyclictest cannot hold /dev/cpu_dma_latency at 0, so an idle isolated core is free to enter
C-states with exit latencies of up to hundreds of microseconds. This script measures the same
configurations with and without a SCHED_IDLE busy-loop ("keep-awake spinner") on the measured CPU. The
spinner keeps the core in C0 but yields at once to any other runnable task, so it removes idle states
without adding competing work. It also records how often the measured CPU entered each cpuidle state.

A second question is why SCHED_OTHER has a median wake-up latency of about 56 us even on an idle core.
Linux applies a default timer slack of 50 us to SCHED_OTHER tasks (zero for real-time tasks), so the
"slack" variants run cyclictest with its timer slack reduced to 1 ns through prctl(PR_SET_TIMERSLACK).

Run:  python3 scripts/experiments/cstate_followup.py --out data/real_pilot/cstate1 [--duration 30 --reps 5]
"""
import argparse
import json
import os
import random
import subprocess
import time
from pathlib import Path

import real_pilot as rp

CPU = 5
PR_SET_TIMERSLACK = 29
SLACK_WRAPPER = ["python3", "-I", "-c",
                 "import ctypes, os, sys; ctypes.CDLL(None).prctl(%d, 1, 0, 0, 0); os.execvp(sys.argv[1], sys.argv[1:])"
                 % PR_SET_TIMERSLACK]


def idle_usage(cpu):
    base = Path(f"/sys/devices/system/cpu/cpu{cpu}/cpuidle")
    out = {}
    for d in sorted(base.glob("state*")):
        name = (d / "name").read_text().strip()
        out[name] = dict(usage=int((d / "usage").read_text()), time_us=int((d / "time").read_text()))
    return out


def spinner_cmd(cpu, duration):
    return ["taskset", "-c", str(cpu), "stress-ng", "--cpu", "1", "--cpu-method", "int64",
            "--sched", "idle", "--timeout", f"{duration + 10}s", "--quiet"]


def measure(cfg, spin, duration, slack=False):
    orig = rp.commands
    if slack:
        def commands(c, d, hf):
            stress, cyc = orig(c, d, hf)
            return stress, SLACK_WRAPPER + cyc
        rp.commands = commands
    sp = None
    if spin:
        sp = subprocess.Popen(spinner_cmd(cfg["cpu"], duration), stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, start_new_session=True)
        time.sleep(0.5)
    try:
        u0 = idle_usage(cfg["cpu"])
        m = rp.measure(cfg, duration)
        u1 = idle_usage(cfg["cpu"])
    finally:
        if sp is not None:
            try:
                os.killpg(sp.pid, 15)
            except ProcessLookupError:
                pass
            sp.wait(timeout=20)
        rp.commands = orig
    m["cpuidle_delta"] = {k: dict(usage=u1[k]["usage"] - u0[k]["usage"],
                                  time_us=u1[k]["time_us"] - u0[k]["time_us"]) for k in u0}
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    out = Path(a.out if os.path.isabs(a.out) else rp.ROOT / a.out)
    out.mkdir(parents=True, exist_ok=True)
    f = out / "evals.jsonl"
    done = set()
    if f.exists():
        done = {json.loads(l)["key"] for l in f.read_text().splitlines() if l.strip()}
    cfgs = {
        "fifo_shared": dict(policy=1, rt_priority=80, cpu=CPU, isolate=0, sibling_free=0),
        "fifo_isolated": dict(policy=1, rt_priority=80, cpu=CPU, isolate=1, sibling_free=1),
        "other_isolated": dict(policy=0, rt_priority=1, cpu=CPU, isolate=1, sibling_free=1),
        "other_isolated_slack": dict(policy=0, rt_priority=1, cpu=CPU, isolate=1, sibling_free=1),
    }
    jobs = [(f"{name}#spin{spin}#{r}", name, cfg, spin)
            for name, cfg in cfgs.items() for spin in (0, 1) for r in range(a.reps)
            if not (spin and name == "fifo_shared")]
    random.Random(3).shuffle(jobs)
    for key, name, cfg, spin in jobs:
        if key in done:
            continue
        slack = name.endswith("_slack")
        m = measure(rp.normalise(cfg), spin, a.duration, slack)
        rec = dict(key=key, ts=time.strftime("%Y-%m-%dT%H:%M:%S"), config=name, spinner=spin, timerslack_1ns=slack,
                   cfg=rp.normalise(cfg), duration=a.duration, **m)
        with open(f, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(f"[{rec['ts']}] {key} -> p50 {m['p50']} p99 {m['p99']} p999 {m['p999']} max {m['max']}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
