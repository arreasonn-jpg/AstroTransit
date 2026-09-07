"""
Faz 1.5: TLS multimode duzeltmeleri.

Duzeltilen:
1. Mod C alt sinirini configs'ten al (0.3d)
2. Mod B TLS penceresini %5'e dusur (harmonik geri donmesin)
3. Genis aramadan sonra bulunan periyoda yeni bir TLS validate CAGIRMA
   - Cunku validate icin BLS pencere secip harmoniği geri buluyor
"""

from pathlib import Path
import shutil

project_root = Path(__file__).resolve().parent.parent
tls_file = project_root / "astrotransit" / "detection" / "tls_search.py"


def main():
    if not tls_file.exists():
        print("HATA: tls_search.py bulunamadi")
        return 1

    shutil.copy(tls_file, tls_file.with_suffix(".py.multimode_v2_backup"))
    print("OK Yedek: tls_search.py.multimode_v2_backup")

    content = tls_file.read_text(encoding="utf-8")

    # -----------------------------------------------------------------
    # 1. Mod C: Alt sinirini 0.3d yap (0.5d yerine)
    # -----------------------------------------------------------------
    old_wide = """            tls_wide = model.power(
                period_min=0.5,
                period_max=wide_max,"""

    new_wide = """            # Alt sinir: 0.3d (kucuk periyotlu gezegenler icin)
            tls_wide = model.power(
                period_min=0.3,
                period_max=wide_max,"""

    if old_wide in content:
        content = content.replace(old_wide, new_wide)
        print("OK Mod C alt siniri 0.5 -> 0.3d")

    # -----------------------------------------------------------------
    # 2. Mod C sonucunda BLS pencere ile validate CAGIRMA
    #    Cunku bu harmonige geri donduruyor
    # -----------------------------------------------------------------
    old_wide_validate = """            # validate'i tekrar cagir bu sefer wide periyoda odakli
            r_c = self.validate(
                detrended, wide_peak, stellar_radius, stellar_mass
            )
            if r_c.sde > 0:
                results.append(("C_wide", r_c, wide_peak))
                logger.info(
                    f"[Mod C wide] {target_id} S{sector}: "
                    f"P={r_c.period:.4f}d, SDE={r_c.sde:.2f}"
                )"""

    new_wide_validate = """            # Mod C sonucunu DOGRUDAN kullan (validate cagirmadan)
            # Cunku validate BLS penceresine sikisir ve harmonige geri doner
            from astrotransit.detection.tls_search import TLSResult
            import numpy as np

            # Wide TLS ciktisindan TLSResult olustur
            try:
                depth_val = float(1.0 - tls_wide.depth)
                rp_rs_val = float(tls_wide.rp_rs) if hasattr(tls_wide, 'rp_rs') else float(np.sqrt(max(0, depth_val)))
                odd_even_val = float(tls_wide.odd_even_mismatch)
                transit_count_val = int(tls_wide.transit_count)
                fap_val = float(tls_wide.FAP) if hasattr(tls_wide, 'FAP') else 1.0

                transit_times_arr = np.array(tls_wide.transit_times) if hasattr(tls_wide, 'transit_times') else np.array([])
                transit_depths_arr = (
                    np.array(tls_wide.transit_depths)
                    if hasattr(tls_wide, 'transit_depths')
                    else np.full(transit_count_val, depth_val)
                )
                folded_phase_arr = np.array(tls_wide.folded_phase) if hasattr(tls_wide, 'folded_phase') else np.array([])
                folded_flux_arr = np.array(tls_wide.folded_y) if hasattr(tls_wide, 'folded_y') else np.array([])
                model_phase_arr = np.array(tls_wide.model_folded_phase) if hasattr(tls_wide, 'model_folded_phase') else np.array([])
                model_flux_arr = np.array(tls_wide.model_folded_model) if hasattr(tls_wide, 'model_folded_model') else np.array([])

                r_c = TLSResult(
                    target_id=target_id,
                    sector=sector,
                    period=wide_period,
                    period_err=float(tls_wide.period_uncertainty),
                    t0=float(tls_wide.T0),
                    duration=float(tls_wide.duration),
                    depth=depth_val,
                    rp_rs=rp_rs_val,
                    sde=wide_sde,
                    snr=wide_snr,
                    odd_even_mismatch=odd_even_val,
                    transit_count=transit_count_val,
                    transit_times=transit_times_arr,
                    transit_depths=transit_depths_arr,
                    folded_phase=folded_phase_arr,
                    folded_flux=folded_flux_arr,
                    model_phase=model_phase_arr,
                    model_flux=model_flux_arr,
                    false_alarm_probability=fap_val,
                    raw_stats={},
                )

                r_c = self._evaluate_threshold(r_c)

                if r_c.sde > 0:
                    results.append(("C_wide", r_c, wide_peak))
                    logger.info(
                        f"[Mod C wide] {target_id} S{sector}: "
                        f"P={r_c.period:.4f}d, SDE={r_c.sde:.2f}"
                    )
            except Exception as e:
                logger.debug(f"Mod C sonuc parse hatasi: {e}")"""

    if old_wide_validate in content:
        content = content.replace(old_wide_validate, new_wide_validate)
        print("OK Mod C dogrudan TLS ciktisi kullaniyor (validate atlaniyor)")

    # -----------------------------------------------------------------
    # 3. Mod B: harmonik icin de wide validate mantığı
    # -----------------------------------------------------------------
    # Su anda Mod B validate icinden gecerken ±%10 pencere aciyor,
    # bu da bazi durumlarda harmonike geri donduruyor.
    # Cozum: Mod B'de period_search_window'u gecici olarak %5'e dusur

    old_mod_b = """        for factor in harmonic_factors:
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
                )"""

    new_mod_b = """        # Mod B icin daha dar pencere (harmonik geri donmesin)
        original_window = self.period_search_window
        self.period_search_window = 0.03  # gecici %3 pencere

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
                )"""

    if old_mod_b in content:
        content = content.replace(old_mod_b, new_mod_b)
        print("OK Mod B pencere daraltildi (%3)")

    # Mod B sonunda pencereyi geri yukle
    # Mod C basladigi yerde pencereyi geri yuklemek gerekiyor
    old_before_c = """        # ─── MOD C: Bagimsiz genis tarama ───
        try:
            from transitleastsquares import transitleastsquares as _tls"""

    new_before_c = """        # Pencereyi orijinaline geri yukle
        self.period_search_window = original_window

        # ─── MOD C: Bagimsiz genis tarama ───
        try:
            from transitleastsquares import transitleastsquares as _tls"""

    if old_before_c in content:
        content = content.replace(old_before_c, new_before_c)
        print("OK Pencere restore mantigi eklendi")

    # Kaydet
    tls_file.write_text(content, encoding="utf-8")
    print("\nOK Dosya kaydedildi")

    # Sozdizim kontrol
    try:
        import ast
        ast.parse(tls_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())