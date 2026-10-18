# Declaration

I declare that this dissertation is my own work and that it has not been submitted, in whole or in part, for any other degree or qualification at this or any other institution. Where the work of others has been used, it is acknowledged and referenced in the text.

\vspace{3em}

Signed: \rule{6cm}{0.4pt}

\vspace{1em}

Carlos Perez Andrade

Date: \rule{4cm}{0.4pt}

# Abstract

In high-frequency trading the 99th and 99.9th percentiles of latency, not the mean, decide profitability, and timestamp accuracy is a regulatory obligation. Kernel bypass dominates on-premises trading infrastructure, but a tuned Linux kernel is increasingly seen as a credible alternative, particularly in the public cloud. Choosing the tuning configuration is itself an expensive search problem: the mechanisms interact, each evaluation is a noisy measurement of a rare event, and in practice the configuration is set by hand.

This dissertation studies that problem on a commodity Linux workstation, as an executable first step towards a cloud study whose design it outlines. It measures the wake-up latency of a periodic thread under heavy contention in 401 measurements of 30 seconds each: a factorial design over real-time scheduling, CPU pinning, affinity-based core isolation, and SMT sibling exclusion, and a comparison of Bayesian optimisation with random search in which every selected configuration is re-measured independently. A simulation with an exactly known optimum quantifies how the advantage of Bayesian optimisation depends on the measurement budget and tests it under perturbation of the model.

Real-time scheduling reduced the 99.9th percentile by a factor of about 32 and separated the scheduling classes completely. Freeing the SMT sibling of an isolated core reduced it by a further 45 per cent. Isolation by affinity alone raised the 99th percentile about six-fold under the default scheduler, which a follow-up experiment linked to processor idle states. Every selected configuration cut the 99.9th percentile from about 2.5 milliseconds to between 14 and 69 microseconds, far beyond the four-fold target fixed in advance. Bayesian optimisation spent its budget far better than random search and its picks had a lower median tail, but with five seeds the difference was not significant. In simulation it came within 5 per cent of the optimum with 20 evaluations in 83 per cent of seeds, against 150 evaluations for random search, under every completed perturbation. The results argue for model-based search with mandatory re-measurement, and show that core isolation must be paired with idle-state control.

# List of Abbreviations

AWS: Amazon Web Services

BO: Bayesian Optimisation

CCDF: Complementary Cumulative Distribution Function

CPU: Central Processing Unit

DPDK: Data Plane Development Kit

EC2: Amazon Elastic Compute Cloud

ENA: Elastic Network Adapter

GP: Gaussian Process

HFT: High-Frequency Trading

IRQ: Interrupt Request

MiFID II: Markets in Financial Instruments Directive II

NIC: Network Interface Card

NTP: Network Time Protocol

NUMA: Non-Uniform Memory Access

PHC: PTP Hardware Clock

PTP: Precision Time Protocol

RTS: Regulatory Technical Standard

SCHED_FIFO: First-In, First-Out real-time scheduling policy of Linux

SCHED_OTHER: Default time-sharing scheduling policy of Linux

SHAP: SHapley Additive exPlanations

SMT: Simultaneous Multithreading

UTC: Coordinated Universal Time
