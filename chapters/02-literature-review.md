# Background and Literature Review

## 2.1 Tail Latency and its Economic Significance
Dean and Barroso on the tail at scale; Hasbrouck and Saar on low-latency trading; MiFID II RTS 25 clock-synchronisation requirement (100 microsecond bound, 1 microsecond granularity).

## 2.2 Sources of Latency Variance in Linux
Lock contention (Boyd-Wickizer et al.), NUMA memory-controller congestion (Dashti et al., Carrefour), interrupt-handler jitter (Herzog et al., INTSPECT), and the PREEMPT_RT scheduling-latency bound (Bristot de Oliveira et al.).

## 2.3 Kernel-Resident Tuning Techniques
CPU isolation via cgroup v2 cpuset, IRQ affinity pinning, nohz_full tickless mode, PREEMPT_RT, SCHED_FIFO. Note the fragmentation of existing evaluations.

## 2.4 Kernel Bypass and its Contemporary Limits
DPDK, RDMA, AF_XDP, OpenOnload; representative latency figures; Jasny et al. DaMoN 2025 "wake-up call"; io_uring as a hybrid path.

## 2.5 Precision Time Protocol and Measurement Fidelity
IEEE 1588-2019, Meta deployment, cloud PHC exposure, Flow Traders NTP artefact. PTP as instrumentation, not intervention.

## 2.6 Identified Research Gap
No published study quantifies the tail-latency distribution of a cloud-hosted, kernel-tuned Linux system against an analytical bound under an HFT-representative workload using PTP hardware timestamps.
