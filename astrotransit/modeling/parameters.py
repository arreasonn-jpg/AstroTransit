"""
Transit ve yörünge parametresi tanımları.

Bu modül pipeline boyunca kullanılan tüm parametre
isimlerini, birimlerini ve fiziksel sınırlarını
merkezi olarak tanımlar.

Literatür referansları:
    Winn (2010) — Transits and Occultations
    Seager & Mallén-Ornelas (2003) — A Unique Solution
    Mandel & Agol (2002) — Analytic Light Curves
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np


# ──────────────────────────────────────
# Fiziksel sabitler
# ──────────────────────────────────────
class PhysicalConstants:
    """Kullanılan fiziksel sabitler (SI)."""

    G = 6.674e-11            # Evrensel çekim sabiti (m³ kg⁻¹ s⁻²)
    R_SUN = 6.957e8          # Güneş yarıçapı (m)
    M_SUN = 1.989e30         # Güneş kütlesi (kg)
    R_JUP = 7.1492e7         # Jüpiter yarıçapı (m)
    R_EARTH = 6.371e6        # Dünya yarıçapı (m)
    AU = 1.496e11            # Astronomik birim (m)
    SIGMA_SB = 5.6704e-8     # Stefan-Boltzmann sabiti (W m⁻² K⁻⁴)
    T_SUN = 5778.0           # Güneş efektif sıcaklığı (K)
    L_SUN = 3.828e26         # Güneş luminositesi (W)


CONST = PhysicalConstants()


# ──────────────────────────────────────
# Parametre sınır tanımları
# ──────────────────────────────────────
@dataclass
class ParameterBounds:
    """
    Tek bir parametrenin fiziksel sınırları ve prior bilgisi.

    Attributes
    ----------
    name : str
        Parametre adı.
    lower : float
        Fiziksel alt sınır.
    upper : float
        Fiziksel üst sınır.
    unit : str
        Birim.
    description : str
        Kısa açıklama.
    prior_type : str
        Prior dağılımı tipi: "uniform", "normal", "loguniform".
    prior_mu : float, opsiyonel
        Normal prior merkezi.
    prior_sigma : float, opsiyonel
        Normal prior standart sapması.
    """

    name: str
    lower: float
    upper: float
    unit: str
    description: str
    prior_type: str = "uniform"
    prior_mu: Optional[float] = None
    prior_sigma: Optional[float] = None

    def is_valid(self, value: float) -> bool:
        """Değerin fiziksel sınırlar içinde olup olmadığını kontrol eder."""
        return self.lower <= value <= self.upper

    def clip(self, value: float) -> float:
        """Değeri fiziksel sınırlar içine kırpar."""
        return float(np.clip(value, self.lower, self.upper))


# ──────────────────────────────────────
# Transit parametresi kataloğu
# ──────────────────────────────────────
TRANSIT_PARAMETER_BOUNDS: dict[str, ParameterBounds] = {

    # ── Temel transit parametreleri ──
    "period": ParameterBounds(
        name="period",
        lower=0.1,
        upper=1000.0,
        unit="day",
        description="Orbital period",
        prior_type="uniform",
    ),
    "t0": ParameterBounds(
        name="t0",
        lower=-1e6,
        upper=1e6,
        unit="BTJD",
        description="Reference transit center time",
        prior_type="uniform",
    ),
    "rp_rs": ParameterBounds(
        name="rp_rs",
        lower=0.001,
        upper=0.5,
        unit="dimensionless",
        description="Planet-to-star radius ratio Rp/Rs",
        prior_type="uniform",
    ),
    "duration": ParameterBounds(
        name="duration",
        lower=0.005,
        upper=1.0,
        unit="day",
        description="Transit duration (first to last contact)",
        prior_type="uniform",
    ),
    "impact_parameter": ParameterBounds(
        name="impact_parameter",
        lower=0.0,
        upper=1.0 + 0.5,  # 1 + max(rp_rs) — grazing izin ver
        unit="dimensionless",
        description="Impact parameter b = (a/Rs) cos(i)",
        prior_type="uniform",
    ),

    # ── Yıldız parametreleri ──
    "stellar_radius": ParameterBounds(
        name="stellar_radius",
        lower=0.05,
        upper=100.0,
        unit="R_sun",
        description="Stellar radius",
        prior_type="normal",
        prior_mu=1.0,
        prior_sigma=0.1,
    ),
    "stellar_mass": ParameterBounds(
        name="stellar_mass",
        lower=0.05,
        upper=50.0,
        unit="M_sun",
        description="Stellar mass",
        prior_type="normal",
        prior_mu=1.0,
        prior_sigma=0.1,
    ),
    "stellar_density": ParameterBounds(
        name="stellar_density",
        lower=1e-3,
        upper=1e6,
        unit="kg/m³",
        description="Mean stellar density",
        prior_type="loguniform",
    ),

    # ── Limb darkening ──
    "u1": ParameterBounds(
        name="u1",
        lower=0.0,
        upper=1.0,
        unit="dimensionless",
        description="Quadratic limb darkening coefficient u1",
        prior_type="uniform",
    ),
    "u2": ParameterBounds(
        name="u2",
        lower=-1.0,
        upper=1.0,
        unit="dimensionless",
        description="Quadratic limb darkening coefficient u2",
        prior_type="uniform",
    ),

    # ── Sistematik ──
    "log_jitter": ParameterBounds(
        name="log_jitter",
        lower=-15.0,
        upper=0.0,
        unit="log(e-)",
        description="Log of additional white noise term",
        prior_type="uniform",
    ),
    "baseline": ParameterBounds(
        name="baseline",
        lower=0.9,
        upper=1.1,
        unit="dimensionless",
        description="Flux baseline offset",
        prior_type="normal",
        prior_mu=1.0,
        prior_sigma=0.01,
    ),
}


# ──────────────────────────────────────
# Transit fit girdisi
# ──────────────────────────────────────
@dataclass
class TransitPriors:
    """
    Bir transit fit işlemi için prior değerleri.

    CascadeCandidate sonuçlarından otomatik olarak
    oluşturulur. MAP ve MCMC fit'leri için başlangıç
    noktası ve Bayesyen prior olarak kullanılır.

    Attributes
    ----------
    period : float
        Periyot başlangıç değeri (gün).
    period_bounds : tuple[float, float]
        Periyot alt-üst sınırları.
    t0 : float
        Birinci transit zamanı (BTJD).
    t0_bounds : tuple[float, float]
        t0 alt-üst sınırları.
    rp_rs : float
        Yarıçap oranı başlangıç değeri.
    rp_rs_bounds : tuple[float, float]
        rp_rs alt-üst sınırları.
    impact_parameter : float
        Etki parametresi başlangıç değeri.
    u1, u2 : float
        Limb darkening katsayıları.
    log_jitter : float
        Jitter başlangıç değeri.
    baseline : float
        Flux baseline başlangıç değeri.
    stellar_radius : float
        Yıldız yarıçapı (R_sun).
    stellar_mass : float
        Yıldız kütlesi (M_sun).
    """

    # Temel transit
    period: float = 1.0
    period_bounds: tuple[float, float] = (0.1, 100.0)

    t0: float = 0.0
    t0_bounds: tuple[float, float] = (-1e6, 1e6)

    rp_rs: float = 0.1
    rp_rs_bounds: tuple[float, float] = (0.001, 0.5)

    impact_parameter: float = 0.0
    impact_parameter_bounds: tuple[float, float] = (0.0, 1.2)

    duration: float = 0.1
    duration_bounds: tuple[float, float] = (0.005, 1.0)

    # Limb darkening (güneş benzeri yıldız için başlangıç değerleri)
    u1: float = 0.3
    u2: float = 0.2

    # Sistematik
    log_jitter: float = -7.0
    baseline: float = 1.0

    # Yıldız özellikleri
    stellar_radius: float = 1.0
    stellar_mass: float = 1.0
    stellar_teff: float = 5778.0

    def to_dict(self) -> dict:
        """Sözlük olarak döndürür."""
        return {
            "period": self.period,
            "t0": self.t0,
            "rp_rs": self.rp_rs,
            "impact_parameter": self.impact_parameter,
            "duration": self.duration,
            "u1": self.u1,
            "u2": self.u2,
            "log_jitter": self.log_jitter,
            "baseline": self.baseline,
            "stellar_radius": self.stellar_radius,
            "stellar_mass": self.stellar_mass,
        }

    @classmethod
    def from_cascade(
        cls,
        candidate,
        stellar_radius: float = 1.0,
        stellar_mass: float = 1.0,
        stellar_teff: float = 5778.0,
    ) -> "TransitPriors":
        """
        CascadeCandidate'den prior oluşturur.

        Parameters
        ----------
        candidate : CascadeCandidate
            Cascade tespit sonucu.
        stellar_radius : float
            Yıldız yarıçapı (R_sun).
        stellar_mass : float
            Yıldız kütlesi (M_sun).
        stellar_teff : float
            Yıldız efektif sıcaklığı (K).

        Returns
        -------
        TransitPriors
            Prior değerleri.
        """

        # Periyot sınırları: TLS belirsizliğinin 5 katı
        period_err = max(candidate.period_err, candidate.period * 0.001)
        p_lo = max(0.1, candidate.period - 5 * period_err)
        p_hi = candidate.period + 5 * period_err

        # t0 sınırları: ±1 periyot
        t0_lo = candidate.t0 - candidate.period
        t0_hi = candidate.t0 + candidate.period

        # rp_rs sınırları: TLS tahmininin ±50%'si
        rp_rs_init = max(0.001, candidate.rp_rs)
        rp_lo = max(0.001, rp_rs_init * 0.5)
        rp_hi = min(0.5, rp_rs_init * 2.0)

        # Limb darkening: Teff'e göre başlangıç tahmini
        # Claret & Bloemen (2011) tablosundan basit yaklaşım
        u1, u2 = cls._estimate_limb_darkening(stellar_teff)

        return cls(
            period=candidate.period,
            period_bounds=(p_lo, p_hi),
            t0=candidate.t0,
            t0_bounds=(t0_lo, t0_hi),
            rp_rs=rp_rs_init,
            rp_rs_bounds=(rp_lo, rp_hi),
            impact_parameter=0.3,
            impact_parameter_bounds=(0.0, 1.2),
            duration=candidate.duration,
            duration_bounds=(
                max(0.005, candidate.duration * 0.5),
                min(1.0, candidate.duration * 2.0),
            ),
            u1=u1,
            u2=u2,
            log_jitter=-7.0,
            baseline=1.0,
            stellar_radius=stellar_radius,
            stellar_mass=stellar_mass,
            stellar_teff=stellar_teff,
        )

    @staticmethod
    def _estimate_limb_darkening(teff: float) -> tuple[float, float]:
        """
        Efektif sıcaklıktan quadratic limb darkening katsayısı tahmini.

        Claret & Bloemen (2011) TESS bandı değerlerine dayalı
        basit doğrusal interpolasyon.

        Parameters
        ----------
        teff : float
            Yıldız efektif sıcaklığı (K).

        Returns
        -------
        tuple[float, float]
            (u1, u2) limb darkening katsayıları.
        """

        # Teff → (u1, u2) basit eşleme (TESS bandı)
        # Kaynak: Claret & Bloemen 2011, TESS passband yaklaşımı
        teff_grid = np.array([3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000])
        u1_grid = np.array([0.60, 0.52, 0.46, 0.40, 0.35, 0.30, 0.26, 0.22])
        u2_grid = np.array([0.15, 0.17, 0.18, 0.19, 0.20, 0.20, 0.19, 0.18])

        teff_clipped = float(np.clip(teff, teff_grid[0], teff_grid[-1]))
        u1 = float(np.interp(teff_clipped, teff_grid, u1_grid))
        u2 = float(np.interp(teff_clipped, teff_grid, u2_grid))

        return u1, u2


# ──────────────────────────────────────
# Türetilmiş parametre hesaplamaları
# ──────────────────────────────────────
@dataclass
class DerivedParameters:
    """
    Transit fit sonuçlarından türetilen fiziksel parametreler.

    Attributes
    ----------
    planet_radius_rjup : float
        Gezegen yarıçapı (Jüpiter yarıçapı).
    planet_radius_rearth : float
        Gezegen yarıçapı (Dünya yarıçapı).
    semi_major_axis_au : float
        Yarı-büyük eksen (AU).
    inclination_deg : float
        Yörünge eğimi (derece).
    stellar_density_gcm3 : float
        Yıldız ortalama yoğunluğu (g/cm³).
    equilibrium_temperature_k : float
        Denge sıcaklığı (K, albedo=0.3 varsayımı).
    transit_depth_ppm : float
        Transit derinliği (ppm).
    insolation_flux : float
        Aldığı ışınım akısı (Dünya'nın aldığının katı).
    """

    planet_radius_rjup: float = 0.0
    planet_radius_rearth: float = 0.0
    semi_major_axis_au: float = 0.0
    inclination_deg: float = 90.0
    stellar_density_gcm3: float = 0.0
    equilibrium_temperature_k: float = 0.0
    transit_depth_ppm: float = 0.0
    insolation_flux: float = 0.0
    equilibrium_temperature_albedo: float = 0.3

    def to_dict(self) -> dict:
        return {
            "planet_radius_rjup": round(self.planet_radius_rjup, 4),
            "planet_radius_rearth": round(self.planet_radius_rearth, 4),
            "semi_major_axis_au": round(self.semi_major_axis_au, 6),
            "inclination_deg": round(self.inclination_deg, 4),
            "stellar_density_gcm3": round(self.stellar_density_gcm3, 4),
            "equilibrium_temperature_k": round(self.equilibrium_temperature_k, 2),
            "equilibrium_temperature_albedo": round(self.equilibrium_temperature_albedo, 4),
            "transit_depth_ppm": round(self.transit_depth_ppm, 2),
            "insolation_flux": round(self.insolation_flux, 4),
        }


def compute_derived_parameters(
    period: float,
    rp_rs: float,
    impact_parameter: float,
    duration: float,
    stellar_radius: float,
    stellar_mass: float,
    stellar_teff: float,
    albedo: float = 0.3,
) -> DerivedParameters:
    """
    Transit fit parametrelerinden fiziksel büyüklükleri hesaplar.

    Parameters
    ----------
    period : float
        Orbital periyot (gün).
    rp_rs : float
        Yarıçap oranı Rp/Rs.
    impact_parameter : float
        Etki parametresi b.
    duration : float
        Transit süresi (gün).
    stellar_radius : float
        Yıldız yarıçapı (R_sun).
    stellar_mass : float
        Yıldız kütlesi (M_sun).
    stellar_teff : float
        Yıldız efektif sıcaklığı (K).
    albedo : float
        Gezegen Bond albedosu.

    Returns
    -------
    DerivedParameters
        Hesaplanan fiziksel parametreler.
    """

    if not np.isfinite(albedo) or not 0.0 <= albedo <= 1.0:
        raise ValueError("Bond albedosu 0 ile 1 arasında olmalıdır.")

    derived = DerivedParameters(equilibrium_temperature_albedo=float(albedo))

    # Transit derinliği (ppm)
    derived.transit_depth_ppm = float((rp_rs ** 2) * 1e6)

    # Gezegen yarıçapı
    r_star_m = stellar_radius * CONST.R_SUN
    r_planet_m = rp_rs * r_star_m
    derived.planet_radius_rjup = float(r_planet_m / CONST.R_JUP)
    derived.planet_radius_rearth = float(r_planet_m / CONST.R_EARTH)

    # Yarı-büyük eksen (Kepler 3. Yasası)
    # a³ = G M* P² / (4π²)
    period_s = period * 86400.0
    m_star_kg = stellar_mass * CONST.M_SUN

    try:
        a_m = (CONST.G * m_star_kg * period_s ** 2 / (4 * np.pi ** 2)) ** (1.0 / 3.0)
        derived.semi_major_axis_au = float(a_m / CONST.AU)
    except (ValueError, ZeroDivisionError):
        derived.semi_major_axis_au = 0.0

    # Yıldız ortalama yoğunluğu (Seager & Mallén-Ornelas 2003)
    # ρ* = (3π / G P²) × (a/Rs)³
    # a/Rs Kepler yasasından çıkar
    try:
        r_star_m_val = stellar_radius * CONST.R_SUN
        if r_star_m_val > 0 and derived.semi_major_axis_au > 0:
            a_over_rs = (a_m / r_star_m_val)
            rho_star = (3 * np.pi / (CONST.G * period_s ** 2)) * a_over_rs ** 3
            derived.stellar_density_gcm3 = float(rho_star / 1000.0)  # kg/m³ → g/cm³
    except (ValueError, ZeroDivisionError):
        derived.stellar_density_gcm3 = 0.0

    # Yörünge eğimi
    # b = (a/Rs) × cos(i)  →  i = arccos(b × Rs / a)
    try:
        if derived.semi_major_axis_au > 0 and r_star_m_val > 0:
            cos_i = impact_parameter * r_star_m_val / a_m
            cos_i_clipped = float(np.clip(cos_i, -1.0, 1.0))
            derived.inclination_deg = float(np.degrees(np.arccos(cos_i_clipped)))
    except (ValueError, ZeroDivisionError):
        derived.inclination_deg = 90.0

    # Denge sıcaklığı
    # T_eq = T_star × sqrt(Rs / 2a) × (1 - A)^0.25
    try:
        if derived.semi_major_axis_au > 0:
            t_eq = (
                stellar_teff
                * np.sqrt(stellar_radius * CONST.R_SUN / (2 * a_m))
                * (1.0 - albedo) ** 0.25
            )
            derived.equilibrium_temperature_k = float(t_eq)
    except (ValueError, ZeroDivisionError):
        derived.equilibrium_temperature_k = 0.0

    # Güneş'e göre ışınım akısı (insolation flux)
    # F/F_earth = (L*/L_sun) × (1 AU / a)²
    try:
        if derived.semi_major_axis_au > 0:
            luminosity_lsun = (stellar_radius ** 2) * ((stellar_teff / CONST.T_SUN) ** 4)
            derived.insolation_flux = float(
                luminosity_lsun / (derived.semi_major_axis_au ** 2)
            )
    except (ValueError, ZeroDivisionError):
        derived.insolation_flux = 0.0

    return derived