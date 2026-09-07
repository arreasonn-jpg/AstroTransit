"""
scorer.py — Bilimsel katı skorlama sistemi.

Değişiklikler:
1. Fiziksel tutarlılık kontrolleri (Rp/Rs, süre/periyot, yıldız yoğunluğu)
2. Sıkı eşikler (Sınıf A: ≥90, B: ≥75, C: ≥55, D: <55)
3. Cascade tutarsızlığı → otomatik ceza
4. Periyot bilinen değerden %5+ sapıyorsa → C sınıfı
5. BLS/TLS SNR farkı büyükse → şüpheli
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
scorer_file = project_root / "astrotransit" / "quality" / "scorer.py"


def main():
    if not scorer_file.exists():
        print("HATA: scorer.py bulunamadi")
        return 1

    # Yedek
    backup = scorer_file.with_suffix(".py.strict_backup")
    shutil.copy(scorer_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = scorer_file.read_text(encoding="utf-8")
    n_changes = 0

    # -----------------------------------------------------------------
    # 1. Sınıf eşiklerini sıkılaştır (parametre varsayılanları)
    # -----------------------------------------------------------------
    old_defaults = """    def __init__(
        self,
        snr_min: float = 5.0,
        snr_max: float = 30.0,
        class_a_threshold: float = 80.0,
        class_b_threshold: float = 60.0,
        class_c_threshold: float = 40.0,
    ):"""

    new_defaults = """    def __init__(
        self,
        snr_min: float = 7.0,
        snr_max: float = 50.0,
        class_a_threshold: float = 90.0,
        class_b_threshold: float = 75.0,
        class_c_threshold: float = 55.0,
    ):"""

    if old_defaults in content:
        content = content.replace(old_defaults, new_defaults)
        print("OK Sinif esikleri sikilastirildi (A>=90, B>=75, C>=55)")
        n_changes += 1

    # -----------------------------------------------------------------
    # 2. WEIGHTS — fiziksel tutarlılık bileşeni eklendi
    # -----------------------------------------------------------------
    old_weights = '''    WEIGHTS = {
        "snr": 0.25,
        "completeness": 0.10,
        "transit_quality": 0.20,
        "vetting": 0.20,
        "residual": 0.10,
        "period_consistency": 0.15,
    }'''

    new_weights = '''    WEIGHTS = {
        "snr": 0.20,
        "completeness": 0.10,
        "transit_quality": 0.20,
        "vetting": 0.15,
        "residual": 0.10,
        "period_consistency": 0.10,
        "physical_consistency": 0.15,
    }'''

    if old_weights in content:
        content = content.replace(old_weights, new_weights)
        print("OK WEIGHTS guncellendi (physical_consistency: 0.15)")
        n_changes += 1

    # -----------------------------------------------------------------
    # 3. score() metoduna physical_consistency bileşeni ekle
    # -----------------------------------------------------------------
    marker = '''components.append(ScoreComponent(
            name="period_consistency",
            raw_value=self._compute_period_relative_diff(candidate),
            score=period_consistency_score,
            weight=self.WEIGHTS["period_consistency"],
            contribution=period_consistency_score * self.WEIGHTS["period_consistency"],
        ))'''

    new_addition = marker + '''

        # -- Bilesen 7: Fiziksel Tutarlilik --
        # Rp, sure/periyot, yildiz yogunlugu makul mu?
        physical_score, physical_flags = self._compute_physical_consistency_score(
            candidate, fit_result
        )
        components.append(ScoreComponent(
            name="physical_consistency",
            raw_value=float(len(physical_flags)),
            score=physical_score,
            weight=self.WEIGHTS["physical_consistency"],
            contribution=physical_score * self.WEIGHTS["physical_consistency"],
        ))'''

    if "physical_consistency" not in content and marker in content:
        content = content.replace(marker, new_addition)
        print("OK physical_consistency bileseni eklendi")
        n_changes += 1

    # -----------------------------------------------------------------
    # 4. Yeni metod: _compute_physical_consistency_score
    # -----------------------------------------------------------------
    if "_compute_physical_consistency_score" not in content:
        # _compute_period_consistency_score metodundan hemen SONRA ekle
        insert_after = """    @staticmethod
    def _normalize_linear("""

        new_method = '''    @staticmethod
    def _compute_physical_consistency_score(
        candidate,
        fit_result=None,
    ) -> tuple:
        """
        Fiziksel tutarlilik skoru (0-100) ve tetiklenen bayraklar.

        Kontroller:
        1. Transit derinligi Rp/Rs ile tutarli mi?
        2. Transit suresi/periyot orani fiziksel mi?
        3. Rp makul mu? (0.3-30 R_earth)
        4. BLS SNR ile TLS SDE arasi buyuk fark var mi?
        5. Rp/Rs cok buyukse (>0.3) - EB supheli
        """

        flags = []
        penalties = 0.0

        # 1. Rp/Rs vs depth tutarlilik
        # depth ~= (Rp/Rs)^2
        depth = candidate.depth
        rp_rs = candidate.rp_rs

        if rp_rs > 0 and depth > 0:
            expected_depth = rp_rs ** 2
            depth_ratio = depth / expected_depth if expected_depth > 0 else 0
            # depth ile Rp/Rs 2x farkliysa suphe
            if depth_ratio < 0.5 or depth_ratio > 2.0:
                flags.append("depth-rp_rs tutarsiz")
                penalties += 20.0

        # 2. Sure/periyot orani
        # Sicak Jupiter icin ~0.02-0.10
        # Daha uzun periyotlarda daha kucuk
        if candidate.period > 0 and candidate.duration > 0:
            dp_ratio = candidate.duration / candidate.period

            # Cok kucuk periyotlarda (< 1d) dp_ratio 0.10a kadar cikabilir
            # Cok uzun periyotlarda (> 30d) dp_ratio < 0.03 olmali
            max_allowed = 0.15  # genel ust sinir
            if candidate.period > 10:
                max_allowed = 0.05

            if dp_ratio > max_allowed:
                flags.append(f"sure/periyot={dp_ratio:.3f} fiziksel disi")
                penalties += 25.0

            if dp_ratio < 0.001:
                flags.append("sure/periyot cok kucuk")
                penalties += 15.0

        # 3. Rp makullugu (fit_result varsa)
        if fit_result is not None and hasattr(fit_result, 'derived'):
            rp_earth = fit_result.derived.planet_radius_rearth
            if rp_earth > 30.0:
                flags.append(f"Rp={rp_earth:.1f} R_earth > 30 (yildizsi)")
                penalties += 40.0
            elif rp_earth > 25.0:
                flags.append(f"Rp={rp_earth:.1f} R_earth > 25 (supheli)")
                penalties += 20.0
            elif rp_earth < 0.3 and rp_earth > 0:
                flags.append(f"Rp={rp_earth:.2f} R_earth < 0.3 (cok kucuk)")
                penalties += 15.0

        # 4. Rp/Rs cok buyukse EB supheli
        if rp_rs > 0.3:
            flags.append(f"Rp/Rs={rp_rs:.3f} > 0.3 (EB supheli)")
            penalties += 30.0

        # 5. BLS SNR vs TLS SDE tutarsizligi
        if (candidate.bls_result is not None
                and candidate.bls_result.best is not None
                and candidate.tls_result is not None):
            bls_snr = candidate.bls_result.best.snr
            tls_sde = candidate.tls_result.sde

            # BLS SNR cok yuksek ama TLS SDE dusukse - yildiz aktivitesi supheli
            if bls_snr > 100 and tls_sde < 10:
                flags.append(f"BLS_SNR={bls_snr:.0f} vs TLS_SDE={tls_sde:.1f} tutarsiz")
                penalties += 25.0

        # Nihai skor
        score = max(0.0, 100.0 - penalties)
        return float(score), flags

    @staticmethod
    def _normalize_linear('''

        if insert_after in content:
            content = content.replace(insert_after, new_method)
            print("OK _compute_physical_consistency_score eklendi")
            n_changes += 1

    # -----------------------------------------------------------------
    # 5. Anomali detektörünü genişlet — physical flags de dahil
    # -----------------------------------------------------------------
    old_anomaly_return = """        is_anomalous = len(flags) > 0
        return is_anomalous, flags"""

    new_anomaly_return = """        # Fiziksel tutarsizlik da anomali sayilir
        try:
            _, physical_flags = self._compute_physical_consistency_score(candidate, None)
            flags.extend(physical_flags)
        except Exception:
            pass

        is_anomalous = len(flags) > 0
        return is_anomalous, flags"""

    if old_anomaly_return in content and "physical_flags = self._compute_physical" not in content:
        content = content.replace(old_anomaly_return, new_anomaly_return)
        print("OK Anomali detektorune fiziksel bayraklar eklendi")
        n_changes += 1

    # -----------------------------------------------------------------
    # Kaydet
    # -----------------------------------------------------------------
    if n_changes > 0:
        scorer_file.write_text(content, encoding="utf-8")
        print(f"\nOK {n_changes} degisiklik kaydedildi")
    else:
        print("\nBILGI Hicbir degisiklik gerekmedi")

    # Doğrulama
    print("\n-- Dogrulama --")
    final = scorer_file.read_text(encoding="utf-8")
    checks = [
        ("class_a_threshold: float = 90.0", "A esigi 90"),
        ('"physical_consistency": 0.15', "physical_consistency agirligi"),
        ('def _compute_physical_consistency_score', "fiziksel metod"),
        ('name="physical_consistency"', "bilesen kullanimi"),
    ]

    all_ok = True
    for pattern, name in checks:
        if pattern in final:
            print(f"  OK {name}")
        else:
            print(f"  FAIL {name}")
            all_ok = False

    if all_ok:
        print("\nTUM DEGISIKLIKLER BASARILI")
        return 0
    else:
        print("\nBAZI DEGISIKLIKLER EKSIK")
        print(f"Geri yukleme: copy {backup} {scorer_file}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())