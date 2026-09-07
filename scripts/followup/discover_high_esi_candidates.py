"""
NASA Exoplanet Archive & TESS TOI Canlı ESI Tarayıcı
Doğrudan ESI > 0.80 - 0.95 (Dünya kizi) Adaylarını Çeker
"""
import requests
import pandas as pd
import numpy as np
from pathlib import Path

# ESI Sabitleri (Schulze-Makuch 2011)
R_EARTH = 1.00
T_EARTH = 288.15
W_RADIUS = 0.57
W_DENSITY = 1.07
W_ESCAPE = 0.70
W_TEMP = 5.58

def calc_esi(r_p, t_eq):
    if pd.isna(r_p) or pd.isna(t_eq) or r_p <= 0 or t_eq <= 0:
        return 0.0
    
    esi_r = (1.0 - abs((r_p - R_EARTH) / (r_p + R_EARTH))) ** W_RADIUS
    esi_t = (1.0 - abs((t_eq - T_EARTH) / (t_eq + T_EARTH))) ** W_TEMP
    
    m_p = 0.981 * (r_p ** 3.0) if r_p < 1.23 else 1.57 * (r_p ** 1.25)
    v_esc = 11.19 * np.sqrt(m_p / r_p)
    rho = 5.51 * (m_p / (r_p ** 3.0))
    
    esi_rho = (1.0 - abs((rho - 5.51) / (rho + 5.51))) ** W_DENSITY
    esi_v = (1.0 - abs((v_esc - 11.19) / (v_esc + 11.19))) ** W_ESCAPE
    
    esi_total = (esi_r * esi_t * esi_rho * esi_v) ** (1.0 / 4.0)
    return round(float(esi_total), 4)

print("="*75)
print("NASA EXOPLANET ARCHIVE - DÜNYA KZ (ESI > 0.80) CANLI SORUSU")
print("="*75)

# NASA TAP SQL Sorgusu
query = """
SELECT 
    toi, tid, tfopwg_disp, pl_orbper, pl_trandep, pl_rade, pl_eqt, 
    st_teff, st_rad, st_tmag
FROM toi
WHERE pl_rade BETWEEN 0.75 AND 1.35
  AND pl_eqt BETWEEN 210 AND 320
  AND st_teff BETWEEN 2600 AND 4200
  AND st_tmag < 13.0
"""

url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
params = {
    "query": query,
    "format": "json"
}

print("NASA TAP sunucusuna bağlanılıyor...")
response = requests.get(url, params=params, timeout=30)

if response.status_code == 200:
    data = response.json()
    df = pd.DataFrame(data)
    print(f"Sorgu başarılı! {len(df)} adet potansiyel yaşanabilir bölge adayı çekildi.")
    
    results = []
    for _, row in df.iterrows():
        rp = float(row.get("pl_rade", 0))
        teq = float(row.get("pl_eqt", 0))
        esi = calc_esi(rp, teq)
        
        if esi >= 0.78:
            results.append({
                "TOI": str(row.get("toi", "")),
                "TIC_ID": f"TIC {row.get('tid', '')}",
                "Status": str(row.get("tfopwg_disp", "")),
                "ESI_Score": esi,
                "Rp_Earth": rp,
                "Teq_K": teq,
                "Period_days": float(row.get("pl_orbper", 0)),
                "Teff_K": float(row.get("st_teff", 0)),
                "R_star": float(row.get("st_rad", 0)),
                "Tmag": float(row.get("st_tmag", 0))
            })
            
    res_df = pd.DataFrame(results).sort_values(by="ESI_Score", ascending=False)
    
    out_csv = Path("benchmarks/earth_twins_nasa_candidates.csv")
    res_df.to_csv(out_csv, index=False)
    
    print("\n🎉 YÜKSEK ESI SKORLU DÜNYA KZ ADAYLARI YÜKLEND:")
    print("="*75)
    print(res_df.head(10).to_string(index=False))
    print("="*75)
else:
    print(f"Hata: {response.status_code}")
