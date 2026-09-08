
# TIC 439949948 b Parametreleri
R_star = 0.61088      # R_sun
M_star = 0.62          # M_sun
T_eff = 3947.0         # K
J_mag = 7.42           # Tmag ~ 7.4 (Çok Parlak!)

R_p = 1.42             # R_earth (Super-Earth / Sub-Neptune boundary)
P_days = 6.7414        # gün
T_eq = 559.0           # K

# Chen & Kipping 2017 fit
M_p = 1.57 * (R_p ** 1.25) # ~2.42 M_earth

G_cgs = 6.6743e-8
M_earth_g = 5.972e27
R_earth_cm = 6.371e8
R_sun_cm = 6.957e10
k_B = 1.380649e-16
u_amu = 1.660539e-24

g_cgs = (G_cgs * M_p * M_earth_g) / ((R_p * R_earth_cm) ** 2)

# TSM Kempton 2018 (1.25 < Rp < 1.5 için Scale Factor = 0.19)
scale_factor = 0.19
tsm = scale_factor * (R_p**3 * T_eq) / (M_p * R_star**2) * (10**(-J_mag/5))

print("="*60)
print("TIC 439949948 b — KARŞILAŞTIRMA HEDEF FZBLTES")
print("="*60)
print(f"Yarıçap: {R_p} R_earth | Kütle: {M_p:.2f} M_earth | Teq: {T_eq} K")
print(f"Yıldız J-mag: {J_mag} (ÇOK PARLAK HOST YILDIZ)")
print(f"Transmission Spectroscopy Metric (TSM): {tsm:.2f}")
print("="*60)
