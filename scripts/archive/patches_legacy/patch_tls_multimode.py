"""
Faz 1: TLS'yi 3 modda calistiran multi-mode arama sistemi.

Mod A: BLS yonlendirmeli dar arama (mevcut)
Mod B: BLS harmonikleri (0.5x, 2x, 3x)
Mod C: Bagimsiz genis tarama (0.5d - 15d)

En yuksek SDE'ye sahip sonucu secer.
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
tls_file = project_root / "astrotransit" / "detection" / "tls_search.py"


def main():
    if not tls_file.exists():
        print("HATA: tls_search.py bulunamadi")
        return 1

    shutil.copy(tls_file, tls_file.with_suffix(".py.multimode_backup"))
    print("OK Yedek: tls_search.py.multimode_backup")

    content = tls_file.read_text(encoding="utf-8")

    # Kontrol: zaten uygulanmis mi?
    if "def validate_multimode" in content:
        print("BILGI Multimode zaten uygulanmis")
        return 0

    # TLSSearch class icinde validate metodundan HEMEN SONRA
    # yeni validate_multimode metodunu ekle
    marker = """    def _failed_result("""

    new_method = '''    def validate_multimode(
        self,
        detrended,
        bls_peak,
        stellar_radius: float = 1.0,
        stellar_mass: float = 1.0,
    ):
        """
        TLS'yi 3 farkli modda calistir ve en iyi sonucu sec.

        Mod A: BLS yonlendirmeli dar arama (mevcut validate)
        Mod B: BLS harmoniklerinde arama (0.5x, 2x, 3x)
        Mod C: Bagimsiz genis tarama

        Her modun sonucu SDE ile karsilastirilir, en yuksek SDE secilir.
        Ayrica fiziksel gecerlilik kontrolu yapilir.
        """
        import numpy as np
        from dataclasses import replace

        target_id = detrended.target_id
        sector = detrended.sector

        results = []  # (mode_name, tls_result, adjusted_bls_peak)

        # ─── MOD A: BLS yonlendirmeli (mevcut davranis) ───
        try:
            r_a = self.validate(
                detrended, bls_peak, stellar_radius, stellar_mass
            )
            if r_a.passed_threshold or r_a.sde > 0:
                results.append(("A_direct", r_a, bls_peak))
                logger.info(
                    f"[Mod A] {target_id} S{sector}: "
                    f"P={r_a.period:.4f}d, SDE={r_a.sde:.2f}"
                )
        except Exception as e:
            logger.debug(f"Mod A hatasi: {e}")

        # ─── MOD B: BLS harmonikleri ───
        # BLS'in gercek periyodu harmonik olarak bulmus olabilir
        # 0.5x, 2x ve 3x etrafinda ayri ayri ara
        harmonic_factors = [0.5, 2.0, 3.0]

        for factor in harmonic_factors:
            harmonic_p = bls_peak.period * factor

            # Fiziksel makul araligi kontrol et
            if harmonic_p < 0.3 or harmonic_p > 30.0:
                continue

            # Yeni bir "sanki BLS peak" olustur
            fake_peak = replace(
                bls_peak,
                period=harmonic_p,
                period_err=bls_peak.period_err * factor,
            )

            try:
                r_h = self.validate(
                    detrended, fake_peak, stellar_radius, stellar_mass
                )
                if r_h.sde > 0:
                    results.append((f"B_harm_{factor}x", r_h, fake_peak))
                    logger.info(
                        f"[Mod B {factor}x] {target_id} S{sector}: "
                        f"P={r_h.period:.4f}d, SDE={r_h.sde:.2f}"
                    )
            except Exception as e:
                logger.debug(f"Mod B ({factor}x) hatasi: {e}")

        # ─── MOD C: Bagimsiz genis tarama ───
        try:
            from transitleastsquares import transitleastsquares as _tls

            time_arr = detrended.time
            flux_arr = detrended.flux
            err_arr = detrended.flux_err

            r_star = float(stellar_radius)
            m_star = float(stellar_mass)

            model = _tls(time_arr, flux_arr, err_arr)

            # Genis arama: 0.5d - 15d (veya gozlem/2)
            obs_duration = float(time_arr[-1] - time_arr[0])
            wide_max = min(15.0, obs_duration / 2.0)

            tls_wide = model.power(
                period_min=0.5,
                period_max=wide_max,
                oversampling_factor=self.oversampling_factor,
                transit_template=self.transit_template,
                use_threads=1,
                R_star=r_star,
                R_star_min=max(0.1, r_star * 0.5),
                R_star_max=r_star * 1.5,
                M_star=m_star,
                M_star_min=max(0.1, m_star * 0.5),
                M_star_max=m_star * 1.5,
            )

            # Sonucu TLSResult formatinda topla
            wide_period = float(tls_wide.period)
            wide_sde = float(tls_wide.SDE)
            wide_snr = float(tls_wide.snr) if hasattr(tls_wide, 'snr') else 0.0

            # Yeni bir BLS peak olustur (sanki wide arama bulmus gibi)
            wide_peak = replace(
                bls_peak,
                period=wide_period,
                period_err=float(tls_wide.period_uncertainty),
            )

            # validate'i tekrar cagir bu sefer wide periyoda odakli
            r_c = self.validate(
                detrended, wide_peak, stellar_radius, stellar_mass
            )
            if r_c.sde > 0:
                results.append(("C_wide", r_c, wide_peak))
                logger.info(
                    f"[Mod C wide] {target_id} S{sector}: "
                    f"P={r_c.period:.4f}d, SDE={r_c.sde:.2f}"
                )
        except Exception as e:
            logger.debug(f"Mod C hatasi: {e}")

        # ─── EN IYI SONUCU SEC ───
        if not results:
            logger.warning(f"{target_id} S{sector}: hicbir TLS modu calismadi")
            return None, bls_peak

        # SDE'ye gore sirala, en yuksek uste
        results.sort(key=lambda x: x[1].sde, reverse=True)

        # Fiziksel gecerlilik onceligi:
        # Passing threshold + en yuksek SDE
        passing = [r for r in results if r[1].passed_threshold]

        if passing:
            best_mode, best_result, best_peak = passing[0]
        else:
            best_mode, best_result, best_peak = results[0]

        logger.info(
            f"[BEST] {target_id} S{sector}: {best_mode} secildi - "
            f"P={best_result.period:.4f}d, SDE={best_result.sde:.2f}"
        )

        return best_result, best_peak

    def _failed_result('''

    if marker in content:
        content = content.replace(marker, new_method)
        tls_file.write_text(content, encoding="utf-8")
        print("OK validate_multimode metodu eklendi")

        # Sozdizim kontrol
        try:
            import ast
            ast.parse(tls_file.read_text(encoding="utf-8"))
            print("OK Python sozdizimi gecerli")
            return 0
        except SyntaxError as e:
            print(f"FAIL Sozdizim hatasi: {e}")
            return 1
    else:
        print("HATA: _failed_result marker bulunamadi")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())