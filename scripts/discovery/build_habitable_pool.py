import pandas as pd
from pathlib import Path
from loguru import logger

def build_habitable_target_pool():
    logger.info("Habitable Zone M-Dwarf hedef havuzu taranıyor...")
    out_path = Path("benchmarks/discovery_targets_habitable_m_dwarfs.csv")
    base_file = Path("benchmarks/discovery_targets_v4_small_cool_1000_dedup_multisector2.csv")
    
    if base_file.exists():
        df = pd.read_csv(base_file)
        logger.info(f"Temel havuz yüklendi: {len(df)} hedef")
        logger.info(f"Mevcut kolonlar: {list(df.columns[:10])} ...")
        
        # Kolon isimlerini dinamik olarak bul
        teff_col = next((c for c in df.columns if 'teff' in c.lower()), None)
        tmag_col = next((c for c in df.columns if 'tmag' in c.lower() or 't_mag' in c.lower()), None)
        
        if not teff_col:
            raise KeyError("Tabloda 'teff' değerini içeren bir kolon bulunamadı!")
            
        logger.info(f"Kullanılan Teff kolonu: '{teff_col}' | Tmag kolonu: '{tmag_col}'")
        
        # Filtreleme
        mask = (df[teff_col] >= 2800) & (df[teff_col] <= 4200)
        if tmag_col:
            mask &= (df[tmag_col] <= 12.0)
            
        habitable_pool = df[mask].copy()
        logger.info(f"Filtrelenmiş Yaşanabilir M-Cüce Hedef Sayısı: {len(habitable_pool)}")
        
        habitable_pool.to_csv(out_path, index=False)
        print(f"\n🎉 Kayıt tamamlandı: {out_path} ({len(habitable_pool)} hedef)")
    else:
        logger.warning(f"{base_file} bulunamadı.")

if __name__ == "__main__":
    build_habitable_target_pool()
