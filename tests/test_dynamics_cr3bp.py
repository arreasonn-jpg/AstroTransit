"""
dynamics.cr3bp birim testleri.

Kapsam
------
- cr3bp_rhs: L1 noktasında ivme sıfır olmalı (denge noktası)
- integrate_orbit: kısa entegrasyon, şekil ve sonlu değerler
- l1_linearized_matrix / l1_eigenvalues: bir pozitif reel özdeğer (kararsızlık)
- stability_e_folding_days: pozitif ve makul mertebe
- linear_lissajous_state: L1 merkezli başlangıç
- station_keeping_* : pozitif delta-v, bütçe tutarlılığı
- summarize_orbit: mesafe istatistikleri
"""

from __future__ import annotations

import numpy as np
import pytest

from astrotransit.dynamics.cr3bp import (
    cr3bp_rhs,
    day_to_unit_time,
    integrate_orbit,
    l1_eigenvalues,
    l1_linearized_matrix,
    linear_lissajous_state,
    stability_e_folding_days,
    station_keeping_budget,
    station_keeping_delta_v_per_correction,
    summarize_orbit,
    unit_time_to_days,
)
from astrotransit.dynamics.lagrange import (
    M_EARTH_KG,
    M_SUN_KG,
    collinear_equilibrium_x,
    mass_ratio,
)

MU_EARTH = mass_ratio(M_SUN_KG, M_EARTH_KG)


# ─────────────────────────────────────────────────────────────
# cr3bp_rhs
# ─────────────────────────────────────────────────────────────


def test_rhs_zero_acceleration_at_l1() -> None:
    """L1 denge noktasında (hız sıfır) ivme ~0 olmalı."""
    x_l1 = collinear_equilibrium_x(MU_EARTH, "L1")
    state = np.array([x_l1, 0.0, 0.0, 0.0])
    out = cr3bp_rhs(0.0, state, MU_EARTH)
    assert out[0] == pytest.approx(0.0, abs=1e-12)
    assert out[1] == pytest.approx(0.0, abs=1e-12)
    assert out[2] == pytest.approx(0.0, abs=1e-10)
    assert out[3] == pytest.approx(0.0, abs=1e-12)


def test_rhs_shape() -> None:
    out = cr3bp_rhs(0.0, np.array([0.5, 0.1, 0.0, 0.0]), 0.01)
    assert out.shape == (4,)
    assert np.all(np.isfinite(out))


# ─────────────────────────────────────────────────────────────
# integrate_orbit
# ─────────────────────────────────────────────────────────────


def test_integrate_orbit_returns_arrays() -> None:
    x_l1 = collinear_equilibrium_x(MU_EARTH, "L1")
    state0 = np.array([x_l1 + 1e-6, 0.0, 0.0, 0.0])
    orbit = integrate_orbit(MU_EARTH, state0, duration=1.0, n_points=50)
    for key in ("t", "x", "y", "vx", "vy"):
        assert orbit[key].shape == (50,)
    assert np.all(np.isfinite(orbit["x"]))


def test_integrate_orbit_rejects_nonpositive_duration() -> None:
    with pytest.raises(ValueError):
        integrate_orbit(MU_EARTH, np.zeros(4), duration=0.0)


def test_unstable_divergence_from_l1() -> None:
    """L1'den küçük sapma ile başlayan yörünge L1'den uzaklaşmalı."""
    x_l1 = collinear_equilibrium_x(MU_EARTH, "L1")
    state0 = np.array([x_l1 + 1e-5, 0.0, 0.0, 0.0])
    orbit = integrate_orbit(MU_EARTH, state0, duration=200.0, n_points=500)
    summary = summarize_orbit(MU_EARTH, orbit)
    assert summary.max_distance_from_l1 > 1e-4


# ─────────────────────────────────────────────────────────────
# L1 doğrusallaştırma ve özdeğerler
# ─────────────────────────────────────────────────────────────


def test_l1_matrix_shape_and_symmetry() -> None:
    a = l1_linearized_matrix(0.01)
    assert a.shape == (4, 4)
    # Coriolis blokları: A[2,3] = 2, A[3,2] = -2
    assert a[2, 3] == pytest.approx(2.0)
    assert a[3, 2] == pytest.approx(-2.0)


