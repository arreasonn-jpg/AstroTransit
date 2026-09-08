# AstroTransit — Pipeline Tasarımı

## TESS Pipeline

### Tam İş Akışı

1. **Yıldız Özellikleri** — TIC katalogdan Teff, R*, M* al
2. **Veri İndirme** — MAST'tan SPOC Light Curve indir
3. **Ön İşleme** — Normalize → Temizle → Detrend (wotan biweight)
4. **Sektör Stitching** — Her sektörü robust medyanla hizala; zaman tabanını ve sektör provenance'ını koru
5. **BLS Tarama** — 0.3–30 gün aralığında hızlı periyot araması
6. **TLS Doğrulama** — BLS adayını gerçekçi transit şekliyle doğrula
7. **Uzun Periyot Tarama** — 20–500 gün aralığında stitched BLS; tek transitleri `single_transit_ambiguous` olarak ayır
8. **MAP Fit** — scipy L-BFGS-B ile hızlı parametre tahmini
9. **PyMC MCMC** — SNR > eşik için tam posterior örnekleme
10. **Kalite Değerlendirme** — Metrik + SNR + Vetting + Skor + Sınıf
11. **Çıktı Üretimi** — Parquet + JSON + CSV + Görseller

### Uzun Periyot ve Tek Transit Kararı

`detection/long_period.py` klasik BLS/TLS cascade'inden **ayrı bir keşif
kanalıdır**: 20–500 gün aralığında stitched BLS üzerinde çalışır
(`LongPeriodSearchConfig`: min_power 7.0, derinlik 1e-4–0.5, en az 3
nokta/transit).

Her güç tepesi için gözlenen/geçerli olay sayısı karşılaştırılarak
identifiability durumu belirlenir:

| Durum | Koşul | Periyot hata varsayımı |
|-------|-------|------------------------|
| `multi_transit` | ≥2 gözlenen olay ve beklenen = gözlenen | `period_err = 0.02 × P` |
| `multi_transit_gapped_ambiguous` | ≥2 gözlenen olay, ama beklenen > gözlenen (gap) | `period_err = 0.5 × P` |
| `single_transit_ambiguous` | yalnızca 1 gözlenen olay | `period_err = 0.5 × P` |

Tepeler önce identifiability sırasına, sonra güce göre sıralanır (%1'den
küçük göreceli farktaki periyotlar dedup edilir).

`detection.long_period` ayarı açık olduğunda, başarıyla detrend edilen tüm
sektörler tekrar birleştirilir. Sektörler arası boşluklar gözlem zaman
baseline'ından ayrı tutulur. Transit süre grid'i yıldız yarıçapı/kütlesi ve
arama periyodu ile fiziksel olarak ölçeklenir. Arama sonucu
identifiability durumlarına göre:

- `multi_transit`: tüm beklenen geçişler gözlenmiş ve periyot daha iyi kısıtlanmış.
- `multi_transit_gapped_ambiguous`: birden fazla geçiş görülmüş, ancak aradaki sektör boşlukları nedeniyle geçişler kaçırılmış olabilir.
- `single_transit_ambiguous`: tek geçiş; periyot ve gezegen sınıfı doğrulanmış değildir.

Tek transitte periyot ve gezegen **doğrulanmış sayılmaz**: sonuç
`PERIOD_ESTIMATED` epistemik durumunda, belirsizlik
`long_period_identifiability` ve `period_err` alanlarında taşınır. Uzun
periyot sonucu normal BLS/TLS `cascade_confirmed` alanını otomatik olarak
onaylamaz; follow-up ve ek sektör önceliklendirmesi için kullanılır. Bu
kanalın çıktısı asla `DETECTED`/`MULTI_SECTOR_CONSISTENT` etiketiyle
karıştırılmaz (bkz. `docs/architecture.md` → İddia Güvenlik Duvarı).

### Earth-like hedef araması

`astrotransit earth-search targets.csv --min-similarity 90` komutu, listedeki
hedefleri TESS pipeline'ından geçirir ve `EarthCandidateRanker` ile tek hedef
başına en iyi Earth-like kaydı seçer. Operasyonel `priority_score`, similarity
skoru, ölçüm tamlığı, detection confidence, FPP ve kategori olgunluğunu
birleştirir; bu skor Earth similarity veya gezegen doğrulama olasılığı değildir.

Sıralama üç ayrı kategori taşır:

- `photometric_earth_like_candidate`: kütlesiz fotometrik öncelik adayı.
- `earth_twin_candidate`: strict profile için yarıçap, ışınım, `T_eq`, yörünge,
  gezegen kütlesi ve yıldız sıcaklığı ölçümleri bulunan aday.
- `confirmed_earth_twin`: yalnızca geçerli takip gözlemi kanıtı ile strict
  adayın birlikte bulunduğu kayıt.

### Takip gözlemi sözleşmesi

`FollowupEvidence`, takip kaynağı, gözlem tipi ve `observation_id` taşır.
RV kütlesi varsa `mass_mearth` olarak similarity hesabına girer; bilinmeyen
kütle hiçbir zaman `1 M_earth` ile doldurulmaz. TESS cascade `confirmed` alanı
ve çıplak `{"confirmed": true}` payload'ı doğrulanmış Earth twin statüsü
üretmez. Mevcut kayıtlar `OutputManager.update_followup()` ile JSON ve
Parquet'te aynı hedef/sektör kimliği altında upsert edilerek güncellenebilir;
kopya aday satırı oluşturulmaz.

### Cascade Karar Ağacı

`detection/cascade.py` sıralı elenme uygular; her elenme adımı açık bir
`CascadeStatus` üretir ve sessiz atlamaya izin vermez:

```
BLS hızlı tarama
   ├─ aday yok        → BLS_FAILED
   └─ aday var
        ↓
TLS doğrulama
   ├─ başarısız       → TLS_FAILED
   └─ başarılı
        ↓
Periyot uyum kontrolü (BLS ↔ TLS periyotları)
   ├─ uyumsuz         → PERIOD_MISMATCH
   └─ uyumlu
        ↓
CONFIRMED → modelleme aşamasına (MAP; seçililerde MCMC)
```

Diğer durumlar: `BLS_ONLY` (`require_both=False` ayarında; her zaman
`confirmed=False`) ve `ERROR` (hata; aday üretilmez). Cascade
`confirmed=True` yalnızca bu ağacın `CONFIRMED` kolundan çıkar; `BLS_ONLY`
dahil hiçbir diğer durum `CONFIRMED_PLANET` iddiasına dönüştürülemez (bkz.
`claims.py` — `confirmed` alanı iddia türetmede yok sayılır).