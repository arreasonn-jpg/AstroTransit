# Reproducibility and release note policy

## Source versus artifact storage

The Git repository is the source and validation implementation. Generated
campaign results, figures, extracted bundles and ZIP archives belong in an
immutable external artifact service (GitHub Releases or Zenodo). The repository
keeps only manifests, checksums and release notes so a checkout remains small
and code review remains meaningful.

## Minimum release record

Every external release must record:

- AstroTransit version and Git commit;
- configuration path and SHA-256;
- Python version and `envs/requirements.lock` (or an equivalent environment
  manifest);
- benchmark report path and seed, when a benchmark was run;
- external artifact URL and DOI, if available;
- SHA-256 calculated from the final archive;
- scientific limitations and unmeasured gates.

`benchmarks/verified_targets.json` is a ground-truth corpus, not a performance
report. A release may claim measured known-target recovery only when the
`astrotransit benchmark` command has produced the JSON/CSV performance report.

## FPP policy

The vetting FPP value is a heuristic risk proxy unless an explicitly calibrated
labeled benchmark is supplied. A missing or uncomputed FPP is represented as
JSON `null` with `fpp_method: "not_estimated"`; it must never be rendered as
`0.0`. In particular, the former TIC 417860263 manually entered `fpp: 0.0`
claim is invalidated by this policy.
