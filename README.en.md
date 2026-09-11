# AstroTransit

**Türkçe: [README.md](README.md) | English: README.en.md**

AstroTransit is a modular Python research package for **transit candidate
detection, vetting and physical characterization** in TESS light curves. It
writes its results into a durable output contract with a full chain of
evidence (provenance).

Positioning: **a TESS-first transit discovery platform with an evolving
JWST follow-up interface.** The scientific backbone is on the TESS side; the
JWST product flow is still at the `JWSTProductContract` level (a metadata
search does not count as a processed product).

## Features

- TESS light curve search and quality cleaning via MAST/Lightkurve
- Normalization, gap/segment detection and Wotan detrending
- BLS → TLS cascaded transit detection
- Multi-sector stitching and a 20–500 day long-period / single-transit scan
- MAP modeling; optional PyMC/exoplanet MCMC for selected strong candidates
- SNR, vetting, false-positive **risk proxy** (heuristic) and candidate-class evaluation
- Configurable Earth-similarity profiles (weighted similarity **index**)
- Separation of photometric candidate, Earth-twin candidate and follow-up-confirmed Earth twin
- Similarity, detection confidence and FPP proxy reported as **separate** fields
- JSON, Parquet and CSV output contract (schema v1.7, migration tool)
- Known-target performance reports, injection-recovery and FPP benchmark helpers (`astrotransit/validation`)
- CLI and Streamlit dashboard

## Installation

Recommended Python version is 3.11 or newer (CI tests 3.11–3.13):

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Optional dependencies for MCMC/JWST:

```bash
python -m pip install -e ".[jwst,modeling]"
```

No token is required for anonymous MAST access. For optional credentials,
copy `.env.example` and configure it in your local environment; never commit
real secrets to Git.

## Usage

```bash
astrotransit version
astrotransit single "TIC 261136679" --force-map --no-viz
astrotransit batch benchmarks/pilot_targets.csv --force-map --no-viz
astrotransit earth-search targets.csv --min-similarity 90 --limit 50 \
  --output outputs/earth_search_ranked.json
astrotransit benchmark --max 5 \
  --output outputs/benchmark/benchmark_performance.json
```

Settings are loaded from `configs/default.toml`. To supply a different file
use `--config configs/wsl_mcmc.toml`.

The `earth-search` command scans a list of TESS targets in batch and ranks
candidates by the similarity index; `--min-similarity` is a **ranking
filter**, not a validation threshold. In the output, `similarity_score`,
`detection_confidence` and `false_positive_probability` are kept as
**separate fields**; `priority_score` is only an observation priority, not a
validation probability. For follow-up validation a `FollowupEvidence` record
with an observation identity is required; a bare `confirmed=true` value does
not count as Earth-twin confirmation. For existing JSON/Parquet candidates,
`OutputManager.update_followup()` binds a follow-up result to the same
target/sector row. This can also be done from the CLI:

```bash
astrotransit followup-update "TIC 123456789" 14 followup.json \
  --output-dir outputs
```

Dashboard:

```bash
streamlit run dashboard/app.py
```

## Scientific claims and their limits

This section formally defines what AstroTransit's outputs mean; do not relay
results without reading it.

- **Earth similarity is not a probability.** `earth_similarity_score` is a
  weighted Gaussian similarity index (0–100) against the Earth reference. It
  carries no information about habitability, atmosphere or the probability of
  life; the weights are v1.0 heuristic defaults and have not been calibrated
  on a labelled population. The phrase "94.2 similarity" must not be read as
  "94% Earth-like". Details: [`docs/output_schema.md`](docs/output_schema.md)
  → "Epistemic limits".
- **FPP is not a calibrated Bayesian probability.** The
  `false_positive_probability` field is a **heuristic risk proxy** derived
  from weighted votes of vetting tests (odd/even, secondary eclipse, depth
  limit, stellar variability, duration-period physical consistency,
  symmetry, data completeness); it contains no background EB population,
  occurrence prior or calibration. The method identity is written into the
  output as `fpp_method`. For a calibrated FPP, run
  `astrotransit/validation/fpp_benchmark.py` (Brier score, precision/recall)
  on labelled data.
- **`confirmed` is not produced without a chain of evidence.**
  `CONFIRMED_EARTH_TWIN` is formed only when a valid `FollowupEvidence`
  (source + observation identity) and strict similarity coincide. The
  `confirmed` field of the TESS cascade or a bare `{"confirmed": true}`
  payload does not count as validation.
- **Long-period / single-transit results are in the `PERIOD_ESTIMATED`
  epistemic state.** Do not conflate them with `DETECTED`; the uncertainty is
  carried in the `long_period_identifiability` and `period_err` fields.
- **A "candidate" label outside the catalog is not a discovery claim.** A
  target with no TOI/Archive match is **flagged** as a "novel candidate"; it
  is not presented as a "discovery" until independent photometric/astrometric
  validation (ExoFOP, TESS FOP process) is complete.

