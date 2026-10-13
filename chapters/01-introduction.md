# Introduction

## 1.1 Context and Motivation
High-frequency trading operates where tail latency (99th and 99.9th percentiles), not mean latency, governs profitability and regulatory compliance. Establish the microsecond regime and why variance matters.

## 1.2 Problem Statement
Kernel-bypass (DPDK, RDMA) dominates on-premises HFT but carries operational complexity, hardware lock-in, and poor cloud compatibility. Recent AWS Nitro PTP Hardware Clocks and maturing kernel features reopen the design space.

## 1.3 Research Question
To what extent can kernel-level tuning, combined with cloud-provided PTP synchronisation, approach the deterministic tail-latency behaviour of kernel-bypass solutions in an HFT context.

## 1.4 Aim and Objectives
State the overall aim and the four research questions (RQ1 to RQ4).

## 1.5 Contributions
Hybrid empirical and analytical methodology; study of the under-characterised cloud-virtualised regime; open reproducible benchmark artefact.

## 1.6 Dissertation Structure
Roadmap of the remaining chapters.
