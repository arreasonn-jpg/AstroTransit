# Changelog

Tüm önemli değişiklikler bu dosyada belgelenir.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Sürümleme: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

### Added — Test Coverage Sprint (4 PR, +1115 test)

Üç aşamalı test coverage çalışması: **%75.89 → %94.66** (+18.77 pp), **+1115 test** (1294 → 2409).

#### PR #56 — Coverage %73.74 → %80.22 (+393 test)
- 14 yeni test dosyası (data, discovery, modeling, preprocessing, quality, temp_cache, validation)

#### PR #57 — Coverage %80.22 → %90.18 (+490 test)
- **B1**: `cli/main.py` (0% → 88.70%), `dashboard/app.py` (0% → 68.99%)
- **B2**: `data/tess_client.py` (19.7% → 89.73%), `pipelines/tess_pipeline.py` (19.3% → 92.14%)
- **B3**: `modeling/fitter.py` (0% → 89.71%), `modeling/pymc_fit.py` (0% → 88.79%)
- **B4**: `preprocessing/jwst_detrend.py` (32.3% → 94.61%), `pipelines/jwst_pipeline.py` (53.6% → 89.79%)
- **B5**: `quality/fpp/eb_test.py` (62.9% → 95.62%), `quality/fpp/neb_test.py` (72.7% → 100%), `detection/long_period.py` (74.0% → 95.39%), `detection/cascade.py` (67.3% → 96.90%)
- **B6**: `outputs/schemas.py` (83.5% → 95.74%), `outputs/writers.py` (65.1% → 96.92%)

#### PR #58 — Coverage %90.18 → %93.28 (+352 test)
- `quality/vetting.py` (78% → 100%)
- `validation/followup.py` (70% → 100%)
- `detection/tls_search.py` (74.5% → 99.4%)
- `quality/residual_analysis.py` (75.5% → 100%)
- `validation/benchmark_report.py` (80% → 98.9%)
- `quality/fpp/beb_test.py` (76% → 100%)
- `quality/fpp/report.py` (65% → 100%)
- `validation/injection_recovery.py` (67% → 99.3%)
- `science/earth_similarity.py` (84.5% → 100%)

#### PR #59 — Coverage %93.28 → %94.66 (+273 test)
- `modeling/parameters.py` (79.1% → 100%)
- `settings.py` (85.7% → 100%)
- `validation/blind_holdout.py` (84.9% → 100%)
- `discovery/earth_search.py` (82.0% → 100%)
- `data/tess_client.py` (89.7% → 100%)

### Fixed — Bug Fixes
- **`quality/timing_analysis.py`**: `ep` → `ep_obs` (crash fix)
- **`quality/scorer.py`**: Çift `* 100` hatası (yanlış skor üretiyordu)
- **`validation/injection_recovery.py`**: `recovered` → `recovered_int` (completeness hesabı `UnboundLocalError` veriyordu)

### Known Issues
- **`validation/blind_holdout.py::allocate_quotas`**: `total > sum(available)` olduğunda `available`'ı aşan kota üretebilir. Test ile sabitlendi, düzeltme ayrı PR'da yapılacak.

### Changed
- `.cov_snap*.json` git tracking'den çıkarıldı ve `.gitignore`'a eklendi (LLM/analysis context çıktıları, kaynak kod değil)

## [0.1.0] — YYYY-MM-DD (İlk sürüm öncesi)
- İlk yayın öncesi geliştirme
