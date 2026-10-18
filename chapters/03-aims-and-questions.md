# 3 Research Aims and Questions

## 3.1 Aim and Objectives

The long-term aim of this line of work is to characterise and bound the tail latency attainable by a kernel-resident, PTP-synchronised Linux system in a public-cloud, HFT-adjacent context. Within the resources of this project, the aim is to establish on commodity Linux hardware how much of the scheduling-latency tail can be removed with the tuning mechanisms that need no kernel reconfiguration, and whether a good combination of them can be found automatically with a small measurement budget and independent re-measurement of the result. Five objectives serve this aim:

1. Build a reproducible harness that records the full wake-up latency distribution of a periodic thread under controlled contention, with per-core interrupt rates, and that can be driven by a search procedure.
2. Measure the effect of real-time scheduling policy and priority, CPU pinning, affinity-based isolation of the latency-critical core, and exclusion of its SMT sibling, one at a time and in combination.
3. Compare Bayesian optimisation against random search as procedures for choosing a configuration, using independent re-measurement of the selected configurations.
4. Use a synthetic latency model with a known optimum to quantify how many measurements each procedure needs, and test whether that conclusion survives perturbation of the model.
5. Outline the design of the cloud study as the basis for future work (Appendix A).

## 3.2 Research Questions

RQ1. On a commodity Linux host without a real-time kernel, how much do real-time scheduling, CPU pinning, affinity-based isolation, and SMT sibling exclusion reduce the 99th and 99.9th percentiles of scheduling latency under contention, individually and in combination?

RQ2. Can Bayesian optimisation identify a near-optimal configuration within a small measurement budget, and does it select better configurations than random search when every evaluation is a noisy tail-latency measurement?

RQ3. Does the advantage of Bayesian optimisation, and the ranking of parameter importance, hold when the coefficients of the latency model are perturbed?

The original proposal also asked whether cloud PTP timestamping changes the conclusions drawn from NTP-based measurement, whether an analytical scheduling-latency bound predicts the observed 99.9th percentile, and how large the residual gap to kernel bypass is. Those questions require the cloud platform and a real-time kernel; they are retained as the agenda of the cloud study and are not answered here.

## 3.3 Hypotheses

The proposal fixed a quantitative threshold for success before any data were collected: the best tuned configuration should reduce the 99.9th-percentile latency by at least a factor of four relative to the untuned baseline. That threshold is kept unchanged.

H1. The best configuration found reduces the 99.9th-percentile scheduling latency by at least a factor of four relative to the untuned default, as measured by independent re-evaluation. The threshold was set for tick-to-trade latency in the cloud and is carried over to the scheduling latency measured here, so it is a minimum standard rather than a demanding test.

H2. For equal budgets on the real host, the configurations selected by Bayesian optimisation are at least as good as those selected by random search when re-measured. A re-measured disadvantage, defined as a Vargha-Delaney A12 below 0.5 for the picks of Bayesian optimisation against those of random search, refutes H2. The proposal stated H2 qualitatively; this criterion was made explicit after data collection. It is descriptive: if the two methods were equivalent it would be met by chance about half the time, so a result that does not refute H2 is weak evidence in its favour. The simulation study is used to explain the outcome of this test, not to confirm it.

Either outcome is reported as found. A refuted hypothesis on commodity hardware is still informative for the cloud study, because it tells the experimenter where measurement effort is, and is not, worth spending.
