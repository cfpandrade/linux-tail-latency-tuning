# 3 Research Aims and Questions

## 3.1 Aim and Objectives

The long-term aim of this line of work is to characterise and bound the tail latency attainable by a kernel-resident, PTP-synchronised Linux system in a public-cloud, HFT-adjacent context. Within the resources of this project, the aim is to establish on commodity Linux hardware how much of the scheduling-latency tail can be removed with the tuning mechanisms that need no kernel reconfiguration, and whether a good combination of them can be found automatically with a small measurement budget and independent re-measurement. Five objectives serve this aim: (1) build a reproducible harness that records the full wake-up latency distribution of a periodic thread under controlled contention and can be driven by a search procedure; (2) measure the effect of real-time scheduling, affinity-based core isolation, and freeing the SMT sibling, singly and in combination, and of CPU pinning observationally; (3) compare Bayesian optimisation against random search with independent re-measurement of the selected configurations; (4) use a synthetic latency model with a known optimum to quantify how many measurements each procedure needs and test that conclusion under perturbation; and (5) outline the design of the cloud study (Appendix A).

## 3.2 Research Questions

RQ1. On a commodity Linux host without a real-time kernel, how much do real-time scheduling, CPU pinning, affinity-based isolation, and freeing the SMT sibling reduce the 99th and 99.9th percentiles of scheduling latency under contention, individually and in combination?

RQ2. Can Bayesian optimisation identify a near-optimal configuration within a small measurement budget, and does it select better configurations than random search when every evaluation is a noisy tail-latency measurement?

RQ3. Does the advantage of Bayesian optimisation, and the ranking of parameter importance, hold when the coefficients of the latency model are perturbed?

The proposal's questions on cloud PTP timestamping, the analytical scheduling-latency bound, and the residual gap to kernel bypass require the cloud platform and a real-time kernel; they are retained as the agenda of the cloud study.

## 3.3 Hypotheses

The proposal fixed a quantitative threshold for success before any data were collected, and it is kept unchanged.

H1. The best configuration found reduces the 99.9th-percentile scheduling latency by at least a factor of four relative to the untuned default, as measured by independent re-evaluation. The threshold was set for tick-to-trade latency in the cloud and is carried over unchanged, so it is a minimum standard rather than a demanding test.

H2. For equal budgets on the real host, the configurations selected by Bayesian optimisation are at least as good as those selected by random search when re-measured. A re-measured disadvantage, a Vargha-Delaney A12 below 0.5 for the picks of Bayesian optimisation against those of random search, refutes H2. The proposal stated H2 qualitatively; this criterion was made explicit after data collection. It is descriptive: if the two methods were equivalent it would be met by chance about half the time, so a result that does not refute H2 is weak evidence in its favour. Either outcome is reported as found.
