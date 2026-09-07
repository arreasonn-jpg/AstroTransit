# AstroTransit — Doğrulama ve Benchmark Yol Haritası

Bu belge, pipeline'ın bilimsel doğrulama borcunu **ölçülebilir kapılar**
hâlinde tanımlar. Kural: yeni özellik, kapalı çevrim doğrulama kanıtından
önce ikinci plandadır ("validation debt" önce ödenir).

Durum sembolü: ✅ mevcut altyapı | 🟧 iskelet var, veri/çalıştırma eksik | ⬜ yapılmalı

| # | Kapı | Tanım | Durum | Araç |
|---|------|-------|-------|------|
| 1 | Injection-recovery | Enjekte edilmiş transitlerin (P, Rp/R*, derinlik, gürültü gridi) kaçta kaçı geri kazanılıyor; `completeness(P, Rp/Rs, duration, noise)` haritası | 🟧 | `astrotransit/validation/injection_recovery.py` |
| 2 | Bilinen gezegen geri kazanımı | TESS'ten bilinen onaylı gezegenler (örn. WASP-18b, WASP-19b) pipeline'dan geçirilir; beklenen/geri kazanılan periyot ve yarıçap hedef bazında raporlanır | 🟧 | `astrotransit benchmark` + `benchmarks/verified_targets.json` + `benchmark_report.py` |
| 3 | Bilinen false positive'ler | Bilinen EB/sistematiği olayların ne oranında elendiği | ⬜ | vetting + etiketli FP seti |
| 4 | Cross-sektör tutarlılığı | Tek sektör başarısı yetmez; aynı aday sektörler arası periyot/derinlik tutarlılığı | 🟧 | çok sektör stitching + `source_sectors` |
| 5 | Parametre geri kazanımı | Enjekte edilen P, Rp/R*, T0, derinlik ile geri kazanılan değerlerin dağılımı (bias, scatter) | 🟧 | `RecoveryTrial.period_error_fraction` + modeling |
| 6 | FPP kalibrasyonu | `fpp ≈ 0.01` denilen adayların gerçekten ~%1 false-positive çıkması; Brier skor + precision/recall e eğrisi | 🟧 | `astrotransit/validation/fpp_benchmark.py` |
| 7 | Earth-similarity duyarlılık analizi | Ağırlıkların ±10–20% değişiminde sıralamanın ne kadar değiştiği (Kendall τ) | ⬜ | `EARTH_SIMILARITY_PROFILES` (profili kopyalayıp ağırlık vektörü değiştirerek) |
| 8 | Tam provenance | Her sonuç: veri kaynağı, sektör, pipeline versiyonu, config hash, bağımlılık ortamı, model versiyonu, zaman damgası, random seed | 🟧 | `scripts/maintenance/make_environment_manifest.py`, `release/manifests/` |

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

## Çıktı sözleşmesi

Doğrulama çıktıları ana aday şemasından ayrıdır: known-target benchmark
raporu kendi JSON/CSV'sinde `pipeline_version`, toleranslar, hedef bazlı
expected/recovered alanları ve ölçülmeyen metrikler için `null` durumunu taşır.
Injection-recovery raporu ayrıca `seed`, `n_trials` ve `completeness` alanlarını
taşır. Kapı #8 (tam provenance) tüm bu raporlar için zorunludur.

Hiçbir benchmark çıktısı, pipeline çalıştırılmadan veya kalibrasyonlu etiketli
veri olmadan "validated", "confirmed" ya da sayısal FPP posterioru olarak
sunulamaz.
