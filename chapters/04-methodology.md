# Methodology

## 4.1 Research Design
Mixed-methods design: controlled empirical experimentation addresses RQ1, RQ2, RQ4; analytical modelling addresses RQ3. The strands cross-validate each other.

## 4.2 Experimental Platform
Amazon EC2 c7i.metal instances exposing the Nitro PTP Hardware Clock via /dev/ptp0 and ENA hardware packet timestamping. Single cluster placement group, one Availability Zone. Ubuntu 24.04 LTS, kernel 6.8 series, optionally PREEMPT_RT.

## 4.3 Workload and Instrumentation
Synthetic HFT tick-to-trade workload in C++20: market-data producer, strategy evaluator, order emitter, connected by SPSC lock-free ring buffers. Poisson arrivals at 1e5, 3e5, 1e6, 3e6 msg/s. Four hardware timestamp points: NIC ingress, application read, post-strategy, NIC egress.

## 4.4 System Architecture and CPU Layout
Two-instance topology with Amazon Time Sync reference. CPU, IRQ, and NUMA layout under the fully optimised configuration (Figures 1 and 2 from the proposal).

## 4.5 Experimental Scenarios
Gradient S0 to S5: S0 stock Ubuntu with irqbalance; S1 IRQ affinity; S2 plus CPU isolation (cgroup v2 cpuset); S3 plus NUMA-aware allocation; S4 plus nohz_full; S5 plus PREEMPT_RT with SCHED_FIFO. Four loads, 30-minute runs after 5-minute warm-up, ten trials per cell on fresh instances.

## 4.6 Analytical Scheduling-Latency Model
Bristot de Oliveira et al. bound L = max(DST, DPOID) + DPAIE + DPSD + INMI(L) + IIRQ(L), evaluated to fixed point. Interference functions parameterised from measured per-scenario interrupt rates via the osnoise tracer. Evaluated at each load to test load-induced tail growth.

## 4.7 Metrics and Statistical Analysis
Primary: 50th, 95th, 99th, 99.9th percentiles from HdrHistogram. Secondary: per-core IRQ counts, context-switch rates, cache-miss counters, PTP offset via phc2sys. Two-sample Kolmogorov-Smirnov at alpha 0.01 with Bonferroni correction; bootstrap confidence intervals (1e4 resamples); Cliff's delta effect sizes.

## 4.8 Ethical and Professional Considerations
Fully synthetic workload, no live market data or order entry. A priori power analysis to limit compute hours and energy. Artefacts released under Apache 2.0 for reproducibility.
