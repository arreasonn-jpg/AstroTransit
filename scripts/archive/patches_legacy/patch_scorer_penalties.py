"""
scorer.py - Anomali ve fiziksel tutarsizlik durumunda
skorlarda ciddi ceza uygulanmasi.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
scorer_file = project_root / "astrotransit" / "quality" / "scorer.py"


def main():
    if not scorer_file.exists():
        print("HATA: scorer.py bulunamadi")
        return 1

    shutil.copy(scorer_file, scorer_file.with_suffix(".py.penalty_backup"))
    print("OK Yedek: scorer.py.penalty_backup")

    content = scorer_file.read_text(encoding="utf-8")
    n_changes = 0

    # -----------------------------------------------------------------
    # 1. score() metodunun sonunda anomali & FP cezasini guclendir
    # -----------------------------------------------------------------
    old_penalty = """        # ── FP penaltisi ──
        if vetting.is_false_positive:
            total_score *= 0.3"""

    new_penalty = """        # ── FP penaltisi ──
        if vetting.is_false_positive:
            total_score *= 0.3

        # ── Anomali cezasi (her bayrak icin -15 puan) ──
        # Anomaliler ciddi. Her fiziksel disi bulgu skoru dusurmeli.
        is_anomalous_pre, anomaly_flags_pre = self._detect_anomaly(
            candidate, metrics, vetting
        )
        n_anomalies = len(anomaly_flags_pre)
        if n_anomalies > 0:
            # Her anomali -15 puan, maks -60
            anomaly_penalty = min(60.0, n_anomalies * 15.0)
            total_score = max(0.0, total_score - anomaly_penalty)

        # ── Fiziksel skor dusukse ek ceza ──
        # physical_consistency < 60 ise ciddi problem
        physical_comp = next(
            (c for c in components if c.name == "physical_consistency"),
            None,
        )
        if physical_comp is not None and physical_comp.score < 60:
            # Skor cezasi: fiziksel skor ne kadar dusukse o kadar ceza
            phys_penalty = (60 - physical_comp.score) * 0.5
            total_score = max(0.0, total_score - phys_penalty)

        # ── Cascade tutarsizligi cezasi ──
        # Cascade onaylamamissa 50den yukari cikmasin
        if not candidate.confirmed:
            total_score = min(total_score, 50.0)"""

    if old_penalty in content and "n_anomalies * 15.0" not in content:
        content = content.replace(old_penalty, new_penalty)
        print("OK Anomali ve fiziksel ceza sistemi eklendi")
        n_changes += 1

    # -----------------------------------------------------------------
    # 2. Fiziksel tutarlilik daha katı hale getir
    # -----------------------------------------------------------------
    # Rp/Rs > 0.2 zaten supheli olmali (Jupiter/Gunes = 0.10)
    old_rprs_check = """        # 4. Rp/Rs cok buyukse EB supheli
        if rp_rs > 0.3:
            flags.append(f"Rp/Rs={rp_rs:.3f} > 0.3 (EB supheli)")
            penalties += 30.0"""

    new_rprs_check = """        # 4. Rp/Rs cok buyukse EB supheli
        # Jupiter/Gunes ~ 0.10, cok nadir yildizsi cisimler > 0.2
        if rp_rs > 0.3:
            flags.append(f"Rp/Rs={rp_rs:.3f} > 0.3 (EB supheli)")
            penalties += 40.0
        elif rp_rs > 0.2:
            flags.append(f"Rp/Rs={rp_rs:.3f} > 0.2 (buyuk gezegen supheli)")
            penalties += 20.0"""

    if old_rprs_check in content:
        content = content.replace(old_rprs_check, new_rprs_check)
        print("OK Rp/Rs kontrolu sikilastirildi")
        n_changes += 1

    # -----------------------------------------------------------------
    # 3. Süre/periyot orani daha esnek olmali (kısa periyotlarda)
    # -----------------------------------------------------------------
    # Zaten iyi, dokunmayacagiz

    # -----------------------------------------------------------------
    # Kaydet
    # -----------------------------------------------------------------
    if n_changes > 0:
        scorer_file.write_text(content, encoding="utf-8")
        print(f"\nOK {n_changes} degisiklik kaydedildi")
    else:
        print("\nBILGI Degisiklik gerekmedi (belki zaten uygulanmis)")

    # Doğrulama
    print("\n-- Dogrulama --")
    final = scorer_file.read_text(encoding="utf-8")
    checks = [
        ("n_anomalies * 15.0", "anomali cezasi"),
        ("total_score = min(total_score, 50.0)", "cascade tutarsizlik cezasi"),
        ("rp_rs > 0.2", "sikilasrilmis Rp/Rs kontrolu"),
    ]
    all_ok = True
    for pattern, name in checks:
        if pattern in final:
            print(f"  OK {name}")
        else:
            print(f"  FAIL {name}")
            all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())