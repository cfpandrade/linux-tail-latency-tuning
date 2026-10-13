# Research Aims and Questions

## 3.1 Overall Aim

The overall aim is to characterise and bound the deterministic tail latency attainable by a kernel-resident, PTP-synchronised Linux system in a public-cloud, HFT-adjacent context. The emphasis is on the 99th and 99.9th percentiles of tick-to-trade latency, measured under a representative synthetic workload and compared against both an analytical bound and published kernel-bypass baselines.

## 3.2 Research Questions

The aim decomposes into four research questions.

RQ1. How do individual kernel-tuning interventions (IRQ affinity, CPU isolation, NUMA-aware allocation, nohz_full tickless operation, and PREEMPT_RT) contribute to reduction of the 95th, 99th, and 99.9th percentiles of tick-to-trade latency, both independently and in combination?

RQ2. To what extent does cloud-provided PTP hardware timestamping reduce measurement uncertainty in tail-latency estimates, and does this change the qualitative conclusions that would have been drawn from NTP-based measurement?

RQ3. Can an analytical scheduling-latency bound, parameterised by empirically measured interrupt rates and interference distributions, predict the observed 99.9th-percentile latency within a stated confidence interval?

RQ4. What is the residual tail-latency gap between the best kernel-tuned configuration and published DPDK baselines, and is this gap narrow enough to justify kernel-resident deployment in cloud HFT-adjacent workflows?

## 3.3 Hypothesis

Framed for falsifiability, the hypothesis is that the fully tuned configuration (S5) reduces the 99.9th-percentile tick-to-trade latency by at least a factor of four relative to the stock baseline (S0), and falls within 20 percent of the analytical bound across the tested load regime. A result outside either threshold refutes the hypothesis and is reported as such.
