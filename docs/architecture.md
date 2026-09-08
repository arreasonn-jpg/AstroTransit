# AstroTransit — Sistem Mimarisi

## Genel Bakış

AstroTransit, TESS ve JWST verilerinden transit tespiti, filtreleme ve
kategorizasyon yapan modüler bir Python platformudur. Konumlandırma:
**TESS-first transit keşif platformu; JWST için gelişen bir takip arayüzü.**
Bilimsel omurga TESS tarafındadır; JWST ürün akışı henüz
`JWSTProductContract` düzeyindedir (metadata araması, işlenmiş bilim ürünü
sayılmaz).

İki tasarım ilkesi tüm katmanlara geçerlidir:

1. **Önce kanıt, sonra iddia.** Hiçbir modül, mevcut kanıtı aşan bir epistemik
   etiket üretemez (bkz. "İddia güvenlik duvarı").
2. **Ölçülmeyen şey null kalır.** Eksik ölçüm `0.0`, tahmin veya katalog
   değeriyle doldurulmaz; durum alanı (`not_evaluated`, `not_estimated`,
   `multi_sector_incomplete`) açıkça raporlanır.

## Katman Mimarisi

```
┌────────────────────────────────────────────────────────────────────┐
│  Arayüz:  cli/main.py (Typer) · dashboard/app.py (Streamlit)       │
├────────────────────────────────────────────────────────────────────┤
│  Orkestrasyon:  pipelines/orchestrator.py (single/batch/sector/    │
│  followup/benchmark) → tess_pipeline · jwst_pipeline ·            │
│  benchmark_pipeline                                              │
├────────────────────────────────────────────────────────────────────┤
│  Bilim:      science/earth_similarity (profil, skor, sınıflandırma)│
│  Kalite:     quality/ (SNR, vetting, FPP proxy, habitability,      │
│              transit_consistency, eb_coorbital_discriminator, …)   │
│  Modelleme:  modeling/ (transit_model, MAP fitter, PyMC/exoplanet  │
│              MCMC, arviz R-hat/ESS kalite kapısı)                  │
│  Tespit:     detection/ (BLS → TLS cascade, 20–500 gün uzun       │
│              periyot taraması, threshold'lar)                      │
│  Ön-işlem:   preprocessing/ (normalize, temizlik, Wotan detrend,   │
│              çok sektör stitching)                                 │
│  Veri:       data/ (MAST/Lightkurve, TESS/JWST istemciler, önbellek)│
├────────────────────────────────────────────────────────────────────┤
│  Çıktı:      outputs/ (schemas v1.7, JSON/Parquet/CSV yazarlar,    │
│              migration, OutputManager)                             │
├────────────────────────────────────────────────────────────────────┤
│  Doğrulama:  validation/ (aşağıda) — pipeline'ın yanındaki ayrı    │
│              bilimsel denetim katmanı                               │
└────────────────────────────────────────────────────────────────────┘
```

`settings.py`, `configs/default.toml` üzerinden tüm katmanlara tek bir
`Settings` nesnesi sunar; `logging_config.py` merkezi log yapılandırmasını
taşır.

## Tek Hedefin Veri Akışı

```
TIC ID → MAST/Lightkurve indirme (data/)
       → normalize + gap/segment temizliği + Wotan detrend (preprocessing/)
       → çok sektör stitching (robust-medyan offset düzeltmesi, varsayılan
         gap eşiği 0.5 gün; transit/atmosfer doğrulaması değildir)
       → BLS hızlı tarama → TLS doğrulama (detection/cascade.py)
       → seçilen adaylarda uzun periyot / single-transit taraması
       → MAP fit (modeling/fitter.py); güçlü adaylarda opsiyonel MCMC
       → SNR + vetting + FPP risk proxy'si + Earth similarity (quality/, science/)
       → claim seviyesi türetilir (validation/claims.py)
       → JSON/Parquet/CSV + provenance manifest (outputs/)
```

`detection/cascade.py` sıralı elenme modelidir: BLS adayı yoksa
`BLS_FAILED`, TLS doğrulaması geçmezse `TLS_FAILED`; hiçbir aşama sessizce
atlanır ve son durum `CascadeCandidate.status` alanında taşınır.

