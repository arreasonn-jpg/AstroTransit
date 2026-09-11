# Radius reliability policy

AstroTransit does not treat every converged MAP radius as a calibrated scientific estimate.

The policy adds mechanical, evidence-preserving labels:

- `boundary_constrained`: `Rp/Rs` reached its configured optimizer bound.
- `grazing_geometry`: the fitted geometry satisfies `b > 1 - Rp/Rs`.
- `other_optimizer_boundary_contact`: a non-radius optimizer coordinate reached a bound.
- `uncalibrated_no_detected_flag`: none of the above flags was found; this is deliberately not named “reliable”.

Reasons and booleans are serialized separately so downstream validation can stratify results without parsing prose.

## Claim boundary

These labels do not estimate posterior coverage, population accuracy, or false-positive probability. They prevent boundary-constrained and grazing solutions from being silently presented as ordinary radius measurements. Calibrated reliability requires parameter-recovery and injection-recovery studies.
