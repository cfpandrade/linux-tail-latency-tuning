# Discussion

This chapter interprets the results of Chapter 6 against the aim and the research questions, draws out the implications for practice and regulation, and states the limitations that bound the conclusions. The interpretive claims are framed so they follow directly from the measured values once the run is complete. The direction of each argument is fixed by the design. Only the magnitudes remain to be inserted.

## 7.1 Interpretation of Findings

The three empirical strands are read together, not in isolation. Attribution (RQ1) identifies which mechanisms carry most of the tail-latency reduction, and whether their effects are additive or interact, in particular whether CPU isolation and real-time scheduling dominate the final scenarios as the practitioner literature suggests. Measurement fidelity (RQ2) then sets the bar for trust: it establishes how much of an apparent effect is genuine and how much is an artefact of the measurement clock, and therefore how much confidence the attribution deserves. The bound validation (RQ3) either corroborates the analytical model or refutes it. Both outcomes are informative. A refuted bound still narrows the space of plausible explanations.

## 7.2 Implications for Practice and Regulation

The findings translate into a concrete tuning recipe for practitioners deploying latency-sensitive workloads on cloud bare-metal instances, ordered by the measured contribution of each mechanism. The achieved tail latency and measurement fidelity are then related to MiFID II Regulatory Technical Standard 25, which requires clock synchronisation to within 100 microseconds at 1 microsecond granularity. The practical question is whether a kernel-resident, cloud-hosted configuration can meet that obligation without specialised hardware.

## 7.3 Comparison with Prior Work

The residual-gap result (RQ4) is positioned within the revisionist literature that argues modern kernel features have narrowed the advantage of kernel bypass. The measured gap either supports that position or qualifies it under cloud constraints, which earlier bare-metal comparisons did not address.

## 7.4 Limitations

Three limitations bound the conclusions, and all three touch precision rather than direction. The workload is synthetic, so the burstiness and protocol-level framing of real exchange feeds are not reproduced by the Poisson approximation. The public-cloud environment adds a noisy-neighbour variable that placement-group co-location only partially controls. The PTP Hardware Clock imposes an irreducible measurement floor of roughly one microsecond, below which effects cannot be separated from noise. None of these overturns a finding; each sets the resolution at which a finding can be trusted, and each maps to a future-work extension in Chapter 8.