## İddia Güvenlik Duvarı (Claim Firewall)

`astrotransit/validation/claims.py` epistemik hiyerarşiyi tek enum altında
toplar ve **kod düzeyinde** uygular:

```
DETECTED → CANDIDATE → MULTI_SECTOR_CONSISTENT →
PHOTOMETRIC_PLANET_CANDIDATE → EARTH_ANALOG_CANDIDATE →
FOLLOWUP_SUPPORTED → VALIDATED_PLANET → CONFIRMED_PLANET
```

Kurallar:

- `infer_claim_status(result)` en güçlü **desteklenen** iddiayı döndürür;
  `confirmed` alanı **kasıtlı olarak yok sayılır**.
- `CONFIRMED_PLANET` yalnızca kayıtlı `FollowupEvidence`
  (kaynak + gözlem kimliği, `validation/followup.py`) ile üretilebilir.
- `MULTI_SECTOR_CONSISTENT` en az iki sektör ve açık tutarlılık sonucu
  ister; tek sektör sonucu bu etiketi asla alamaz.
- `validate_claim(result, requested)` daha güçlü bir iddia istenirse
  `ClaimEvidenceError` fırlatır.

Bu modül bağımsızdır (standalone import); pipeline, exporter ve dış denetim
script'leri aynı sözleşmeyi kullanır.

## FPP Semantiği

`quality/fpp/` altındaki testler (EB/NEB/BEB, yıldız değişkenliği,
derinlik limiti, süre-periyot fizik tutarlılığı, simetri, veri tamlığı)
ağırlıklı oyla tek bir **heuristik risk proxy'si** üretir:

- Metod kimliği `FPP_METHOD = "heuristic_vetting_weighted_v1"`
  sabitiyle her çıktıya `fpp_method` alanı olarak işlenir.
- Değer, kalibre edilmiş Bayesyen FPP değildir; background EB popülasyonu,
  occurrence prior veya kalibrasyon içermez.
- FPP hesaplanamadıysa alan JSON `null` + `fpp_method: "not_estimated"`
  olur; `0.0` asla "bilinmeyen" yerine yazılmaz.
- Kalibrasyon (Brier skor, ECE, ROC/PR-AUC, reliability curve)
  `astrotransit/validation/fpp_benchmark.py` içinde ayrı bir benchmark
  sözleşmesidir; etiketli corpus olmadan çalıştırılmaz.

## Earth Similarity

`science/earth_similarity.py` versiyonlu profiller
(`EARTH_SIMILARITY_DEFINITION_VERSION = "1.0"`) üzerinde ağırlıklı Gaussian
benzerlik indeksi (0–100) hesaplar:

- Profiller: `strict_earth_twin`, `photometric_earth_analog`,
  `terrestrial_hz_analog`. Ağırlıklar v1.0 **heuristik varsayılanlarıdır**;
  etiketli popülasyon üzerinde kalibre edilmemiştir.
- Skor bir olasılık değildir ("94.2 similarity" ≠ "94% Earth-like").
- Eksik ölçüm Dünya değeriyle doldurulmaz; tamlık
  `measurement_completeness` olarak raporlanır ve zorunlu dimension
  eksikliğinde sınıflandırma `INCOMPLETE_EARTH_TWIN` kalır.
- Ağırlık duyarlılık analizi (±10/20%, Kendall τ + top-k overlap)
  `validation/sensitivity.py` içinde; ölçülmüş ilk sonuç
  `benchmarks/results/similarity_sensitivity_v1.json` (Gate 7,
  `docs/validation.md`).

## Doğrulama Katmanı (validation/)

Pipeline'ın yanındaki ayrı denetim katmanı; `docs/validation.md`'daki 8
kapının her birine karşılık gelir:

| Modül | Sorumluluk |
|-------|-----------|
| `claims.py` | epistemik hiyerarşi + kanıt kapısı (yukarıda) |
| `injection_recovery.py` | `InjectionScenario`/`RecoveryTrial`/`InjectionRecoveryReport`; `make_injection_grid` period × depth × duration deneyi, completeness haritası |
| `benchmark_report.py` | known-target performans raporu (expected/recovered P, Rp, ΔP, ΔRp, recall, sektör tutarlılığı) |
| `fpp_benchmark.py` | etiketli corpus üzerinde Brier, ECE, ROC-AUC, PR-AUC, confusion matrix; train/holdout ayrımı |
| `corpus.py` + `corpus_evaluation.py` | etiketli FP/quiet-star/planet corpus sözleşmesi (FPR, specificity, precision, recall) |
| `sensitivity.py` | Earth-similarity ağırlık duyarlılığı (Kendall τ, top-k overlap) |
| `cross_sector.py` | period/depth/duration/epoch tutarlılığı; tek sektör asla multi-sector etiketlenmez |
| `baselines.py` | AstroTransit vs TLS-only vs BLS-only karşılaştırma sözleşmesi (recall, FPR, runtime) |
| `metrics.py` | parameter recovery: bias, scatter, RMSE, 68/90/95% coverage |
| `splits.py` | deterministic development/validation/blind-test ayrımı |
| `determinism.py` | canonical JSON + SHA-256 output hash; timestamp hariç |
| `performance.py` | `RuntimeMeasurement` (seconds, seconds/target, peak memory, cpu) |
| `provenance.py` | git commit, config/input hash, seed, platform; eksik ölçüm `null` |
| `release_gate.py` | `docs/release_acceptance.md` matrisinin makine okunur değerlendirmesi |
| `adapters.py`, `plots.py`, `artifacts.py`, `failures.py` | pipeline çıktılarını doğrulama girdilerine çevirir; ölçülmüş-rapor-öncelikli figürler; hata sınıflandırması |

Kurallı sonuçlar: `PASS` yalnızca immutable rapor + yeniden üretim komutu
vardır; `PENDING DATA` / `PENDING RUN` sayısal skora çevrilemez.

## Çıktı Sözleşmesi

- Şema sürümü `1.7` (`outputs/schemas.py`); `docs/candidate.schema.json`
  Draft 2020-12 olarak CI'da makine doğrulanır; geçiş aracı
  `outputs/migration.py`.
- `similarity_score`, `detection_confidence` ve `false_positive_probability`
  **ayrı alanlardır**; `priority_score` yalnızca takip gözlemi önceliğidir.
- `outputs/` altı: `json/` (aday başına bölümlenmiş rapor), `parquet/`
  (filtrelenebilir katalog), `csv/` (özet), `figures/` (tanı grafikleri).
- `OutputManager.update_followup()` follow-up sonucunu aynı hedef/sektör
  satırına kalıcı bağlar (CLI: `astrotransit followup-update`).
- Benchmark/doğrulama çıktıları ana aday şemasından ayrıdır; ölçülmeyen
  metrikler `null` + durum alanı taşır.

## Arayüzler

- **CLI** (`cli/main.py`, Typer): `single`, `batch`, `earth-search`,
  `followup-update`, `benchmark`, `reproduce`, `release-gate`,
  `evaluate-corpus`, `evaluate-fpp`, `migrate`, `target-pool`, `version`.
- **Dashboard** (`dashboard/app.py`, Streamlit): katalog gezgini + aday
  detayı; similarity P05–P95, `earth_analog_class`, detection confidence ve
  FPP ayrı panellerde gösterilir.

## Ortam ve Tekrarlanabilirlik

- `pyproject.toml` (v0.3.0, MIT, Python ≥3.11) + `uv.lock` +
  `envs/requirements.lock` (Python 3.11 referans snapshot) + `Dockerfile`
  (locked requirements ile build; CI'da `docker` job'unda doğrulanır).
- Her çalışma için provenance seti: git commit + config SHA-256 + ortam
  manifesti (`scripts/maintenance/make_environment_manifest.py`).
- `CITATION.cff` yazılım atfı metadata'sını sağlar; `release/` yalnızca
  manifest, checksum ve release notu taşır — büyük artefaktlar GitHub
  Release/Zenodo üzerindedir (`release/README.md`).
