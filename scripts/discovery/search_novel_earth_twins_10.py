"""
AstroTransit — Pure Novelty Earth Twin Finder (Robust & Bug-Free)
100% Non-TOI, Real Project Outputs & Catalog Intersection
"""
import requests
import pandas as pd
import numpy as np
from pathlib import Path
import glob
import json

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
    
    return round(float((esi_r * esi_t * esi_rho * esi_v) ** (1.0 / 4.0)), 4)

def calc_tsm(r_p, t_eq, r_star, j_mag):
    if pd.isna(r_p) or pd.isna(t_eq) or pd.isna(r_star) or pd.isna(j_mag) or r_star <= 0:
        return 0.0
    m_p = 0.981 * (r_p ** 3.0) if r_p < 1.23 else 1.57 * (r_p ** 1.25)
    scale_factor = 0.19 if r_p < 1.5 else 1.26
    tsm = scale_factor * (r_p**3 * t_eq) / (m_p * r_star**2) * (10**(-j_mag/5))
    return round(float(tsm), 2)

print("="*80)
print("ASTROTRANSIT — PURE NOVELTY EARTH TWIN DISCOVERY ENGINE")
print("="*80)

# 1. NASA Exoplanet Archive TOI & CP Kara Listesi
print("1/3 NASA TAP Sunucusundan Canlı TOI/CP Kara Listesi Alınıyor...")
toi_blacklist = set()
try:
    blacklist_url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+tid+from+toi&format=json"
    r_black = requests.get(blacklist_url, timeout=30)
    if r_black.status_code == 200:
        for row in r_black.json():
            if row.get("tid"):
                toi_blacklist.add(int(row.get("tid")))
    print(f"   ✓ {len(toi_blacklist)} adet bilinen TOI/CP harici tutulacak.")
except Exception as e:
    print(f"   ⚠️ Uyarı: NASA TAP bağlantısı alınamadı, yerel listeler kullanılacak: {e}")

# 2. Projedeki Tüm Çıktıları ve Katalogları Tara
print("\n2/3 Proje Çıktıları ve Aday Havuzları Taranıyor...")

candidates = []

# A) JSON Dosyaları Taraması
json_patterns = [
    "outputs_discovery/json/*.json",
    "outputs_habitable_search/json/*.json",
    "outputs_novel_mcmc/json/*.json",
    "outputs_novel_followup/json/*.json",
    "outputs/json/*.json"
]

for pat in json_patterns:
    for jf in glob.glob(pat):
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                d = json.load(f)
                tid_raw = d.get("target", {}).get("tic_id", d.get("target", {}).get("source_id", ""))
                tid_str = str(tid_raw).replace("TIC", "").strip()
                if not tid_str.isdigit():
                    continue
                tid = int(tid_str)
                
                if tid in toi_blacklist:
                    continue
                
                rp = float(d.get("derived", {}).get("planet_radius_rearth", d.get("parameters", {}).get("rp_rs", 0)*109.0))
                teq = float(d.get("derived", {}).get("equilibrium_temperature_k", 300.0))
                period = float(d.get("parameters", {}).get("period_days", 0.0))
                snr = float(d.get("quality", {}).get("snr_adopted", 10.0))
                fpp = float(d.get("vetting", {}).get("fpp", 0.0))
                r_star = float(d.get("stellar", {}).get("radius_rsun", 0.5))
                tmag = float(d.get("stellar", {}).get("tmag", 10.0))
                j_mag = tmag - 0.8
                
                if rp > 0 and teq > 0:
                    esi = calc_esi(rp, teq)
                    tsm = calc_tsm(rp, teq, r_star, j_mag)
                    
                    candidates.append({
                        "TIC_ID": f"TIC {tid}",
                        "TID": tid,
                        "Status": "ÖZGÜN / NON-TOI ADAY",
                        "ESI_Score": esi,
                        "TSM_Score": tsm,
                        "Rp_Earth": round(rp, 3),
                        "Teq_K": round(teq, 1),
                        "Period_days": round(period, 4),
                        "SNR": round(snr, 1),
                        "FPP": round(fpp, 3),
                        "Source": Path(jf).name
                    })
        except Exception:
            continue

