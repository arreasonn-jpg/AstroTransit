# AstroTransit — Doğrulama ve Benchmark Yol Haritası

Bu belge, pipeline'ın bilimsel doğrulama borcunu **ölçülebilir kapılar**
hâlinde tanımlar. Kural: yeni özellik, kapalı çevrim doğrulama kanıtından
önce ikinci plandadır ("validation debt" önce ödenir).

Durum sembolü: ✅ ölçüm yapıldı, sonuç donduruldu | 🟩 mevcut altyapı, çalıştırma bekleniyor | 🟧 iskelet var, veri/çalıştırma eksik | ⬜ yapılmalı

| # | Kapı | Tanım | Durum | Araç |
|---|------|-------|-------|------|
| 1 | Injection-recovery | Enjekte edilmiş transitlerin (P, Rp/R*, derinlik, gürültü gridi) kaçta kaçı geri kazanılıyor; `completeness(P, Rp/Rs, duration, noise)` haritası | 🟧 | `astrotransit/validation/injection_recovery.py` |
| 2 | Bilinen gezegen geri kazanımı | TESS'ten bilinen onaylı gezegenler (örn. WASP-18b, WASP-19b) pipeline'dan geçirilir; beklenen/geri kazanılan periyot ve yarıçap hedef bazında raporlanır | 🟧 | `astrotransit benchmark` + `benchmarks/verified_targets.json` + `benchmark_report.py` |
| 3 | Bilinen false positive'ler | Bilinen EB/sistematiği olayların ne oranında elendiği | 🟧 | `corpus.py`, `build_labelled_corpus.py` + etiketli FP seti |
| 4 | Cross-sektör tutarlılığı | Tek sektör başarısı yetmez; aynı aday sektörler arası periyot/derinlik tutarlılığı | 🟧 | çok sektör stitching + `source_sectors` |
| 5 | Parametre geri kazanımı | Enjekte edilen P, Rp/R*, T0, derinlik ile geri kazanılan değerlerin dağılımı (bias, scatter) | 🟧 | `RecoveryTrial.period_error_fraction` + modeling |
| 6 | FPP kalibrasyonu | `fpp ≈ 0.01` denilen adayların gerçekten ~%1 false-positive çıkması; Brier skor + precision/recall e eğrisi | 🟧 | `astrotransit/validation/fpp_benchmark.py` |
| 7 | Earth-similarity duyarlılık analizi | Ağırlıkların ±10–20% değişiminde sıralamanın ne kadar değiştiği (Kendall τ) | ✅ | `astrotransit/validation/sensitivity.py` |
| 8 | Tam provenance | Her sonuç: veri kaynağı, sektör, pipeline versiyonu, config hash, bağımlılık ortamı, model versiyonu, zaman damgası, random seed | 🟩 | `astrotransit/validation/provenance.py`, `scripts/maintenance/make_environment_manifest.py` |

## Nasıl çalıştırılır

### 1. Injection-recovery (iskelet)

`InjectionScenario` listesi tanımlanır, her senaryo için sentetik ışık eğrisi
üretip pipeline'ın tespit adımı çalıştırılır; `InjectionRecoveryReport`
completeness ve `completeness_by_label` verir. Gerçek benchmark seti
(grid: derinlik × periyot × gürültü) Gate 1'in kapanışı için eklenmelidir.

### 2. Bilinen gezegenler

`astrotransit benchmark` komutu `benchmarks/verified_targets.json` içindeki
known-target listesini MAP-odaklı pipeline'dan geçirir. Çalışma tamamlandığında
`outputs/benchmark/benchmark_performance.json` ve
`outputs/benchmark/benchmark_targets.csv` içinde her hedef için şu alanlar
üretilir: expected/recovered period, `ΔP`, expected/recovered radius, `ΔRp`,
detection/recovery status ve sektör tutarlılığı. Bu dosyalar üretilmeden
sadece ground-truth JSON'unun varlığı performans kanıtı değildir.

Etiketli false-positive/quiet-star corpus'u yapılandırılmamışsa rapor
`false_positive_rejection: null` ve `not_evaluated` durumu taşır; bu değer
sıfır false-positive iddiası değildir.

### 3. FPP kalibrasyonu

`FPPBenchmarkCase(target_id, is_false_positive, fpp)` etiketli setiyle
`Brier score`, `false_positive_recall`, `planet_precision` ve kafa karıştırma
matrisi üretilir. Proxy `heuristic_vetting_weighted_v1` çıktısı için
kalibrasyon öncesi bu metrikler rastsal sıralama kadar iyi olmamalıdır;
kalibrasyon sonrası Brier skorun azalması beklenir.

### 7. Benzerlik duyarlılığı

`EARTH_SIMILARITY_PROFILES["strict_earth_twin"]` kopyalanır; ağırlık vektörü
±10/20% değiştirilerek aynı aday setinde skor sıralamasının Kendall τ'si
hesaplanır. τ < 0.9 ise ağırlık seçimi sıralamayı belirleyici demektir ve
sonuçlar "ağırlığa duyarlı" olarak etiketlenmelidir.

