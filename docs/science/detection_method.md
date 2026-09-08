# Detection method

## Method
AstroTransit runs TLS/BLS-backed searches on cleaned, normalized light curves.
The reported detection is a signal candidate, not a planet confirmation.

## Assumptions
- Cadence and gaps are retained during preprocessing.
- Detection thresholds are configuration values and must be benchmarked.
- A single-sector signal remains a `single_sector_candidate`.

## Input / output
Input is time, flux, uncertainty and sector metadata. Output includes period,
depth, SNR, detection status, claim status and provenance.

## Failure modes
`NO_DATA`, `INSUFFICIENT_BASELINE`, `HIGH_SYSTEMATICS`, `NO_TRANSIT` and
`AMBIGUOUS_SINGLE_TRANSIT` are explicit outcomes.

## Test / reference
Detection is evaluated with known-target and injection-recovery benchmarks;
TLS/BLS implementation references are recorded in `docs/science/references.md`.
