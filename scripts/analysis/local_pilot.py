"""Local feasibility pilot for tick-to-trade tail-latency tuning.

Synthetic single-process tick-to-trade loop under a Poisson arrival process,
measuring end-to-end latency (nanoseconds) for a gradient of configurations
applicable locally without reconfiguring the kernel:

  L0  baseline: default affinity, default scheduler
  L1  CPU affinity pinned to one core (os.sched_setaffinity)
  L2  L1 + SCHED_FIFO real-time policy (requires privilege; skipped if denied)

The offered rate is calibrated from the measured service time so that the
pipeline runs at a target utilisation well below saturation; otherwise queueing
backlog, not scheduler jitter, dominates the tail.

Outputs:
  data/local_pilot_latencies.csv       raw per-sample latency
  data/local_pilot_summary.csv          percentiles per config
  figures/local_pilot_percentiles.png   p50/p95/p99/p99.9 chart (microseconds, log y)

Trend/direction pilot: it transfers the ordering of interventions, not the
absolute magnitude of an AWS c7i.metal run with PHC/ENA timestamping.
"""
import csv
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.common import DATA_DIR, FIGURES_DIR  # noqa: E402

N_SAMPLES = 120_000
WARMUP = 5_000
WORK_ITERS = 60
TARGET_UTIL = 0.35        # offered load as a fraction of service capacity
SEED = 20261013


def strategy_work(iters):
    acc = 0.0
    for i in range(iters):
        acc += (i * 1.0000001) ** 0.5
    return acc


def calibrate_service_ns(trials=20_000):
    """Median service time of one strategy evaluation, in nanoseconds."""
    perf = time.perf_counter_ns
    samples = np.empty(trials, dtype=np.int64)
    for k in range(trials):
        t0 = perf()
        strategy_work(WORK_ITERS)
        samples[k] = perf() - t0
    return float(np.median(samples))


def run_once(n_samples, interval_ns, rng):
    latencies = np.empty(n_samples, dtype=np.int64)
    perf = time.perf_counter_ns
    target = perf()
    sink = 0.0
    for k in range(n_samples):
        target += int(rng.exponential(interval_ns))
        now = perf()
        while now < target:
            now = perf()
        sink += strategy_work(WORK_ITERS)
        latencies[k] = perf() - target
    if sink == float("inf"):
        print("unreachable")
    return latencies


def try_pin_affinity():
    try:
        os.sched_setaffinity(0, {max(os.cpu_count() - 1, 0)})
        return True
    except (AttributeError, OSError, PermissionError):
        return False


def try_fifo():
    try:
        param = os.sched_param(os.sched_get_priority_max(os.SCHED_FIFO))
        os.sched_setscheduler(0, os.SCHED_FIFO, param)
        return True
    except (AttributeError, OSError, PermissionError):
        return False


def percentiles(latencies):
    return {p: float(np.percentile(latencies, p)) for p in (50, 95, 99, 99.9)}


def main():
    rng = np.random.default_rng(SEED)
    DATA_DIR.mkdir(exist_ok=True)
    FIGURES_DIR.mkdir(exist_ok=True)

    service_ns = calibrate_service_ns()
    interval_ns = service_ns / TARGET_UTIL
    rate_hz = 1e9 / interval_ns
    print(
        f"calibration: service={service_ns/1000:.2f} us/msg  "
        f"util={TARGET_UTIL}  offered_rate={rate_hz:,.0f} Hz"
    )

    configs = []

    lat = run_once(N_SAMPLES, interval_ns, rng)[WARMUP:]
    configs.append(("L0_baseline", lat))

    pinned = try_pin_affinity()
    lat = run_once(N_SAMPLES, interval_ns, rng)[WARMUP:]
    configs.append(("L1_affinity" if pinned else "L1_affinity_unavailable", lat))

    fifo = try_fifo()
    lat = run_once(N_SAMPLES, interval_ns, rng)[WARMUP:]
    configs.append(("L2_fifo" if fifo else "L2_fifo_unavailable", lat))

    with (DATA_DIR / "local_pilot_latencies.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "latency_ns"])
        for name, lat in configs:
            for v in lat:
                w.writerow([name, int(v)])

    rows = []
    with (DATA_DIR / "local_pilot_summary.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "p50_ns", "p95_ns", "p99_ns", "p999_ns", "n"])
        for name, lat in configs:
            pc = percentiles(lat)
            w.writerow([name, pc[50], pc[95], pc[99], pc[99.9], len(lat)])
            rows.append((name, pc))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        labels = [r[0] for r in rows]
        x = np.arange(len(labels))
        width = 0.2
        for i, p in enumerate([50, 95, 99, 99.9]):
            vals = [r[1][p] / 1000.0 for r in rows]
            plt.bar(x + (i - 1.5) * width, vals, width, label=f"p{p}")
        plt.yscale("log")
        plt.xticks(x, labels, rotation=20, ha="right")
        plt.ylabel("Latency (microseconds, log scale)")
        plt.title("Local pilot: tick-to-trade latency percentiles")
        plt.legend()
        plt.tight_layout()
        plt.savefig(FIGURES_DIR / "local_pilot_percentiles.png", dpi=130)
        print(f"figure: {FIGURES_DIR / 'local_pilot_percentiles.png'}")
    except Exception as e:
        print(f"figure skipped: {e}")

    print(f"samples/config={N_SAMPLES - WARMUP}")
    for name, pc in rows:
        print(
            f"{name:28s} p50={pc[50]/1000:7.2f}  p95={pc[95]/1000:7.2f}  "
            f"p99={pc[99]/1000:7.2f}  p99.9={pc[99.9]/1000:8.2f}  (microseconds)"
        )


if __name__ == "__main__":
    main()
