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
        InferenceData'dan parametre posterior özetini güvenli şekilde çıkarır.

        ArviZ sürüm farklarından etkilenmemek için:
        - mean/std/median doğrudan sample'lardan hesaplanır
        - %94 aralık np.quantile ile hesaplanır
        - r_hat ve ess mümkünse ArviZ'den alınır, olmazsa fallback kullanılır
        """

        try:
            if param_name not in idata.posterior:
                return None

            samples = idata.posterior[param_name].values.reshape(-1)

            if len(samples) == 0:
                return None

            mean = float(np.mean(samples))
            std = float(np.std(samples, ddof=1)) if len(samples) > 1 else 0.0
            median = float(np.median(samples))

            # %94 interval (3% - 97%)
            q_low, q_high = np.quantile(samples, [0.03, 0.97])
            hdi_low = float(q_low)
            hdi_high = float(q_high)

            # r_hat
            r_hat = 99.0
            try:
                if _ARVIZ_AVAILABLE:
                    rhat_ds = az.rhat(idata, var_names=[param_name])
                    rhat_val = rhat_ds[param_name].values
                    r_hat = float(np.asarray(rhat_val).reshape(-1)[0])
            except Exception as e:
                logger.debug(f"r_hat hesaplanamadi ({param_name}): {e}")

            # ESS
            ess = 0.0
            try:
                if _ARVIZ_AVAILABLE:
                    ess_ds = az.ess(idata, var_names=[param_name], method="bulk")
                    ess_val = ess_ds[param_name].values
                    ess = float(np.asarray(ess_val).reshape(-1)[0])
            except Exception as e:
                logger.debug(f"ESS hesaplanamadi ({param_name}): {e}")

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

    backup = pymc_file.with_suffix(".py.extractor_backup")
    shutil.copy(pymc_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = pymc_file.read_text(encoding="utf-8")

    start_marker = "    def _extract_posterior_summary("
    end_marker = "    def fit("

    if start_marker not in content or end_marker not in content:
        print("HATA: extractor veya fit marker bulunamadi")
        return 1

    start = content.index(start_marker)
    end = content.index(end_marker, start)

    new_content = content[:start] + NEW_EXTRACTOR + "\n\n" + content[end:]

    pymc_file.write_text(new_content, encoding="utf-8")
    print("OK Posterior extractor guncellendi")

    try:
        ast.parse(pymc_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        print(f"Geri yukleme: cp {backup} {pymc_file}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())