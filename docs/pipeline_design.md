# AstroTransit — Pipeline Tasarımı

## TESS Pipeline

### Tam İş Akışı

1. **Yıldız Özellikleri** — TIC katalogdan Teff, R*, M* al
2. **Veri İndirme** — MAST'tan SPOC Light Curve indir
3. **Ön İşleme** — Normalize → Temizle → Detrend (wotan biweight)
4. **BLS Tarama** — 0.3–30 gün aralığında hızlı periyot araması
5. **TLS Doğrulama** — BLS adayını gerçekçi transit şekliyle doğrula
6. **MAP Fit** — scipy L-BFGS-B ile hızlı parametre tahmini
7. **PyMC MCMC** — SNR > eşik için tam posterior örnekleme
8. **Kalite Değerlendirme** — Metrik + SNR + Vetting + Skor + Sınıf
9. **Çıktı Üretimi** — Parquet + JSON + CSV + Görseller

### Cascade Karar Ağacı