# Appendix A: Planned Cloud Protocol

The cloud study keeps the design of the original proposal and extends the harness developed in this dissertation. It runs on Amazon EC2 bare-metal instances of the C7i family, for which the Nitro PTP Hardware Clock is exposed to Linux guests as a PTP device (/dev/ptp_ena) when the instance is launched in a precision time placement group with ENA driver 2.10 or later [@aws2026phc; @aws2024timesync], and which support hardware packet timestamping at ingress on the Elastic Network Adapter. Bare-metal instances avoid a co-resident hypervisor scheduler while keeping the public-cloud setting in which the research gap was identified. A producer and a consumer instance are placed in one placement group, with data-plane traffic and PTP synchronisation on separate paths (Figure A.1).

![Figure A.1: Planned cloud topology. Solid lines indicate data-plane traffic; dashed lines indicate PTP synchronisation.](figures/topology.png)

The workload is a three-stage synthetic tick-to-trade pipeline (market-data producer, strategy evaluator, order emitter) under Poisson arrivals at four offered loads, timestamped at NIC ingress, application read, post-decision, and NIC egress, and accumulated in HdrHistogram structures [@tene2014hdrhistogram]. Six scenarios form an interpretable gradient: S0 stock Ubuntu with irqbalance; S1 adds IRQ affinity; S2 adds cpuset isolation; S3 adds NUMA-aware allocation; S4 adds nohz_full on the isolated cores; S5 adds PREEMPT_RT with the strategy thread under SCHED_FIFO. Figure A.2 shows the intended CPU, IRQ, and NUMA layout for S5. The analytical strand instantiates the PREEMPT_RT scheduling-latency bound of @bristot2020demystifying with interrupt rates measured by the osnoise tracer and compares the predicted worst case with the observed distribution, treating the two as different quantities rather than as validators of each other. The interrupt-rate recording already built into the local harness is the first step towards that parameterisation.

![Figure A.2: Schematic of the intended CPU, IRQ, and NUMA layout of the consumer instance under the fully optimised cloud scenario (S5). The receiving thread is labelled "Producer" in the diagram; the order emitter shares the isolated SCHED_FIFO set with the strategy thread, and cores 0 and 1 remain with the operating system. Core counts are illustrative.](figures/cpu_layout.png)

The present study changes one element of this plan. Instead of measuring only the fixed gradient S0 to S5, the cloud study should let the search procedure validated here choose among the mechanisms, with the gradient retained as a set of reference points. The budget study of Section 6.5 suggests 20 to 40 evaluations per search. At five minutes per evaluation, ten seeds at each of the four offered loads would need roughly 70 to 130 instance-hours for each search method, or 130 to 270 hours to compare two methods, before re-measurement. The results of Chapter 6 add two requirements: the search space should include idle-state control from the start, and every selected configuration should be re-measured independently.

# Appendix B: Supplementary Tables

| Configuration | p50 | p99 | p99.9 | p99.9 pooled [95% CI] | Max |
|------------------------------------------|-----|-----|-------|------------------------|----------|
| OTHER, CPU 0 | 56 | 105 | 2,264 | 2,458 [2,115, 2,732] | > 20,000 |
| OTHER, CPU 5 | 56 | 70 | 2,865 | 2,642 [2,031, 2,928] | > 20,000 |
| OTHER, CPU 0, isolated | 57 | 531 | 3,251 | 3,189 [2,771, 3,513] | > 20,000 |
| OTHER, CPU 5, isolated | 57 | 444 | 2,888 | 2,890 [2,761, 3,009] | > 20,000 |
| OTHER, CPU 0, isolated, sibling free | 57 | 206 | 1,647 | 1,685 [1,616, 1,758] | > 20,000 |
| OTHER, CPU 5, isolated, sibling free | 56 | 213 | 1,861 | 1,803 [1,670, 1,866] | > 20,000 |
| FIFO 80, CPU 0 | 5 | 11 | 58 | 77 [29, 96] | 9,388 |
| FIFO 80, CPU 5 | 5 | 11 | 91 | 90 [87, 97] | 3,835 |
| FIFO 80, CPU 0, isolated | 6 | 20 | 113 | 102 [74, 117] | 611 |
| FIFO 80, CPU 5, isolated | 6 | 14 | 108 | 109 [100, 120] | 574 |
| FIFO 80, CPU 0, isolated, sibling free | 5 | 35 | 61 | 58 [54, 62] | 642 |
| FIFO 80, CPU 5, isolated, sibling free | 6 | 33 | 49 | 50 [45, 59] | 903 |

: Table B.1: Factorial phase (microseconds). Percentiles are the median over three runs; the pooled p99.9 is computed from the merged histograms with a run-level bootstrap interval, which with three runs approximates the range of the runs. "Max > 20,000" means at least one sample overflowed the histogram.

