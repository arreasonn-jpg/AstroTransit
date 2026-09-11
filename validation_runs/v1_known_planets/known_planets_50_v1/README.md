# Availability-aware N=50 known-planet benchmark

This directory freezes the first selected N=50 real-TESS known-planet campaign.

## Execution

- Selected targets: 50
- Evaluated targets: 46
- Not evaluated because no measured sector was available: 4
- Evaluated aggregate: 46 independent one-target shards
- Pipeline: AstroTransit 0.3.0
- Python: 3.11.16
- Seed: 42
- Frozen input SHA-256: `c90de0ff053026f16781a8b8ffcc3e35088cae1385a2138a62e6f93afd54673a`
- Aggregate canonical output hash: `6efcb7834f8e310744a76c7ffec0c8b46fc20622b49e7d9203a0c1d123e889d0`

## Data availability

The following selected targets produced no measured sector and are excluded from all recovery denominators:

- TIC 4610830
- TIC 8348911
- TIC 14570099
- TIC 17307715

They are retained as explicit data-availability outcomes, not converted into non-detections or recovery failures.

## Measured results on 46 evaluable targets

| Metric | Measured value |
|---|---:|
| Detection | 46/46 |
| Joint period + radius recovery | 21/46 (0.456522) |
| Period recovery | 32/46 (0.695652) |
| Radius recovery | 23/46 (0.500000) |
| Sector consistency | 20/38 (0.526316) |
| False-positive rejection | Not evaluated |

## Interpretation boundary

The measured detection value is conditional on the selected, evaluable known-target set and must not be reported as general population recall. Four corpus targets were not evaluable. This campaign does not measure false-positive rejection, injection-recovery completeness, calibrated precision, survey completeness, or population-level radius accuracy. The reliability labels introduced in PR #19 remain diagnostic; calibrated radius coverage is still pending.
