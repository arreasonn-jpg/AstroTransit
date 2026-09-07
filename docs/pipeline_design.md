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

### Cascade Karar Ağacı