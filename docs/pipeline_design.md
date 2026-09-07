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

`detection.long_period` ayarı açık olduğunda, başarıyla detrend edilen tüm
sektörler tekrar birleştirilir. Sektörler arası boşluklar gözlem zaman
baseline'ından ayrı tutulur. Transit süre grid'i yıldız yarıçapı/kütlesi ve
arama periyodu ile fiziksel olarak ölçeklenir. Arama sonucu:

- `multi_transit`: tüm beklenen geçişler gözlenmiş ve periyot daha iyi kısıtlanmış.
- `multi_transit_gapped_ambiguous`: birden fazla geçiş görülmüş, ancak aradaki sektör boşlukları nedeniyle geçişler kaçırılmış olabilir.
- `single_transit_ambiguous`: tek geçiş; periyot ve gezegen sınıfı doğrulanmış değildir.

Uzun periyot sonucu normal BLS/TLS `cascade_confirmed` alanını otomatik olarak
onaylamaz; follow-up ve ek sektör önceliklendirmesi için kullanılır.

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