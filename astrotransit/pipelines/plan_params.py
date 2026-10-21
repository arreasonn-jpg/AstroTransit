"""Analiz parametreleri (Plan/Yörünge parametreleri) yardımcı katmanı.

Kullanıcının masaüstünde manuel girdiği bilinen transit parametrelerini
(Periyot, T0, Rp/Rs, b, a/Rs, i, Re, Rj, AU, sıcaklık, Log L) kütüphanenin
``TransitPriors``/``MAPFitter`` katmanına bağlayan SAF (I/O'suz) mantık.

Kural: boş (None) bırakılan alanlar hariç — dolu olan alanlar prior'a;
Re/Rj/AU/Sıcaklık/Log L ise türetilmiş-referans veya yıldız yarıçapı
formülüne bağlanır. Hiç alan girilmemişse ``plan_from_user_input`` None
döndürür ve çağıran taraf varsayılan (kör arama) akışa devam eder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from astrotransit.modeling.parameters import TransitPriors

# ── Fiziksel sabitler (IAU 2015) ────────────────────────────────────────
R_SUN_CM = 6.957e10
R_EARTH_CM = 6.371e8
R_JUP_CM = 7.1492e9
AU_CM = 1.495978707e13
TEFF_SUN = 5778.0

_REQUIRED_FOR_PLAN_MODE = ("period_days", "t0_btjd")


@dataclass
class PlanParams:
    """Kullanıcının manuel analiz parametreleri (None = boş bırakıldı)."""

    period_days: Optional[float] = None
    t0_btjd: Optional[float] = None
    rp_rs: Optional[float] = None
    impact_parameter: Optional[float] = None
    a_over_rs: Optional[float] = None
    inclination_deg: Optional[float] = None
    planet_radius_rearth: Optional[float] = None
    planet_radius_rjup: Optional[float] = None
    semi_major_axis_au: Optional[float] = None
    teff_k: Optional[float] = None
    log_l_lsun: Optional[float] = None  # log10(L / L☉)

    extras: dict[str, Any] = field(default_factory=dict)

    def complete_for_plan_mode(self) -> bool:
        """Kısıtlı doğrulama için asgari zorunlu alanlar (P + T0) dolu mu?"""

        return all(getattr(self, name) is not None for name in _REQUIRED_FOR_PLAN_MODE)


def plan_params_from_user_input(
    values: Optional[dict[str, Any]],
) -> Optional[PlanParams]:
    """UI sözlüğünü ``PlanParams``'a çevirir.

    Kural: tüm anlamlı alanlar None/boş ise None döner (varsayılan kör
    arama). Sözlük anahtarları PlanParams alan adlarıyla aynıdır.
    """

    if not values:
        return None
    field_names = {f for f in PlanParams.__dataclass_fields__ if f != "extras"}
    cleaned: dict[str, Any] = {}
    for name in field_names:
        raw = values.get(name)
        value: Optional[float]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            value = None
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Geçersiz sayı: {name} = {raw!r}") from None
        cleaned[name] = value
    if all(v is None for v in cleaned.values()):
        return None
    params = PlanParams(**cleaned)
    _validate(params)
    return params


def _validate(params: PlanParams) -> None:
    """Aralık doğrulaması: kullanıcıya erkenden anlaşılır hata döner."""

    checks = (
        ("period_days", params.period_days, (0.0, 1e4), "Periyot > 0 olmalı"),
        (
            "rp_rs",
            params.rp_rs,
            (0.0, 0.5),
            "Rp/Rs 0 ile 0.5 arasında olmalı",
        ),
        (
            "impact_parameter",
            params.impact_parameter,
            (0.0, 1.2),
            "b sıfırı aşamaz (0 ≤ b ≤ 1.2)",
        ),
        (
            "a_over_rs",
            params.a_over_rs,
            (1.0, 1e4),
            "a/Rs en az 1 olmalı",
        ),
        (
            "inclination_deg",
            params.inclination_deg,
            (0.0, 90.0),
            "i 0 ile 90 derece arasında olmalı",
        ),
        (
            "planet_radius_rearth",
            params.planet_radius_rearth,
            (0.0, 1e5),
            "Re ≥ 0 olmalı",
        ),
        (
            "planet_radius_rjup",
            params.planet_radius_rjup,
            (0.0, 1e4),
            "Rj ≥ 0 olmalı",
        ),
        (
            "semi_major_axis_au",
            params.semi_major_axis_au,
            (1e-4, 1e5),
            "AU ≥ 0 olmalı",
        ),
        ("teff_k", params.teff_k, (1500.0, 50000.0), "Sıcaklık aralık dışı"),
    )
    for _name, value, (lo, hi), message in checks:
        if value is not None and not (lo <= value <= hi):
            raise ValueError(message)


def stellar_radius_from_log_l(teff_k: float, log_l_lsun: float) -> float:
    """Log luminosity + Teff'ten yıldız yarıçapı (R_sun).

    L/L☉ = (R/R☉)² · (Teff/T☉)⁴  →
    R/R☉ = sqrt(10^logL) · (T☉/Teff)²
    """

    if teff_k <= 0:
        raise ValueError("Teff pozitif olmalı")
    teff = float(teff_k)
    luminosity_ratio = float(10.0 ** float(log_l_lsun))
    radius = (luminosity_ratio ** 0.5) * (TEFF_SUN / teff) ** 2
    return float(radius)


def impact_parameter_from_geometry(
    a_over_rs: float,
    inclination_deg: float,
) -> float:
    """Geometriden etki parametresi: b = (a/Rs)·cos(i)."""

    import math

    if a_over_rs <= 0:
        raise ValueError("a/Rs pozitif olmalı")
    if not (0.0 <= inclination_deg <= 90.0):
        raise ValueError("i 0-90 derece arasında olmalı")
    return a_over_rs * math.cos(math.radians(inclination_deg))


def rp_rs_from_planet_radius_rearth(r_earth: float, stellar_rsun: float) -> float:
    """Kullanıcının Re (R⊕) girdisini Rp/Rs'e çevirir (R★ verilmişse)."""

    if stellar_rsun <= 0:
        raise ValueError("Yıldız yarıçapı pozitif olmalı")
    if r_earth < 0:
        raise ValueError("Re negatif olamaz")
    return (r_earth * R_EARTH_CM) / (stellar_rsun * R_SUN_CM)


