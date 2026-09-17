# Measured validation results

Only immutable, provenance-backed campaign outputs are numeric evidence here. `PENDING DATA` and `PENDING RUN` are never converted into scores.

## Known targets — availability-aware N=50 campaign

| Quantity | Measured result |
|---|---:|
| Selected known targets | 50 |
| Evaluable targets | 46 |
| Not evaluated: no measured sector | 4 |
| Detection on evaluable selected subset | 46/46 (100.0%) |
| Joint period + radius recovery | 21/46 (45.6522%) |
| Period recovery | 32/46 (69.5652%) |
| Radius recovery | 23/46 (50.0000%) |
| Sector consistency | 20/38 (52.6316%) |
| False-positive rejection | Not evaluated |

The four unavailable targets are TIC 4610830, TIC 8348911, TIC 14570099 and TIC 17307715. They are excluded from recovery denominators and are not counted as non-detections.

Evidence: [`validation_runs/v1_known_planets/known_planets_50_v1/`](../validation_runs/v1_known_planets/known_planets_50_v1/)

Frozen input SHA-256: `c90de0ff053026f16781a8b8ffcc3e35088cae1385a2138a62e6f93afd54673a`

Aggregate canonical output hash: `6efcb7834f8e310744a76c7ffec0c8b46fc20622b49e7d9203a0c1d123e889d0`

## Real-noise injection recovery — 960 planned trials

The frozen v1 campaign injected box transits after detrending into ten selected real-TESS quiet-host light curves. It recorded all 960 planned trial identities. Availability and detector outcomes remain separate.

| Quantity | Measured result |
|---|---:|
| Planned and recorded trials | 960/960 |
| Evaluable trials | 888 |
| Not evaluated: no observed injected cadence | 72 |
| Data-access failures | 0 |
| Detector errors | 0 |
| Strict period recovery | 450/888 (50.6757%) |
| Strict recovery 95% Wilson interval | 47.3915%–53.9540% |
| Harmonic-aware period recovery | 466/888 (52.4775%) |
| Harmonic-only recoveries | 16 |

### Recovery by execution lane

| Lane | Evaluable/planned | Strict recovery | Harmonic-aware recovery |
|---|---:|---:|---:|
| Cascade single-sector, P ≤ 20 d | 800/800 | 449/800 (56.1250%) | 465/800 (58.1250%) |
| Stitched long-period, P = 50 d | 88/160 | 1/88 (1.1364%) | 1/88 (1.1364%) |

### Recovery by period bin

| Period bin | Strict recovery | Harmonic-aware recovery |
|---|---:|---:|
| Short, P < 5 d | 265/320 (82.8125%) | 271/320 (84.6875%) |
| Mid, 5 ≤ P ≤ 20 d | 184/480 (38.3333%) | 194/480 (40.4167%) |
| Long, P = 50 d | 1/88 (1.1364%) | 1/88 (1.1364%) |

### Recovery by injected depth

| Depth | Strict recovery | Harmonic-aware recovery |
|---|---:|---:|
| 200 ppm | 41/222 (18.4685%) | 44/222 (19.8198%) |
| 500 ppm | 110/222 (49.5495%) | 114/222 (51.3514%) |
| 1000 ppm | 147/222 (66.2162%) | 152/222 (68.4685%) |
| 2000 ppm | 152/222 (68.4685%) | 156/222 (70.2703%) |

Evidence: [`validation_runs/v1_injection_recovery/real_noise_v1/`](../validation_runs/v1_injection_recovery/real_noise_v1/)

Frozen host-corpus SHA-256: `8175058b8b519bffbff8a37a8c7978bb67ad8f1e03b777a9568ed35f21ffbe42`

Frozen grid SHA-256: `a741396df50d6340bb73b4b09c874b32d08b149c8eb67ebe0799853a656ebb21`

Trials SHA-256: `6dff856f848b89b17b14dca33a938ab2bc13ae5830fd25795998ed4dea199a47`

Report SHA-256: `86eb94c77b15c60d7e91de0ca2797e3f87cc64adf3b8ac897ed8b6a7220493d9`

Canonical combined output SHA-256: `c142612b64fb888f76725b45df5e494b3ac8186804c3238b1a8df56a868ba810`

## Adversarial and blind-holdout corpora

Both gates have a frozen corpus and a pre-declared contract. The adversarial grid
has now been measured on this machine (it needs no external data); the blind
holdout still has **no** measured statistic because it needs real light curves
that this machine cannot fetch. In neither case does a number exist that the
contract was written around: `final_acceptance_audit` reads the report at the
canonical gate path and keeps both gates open.