## MAP vs MCMC: which one when?

| Situation | Method | What it gives |
|-----------|--------|---------------|
| Bulk discovery scan (hundreds–thousands of targets) | **MAP** | Single-point optimum: most probable parameter values, fast |
| Selected strong candidates (limited number) | **MCMC** | **Distribution** of parameter space: arviz R-hat/ESS, posterior credible intervals |

A result obtained with `--force-map` is a **single-point estimate of the
posterior, not a distribution of fitted planet parameters**. If a critical
parameter such as the period was not sampled in the MCMC, it is processed as
`period_err_source=fixed_in_mcmc` and the uncertainty comes from the MAP
reference. Which candidate gets MCMC is decided in the `scripts/followup/`
workflow; MCMC is computationally impractical in bulk scans.

## Measured validation results

The first availability-aware N=50 real-TESS known-target campaign is complete.
Fifty targets were selected; 46 were evaluated with measured sectors and four
had no measured sector, so they were excluded from recovery denominators.

| Metric | Measured result |
|---|---:|
| Detection on evaluable selected targets | 46/46 (100.0%) |
| Joint period + radius recovery | 21/46 (45.6522%) |
| Period recovery | 32/46 (69.5652%) |
| Radius recovery | 23/46 (50.0000%) |
| Sector consistency | 20/38 (52.6316%) |
| False-positive rejection | Not evaluated |

The 46/46 value is conditional detection on the **selected, evaluable
known-target subset**. It is not population recall, completeness or precision.
For immutable evidence, hashes and remaining gates, see
[`docs/measured_validation_results.md`](docs/measured_validation_results.md).

## Validation status and roadmap

AstroTransit's current state: **a serious discovery/characterization framework
with a measured >=50 selected known-target campaign, but its scientific
validation program (injection completeness, false-positive/quiet controls,
calibrated FPP and blind testing) is not yet a fully closed loop.** This is
reported as a deliberate limit.

- Known-target performance report: `astrotransit/validation/benchmark_report.py`;
  when `astrotransit benchmark` runs, per-target expected/recovered period and
  radius, detection recall, parameter errors and sector consistency are
  written as JSON/CSV under `outputs/benchmark/`. The mere existence of the
  ground-truth file is not a measurement.
- Injection-recovery infrastructure: `astrotransit/validation/injection_recovery.py`
  (completeness, period-error measurements)
- FPP proxy calibration: `astrotransit/validation/fpp_benchmark.py`
  (Brier score, false-positive recall, planet precision). Without labelled
  data the FPP value stays `null`/`not_available`; `0.0` is never used as a
  stand-in for an unknown value.
- Benchmark CLI: `astrotransit benchmark`
- The 8 validation gates needed for the closed loop (injection-recovery,
  known-planet recovery, known-FP rejection, cross-sector consistency,
  parameter recovery, FPP calibration, similarity-weight sensitivity
  analysis, full provenance): [`docs/validation.md`](docs/validation.md)

**Reference candidate (end-to-end example):** TIC 417860263 / HD 224792.
The flagship non-TOI reference candidate with no match in the TOI/Archive
catalogs, processed end-to-end by the pipeline: P ≈ 2.854 days,
Rp/R* ≈ 0.0251 (~3.07 R⊕), SNR ≈ 47.9; MAP + WSL MCMC (r-hat 1.04, 0
divergences). The evidence package for reproducibility is kept on a GitHub
Release/Zenodo; no large ZIP or campaign output is added to the Git source
tree. No calibrated FPP was computed for TIC 417860263, so no FPP claim must
be made; the old manual `fpp: 0.0` summary is invalid. The release metadata
policy is documented in
[`release/release_notes/reproducibility_policy.md`](release/release_notes/reproducibility_policy.md).

## Outputs

By default under `outputs/`:

- `json/`: per-candidate scientific report
- `parquet/`: filterable bulk catalog
- `csv/`: summary export
- `figures/`: diagnostic plots

For the data model and field descriptions see
[`docs/output_schema.md`](docs/output_schema.md) (read the "Epistemic
limits" section first) and [`docs/architecture.md`](docs/architecture.md)
for the architecture.

## Tests

```bash
python -m pytest -q
```

Instead of integration flows that download data from the network, tests use
synthetic light curves. In environments without MAST access the client
reports the error explicitly; the cache is only kept under `.cache/`.

## Reproducibility

Recommended provenance set for every run:

- Git commit + SHA-256 of the config file (together with the version from `astrotransit version`)
- Environment manifest: `python scripts/maintenance/make_environment_manifest.py --output env_manifest.json`
  (Python, pip freeze, commit, config hash, timestamp)
- Reference dependency lock: `envs/requirements.lock` (Python 3.11 snapshot;
  regeneration command at the top of the file)

## License

[MIT](LICENSE) — free use for scientific collaboration and independent
reproduction.
