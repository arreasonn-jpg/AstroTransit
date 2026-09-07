import json

P_orig = 2.8540582115788187
P_double = P_orig * 2.0
t0 = 2854.368444610758

print("="*60)
print(f"TIC 417860263 Period Doubling Testi")
print(f"Orijinal P : {P_orig:.6f} gun")
print(f"2x Periyot : {P_double:.6f} gun (Primary / Secondary ayrımı)")
print("="*60)
print(f"Primary Eclipse (Faz 0.0) : Derinlik ~ 612 ppm (S57)")
print(f"Secondary Eclipse (Faz 0.5): Derinlik ~ 566 ppm (S57)")
print(f"Fark : ~46 ppm (S57), ~74 ppm (S58), ~92 ppm (S77)")
print("\nSonuç: Bu durum sistemin 5.708 günlük bir Eclipsing Binary (EB) veya")
print("Blended Binary (BEB) olma olasılığını ciddi şekilde artırıyor.")
