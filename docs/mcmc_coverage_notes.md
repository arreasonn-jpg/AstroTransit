# MCMC Kapsama Tuning Analizi (v1 kanıt: measured_fail)

## Kanıt

`validation_runs/final_acceptance_v1/mcmc/report.json` — 12 sentetik vaka,
600+400 draw/tune (declared: draws=600, tune=500), fix_jitter=1, configurations
hash kilitli. **Durum: `measured_fail`** — finalize audit'i akıllıca durağandı:
`status equals measured` kontrolü sağlanmadığından program.json'daki gate
`pending_run` olarak kaldı (kanıt mevcut, kapı KAPANMADI).

## Ölçüm özeti

| metrik | değer | değerlendirme |
|---|---|---|
| n_measured | 12/12 | örnekleme hiçbir vakada bozulmadı |
| 0 ıraksama | tüm vakalar | NUTS sağlıklı |
| r_hat_max_median | 1.007 | sağlık, kabul |
| ess_median | 641 | taban 100'ün üstünde |
| PPC-proxy | 1.016 | band içi [0.5, 1.5] |
| **HDI-94% kaplama (pooled)** | **0.556** | **taban 0.75 ALTINDA** |

Per parametre: `rp_rs` %50, `t0` %50, `impact_parameter` %67.

## Tanı

Örnekleyici sorunu DEĞİL: yakınsama ölçümleri sağlıklıydı. Kaplama açığı,
posterior genişliğinin sistematik ~½ kat küçük olduğuna işaret — yani
**aşırı güvenli posterior**. Olası kök neden:

1. **Veri-tekrar-kullanımı (MAP-merkezli prior)**: `PyMCFitter`, prior merkezini
   aynı veriden üretilmiş MAP kestirimi etrafında dar sigma ile (t0 σ=0.02,
   log_rp_rs σ=0.15, b σ=0.15, baseline σ=0.003) yerleştiriyor. Bu, verinin
   bilgisini örtük olarak ikiye sayar; posterior MAP etrafında kilitlenir ve
   gerçek örnekleme hatasını temsil etmeyen dar HDI üretir.
2. Vaka-mekanizmada `impact_parameter` kaplaması (0.67) diğerlerinden yüksek —
   b/rp_rs korelasyonu başka kombinasyonlarda daha sert daraltma üretiyor
   olabilir (lab: verilere binaen, tek-türkü değil).
3. `fix_jitter` DEĞİL: jitter sabitlendiğinde de kaplama açığı aynıydı; sorun
   jitter'dan değil prior merkezleme mekanizmalarından.

## v2 düzeltme planı (kanıt öncesi ilan usulü korunacak)

1. **Prior merkezleme düzeltmesi**: sentetik kalibrasyon kampanyasında prior'lar
   veriden TÜRETMEZ; bilinen büyüklükteki dogal aralık prior'ları (ör. b ∈
   U(0,1.2), log_rp_rs σ=0.5, t0 σ=0.05) kullanılır — sentetik vakada kesirli
   gerçeği yansıtan "detection_CONDİDİONED prior" yerine data-free kalibrasyon
   prior'larının kurulması, "dual-use data" sorununu kaldırır.
2. Kampanya yenisi `synthetic_mcmc_coverage_v2` olarak yeniden ilan edilir:
   tabanlar (kaplama aralığı vb.) KANIT ÖNCESİ program.json'a yazılır; v1
   kanıtın `measured_fail` durumu ROM'a geçirilmez — doküman bu dosyada kalır.
3. `PyMCFitter`'a gerçek-veri davranışıyla uyumluluğu korumak için gerekli
   bozmaları yapmadan önce: sentetik deja-vu estable prior vare yatısal test
   (`tests/test_mcmc_priors_calibrated.py` benzeri) ile kök neden izole edilir.
4. Kapsama ölçümü v2'de parametre-başına ayrıca raporlanır (rp_rs/t0/b) ve
   havuz-tabanın yanı sıra her parametreye taban konulur.

## Çıkarım

Kapı açık kalır; bu sonuç bir Güven-değer sıçraması DEĞİL, dürüst bir
kalibrasyon-eksik tespitidir — posterior aralıklarının pratikte ~½ kat küçük
olduğunun ölçülmüş kanıtı. Roadmap:
- v1 kanıt gerçekliği: `measured_fail` (kapı açık, tipi açıklaması report
  içi claim_boundary alanında)
- v2 planı: yukarıdaki 4 madde
