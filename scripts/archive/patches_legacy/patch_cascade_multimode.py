"""
Faz 1: cascade.py'yi TLS multimode kullanacak sekilde guncelle.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
cascade_file = project_root / "astrotransit" / "detection" / "cascade.py"


def main():
    if not cascade_file.exists():
        print("HATA: cascade.py bulunamadi")
        return 1

    shutil.copy(cascade_file, cascade_file.with_suffix(".py.multimode_backup"))
    print("OK Yedek: cascade.py.multimode_backup")

    content = cascade_file.read_text(encoding="utf-8")

    # Cascade detect metodunda TLS cagrisini bul ve degistir
    old_block = """        # En fazla 3 aday dene
        candidates_to_try = passed_peaks[:3]

        log.append(
            f"BLS: {len(candidates_to_try)} aday TLS ile denenecek"
        )

        best_tls_result = None
        best_bls_peak = None
        best_score = -1.0  # SDE * SNR ile skor

        for idx, bls_peak_try in enumerate(candidates_to_try):
            log.append(
                f"  Aday {idx + 1}: P={bls_peak_try.period:.4f}d, "
                f"güç={bls_peak_try.power:.2f}"
            )

            try:
                tls_try = self._tls.validate(
                    detrended,
                    bls_peak_try,
                    stellar_radius=self.stellar_radius,
                    stellar_mass=self.stellar_mass,
                )"""

    new_block = """        # En fazla 3 aday dene
        candidates_to_try = passed_peaks[:3]

        log.append(
            f"BLS: {len(candidates_to_try)} aday TLS multimode ile denenecek"
        )

        best_tls_result = None
        best_bls_peak = None
        best_score = -1.0  # SDE * SNR ile skor

        for idx, bls_peak_try in enumerate(candidates_to_try):
            log.append(
                f"  Aday {idx + 1}: P={bls_peak_try.period:.4f}d, "
                f"güç={bls_peak_try.power:.2f}"
            )

            try:
                # MULTIMODE: A/B/C modlarini calistir, en iyisini sec
                tls_try, adjusted_peak = self._tls.validate_multimode(
                    detrended,
                    bls_peak_try,
                    stellar_radius=self.stellar_radius,
                    stellar_mass=self.stellar_mass,
                )

                if tls_try is None:
                    logger.debug(f"Aday {idx+1} TLS multimode basarisiz")
                    continue

                # bls_peak'i ayarlanmis periyoda guncelle
                bls_peak_try = adjusted_peak"""

    if old_block in content:
        content = content.replace(old_block, new_block)
        cascade_file.write_text(content, encoding="utf-8")
        print("OK Cascade validate_multimode kullaniyor")

        # Sozdizim kontrol
        try:
            import ast
            ast.parse(cascade_file.read_text(encoding="utf-8"))
            print("OK Python sozdizimi gecerli")
            return 0
        except SyntaxError as e:
            print(f"FAIL Sozdizim hatasi: {e}")
            return 1
    else:
        print("HATA: Cascade TLS cagrisi bulunamadi")
        print("Cascade dosyasi belki farkli bir surumden")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())