def build_plan_priors(
    plan: PlanParams,
    *,
    stellar_radius: float,
    stellar_mass: float,
    stellar_teff: float,
) -> TransitPriors:
    """Kullanıcı parametrelerinden MAP prior'u kurar.

    Kurallar:
    - Periyot/T0 zorunlu (kısıtlı doğrulama ön koşulu).
    - Rp/Rs: doğrudan kullanıcı değeri, yoksa Re→Rp/Rs dönüşümü, ikisi de
      yoksa 0.05 varsayılanı.
    - b: doğrudan kullanıcı değeri, yoksa (a/Rs, i) geometrisi, o da yoksa 0
      (kenar geçişi bulunmayan) varsayılanı.
    - Yıldız: kullanıcı Teff+LogL vermişse yıldız yarıçapı formülden
      hesaplanır ve önceliği katalog değerine ÜSTÜNDÜR (kullanıcı bilinçli
      girdi; katalog arka plan referansıdır).
    """

    if not plan.complete_for_plan_mode():
        raise ValueError("Kısıtlı doğrulama için Periyot ve T0 zorunludur")
    period = plan.period_days
    t0 = plan.t0_btjd
    if period is None or t0 is None:  # mypy daraltması için çift koruma
        raise ValueError("Kısıtlı doğrulama için Periyot ve T0 zorunludur")

    if not plan.complete_for_plan_mode():
        raise ValueError("Kısıtlı doğrulama için Periyot ve T0 zorunludur")

    # Yıldız yarıçapı: kullanıcı önceliği
    radius_used = stellar_radius
    if plan.teff_k is not None and plan.log_l_lsun is not None:
        radius_used = stellar_radius_from_log_l(plan.teff_k, plan.log_l_lsun)
    teff_used = plan.teff_k if plan.teff_k is not None else stellar_teff

    # Rp/Rs
    if plan.rp_rs is not None:
        rp_rs = plan.rp_rs
    elif plan.planet_radius_rearth is not None:
        rp_rs = rp_rs_from_planet_radius_rearth(plan.planet_radius_rearth, radius_used)
    elif plan.planet_radius_rjup is not None:
        rp_rs = rp_rs_from_planet_radius_rearth(
            plan.planet_radius_rjup * R_JUP_CM / R_EARTH_CM, radius_used
        )
    else:
        rp_rs = 0.05

    # b
    if plan.impact_parameter is not None:
        impact = plan.impact_parameter
    elif plan.a_over_rs is not None and plan.inclination_deg is not None:
        impact = impact_parameter_from_geometry(plan.a_over_rs, plan.inclination_deg)
    else:
        impact = 0.0

    # Periyot ±%2 sık pencere: kısıtlı doğrulama bilinci
    period_window = max(period * 0.02, 1e-3)

    return TransitPriors(
        period=period,
        period_bounds=(period - period_window, period + period_window),
        t0=t0,
        t0_bounds=(t0 - 0.25, t0 + 0.25),
        rp_rs=rp_rs,
        impact_parameter=min(impact, 1.1),
        stellar_radius=radius_used,
        stellar_mass=stellar_mass,
        stellar_teff=teff_used,
    )
