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
| snr_adopted | float64 | Benimsenen SNR |
| total_score | float64 | Kalite skoru (0-100) |
| candidate_class | string | A/B/C/D/X sınıfı |
| fpp | float64 | False Positive Probability |
| cascade_confirmed | bool | Cascade onayladı mı |
| fit_method | string | "map" veya "mcmc" |

Tam şema `astrotransit/outputs/schemas.py` dosyasında
55 alandan oluşmaktadır.

## JSON Rapor Yapısı

```json
{
  "metadata": { "version": "...", "created_at": "..." },
  "target": { "source_id": "...", "sector": 14 },
  "stellar": { "radius_rsun": 1.0, "teff_k": 5500 },
  "detection": { "bls": {...}, "tls": {...}, "cascade": {...} },
  "parameters": { "period_days": 3.5, "rp_rs": 0.1, ... },
  "derived": { "planet_radius_rearth": 1.1, ... },
  "quality": { "snr_adopted": 12.5, ... },
  "vetting": { "fpp": 0.03, "tests": [...] },
  "score": { "total_score": 82, "candidate_class": "A" },
  "modeling": { "fit_method": "map", ... }
}