**Kapalı çevrim çalıştırıldı (2026-09-08).** Gerçek aday kataloğu
(`benchmarks/toi_catalog.csv`, 8064 TOI kaydından 7320 fotometrik aday)
üzerinde her iki profil için ±10% ve ±20% perturbasyon ölçüldü:

| Profil | Perturbasyon | τ (min) | Top-10 overlap | Karar |
|--------|-------------|---------|----------------|-------|
| `photometric_earth_analog` | ±10% | 1.0 | 1.0 | `ranking_stable` |
| `photometric_earth_analog` | ±20% | 1.0 | 1.0 | `ranking_stable` |
| `strict_earth_twin` | ±10% | 1.0 | 1.0 | `ranking_stable` |
| `strict_earth_twin` | ±20% | 1.0 | 1.0 | `ranking_stable` |

Yeniden üretim komutu (tek komut, deterministik):

```bash
python scripts/validation/run_similarity_sensitivity.py
```

Ölçülmüş ve provenance'lı (git commit, input SHA-256, rapor hash'i) dondurulmuş
sonuç: `benchmarks/results/similarity_sensitivity_v1.json`. Sözleşme testi:
`tests/test_similarity_sensitivity_results.py`.

Sınırlar (rapor içine de işlenmiştir): bu ölçüm, heuristik ağırlık seçiminin
**sıralama kararlılığı** testidir; mutlak skorların kalibrasyonu ve
yaşanabilirlik iddiası değildir. TOI kataloğu gezegen kütlesi/yoğunluğu
taşımadığından `strict_earth_twin` yalnızca mevcut boyutlarla değerlendirilmiştir
(sınıflandırma `INCOMPLETE_EARTH_TWIN` kalır). `tfopwg_disp` etiketleri
hiçbir skora ağırlık olarak girmez.

## Ölçülen ve dondurulan sonuçlar

| Sonuç dosyası | Kapı | Üreten komut |
|---------------|------|--------------|
| `benchmarks/results/similarity_sensitivity_v1.json` | 7 (benzerlik duyarlılığı) | `python scripts/validation/run_similarity_sensitivity.py` |

Bu listede yer almayan kapılar için sonuç iddiası yapılamaz; durumları tablodaki
sembollerle aynı kalmaya devam eder. Yeni bir ölçüm eklendiğinde bu tabloya
satır eklenir ve dosya commit/tag ile immutable kabul edilir.

## Release-gate sözleşmeleri (uygulandı)

- `astrotransit.validation.claims` claim seviyelerini tek bir enum altında toplar;
  takip kanıtı olmadan `CONFIRMED_PLANET` üretilemez.
- `provenance.build_manifest` her deney için git commit, config/input hash,
  seed, platform ve zaman damgasını taşır. Eksik ölçümler `null` kalır.
- `make_injection_grid` period × depth × duration deneyini üretir; rapor seed,
  completeness map ve provenance içerir.
- FPP benchmark raporu Brier skoruna ek olarak reliability curve, ECE, ROC-AUC
  ve PR-AUC üretir. Bunlar proxy kalibrasyonudur; Bayesian posterior değildir.
- Makine doğrulaması için aday JSON şeması `docs/candidate.schema.json` altında
  ve CI içinde Draft 2020-12 validator ile zorunlu olarak kontrol edilir.
  sürümlenmiştir. `CITATION.cff` yazılım atfı metadata'sını sağlar.
- `cross_sector.assess_cross_sector_consistency` period, depth, duration ve epoch
  tutarlılığını ayrı ayrı raporlar; tek sektör sonucu asla multi-sector olarak
  etiketlenmez. Ölçülmeyen boyutlar `multi_sector_incomplete` durumunda kalır.
- MCMC çıktısı `mcmc_quality=PASS` olmadan güvenilir posterior olarak işaretlenmez;
  `R-hat < 1.01`, minimum bulk ESS `>= 400` ve sıfır divergence zorunludur.
- `metrics.parameter_recovery` bias, scatter, RMSE ve interval coverage üretir.
  `splits.partition_target_ids` deterministic development/validation/blind-test
  ayrımı sağlar; blind set pipeline skorlarıyla yeniden karıştırılmaz.

## Çıktı sözleşmesi

Doğrulama çıktıları ana aday şemasından ayrıdır: known-target benchmark
raporu kendi JSON/CSV'sinde `pipeline_version`, toleranslar, hedef bazlı
expected/recovered alanları ve ölçülmeyen metrikler için `null` durumunu taşır.
Injection-recovery raporu ayrıca `seed`, `n_trials` ve `completeness` alanlarını
taşır. Kapı #8 (tam provenance) tüm bu raporlar için zorunludur.

Hiçbir benchmark çıktısı, pipeline çalıştırılmadan veya kalibrasyonlu etiketli
veri olmadan "validated", "confirmed" ya da sayısal FPP posterioru olarak
sunulamaz.
