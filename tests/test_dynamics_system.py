"""
dynamics.system birim testleri.

Kapsam
------
- L1System property'leri: eksik girdi -> None (null kalır, 0.0 değil)
- assess_l1 tam akış: Güneş-Dünya benzeri sistem
- assess_l1 eksik kütle: tüm L1 alanları None, notlarda uyarı
- HZ bayrağı dalları: True / False / None
- to_dict yuvarlama ve null korunumu
"""

from __future__ import annotations

import pytest

from astrotransit.dynamics.lagrange import M_EARTH_KG, M_SUN_KG
from astrotransit.dynamics.system import L1Assessment, L1System, assess_l1


@pytest.fixture
def sun_earth() -> L1System:
    return L1System(
        star_name="Sun-like",
        m_star_kg=M_SUN_KG,
        m_planet_kg=M_EARTH_KG,
        separation_au=1.0,
        planet_in_habitable_zone=True,
    )


# ─────────────────────────────────────────────────────────────
# L1System property'leri
# ─────────────────────────────────────────────────────────────


def test_mu_none_when_masses_missing() -> None:
    s = L1System(star_name="X")
    assert s.mu is None
    assert s.mean_motion_per_day is None
    assert s.unit_velocity_m_per_s is None


def test_mu_computed(sun_earth: L1System) -> None:
    assert sun_earth.mu is not None
    assert 0.0 < sun_earth.mu < 1e-5


def test_unit_velocity_earth_like(sun_earth: L1System) -> None:
    """1 AU'de birim hız a*n ~ 29.8 km/s."""
    u = sun_earth.unit_velocity_m_per_s
    assert u is not None
    assert u == pytest.approx(29_785.0, rel=1e-2)


# ─────────────────────────────────────────────────────────────
# assess_l1 tam akış
# ─────────────────────────────────────────────────────────────


def test_assess_full_system(sun_earth: L1System) -> None:
    a = assess_l1(sun_earth)
    assert isinstance(a, L1Assessment)
    assert a.mu is not None and a.mu > 0.0
    assert a.x_l1 == pytest.approx(0.99, abs=1e-3)
    assert a.l1_distance_from_planet_au == pytest.approx(0.01, abs=1e-3)
    assert a.l1_distance_from_star_au == pytest.approx(0.99, abs=1e-3)
    assert a.orbital_period_days == pytest.approx(365.25, rel=1e-3)
    assert a.l1_unstable_eigenvalue is not None and a.l1_unstable_eigenvalue > 0.0
    assert a.stability_e_folding_days is not None and 10.0 < a.stability_e_folding_days < 60.0
    assert a.station_keeping is not None
    assert a.station_keeping["total_delta_v"] > 0.0
    assert "total_delta_v_m_per_s" in a.station_keeping
    assert a.planet_in_habitable_zone is True
    assert any("HZ" in n for n in a.notes)


def test_assess_to_dict_rounds_and_keeps_nulls() -> None:
    a = assess_l1(L1System(star_name="Empty"))
    d = a.to_dict()
    assert d["mu"] is None
    assert d["x_l1"] is None
    assert d["stability_e_folding_days"] is None
    assert d["station_keeping"] is None
    assert d["planet_in_habitable_zone"] is None
    assert any("null" in n for n in d["notes"])


def test_assess_missing_masses_returns_nulls() -> None:
    a = assess_l1(L1System(star_name="NoMass", separation_au=1.0))
    assert a.mu is None
    assert a.x_l1 is None
    assert a.station_keeping is None


def test_assess_missing_separation_keeps_mu() -> None:
    a = assess_l1(L1System(star_name="NoSep", m_star_kg=M_SUN_KG, m_planet_kg=M_EARTH_KG))
    assert a.mu is not None
    assert a.l1_distance_from_planet_au is None
    assert a.orbital_period_days is None
    assert a.stability_e_folding_days is None


# ─────────────────────────────────────────────────────────────
# HZ bayrağı dalları
# ─────────────────────────────────────────────────────────────


def test_hz_false_note() -> None:
    s = L1System(
        star_name="Hot",
        m_star_kg=M_SUN_KG,
        m_planet_kg=M_EARTH_KG,
        separation_au=0.3,
        planet_in_habitable_zone=False,
    )
    a = assess_l1(s)
    assert a.planet_in_habitable_zone is False
    assert any("HZ dışı" in n for n in a.notes)


def test_hz_unknown_note() -> None:
    s = L1System(
        star_name="Unknown",
        m_star_kg=M_SUN_KG,
        m_planet_kg=M_EARTH_KG,
        separation_au=1.0,
        planet_in_habitable_zone=None,
    )
    a = assess_l1(s)
    assert any("bilinmiyor" in n for n in a.notes)


def test_control_caveat_always_present(sun_earth: L1System) -> None:
    """Kol 2 epistemik notu her değerlendirmede bulunmalı."""
    a = assess_l1(sun_earth)
    assert any("kontrol kanıtı değildir" in n for n in a.notes)
