"""
L1 sistem değerlendirmesi: yıldız-gezegen parametrelerinden L1 geometrisi,
kararlılık ve istasyon tutma gereksinimlerini tek çağrıda üretir.

Girişler eksikse (None) ilgili alanlar None kalır — "ölçülmeyen şey
null kalır" ilkesine uygun olarak 0.0 uydurulmaz.

Epistemik not: Bu değerlendirme iki kolu da besler ama aynı varsayımla
değil:
- Kol 1 (yaşanabilir L1 gezegeni): L1'in kendisi yaşanabilir bölge
  değildir; yaşanabilirlik ancak ana gezegen HZ'deyse ve L1 bölgesi
  yıldız ışınımına açık kaldığında anlamlıdır.
- Kol 2 (kontrollü yapı): L1 kararsızdır; yapının orada kalması ancak
  aktif istasyon tutma ile mümkündür. "L1'de görüldü" kontrol kanıtı
  değildir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from loguru import logger

from astrotransit.dynamics.cr3bp import (
    l1_eigenvalues,
    stability_e_folding_days,
    station_keeping_budget,
)
from astrotransit.dynamics.lagrange import (
    AU_M,
    DAY_S,
    collinear_equilibrium_x,
    hill_radius_au,
    l1_distance_from_planet_au,
    l1_distance_from_star_au,
    mass_ratio,
    orbital_period_days,
)


@dataclass(frozen=True)
class L1System:
    """Bir yıldız-gezegen çifti için L1 sistemi tanımı.

    Eksik parametreler None olarak saklanır; hesaplar None döndürür.
    """

    star_name: str
    m_star_kg: float | None = None
    m_planet_kg: float | None = None
    separation_au: float | None = None
    planet_in_habitable_zone: bool | None = None

    @property
    def mu(self) -> float | None:
        if self.m_star_kg is None or self.m_planet_kg is None:
            return None
        return mass_ratio(self.m_star_kg, self.m_planet_kg)

    @property
    def mean_motion_per_day(self) -> float | None:
        """n = 2*pi / periyot (rad/gün)."""
        if self.m_star_kg is None or self.separation_au is None:
            return None
        period_days = orbital_period_days(self.m_star_kg, self.separation_au)
        return 2.0 * math.pi / period_days

    @property
    def unit_velocity_m_per_s(self) -> float | None:
        """Birim hız a*n (m/s): CR3BP delta-v birimlerini gerçek hıza çevirir."""
        if self.separation_au is None or self.mean_motion_per_day is None:
            return None
        a_m = self.separation_au * AU_M
        n_per_s = self.mean_motion_per_day / DAY_S
        return a_m * n_per_s


@dataclass(frozen=True)
class L1Assessment:
    """assess_l1 çıktısı. Tüm alanlar hesaplanamıyorsa None kalır."""

    star_name: str
    mu: float | None
    x_l1: float | None
    l1_distance_from_star_au: float | None
    l1_distance_from_planet_au: float | None
    hill_radius_au: float | None
    orbital_period_days: float | None
    l1_unstable_eigenvalue: float | None
    stability_e_folding_days: float | None
    station_keeping: dict[str, float] | None
    planet_in_habitable_zone: bool | None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        def r(v: float | None) -> float | None:
            return None if v is None else round(v, 6)

        return {
            "star_name": self.star_name,
            "mu": r(self.mu),
            "x_l1": r(self.x_l1),
            "l1_distance_from_star_au": r(self.l1_distance_from_star_au),
            "l1_distance_from_planet_au": r(self.l1_distance_from_planet_au),
            "hill_radius_au": r(self.hill_radius_au),
            "orbital_period_days": r(self.orbital_period_days),
            "l1_unstable_eigenvalue": r(self.l1_unstable_eigenvalue),
            "stability_e_folding_days": r(self.stability_e_folding_days),
            "station_keeping": self.station_keeping,
            "planet_in_habitable_zone": self.planet_in_habitable_zone,
            "notes": list(self.notes),
        }


def assess_l1(
    system: L1System,
    correction_interval_days: float = 30.0,
    station_keeping_amplitude: float = 1e-4,
    mission_days: float = 365.25,
) -> L1Assessment:
    """L1 değerlendirmesini üretir.

    Eksik girdi varsa ilgili alanlar None döner; hata fırlatılmaz.
    """
    notes: list[str] = []
    mu = system.mu
    if mu is None:
        logger.warning(f"{system.star_name}: kütle bilgisi eksik, L1 geometrisi hesaplanamadı.")
        return L1Assessment(
            star_name=system.star_name,
            mu=None,
            x_l1=None,
            l1_distance_from_star_au=None,
            l1_distance_from_planet_au=None,
            hill_radius_au=None,
            orbital_period_days=None,
            l1_unstable_eigenvalue=None,
            stability_e_folding_days=None,
            station_keeping=None,
            planet_in_habitable_zone=system.planet_in_habitable_zone,
            notes=["kütle bilgisi eksik; tüm L1 alanları null"],
        )

    x_l1 = collinear_equilibrium_x(mu, "L1")
    sep = system.separation_au
    d_star = l1_distance_from_star_au(mu, sep) if sep is not None else None
    d_planet = l1_distance_from_planet_au(mu, sep) if sep is not None else None
    hill = hill_radius_au(mu, sep) if sep is not None else None
    period = orbital_period_days(system.m_star_kg, sep) if (system.m_star_kg is not None and sep is not None) else None

    eigs = l1_eigenvalues(mu)
    lam_max = float(max(e.real for e in eigs))
    n_per_day = system.mean_motion_per_day
    e_fold = stability_e_folding_days(mu, n_per_day) if n_per_day is not None else None

    sk: dict[str, float] | None = None
    if e_fold is not None:
        budget = station_keeping_budget(e_fold, mission_days, correction_interval_days, station_keeping_amplitude)
        u_v = system.unit_velocity_m_per_s
        if u_v is not None:
            budget = {
                **budget,
                "delta_v_per_correction_m_per_s": budget["delta_v_per_correction"] * u_v,
                "total_delta_v_m_per_s": budget["total_delta_v"] * u_v,
            }
        sk = budget
        notes.append(
            f"L1 kararsız: e-katlama süresi {e_fold:.1f} gün; "
            f"~{budget['n_corrections']:.0f} düzeltme/yıl gerekebilir (model tahmini)."
        )
    else:
        notes.append("ortalama hareket hesaplanamadı; kararlılık süresi null")

    if system.planet_in_habitable_zone is True:
        notes.append("Ana gezegen HZ'de: L1 bölgesi yıldız ışınımına açık olabilir (Kol 1 için ön koşul).")
    elif system.planet_in_habitable_zone is False:
        notes.append("Ana gezegen HZ dışı: L1 bölgesi yaşanabilirlik için elverişli değil (Kol 1 elenir).")
    else:
        notes.append("Ana gezegenin HZ durumu bilinmiyor: null (Kol 1 ön koşulu belirsiz).")

    notes.append("L1'de görülen bir cisim kontrol kanıtı değildir; istasyon tutma gereksinimi yukarıda modellenmiştir (Kol 2).")

    return L1Assessment(
        star_name=system.star_name,
        mu=mu,
        x_l1=x_l1,
        l1_distance_from_star_au=d_star,
        l1_distance_from_planet_au=d_planet,
        hill_radius_au=hill,
        orbital_period_days=period,
        l1_unstable_eigenvalue=lam_max,
        stability_e_folding_days=e_fold,
        station_keeping=sk,
        planet_in_habitable_zone=system.planet_in_habitable_zone,
        notes=notes,
    )


__all__ = ["L1Assessment", "L1System", "assess_l1"]