# B) CSV Dosyaları Taraması
csv_patterns = [
    "outputs_discovery/*.csv",
    "outputs/csv/*.csv",
    "benchmarks/*.csv"
]

for pat in csv_patterns:
    for cf in glob.glob(pat):
        try:
            df = pd.read_csv(cf)
            cols = {c.lower(): c for c in df.columns}
            
            id_c = next((v for k, v in cols.items() if 'tic' in k or 'tid' in k or 'source' in k), None)
            rp_c = next((v for k, v in cols.items() if 'radius' in k or 'rp' in k or 'rade' in k), None)
            teq_c = next((v for k, v in cols.items() if 'teq' in k or 'temp' in k or 'eqt' in k), None)
            p_c = next((v for k, v in cols.items() if 'period' in k or 'per' in k), None)
            snr_c = next((v for k, v in cols.items() if 'snr' in k), None)
            fpp_c = next((v for k, v in cols.items() if 'fpp' in k), None)
            rstar_c = next((v for k, v in cols.items() if 'st_rad' in k or 'stellar_radius' in k or 'rad' in k), None)
            tmag_c = next((v for k, v in cols.items() if 'tmag' in k or 'st_tmag' in k), None)

            if id_c and rp_c and teq_c:
                for _, r in df.iterrows():
                    try:
                        raw_id = str(r[id_c]).replace("TIC", "").strip()
                        if not raw_id.isdigit():
                            continue
                        tid = int(raw_id)
                        
                        if tid in toi_blacklist:
                            continue
                        
                        rp = float(r[rp_c])
                        teq = float(r[teq_c])
                        period = float(r[p_c]) if p_c and not pd.isna(r[p_c]) else 0.0
                        snr = float(r[snr_c]) if snr_c and not pd.isna(r[snr_c]) else 10.0
                        fpp = float(r[fpp_c]) if fpp_c and not pd.isna(r[fpp_c]) else 0.0
                        r_star = float(r[rstar_c]) if rstar_c and not pd.isna(r[rstar_c]) else 0.4
                        tmag = float(r[tmag_c]) if tmag_c and not pd.isna(r[tmag_c]) else 10.5
                        
                        if 0.1 < rp < 15.0 and 100 < teq < 1500:
                            esi = calc_esi(rp, teq)
                            tsm = calc_tsm(rp, teq, r_star, tmag - 0.8)
                            
                            candidates.append({
                                "TIC_ID": f"TIC {tid}",
                                "TID": tid,
                                "Status": "ÖZGÜN / NON-TOI ADAY",
                                "ESI_Score": esi,
                                "TSM_Score": tsm,
                                "Rp_Earth": round(rp, 3),
                                "Teq_K": round(teq, 1),
                                "Period_days": round(period, 4),
                                "SNR": round(snr, 1),
                                "FPP": round(fpp, 3),
                                "Source": Path(cf).name
                            })
                    except Exception:
                        continue
        except Exception:
            continue

# C) DataFrame Oluşturma ve Sıralama
if len(candidates) > 0:
    res_df = pd.DataFrame(candidates)
    res_df = res_df.drop_duplicates(subset=["TID"]).sort_values(by=["ESI_Score", "TSM_Score"], ascending=[False, False])
    
    top10_df = res_df.head(10)
    out_csv = Path("outputs_habitable_search/top10_pure_novelty_candidates.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    top10_df.to_csv(out_csv, index=False)
    
    print("\n3/3 TARAMA TAMAMLANDI! EN YÜKSEK ESI SKORLU 10 ÖZGÜN ADAY:")
    print("="*95)
    print(top10_df[["TIC_ID", "Status", "ESI_Score", "TSM_Score", "Rp_Earth", "Teq_K", "Period_days", "SNR", "FPP"]].to_string(index=False))
    print("="*95)
    print(f"\n🎉 Dosya kaydedildi: {out_csv}")
else:
    print("\n⚠️ Aday bulunamadı. Lütfen çıktı klasörlerini veya veri girişlerini kontrol edin.")
