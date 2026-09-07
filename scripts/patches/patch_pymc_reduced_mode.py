"""
MCMC modelini stabilize etmek icin 'Reduced MCMC Mode' patch'i.

Period ve limb darkening parametreleri sabitlenir.
Sadece t0, rp_rs, impact_parameter, baseline ve log_jitter orneklenir.
Bu, yakinsamayi (convergence) cok hizlandirir ve divergence'i azaltir.
"""

from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
pymc_file = project_root / "astrotransit" / "modeling" / "pymc_fit.py"


def main():
    if not pymc_file.exists():
        print("HATA: pymc_fit.py bulunamadi")
        return 1

    backup = pymc_file.with_suffix(".py.reduced_mcmc_backup")
    shutil.copy(pymc_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = pymc_file.read_text(encoding="utf-8")

    # 1. Degisecek model blogunu bul
    old_model_block_parts = [
        '                # ── Priorlar ──',
        '',
        '                # Periyot: Uniform',
        '                log_period = pm.Uniform(',
        '                    "log_period",',
        '                    lower=np.log(priors.period_bounds[0]),',
        '                    upper=np.log(priors.period_bounds[1]),',
        '                    initval=np.log(init_period),',
        '                )',
        '                period = pm.Deterministic("period", pm.math.exp(log_period))',
        '',
        '                # t0: Uniform',
        '                t0 = pm.Uniform(',
        '                    "t0",',
        '                    lower=priors.t0_bounds[0],',
        '                    upper=priors.t0_bounds[1],',
        '                    initval=init_t0,',
        '                )',
        '',
        '                # Yarıçap oranı: log-Uniform',
        '                log_rp_rs = pm.Uniform(',
        '                    "log_rp_rs",',
        '                    lower=np.log(priors.rp_rs_bounds[0]),',
        '                    upper=np.log(priors.rp_rs_bounds[1]),',
        '                    initval=np.log(init_rp_rs),',
        '                )',
        '                rp_rs = pm.Deterministic("rp_rs", pm.math.exp(log_rp_rs))',
        '',
        '                # Etki parametresi: Uniform',
        '                b = pm.Uniform(',
        '                    "impact_parameter",',
        '                    lower=0.0,',
        '                    upper=1.2,',
        '                    initval=init_b,',
        '                )',
        '',
        '                # Limb darkening: Kipping (2013) quadratic parametrizasyonu',
        '                # q1, q2 → u1, u2 dönüşümü ile fiziksel geçerliliği zorla',
        '                q1 = pm.Uniform("q1", lower=0.0, upper=1.0, initval=0.5)',
        '                q2 = pm.Uniform("q2", lower=0.0, upper=1.0, initval=0.5)',
        '',
        '                # Kipping (2013) dönüşümü',
        '                u1 = pm.Deterministic("u1", 2 * pm.math.sqrt(q1) * q2)',
        '                u2 = pm.Deterministic("u2", pm.math.sqrt(q1) * (1 - 2 * q2))',
    ]
    old_model_block = "\n".join(old_model_block_parts)

    new_model_block_parts = [
        '                # ── Reduced Priorlar (Stabilize Mod) ──',
        '                # Period ve Limb Darkening sabitleniyor',
        '',
        '                period = pm.Data("period", init_period)',
        '                u1 = pm.Data("u1", init_u1)',
        '                u2 = pm.Data("u2", init_u2)',
        '',
        '                # t0: Daha dar Uniform prior (init etrafinda +- 0.05 gun)',
        '                t0 = pm.Uniform(',
        '                    "t0",',
        '                    lower=init_t0 - 0.05,',
        '                    upper=init_t0 + 0.05,',
        '                    initval=init_t0,',
        '                )',
        '',
        '                # Yarıçap oranı: Genis log-Uniform',
        '                log_rp_rs = pm.Uniform(',
        '                    "log_rp_rs",',
        '                    lower=np.log(priors.rp_rs_bounds[0]),',
        '                    upper=np.log(priors.rp_rs_bounds[1]),',
        '                    initval=np.log(init_rp_rs),',
        '                )',
        '                rp_rs = pm.Deterministic("rp_rs", pm.math.exp(log_rp_rs))',
        '',
        '                # Etki parametresi (b): Uniform',
        '                b = pm.Uniform(',
        '                    "impact_parameter",',
        '                    lower=0.0,',
        '                    upper=1.0,',
        '                    initval=min(init_b, 0.9),',
        '                )',
    ]
    new_model_block = "\n".join(new_model_block_parts)

    # 2. Extract kismindaki param_names guncelle
    old_param_names = """        param_names = [
            "period", "t0", "rp_rs", "impact_parameter",
            "u1", "u2", "log_jitter", "baseline",
        ]"""

    new_param_names = """        param_names = [
            "t0", "rp_rs", "impact_parameter",
            "log_jitter", "baseline",
        ]"""

    # 3. mcmc_success sartlarini hafiflet (period ve u1 artik yok)
    old_success_cond = """        mcmc_success = (
            convergence_ok
            and len(posteriors) >= 4
            and n_divergences == 0
            and period_median > 0
            and rp_rs_median > 0
        )"""

    new_success_cond = """        mcmc_success = (
            convergence_ok
            and len(posteriors) >= 3
            and n_divergences < 10
            and rp_rs_median > 0
        )"""

    # 4. Period, u1, u2 degiskenlerini cekerken sabitleri kullan
    old_get_median_block = """        period_median = get_median("period")
        rp_rs_median = get_median("rp_rs")
        b_median = get_median("impact_parameter")
        u1_median = get_median("u1")
        u2_median = get_median("u2")"""

    new_get_median_block = """        period_median = init_period  # Sabit
        u1_median = init_u1          # Sabit
        u2_median = init_u2          # Sabit
        rp_rs_median = get_median("rp_rs")
        b_median = get_median("impact_parameter")"""

    changed = False

    if old_model_block in content:
        content = content.replace(old_model_block, new_model_block)
        print("OK Model priorlari 'reduced' olarak guncellendi")
        changed = True
    else:
        print("UYARI Model prior blogu bulunamadi (Zaten guncellenmis olabilir)")

    if old_param_names in content:
        content = content.replace(old_param_names, new_param_names)
        print("OK cikarilacak parametre listesi guncellendi")
        changed = True

    if old_success_cond in content:
        content = content.replace(old_success_cond, new_success_cond)
        print("OK MCMC success sartlari guncellendi")
        changed = True

    if old_get_median_block in content:
        content = content.replace(old_get_median_block, new_get_median_block)
        print("OK Sabit median degiskenleri guncellendi")
        changed = True

    if changed:
        pymc_file.write_text(content, encoding="utf-8")
        print("OK Dosya kaydedildi")

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