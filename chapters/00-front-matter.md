# Abstract

High-frequency trading systems operate in a regime where tail latency, specifically the 99th and 99.9th percentiles rather than mean latency, governs both profitability and regulatory compliance. Kernel-bypass technologies such as DPDK and RDMA dominate on-premises trading infrastructure, but their operational complexity, hardware lock-in, and historical incompatibility with public-cloud environments motivate a renewed examination of kernel-resident optimisation. The recent availability of Precision Time Protocol Hardware Clocks in AWS Nitro provides, for the first time, sub-microsecond timestamping without customer-owned grand-master hardware, yet the interaction of cloud precision time with Linux kernel tuning has not been systematically characterised in the peer-reviewed literature.

This dissertation presents a hybrid empirical and analytical study that quantifies the contribution of IRQ affinity, CPU isolation, NUMA-aware placement, tickless operation, and PREEMPT_RT to tail-latency reduction in cloud-hosted Linux, under a synthetic high-frequency-trading tick-to-trade workload. A scheduling-latency bound derived from the thread-synchronisation model of PREEMPT_RT is instantiated with empirically measured parameters, and hardware timestamps are used to bound measurement error below the target effect size. Six incremental tuning scenarios are evaluated across four offered loads on bare-metal cloud instances, with heavy-tail-aware statistical treatment.

The intended contributions are a cloud-specific tuning methodology validated against an analytical bound, a reproducible open-source benchmark harness, and a quantified residual gap with respect to published kernel-bypass baselines, with implications for regulated financial infrastructure under MiFID II Regulatory Technical Standard 25.

# List of Abbreviations

ENA: Elastic Network Adapter

DPDK: Data Plane Development Kit

HFT: High-Frequency Trading

IRQ: Interrupt Request

MiFID II: Markets in Financial Instruments Directive II

NUMA: Non-Uniform Memory Access

NTP: Network Time Protocol

PHC: PTP Hardware Clock

PTP: Precision Time Protocol

RDMA: Remote Direct Memory Access

RTS: Regulatory Technical Standard

SRE: Site Reliability Engineering