### `adversarial_false_positives` (synthetic) — measured, gate left open

`validation_runs/final_acceptance_v1/adversarial_fp/corpus_manifest.json` freezes
56 scenarios: six morphologies chosen to confront one vetting test each
(`eclipsing_binary_v`, `grazing_eclipsing_binary`, `blended_diluted_eb`,
`eb_with_secondary_eclipse`, `odd_even_alternating_eb`, `spot_modulated_dip`) plus
a `planetary_control` family that must mostly be *accepted*, so "reject
everything" cannot score as success. Shapes are analytic trapezoid/V
(`steepness=1` triangle, `steepness→0` box) on a uniform 600 s cadence with
seeded Gaussian noise; no limb darkening, no gaps, no `batman` dependency.
Grid identity: `2e2b434d5d609883c3f3803dd24950f595a1482e523e8bf71d04d214bd4ace20`.

The harness runs the production wiring — MAP fit, then
`evaluate(detrended, candidate, fit_result)` exactly as
`astrotransit/pipelines/tess_pipeline.py` does — and the report pins the code it
ran from (`provenance.git_commit = 79e06e16…`). All 56 scenarios produced a row;
zero errors. Report SHA-256: `8536412586cf2bdbc0bb651c4ed7e11520d1fb394b3798f4b10d97dd3a39af6e`.

| Family (8 scenarios each) | Rejection rate | 95% CI | Rejected at |
|---|---|---|---|
| `blended_diluted_eb` | 0.875 | 0.529–0.978 | detection 7 |
| `spot_modulated_dip` | 0.500 | 0.215–0.785 | cascade 3, vetting 1 |
| `grazing_eclipsing_binary` | 0.250 | 0.071–0.591 | cascade 2 |
| `eclipsing_binary_v` | 0.000 | 0.000–0.324 | — |
| `eb_with_secondary_eclipse` | 0.000 | 0.000–0.324 | — |
| `odd_even_alternating_eb` | 0.000 | 0.000–0.324 | — |
| `planetary_control` (acceptance) | 1.000 | 0.676–1.000 | — |

**Overall adversarial rejection 13/48 = 0.271 (95% CI 0.166–0.410)** against the
pre-declared floor of 0.80; by stage: detection 7, cascade 5, **vetting 1**,
anomaly 0. The gate therefore reports `status: pending_run`, lists five blocking
reasons, `aggregate`/`run` exit 3, and `final_acceptance_audit` marks 6 of the 20
checks failed. No floor was adjusted after seeing these numbers.

What the measurement does and does not say:

- The pipeline's rejection of these morphologies is overwhelmingly a
  **sensitivity** effect, not adjudication: the only family that clears its floor
  (`blended_diluted_eb`) is rejected because BLS finds no peak at 750–1800 ppm
  under 600 ppm noise, not because vetting recognised an EB. Reading 0.875 as
  vetting quality would be wrong, which is why the report attributes every
  rejection to a stage.
- Vetting essentially never fires here: 53 of 56 rows have zero failing vetting
  tests, and `false_positive_probability > 0` in 11 rows. Median injected-secondary
  measurement is 8.7 ppm (max 1792 ppm) against a test threshold of
  `0.5 × primary depth`, so the secondary-eclipse test cannot trigger on these
  shapes; `odd_even_mismatch` does respond directionally (alternating family
  median 0.84, max 2.65, vs control median 0.17) but stays below the 3σ
  threshold; `depth_limit` compares against `max_depth_ratio = 0.5`, i.e. 50%,
  so realistic 1–5% eclipses pass by construction.
- **Limitation of this wiring, recorded in the report:** the anomaly stage emitted
  no report for any scenario, so `rejected_at_anomaly` was structurally
  unreachable. The measured number covers detection + cascade + vetting; the
  repo's `quality/eb_coorbital_discriminator.py` and anomaly scorer are not part
  of the per-target quality path and are therefore not credited or blamed.
- 32 of 56 scenarios recovered the injected period within 2%; the rest are
  detector-side outcomes that the rejection attribution already accounts for.

Candidate follow-ups (owner decision, none applied here): add a morphology test
that measures ingress steepness / V-shape directly, compute the secondary-eclipse
and odd/even statistics from our own per-transit estimator instead of TLS's
standard-error ratio, or wire the existing EB/anomaly discriminator into
`QualityEvaluationPipeline`. Any of these changes the pipeline, so this gate must
be re-measured afterwards — the recorded `provenance.git_commit` makes a stale
number visible.

### `blind_domain_holdout` (real targets — corpus frozen offline, run pending)

`validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json` freezes
144 targets (72 planet / 72 false-positive) over five FOP-disposition strata
(`planet:CP` 37, `planet:KP` 35, `false_positive:FP` 42, `false_positive:APC` 20,
`false_positive:FA` 10). Membership is derived only from the `blind_test` partition
of `assign_split(seed=13)`, ranked by a seeded SHA-256 key, and **never** from a
detector output; 170 ids already touched by prior gates (FP run subset, quiet-sky
hosts, the FPP cohort, any committed row file) are removed before ranking.
Corpus identity: `3fd1e65a2ddc15d37c624571a5f39d7bdeae724609d427d7dfbc2e1320a0b1d2`.

22 pre-declared checks include `recall ≥ 0.5`, `false_positive_rate ≤ 0.6`,
`errors == 0`, `non_blind_rows == 0`, `detector_used_for_selection == false`,
`retrained == false` and per-stratum coverage. Unevaluated targets are blockers,
never dropped from a denominator, and a manifest whose hash or membership was
edited after the fact is refused (`holdout_manifest_self_inconsistent`,
`rows_not_in_frozen_corpus`, `corpus_rows_missing`).



## Interpretation boundaries

The known-target 46/46 value is conditional detection on the selected, evaluable known-target subset. It is not population recall, survey completeness or calibrated precision.

The injection-recovery values measure the detection stage after detrending on the frozen selected real-noise hosts. They are not population completeness or end-to-end preprocessing completeness. The selected ten hosts are not population representative. The 72 long-period scenarios with no injected cadence in an observed window are availability outcomes and are excluded from scientific denominators, not counted as detector failures.

The very low measured 50-day stitched recovery is a recorded pipeline limitation, not an availability-adjusted success. No acceptance threshold was frozen before this run, so the campaign is `MEASURED`, not retroactively declared `PASS`.

The adversarial 0.271 is a rejection rate **of six declared morphologies under one
specific wiring** (synthetic trapezoid/V shapes, uniform cadence, single-sector
27 d baseline, no anomaly stage), not "the pipeline rejects 27% of false positives".
Its Wilson interval (0.166-0.410) is wide because each family holds 8 scenarios; the
control family's 8/8 acceptance is what stops the low number from being explained by
a uniformly rejecting pipeline.

## Remaining gates

| Validation area | Status |
|---|---|
| Parameter recovery | N=50 period/radius bias, scatter and RMSE measured; injection-trial parameter-error aggregation and interval coverage pending |
| Injection recovery | 960/960 trial records frozen; 888 evaluable; strict and harmonic-aware recovery measured |
| False positives and quiet controls | Labelled FP/planet input available; 100-target quiet-control corpus frozen; controlled run pending (20-shard CI lane). Campaign rows now also carry per-target FPP telemetry (shard schema 1.1) |
| FPP calibration | Producer implemented (`fpp_calibration.py` + `run_fpp_calibration_campaign.py`); 100 FP + 100 planet cohorts frozen (`cohort_manifest.json`, `9de7d31a…`); 13 acceptance checks pre-declared in `program.json`; MAST run pending |
| Adversarial false positives | **Measured** on the frozen 56-scenario grid (0 errors): overall rejection 13/48 = 0.271 (CI 0.166–0.410) vs declared floor 0.80 — vetting rejected 1, cascade 5, detection 7; positive control accepted 8/8. **Gate left open** (6 of 20 checks failed, no floor re-tuned); report `85364125…` |
| Blind domain holdout | 144 real targets (72 planet / 72 false-positive) frozen from the blind partition, disjoint from every prior-gate id (`holdout_manifest.json`, `3fd1e65a…`); 22 acceptance checks pre-declared; light-curve run pending (`blind-holdout-v1.yml`, dispatch-only) |
| Blind test | Implemented; held-out data/run pending |
| TLS/BLS baselines | Implemented; same-corpus run pending |
| Performance | Implemented; measured campaign pending |

The next step is deterministic recovered-parameter analysis from the frozen injection trial table. It must preserve the measured detection results and report unavailable parameter values as `not_evaluated`, never as zero.

Four pending gates are executable today without new code: the false-positive/quiet-control and FPP-calibration campaigns fan out to 20 shards in GitHub Actions (`.github/workflows/fp-quiet-controls-v1.yml`, `.github/workflows/fpp-calibration-v1.yml`), the adversarial FP gate runs its synthetic grid in 8 shards (`.github/workflows/adversarial-fp-v1.yml`), and the blind-domain holdout fans out to 12 shards on dispatch (`.github/workflows/blind-holdout-v1.yml`). All of them aggregate offline, and every corpus identity is frozen by SHA-256, so a re-run cannot silently reselect targets.
