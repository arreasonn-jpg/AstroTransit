# Changelog

Tüm önemli değişiklikler bu dosyada belgelenir.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Sürümleme: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

### Added — Masaüstü uygulaması + gerçek ilerleme
- **`desktop/` paketi**: PySide6 tabanlı native masaüstü uygulaması (`astrotransit-desktop` veya `python -m desktop.main`).
  - `desktop/helpers.py` (Qt-bağımsız, test edilebilir): çıktı kök keşfi, aday JSON listeleme, görsel kanıt zinciri sıralaması, `TESSTargetResult` → tablo satırı dönüşümü
  - `desktop/analysis.py` (Qt-bağımsız): orkestratör çağrısı + loguru → callback log aktarımı
  - `desktop/worker.py` / `app.py` / `main.py`: QThread worker, ana pencere (Analiz / Sonuçlar / Kayıtlı Çıktılar / Log sekmeleri), aday detay penceresi
  - `--smoke` bayrağı: pencere açılır 300 ms sonra kapanır (CI/PyInstaller doğrulaması)
- **Windows .exe paketi**: `packaging/astrotransit-desktop.spec` (PyInstaller onedir; astropy/astroquery veri dosyaları + configs bundle; ağır opsiyonel paketler pymc/streamlit/exoplanet dışlanır) — `scripts/package/build_desktop_exe.bat` / `.sh`
- **`desktop` projesinde**: `[project.optional-dependencies].gui` (`PySide6`), console script `astrotransit-desktop`
- **`run_batch(progress=...)`**: öncesinde dashboard'da sahte 0/10/20/100 progress bar vardı; artık orkestratör/`TESSPipeline.run_batch` gerçek hedef-bazlı ilerleme geri çağrısı destekliyor; `progress=None` iken çağrı kontratı korunur.
- **Robustness kapısı (contract missing listesinden çıkarıldı)**:
  - `astrotransit/validation/robustness.py`: `measure_cadence_robustness` (enjektif detector/perturbations), `evaluate_cadence_robustness_gate` (önceden dondurulan eşikler; pending_run / measured_pass / measured_fail)
  - `release_gate.py`: yeni `cadence_robustness` kapısı (`--robustness-report` CLI flag)
  - `scripts/validation/run_robustness_campaign.py`: kapı kanıt artefaktı üretimi (`detrending_cadence_impact_robustness`), threshold ilanı CLI'den dondurulur
- **Performance kapısı koşucusu**: `scripts/validation/run_performance_campaign.py` — `noop`/`csv-read` operasyonları; medyan saniye/1000-satır tavanı CLI'den dondurulur
- **`reproduce --verify`**: her kapı evidans manifest'inin (evidence_manifest.json / reproduce manifest) SHA-256 kayıtları yeniden hesaplanıp doğrulanabilir — `docs/validation_status.md` Kural 3'ün komut karşılığı (eşiksiz, salt-hash doğrulama).
- **CLI simetri**: `batch` komutuna eksik `--force-mcmc` bayrağı eklendi.
- Yeni testler: `test_desktop_app.py`, `test_temp_cache_concurrency.py`, `test_validation_performance.py`, `test_validation_robustness.py`, `test_robustness_campaign.py`, `test_performance_campaign.py`, `test_provenance_evidence.py`, `test_reproduce_verify.py`, `release-gate` kabul testleri

### Fixed — Bilinen hatalar
- **3 tarihsel test hatası (sessizce HEAD'de bulunuyordu)**: `labelled_fp_quiet_controls` / `adversarial_false_positives` kapıları commit `360625c` ile ölçülmüştü; 3 test eski `pending_run` beklentisini koruyordu. Testler ölçülmüş gerçek duruma (3 kapı kapalı) ve **önce/sonra snapshot** kontratına güncellendi:
  - `test_final_acceptance_program.py::test_current_program_closes_measured_fp_gates`
  - `test_adversarial_fp.py::test_program_json_declares_the_gate_contract` (`measured` bekler)
  - `test_fpp_calibration_freeze.py` — freeze'in yalnızca kendi kapısını değiştirdiği kontratı önce/sonra snapshot ile tanımlandı
- **`data/temp_cache.py` — çoklu-process yarış koşulu**: indeks oku-değiştir-yaz işlemleri artık `_cache_index.lock` üzerinde danışma kilidi (flock/msvcrt) altında, her zaman diskteki en güncel indeksle birleştirilerek yapılıyor. Sharded benchmark'ta last-writer-wins kaybı ve başka worker'ın dosyasını silmesi engellendi. Geçici yazım dosyası pid-suffix'li; `stats()` TOCTOU (exists→stat) durumu güvenli hale getirildi.
- **Provenance kontratı (B2)**: `astrotransit/validation/provenance.py::report_carries_provenance()` — `has_provenance` kapısı "dosya var" yeterliliğinden commit/hash/manifest yükü doğrulamasına geçti (boş JSON kanıt sayılmaz).
- **`validation/performance.py` — peak memory birim hatası**: `ru_maxrss` birimi artık platforma göre sabit katalığa çevriliyor (Linux=KiB, macOS=bayt). Değer büyüklüğüne göre tahmin (10 GB üzeri RSS'te iki kez bölme) ve anlamsız "before delta" hesabı kaldırıldı.
- **`cli/main.py` — bayat şema metni**: `migrate` komutundaki "Schema 1.6" ifadeleri `SCHEMA_VERSION` (1.7) kaynaklı dinamik hale getirildi.
- **`dashboard/app.py`**: ölü kod `list_json_candidates` kaldırıldı (karşılık testleri `desktop.helpers` üzerinden yenilendi); "Demo Veri Olustur" artık kullanıcının gerçek katalog parquet'ini ezemez — yalnızca ayrı bir `astrotransit_demo.parquet` sandbox dosyasına yazar; ana sayfa "TESS + JWST" abartısı bilimsel konumlandırma (TESS-first, JWST takip arayüzü) ile hizalandı.
- **`cli/main.py` — CLI simetri**: `batch` komutuna eksik `--force-mcmc` bayrağı eklendi (single ile eşitlen).

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
