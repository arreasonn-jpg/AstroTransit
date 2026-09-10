# TLS–MAP radius diagnostics

## Purpose

This diagnostic contract records the measured quantities needed to investigate the TLS-versus-fit radius discrepancy before scaling the known-planet campaign to N>=50. It is an observability layer, not a scientific acceptance gate.

For each target and sector with a cascade result, the report keeps these values separate:

- TLS period, duration, depth, `Rp/Rs`, and transit count;
- fitted `Rp/Rs` and derived planet radius;
- fitted impact parameter, `a/Rs`, limb-darkening coefficients, baseline, jitter, and residual RMS;
- catalog stellar radius and its source;
- detrending method and window;
- configured and observed median cadence;
- a direct local-median depth estimate from the detrended light curve;
- signed and fractional `Rp/Rs` differences.

Missing TLS or fit results are represented by explicit `not_evaluated_*` statuses. They are never converted to zero-valued measurements.

## Run

```bash
python scripts/validation/run_radius_diagnostics.py \
  --targets validation_runs/v1_known_planets/known_planets_10_v1/input/targets.json \
  --output-dir validation_runs/radius_diagnostics/tls_map_n10_v1
```

The command writes deterministic `radius_diagnostics.json` and `radius_diagnostics.csv` files. Campaign provenance and artifact hashes must be captured by the same clean-run workflow used for other frozen validation evidence.

## Interpretation boundary

The report intentionally defines no discrepancy threshold and produces no PASS/FAIL verdict. A measured difference can arise from detrending, catalog stellar-radius inputs, transit geometry, limb darkening, cadence treatment, or optimizer behavior. Numeric conclusions must come from a real frozen campaign; until then they remain pending measurements.
