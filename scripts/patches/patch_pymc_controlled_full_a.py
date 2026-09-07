from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent
pymc_file = project_root / "astrotransit" / "modeling" / "pymc_fit.py"


def replace_between(text: str, start_marker: str, end_marker: str, new_block: str):
    if start_marker not in text or end_marker not in text:
        return text, False
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    updated = text[:start] + new_block + text[end:]
    return updated, True


def main():
    if not pymc_file.exists():
        print("HATA: pymc_fit.py bulunamadi")
        return 1

    backup = pymc_file.with_suffix(".py.controlled_full_a_backup")
    shutil.copy(pymc_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = pymc_file.read_text(encoding="utf-8")
    changed = False

    # ============================================================
    # 1. Reduced prior blogunu Controlled Full-A ile degistir
    # ============================================================
    start_marker = "                # ── Reduced Priorlar (Stabilize Mod) ──"
    end_marker = "                # Jitter"

    new_prior_block = """                # ── Controlled Full-A Priorlar ──
                # Period ve limb darkening sabit
                period = pm.Data("period", init_period)
                u1 = pm.Data("u1", init_u1)
                u2 = pm.Data("u2", init_u2)

                # t0: MAP etrafinda dar Normal
                t0 = pm.Normal(
                    "t0",
                    mu=init_t0,
                    sigma=0.02,
                    initval=init_t0,
                )

                # rp/rs: MAP etrafinda truncated normal (log uzayinda)
                log_rp_rs = pm.TruncatedNormal(
                    "log_rp_rs",
                    mu=np.log(init_rp_rs),
                    sigma=0.15,
                    lower=np.log(priors.rp_rs_bounds[0]),
                    upper=np.log(priors.rp_rs_bounds[1]),
                    initval=np.log(init_rp_rs),
                )
                rp_rs = pm.Deterministic("rp_rs", pm.math.exp(log_rp_rs))

                # impact parameter: MAP etrafinda truncated normal
                b = pm.TruncatedNormal(
                    "impact_parameter",
                    mu=min(max(init_b, 0.05), 0.9),
                    sigma=0.15,
                    lower=0.0,
                    upper=1.0,
                    initval=min(max(init_b, 0.05), 0.9),
                )

"""

    content2, ok = replace_between(content, start_marker, end_marker, new_prior_block)
    if ok:
        content = content2
        print("OK Controlled Full-A prior blogu yazildi")
        changed = True
    else:
        print("UYARI Reduced prior blogu bulunamadi")

    # ============================================================
    # 2. Jitter blogunu daralt
    # ============================================================
    old_jitter = """                # Jitter
                log_jitter = pm.Uniform(
                    "log_jitter",
                    lower=-15.0,
                    upper=0.0,
                    initval=-7.0,
                )"""

    new_jitter = """                # Jitter: daha kontrollu prior
                log_jitter = pm.TruncatedNormal(
                    "log_jitter",
                    mu=-7.0,
                    sigma=2.0,
                    lower=-15.0,
                    upper=0.0,
                    initval=-7.0,
                )"""

    if old_jitter in content:
        content = content.replace(old_jitter, new_jitter)
        print("OK Jitter prior daraltildi")
        changed = True
    elif 'mu=-7.0' in content and '"log_jitter"' in content:
        print("BILGI Jitter blogu zaten patchli")

    # ============================================================
    # 3. Baseline priorini biraz daralt
    # ============================================================
    old_baseline = """                # Baseline
                baseline = pm.Normal(
                    "baseline",
                    mu=1.0,
                    sigma=0.01,
                    initval=1.0,
                )"""

    new_baseline = """                # Baseline: dar prior
                baseline = pm.Normal(
                    "baseline",
                    mu=1.0,
                    sigma=0.003,
                    initval=1.0,
                )"""

    if old_baseline in content:
        content = content.replace(old_baseline, new_baseline)
        print("OK Baseline prior daraltildi")
        changed = True
    elif 'sigma=0.003' in content and '"baseline"' in content:
        print("BILGI Baseline blogu zaten patchli")

    # ============================================================
    # 4. sample() target_accept guclendir
    # ============================================================
    old_target_accept = "                    target_accept=self.target_accept,"
    new_target_accept = '                    target_accept=max(self.target_accept, 0.99),'

    if old_target_accept in content:
        content = content.replace(old_target_accept, new_target_accept)
        print("OK target_accept guclendirildi")
        changed = True
    elif "max(self.target_accept, 0.99)" in content:
        print("BILGI target_accept zaten patchli")

    # ============================================================
    # 5. MCMC success mantigini Controlled Full-A icin ayarla
    # ============================================================
    old_success = """        mcmc_success = (
            convergence_ok
            and len(posteriors) >= 3
            and n_divergences < 10
            and rp_rs_median > 0
        )"""

    new_success = """        mcmc_success = (
            convergence_ok
            and len(posteriors) >= 4
            and n_divergences < 20
            and rp_rs_median > 0
            and b_median >= 0
        )"""

    if old_success in content:
        content = content.replace(old_success, new_success)
        print("OK success mantigi Controlled Full-A icin ayarlandi")
        changed = True
    elif "len(posteriors) >= 4" in content and "n_divergences < 20" in content:
        print("BILGI success mantigi zaten patchli")

    # ============================================================
    # 6. convergence_ok tanimini guclendir
    # ============================================================
    old_conv = "        convergence_ok = r_hat_max < 1.1"
    new_conv = "        convergence_ok = (r_hat_max < 1.05) and (n_divergences < 20)"

    if old_conv in content:
        content = content.replace(old_conv, new_conv)
        print("OK convergence kriteri sikilastirildi")
        changed = True
    elif "r_hat_max < 1.05" in content:
        print("BILGI convergence kriteri zaten patchli")

    # ============================================================
    # 7. Parametre listesi impact_parameter dahil olmali
    # ============================================================
    desired_param_block = """        param_names = [
            "t0", "rp_rs", "impact_parameter",
            "log_jitter", "baseline",
        ]"""
    if desired_param_block in content:
        print("BILGI param_names uygun")
    else:
        print("UYARI param_names blogunu manuel kontrol et")

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