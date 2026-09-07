from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
pymc_file = project_root / "astrotransit" / "modeling" / "pymc_fit.py"


def main():
    if not pymc_file.exists():
        print("HATA: pymc_fit.py bulunamadi")
        return 1

    backup = pymc_file.with_suffix(".py.div_backup")
    shutil.copy(pymc_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = pymc_file.read_text(encoding="utf-8")

    old_block = """        # Yakınsama kontrolü
        r_hat_values = [
            p.r_hat for p in posteriors.values()
            if np.isfinite(p.r_hat)
        ]
        r_hat_max = max(r_hat_values) if r_hat_values else 99.0
        convergence_ok = (r_hat_max < 1.05) and (n_divergences < 20)

        # Iraksama sayısı
        try:
            n_divergences = int(
                idata.sample_stats.diverging.values.sum()
            )
        except Exception:
            n_divergences = -1"""

    new_block = """        # Iraksama sayısı
        try:
            n_divergences = int(
                idata.sample_stats.diverging.values.sum()
            )
        except Exception:
            n_divergences = -1

        # Yakınsama kontrolü
        r_hat_values = [
            p.r_hat for p in posteriors.values()
            if np.isfinite(p.r_hat)
        ]
        r_hat_max = max(r_hat_values) if r_hat_values else 99.0
        convergence_ok = (r_hat_max < 1.05) and (n_divergences < 20)"""

    if old_block in content:
        content = content.replace(old_block, new_block)
        print("OK divergence/convergence scope siralamasi duzeltildi")
    else:
        print("UYARI Hedef blok bulunamadi, manuel fix gerekiyor.")
        return 1

    pymc_file.write_text(content, encoding="utf-8")

    try:
        ast.parse(pymc_file.read_text(encoding="utf-8"))
        print("OK Python sozdizimi gecerli")
        return 0
    except SyntaxError as e:
        print(f"FAIL Sozdizim hatasi: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())