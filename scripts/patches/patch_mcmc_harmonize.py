"""
Patch: MCMC result harmonization
- MCMCFitResult'a eksik MAP alanlarını doldurur
- downstream output/visualization contract'ı karşılanır
- fitter.py içine iki yardımcı metod + harmonize çağrısı eklenir
"""

from pathlib import Path

TARGET = Path("astrotransit/modeling/fitter.py")
BACKUP = Path("astrotransit/modeling/fitter.py.bak_pre_harmonize")


def main():
    original = TARGET.read_text(encoding="utf-8")

    # backup
    BACKUP.write_text(original, encoding="utf-8")
    print(f"Backup: {BACKUP}")

    # ── 1) yardımcı metodlar ──
    new_methods = '''
    def _posterior_center(self, fit_result, name: str):
        """Posterior özetinden merkez değer döndürür."""
        posteriors = getattr(fit_result, "posteriors", None) or {}
        post = posteriors.get(name)
        if post is None:
            return None
        for attr in ("median", "value", "mean"):
            if hasattr(post, attr):
                try:
                    return float(getattr(post, attr))
                except Exception:
                    pass
        if isinstance(post, dict):
            for key in ("median", "value", "mean"):
                if key in post:
                    try:
                        return float(post[key])
                    except Exception:
                        pass
        return None

    def _harmonize_mcmc_result(self, mcmc_result, map_result):
        """
        Başarılı MCMC sonucunu downstream MAP-odaklı output/visualization
        contract'ına uyumlu hale getirir.

        MCMCFitResult bazı alanlara sahip olmayabilir.
        Bu metod eksik alanları map_result'tan tamamlar,
        sonra posterior merkezlerini varsa üstüne yazar.
        """
        attrs_from_map = [
            "period",
            "period_err",
            "t0",
            "duration_hours",
            "depth",
            "depth_ppm",
            "rp_rs",
            "rp_rs_err",
            "impact_parameter",
            "a_over_rs",
            "inclination_deg",
            "u1",
            "u2",
            "baseline",
            "log_jitter",
            "log_likelihood",
            "semi_major_axis_au",
            "stellar_density_gcm3",
            "planet_radius_rearth",
            "planet_radius_rjup",
            "equilibrium_temperature_k",
            "insolation_flux",
            "transit_depth_ppm",
            "residuals",
        ]

        for attr in attrs_from_map:
            if getattr(mcmc_result, attr, None) is None:
                val = getattr(map_result, attr, None)
                if val is not None:
                    try:
                        setattr(mcmc_result, attr, val)
                    except Exception:
                        pass

        # Posterior merkezlerini üstüne yaz (daha iyi MCMC değerleri)
        posterior_map = {
            "baseline": "baseline",
            "log_jitter": "log_jitter",
            "impact_parameter": "impact_parameter",
            "rp_rs": "rp_rs",
            "t0": "t0",
        }
        for attr, post_name in posterior_map.items():
            val = self._posterior_center(mcmc_result, post_name)
            if val is not None:
                try:
                    setattr(mcmc_result, attr, val)
                except Exception:
                    pass

        # Derived bundle varsa oradan da doldur
        derived = getattr(mcmc_result, "derived", None)
        if derived is not None:
            for attr in [
                "planet_radius_rearth",
                "planet_radius_rjup",
                "semi_major_axis_au",
                "equilibrium_temperature_k",
                "insolation_flux",
            ]:
                if getattr(mcmc_result, attr, None) is None:
                    val = getattr(derived, attr, None)
                    if val is not None:
                        try:
                            setattr(mcmc_result, attr, val)
                        except Exception:
                            pass

        # Output contract etiketleri
        for attr, val in [
            ("period_sampled", False),
            ("period_err_source", "fixed_in_mcmc"),
        ]:
            if not hasattr(mcmc_result, attr):
                try:
                    setattr(mcmc_result, attr, val)
                except Exception:
                    pass

        # period_err None olarak bırak (fixed, sample edilmedi)
        if getattr(mcmc_result, "period_err", None) in (None, 0.0):
            try:
                setattr(mcmc_result, "period_err", None)
            except Exception:
                pass

        logger.debug(
            f"MCMC harmonization tamamlandı — "
            f"baseline={getattr(mcmc_result, 'baseline', None)}, "
            f"log_jitter={getattr(mcmc_result, 'log_jitter', None)}, "
            f"a_over_rs={getattr(mcmc_result, 'a_over_rs', None)}"
        )

        return mcmc_result

'''

    # ── 2) ekleme noktası: _should_run_mcmc metodunun hemen öncesi ──
    INSERT_BEFORE = "    def _should_run_mcmc("

    if INSERT_BEFORE not in original:
        print("HATA: ekleme noktası bulunamadı: _should_run_mcmc")
        return

    patched = original.replace(
        INSERT_BEFORE,
        new_methods + INSERT_BEFORE,
        1,
    )

    # ── 3) MCMC başarılı branch'ini bul ve harmonize çağrısını ekle ──
    OLD_BRANCH = (
        "                if mcmc_result.success:\n"
        "                    logger.info(\n"
        "                        f\"MCMC sonucu kullanılıyor — \"\n"
        "                        f\"{target_id} sektör {sector}\"\n"
        "                    )\n"
        "                    return mcmc_result"
    )

    NEW_BRANCH = (
        "                if mcmc_result.success:\n"
        "                    mcmc_result = self._harmonize_mcmc_result(\n"
        "                        mcmc_result, map_result\n"
        "                    )\n"
        "                    logger.info(\n"
        "                        f\"MCMC sonucu kullanılıyor — \"\n"
        "                        f\"{target_id} sektör {sector}\"\n"
        "                    )\n"
        "                    return mcmc_result"
    )

    if OLD_BRANCH not in patched:
        print("HATA: MCMC başarılı branch bulunamadı.")
        print("Lütfen fitter.py içinde şu bloğu manuel kontrol et:")
        print(OLD_BRANCH)
        return

    patched = patched.replace(OLD_BRANCH, NEW_BRANCH, 1)

    TARGET.write_text(patched, encoding="utf-8")
    print(f"Patch uygulandı: {TARGET}")
    print("Yapılan değişiklikler:")
    print("  1) _posterior_center() metodu eklendi")
    print("  2) _harmonize_mcmc_result() metodu eklendi")
    print("  3) MCMC başarılı branch'ine harmonize çağrısı eklendi")


if __name__ == "__main__":
    main()