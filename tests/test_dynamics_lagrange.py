"""
dynamics.lagrange birim testleri.

Kapsam
------
- mass_ratio: sınır değerler, hata durumları
- collinear_equilibrium_x: L1/L2/L3 bilinen değerler (Dünya-Güneş, Jüpiter-Güneş)
- lagrange_point_positions: sıralama ve tutarlılık
- L1 mesafe fonksiyonları ve Hill yarıçapı
- orbital_period_days: Kepler III doğrulaması (Dünya ~365.25 gün)
"""

from __future__ import annotations

import math

import pytest

from astrotransit.dynamics.lagrange import (
    AU_M,
    M_EARTH_KG,
    M_JUP_KG,
    M_SUN_KG,
    collinear_equilibrium_x,
    hill_radius_au,
    l1_distance_from_planet_au,
    l1_distance_from_star_au,
    lagrange_point_positions,
    mass_ratio,
    orbital_period_days,
)

# ─────────────────────────────────────────────────────────────
# mass_ratio
# ─────────────────────────────────────────────────────────────


def test_mass_ratio_earth_sun() -> None:
    mu = mass_ratio(M_SUN_KG, M_EARTH_KG)
    assert mu == pytest.approx(3.0034e-6, rel=1e-3)


def test_mass_ratio_jupiter_sun() -> None:
    mu = mass_ratio(M_SUN_KG, M_JUP_KG)
    assert mu == pytest.approx(9.545e-4, rel=1e-3)


def test_mass_ratio_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        mass_ratio(0.0, M_EARTH_KG)
    with pytest.raises(ValueError):
        mass_ratio(M_SUN_KG, -1.0)


def test_mass_ratio_rejects_mu_above_half() -> None:
    with pytest.raises(ValueError):
        mass_ratio(1.0, 2.0)  # mu = 2/3 > 0.5


# ─────────────────────────────────────────────────────────────
# collinear_equilibrium_x
# ─────────────────────────────────────────────────────────────


def test_l1_earth_sun_known_value() -> None:
    """Dünya-Güneş L1, Güneş'den ~1.5e6 km (0.01 AU) içeride; x_L1 ~ 0.99."""
    mu = mass_ratio(M_SUN_KG, M_EARTH_KG)
    x_l1 = collinear_equilibrium_x(mu, "L1")
    assert x_l1 == pytest.approx(0.9900, abs=1e-3)


def test_l2_earth_sun_known_value() -> None:
    mu = mass_ratio(M_SUN_KG, M_EARTH_KG)
    x_l2 = collinear_equilibrium_x(mu, "L2")
    assert x_l2 == pytest.approx(1.0100, abs=1e-3)


def test_l3_behind_star() -> None:
    mu = mass_ratio(M_SUN_KG, M_EARTH_KG)
    x_l3 = collinear_equilibrium_x(mu, "L3")
    assert x_l3 == pytest.approx(-1.0, abs=1e-3)


def test_equilibrium_satisfies_quintic() -> None:
    """Dönen nokta quintic denklemi neredeyse sıfırlamalı."""
    mu = mass_ratio(M_SUN_KG, M_JUP_KG)
    for p in ("L1", "L2", "L3"):
        x = collinear_equilibrium_x(mu, p)
        d1 = x + mu
        d2 = x - 1.0 + mu
        f = x - (1.0 - mu) * d1 / abs(d1) ** 3 - mu * d2 / abs(d2) ** 3
        assert abs(f) < 1e-10


def test_collinear_rejects_bad_point() -> None:
    with pytest.raises(ValueError):
        collinear_equilibrium_x(0.01, "L4")


def test_collinear_rejects_bad_mu() -> None:
    with pytest.raises(ValueError):
        collinear_equilibrium_x(0.0, "L1")
    with pytest.raises(ValueError):
        collinear_equilibrium_x(0.6, "L1")


# ─────────────────────────────────────────────────────────────
# lagrange_point_positions
# ─────────────────────────────────────────────────────────────


def test_positions_ordering() -> None:
    mu = mass_ratio(M_SUN_KG, M_EARTH_KG)
    pos = lagrange_point_positions(mu)
    assert set(pos) == {"L1", "L2", "L3"}
    assert pos["L3"] < -mu < pos["L1"] < 1.0 - mu < pos["L2"]


# ─────────────────────────────────────────────────────────────
# L1 mesafeleri ve Hill yarıçapı
# ─────────────────────────────────────────────────────────────


def test_l1_distance_from_planet_earth() -> None:
    """Dünya'nın L1'e mesafesi ~0.01 AU (~1.5e6 km)."""
    mu = mass_ratio(M_SUN_KG, M_EARTH_KG)
    d = l1_distance_from_planet_au(mu, 1.0)
    assert d == pytest.approx(0.01, abs=1e-3)


def test_l1_distances_sum_to_separation() -> None:
    mu = mass_ratio(M_SUN_KG, M_JUP_KG)
    sep = 5.2
    d_star = l1_distance_from_star_au(mu, sep)
    d_planet = l1_distance_from_planet_au(mu, sep)
    assert d_star + d_planet == pytest.approx(sep, rel=1e-12)


def test_hill_radius_earth() -> None:
    """Dünya Hill yarıçapı ~0.01 AU."""
    mu = mass_ratio(M_SUN_KG, M_EARTH_KG)
    assert hill_radius_au(mu, 1.0) == pytest.approx(0.01, abs=1e-3)


def test_distance_functions_reject_nonpositive_separation() -> None:
    mu = 0.001
    with pytest.raises(ValueError):
        l1_distance_from_planet_au(mu, 0.0)
    with pytest.raises(ValueError):
        l1_distance_from_star_au(mu, -1.0)
    with pytest.raises(ValueError):
        hill_radius_au(mu, 0.0)


# ─────────────────────────────────────────────────────────────
# orbital_period_days
# ─────────────────────────────────────────────────────────────


def test_orbital_period_earth() -> None:
    period = orbital_period_days(M_SUN_KG, 1.0)
    assert period == pytest.approx(365.25, rel=1e-3)


def test_orbital_period_kepler_scaling() -> None:
    """a 2 katına çıkarsa periyot 2^1.5 katına çıkar."""
    p1 = orbital_period_days(M_SUN_KG, 1.0)
    p2 = orbital_period_days(M_SUN_KG, 2.0)
    assert p2 / p1 == pytest.approx(2.0 ** 1.5, rel=1e-9)


def test_orbital_period_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        orbital_period_days(0.0, 1.0)
    with pytest.raises(ValueError):
        orbital_period_days(M_SUN_KG, -1.0)


def test_au_constant_sane() -> None:
    assert AU_M == pytest.approx(1.496e11, rel=1e-3)
    assert math.isfinite(AU_M)