def test_l1_has_positive_real_eigenvalue() -> None:
    """Kolineer noktalar kararsızdır: en az bir pozitif reel özdeğer olmalı."""
    eigs = l1_eigenvalues(MU_EARTH)
    assert np.max(eigs.real) > 0.0


def test_l1_eigenvalues_come_in_pairs() -> None:
    """Simetrik yapı nedeniyle özdeğerler ± çiftler halinde gelir."""
    eigs = np.sort_complex(l1_eigenvalues(0.01))
    reals = np.sort(eigs.real)
    assert reals[0] == pytest.approx(-reals[-1], rel=1e-9)


# ─────────────────────────────────────────────────────────────
# stability_e_folding_days
# ─────────────────────────────────────────────────────────────


def test_e_folding_days_positive() -> None:
    n_per_day = 2.0 * np.pi / 365.25  # Dünya benzeri
    t_e = stability_e_folding_days(MU_EARTH, n_per_day)
    assert t_e is not None
    assert t_e > 0.0
    # Dünya-Güneş L1 için e-katlama süresi ~23 gün (lambda ~ 2.53 birim n)
    assert 10.0 < t_e < 60.0


def test_e_folding_rejects_bad_n() -> None:
    with pytest.raises(ValueError):
        stability_e_folding_days(MU_EARTH, 0.0)


# ─────────────────────────────────────────────────────────────
# linear_lissajous_state
# ─────────────────────────────────────────────────────────────


def test_lissajous_state_centered_on_l1() -> None:
    state = linear_lissajous_state(MU_EARTH, amplitude=1e-3, phase=0.0)
    x_l1 = collinear_equilibrium_x(MU_EARTH, "L1")
    assert state[0] == pytest.approx(x_l1 + 1e-3, rel=1e-9)
    assert state[1] == pytest.approx(0.0, abs=1e-15)


def test_lissajous_rejects_nonpositive_amplitude() -> None:
    with pytest.raises(ValueError):
        linear_lissajous_state(MU_EARTH, amplitude=0.0)


# ─────────────────────────────────────────────────────────────
# station_keeping
# ─────────────────────────────────────────────────────────────


def test_delta_v_per_correction_positive() -> None:
    dv = station_keeping_delta_v_per_correction(
        e_folding_days=90.0, correction_interval_days=30.0, amplitude=1e-4
    )
    assert dv > 0.0
    assert dv == pytest.approx(1e-4 / 90.0, rel=1e-9)


def test_station_keeping_budget_consistency() -> None:
    budget = station_keeping_budget(
        e_folding_days=90.0,
        mission_days=365.25,
        correction_interval_days=30.0,
        amplitude=1e-4,
    )
    assert budget["n_corrections"] == pytest.approx(13.0)
    assert budget["total_delta_v"] == pytest.approx(
        budget["delta_v_per_correction"] * budget["n_corrections"], rel=1e-12
    )


def test_station_keeping_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        station_keeping_budget(90.0, 0.0, 30.0, 1e-4)
    with pytest.raises(ValueError):
        station_keeping_delta_v_per_correction(-1.0, 30.0, 1e-4)


# ─────────────────────────────────────────────────────────────
# summarize_orbit ve zaman dönüşümleri
# ─────────────────────────────────────────────────────────────


def test_summarize_orbit_stats() -> None:
    x_l1 = collinear_equilibrium_x(MU_EARTH, "L1")
    orbit = integrate_orbit(MU_EARTH, np.array([x_l1 + 1e-4, 0.0, 0.0, 0.0]), duration=5.0, n_points=100)
    s = summarize_orbit(MU_EARTH, orbit)
    d = s.to_dict()
    assert d["n_points"] == 100
    assert d["max_distance_from_l1"] >= d["final_distance_from_l1"] - 1e-12
    assert d["max_distance_from_l1"] >= 1e-4 - 1e-9


def test_time_conversion_roundtrip() -> None:
    n = 2.0 * np.pi / 365.25
    assert unit_time_to_days(day_to_unit_time(n), n) == pytest.approx(1.0, rel=1e-12)
