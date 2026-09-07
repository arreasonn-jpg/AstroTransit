from pathlib import Path
import shutil
import ast

project_root = Path(__file__).resolve().parent.parent

fitter_file = project_root / "astrotransit" / "modeling" / "fitter.py"
schemas_file = project_root / "astrotransit" / "outputs" / "schemas.py"
parquet_file = project_root / "astrotransit" / "outputs" / "parquet_writer.py"


def patch_fitter():
    if not fitter_file.exists():
        print("HATA: fitter.py bulunamadi")
        return False

    backup = fitter_file.with_suffix(".py.contract_backup")
    shutil.copy(fitter_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = fitter_file.read_text(encoding="utf-8")
    changed = False

    # MAP basarisiz durumuna status ekle
    old = """        if not map_result.success:
            logger.warning(
                f"MAP fit başarısız — {target_id} sektör {sector}"
            )
            return map_result"""
    new = """        if not map_result.success:
            map_result.fit_status = "map_failed"
            map_result.fallback_used = False
            map_result.posterior_available = False
            map_result.posterior_converged = None
            logger.warning(
                f"MAP fit başarısız — {target_id} sektör {sector}"
            )
            return map_result"""
    if old in content:
        content = content.replace(old, new)
        print("OK fitter: map_failed status eklendi")
        changed = True

    # MCMC success
    old = """                if mcmc_result.success:
                    logger.info(
                        f"MCMC sonucu kullanılıyor — "
                        f"{target_id} sektör {sector}"
                    )
                    return mcmc_result
                else:
                    logger.warning(
                        f"MCMC başarısız, MAP sonucu kullanılıyor — "
                        f"{target_id} sektör {sector}"
                    )
                    return map_result"""
    new = """                if mcmc_result.success:
                    mcmc_result.fit_status = "mcmc_success"
                    mcmc_result.fallback_used = False
                    mcmc_result.posterior_available = True
                    mcmc_result.posterior_converged = getattr(mcmc_result, "convergence_ok", False)
                    logger.info(
                        f"MCMC sonucu kullanılıyor — "
                        f"{target_id} sektör {sector}"
                    )
                    return mcmc_result
                else:
                    map_result.fit_status = "fallback_map"
                    map_result.fallback_used = True
                    map_result.posterior_available = True
                    map_result.posterior_converged = False
                    logger.warning(
                        f"MCMC başarısız, MAP sonucu kullanılıyor — "
                        f"{target_id} sektör {sector}"
                    )
                    return map_result"""
    if old in content:
        content = content.replace(old, new)
        print("OK fitter: mcmc_success / fallback_map status eklendi")
        changed = True

    # MCMC exception fallback
    old = """            except Exception as e:
                logger.warning(
                    f"MCMC hatası, MAP kullanılıyor: {e}"
                )
                return map_result"""
    new = """            except Exception as e:
                map_result.fit_status = "fallback_map_exception"
                map_result.fallback_used = True
                map_result.posterior_available = False
                map_result.posterior_converged = False
                logger.warning(
                    f"MCMC hatası, MAP kullanılıyor: {e}"
                )
                return map_result"""
    if old in content:
        content = content.replace(old, new)
        print("OK fitter: exception fallback status eklendi")
        changed = True

    # MAP final
    old = """        logger.info(
            f"MAP sonucu nihai — "
            f"{target_id} sektör {sector}"
        )

        return map_result"""
    new = """        map_result.fit_status = "map_success"
        map_result.fallback_used = False
        map_result.posterior_available = False
        map_result.posterior_converged = None

        logger.info(
            f"MAP sonucu nihai — "
            f"{target_id} sektör {sector}"
        )

        return map_result"""
    if old in content:
        content = content.replace(old, new)
        print("OK fitter: map_success status eklendi")
        changed = True

    if changed:
        fitter_file.write_text(content, encoding="utf-8")

    ast.parse(fitter_file.read_text(encoding="utf-8"))
    return True


def patch_schemas():
    if not schemas_file.exists():
        print("HATA: schemas.py bulunamadi")
        return False

    backup = schemas_file.with_suffix(".py.contract_backup")
    shutil.copy(schemas_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = schemas_file.read_text(encoding="utf-8")
    changed = False

    # Dataclass alanlari ekle
    marker = """    # ── Modelleme ──
    fit_method: str = ""
    log_likelihood: float = 0.0
    r_hat_max: float = 0.0
    n_divergences: int = 0
    mcmc_converged: bool = False

    # ── Dosya yolları ──"""
    replacement = """    # ── Modelleme ──
    fit_method: str = ""
    fit_status: str = ""
    posterior_available: bool = False
    posterior_converged: bool = False
    fallback_used: bool = False

    log_likelihood: float = 0.0
    r_hat_max: float = 0.0
    n_divergences: int = 0
    mcmc_converged: bool = False

    # ── Parametre güvenilirlik contract ──
    period_sampled: bool = False
    period_err_source: str = ""
    rp_rs_sampled: bool = False
    rp_rs_err_source: str = ""
    u1_sampled: bool = False
    u1_err_source: str = ""
    u2_sampled: bool = False
    u2_err_source: str = ""
    derived_errors_available: bool = False

    # ── Dosya yolları ──"""
    if marker in content:
        content = content.replace(marker, replacement)
        print("OK schemas: contract alanlari eklendi")
        changed = True

    # build_record icinde fit_success blogunu guclendir
    old = """    fit_success = (
        fit_result is not None
        and hasattr(fit_result, 'success')
        and fit_result.success
    )"""
    new = """    fit_success = (
        fit_result is not None
        and hasattr(fit_result, 'success')
        and fit_result.success
    )

    # Contract varsayilanlari
    rec.period_err = None
    rec.rp_rs_err = None
    rec.fit_status = "unfitted"
    rec.posterior_available = False
    rec.posterior_converged = False
    rec.fallback_used = False

    rec.period_sampled = False
    rec.period_err_source = "unavailable"
    rec.rp_rs_sampled = False
    rec.rp_rs_err_source = "unavailable"
    rec.u1_sampled = False
    rec.u1_err_source = "fixed_or_unavailable"
    rec.u2_sampled = False
    rec.u2_err_source = "fixed_or_unavailable"
    rec.derived_errors_available = False"""
    if old in content:
        content = content.replace(old, new)
        print("OK schemas: contract varsayilanlari eklendi")
        changed = True

    # fit_success bloguna metadata ekle
    old = """    if fit_success:
        # MAP/MCMC başarılıysa fit değerlerini kullan
        rec.period = fit_result.period
        rec.period_err = fit_result.period_err
        rec.t0 = fit_result.t0
        rec.rp_rs = fit_result.rp_rs"""
    new = """    if fit_success:
        # MAP/MCMC başarılıysa fit değerlerini kullan
        rec.period = fit_result.period
        rec.t0 = fit_result.t0
        rec.rp_rs = fit_result.rp_rs

        rec.fit_status = getattr(fit_result, "fit_status", fit_result.fit_method)
        rec.posterior_available = bool(getattr(fit_result, "posterior_available", False))
        rec.posterior_converged = bool(getattr(fit_result, "posterior_converged", False))
        rec.fallback_used = bool(getattr(fit_result, "fallback_used", False))

        # period contract
        if fit_result.fit_method == "mcmc":
            if hasattr(fit_result, "posteriors") and "period" in fit_result.posteriors:
                rec.period_sampled = True
                rec.period_err = fit_result.posteriors["period"].std
                rec.period_err_source = "posterior"
            else:
                rec.period_sampled = False
                rec.period_err = None
                rec.period_err_source = "fixed_in_mcmc"
        else:
            rec.period_sampled = False
            if getattr(fit_result, "period_err", None) not in (None, 0, 0.0):
                rec.period_err = fit_result.period_err
                rec.period_err_source = "map_approx"
            else:
                rec.period_err = None
                rec.period_err_source = "unavailable"

        # rp_rs contract
        if fit_result.fit_method == "mcmc":
            rec.rp_rs_sampled = True
            if hasattr(fit_result, "rp_rs_err") and fit_result.rp_rs_err not in (None, 0, 0.0):
                rec.rp_rs_err = fit_result.rp_rs_err
                rec.rp_rs_err_source = "posterior"
            else:
                rec.rp_rs_err = None
                rec.rp_rs_err_source = "unavailable"
        else:
            rec.rp_rs_sampled = False
            if getattr(fit_result, "rp_rs_err", None) not in (None, 0, 0.0):
                rec.rp_rs_err = fit_result.rp_rs_err
                rec.rp_rs_err_source = "map_approx"
            else:
                rec.rp_rs_err = None
                rec.rp_rs_err_source = "unavailable"

        # limb darkening contract
        if fit_result.fit_method == "mcmc" and hasattr(fit_result, "posteriors"):
            rec.u1_sampled = "u1" in fit_result.posteriors
            rec.u2_sampled = "u2" in fit_result.posteriors
            rec.u1_err_source = "posterior" if rec.u1_sampled else "fixed_in_mcmc"
            rec.u2_err_source = "posterior" if rec.u2_sampled else "fixed_in_mcmc"
        else:
            rec.u1_sampled = False
            rec.u2_sampled = False
            rec.u1_err_source = "fixed_or_unavailable"
            rec.u2_err_source = "fixed_or_unavailable"

        rec.derived_errors_available = False

        rec.impact_parameter = fit_result.impact_parameter
        rec.u1 = fit_result.u1
        rec.u2 = fit_result.u2
        rec.log_jitter = fit_result.log_jitter
        rec.baseline = fit_result.baseline
        rec.log_likelihood = fit_result.log_likelihood
        rec.fit_method = fit_result.fit_method"""
    if old in content:
        content = content.replace(old, new)
        print("OK schemas: fit contract mantigi eklendi")
        changed = True

    old = """    else:
        # Fit başarısız veya yapılmadı → cascade bulgularını kullan
        # (Cascade zaten TLS'ten iyi tahminler getirdi)
        rec.fit_method = "cascade_only" """
    new = """    else:
        # Fit başarısız veya yapılmadı → cascade bulgularını kullan
        # (Cascade zaten TLS'ten iyi tahminler getirdi)
        rec.fit_method = "cascade_only"
        rec.fit_status = "cascade_only"
        rec.posterior_available = False
        rec.posterior_converged = False
        rec.fallback_used = False"""
    if old in content:
        content = content.replace(old, new)
        print("OK schemas: cascade_only contract eklendi")
        changed = True

    if changed:
        schemas_file.write_text(content, encoding="utf-8")

    ast.parse(schemas_file.read_text(encoding="utf-8"))
    return True


def patch_parquet_schema():
    if not parquet_file.exists():
        print("HATA: parquet_writer.py bulunamadi")
        return False

    backup = parquet_file.with_suffix(".py.contract_backup")
    shutil.copy(parquet_file, backup)
    print(f"OK Yedek: {backup.name}")

    content = parquet_file.read_text(encoding="utf-8")
    changed = False

    marker = """        # Modelleme
        pa.field("fit_method", pa.string()),
        pa.field("log_likelihood", pa.float64()),
        pa.field("r_hat_max", pa.float64()),
        pa.field("n_divergences", pa.int32()),
        pa.field("mcmc_converged", pa.bool_()),

        # Dosya yolları"""
    replacement = """        # Modelleme
        pa.field("fit_method", pa.string()),
        pa.field("fit_status", pa.string()),
        pa.field("posterior_available", pa.bool_()),
        pa.field("posterior_converged", pa.bool_()),
        pa.field("fallback_used", pa.bool_()),
        pa.field("log_likelihood", pa.float64()),
        pa.field("r_hat_max", pa.float64()),
        pa.field("n_divergences", pa.int32()),
        pa.field("mcmc_converged", pa.bool_()),

        # Parametre güvenilirlik contract
        pa.field("period_sampled", pa.bool_()),
        pa.field("period_err_source", pa.string()),
        pa.field("rp_rs_sampled", pa.bool_()),
        pa.field("rp_rs_err_source", pa.string()),
        pa.field("u1_sampled", pa.bool_()),
        pa.field("u1_err_source", pa.string()),
        pa.field("u2_sampled", pa.bool_()),
        pa.field("u2_err_source", pa.string()),
        pa.field("derived_errors_available", pa.bool_()),

        # Dosya yolları"""
    if marker in content:
        content = content.replace(marker, replacement)
        print("OK parquet schema: contract alanlari eklendi")
        changed = True

    if changed:
        parquet_file.write_text(content, encoding="utf-8")

    ast.parse(parquet_file.read_text(encoding="utf-8"))
    return True


def main():
    print("=" * 72)
    print("Output Contract Patch")
    print("=" * 72)

    ok1 = patch_fitter()
    ok2 = patch_schemas()
    ok3 = patch_parquet_schema()

    print()
    if ok1 and ok2 and ok3:
        print("BASARILI")
        return 0
    print("Bazi patchler basarisiz")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())