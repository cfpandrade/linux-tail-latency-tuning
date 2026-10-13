# Results and Analysis

This chapter reports the experimental results against each research question in turn. All percentile figures are recovered from the per-trial HdrHistogram accumulators described in Chapter 5, and all confidence intervals are the non-parametric bootstrap intervals defined in Section 4.7. The numeric cells in the tables below are placeholders pending the full experimental run on the cloud platform; the structure, metrics, and statistical treatment are fixed so that the measured values drop directly into place.

## 6.1 Per-Intervention Attribution (RQ1)

This section reports the 50th, 95th, 99th, and 99.9th percentiles of tick-to-trade latency for each scenario S0 to S5 at each of the four offered loads, together with the marginal change attributable to the single mechanism added at each step. Effect sizes are reported as Cliff's delta with bootstrap confidence intervals, and pairwise distributional differences are assessed with the Kolmogorov-Smirnov test under Bonferroni correction.

Table 6.1 reports the tail percentiles per scenario at the reference load. Figure 6.1 overlays the latency cumulative distribution functions for the baseline and the fully tuned configuration, and Figure 6.2 shows the progression of the 99th and 99.9th percentiles across the scenario gradient.

| Scenario | p50 (us) | p95 (us) | p99 (us) | p99.9 (us) | Cliff's delta vs S0 |
|----------|----------|----------|----------|------------|---------------------|
| S0 baseline | TBD | TBD | TBD | TBD | - |
| S1 IRQ affinity | TBD | TBD | TBD | TBD | TBD |
| S2 CPU isolation | TBD | TBD | TBD | TBD | TBD |
| S3 NUMA-aware | TBD | TBD | TBD | TBD | TBD |
| S4 nohz_full | TBD | TBD | TBD | TBD | TBD |
| S5 PREEMPT_RT + FIFO | TBD | TBD | TBD | TBD | TBD |

Table 6.1: Tick-to-trade latency percentiles per scenario at the reference offered load, with effect size relative to the stock baseline.

## 6.2 Measurement Fidelity: NTP versus PHC (RQ2)

This section quantifies the measurement artefact introduced by NTP-based timestamping relative to the PTP Hardware Clock, and examines whether the qualitative conclusions of Section 6.1 would change had NTP been used. The expected signature, following the Flow Traders deployment, is an apparent negative one-way latency under NTP that disappears under PHC. Table 6.2 reports the paired per-scenario offset between the two clocks and the resulting error in the estimated 99.9th percentile.

| Scenario | NTP p99.9 (us) | PHC p99.9 (us) | Artefact (us) |
|----------|----------------|----------------|---------------|
| S0 to S5 | TBD | TBD | TBD |

Table 6.2: Measurement artefact between NTP and PHC timestamping.

## 6.3 Analytical Bound Validation (RQ3)

This section compares the predicted 99.9th-percentile bound from the fixed-point model of Section 4.6, parameterised by the per-scenario interrupt rates captured through the osnoise tracer, against the empirically observed 99.9th percentile. Agreement is assessed at each of the four loads to test whether the model captures the super-linear growth of the tail near saturation. Figure 6.3 plots predicted against observed values with the line of equality.

| Scenario | Predicted p99.9 (us) | Observed p99.9 (us) | Relative error |
|----------|----------------------|---------------------|----------------|
| S0 to S5 | TBD | TBD | TBD |

Table 6.3: Predicted versus observed 99.9th-percentile latency.

## 6.4 Residual Gap versus DPDK Baselines (RQ4)

This section situates the best kernel-tuned configuration, scenario S5, against published DPDK median and tail figures, quantifying the residual gap and relating it to the factor-of-two-to-five expectation set out in the literature. The comparison is framed to answer whether the gap is narrow enough to justify kernel-resident deployment in cloud HFT-adjacent workflows.

| Metric | S5 kernel-tuned | Published DPDK | Residual factor |
|--------|-----------------|----------------|-----------------|
| Median latency | TBD | TBD | TBD |
| p99.9 latency | TBD | TBD | TBD |

Table 6.4: Residual gap between the best kernel-tuned configuration and published kernel-bypass baselines.
