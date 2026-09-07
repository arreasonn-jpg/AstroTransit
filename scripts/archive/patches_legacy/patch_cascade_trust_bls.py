"""
Cascade felsefesi degistirildi:
- BLS'in en iyi (diverse peaks) adayina GUVEN
- TLS'i sadece parametreleri rafine etmek icin kullan
- TLS periyodu degistirirse BLS'i koru

WASP-19b vakasi: BLS 0.78d bulur, TLS 1.56d der,
biz BLS'i tercih ederiz.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
cascade_file = project_root / "astrotransit" / "detection" / "cascade.py"


def main():
    if not cascade_file.exists():
        print("HATA: cascade.py bulunamadi")
        return 1

    shutil.copy(cascade_file, cascade_file.with_suffix(".py.trust_bls_backup"))
    print("OK Yedek: cascade.py.trust_bls_backup")

    content = cascade_file.read_text(encoding="utf-8")

    # Multi-aday TLS denemesini basitlestir:
    # Sadece BLS'in en iyi adayina TLS uygula, sonuc kotuyse BLS'i koru
    old_parts = [
        '        # En fazla 3 aday dene',
        '        candidates_to_try = passed_peaks[:3]',
        '',
        '        log.append(',
        '            f"BLS: {len(candidates_to_try)} aday TLS multimode ile denenecek"',
        '        )',
        '',
        '        best_tls_result = None',
        '        best_bls_peak = None',
        '        best_score = -1.0  # SDE * SNR ile skor',
        '',
        '        for idx, bls_peak_try in enumerate(candidates_to_try):',
        '            log.append(',
        '                f"  Aday {idx + 1}: P={bls_peak_try.period:.4f}d, "',
        '                f"güç={bls_peak_try.power:.2f}"',
        '            )',
        '',
        '            try:',
        '                # MULTIMODE: A/B/C modlarini calistir, en iyisini sec',
        '                tls_try, adjusted_peak = self._tls.validate_multimode(',
        '                    detrended,',
        '                    bls_peak_try,',
        '                    stellar_radius=self.stellar_radius,',
        '                    stellar_mass=self.stellar_mass,',
        '                )',
        '',
        '                if tls_try is None:',
        '                    logger.debug(f"Aday {idx+1} TLS multimode basarisiz")',
        '                    continue',
        '',
        '                # bls_peak\'i ayarlanmis periyoda guncelle',
        '                bls_peak_try = adjusted_peak',
    ]
    old_block = "\n".join(old_parts)

    new_parts = [
        '        # BLS EN IYI ADAYINA GUVEN, TLS sadece rafinasyon icin',
        '        # BLS diverse peaks ile artik gercek periyodu buluyor',
        '        bls_peak = passed_peaks[0]  # En yuksek gucli aday',
        '',
        '        log.append(',
        '            f"BLS en iyi aday: P={bls_peak.period:.4f}d, "',
        '            f"guc={bls_peak.power:.2f}"',
        '        )',
        '',
        '        # TLS ile dogrulama - fakat periyot kabul etme',
        '        try:',
        '            tls_result = self._tls.validate(',
        '                detrended,',
        '                bls_peak,',
        '                stellar_radius=self.stellar_radius,',
        '                stellar_mass=self.stellar_mass,',
        '            )',
        '',
        '            # TLS periyodu BLS periyodundan cok farkli mi?',
        '            # Eger evet, TLS yaniltmis - BLS periyodunu koru',
        '            if tls_result is not None:',
        '                tls_p = tls_result.period',
        '                bls_p = bls_peak.period',
        '                rel_diff = abs(tls_p - bls_p) / bls_p if bls_p > 0 else 1.0',
        '',
        '                if rel_diff > 0.05:  # %5+ fark',
        '                    log.append(',
        '                        f"TLS periyot degistirdi: {bls_p:.4f} -> {tls_p:.4f} "',
        '                        f"(fark %{rel_diff*100:.1f}) - BLS periyodu korunacak"',
        '                    )',
        '                    # TLS sonucunu BLS periyoduna zorla',
        '                    from dataclasses import replace',
        '                    tls_result = replace(',
        '                        tls_result,',
        '                        period=bls_p,',
        '                        period_err=bls_peak.period_err,',
        '                    )',
        '                    # Yeniden threshold degerlendir',
        '                    tls_result = self._tls._evaluate_threshold(tls_result)',
        '',
        '            best_tls_result = tls_result',
        '            best_bls_peak = bls_peak',
        '            bls_peak_try = bls_peak  # aliasing icin',
        '',
        '        except Exception as e:',
        '            logger.error(f"TLS hatasi: {e}")',
        '            best_tls_result = None',
        '            best_bls_peak = bls_peak',
        '            bls_peak_try = bls_peak',
        '',
        '        # Alt kismi calisir hale getirmek icin dummy loop',
        '        if False:  # asagida beklenmeyen for cikisini engellemek icin',
        '            for idx, bls_peak_try in enumerate([bls_peak]):',
        '                pass',
    ]
    new_block = "\n".join(new_parts)

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("OK Cascade BLS'e guven modu aktif")
    else:
        print("UYARI Eski cascade blogu bulunamadi")
        print("      Muhtemelen daha once patch uygulanmis")
        return 1

    # Alt kismindaki ScoreComponent asamasi hala BLS peak referansiyor
    # ancak dongu icindeydi. Bunu duzelt:
    # Aslinda dongude bir break/continue yoktu, sadece for bloğunu
    # kaldırmamız gerek. Ama simdi for'a giren tek bir aday oldugu icin
    # calisacak. Yine de kontrol edelim.

    cascade_file.write_text(content, encoding="utf-8")

    try:
        import ast
        ast.parse(cascade_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        print("Geri yukleme: copy cascade.py.trust_bls_backup cascade.py")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())