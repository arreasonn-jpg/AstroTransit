# Real-noise injection-recovery v1

This directory freezes the campaign contract before any measured result exists.

## Scope

The campaign will inject box-shaped transits into post-detrending residuals from ten independently curated quiet TESS hosts. It measures detection-stage completeness on those selected real-noise hosts. It does not measure end-to-end preprocessing completeness or population completeness.

## Frozen grid

- Periods: 0.75, 2, 5, 10, 20 and 50 days.
- Depths: 200, 500, 1000 and 2000 ppm.
- Durations: 0.08 and 0.15 days.
- Orbital phases: 0.2 and 0.7.
- Scenarios per host: 96.
- Required hosts: 10.
- Planned trials after the host corpus is frozen: 960.
- Expanded-grid SHA-256: `a741396df50d6340bb73b4b09c874b32d08b149c8eb67ebe0799853a656ebb21`.

Periods through 20 days use the production `CascadeDetector`. The 50-day lane requires stitched multi-sector residuals and `LongPeriodTransitSearch`.

## Recovery semantics

The primary metric is strict period recovery within 2%. Harmonic-aware recovery using factors 1/3, 1/2, 1, 2 and 3 is secondary and must be reported separately. Detector exceptions count as failures; genuine data-availability outcomes are tracked separately and excluded from denominators.

Completeness must be reported by period bin, depth, duration and host-noise bin. Aggregate-only reporting is insufficient.

## Current status

`PENDING DATA`: the quiet-host corpus is not frozen. No completeness number may be published from this contract.

A host cannot be called quiet merely because its class is unknown. Each host must have real SPOC 120-second data, no TOI/TFOP history at the frozen snapshot, no pre-injection pipeline candidate, at least 20 days of valid baseline, finite stellar radius/mass and recorded residual-noise/variability metrics.

Synthetic white noise and unmasked known-planet hosts are forbidden substitutes.

## Next operations

1. Curate and freeze `input/quiet_hosts.json` with provenance and availability checks.
2. Implement the production-detector runner against the frozen contract.
3. Execute sharded trials and freeze the required outputs.
4. Only then change the campaign status from `PENDING DATA/PENDING RUN` to a measured state.
