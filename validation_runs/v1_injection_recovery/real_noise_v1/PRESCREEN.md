# Quiet-host prescreen operation

This branch adds a one-time GitHub Actions workflow that attempts to freeze ten real-TESS hosts for the injection-recovery campaign.

The candidate order comes from `benchmarks/discovery_targets_v4_small_cool_200_dedup.csv`. Every target present in the frozen TFOP disposition corpus is excluded before network work. The screen then uses the first and last catalog sectors for each remaining candidate, requires at least 20 days of valid data in both, queries finite TIC radius and mass, preprocesses real SPOC 120-second light curves and rejects any target for which the production cascade produces a pre-injection candidate.

A successful run writes `input/quiet_hosts.json`, the full prescreen audit and an environment manifest, advances the contract only to `PENDING RUN`, and removes the one-time workflow. An unsuccessful run uploads its partial audit but does not freeze a corpus.

The selected hosts are deterministic conditional on the frozen inputs and data products, but they are not a population-representative quiet-star sample. They are valid only as selected real-noise hosts for the scoped detection-stage injection campaign.

The first measured pass screened 30 deterministic candidates and accepted 7/10 required hosts. The criteria remain unchanged. The follow-up pass expands only the candidate limit to 60 so that three additional qualifying hosts can be found without relabelling, substituting synthetic data or weakening the pre-injection gate.
