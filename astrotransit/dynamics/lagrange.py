"""
Lagrange noktaları geometrisi (dairesel kısıtlı üç-cisim problemi, CR3BP).

Birimler: dönen (rotating) koordinatlarda, iki ana cisim arasındaki mesafe
birim uzunluk (a = 1) ve toplam kütle M = m1 + m2 = 1 alınır. m1 ana yıldız
(büyük kütle, x = -mu), m2 gezegen (küçük kütle, x = 1 - mu) ile yerleşir.

Kütle oranı: mu = m2 / (m1 + m2)  (0 < mu <= 0.5)

Kolineer denge noktaları L1, L2, L3 quintic denkleminin kökleridir; burada
Newton-Raphson ile çözülür. L1 yıldız ile gezegen arasındadır.

Not: L1 bir "yaşanabilir bölge" noktası değildir; yaşanabilir bölge
yıldızdan gelen ışınıma bağlıdır. Bu modül yalnızca geometrik/dinamik
konum üretir.
"""

from __future__ import annotations

import math

# Sabitler
G_SI = 6.67430e-11          # m^3 kg^-1 s^-2
M_SUN_KG = 1.98847e30
M_JUP_KG = 1.89813e27
M_EARTH_KG = 5.9722e24
AU_M = 1.495978707e11
DAY_S = 86400.0


def mass_ratio(m_star_kg: float, m_planet_kg: float) -> float:
    """CR3BP kütle oranı mu = m_planet / (m_star + m_planet).

    Negatif veya sıfır kütleler ValueError fırlatır; mu 0.5'i aşamaz.
    """
    if m_star_kg <= 0.0 or m_planet_kg <= 0.0:
        raise ValueError("Kütleler pozitif olmalıdır.")
    mu = m_planet_kg / (m_star_kg + m_planet_kg)
    if mu > 0.5:
        raise ValueError("mu 0.5'i aşamaz; büyük kütle yıldız kabul edilir.")
    return mu


def _f(x: float, mu: float) -> float:
    """Kolineer denge quintic'i: x - (1-mu)(x+mu)/|x+mu|^3 - mu(x-1+mu)/|x-1+mu|^3 = 0."""
    d1 = x + mu
    d2 = x - 1.0 + mu
    return x - (1.0 - mu) * d1 / abs(d1) ** 3 - mu * d2 / abs(d2) ** 3


def _fprime(x: float, mu: float) -> float:
    d1 = x + mu
    d2 = x - 1.0 + mu
    return 1.0 + 2.0 * (1.0 - mu) / abs(d1) ** 3 + 2.0 * mu / abs(d2) ** 3


def collinear_equilibrium_x(mu: float, point: str, tol: float = 1e-14, max_iter: int = 100) -> float:
    """Belirtilen kolinear noktanın (L1/L2/L3) x koordinatını Newton ile çözer.

    Başlangıç tahminleri klasik yaklaşımdır:
    - L1: gezegenin yıldıza bakan yüzü yakını, x0 = 1 - mu - (mu/3)^(1/3)
    - L2: gezegenin arkası, x0 = 1 - mu + (mu/3)^(1/3)
    - L3: yıldızın karşısı, x0 = -1 - 5mu/12
    """
    if not 0.0 < mu <= 0.5:
        raise ValueError("mu (0, 0.5] aralığında olmalıdır.")
    point = point.upper()
    if point == "L1":
        x = 1.0 - mu - (mu / 3.0) ** (1.0 / 3.0)
    elif point == "L2":
        x = 1.0 - mu + (mu / 3.0) ** (1.0 / 3.0)
    elif point == "L3":
        x = -1.0 - 5.0 * mu / 12.0
    else:
        raise ValueError("point 'L1', 'L2' veya 'L3' olmalıdır.")
    for _ in range(max_iter):
        fx = _f(x, mu)
        if abs(fx) < tol:
            return x
        x -= fx / _fprime(x, mu)
    raise RuntimeError(f"{point} için yakınsama sağlanamadı (mu={mu}).")


def lagrange_point_positions(mu: float) -> dict[str, float]:
    """L1, L2, L3'ün dönen koordinatlardaki x konumlarını döndürür."""
    return {p: collinear_equilibrium_x(mu, p) for p in ("L1", "L2", "L3")}


def l1_distance_from_planet_au(mu: float, separation_au: float) -> float:
    """L1'in gezegene olan mesafesi (AU): (1 - mu - x_L1) * separation_au."""
    if separation_au <= 0.0:
        raise ValueError("Yörünge yarı-büyük ekseni pozitif olmalıdır.")
    x_l1 = collinear_equilibrium_x(mu, "L1")
    return (1.0 - mu - x_l1) * separation_au


def l1_distance_from_star_au(mu: float, separation_au: float) -> float:
    """L1'in yıldıza olan mesafesi (AU): (x_L1 + mu) * separation_au."""
    if separation_au <= 0.0:
        raise ValueError("Yörünge yarı-büyük ekseni pozitif olmalıdır.")
    x_l1 = collinear_equilibrium_x(mu, "L1")
    return (x_l1 + mu) * separation_au


def hill_radius_au(mu: float, separation_au: float) -> float:
    """Gezegenin Hill yarıçapı (AU): a * (mu/3)^(1/3)."""
    if separation_au <= 0.0:
        raise ValueError("Yörünge yarı-büyük ekseni pozitif olmalıdır.")
    return separation_au * (mu / 3.0) ** (1.0 / 3.0)


def orbital_period_days(m_star_kg: float, separation_au: float) -> float:
    """Kepler III ile yörünge periyodu (gün)."""
    if m_star_kg <= 0.0 or separation_au <= 0.0:
        raise ValueError("Kütle ve yarı-büyük eksen pozitif olmalıdır.")
    a_m = separation_au * AU_M
    period_s = 2.0 * math.pi * math.sqrt(a_m ** 3 / (G_SI * m_star_kg))
    return period_s / DAY_S
