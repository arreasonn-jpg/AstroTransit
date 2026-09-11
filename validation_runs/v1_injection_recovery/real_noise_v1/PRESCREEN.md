# Quiet-host prescreen operation

This branch adds a one-time manual GitHub Actions workflow that attempts to freeze ten real-TESS hosts for the injection-recovery campaign.

The candidate order comes from `benchmarks/discovery_targets_v4_small_cool_200_dedup.csv`. Every target present in the frozen TFOP disposition corpus is excluded before network work. The screen then uses the first and last catalog sectors for each remaining candidate, requires at least 20 days of valid data in both, queries finite TIC radius and mass, preprocesses real SPOC 120-second light curves and rejects any target for which the production cascade produces a pre-injection candidate.

A successful run writes `input/quiet_hosts.json`, the full prescreen audit and an environment manifest, advances the contract only to `PENDING RUN`, and removes the one-time workflow. An unsuccessful run uploads its partial audit but does not freeze a corpus.

The selected hosts are deterministic conditional on the frozen inputs and data products, but they are not a population-representative quiet-star sample. They are valid only as selected real-noise hosts for the scoped detection-stage injection campaign.

Run `Quiet host prescreen v1` from the Actions tab on branch `validation/quiet-host-prescreen-v1`. Start with `candidate_limit=30`. If fewer than ten hosts pass, inspect the uploaded audit before expanding the limit; do not relax the scientific acceptance criteria merely to reach ten.
