# AstroTransit

**Türkçe: README.md | English: [README.en.md](README.en.md)**

AstroTransit, TESS ışık eğrilerinde transit adayı **tespiti, vetting ve
fiziksel karakterizasyonu** yapan, sonuçları kanıt zinciriyle (provenance)
birlikte kalıcı çıktı sözleşmesine döken, modüler bir Python araştırma
yazılımıdır.

Konumlandırma: **TESS-first transit keşif platformu; JWST için gelişen
bir takip arayüzü.** Bilimsel omurga TESS tarafındadır; JWST ürün akışı
henüz `JWSTProductContract` düzeyindedir (metadata araması işlemiş ürün
sayılmaz).

## Özellikler

- MAST/Lightkurve üzerinden TESS light curve arama ve kalite temizliği
- Normalize etme, gap/segment tespiti ve Wotan detrending
- BLS → TLS kademeli transit tespiti
- Çok sektör stitching ve 20–500 gün uzun periyot / single-transit taraması
- MAP modelleme; seçilmiş güçlü adaylarda opsiyonel PyMC/exoplanet MCMC
- SNR, vetting, false-positive **risk proxy'si** (heuristik) ve aday sınıfı değerlendirmesi
- Yapılandırılabilir Dünya-benzerlik profilleri (ağırlıklı benzerlik **indeksi**)
- Photometric aday, Earth-twin adayı ve follow-up ile confirmed Earth twin ayrımı
- Similarity, detection confidence ve FPP proxy'sinin **ayrı** raporlanması
- JSON, Parquet ve CSV çıktı sözleşmesi (şema v1.7, migration aracı)
- Known-target performans raporu, injection-recovery ve FPP benchmark yardımcıları (`astrotransit/validation`)
- CLI ve Streamlit dashboard

## Kurulum

