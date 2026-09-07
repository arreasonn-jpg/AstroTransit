"""Kalıcı çıktı şemaları ve pipeline sonuçlarını kayıt haline getiren yardımcılar.

`TransitCandidateRecord` Parquet/CSV için düz (flat) bir sözlük, JSON için
ise aynı bilgilerin insan tarafından okunabilir bölümlenmiş biçimini sağlar.
Kayıt oluşturma kodu, pipeline'ın opsiyonel adımlarını (katalog, fit,
vetting ve görselleştirme) tolere eder; böylece başarısız bir alt adım bütün
sonucun kaydedilmesini engellemez.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import math
from typing import Any, Optional

import numpy as np

from astrotransit.utils.identifiers import extract_tic_number


SCHEMA_VERSION = "1.1"


def _finite_or_none(value: Any) -> Any:
    """JSON/Arrow için numpy ve sonlu olmayan sayıları güvenli hale getirir."""

    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in value]


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Dataclass, mapping veya basit mock nesneleri için güvenli erişim."""

    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _length(value: Any) -> int:
    """NumPy dizileri dahil iterable'ların uzunluğunu güvenle döndürür."""

    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 0


def _dict_from_dataclass(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            pass
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return {}


@dataclass
class TransitCandidateRecord:
    """Tek bir hedef/sektör transit sonucunun düz çıktı kaydı.

    Tüm alanların varsayılanı olması, pipeline'ın aday bulunamayan veya fit
    çalıştırılamayan sonuçları da aynı Parquet şemasına yazabilmesini sağlar.
    ``None`` değerleri ölçümün mevcut olmadığını, sıfır ise ölçülen/değerlenen
    alanlarda gerçek sıfırı ifade eder.
    """

    # Hedef
    source_id: str = ""
    tic_id: int = 0
    mission: str = "TESS"
    sector: int = -1
    instrument: str = "TESS"

    # Yıldız
    radius_rsun: Optional[float] = 0.0
    mass_msun: Optional[float] = 0.0
    teff_k: Optional[float] = 0.0
    tmag: Optional[float] = 0.0
    logg: Optional[float] = 0.0
    ra_deg: Optional[float] = 0.0
    dec_deg: Optional[float] = 0.0

    # Tespit
    bls_period: Optional[float] = 0.0
    bls_power: Optional[float] = 0.0
    bls_depth_ppm: Optional[float] = 0.0
    tls_period: Optional[float] = 0.0
    tls_sde: Optional[float] = 0.0
    tls_snr: Optional[float] = 0.0
    tls_odd_even_mismatch: Optional[float] = 0.0
    cascade_status: str = ""
    cascade_confirmed: bool = False

    # Transit parametreleri
    period: Optional[float] = 0.0
    period_err: Optional[float] = 0.0
    t0: Optional[float] = 0.0
    duration_hours: Optional[float] = 0.0
    depth: Optional[float] = 0.0
    depth_ppm: Optional[float] = 0.0
    rp_rs: Optional[float] = 0.0
    rp_rs_err: Optional[float] = 0.0
    impact_parameter: Optional[float] = 0.0
    a_over_rs: Optional[float] = 0.0
    inclination_deg: Optional[float] = 0.0
    u1: Optional[float] = 0.0
    u2: Optional[float] = 0.0
    log_jitter: Optional[float] = 0.0
    baseline: Optional[float] = 1.0

    # Türetilmiş fiziksel parametreler
    planet_radius_rearth: Optional[float] = 0.0
    planet_radius_rjup: Optional[float] = 0.0
    semi_major_axis_au: Optional[float] = 0.0
    equilibrium_temperature_k: Optional[float] = 0.0
    insolation_flux: Optional[float] = 0.0
    stellar_density_gcm3: Optional[float] = 0.0
    transit_depth_ppm: Optional[float] = 0.0

    # Kalite
    snr_adopted: Optional[float] = 0.0
    snr_tls: Optional[float] = 0.0
    snr_dutycycle: Optional[float] = 0.0
    noise_ppm: Optional[float] = 0.0
    cdpp_1hr_ppm: Optional[float] = 0.0
    data_completeness: Optional[float] = 0.0
    n_points: int = 0
    n_transits: int = 0
    residual_rms_ppm: Optional[float] = 0.0
    transit_symmetry: Optional[float] = 0.0
    timing_rms_min: Optional[float] = 0.0

    # Vetting
    fpp: Optional[float] = 0.0
    is_false_positive: bool = False
    is_variable_star: bool = False
    is_binary_suspect: bool = False
    secondary_eclipse_depth_ppm: Optional[float] = 0.0
    n_pass: int = 0
    n_fail: int = 0
    n_warn: int = 0
    flags: str = ""

    # Skor
    total_score: Optional[float] = 0.0
    candidate_class: str = ""
    is_anomalous: bool = False
    anomaly_flags: str = ""

    # Modelleme ve örnekleme sözleşmesi
    fit_method: str = ""
    fit_status: str = ""
    posterior_available: bool = False
    posterior_converged: bool = False
    fallback_used: bool = False
    log_likelihood: Optional[float] = 0.0
    r_hat_max: Optional[float] = 0.0
    n_divergences: int = 0
    mcmc_converged: bool = False
    period_sampled: bool = False
    period_err_source: str = ""
    rp_rs_sampled: bool = False
    rp_rs_err_source: str = ""
    u1_sampled: bool = False
    u1_err_source: str = ""
    u2_sampled: bool = False
    u2_err_source: str = ""
    derived_errors_available: bool = False

    # Dosya/provenance
    json_path: str = ""
    figure_dir: str = ""
    created_at: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        # Dataclass'a dışarıdan numpy scalar veya NaN verilse bile kayıt
        # serileştirmeden önce normalize edilebilir; burada yalnızca temel
        # kimliği standartlaştırıyoruz.
        self.source_id = str(self.source_id or "")
        self.mission = str(self.mission or "TESS")
        self.instrument = str(self.instrument or "TESS")

    def to_flat_dict(self) -> dict[str, Any]:
        """Parquet/CSV için tek seviyeli, serileştirilebilir sözlük döndürür."""

        result: dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, (list, tuple, np.ndarray)):
                value = list(value)
            result[item.name] = _finite_or_none(value)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Geriye dönük uyumluluk için düz kayıt sözlüğü."""

        return self.to_flat_dict()

    def to_nested_dict(self) -> dict[str, Any]:
        """JSON rapor formatındaki bölümlenmiş temsil."""

        flat = self.to_flat_dict()
        return {
            "metadata": {
                "astrotransit_version": "0.1.0",
                "created_at": flat["created_at"],
                "schema_version": flat["schema_version"],
            },
            "target": {
                "source_id": flat["source_id"],
                "tic_id": flat["tic_id"],
                "mission": flat["mission"],
                "sector": flat["sector"],
                "instrument": flat["instrument"],
            },
            "stellar": {
                "radius_rsun": flat["radius_rsun"],
                "mass_msun": flat["mass_msun"],
                "teff_k": flat["teff_k"],
                "tmag": flat["tmag"],
                "logg": flat["logg"],
                "ra_deg": flat["ra_deg"],
                "dec_deg": flat["dec_deg"],
            },
            "detection": {
                "bls": {
                    "period_days": flat["bls_period"],
                    "power": flat["bls_power"],
                    "depth_ppm": flat["bls_depth_ppm"],
                },
                "tls": {
                    "period_days": flat["tls_period"],
                    "sde": flat["tls_sde"],
                    "snr": flat["tls_snr"],
                    "odd_even_mismatch": flat["tls_odd_even_mismatch"],
                },
                "cascade": {
                    "status": flat["cascade_status"],
                    "confirmed": flat["cascade_confirmed"],
                },
            },
            "parameters": {
                "period_days": flat["period"],
                "period_err_days": flat["period_err"],
                "t0_btjd": flat["t0"],
                "duration_hours": flat["duration_hours"],
                "depth": flat["depth"],
                "depth_ppm": flat["depth_ppm"],
                "rp_rs": flat["rp_rs"],
                "rp_rs_err": flat["rp_rs_err"],
                "impact_parameter": flat["impact_parameter"],
                "a_over_rs": flat["a_over_rs"],
                "inclination_deg": flat["inclination_deg"],
                "u1": flat["u1"],
                "u2": flat["u2"],
                "log_jitter": flat["log_jitter"],
                "baseline": flat["baseline"],
            },
            "derived": {
                "planet_radius_rearth": flat["planet_radius_rearth"],
                "planet_radius_rjup": flat["planet_radius_rjup"],
                "semi_major_axis_au": flat["semi_major_axis_au"],
                "equilibrium_temperature_k": flat["equilibrium_temperature_k"],
                "insolation_flux": flat["insolation_flux"],
                "stellar_density_gcm3": flat["stellar_density_gcm3"],
                "transit_depth_ppm": flat["transit_depth_ppm"],
            },
            "quality": {
                "snr_adopted": flat["snr_adopted"],
                "snr_tls": flat["snr_tls"],
                "snr_dutycycle": flat["snr_dutycycle"],
                "noise_ppm": flat["noise_ppm"],
                "cdpp_1hr_ppm": flat["cdpp_1hr_ppm"],
                "data_completeness": flat["data_completeness"],
                "n_points": flat["n_points"],
                "n_transits": flat["n_transits"],
                "residual_rms_ppm": flat["residual_rms_ppm"],
                "transit_symmetry": flat["transit_symmetry"],
                "timing_rms_min": flat["timing_rms_min"],
            },
            "vetting": {
                "fpp": flat["fpp"],
                "is_false_positive": flat["is_false_positive"],
                "is_variable_star": flat["is_variable_star"],
                "is_binary_suspect": flat["is_binary_suspect"],
                "secondary_eclipse_depth_ppm": flat["secondary_eclipse_depth_ppm"],
                "n_pass": flat["n_pass"],
                "n_fail": flat["n_fail"],
                "n_warn": flat["n_warn"],
                "flags": flat["flags"],
            },
            "score": {
                "total_score": flat["total_score"],
                "candidate_class": flat["candidate_class"],
                "is_anomalous": flat["is_anomalous"],
                "anomaly_flags": flat["anomaly_flags"],
            },
            "modeling": {
                "fit_method": flat["fit_method"],
                "fit_status": flat["fit_status"],
                "posterior_available": flat["posterior_available"],
                "posterior_converged": flat["posterior_converged"],
                "fallback_used": flat["fallback_used"],
                "log_likelihood": flat["log_likelihood"],
                "r_hat_max": flat["r_hat_max"],
                "n_divergences": flat["n_divergences"],
                "mcmc_converged": flat["mcmc_converged"],
                "period_sampled": flat["period_sampled"],
                "period_err_source": flat["period_err_source"],
                "rp_rs_sampled": flat["rp_rs_sampled"],
                "rp_rs_err_source": flat["rp_rs_err_source"],
                "u1_sampled": flat["u1_sampled"],
                "u1_err_source": flat["u1_err_source"],
                "u2_sampled": flat["u2_sampled"],
                "u2_err_source": flat["u2_err_source"],
                "derived_errors_available": flat["derived_errors_available"],
            },
            "files": {
                "json_path": flat["json_path"],
                "figure_dir": flat["figure_dir"],
            },
        }


def _stellar_value(stellar_props: Any, attr: str, default: Any = 0.0) -> Any:
    return _finite_or_none(_get(stellar_props, attr, default))


def build_record(
    candidate: Any,
    quality_result: Any = None,
    fit_result: Any = None,
    stellar_props: Any = None,
    *,
    json_path: str = "",
    figure_dir: str = "",
) -> TransitCandidateRecord:
    """Pipeline nesnelerinden ``TransitCandidateRecord`` üretir.

    Bu fonksiyon bilinçli olarak duck-typed'dır; testlerde kullanılan küçük
    mock nesneleri ve gerçek pipeline dataclass'ları aynı arayüzü paylaşır.
    """

    candidate = candidate
    bls = _get(candidate, "bls_result")
    bls_peak = _get(bls, "best")
    tls = _get(candidate, "tls_result")

    quality_metrics = _get(quality_result, "metrics")
    photometric = _get(quality_metrics, "photometric")
    transit_metrics = _get(quality_metrics, "transit")
    stellar_metrics = _get(quality_metrics, "stellar")
    snr = _get(quality_result, "snr")
    vetting = _get(quality_result, "vetting")
    score = _get(quality_result, "score")
    anomaly = _get(quality_result, "anomaly")

    fit_success = bool(_get(fit_result, "success", False))
    fit_method = str(_get(fit_result, "fit_method", "") or "")

    # Fit mevcut değilse cascade değerleri kullanılır.
    period = _get(fit_result, "period") if fit_success else _get(candidate, "period", 0.0)
    period_err = _get(fit_result, "period_err") if fit_success else _get(candidate, "period_err", 0.0)
    t0 = _get(fit_result, "t0") if fit_success else _get(candidate, "t0", 0.0)
    rp_rs = _get(fit_result, "rp_rs") if fit_success else _get(candidate, "rp_rs", 0.0)
    impact = _get(fit_result, "impact_parameter") if fit_success else 0.0
    a_over_rs = _get(fit_result, "a_over_rs") if fit_success else 0.0
    inclination = (
        _get(fit_result, "inclination", _get(fit_result, "inclination_deg", 0.0))
        if fit_success else 0.0
    )
    u1 = _get(fit_result, "u1") if fit_success else 0.0
    u2 = _get(fit_result, "u2") if fit_success else 0.0
    log_jitter = _get(fit_result, "log_jitter") if fit_success else 0.0
    baseline = _get(fit_result, "baseline", 1.0) if fit_success else 1.0

    candidate_depth = _get(candidate, "depth", 0.0)
    candidate_duration = _get(candidate, "duration", 0.0)
    candidate_depth_ppm = _finite_or_none(candidate_depth * 1e6) if candidate_depth is not None else 0.0

    # Fit sonucu yokken de yıldız bilgisi ve cascade parametreleri ile
    # fiziksel türevler hesaplanabilir. Hesaplama başarısızsa sıfır bırakılır.
    derived = _get(fit_result, "derived") if fit_success else None
    if derived is None:
        try:
            from astrotransit.modeling.parameters import compute_derived_parameters

            if float(period or 0) > 0 and float(rp_rs or 0) > 0:
                derived = compute_derived_parameters(
                    period=float(period),
                    rp_rs=float(rp_rs),
                    impact_parameter=float(impact or 0),
                    duration=float(candidate_duration or 0.1),
                    stellar_radius=float(_get(stellar_props, "radius", 1.0) or 1.0),
                    stellar_mass=float(_get(stellar_props, "mass", 1.0) or 1.0),
                    stellar_teff=float(_get(stellar_props, "teff", 5778.0) or 5778.0),
                )
        except Exception:
            derived = None

    derived_dict = _dict_from_dataclass(derived)
    candidate_class = _get(score, "candidate_class", "")
    candidate_class = getattr(candidate_class, "value", candidate_class) or ""
    anomaly_flags = _as_list(_get(score, "anomaly_flags", []))
    if anomaly is not None:
        anomaly_flags.extend(_as_list(_get(anomaly, "recommended_action", "")))
    fp_flags = _as_list(_get(vetting, "fp_flags", []))

    # MCMC sampling contract. Eski fit sonuçlarında bu alanlar olmayabilir.
    posterior_available = bool(_get(fit_result, "posterior_available", fit_method == "mcmc"))
    posterior_converged = bool(
        _get(fit_result, "posterior_converged", _get(fit_result, "convergence_ok", False))
    )
    if fit_success and fit_method == "mcmc":
        posteriors = _get(fit_result, "posteriors", {}) or {}
        period_sampled = "period" in posteriors
        period_err_source = "posterior" if period_sampled else "fixed_in_mcmc"
        rp_rs_sampled = True
        rp_rs_err_source = "posterior" if _get(fit_result, "rp_rs_err", 0.0) not in (None, 0, 0.0) else "unavailable"
        u1_sampled = "u1" in posteriors
        u2_sampled = "u2" in posteriors
        fit_status = str(_get(fit_result, "fit_status", "mcmc_success"))
    elif fit_success:
        period_sampled = False
        period_err_source = "map_approx" if period_err not in (None, 0, 0.0) else "unavailable"
        rp_rs_sampled = False
        rp_rs_err_source = "unavailable"
        u1_sampled = u2_sampled = False
        fit_status = str(_get(fit_result, "fit_status", "map_success"))
    else:
        period_sampled = False
        period_err_source = "unavailable"
        rp_rs_sampled = False
        rp_rs_err_source = "unavailable"
        u1_sampled = u2_sampled = False
        fit_status = "cascade_only" if candidate is not None else "unfitted"
        fit_method = "cascade_only" if candidate is not None else ""

    return TransitCandidateRecord(
        source_id=str(_get(candidate, "target_id", "") or ""),
        tic_id=_tic_id_or_zero(_get(candidate, "target_id", "")),
        sector=int(_get(candidate, "sector", -1) or -1),
        radius_rsun=_stellar_value(stellar_props, "radius"),
        mass_msun=_stellar_value(stellar_props, "mass"),
        teff_k=_stellar_value(stellar_props, "teff"),
        tmag=_stellar_value(stellar_props, "tmag"),
        logg=_stellar_value(stellar_props, "logg"),
        ra_deg=_stellar_value(stellar_props, "ra"),
        dec_deg=_stellar_value(stellar_props, "dec"),
        bls_period=_finite_or_none(_get(bls_peak, "period", 0.0)),
        bls_power=_finite_or_none(_get(bls_peak, "power", 0.0)),
        bls_depth_ppm=_finite_or_none((_get(bls_peak, "depth", 0.0) or 0.0) * 1e6),
        tls_period=_finite_or_none(_get(tls, "period", 0.0)),
        tls_sde=_finite_or_none(_get(tls, "sde", 0.0)),
        tls_snr=_finite_or_none(_get(tls, "snr", 0.0)),
        tls_odd_even_mismatch=_finite_or_none(_get(tls, "odd_even_mismatch", 0.0)),
        cascade_status=str(getattr(_get(candidate, "status", ""), "value", _get(candidate, "status", "")) or ""),
        cascade_confirmed=bool(_get(candidate, "confirmed", False)),
        period=_finite_or_none(period),
        period_err=_finite_or_none(period_err),
        t0=_finite_or_none(t0),
        duration_hours=_finite_or_none((candidate_duration or 0.0) * 24),
        depth=_finite_or_none(candidate_depth),
        depth_ppm=_finite_or_none(candidate_depth_ppm),
        rp_rs=_finite_or_none(rp_rs),
        rp_rs_err=_finite_or_none(_get(fit_result, "rp_rs_err", 0.0) if fit_success else 0.0),
        impact_parameter=_finite_or_none(impact),
        a_over_rs=_finite_or_none(a_over_rs),
        inclination_deg=_finite_or_none(inclination),
        u1=_finite_or_none(u1),
        u2=_finite_or_none(u2),
        log_jitter=_finite_or_none(log_jitter),
        baseline=_finite_or_none(baseline),
        planet_radius_rearth=_finite_or_none(derived_dict.get("planet_radius_rearth", 0.0)),
        planet_radius_rjup=_finite_or_none(derived_dict.get("planet_radius_rjup", 0.0)),
        semi_major_axis_au=_finite_or_none(derived_dict.get("semi_major_axis_au", 0.0)),
        equilibrium_temperature_k=_finite_or_none(derived_dict.get("equilibrium_temperature_k", 0.0)),
        insolation_flux=_finite_or_none(derived_dict.get("insolation_flux", 0.0)),
        stellar_density_gcm3=_finite_or_none(derived_dict.get("stellar_density_gcm3", 0.0)),
        transit_depth_ppm=_finite_or_none(derived_dict.get("transit_depth_ppm", candidate_depth_ppm)),
        snr_adopted=_finite_or_none(_get(snr, "snr_adopted", _get(candidate, "snr", 0.0))),
        snr_tls=_finite_or_none(_get(snr, "snr_tls", _get(tls, "snr", 0.0))),
        snr_dutycycle=_finite_or_none(_get(snr, "snr_dutycycle", 0.0)),
        noise_ppm=_finite_or_none(_get(snr, "noise_floor_ppm", _get(photometric, "noise_ppm", 0.0))),
        cdpp_1hr_ppm=_finite_or_none(_get(photometric, "cdpp_1hr", 0.0)),
        data_completeness=_finite_or_none(_get(photometric, "data_completeness", 0.0)),
        n_points=int(_get(photometric, "n_points", 0) or 0),
        n_transits=int(
            _get(
                transit_metrics,
                "n_transits",
                _length(_get(candidate, "transit_times", [])),
            )
            or 0
        ),
        residual_rms_ppm=_finite_or_none((_get(transit_metrics, "residual_rms", 0.0) or 0.0) * 1e6),
        transit_symmetry=_finite_or_none(_get(transit_metrics, "transit_symmetry", 0.0)),
        timing_rms_min=_finite_or_none((_get(transit_metrics, "timing_rms", 0.0) or 0.0) * 1440),
        fpp=_finite_or_none(_get(vetting, "false_positive_probability", 0.0)),
        is_false_positive=bool(_get(vetting, "is_false_positive", False)),
        is_variable_star=bool(_get(stellar_metrics, "is_variable_star", False)),
        is_binary_suspect=bool(_get(stellar_metrics, "is_binary_suspect", False)),
        secondary_eclipse_depth_ppm=_finite_or_none((_get(stellar_metrics, "secondary_eclipse_depth", 0.0) or 0.0) * 1e6),
        n_pass=int(_get(vetting, "n_pass", 0) or 0),
        n_fail=int(_get(vetting, "n_fail", 0) or 0),
        n_warn=int(_get(vetting, "n_warn", 0) or 0),
        flags=", ".join(fp_flags),
        total_score=_finite_or_none(_get(score, "total_score", 0.0)),
        candidate_class=str(candidate_class),
        is_anomalous=bool(_get(score, "is_anomalous", False) or _get(anomaly, "anomaly_flag", "") not in ("", "CLEAN", "UNKNOWN")),
        anomaly_flags=", ".join(dict.fromkeys(anomaly_flags)),
        fit_method=fit_method,
        fit_status=fit_status,
        posterior_available=posterior_available,
        posterior_converged=posterior_converged,
        fallback_used=bool(_get(fit_result, "fallback_used", False)),
        log_likelihood=_finite_or_none(_get(fit_result, "log_likelihood", 0.0) if fit_success else 0.0),
        r_hat_max=_finite_or_none(_get(fit_result, "r_hat_max", 0.0) if fit_success else 0.0),
        n_divergences=int(_get(fit_result, "n_divergences", 0) or 0),
        mcmc_converged=bool(_get(fit_result, "convergence_ok", False)),
        period_sampled=period_sampled,
        period_err_source=period_err_source,
        rp_rs_sampled=rp_rs_sampled,
        rp_rs_err_source=rp_rs_err_source,
        u1_sampled=u1_sampled,
        u1_err_source="posterior" if u1_sampled else "fixed_or_unavailable",
        u2_sampled=u2_sampled,
        u2_err_source="posterior" if u2_sampled else "fixed_or_unavailable",
        derived_errors_available=False,
        json_path=json_path,
        figure_dir=figure_dir,
    )


def _tic_id_or_zero(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(extract_tic_number(str(value)))
    except (TypeError, ValueError):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
