# AstroTransit — Çıktı Şeması

## Parquet Katalog Şeması

| Alan | Tip | Açıklama |
|------|-----|----------|
| source_id | string | Hedef TIC ID |
| sector | int32 | TESS sektör numarası |
| period | float64 | Orbital periyot (gün) |
| period_err | float64 | Periyot belirsizliği |
| t0 | float64 | İlk transit zamanı (BTJD) |
| depth_ppm | float64 | Transit derinliği (ppm) |
| rp_rs | float64 | Yarıçap oranı |
| planet_radius_rearth | float64 | Gezegen yarıçapı (R⊕) |
| semi_major_axis_au | float64 | Yarı-büyük eksen (AU) |
| equilibrium_temperature_k | float64 | Denge sıcaklığı (K) |
| insolation_s_earth | float64 | Dünya ışınımına oran |
| planet_mass_mearth | float64 | Gezegen kütlesi (M⊕), varsa |
| snr_adopted | float64 | Benimsenen SNR |
| total_score | float64 | Genel kalite skoru (0-100) |
| candidate_class | string | A/B/C/D/X sınıfı |
| fpp | float64 | False Positive Probability |
| cascade_confirmed | bool | Cascade onayladı mı |
| fit_method | string | "map" veya "mcmc" |
| earth_similarity_profile | string | Dünya-benzerlik profili |
| earth_similarity_definition_version | string | Tekrarlanabilir similarity tanım sürümü |
| earth_similarity_score | float64 | Medyan Dünya-benzerlik skoru (0-100) |
| earth_similarity_p05/p95 | float64 | Belirsizlik aralığı sınırları |
| earth_similarity_completeness | float64 | Kullanılan ölçümlerin ağırlıklı tamlığı (0-1) |
| earth_analog_class | string | Earth-twin/analog sınıflandırması |
| earth_twin_status | string | photometric / candidate / confirmed ayrımı |
| earth_similarity_missing_dimensions | JSON string | Eksik similarity ölçümleri |
| mass_status | string | Kütle ölçümünün durumu |
| detection_confidence | string | Tespit/vetting güveni, similarity'den bağımsız |
| false_positive_probability | float64 | FPP, similarity skorundan bağımsız |
| coverage_baseline_days | float64 | Sektörler arası toplam zaman baseline'ı |
| observed_days | float64 | Gerçek gözlem günlerinin toplamı |
| n_observed_transits | int64 | Gözlenen transit sayısı |
| search_channel | string | `sector_cascade` veya `long_period` |
| source_sectors | JSON string | Uzun periyot taramasına giren sektörler |
| long_period_identifiability | string | Çok/tek transit tanımlanabilirliği |
| long_period_screening | bool | Uzun periyot screening kaydı mı |
| followup_confirmed | bool | Geçerli takip kanıtı açıkça doğruladı mı |
| followup_status | string | Takip kanıtının durumu |
| followup_evidence_quality | string | Takip kanıtının kalite sınıfı |
| followup_sources | JSON string | Takip gözlemi kaynakları |
| followup_observation_ids | JSON string | Takip gözlemlerinin kimlikleri |
| followup_evidence | JSON string | Takip kanıtı ayrıntıları |

Tam şema `astrotransit/outputs/schemas.py` dosyasında, şema sürümü `1.5`
olarak tanımlıdır. Similarity hesabı ayrıca `definition_version="1.0"`
ile etiketlenir.

## Dünya-benzerlik skoru

`earth_similarity_profile` üç profilden biri olabilir:

- `strict_earth_twin`: yarıçap, ışınım, denge sıcaklığı, yörünge, kütle ve yıldız sıcaklığı gerekir.
- `photometric_earth_analog`: transit ve yıldız fotometrisiyle kütlesiz önceliklendirme.
- `terrestrial_hz_analog`: daha geniş yaşanabilir bölge keşif profili.

Her dimension, Dünya referansına karşı tanımlı ağırlıklı Gaussian benzerlik
fonksiyonuyla hesaplanır; pozitif oranlar log-uzayında, sıcaklık ve yıldız
etkin sıcaklığı lineer uzayda değerlendirilir. Işınım `S/S_earth`, yörünge
`a/AU`, denge sıcaklığı ise `T_eq` olarak ayrı ayrı kullanılır. Yıldız tipi
TESS katalogundaki etkin sıcaklık (`host_teff`) ile tekrarlanabilir bir proxy
olarak temsil edilir. `T_eq` türetiminde varsayılan Bond albedosu `A=0.3`
olduğu için bu varsayım yaşam/atmosfer kanıtı değildir.

Eksik kütle veya yıldız parametresi Dünya değeriyle doldurulmaz. Böyle bir
sonuç yüksek fotometrik skor alabilir, ancak `INCOMPLETE_EARTH_TWIN` olarak
kalır ve strict aday kabul edilmez. `CONFIRMED_EARTH_TWIN` yalnızca geçerli bir `FollowupEvidence` kaydı (kaynak
ve gözlem kimliği içeren açık takip doğrulaması) ile strict similarity
adaylığı birlikte bulunduğunda üretilir. TESS cascade'in `confirmed` alanı,
çıplak `{"confirmed": true}` payload'ı veya similarity skoru tek başına
follow-up doğrulaması sayılmaz. Takip kütlesi yoksa strict profil yine
kütlesiz tamamlanmış kabul edilmez.

## Uzun periyot arama özeti

Hedef pipeline sonucu ayrıca `long_period` özeti taşıyabilir. Bu sonuç
transit doğrulaması değildir:

```json
{
  "source_sectors": [14, 40],
  "coverage_baseline_days": 126.95,
  "observed_days": 53.9,
  "n_observed_transits": 1,
  "identifiability": "single_transit_ambiguous",
  "best_peak": {
    "period_days": 87.4,
    "period_err_days": 43.7,
    "depth_ppm": 820.0
  }
}
```

## JSON Rapor Yapısı

```json
{
  "metadata": { "version": "...", "created_at": "..." },
  "target": { "source_id": "...", "sector": 14 },
  "stellar": { "radius_rsun": 1.0, "teff_k": 5500 },
  "detection": { "bls": {}, "tls": {}, "cascade": {} },
  "parameters": { "period_days": 3.5, "rp_rs": 0.1 },
  "derived": { "planet_radius_rearth": 1.1 },
  "earth_similarity": {
    "profile": "photometric_earth_analog",
    "score_p50": 91.2,
    "score_p05": 84.0,
    "classification": "PHOTOMETRIC_EARTH_ANALOG",
    "status": "photometric_earth_like_candidate",
    "measurement_completeness": 0.76
  },
  "detection_confidence": "MEDIUM",
  "quality": { "snr_adopted": 12.5 },
  "vetting": {
    "fpp": 0.03,
    "false_positive_probability": 0.03,
    "detection_confidence": "MEDIUM"
  },
  "score": { "total_score": 82, "candidate_class": "A" },
  "modeling": { "fit_method": "map" }
}
```