Önerilen Python sürümü 3.11 veya daha yenisidir (CI'da 3.11–3.13 test edilir):

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

MCMC/JWST için opsiyonel bağımlılıklar:

```bash
python -m pip install -e ".[jwst,modeling]"
```

MAST anonim erişim için token gerekmez. İsteğe bağlı kimlik bilgileri için
`.env.example` dosyasını kopyalayıp yerel ortamda ayarlayın; gerçek sırları
Git'e eklemeyin.

## Kullanım

```bash
astrotransit version
astrotransit single "TIC 261136679" --force-map --no-viz
astrotransit batch benchmarks/pilot_targets.csv --force-map --no-viz
astrotransit earth-search targets.csv --min-similarity 90 --limit 50 \
  --output outputs/earth_search_ranked.json
astrotransit benchmark --max 5 \
  --output outputs/benchmark/benchmark_performance.json
```

Ayarlar `configs/default.toml` içinden yüklenir. Farklı bir dosya vermek için
`--config configs/wsl_mcmc.toml` kullanabilirsiniz.

`earth-search` komutu listedeki TESS hedeflerini batch olarak tarar ve
benzerlik indeksine göre adayları sıralar; `--min-similarity` bir **sıralama
filtresidir**, doğrulama eşiği değildir. Çıktıda `similarity_score`,
`detection_confidence` ve `false_positive_probability` **ayrı alanlar** olarak
tutulur; `priority_score` yalnızca takip gözlemi önceliğidir, doğrulama
olasılığı değildir. Takip doğrulaması için `FollowupEvidence` kaydı ve gözlem
kimliği kullanılmalıdır; çıplak `confirmed=true` değeri Earth twin onayı
sayılmaz. Mevcut JSON/Parquet adayları için `OutputManager.update_followup()`
aynı hedef/sektör satırını güncelleyerek follow-up sonucunu kalıcı kayda
bağlar. CLI ile de yapılabilir:

```bash
astrotransit followup-update "TIC 123456789" 14 followup.json \
  --output-dir outputs
```

Dashboard:

```bash
streamlit run dashboard/app.py
```

## Bilimsel iddialar ve sınırlar

Bu bölüm, AstroTransit'in çıktılarının ne anlama geldiğini resmi olarak
tanımlar; okumadan sonuçları aktarmayın.

- **Earth similarity bir olasılık değildir.** `earth_similarity_score`,
  Dünya referansına göre ağırlıklı Gaussian benzerlik indeksidir (0-100).
  Yaşanabilirlik, atmosfer veya yaşam olasılığı hakkında bilgi vermez;
  ağırlıklar v1.0 heuristik varsayılanlarıdır ve etiketli bir popülasyonda
  kalibre edilmemiştir. `94.2 similarity` ifadesi "94% Earth-like" diye
  okunmamalıdır. Detay: [`docs/output_schema.md`](docs/output_schema.md) →
  "Epistemik sınırlar".
- **FPP kalibre bir Bayesyen olasılık değildir.** `false_positive_probability`
  alanı, vetting testlerinin (odd/even, ikincil tutulma, derinlik limiti,
  yıldız değişkenliği, süre-periyot fizik tutarlılığı, simetri, veri
  tamlığı) ağırlıklı oylarından türetilen **heuristik risk proxy'sidir**;
  background EB popülasyonu, occurrence prior veya kalibrasyon içermez.
  Metod kimliği çıktıya `fpp_method` olarak işlenir. Kalibre FPP için
  `astrotransit/validation/fpp_benchmark.py` (Brier skor, precision/recall)
  etiketli veri üzerinde çalıştırılmalıdır.
- **`confirmed` kanıt zinciri olmadan üretilmez.** `CONFIRMED_EARTH_TWIN`
  yalnızca geçerli `FollowupEvidence` (kaynak + gözlem kimliği) + strict
  similarity bir aradayken oluşur. TESS cascade'in `confirmed` alanı veya
  çıplak `{"confirmed": true}` payload'ı doğrulama sayılmaz.
- **Uzun periyot / single-transit sonuçları `PERIOD_ESTIMATED` epistemik
  durumundadır.** `DETECTED` ile periyot tahmini karıştırılmamalıdır;
  belirsizlik `long_period_identifiability` ve `period_err` alanlarında
  taşınır.
- **Katalog dışı "aday" ifadesi keşif iddiası değildir.** TOI/Arcive
  eşleşmesi bulunmayan bir hedef "novel candidate" olarak **işaretlenir**;
  bağımsız fotometrik/astrometrik doğrulama (ExoFOP, TESS FOP süreci) tamamlanana
  kadar "keşif" olarak sunulmaz.

## MAP ve MCMC: ne zaman hangisi?

| Durum | Yöntem | Ne verir |
|-------|--------|----------|
| Toplu keşif taraması (yüzlerce–binlerce hedef) | **MAP** | Tek nokta optimum: en olası parametre değerleri, hızlı |
| Seçilmiş güçlü adaylar (sınırlı sayıda) | **MCMC** | Parametre uzayının **dağılımı**: arviz R-hat/ESS, posterior credible interval |

`--force-map` ile elde edilen sonuç **fit edilmiş gezegen parametreleri
dağılımı değil, posterior'ın tek noktalı tahminidir**. Periyot gibi kritik
parametreler MCMC'de örneklenmediyse `period_err_source=fixed_in_mcmc` olarak
işlenir ve belirsizlik MAP referansından gelir. Hangi adaya MCMC çalıştırılacağı
`scripts/followup/` iş akışında; toplu taramada MCMC hesapsal olarak uygulanabilir
değildir.

## Ölçülmüş doğrulama sonuçları

İlk availability-aware N=50 gerçek-TESS known-target kampanyası tamamlandı.
50 hedef seçildi; 46 hedef ölçülmüş sektörlerle değerlendirildi, dört hedefte
ölçülmüş sektör bulunamadı ve recovery paydalarından çıkarıldı.

| Metrik | Ölçülen değer |
|---|---:|
| Değerlendirilebilir seçili hedeflerde detection | 46/46 (%100,0) |
| Birleşik dönem + yarıçap recovery | 21/46 (%45,6522) |
| Dönem recovery | 32/46 (%69,5652) |
| Yarıçap recovery | 23/46 (%50,0) |
| Sektör tutarlılığı | 20/38 (%52,6316) |
| False-positive rejection | Değerlendirilmedi |

46/46 değeri yalnızca **seçilmiş ve değerlendirilebilir known-target alt kümesi**
için koşullu detection sonucudur; population recall, completeness veya precision
değildir. Ayrıntılı kanıt, hash'ler ve kalan kapılar:
[`docs/measured_validation_results.md`](docs/measured_validation_results.md).

## Doğrulama durumu ve yol haritası

AstroTransit'in mevcut durumu: **ciddi bir keşif/örüntüleme (characterization)
framework'ü; >=50 seçili known-target kampanyası ölçülmüştür, ancak pipeline'ın
bilimsel doğrulama programı (injection completeness, false-positive/quiet
controls, kalibre FPP ve blind test) henüz tam kapalı çevrimde değildir.** Bu
bilinçli bir sınır olarak raporlanır.

- Known-target performans raporu: `astrotransit/validation/benchmark_report.py`;
  `astrotransit benchmark` çalıştırıldığında hedef bazında expected period/radius,
  recovered değerler, detection recall, parametre hataları ve sektör tutarlılığı
  `outputs/benchmark/` altında JSON/CSV olarak yazılır. Ground-truth dosyasının
  mevcut olması tek başına ölçüm sonucu değildir.
- Injection-recovery altyapısı: `astrotransit/validation/injection_recovery.py`
  (completeness, periyot hatası ölçümleri)
- FPP proxy kalibrasyonu: `astrotransit/validation/fpp_benchmark.py`
  (Brier skor, false-positive recall, planet precision). Etiketli veri yoksa
  FPP değeri `null`/`not_available` kalır; `0.0` bilinmeyen değer yerine kullanılmaz.
- Benchmark CLI'ı: `astrotransit benchmark`
- Kapalı çevrim için gereken 8 doğrulama kapısı (injection-recovery,
  bilinen gezegen geri kazanımı, bilinen FP'lerin elenmesi, cross-sektör
  tutarlılığı, parametre geri kazanımı, FPP kalibrasyonu, benzerlik ağırlığı
  duyarlılık analizi, tam provenance): [`docs/validation.md`](docs/validation.md)

**Referans aday (uçtan uca örnekleme):** TIC 417860263 / HD 224792.
TOI/Arşiv kataloglarında eşleşmesi bulunmayan, pipeline'dan uçtan uca geçmiş
başlıca TOI-dışı referans adaydır: P ≈ 2.854 gün, Rp/R* ≈ 0.0251
(~3.07 R⊕), SNR ≈ 47.9; MAP + WSL MCMC (r-hat 1.04, 0 divergence).
Tekrarlanabilirlik için kanıt paketi GitHub Release/Zenodo üzerinde tutulur;
Git kaynak ağacına büyük ZIP veya campaign çıktısı eklenmez. TIC 417860263 için
kalibre edilmiş bir FPP hesaplanmadığından FPP iddiası yapılmamalıdır; eski
manuel `fpp: 0.0` özeti geçersizdir. Release metadata politikası
[`release/release_notes/reproducibility_policy.md`](release/release_notes/reproducibility_policy.md)
ile belgelenir.

## Çıktılar

Varsayılan olarak `outputs/` altında:

- `json/`: aday başına bölümlenmiş bilimsel rapor
- `parquet/`: filtrelenebilir toplu katalog
- `csv/`: özet dışa aktarım
- `figures/`: tanı grafikleri

Veri modeli ve alan açıklamaları için [`docs/output_schema.md`](docs/output_schema.md)
(önce "Epistemik sınırlar" bölümünü okuyun) ve mimari için
[`docs/architecture.md`](docs/architecture.md) dosyalarına bakın.

## Testler

```bash
python -m pytest -q
```

Ağdan veri indiren entegrasyon akışları yerine testler sentetik light curve
kullanır. MAST erişiminin olmadığı ortamlarda istemci hatayı açıkça raporlar;
önbellek yalnızca `.cache/` altında tutulur.

## Tekrarlanabilirlik

Her çalışma için önerilen provenance seti:

- Git commit + config dosyasının SHA-256'i (`astrotransit version` versiyonuyla birlikte)
- Ortam manifesti: `python scripts/maintenance/make_environment_manifest.py --output env_manifest.json`
  (Python, pip freeze, commit, config hash, zaman damgası)
- Referans bağımlılık kilidi: `envs/requirements.lock` (Python 3.11 snapshot;
  yeniden üretim komutu dosya başında)

## Lisans

[MIT](LICENSE) — bilimsel işbirliği ve bağımsız yeniden üretim amaçlı serbest
kullanım.
