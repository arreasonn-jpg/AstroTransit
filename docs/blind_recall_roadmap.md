# Körlü Holdout Recall İyileştirme Yol Haritası (v2 planı girdisi)

## Amaç ve epistemik sınır

`blind_domain_holdout` v1 kapısı **kapatılamıyor**: dondurulmuş v1 corpus'ta 53
gezegen / 55 yanlış-pozitif (kabul tabanı ≥60/≥60), `n_evaluated 108 < 120`,
`data.errors 9 ≠ 0`, `overall.recall 0.264 < 0.5`. Bu belge iyileştirme planını
tutar. **Kırmızı çizgi:** körlü veride hiçbir eşik/parametre ayarı yapılmaz
(kontaminasyon riski). Tüm ayar/yeniden-tasarım önce dondurulmuş eğitim ve
enjeksiyon corpora'larında doğrulanır; v2 corpus için yeni tabanlar kanıt
**önce** ilan edilir; körlü koşum en sonda tek denemede koşulur.

## Triyaj incide kanıtı (8 satır, gerçek ışık eğrileri)

`validation_runs/_triage/triage_shard0.json` (gerçek TESS SPOC verisi,
shard 144/18 → 8 vaka; **triyaj amaçlı, kapı kanıtı değildir**):

| mod | n | örnekler |
|---|---|---|
| accepted | 2 | 306362738 (G), 268334473 (G) |
| vetoed | 3 | 88902249 (G), 102713734 (G), 77951245 (SP) |
| fp_leak | 3 | 118329434 (SP), 141412823 (SP), 286561122 (SP) |

Veto bayrak frekansları (vetoed satırlar): `secondary_eclipse_snr` ×3,
`secondary_eclipse` ×2, `odd_even_mismatch` ×1, `odd_even_harmonic` ×1.
Vetting kestirimlerinin etiket dağılımı incelticidir: `secondary_eclipse:warn` 4
SP'nin 3'ünde **ve** 4 gezegenin 3'ünde de görülüyor (bu incide'da ayırıcılığı
zayıf); `odd_even_mismatch:fail` hem gezegen (102713734 → veto), hem SP
(141412823 → yine de kabul) bir satırda ateşlenmiş.

## Bulgu 1 — Recall: ikincil tutulma vetoları

Recall kaybının ana kabahatli adayı ikincil tutulma ailesi vetoları: vetoed 3
satırın 2'si gerçek gezegen (88902249: cascade onayladı → FPP 0.337 → veto;
102713734: üç bayrakla veto). Olası mekanizma: derin/SDE yüksek geçişlerde
kalıntı modelleme artığı ikincil tutulmaya benzeyen bir "negatif derinlik"
üretiyor; veto tek sektör kanıtıyla keskin kesim yapıyor.

Yol haristası (ölçüm yeri: eğitim corpora'ları, körlü veri değil):

1. `secondary_eclipse_snr` veto'sunu tek başına keskin kesimden çıkarmak:
   keskin kesim yerine `secondary_eclipse:fail` **ve** `secondary_eclipse_snr`
   ikilisinin birlikte gerekmesi, veya çok sektör kanıtı şartı ("tek sektörde
   ikincil şüpheli" vakalar eğitim corpora'sında karşılaştırılmalı).
2. Bayrak ölçümünü sağlamlaştırmak: ikincil tutulma fazındaki kalıntı
   genişliği, faz-filtre/kalibrasyon artığından bağımsız ölçülmeli (mevcut tek
   kesim yönteminin yanlışlaşma modu eğitim corpus'unda ayrıştırılmalı).
3. Çok sektör agregasyonu: eşleşen periyotta en az 2 sektörde geçiş görüldüğünde
   sektör-içi vetoların etkisi azaltılma yoluna gidilmeli (v1 raporun stratum
   kırılımı bunun etkisini ölçmeye uygun olduğundan çalışma eğitim ve/veya
   sentetik corpora'lar üzerinde yapılmalıdır).

## Bulgu 2 — Özgünlük: yanlış-pozitif sızması

İncide'da SP'lerin 3/4'ü kabul edildi; 2'si hiç vetolama bayrağı almadan
(118329434, 286561122 — "sessiz sızma"). Ayrıca `odd_even_mismatch:fail`
ateşlendiği halde kabul görülebiliyor (141412823) ve cascade, TLS odd/even
doğrulaması **iki kez başarısız** olmasına karşın adayı onaylıyor (88902249:
odd_even_mismatch=14.1 ve 24.6 > 3.0 → yine ONAYLANDI; sonra vetting'de
yanlış-pozitif). Bu, doğrulama katmanı ile kabul kapısı arasındaki gevşek
bağın göstergesi.

Yol haristası:

1. Cascade–vetting sözleşmesi: TLS doğrulama başarısızlıklarının
   (özellikle `odd_even_mismatch`) yalnız bilgilendirici uyarı değil, kabul
   kararına giren ayrı bir puan bileşeni olması; hangi sinyallerin kabul
   kararına girdiği satır bazında rapora yazılmalı (şu an per_sector
   kayıtlarından geriye dönük izlenebildiği için savunulabilir, ama kural
   açıkça koda bağlanmalı).
2. "Sessiz sızma" hedefi: hiç bayrak almadan kabul edilen SP'ler eğitim
   corpora'sında ayrı bir arama sınıfı olarak incelenmelidir; yapısal
   öznitelikler (kabuk-genişlik, v-shape, periyodik varyans komşuları gibi)
   yalnızca eğitim corpora'larında seçilir.

## Bulgu 3 — Corpus ve koşum altyapısı (v2)

- v2 corpus: ≥60/≥60 kompozisyon (aynı yıldız-bölmesi strata kurallarıyla)
  yeniden kurulup sha kilitlenir; v1'deki 9 veri hatasının kök nedenleri
  (eksik sektör/indirme davranışı) önce triyaj taksonomisiyle sınıflandırılıp
  giderilir.
- v2 kabul tabanları kanıt öncesi `program.json`'a ilan edilir (var olan
  epistemik protokolle aynı usül).
- Şu anki `run-shard` + `aggregate` altyapısı yeterli; tam körlü koşum
  shard'lara bölünerek çoklu oturumlarda yürütülüp toplanabilir.

## Sıra ve doğrulama girdileri

1. Eğitim corpora'larında ikincil tutulma bayrağı davranışını ölç
   (`analyze_real_noise_injection_parameters.py` usulüne uygun ölçüm).
2. Veto/kaçırma kuralı değişikliklerini eğitim corpora'larında doğrula;
   değişken listesi ve değerleri dondur.
3. v2 corpus'u kur, sha kilitle.
4. v2 tabanlarını kanıt öncesi ilan et.
5. Tek körlü koşum + `finalize_*_gate` akışıyla kapı durumunu çevir.
