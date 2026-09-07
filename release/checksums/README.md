# External artifact checksums

Store one SHA-256 line per published release archive here, for example:

```text
<sha256>  AstroTransit_v0.3.0_zenodo.zip
```

Do not calculate a checksum from a Git LFS pointer. Generate it from the final
archive downloaded from GitHub Releases or Zenodo and record the corresponding
tag/DOI in `release_notes/`.
