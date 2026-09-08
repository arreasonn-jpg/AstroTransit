# Candidate-list disclaimer and independent review policy

## What AstroTransit releases are and are not

AstroTransit publishes **candidate lists and analysis products**, never
peer-reviewed discovery claims. A release that contains targets without a
TOI/ExoFOP archive match is a **novel-candidate flag**, not a discovery.

- The TESS transit-cascade `confirmed` field, a bare `{"confirmed": true}`
  payload, a high `earth_similarity_score` or a low FPP proxy value is
  **photometric evidence at most** (`PHOTOMETRIC_PLANET_CANDIDATE` in
  `astrotransit.validation.claims`); the codebase will not promote it to
  `CONFIRMED_PLANET` without recorded follow-up evidence.
- Zenodo and GitHub Releases provide **artifact provenance** (DOI, SHA-256,
  environment manifest). They are not a review process: a DOI on a release
  does not make its candidate list peer-reviewed.
- `fpp` values in releases are heuristic risk proxies unless the release
  explicitly records a calibrated labelled benchmark (see
  `reproducibility_policy.md`). Missing FPP is `null` +
  `fpp_method: "not_estimated"`, never `0.0`.

## Independent review plan for novel-candidate claims

Before any AstroTransit novel-candidate claim is presented as a discovery:

1. **ExoFOP / TESS FOP:** the target is submitted to the Exoplanet Follow-up
   Observing Program (or the TESS FOP for non-TESS products) for
   independent vetting; working-group disposition (`CN`, `CP`, `FP`, `VF`)
   is recorded in the target's release note.
2. **Independent photometric/astrometric confirmation:** at least one
   follow-up observation from an instrument and team not involved in the
   original detection is archived with a stable observation ID; the result
   is attached via `FollowupEvidence` and `astrotransit followup-update`.
3. **Claim status upgrade:** only then may the claim level move along the
   `claims.py` hierarchy toward `VALIDATED_PLANET` / `CONFIRMED_PLANET`.
   Until step 3, all external materials must carry the sentence:

   > "This is a candidate list produced by the AstroTransit pipeline, not a
   > peer-reviewed discovery. Independent follow-up (ExoFOP/TESS FOP) is
   > required before any discovery claim."

## Release-note requirement

Every release note that lists novel or previously unmatched candidates must
contain, verbatim or equivalent:

- the disclaimer sentence above;
- the ExoFOP/TFOP submission status for each novel target (submitted /
  pending / no disposition yet);
- the explicit statement that no peer review has taken place for that
  release.

A release that omits this block must not label any target as a discovery,
validated planet or confirmed planet.
