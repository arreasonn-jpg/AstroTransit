# AstroTransit L1 Discovery Program: Two Research Tracks

**Status:** Research specification and first numerical geometry component  
**Model scope:** Star--planet L1, circular restricted three-body problem (CR3BP)

## Scientific objectives

AstroTransit will investigate two distinct hypotheses. They share the star--planet L1 geometry but must not share assumptions about the candidate's mass, physical nature, habitability, or ability to station-keep.

### Track 1: Earth-like habitable planet near star--planet L1

The ambitious target is a near-Earth-twin candidate associated with the L1 region of a separate host-star/planet pair. Earth similarity is not a substitute for habitability: the assessment must separately consider radius, mass, incident stellar flux, atmosphere, temperature constraints, water indicators where measurable, and stellar activity.

The host star--planet pair defines the L1 reference geometry. L1 is a gravitational equilibrium point, not a habitable zone by definition; the candidate's local stellar irradiance must be calculated and compared with an explicitly stated habitable-zone model. A candidate with non-negligible mass cannot be treated as a massless test particle at L1: its gravity changes the three-body configuration. Any candidate-scale interpretation therefore requires a finite-mass N-body model and a stability analysis, not only the CR3BP equilibrium calculation.

A body exactly at the ideal L1 equilibrium is not a stable free equilibrium. The research must test whether a physically admissible nearby trajectory exists and persists under perturbations. A photometric signal alone cannot establish L1 occupancy.

### Track 2: Controlled satellite or megastructure near star--planet L1

The host planet's size is not a selection criterion. Candidate structures may be natural satellites, artificial satellites, stations, or larger engineered structures. The key hypothesis is that the object or structure occupies an L1-associated trajectory whose motion is actively controlled or corrected.

Halo and Lissajous trajectories are relevant dynamical families around L1. They are not themselves proof of passive long-term stability. A controlled structure may require station-keeping; the model must explicitly distinguish uncontrolled dynamics from control input and propellant/energy constraints.

Potential observables include repeatable transit residuals, additional photometric events, transit timing/duration perturbations, phase-correlated signals, and (where available) independent radial-velocity or imaging constraints. None is a unique technosignature by itself. Instrumental effects, stellar variability, eclipsing binaries, background sources, and ordinary planetary companions must be tested as alternatives.

## Geometry model implemented in Phase 1

`astrotransit.dynamics.l1.StarPlanetCR3BP` solves the collinear L1 equilibrium for two point-mass primaries on a circular orbit. It reports normalized barycentric and primary/secondary distances, plus dimensional distances for a user-supplied separation.

The model assumes:
- circular star--planet orbit;
- point-mass primaries;
- constant separation;
- negligible candidate mass for the geometry calculation;
- rotating-frame equilibrium.

It does **not** calculate:
- a finite-mass candidate's orbit;
- halo/Lissajous initial conditions or propagation;
- long-term stability or escape time;
- station-keeping control effort;
- habitability;
- detection significance or candidate confirmation.

Those are explicit subsequent work packages, not implicit capabilities.

## Development sequence

1. **L1 geometry foundation:** validated L1 root solver and physical input checks.
2. **CR3BP propagation:** rotating-frame equations, Jacobi constant, equilibrium and trajectory regression tests.
3. **Track 1 finite-mass dynamics:** add the candidate as a gravitating body; integrate and perturb the full system; quantify boundedness and collision/escape outcomes.
4. **Track 2 controlled dynamics:** add explicit control acceleration, station-keeping policy, control effort, and uncontrolled comparison.
5. **Observational forward models:** predict transit/residual signatures for each track, including viewing geometry and cadence.
6. **Search and validation:** inject synthetic signals into development data, measure completeness and false positives, then perform independent follow-up checks.
7. **Evidence-gated candidate reports:** preserve inputs, catalog/data provenance, model version, parameter uncertainty, random seed, and reproducible commands.

## Claim and evidence rules

- `L1_GEOMETRY_COMPUTED` means only that the idealized two-primary L1 point was calculated.
- `DYNAMICALLY_PLAUSIBLE` requires a documented trajectory integration and perturbation study with stated duration and tolerances.
- `CONTROL_REQUIRED` requires a comparison showing that the uncontrolled trajectory fails the declared bound while a specified control law maintains it within that bound.
- `OBSERVATIONAL_CANDIDATE` requires repeatable data evidence and explicit false-positive tests.
- `EARTH_ANALOG_CANDIDATE` requires measured Earth-relevant properties and completeness reporting; it is not a habitability or life claim.
- `HABITABILITY_SUPPORTED` requires independent support for the relevant environmental conditions and cannot be assigned from an Earth-similarity score alone.
- `CONFIRMED` is reserved for independent follow-up evidence.

The blind holdout remains untouched during development. All tuning and injection-recovery work must use development data until the pre-registered final validation stage.
