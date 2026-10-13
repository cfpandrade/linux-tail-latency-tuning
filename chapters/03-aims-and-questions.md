# Research Aims and Questions

## 3.1 Overall Aim

The overall aim is to characterise and bound the deterministic tail latency attainable by a kernel-resident, PTP-synchronised Linux system in a public-cloud, HFT-adjacent context. The emphasis is on the 99th and 99.9th percentiles of tick-to-trade latency, measured under a representative synthetic workload and compared against both an analytical bound and published kernel-bypass baselines. The aim is framed so that success is defined not by a single headline figure but by a defensible, reproducible characterisation of the whole tail of the distribution across a realistic range of offered load.

## 3.2 Objectives

The aim is pursued through five concrete objectives, which together convert the research gap identified in Section 2.6 into an executable programme of work.

1. Build a reproducible synthetic tick-to-trade workload and a four-point hardware-timestamped measurement pipeline that isolate scheduling behaviour from application artefacts.
2. Define an incremental gradient of tuning scenarios, from a stock baseline to a fully tuned real-time configuration, so that the marginal contribution of each mechanism can be attributed rather than confounded.
3. Quantify the tail-latency distribution of each scenario across a realistic range of offered load, with statistical treatment appropriate to heavy-tailed, non-Gaussian data.
4. Instantiate an analytical scheduling-latency bound with empirically measured parameters, and test its predictions against the observed percentiles.
5. Situate the best kernel-tuned result against published kernel-bypass figures, so that the residual gap is quantified rather than asserted.

## 3.3 Research Questions

The aim and objectives decompose into four research questions, each mapped to a strand of the methodology in Chapter 4.

RQ1. How do individual kernel-tuning interventions (IRQ affinity, CPU isolation, NUMA-aware allocation, nohz_full tickless operation, and PREEMPT_RT) contribute to reduction of the 95th, 99th, and 99.9th percentiles of tick-to-trade latency, both independently and in combination?

RQ2. To what extent does cloud-provided PTP hardware timestamping reduce measurement uncertainty in tail-latency estimates, and does this change the qualitative conclusions that would have been drawn from NTP-based measurement?

RQ3. Can an analytical scheduling-latency bound, parameterised by empirically measured interrupt rates and interference distributions, predict the observed 99.9th-percentile latency within a stated confidence interval?

RQ4. What is the residual tail-latency gap between the best kernel-tuned configuration and published DPDK baselines, and is this gap narrow enough to justify kernel-resident deployment in cloud HFT-adjacent workflows?

## 3.4 Hypothesis

Framed for falsifiability, the hypothesis is that the fully tuned configuration (S5) reduces the 99.9th-percentile tick-to-trade latency by at least a factor of four relative to the stock baseline (S0), and falls within 20 percent of the analytical bound across the tested load regime. A result outside either threshold refutes the hypothesis and is reported as such, since a refuted but well-characterised bound is itself a contribution to the understanding of deterministic latency in virtualised systems.
