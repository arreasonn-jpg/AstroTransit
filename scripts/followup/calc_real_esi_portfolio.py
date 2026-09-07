"""
Gerçek Fotometrik Fits Üzerinden ESI ve TSM Hesaplayıcı
"""
import pandas as pd
import numpy as np

# Schulze-Makuch 2011 ESI Formülü
R_EARTH = 1.00
T_EARTH = 288.15 # Kelvin
W_RADIUS = 0.57
W_DENSITY = 1.07
W_ESCAPE = 0.70
W_TEMP = 5.58

def calc_esi(r_p, teq_c):
    t_eq = teq_c + 273.15
    esi_r = (1.0 - abs((r_p - R_EARTH) / (r_p + R_EARTH))) ** W_RADIUS
    esi_t = (1.0 - abs((t_eq - T_EARTH) / (t_eq + T_EARTH))) ** W_TEMP
    m_p = 0.981 * (r_p ** 3.0) if r_p < 1.23 else 1.57 * (r_p ** 1.25)
    v_esc = 11.19 * np.sqrt(m_p / r_p)
    rho = 5.51 * (m_p / (r_p ** 3.0))
    esi_rho = (1.0 - abs((rho - 5.51) / (rho + 5.51))) ** W_DENSITY
    esi_v = (1.0 - abs((v_esc - 11.19) / (v_esc + 11.19))) ** W_ESCAPE
    return round(float((esi_r * esi_t * esi_rho * esi_v) ** (1.0 / 4.0)), 4)

def calc_tsm(r_p, teq_c, r_star=0.35, j_mag=9.5):
    t_eq = teq_c + 273.15
    m_p = 0.981 * (r_p ** 3.0) if r_p < 1.23 else 1.57 * (r_p ** 1.25)
    scale_factor = 0.19 if r_p < 1.5 else 1.26
    tsm = scale_factor * (r_p**3 * t_eq) / (m_p * r_star**2) * (10**(-j_mag/5))
    return round(float(tsm), 2)

# Gerçek fotometrik çıktılardan seçilen öne çıkan adaylar
real_data = [
    {"TIC_ID": "TIC 383353664", "Sector": 66, "P_days": 11.02, "Rp": 1.71, "Teq_C": 41.9, "SNR": 10.3, "Class": "A"},
    {"TIC_ID": "TIC 74401074",  "Sector": 39, "P_days": 11.07, "Rp": 1.66, "Teq_C": 47.6, "SNR": 7.6,  "Class": "A"},
    {"TIC_ID": "TIC 74401074",  "Sector": 65, "P_days": 8.70,  "Rp": 1.45, "Teq_C": 74.4, "SNR": 7.2,  "Class": "A"},
    {"TIC_ID": "TIC 152366332", "Sector": 100,"P_days": 2.09,  "Rp": 1.08, "Teq_C": 254.5,"SNR": 7.9,  "Class": "A"},
    {"TIC_ID": "TIC 152366332", "Sector": 90, "P_days": 2.04,  "Rp": 0.96, "Teq_C": 259.1,"SNR": 8.5,  "Class": "A"},
    {"TIC_ID": "TIC 352179145", "Sector": 84, "P_days": 12.61, "Rp": 0.71, "Teq_C": 223.0,"SNR": 15.1, "Class": "A"},
    {"TIC_ID": "TIC 320049266", "Sector": 18, "P_days": 11.40, "Rp": 3.19, "Teq_C": 223.1,"SNR": 14.8, "Class": "A"},
    {"TIC_ID": "TIC 289972535", "Sector": 40, "P_days": 2.22,  "Rp": 1.81, "Teq_C": 243.2,"SNR": 30.7, "Class": "A"},
]

results = []
for d in real_data:
    esi = calc_esi(d["Rp"], d["Teq_C"])
    tsm = calc_tsm(d["Rp"], d["Teq_C"])
    d["ESI_Score"] = esi
    d["TSM_Score"] = tsm
    results.append(d)

df_res = pd.DataFrame(results).sort_values(by="ESI_Score", ascending=False)

print("="*85)
print("GERÇEK FOTOMETRK FTLERDEN HESAPLANAN ESI VE TSM PORTFÖYÜ")
print("="*85)
print(df_res[["TIC_ID", "Sector", "ESI_Score", "TSM_Score", "Rp", "Teq_C", "P_days", "SNR", "Class"]].to_string(index=False))
print("="*85)
