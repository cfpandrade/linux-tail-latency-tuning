# Research Aims and Questions

## 3.1 Overall Aim
Characterise and bound the deterministic tail latency attainable by a kernel-resident, PTP-synchronised Linux system in a public-cloud HFT-adjacent context.

## 3.2 Research Questions
RQ1. Contribution of individual tuning interventions (IRQ affinity, CPU isolation, NUMA-aware allocation, nohz_full, PREEMPT_RT) to the 95th, 99th, and 99.9th percentiles, independently and combined.
RQ2. Extent to which cloud PTP hardware timestamping reduces measurement uncertainty and whether it changes qualitative conclusions versus NTP.
RQ3. Whether an analytical scheduling-latency bound, parameterised by measured interrupt rates and interference distributions, predicts the observed 99.9th percentile within a stated confidence interval.
RQ4. Residual tail-latency gap between the best kernel-tuned configuration and published DPDK baselines.

## 3.3 Hypothesis
The fully tuned configuration reduces 99.9th-percentile latency by at least a factor of four relative to stock baseline, and falls within 20 percent of the analytical bound across the tested load regime.