| Condition | p50 | p99 | p99.9 | p99.9 pooled [95% CI] | Max | Idle entries per second |
|------------------------------------------------------|-----|-----|-------|------------------------|--------|-------|
| FIFO 80, core shared with load | 5 | 12 | 93 | 93 [50, 118] | 2,358 | 5 |
| FIFO 80, core and sibling free | 7 | 33 | 66 | 65 [60, 71] | 498 | 6,312 |
| FIFO 80, core and sibling free, keep-awake | 5 | 14 | 59 | 53 [38, 71] | 481 | 0 |
| OTHER, core and sibling free | 57 | 272 | 1,935 | 2,176 [1,767, 2,668] | 16,524 | 6,638 |
| OTHER, core and sibling free, keep-awake | 54 | 111 | 830 | 985 [614, 1,328] | 12,650 | 0 |
| OTHER, core and sibling free, slack 1 ns | 57 | 302 | 2,180 | 2,768 [1,903, 3,418] | 18,844 | 6,151 |
| OTHER, core and sibling free, keep-awake, slack 1 ns | 54 | 115 | 895 | 817 [577, 950] | 11,039 | 0 |

: Table B.2: C-state follow-up on CPU 5 (microseconds), five runs per condition. Percentiles and maxima are medians over runs. The last column is the mean rate at which the measured CPU entered an idle state of C1E or deeper.

| Pick | Configuration | p50 | p99 | p99.9 | p99.9 pooled [95% CI] | Max | Cliff's delta |
|----------------|--------------------|-----|-----|-------|------------------------|----------|--------|
| Default | OTHER, unpinned | 56 | 75 | 2,385 | 2,541 [2,159, 2,780] | 18,913 | 0 |
| BO, seed 0 | FIFO 1, CPU 10 | 5 | 10 | 19 | 54 [14, 87] | 453 | -0.998 |
| BO, seed 1 | FIFO 52, CPU 10 | 5 | 10 | 17 | 17 [14, 23] | > 20,000 | -0.999 |
| BO, seed 2 | FIFO 1, unpinned | 5 | 10 | 27 | 50 [17, 80] | 2,322 | -0.998 |
| BO, seed 3 | FIFO 99, unpinned | 5 | 10 | 31 | 58 [26, 79] | 2,392 | -0.998 |
| BO, seed 4 | FIFO 1, unpinned | 5 | 9 | 14 | 14 [12, 17] | 454 | -1.000 |
| Random, seed 0 | FIFO 80, unpinned | 5 | 10 | 67 | 59 [15, 87] | 6,505 | -0.998 |
| Random, seed 1 | FIFO 36, unpinned | 5 | 10 | 17 | 21 [14, 60] | 494 | -0.999 |
| Random, seed 2 | FIFO 64, CPU 6 | 5 | 10 | 25 | 30 [14, 69] | 535 | -0.999 |
| Random, seed 3 | FIFO 76, CPU 1 | 5 | 10 | 61 | 63 [22, 82] | 2,521 | -0.998 |
| Random, seed 4 | FIFO 20, CPU 2 | 5 | 11 | 69 | 69 [44, 81] | 8,414 | -0.997 |

: Table B.3: Re-evaluation (microseconds) of the untuned default and of every pick of Phase B, five runs each in shuffled order. Percentiles are medians over runs. Cliff's delta compares all samples of the pick with all samples of the default; minus one means every sample of the pick was faster.

| Budget | BO median regret | BO within 5% | BO exact optimum | Random median regret | Random within 5% | A12 | p |
|--------|-----------|---------|----------|------------|----------|------|---------|
| 10 | 17.5% | 3% | 0% | 24.1% | 3% | 0.61 | 0.065 |
| 20 | 0.8% | 83% | 0% | 14.6% | 3% | 0.96 | < 0.001 |
| 40 | 0.3% | 100% | 43% | 10.7% | 20% | 0.99 | < 0.001 |
| 80 | 0.0% | 100% | 63% | 6.4% | 37% | 1.00 | < 0.001 |
| 150 | 0.0% | 100% | 77% | 4.9% | 53% | 0.98 | < 0.001 |

: Table B.4: Budget study on the synthetic model, 30 seeds per cell. "Within 5%" is the fraction of seeds whose pick had a true 99.9th percentile no more than 5 per cent above the optimum. A12 is the probability that a pick of Bayesian optimisation has lower regret than a pick of random search; p is the one-sided Mann-Whitney test.

# Appendix C: Repository Contents

The project repository is public at \url{https://github.com/cfpandrade/linux-tail-latency-tuning}. It contains the measurement harness and search driver (scripts/experiments/real_pilot.py), the follow-up experiment (cstate_followup.py) and its analysis (cstate_analyse.py), the simulation model and studies (bo_sim.py, bo_budget.py, bo_sensitivity.py), the analysis script that produces every table and figure of Chapter 6 (real_pilot_analyse.py), the unit tests and the measurement smoke test (test_real_pilot.py, test_bo_sim.py; tests/test_smoke.py checks only the repository layout and imports), the raw logs of every real measurement (data/real_pilot/run1/evals.jsonl and data/real_pilot/cstate1/evals.jsonl), and the simulation checkpoints (data/bo_sim_runs/). Re-running the real study requires the rt-tests and stress-ng packages and a raised RLIMIT_RTPRIO and reproduces the design exactly, although measured values will differ with the hardware. Re-running the simulation reproduces its results exactly, because every random draw is seeded.
