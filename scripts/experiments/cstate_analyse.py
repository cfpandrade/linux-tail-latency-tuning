"""Analyse the C-state follow-up (cstate_followup.py): percentiles and idle-state entries per condition.

Run:  python3 scripts/experiments/cstate_analyse.py --run data/real_pilot/cstate1
"""
import argparse
import json
from pathlib import Path

import numpy as np

import real_pilot_analyse as rpa

LABELS = {
    ("fifo_shared", 0): "FIFO 80, CPU 5 shared with load",
    ("fifo_isolated", 0): "FIFO 80, CPU 5 + sibling free",
    ("fifo_isolated", 1): "FIFO 80, CPU 5 + sibling free, keep-awake",
    ("other_isolated", 0): "OTHER, CPU 5 + sibling free",
    ("other_isolated", 1): "OTHER, CPU 5 + sibling free, keep-awake",
    ("other_isolated_slack", 0): "OTHER, CPU 5 + sibling free, slack 1 ns",
    ("other_isolated_slack", 1): "OTHER, CPU 5 + sibling free, keep-awake, slack 1 ns",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    run = Path(a.run if Path(a.run).is_absolute() else rpa.ROOT / a.run)
    recs = [json.loads(l) for l in (run / "evals.jsonl").read_text().splitlines() if l.strip()]
    groups = {}
    for r in recs:
        groups.setdefault((r["config"], r["spinner"]), []).append(r)
    rows, out = [], {}
    for key, label in LABELS.items():
        g = groups.get(key)
        if not g:
            continue
        d = rpa.describe(g)
        idle = {}
        for r in g:
            for s, v in r["cpuidle_delta"].items():
                idle[s] = idle.get(s, 0) + v["usage"] / r["duration"]
        idle = {s: v / len(g) for s, v in idle.items()}
        deep = sum(v for s, v in idle.items() if s not in ("POLL", "C1"))
        out[label] = dict(**d, idle_entries_per_s=idle, deep_idle_entries_per_s=deep)
        rows.append(f"| {label} | {len(g)} | {d['median_of_runs']['p50']:.0f} | {d['median_of_runs']['p99']:.0f} | "
                    f"{d['median_of_runs']['p999']:.0f} | {d['pooled']['p99.9']:.0f} "
                    f"[{d['p999_ci95'][0]:.0f}, {d['p999_ci95'][1]:.0f}] | {d['median_of_runs']['max']:.0f} | {deep:.0f} |")
    (run / "summary.json").write_text(json.dumps(out, indent=2))
    table = ("| Condition | Runs | p50 | p99 | p99.9 | p99.9 pooled [95% CI] | max (median) | idle entries/s (C1E or deeper) |\n"
             "|---|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")
    (run / "tables.md").write_text(table)
    print(table)


if __name__ == "__main__":
    main()
