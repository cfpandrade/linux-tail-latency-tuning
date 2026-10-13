# Discussion

This chapter interprets the results of Chapter 6 against the aim and research questions, draws out the implications for practice and regulation, and states the limitations that bound the conclusions. The interpretive claims below are framed so that they follow directly from the measured values once the experimental run is complete; the direction of each argument is fixed by the design, and only the magnitudes remain to be inserted.

## 7.1 Interpretation of Findings

This section interprets the per-intervention attribution, the measurement-fidelity comparison, and the bound validation as a single coherent picture. The attribution result (RQ1) is read to identify which mechanisms carry most of the tail-latency reduction and whether their effects are additive or interact, in particular whether CPU isolation and real-time scheduling dominate the final scenarios as the practitioner literature suggests. The measurement-fidelity result (RQ2) is used to establish how much of an apparent effect is genuine rather than an artefact of the measurement clock, and therefore how much confidence the attribution deserves. The bound-validation result (RQ3) is interpreted as either corroborating or refuting the analytical model; both outcomes are treated as informative, since a refuted bound still constrains the space of plausible explanations.

## 7.2 Implications for Practice and Regulation

This section translates the findings into a concrete tuning recipe for practitioners deploying latency-sensitive workloads on cloud bare-metal instances, ordered by the measured contribution of each mechanism. It then relates the achieved tail latency and measurement fidelity to the MiFID II Regulatory Technical Standard 25 requirement for clock synchronisation to within 100 microseconds at 1 microsecond granularity, assessing whether a kernel-resident, cloud-hosted configuration can meet the obligation without specialised hardware.

## 7.3 Comparison with Prior Work

This section positions the residual-gap result (RQ4) within the revisionist literature that argues modern kernel features have narrowed the advantage of kernel bypass. It discusses whether the measured gap supports or qualifies that position under cloud constraints, which prior bare-metal comparisons did not address.

## 7.4 Limitations

Three limitations bound the conclusions. The workload is synthetic, so the burstiness and protocol-level framing of real exchange feeds are not reproduced by the Poisson approximation. The public-cloud environment introduces a noisy-neighbour variable that placement-group co-location only partially controls. Finally, the PTP Hardware Clock imposes an irreducible measurement floor of approximately one microsecond, below which effects cannot be separated from noise. Each limitation constrains the precision of the findings rather than their direction, and each maps to a future-work extension in Chapter 8.
