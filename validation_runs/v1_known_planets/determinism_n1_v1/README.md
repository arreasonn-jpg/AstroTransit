# N=1 deterministic rerun — v1

Bu klasör, AstroTransit `0.3.0` için ilk gerçek iki-koşulu determinism kanıtını içerir.

## Kapsam

- Hedef: `TIC 100100827` / WASP-18b
- Git commit: `2502ebe92a628b2180ad8433cbdedcf91cf4f1d9`
- Python: `3.11.16`
- Seed: `42`
- Değerlendirilen sektör sayısı: `9`
- Koşular: aynı commit, corpus, config ve environment içinde ardışık Run A + Run B

## Gate sonucu

`determinism.json` sonucu: **PASS**

- Canonical JSON hash: eşit
- CSV SHA-256: eşit
- Metrics hash: eşit
- Target order: eşit
- Fark listesi: boş

Run A ve Run B aynı recovered period (`0.9414520040814421` gün), recovered radius
(`14.7585 R_earth`) ve toplu metrikleri üretmiştir. Ham JSON dosya hash'leri zaman
damgaları nedeniyle farklıdır; uçucu metadata çıkarıldıktan sonraki canonical output
hash'i iki koşuda da aynıdır.

## Bilimsel sınır

Bu kanıt yalnızca bu N=1 benchmarkın aynı ortamda deterministik yeniden üretildiğini
gösterir. Genel recall, precision, completeness, false-positive rejection veya geniş
corpus parameter-recovery başarısı olarak yorumlanamaz.

Dosya bütünlüğü ve provenance için `manifest.json`; karşılaştırma sonucu için
`determinism.json`; özgün ölçümler için `run_a/` ve `run_b/` kullanılmalıdır.
