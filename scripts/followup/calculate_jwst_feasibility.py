"""
TIC 303241161 için JWST Transmission Spectroscopy Metric (TSM) 
ve Atmosferik Ölçek Yüksekliği (Scale Height) hesaplayıcı.
Referans: Kempton et al. 2018 (TSM formülleri)
"""

# Gezegen ve Yıldız Parametreleri (MCMC/MAP çıktılarından)
R_star = 0.670746      # R_sun
M_star = 0.64          # M_sun
T_eff = 4118.0         # K
J_mag = 10.3152        # Tmag yerine Jmag simülasyonu (yakın değerler)

R_p = 2.2059          # R_earth
P_days = 0.754877      # gün
T_eq = 1257.96         # K

# Sabitler
G_cgs = 6.6743e-8
M_earth_g = 5.972e27
R_earth_cm = 6.371e8
R_sun_cm = 6.957e10
k_B = 1.380649e-16     # erg/K
u_amu = 1.660539e-24   # g

# 1) Gezegen Kütle Tahmini (Chen & Kipping 2017 empirik bağıntısı)
# Rp < 1.23: Terrestrial, 1.23 < Rp < 14.2: Neptunian
if R_p < 1.23:
    M_p = 0.981 * (R_p ** 3.0)
else:
    M_p = 1.57 * (R_p ** 1.25) # Neptunian fit

print("="*70)
print("TIC 303241161 - JWST FZBLTE VE SPEKTROSKOP ANALZ")
print("="*70)
print(f"Tahmini Gezegen Kütlesi (M_earth) : {M_p:.2f} M_⊕")

# 2) Gezegen Yüzey Yerçekimi (g)
g_cgs = (G_cgs * M_p * M_earth_g) / ((R_p * R_earth_cm) ** 2)
print(f"Gezegen Yerçekimi (g)            : {g_cgs:.2f} cm/s²")

# 3) Atmosferik Ölçek Yüksekliği (H)
# ki senaryo test edilir: 
# Senaryo A: Hidrojen/Helyum zarfı (H/He dominated, mu = 2.3)
# Senaryo B: Su Dünyası / Ağır Atmosfer (Water-world, mu = 18.0)
mu_HHe = 2.3
mu_H2O = 18.0

H_HHe_km = (k_B * T_eq) / (g_cgs * mu_HHe * u_amu) / 1e5
H_H2O_km = (k_B * T_eq) / (g_cgs * mu_H2O * u_amu) / 1e5

print(f"Ölçek Yüksekliği (H_HHe)         : {H_HHe_km:.1f} km (H/He Zarfı)")
print(f"Ölçek Yüksekliği (H_H2O)         : {H_H2O_km:.1f} km (Su Dünyası)")

# 4) Geçiş Sinyali Genliği (Transit Signal Amplitude - 5 Scale Heights)
# Sinyal = 5 * (2 * H * Rp) / R_star^2
def calc_signal(H_km):
    H_cm = H_km * 1e5
    R_p_cm = R_p * R_earth_cm
    R_star_cm = R_star * R_sun_cm
    # Alan oranı diferansiyeli
    return 1e6 * (10 * H_cm * R_p_cm) / (R_star_cm ** 2)

sig_HHe = calc_signal(H_HHe_km)
sig_H2O = calc_signal(H_H2O_km)

print(f"Geçiş Spektroskopisi Sinyali (H/He): {sig_HHe:.1f} ppm")
print(f"Geçiş Spektroskopisi Sinyali (H2O): {sig_H2O:.1f} ppm")

# 5) Transmission Spectroscopy Metric (TSM) Kempton et al. 2018
# TSM = Scale_Factor * (Rp^3 * Teq) / (M_p * R_star^2) * 10^(-m_J/5)
# R_p 1.5 - 2.75 için Scale_Factor = 1.26
scale_factor = 1.26
tsm = scale_factor * (R_p**3 * T_eq) / (M_p * R_star**2) * (10**(-J_mag/5))
print(f"Transmission Spectroscopy Metric  : {tsm:.2f}")

print("\n" + "-"*50)
print("JWST ALET PLANLAMASI VE ANALZ")
print("-"*50)
if tsm > 90:
    print("🚨 KATEGOR: ÇOK GÜÇLÜ (Golden Target) - JWST için birinci öncelik!")
elif tsm > 50:
    print("✅ KATEGOR: YÜKSEK ÖNCELK (High Priority) - Keşif değeri çok yüksek.")
else:
    print("🟡 KATEGOR: ORTA ÖNCELK (Moderate) - Uzun gözlem süresi gerektirebilir.")

print("""
ÖNERLEN ENSTRÜMAN: JWST NIRISS SOSS (0.6 - 2.8 mikron)
  - 2.2 R_earth boyutu ve ~1250 K sıcaklığı ile bu hedef 'Lava World' 
    veya 'Atmospheric Escape' aşamasındaki bir sub-Neptune'dür.
  - NIRISS SOSS, su buharı (1.4 ve 1.9 mikron) ve bulut/pus (haze) 
    yapılarını tespit etmek için en kararlı moddur.
""")
print("="*70)
