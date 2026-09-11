# MAP physical constraints and boundary reporting

The frozen N=10 TLS–MAP diagnostic found that the largest radius differences were concentrated in high-impact/grazing solutions and frequently accompanied by non-physical quadratic limb-darkening coefficients or `Rp/Rs` boundary contact.

## Limb-darkening parameterization

MAP now optimizes quadratic limb darkening through the Kipping unit-square coordinates:

- `q1 = (u1 + u2)^2`
- `q2 = u1 / (2 (u1 + u2))`

with `q1, q2` constrained to `[0, 1]`. The inverse transformation guarantees coefficients in the physical quadratic limb-darkening region. Public fit results continue to report `u1` and `u2` for compatibility and interpretation.

## Boundary evidence

Every MAP result reports:

- `optimizer_boundary_hit`: whether any optimized coordinate reached a bound;
- `optimizer_boundary_hits`: stable `parameter:lower|upper` labels;
- `limb_darkening_parameterization`: the parameterization used.

A boundary hit is diagnostic evidence, not automatic fit failure. In particular, grazing transits may remain weakly identified even after the limb-darkening constraint is corrected.

## Validation sequence

1. Merge the physical parameterization and boundary-reporting change.
2. Rerun the same frozen N=10 corpus with clean provenance.
3. Compare v1 and v2 without changing the corpus or interpreting either run as a general parameter-recovery claim.
4. Decide whether additional geometry priors or cadence integration are justified before N>=50.
