# Release metadata policy

AstroTransit source control contains code, tests, benchmark ground truth and
small provenance metadata only. ZIP archives, extracted release bundles,
figures, Parquet campaign snapshots and logs are **not source files** and must
be published through a tagged GitHub Release or Zenodo.

The current repository cleanup removed the previously tracked contents of
`release/` and `campaign_runs/`. The historical bundles are listed in
`manifests/archive_inventory.json`; their binary payloads are intentionally not
recreated here. A release is reproducible only when the external artifact's
SHA-256 is recorded in `checksums/` and the release tag, DOI and environment
manifest are recorded in the release notes.

## Required release metadata

1. `manifests/archive_inventory.json` — artifact name, external location and
   publication state.
2. `checksums/<tag>.sha256` — SHA-256 of the externally published archive,
   generated from the final archive rather than a Git LFS pointer.
3. `release_notes/<tag>.md` — scope, pipeline version, config hash, commit,
   environment manifest, DOI/URL and scientific limitations.
4. `release_notes/candidate_disclaimer.md` — binding policy: releases are
   candidate lists, not peer-reviewed discoveries. Any release note listing
   novel candidates must embed the disclaimer sentence, the ExoFOP/TESS FOP
   submission status per target, and the "no peer review has taken place"
   statement.

Never add a manual `fpp: 0.0` value to a release report. If no calibrated FPP
was computed, use JSON `null`, `fpp_method: "not_estimated"` and explain the
limitation in the release note.
