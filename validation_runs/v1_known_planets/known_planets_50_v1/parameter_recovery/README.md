# N=50 parameter-recovery evidence

This report is a deterministic post-processing analysis of the frozen availability-aware N=50 known-target campaign. It does not rerun TESS retrieval or the pipeline.

## Failure-inclusive results — 46 evaluable targets

| Parameter | Bias | Scatter | RMSE | MAE | Median absolute relative error |
|---|---:|---:|---:|---:|---:|
| Period (days) | +0.307940 | 2.768195 | 2.785271 | 1.301592 | 0.2052% |
| Radius (R_Earth) | -0.976808 | 4.219685 | 4.331270 | 2.169259 | 20.6084% |

These values include aliases and catastrophic recovery failures. Their means and RMSE values are therefore intentionally failure-sensitive.

## Conditional within-tolerance results

| Parameter | N | Bias | Scatter | RMSE | MAE | Median absolute relative error |
|---|---:|---:|---:|---:|---:|---:|
| Period (days) | 32 | +0.005192 | 0.030390 | 0.030830 | 0.009981 | 0.0245% |
| Radius (R_Earth) | 23 | -0.122818 | 0.618107 | 0.630191 | 0.386722 | 3.0760% |

Conditional rows describe only targets already inside the frozen 2% period or 20% radius tolerance. They are diagnostic and must not be presented as completeness.

## Difficulty stratification

- Easy: N=18; period within tolerance 16/18, radius 12/18.
- Medium: N=15; period within tolerance 10/15, radius 9/15.
- Hard: N=13; period within tolerance 6/13, radius 2/13.

The radius result degrades strongly on the hard subset. The easy-subset radius RMSE is also large because several large-radius targets are severely underestimated, so the labels are not monotonic proxies for radius recoverability.

## Unsupported measurements

- Credible-interval coverage: `not_evaluated_no_intervals`.
- Reliability-stratified radius performance: not available in the frozen aggregate.

The campaign contains point estimates but no per-target credible intervals. Coverage must remain null. A separate diagnostic artifact is required before linking radius errors to the reliability policy.

## Reproduction

```bash
python scripts/validation/analyze_parameter_recovery.py \
  --source validation_runs/v1_known_planets/known_planets_50_v1/aggregate/targets.csv \
  --output /tmp/parameter-recovery.json
```

Canonical report hash: `6b6c12a34d3c9f3443c6b107593331c781dad8da3e327f48a7dd8d83c6de9ddd`.
