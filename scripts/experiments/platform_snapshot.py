"""Record the measurement platform described in Section 4.2 from the running system.

Writes <out>/platform.json with the kernel, distribution, CPU, memory, NUMA, boot parameters,
preemption model, idle states and their exit latencies, SMT topology, irqbalance state, and tool
versions, so that every platform statement in the dissertation can be checked against a file in
the repository rather than against the author's recollection.

Run on the measurement host:  python3 scripts/experiments/platform_snapshot.py --out data/real_pilot/run1
"""
import argparse
import glob
import json
import os
import re
import resource
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def rd(p):
    try:
        return open(p).read().strip()
    except OSError as e:
        return f"<unavailable: {e.strerror}>"


def tool_version(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return (r.stdout + r.stderr).splitlines()[0][:120]
    except Exception as e:  # noqa: BLE001
        return f"<unavailable: {e}>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/real_pilot/run1")
    a = ap.parse_args()
    u = os.uname()
    cpuinfo = rd("/proc/cpuinfo")
    out = {
        "captured": datetime.now().isoformat(timespec="seconds"),
        "hostname": u.nodename,
        "kernel": f"{u.sysname} {u.release} {u.version}",
        "distribution": next((l.split("=", 1)[1].strip('"') for l in rd("/etc/os-release").splitlines()
                              if l.startswith("PRETTY_NAME=")), None),
        "cmdline": rd("/proc/cmdline"),
        "cpu_model": (re.search(r"model name\s*:\s*(.*)", cpuinfo) or [None, None])[1],
        "logical_cpus": os.cpu_count(),
        "physical_cores": len(set(re.findall(r"core id\s*:\s*(\d+)", cpuinfo))),
        "mem_total_kB": int(re.search(r"MemTotal:\s*(\d+)", rd("/proc/meminfo")).group(1)),
        "numa_nodes": sorted(os.path.basename(p) for p in glob.glob("/sys/devices/system/node/node*")),
        "isolated_cpus": rd("/sys/devices/system/cpu/isolated"),
        "nohz_full_cpus": rd("/sys/devices/system/cpu/nohz_full"),
        "cpufreq_scaling_driver": rd("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver"),
        "cpuidle_driver": rd("/sys/devices/system/cpu/cpuidle/current_driver"),
        "cpuidle_states_cpu5": [{"name": rd(f"{s}/name"), "exit_latency_us": int(rd(f"{s}/latency")),
                                 "disabled": rd(f"{s}/disable")}
                                for s in sorted(glob.glob("/sys/devices/system/cpu/cpu5/cpuidle/state*"),
                                                key=lambda p: int(p.rsplit("state", 1)[1]))],
        "smt_siblings": {f"cpu{i}": rd(f"/sys/devices/system/cpu/cpu{i}/topology/thread_siblings_list")
                         for i in range(os.cpu_count() or 0)},
        "irqbalance_running": any(rd(f"/proc/{p}/comm") == "irqbalance" for p in os.listdir("/proc") if p.isdigit()),
        "sched_rt_runtime_us": rd("/proc/sys/kernel/sched_rt_runtime_us"),
        "rlimit_rtprio_in_this_shell": resource.getrlimit(resource.RLIMIT_RTPRIO),
        "tools": {"cyclictest": tool_version(["cyclictest", "--help"]),
                  "stress-ng": tool_version(["stress-ng", "--version"]),
                  "python3": tool_version(["python3", "--version"])},
    }
    cfg = Path(f"/boot/config-{u.release}")
    if cfg.exists():
        c = cfg.read_text()
        out["kernel_config"] = {k: bool(re.search(rf"^{k}=y", c, re.M)) for k in
                                ("CONFIG_PREEMPT_DYNAMIC", "CONFIG_PREEMPT_RT", "CONFIG_PREEMPT",
                                 "CONFIG_PREEMPT_VOLUNTARY", "CONFIG_NO_HZ_FULL")}
        m = re.search(r"^CONFIG_HZ=(\d+)", c, re.M)
        out["kernel_config"]["CONFIG_HZ"] = int(m.group(1)) if m else None
    try:
        import numpy, scipy, sklearn, skopt  # noqa: E401
        out["python_packages"] = {"numpy": numpy.__version__, "scipy": scipy.__version__,
                                  "scikit-learn": sklearn.__version__, "scikit-optimize": skopt.__version__}
    except ImportError as e:
        out["python_packages"] = f"<unavailable: {e}>"
    dest = ROOT / a.out / "platform.json"
    dest.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
