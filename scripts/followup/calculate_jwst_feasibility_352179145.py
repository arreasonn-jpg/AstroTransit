import numpy as np

# TIC 352179145 Parametreleri
R_star = 0.713032      # R_sun
M_star = 0.63          # M_sun (tahmini)
T_eff = 4017.0         # K
J_mag = 7.543          # Tmag'den tahmin

R_p = 0.67             # R_earth (DÜNYADAN KÜÇÜK!)
P_days = 12.6141       # gün
T_eq = 496.0           # K

# Sabitler
G_cgs = 6.6743e-8
M_earth_g = 5.972e27
R_earth_cm = 6.371e8
R_sun_cm = 6.957e10
k_B = 1.380649e-16
u_amu = 1.660539e-24

# Kütle tahmini (Chen & Kipping 2017, Terrestrial)
M_p = 0.981 * (R_p ** 3.0)  # ~0.29 M_earth (Mars benzeri)

g_cgs = (G_cgs * M_p * M_earth_g) / ((R_p * R_earth_cm) ** 2)

# Ölçek Yükseklikleri
mu_CO2 = 44.0   # Karbondioksit atmosferi (Venüs/Mars benzeri)
mu_H2O = 18.0   # Su buharı
mu_N2  = 28.0   # Azot (Dünya benzeri)

H_CO2 = (k_B * T_eq) / (g_cgs * mu_CO2 * u_amu) / 1e5
H_H2O = (k_B * T_eq) / (g_cgs * mu_H2O * u_amu) / 1e5
H_N2  = (k_B * T_eq) / (g_cgs * mu_N2 * u_amu) / 1e5

# Sinyal genlikleri (5 scale height)
def calc_signal(H_km):
    H_cm = H_km * 1e5
    R_p_cm = R_p * R_earth_cm
    R_star_cm = R_star * R_sun_cm
    return 1e6 * (10 * H_cm * R_p_cm) / (R_star_cm ** 2)

print("="*70)
print("TIC 352179145 b — JWST FZBLTE (DÜNYA BENZER GEZEGEN)")
print("="*70)
print(f"Gezegen Yarıçapı: {R_p} R_earth (Mars boyutunda!)")
print(f"Gezegen Kütlesi:  {M_p:.3f} M_earth")
print(f"Yerçekimi:        {g_cgs:.1f} cm/s²")
print(f"Denge Sıcaklığı:  {T_eq} K")
print()
print(f"Ölçek Yüksekliği (CO2): {H_CO2:.1f} km → Sinyal: {calc_signal(H_CO2):.1f} ppm")
print(f"Ölçek Yüksekliği (H2O): {H_H2O:.1f} km → Sinyal: {calc_signal(H_H2O):.1f} ppm")
print(f"Ölçek Yüksekliği (N2):  {H_N2:.1f} km → Sinyal: {calc_signal(H_N2):.1f} ppm")
print()

# TSM (Kempton et al. 2018, Rp < 1.5 için Scale Factor = 0.19)
scale_factor = 0.19
tsm = scale_factor * (R_p**3 * T_eq) / (M_p * R_star**2) * (10**(-J_mag/5))
print(f"Transmission Spectroscopy Metric (TSM): {tsm:.2f}")
print()

if tsm > 10:
    print("✅ KATEGOR: YÜKSEK ÖNCELK (Earth-size target)")
    print("   Earth-size gezegenler için TSM > 10 barajı aşılıyor!")
else:
    print("🟡 KATEGOR: ORTA ÖNCELK")
    print("   Daha uzun gözlem süresi gerekebilir.")

print()
print("ÖNERLEN ENSTRÜMAN: JWST NIRISS SOSS veya NIRSpec PRISM")
print("  - CO2 atmosferi (4.3 mikron) tespiti için NIRSpec PRISM")
print("  - H2O/O3 araması için NIRISS SOSS")
print("  - Gerekli transit sayısı: 3-5 (toplam ~20-35 saat)")
print("="*70)
