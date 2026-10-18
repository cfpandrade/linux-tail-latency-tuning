# Sensitivity analysis of the BO-vs-random budget study (SYNTHETIC model)

All numbers come from the synthetic latency model in `scripts/experiments/bo_sim.py`; they test whether the
methodological conclusions survive changes to its hand-chosen coefficients, not anything about a real kernel.

Produced by `scripts/experiments/bo_sensitivity.py` (see its docstring for the full design).

## What was run
- Models complete: {'base': 1, 'oat': 56, 'global': 0} (designed: {'base': 1, 'oat': 88, 'global': 128}).
- Perturbed coefficients (22): magnitudes scaled by f (base_median_us, base_event_p, base_stall_us, alpha, body_sigma, iso_decay, iso_cap, rtprio_scale_gain, coalesce_gain, coalesce_sat_us, coalesce_body);
  multiplicative factors with the log-effect scaled, value**f (irq_noiso_p, irq_iso_p, irq_over_p, nohz_p, rt_scale, rt_body, gov_p, gov_body, numa_p, numa_body, rt_high_p). Clamps: {'base_event_p': (1e-07, 0.5), 'rtprio_scale_gain': (0.0, 0.95), 'coalesce_gain': (0.0, 0.95), 'iso_cap': (1, 8), 'coalesce_sat_us': (1.0, 100.0), 'body_sigma': (0.01, 2.0), 'alpha': (0.2, 20.0)}.
- OAT grid f in {0.5, 0.75, 1.5, 2}; global sweep: scrambled Sobol (seed 20261014), each multiplier log-uniform in [0.5, 2].
- Per model: budgets [10, 20, 40, 80, 150] x {BO, random} x 30 seeds (seeds shared across models),
  1,000,000 samples per noisy evaluation; BO budgets are prefixes of one 150-evaluation chain
  (exactly equivalent to separate gp_minimize runs).
- Ground truth per model: exhaustive over the full 2,879,712-point space; regret = true p99.9(pick)/optimum - 1.
- True importance: exact first-order and total-effect Sobol indices of log10 true p99.9 under the uniform
  distribution on the search space; RF-SHAP on the random-search trials (budget 150, all seeds) for comparison.

## Headline (all complete models)
| budget | median A12 | A12 p5-p95 | median (BO - random) regret | p5-p95 | frac p<0.05 |
|---|---|---|---|---|---|
| 10 | 0.614 | 0.601-0.634 | -0.0655 | -0.0742--0.0413 | 0.140 |
| 20 | 0.977 | 0.932-0.997 | -0.1381 | -0.1652--0.1190 | 1.000 |
| 40 | 0.987 | 0.970-0.994 | -0.1041 | -0.1238--0.0804 | 1.000 |
| 80 | 0.996 | 0.992-0.998 | -0.0635 | -0.0885--0.0524 | 1.000 |
| 150 | 0.979 | 0.972-0.982 | -0.0485 | -0.0774--0.0403 | 1.000 |

isolated_cores is the top parameter (total-effect Sobol) in 100.0% of 57 models.

Base-model reproduction: 300/300 identical picks vs the base run, max relative difference of true p99.9 0.00e+00; optimum 10.2910 us (base run 10.2910), default 766.67 us.

## Files
- `models.json` design (multipliers and coefficient overrides); `run_config.json` settings.
- `checkpoint.jsonl` one line per finished job (truth / BO chain / random run; trials kept for BO chains
  and random budget-150 runs); `shap.jsonl` RF-SHAP per model.
- `model_metrics.csv` per (model, budget) metrics; `models.csv` per-model truth, importance and ranks.
- `summary.json` aggregates; figures `a12_by_budget.png`, `regret_diff_by_budget.png`, `regret_envelope.png`,
  `oat_a12_heatmap.png`, `global_a12_regression.png`, `importance_rank_stability.png`.


