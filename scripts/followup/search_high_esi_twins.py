"""
Tam Matematiksel ESI (Earth Similarity Index) Tarayıcı ve Filtreleyici
Referans: Schulze-Makuch et al. (2011) Astrobiology
"""
import pandas as pd
import numpy as np
from pathlib import Path
import glob
import json

# ESI Parametreleri ve Ağırlıkları (Dünya Referanslı)
R_EARTH = 1.00     # R_earth
T_EARTH = 288.15   # Kelvin (Surface/Equilibrium reference)
RHO_EARTH = 5.51   # g/cm3
V_ESCAPE = 11.19   # km/s

W_RADIUS = 0.57
W_DENSITY = 1.07
W_ESCAPE = 0.70
W_TEMP = 5.58

def calc_esi(r_p, t_eq, rho_p=5.51):
    """2 ve 4 parametreli ESI hesabı"""
    if pd.isna(r_p) or pd.isna(t_eq) or r_p <= 0 or t_eq <= 0:
        return 0.0
    
    # 1. Yarıçap ESI
    esi_r = (1.0 - abs((r_p - R_EARTH) / (r_p + R_EARTH))) ** W_RADIUS
    
    # 2. Sıcaklık ESI
    esi_t = (1.0 - abs((t_eq - T_EARTH) / (t_eq + T_EARTH))) ** W_TEMP
    
    # Kütle & Kaçış Hızı Tahmini (Chen & Kipping 2017)
    m_p = 0.981 * (r_p ** 3.0) if r_p < 1.23 else 1.57 * (r_p ** 1.25)
    v_esc = 11.19 * np.sqrt(m_p / r_p)
    rho = 5.51 * (m_p / (r_p ** 3.0))
    
    esi_rho = (1.0 - abs((rho - RHO_EARTH) / (rho + RHO_EARTH))) ** W_DENSITY
    esi_v = (1.0 - abs((v_esc - V_ESCAPE) / (v_esc + V_ESCAPE))) ** W_ESCAPE
    
    # Toplam Geometrik Ortalama ESI
    esi_total = (esi_r * esi_t * esi_rho * esi_v) ** (1.0 / 4.0)
    return round(float(esi_total), 4)

print("="*75)
print("HASSAS ESI (EARTH SIMILARITY INDEX) TARAMASI BAŞLADI")
print("="*75)

# Tüm discovery ve benchmark dosyalarını topla
files = glob.glob("benchmarks/*.csv") + glob.glob("outputs_discovery/*.csv")

candidate_list = []

for f in files:
    try:
        df = pd.read_csv(f)
        r_col = next((c for c in df.columns if 'radius' in c.lower() or 'rp' in c.lower()), None)
        t_col = next((c for c in df.columns if 'teq' in c.lower() or 'temperature' in c.lower() or 'eq' in c.lower()), None)
        p_col = next((c for c in df.columns if 'period' in c.lower()), None)
        id_col = next((c for c in df.columns if 'tic' in c.lower() or 'target' in c.lower() or 'source' in c.lower()), None)
        snr_col = next((c for c in df.columns if 'snr' in c.lower()), None)
        fpp_col = next((c for c in df.columns if 'fpp' in c.lower()), None)
        
        if r_col and t_col and id_col:
            for _, row in df.iterrows():
                try:
                    rp = float(row[r_col])
                    teq = float(row[t_col])
                    period = float(row[p_col]) if p_col else 0.0
                    tic_id = str(row[id_col])
                    snr = float(row[snr_col]) if snr_col and not pd.isna(row[snr_col]) else 10.0
                    fpp = float(row[fpp_col]) if fpp_col and not pd.isna(row[fpp_col]) else 0.0
                    
                    # Düzenleme: Eğer Rp Earth cinsinden değilse dönüştür
                    if rp > 50: # ppm cinsinden depth geldiyse atla
                        continue
                    
                    esi_score = calc_esi(rp, teq)
                    
                    if esi_score >= 0.70 and fpp < 0.05 and snr >= 6.0:
                        candidate_list.append({
                            "TIC_ID": tic_id,
                            "ESI_Score": esi_score,
                            "Rp_Earth": rp,
                            "Teq_K": teq,
                            "Period_days": period,
                            "SNR": snr,
                            "FPP": fpp,
                            "Source_File": Path(f).name
                        })
                except Exception:
                    continue
    except Exception:
        continue

# JSON dosyalarını da tara
json_files = glob.glob("outputs_discovery/json/*.json") + glob.glob("outputs_habitable_search/json/*.json")
for jf in json_files:
    try:
        with open(jf, 'r') as jfile:
            data = json.load(jfile)
            rp = data.get("derived", {}).get("planet_radius_rearth", 0)
            teq = data.get("derived", {}).get("equilibrium_temperature_k", 0)
            period = data.get("parameters", {}).get("period_days", 0)
            tic_id = data.get("target", {}).get("source_id", "")
            snr = data.get("quality", {}).get("snr_adopted", 10.0)
            fpp = data.get("vetting", {}).get("fpp", 0.0)
            
            esi_score = calc_esi(rp, teq)
            if esi_score >= 0.70 and fpp < 0.05:
                candidate_list.append({
                    "TIC_ID": tic_id,
                    "ESI_Score": esi_score,
                    "Rp_Earth": rp,
                    "Teq_K": teq,
                    "Period_days": period,
                    "SNR": snr,
                    "FPP": fpp,
                    "Source_File": Path(jf).name
                })
    except Exception:
        continue

# Sonuçları temizle ve sırala
res_df = pd.DataFrame(candidate_list).drop_duplicates(subset=["TIC_ID"]).sort_values(by="ESI_Score", ascending=False)

out_csv = Path("outputs_habitable_search/high_esi_earth_twins.csv")
out_csv.parent.mkdir(parents=True, exist_ok=True)
res_df.to_csv(out_csv, index=False)

print(f"\n🎉 TARAMA TAMAMLANTI! Toplam {len(res_df)} adet ESI >= 0.70 Aday Bulundu.")
print("\n--- EN YÜKSEK ESI SKORLU LK 10 HEDEF ---")
print(res_df.head(10).to_string(index=False))
