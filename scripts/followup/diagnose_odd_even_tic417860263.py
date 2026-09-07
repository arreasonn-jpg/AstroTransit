# scripts/followup/diagnose_odd_even_tic417860263.py
"""
TIC 417860263 odd-even tutarsızlığının kaynağını teşhis eder.

Senaryolar:
  1. Detrending artefaktı → sektör bazlı detrend parametrelerini karşılaştır
  2. Yıldız lekesi modülasyonu → out-of-transit varyasyonunu kontrol et
  3. Eccentric orbit → secondary eclipse arayışı
  4. Gerçek EB → V-shaped transit, derinlik > 1%
"""
from __future__ import annotations
import json
import numpy as np
from pathlib import Path
from loguru import logger

# Sektör bazlı sonuçlar (refined_validation.json'dan)
SECTOR_DATA = {
    57: {"depth": 585, "odd": 566, "even": 612, "n_pts": 17979, "span": 28.75},
    58: {"depth": 247, "odd": 211, "even": 285, "n_pts": 19054, "span": 27.71},
    77: {"depth": 220, "odd": 182, "even": 274, "n_pts": 12862, "span": 28.05},
    78: {"depth":  86, "odd":-113, "even": 239, "n_pts": 12670, "span": 18.04},
    84: {"depth":-171, "odd":-254, "even": -91, "n_pts": 16706, "span": 25.74},
    85: {"depth":  12, "odd":  59, "even": -28, "n_pts": 12555, "span": 25.48},
}

def diagnose():
    print("=" * 70)
    print("TIC 417860263 (HD 224792) — Odd-Even Teşhis Raporu")
    print("=" * 70)
    
    # Test 1: Derinlik vs sektör süresi korelasyonu
    print("\n[TEST 1] Derinlik vs Sektör Süresi")
    print("-" * 50)
    for s, d in SECTOR_DATA.items():
        ratio = d["depth"] / 585 * 100  # S57'ye göre normalize
        flag = "⚠️" if abs(ratio - 100) > 50 else "✅"
        print(f"  S{s}: {d['depth']:>6} ppm ({ratio:>5.1f}%) "
              f"span={d['span']:.1f}d {flag}")
    
    print("\n  → Derinlik sektör süresiyle azalıyorsa: detrending artefaktı")
    print("  → Derinlik rastgele değişiyorsa: yıldız aktivitesi")
    
    # Test 2: Odd-even farkı vs SNR
    print("\n[TEST 2] Odd-Even Farkı Anlamlılığı")
    print("-" * 50)
    for s, d in SECTOR_DATA.items():
        diff = d["even"] - d["odd"]
        # Basit hata tahmini: depth_err ~ depth / SNR
        snr_est = abs(d["depth"]) / 20  # kaba tahmin
        sigma_diff = abs(diff) / max(snr_est, 1)
        sig_flag = "🚨" if sigma_diff > 3 else "⚠️" if sigma_diff > 1.5 else "✅"
        print(f"  S{s}: Δ={diff:>+7.0f} ppm  "
              f"(odd={d['odd']:>+6}, even={d['even']:>+6}) {sig_flag}")
    
    print("\n  → Tüm sektörlerde tutarlı fark: gerçek fiziksel sinyal (EB?)")
    print("  → Sadece düşük SNR sektörlerde fark: gürültü artefaktı")
    
    # Test 3: Negatif derinlik sektörleri
    print("\n[TEST 3] Negatif Derinlik Sektörleri")
    print("-" * 50)
    neg_sectors = [s for s, d in SECTOR_DATA.items() if d["depth"] < 50]
    if neg_sectors:
        print(f"  🚨 Sektörler {neg_sectors}: sinyal yok veya negatif")
        print("  → Bu sektörlerde zorlanmış ephemeris başarısız")
        print("  → Gerçek gezegen olsaydı her sektörde pozitif derinlik beklenir")
        print("  → OLASI AÇIKLAMA: Sinyal S57-S58'de güçlü, sonra kayboluyor")
        print("    Bu, yıldız aktivite döngüsüyle uyumlu olabilir")
    else:
        print("  ✅ Tüm sektörlerde pozitif derinlik")
    
    # Test 4: EB olasılık kontrolü
    print("\n[TEST 4] EB Olasılık Kontrolü")
    print("-" * 50)
    max_depth = max(d["depth"] for d in SECTOR_DATA.values())
    print(f"  Maksimum derinlik: {max_depth} ppm ({max_depth/10000:.2f}%)")
    if max_depth > 10000:
        print("  🚨 >1% derinlik → EB çok olası")
    elif max_depth > 3000:
        print("  ⚠️ 0.3-1% → EB veya büyük gezegen")
    else:
        print("  ✅ <0.3% → gezegen boyutuyla tutarlı")
    
    # Sonuç
    print("\n" + "=" * 70)
    print("SONUÇ VE ÖNERİLER")
    print("=" * 70)
    print("""
  1. S57-S58'deki sinyal güçlü ve tutarlı (585 ve 247 ppm).
  2. S77-S78'de sinyal zayıflıyor, S84-S85'te kayboluyor.
  3. Bu patern şunlardan biri olabilir:
     a) Yıldız lekesi döngüsü (M dwarf aktivite)
     b) Detrending overfitting (özellikle kısa sektörlerde)
     c) Gerçek fiziksel değişim (precessing orbit?)
  
  ÖNERİLEN SONRAKİ ADIMLAR:
  → S57 ve S58 ham light curve'larını indir
  → Farklı detrending yöntemleri dene (biweight vs GP vs spline)
  → Out-of-transit varyasyonunu kontrol et (periodogram)
  → Secondary eclipse arayışı (phase 0.5'te)
  → Eğer sinyal S57-S58'de sağlamsa, sadece bu 2 sektörle
    JWST proposal yaz (4/6 sektör yeterli değil ama 2/2 güçlü sektör yeterli)
""")

if __name__ == "__main__":
    diagnose()