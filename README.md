# AstroTransit

AstroTransit, TESS (ve opsiyonel JWST) ışık eğrilerinde transit adaylarını
aramak, doğrulamak ve kalite sınıflandırması yapmak için modüler bir Python
projesidir.

## Özellikler

- MAST/Lightkurve üzerinden TESS light curve arama ve kalite temizliği
- Normalize etme, gap/segment tespiti ve Wotan detrending
- BLS → TLS kademeli transit tespiti
- Çok sektör stitching ve 20–500 gün uzun periyot / single-transit taraması
- MAP modelleme; kurulu ve güçlü adaylarda opsiyonel PyMC/exoplanet MCMC
- SNR, vetting, false-positive, anomaly ve aday sınıfı değerlendirmesi
- Configurable Dünya-benzerlik profilleri ve belirsizlikli aday sıralaması
- Photometric aday, Earth-twin adayı ve follow-up ile confirmed Earth twin ayrımı
- Similarity, detection confidence ve FPP'nin ayrı raporlanması
- JSON, Parquet ve CSV çıktı sözleşmesi
- CLI ve Streamlit dashboard

## Kurulum

Önerilen Python sürümü 3.11 veya daha yenisidir:

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
astrotransit benchmark --max 5
```

Ayarlar `configs/default.toml` içinden yüklenir. Farklı bir dosya vermek için
`--config configs/wsl_mcmc.toml` kullanabilirsiniz.

`earth-search` komutu listedeki TESS hedeflerini batch olarak tarar ve yaklaşık
`%90+` Earth similarity adaylarını sıralar. Çıktıda `similarity_score`,
`detection_confidence` ve `false_positive_probability` ayrı tutulur;
`priority_score` yalnızca takip gözlemi önceliğidir, doğrulama olasılığı
değildir. Takip doğrulaması için `FollowupEvidence` kaydı ve gözlem kimliği
kullanılmalıdır; çıplak `confirmed=true` değeri Earth twin onayı sayılmaz.
Mevcut JSON/Parquet adayları için `OutputManager.update_followup()` aynı
hedef/sektör satırını güncelleyerek follow-up sonucunu kalıcı kayda bağlar.

Dashboard:

```bash
streamlit run dashboard/app.py
```

## Çıktılar

Varsayılan olarak `outputs/` altında:

- `json/`: aday başına bölümlenmiş bilimsel rapor
- `parquet/`: filtrelenebilir toplu katalog
- `csv/`: özet dışa aktarım
- `figures/`: tanı grafikleri

Veri modeli ve alan açıklamaları için [`docs/output_schema.md`](docs/output_schema.md)
ve mimari için [`docs/architecture.md`](docs/architecture.md) dosyalarına bakın.

## Testler

```bash
python -m pytest -q
```

Ağdan veri indiren entegrasyon akışları yerine testler sentetik light curve
kullanır. MAST erişiminin olmadığı ortamlarda istemci hatayı açıkça raporlar;
önbellek yalnızca `.cache/` altında tutulur.
