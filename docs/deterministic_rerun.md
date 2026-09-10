# Deterministic benchmark rerun gate

Bu kapı, aynı benchmarkın iki bağımsız koşusunun yalnızca başarı metriğini değil,
çıktı sözleşmesinin tamamını yeniden üretip üretmediğini doğrular.

## Çalıştırma

Önce aynı commit, config, corpus, environment manifest ve seed ile iki koşu üret:

```bash
astrotransit benchmark --output run_a/benchmark.json --csv-output run_a/targets.csv
astrotransit benchmark --output run_b/benchmark.json --csv-output run_b/targets.csv
```

Ardından kapıyı çalıştır:

```bash
python scripts/validation/compare_benchmark_reruns.py \
  run_a/benchmark.json run_a/targets.csv \
  run_b/benchmark.json run_b/targets.csv \
  --output run_comparison/determinism.json
```

Komut yalnızca şu dört koşul birlikte sağlanırsa `0` ile çıkar ve `PASS` üretir:

1. Zaman damgası ve gömülü hash gibi uçucu metadata çıkarıldıktan sonra JSON hash'i aynı.
2. CSV dosyasının SHA-256 hash'i aynı.
3. `metrics` nesnesinin canonical hash'i aynı.
4. JSON ve CSV içindeki `target_id` sırası iki koşuda da aynı ve birbiriyle tutarlı.

Herhangi bir farkta komut `1` ile çıkar; rapordaki `differences` alanı başarısız
kontrolleri listeler. Bu sonuç gerçek benchmark koşuları yapılmadan release
matrix'teki Determinism satırını `PASS` yapmaz.

## Provenance sözleşmesi

`build_manifest()` artık git commit, config/input hash, environment manifest hash,
Python sürümü, temel paket sürümleri, random seed, timestamp ve output hash alanlarını
tek manifest altında taşır. Eksik dosya veya paketler sayısal başarıya çevrilmez;
alanları `null` kalır.
