"""
scorer.py'ye periyot uyumu bileşenini ekler.
Çalıştırma: python scripts/patch_scorer.py
"""

from __future__ import annotations

import sys
import shutil
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
scorer_file = project_root / "astrotransit" / "quality" / "scorer.py"


def main():
    if not scorer_file.exists():
        print(f"HATA: {scorer_file} bulunamadi")
        return 1

    # Yedek al
    backup = scorer_file.with_suffix(".py.backup")
    shutil.copy(scorer_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = scorer_file.read_text(encoding="utf-8")

    n_changes = 0

    # ─────────────────────────────────────
    # 1. WEIGHTS sözlüğünü güncelle
    # ─────────────────────────────────────
    old_weights = '''    WEIGHTS = {
        "snr": 0.30,
        "completeness": 0.15,
        "transit_quality": 0.20,
        "vetting": 0.25,
        "residual": 0.10,
    }'''

    new_weights = '''    WEIGHTS = {
        "snr": 0.25,
        "completeness": 0.10,
        "transit_quality": 0.20,
        "vetting": 0.20,
        "residual": 0.10,
        "period_consistency": 0.15,
    }'''

    if old_weights in content:
        content = content.replace(old_weights, new_weights)
        print("OK WEIGHTS sozlugu guncellendi")
        n_changes += 1
    else:
        print("UYARI WEIGHTS bulunamadi (belki zaten guncel)")

    # ─────────────────────────────────────
    # 2. Residual bileşeninden sonra period_consistency ekle
    # ─────────────────────────────────────
    marker = '''components.append(ScoreComponent(
            name="residual",
            raw_value=residual_rms,
            score=residual_score,
            weight=self.WEIGHTS["residual"],
            contribution=residual_score * self.WEIGHTS["residual"],
        ))'''

    new_component_addition = marker + '''

        # ── Bilesen 6: Periyot Uyumu (BLS vs TLS) ──
        period_consistency_score = self._compute_period_consistency_score(
            candidate
        )
        components.append(ScoreComponent(
            name="period_consistency",
            raw_value=self._compute_period_relative_diff(candidate),
            score=period_consistency_score,
            weight=self.WEIGHTS["period_consistency"],
            contribution=period_consistency_score * self.WEIGHTS["period_consistency"],
        ))'''

    if 'name="period_consistency"' in content:
        print("BILGI period_consistency bileseni zaten var")
    elif marker in content:
        content = content.replace(marker, new_component_addition)
        print("OK period_consistency bileseni eklendi")
        n_changes += 1
    else:
        print("UYARI Residual bileseni bulunamadi")

    # ─────────────────────────────────────
    # 3. Yeni yardımcı metodları ekle
    # ─────────────────────────────────────
    if "def _compute_period_consistency_score" in content:
        print("BILGI Yardimci metodlar zaten var")
    else:
        # _normalize_linear metodundan hemen önce ekle
        # Marker: satır başında 4 boşluk + @staticmethod, sonra _normalize_linear tanımı
        old_block = """    @staticmethod
    def _normalize_linear("""

        new_block = """    @staticmethod
    def _compute_period_relative_diff(candidate) -> float:
        \"\"\"
        BLS ve TLS periyotlari arasindaki goreli farki hesaplar.

        Harmonik toleransi ile en yakin faktoru kullanir.
        Sonuc: 0.0 = mukemmel uyum, 0.10 = %10 fark.
        \"\"\"

        from astrotransit.detection.cascade import CascadeStatus

        if candidate.status in (
            CascadeStatus.BLS_FAILED,
            CascadeStatus.TLS_FAILED,
            CascadeStatus.ERROR,
        ):
            return 1.0

        if (candidate.bls_result is None
                or candidate.bls_result.best is None
                or candidate.tls_result is None):
            return 0.0

        bls_p = candidate.bls_result.best.period
        tls_p = candidate.tls_result.period

        if bls_p <= 0 or tls_p <= 0:
            return 1.0

        best_diff = float('inf')
        for factor in [1/3, 1/2, 1.0, 2.0, 3.0]:
            expected = bls_p * factor
            if expected > 0:
                diff = abs(expected - tls_p) / expected
                if diff < best_diff:
                    best_diff = diff

        return float(best_diff)

    @staticmethod
    def _compute_period_consistency_score(candidate) -> float:
        \"\"\"
        Periyot uyum skoru uretir (0-100).

        %0 fark   -> 100 puan
        %1 fark   -> 90 puan
        %5 fark   -> 50 puan
        %10 fark  -> 20 puan

        Cascade PERIOD_MISMATCH ise ek ceza.
        \"\"\"

        from astrotransit.detection.cascade import CascadeStatus

        rel_diff = CandidateScorer._compute_period_relative_diff(candidate)

        score = 100.0 * float(np.exp(-30.0 * rel_diff))

        if candidate.status == CascadeStatus.PERIOD_MISMATCH:
            score *= 0.3

        if candidate.status in (
            CascadeStatus.BLS_FAILED,
            CascadeStatus.TLS_FAILED,
            CascadeStatus.ERROR,
        ):
            score = min(score, 20.0)

        return float(np.clip(score, 0.0, 100.0))

    @staticmethod
    def _normalize_linear("""

        if old_block in content:
            content = content.replace(old_block, new_block)
            print("OK Yardimci metodlar eklendi")
            n_changes += 1
        else:
            print("UYARI _normalize_linear marker bulunamadi")

    # ─────────────────────────────────────
    # Kaydet
    # ─────────────────────────────────────
    if n_changes > 0:
        scorer_file.write_text(content, encoding="utf-8")
        print(f"\nOK Dosya guncellendi ({n_changes} degisiklik)")
    else:
        print("\nBILGI Hicbir degisiklik gerekmedi")

    # ─────────────────────────────────────
    # Doğrulama
    # ─────────────────────────────────────
    print("\n── Dogrulama ──")

    checks = [
        ('period_consistency": 0.15', "WEIGHTS ayarli"),
        ('name="period_consistency"', "bilesen eklenmis"),
        ('def _compute_period_relative_diff', "diff metodu var"),
        ('def _compute_period_consistency_score', "score metodu var"),
    ]

    all_ok = True
    final_content = scorer_file.read_text(encoding="utf-8")
    for pattern, name in checks:
        if pattern in final_content:
            print(f"  OK {name}")
        else:
            print(f"  FAIL {name}")
            all_ok = False

    if all_ok:
        print("\nTUM DEGISIKLIKLER BASARILI")
        print("\nSonraki adim:")
        print("  python -c \"from astrotransit.quality.scorer import CandidateScorer; print('OK')\"")
        print("  python scripts/run_batch_test.py --quick --no-viz")
        return 0
    else:
        print("\nBAZI DEGISIKLIKLER EKSIK")
        print("Yedegi geri yuklemek icin:")
        print(f"  copy {backup} {scorer_file}")
        return 1


if __name__ == "__main__":
    sys.exit(main())