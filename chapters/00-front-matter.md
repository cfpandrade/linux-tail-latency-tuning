# Abstract

In high-frequency trading the 99th and 99.9th percentiles of latency, not the mean, govern profitability, and timestamp accuracy is a regulatory obligation. A tuned Linux kernel is a credible alternative to kernel bypass, particularly in the public cloud, but choosing the tuning configuration is itself an expensive search problem: the mechanisms interact, each evaluation is a noisy measurement of a rare event, and in practice the configuration is set by hand.

This dissertation studies that problem on a commodity Linux workstation, as a feasible first step towards a cloud study it outlines. It measures the wake-up latency of a periodic thread under heavy contention in 401 measurements of 30 seconds each: a factorial design over real-time scheduling, affinity-based core isolation, and freeing of the simultaneous multithreading (SMT) sibling, with CPU pinning assessed observationally, and a comparison of Bayesian optimisation with random search in which every selected configuration is re-measured independently. A simulation with an exactly known optimum quantifies how the advantage of Bayesian optimisation depends on the measurement budget and tests it under perturbation.

Real-time scheduling reduced the 99.9th percentile by a factor of about 32 and separated the scheduling classes completely. Freeing the SMT sibling of an isolated core reduced it by a further 45 per cent. Isolation by affinity alone raised the 99th percentile about six-fold under the default scheduler; a follow-up experiment linked the isolation penalty to processor idle states. Every selected configuration cut the 99.9th percentile from about 2.5 milliseconds to between 14 and 69 microseconds, well beyond the four-fold target fixed in advance. Bayesian optimisation wasted far fewer measurements on poor configurations than random search and its picks had a lower median tail, though not significantly so with five seeds. In simulation it came within 5 per cent of the optimum with 20 evaluations in 83 per cent of seeds, whereas random search reached that in about half of its seeds at 150, and the advantage held under every completed perturbation. The results argue for model-based search with mandatory re-measurement, and indicate that core isolation should be paired with idle-state control.

# List of Abbreviations

AWS: Amazon Web Services

BCS: British Computer Society

BO: Bayesian Optimisation

CI: Confidence Interval

CPU: Central Processing Unit

DPDK: Data Plane Development Kit

EC2: Amazon Elastic Compute Cloud

ENA: Elastic Network Adapter

HFT: High-Frequency Trading

IRQ: Interrupt Request

MiFID II: Markets in Financial Instruments Directive II

NIC: Network Interface Card

NTP: Network Time Protocol

NUMA: Non-Uniform Memory Access

PTP: Precision Time Protocol

RDMA: Remote Direct Memory Access

RQ: Research Question

RTS: Regulatory Technical Standard

SCHED_FIFO: First-In, First-Out real-time scheduling policy of Linux

SCHED_OTHER: Default time-sharing scheduling policy of Linux

SHAP: SHapley Additive exPlanations

SMT: Simultaneous Multithreading
