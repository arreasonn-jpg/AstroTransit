# Five-target known-planet sanity benchmark — v1

Bu klasör, AstroTransit `0.3.0` için gerçek TESS verisiyle çalıştırılan ilk N=5 known-planet sanity kampanyasını içerir.

## Kapsam

- Git commit: `5987f798fdd36ef97eb61c4494482a6c2062a8cd`
- Python: `3.11.16`
- Seed: `42`
- Hedef sayısı: `5`
- Ortam durumu: temiz git çalışma ağacı (`dirty: false`)
- Pipeline hedefler için mevcut sektörleri değerlendirmiştir.

## Ölçülen toplu sonuçlar

- Detection: `5/5` (`1.0`)
- Correct recovery: `2/5` (`0.4`)
- Period recovery: `3/5` (`0.6`)
- Radius recovery: `3/5` (`0.6`)
- Sector consistency: `1/4` (`0.25`; bir hedefte değerlendirilemedi)
- False-positive rejection: değerlendirilmedi

## Hedef bazında özet

| Hedef | Zorluk | Period | Radius | Correct | Sektör |
|---|---|---:|---:|---:|---:|
| WASP-18b | easy | PASS | PASS | PASS | 9 |
| WASP-126b | easy | PASS | PASS | PASS | 42 |
| TOI-125b | medium | FAIL | PASS | FAIL | 6 |
| TOI-561b | hard | FAIL | FAIL | FAIL | 7 |
| WASP-19b | easy | PASS | FAIL | FAIL | 1 |

## Yorum

Çalışma teknik olarak tamamlandı ve beş hedefin tamamında bir aday tespit edildi. Ancak bilimsel recovery sonucu yalnızca `2/5` tam doğru olduğundan bu kampanya genel başarı kanıtı değildir. Sonuçlar özellikle period alias/seçimi, radius tahmini ve sektörler arası tutarlılık alanlarında iyileştirme gerektiğini gösterir.

## Bilimsel sınır

Bu N=5 sanity kampanyası injection-recovery completeness, false-positive rejection, calibrated precision veya release-level performans iddiası değildir. Ölçülen değerler yalnızca dondurulmuş bu corpus, commit ve ortam için geçerlidir.

Dosya bütünlüğü ve provenance için `manifest.json`; özgün ölçümler için `results/benchmark.json` ve `results/targets.csv` kullanılmalıdır.
