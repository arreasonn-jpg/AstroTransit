from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
pymc_file = project_root / "astrotransit" / "modeling" / "pymc_fit.py"


NEW_EXTRACTOR = '''
    def _extract_posterior_summary(
        self,
        idata,
        param_name: str,
    ) -> Optional[PosteriorSummary]:
        """
        InferenceData'dan parametre posterior özetini daha güvenli şekilde çıkarır.
        az.summary yerine doğrudan posterior sample'larını kullanır.
        """

        if not _ARVIZ_AVAILABLE:
            return None

        try:
            if param_name not in idata.posterior:
                return None

            samples = idata.posterior[param_name].values.reshape(-1)

            if len(samples) == 0:
                return None

            mean = float(np.mean(samples))
            std = float(np.std(samples))
            median = float(np.median(samples))

            hdi = az.hdi(samples, hdi_prob=0.94)
            hdi_low = float(hdi[0])
            hdi_high = float(hdi[1])

            # r_hat
            try:
                rhat_ds = az.rhat(idata, var_names=[param_name])
                r_hat = float(rhat_ds[param_name].values)
            except Exception:
                r_hat = 99.0

            # ess
            try:
                ess_ds = az.ess(idata, var_names=[param_name], method="bulk")
                ess = float(ess_ds[param_name].values)
            except Exception:
                ess = 0.0

            return PosteriorSummary(
                name=param_name,
                mean=mean,
                std=std,
                median=median,
                hdi_3=hdi_low,
                hdi_97=hdi_high,
                r_hat=r_hat,
                ess=ess,
            )

        except Exception as e:
            logger.debug(f"Posterior özet çıkarma hatası ({param_name}): {e}")
            return None
'''


def main():
    if not pymc_file.exists():
        print("HATA: pymc_fit.py bulunamadi")
        return 1

    backup = pymc_file.with_suffix(".py.mcmc_backup")
    shutil.copy(pymc_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = pymc_file.read_text(encoding="utf-8")
    changed = False

    # ------------------------------------------------------------
    # 1. r=rp_rs * stellar_radius  ->  r=rp_rs
    # ------------------------------------------------------------
    old = "                    r=rp_rs * stellar_radius,"
    new = "                    r=rp_rs,"
    if old in content:
        content = content.replace(old, new)
        print("OK exoplanet radius parametresi duzeltildi (r=rp_rs)")
        changed = True
    elif "r=rp_rs," in content:
        print("BILGI radius parametresi zaten duzeltilmis")

    # ------------------------------------------------------------
    # 2. progressbar=False altina cores=1 ve init=adapt_diag ekle
    # ------------------------------------------------------------
    old = """                    progressbar=False,
                    return_inferencedata=True,
                )"""
    new = """                    progressbar=False,
                    cores=1,
                    init="adapt_diag",
                    return_inferencedata=True,
                )"""
    if old in content:
        content = content.replace(old, new)
        print("OK pm.sample ayarlari iyilestirildi (cores=1, init=adapt_diag)")
        changed = True
    elif 'init="adapt_diag"' in content:
        print("BILGI pm.sample zaten patchli")

    # ------------------------------------------------------------
    # 3. _extract_posterior_summary metodunu tamamen degistir
    # ------------------------------------------------------------
    start_marker = "    def _extract_posterior_summary("
    end_marker = "    def fit("

    if start_marker in content and end_marker in content:
        start = content.index(start_marker)
        end = content.index(end_marker)
        content = content[:start] + NEW_EXTRACTOR + "\n\n" + content[end:]
        print("OK posterior extractor guvenli hale getirildi")
        changed = True
    else:
        print("UYARI extractor bloklari bulunamadi")

    # ------------------------------------------------------------
    # 4. MCMCFitResult success=True -> convergence bazli olsun
    # ------------------------------------------------------------
    old = """        result = MCMCFitResult(
            target_id=target_id,
            sector=sector,
            success=True,"""
    new = """        mcmc_success = (
            convergence_ok
            and len(posteriors) >= 4
            and n_divergences == 0
            and period_median > 0
            and rp_rs_median > 0
        )

        result = MCMCFitResult(
            target_id=target_id,
            sector=sector,
            success=mcmc_success,"""
    if old in content:
        content = content.replace(old, new)
        print("OK success artik gercek MCMC kalitesine baglandi")
        changed = True
    elif "mcmc_success =" in content:
        print("BILGI success mantigi zaten patchli")

    # ------------------------------------------------------------
    # 5. Bos posterior durumunda erken fail
    # ------------------------------------------------------------
    old = """        # Yakınsama kontrolü
        r_hat_values = [
            p.r_hat for p in posteriors.values()
            if np.isfinite(p.r_hat)
        ]"""
    new = """        # Posteriorlar bossa MCMC fiilen basarisiz
        if len(posteriors) == 0:
            logger.error("MCMC posterior bos dondu - sonuc kullanilamaz")
            return self._failed_result(target_id, sector, "empty posterior")

        # Yakınsama kontrolü
        r_hat_values = [
            p.r_hat for p in posteriors.values()
            if np.isfinite(p.r_hat)
        ]"""
    if old in content:
        content = content.replace(old, new)
        print("OK bos posterior icin erken fail eklendi")
        changed = True
    elif "empty posterior" in content:
        print("BILGI empty posterior guard zaten var")

    if changed:
        pymc_file.write_text(content, encoding="utf-8")
        print("OK Dosya kaydedildi")
    else:
        print("BILGI Degisiklik gerekmedi")

    # syntax check
    try:
        ast.parse(pymc_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        print(f"Geri yukleme: copy {backup} {pymc_file}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())