# Tail-Latency Tuning of Linux for Low-Latency Trading

An empirical study of user-space mechanisms and Bayesian optimisation, with a design for cloud evaluation.

MSc Computer Science with Artificial Intelligence dissertation, University of Wolverhampton, module 7CS077, October 2026.
Author: Carlos Andrade. Supervisor: Dr Vahid Rafe.

The compiled dissertation is `build/dissertation.pdf`. Repository: https://github.com/cfpandrade/linux-tail-latency-tuning

## Contents

- `chapters/` Markdown source of the dissertation, one file per chapter, compiled with pandoc (`make pdf`).
- `references.bib` bibliography (Harvard, Cite Them Right style via `templates/`).
- `scripts/experiments/real_pilot.py` measurement harness and search driver for the real study (cyclictest under stress-ng contention, Bayesian optimisation versus random search, re-evaluation and factorial phases).
- `scripts/experiments/cstate_followup.py` and `cstate_analyse.py` idle-state follow-up experiment.
- `scripts/experiments/bo_sim.py`, `bo_budget.py`, `bo_sensitivity.py` synthetic latency model, budget study, and sensitivity study.
- `scripts/experiments/real_pilot_analyse.py` produces every table and figure of the results chapter from the raw logs.
- `scripts/experiments/test_*.py`, `tests/` unit and smoke tests.
- `data/real_pilot/` raw logs of every real measurement (one JSON record per 30-second measurement).
- `data/bo_sim_runs/` simulation checkpoints and summaries.
- `figures/` figures used in the dissertation.

## Reproducing

Real study: Linux host with `rt-tests` (cyclictest) and `stress-ng` installed and `RLIMIT_RTPRIO` raised to 99 for the launching process. Run `python -m scripts.experiments.real_pilot` and then `python -m scripts.experiments.real_pilot_analyse`. Measured values depend on the hardware and the state of the machine; the design is reproduced exactly.

Simulation: `pip install -r requirements-analysis.txt`, then run `bo_budget.py` and `bo_sensitivity.py`. Every random draw is seeded, so the results are reproduced exactly.

Document: `make pdf` requires pandoc, pandoc-citeproc support, and XeLaTeX.

## Licence

Text and figures of the dissertation: CC BY 4.0. Code: MIT.
