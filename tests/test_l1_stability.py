"""Independent regression tests for the CR3BP L1 linear stability model."""

from __future__ import annotations

import math

import pytest

from astrotransit.dynamics.cr3bp import CR3BPDynamics
from astrotransit.dynamics.l1 import L1Geometry, StarPlanetCR3BP
from astrotransit.dynamics.stability import analyze_l1_local_stability


def _earth_moon_model() -> tuple[CR3BPDynamics, L1Geometry]:
    mu = 0.0121505856
    geometry = StarPlanetCR3BP(1.0 - mu, mu, 1.0).l1_geometry()
    return CR3BPDynamics(mu), geometry


def test_l1_spectrum_has_one_unstable_and_two_oscillatory_pairs() -> None:
    dynamics, geometry = _earth_moon_model()
    result = analyze_l1_local_stability(dynamics, geometry)

    assert result.spectral_class == "saddle-center-center"
    assert result.planar_growth_rate > 0.0
    assert result.planar_oscillation_frequency > 0.0
    assert result.vertical_oscillation_frequency > 0.0
    assert result.eigenvalues[0].real > 0.0
    assert result.eigenvalues[1].real < 0.0
    assert result.eigenvalues[2].imag > 0.0
    assert result.eigenvalues[4].imag > 0.0
    assert result.eigenvalues[0].imag == 0.0
    assert result.eigenvalues[2].real == 0.0
    assert result.eigenvalues[4].real == 0.0


def test_planar_eigenvalues_satisfy_characteristic_polynomial() -> None:
    dynamics, geometry = _earth_moon_model()
    result = analyze_l1_local_stability(dynamics, geometry)
    c2, c0 = result.characteristic_polynomial_coefficients
    gradient = result.gravity_gradient
    assert c2 == pytest.approx(2.0 - gradient)
    assert c0 == pytest.approx(1.0 + gradient - 2.0 * gradient**2)

    for eigenvalue in result.eigenvalues[:4]:
        residual = eigenvalue**4 + c2 * eigenvalue**2 + c0
        assert abs(residual) < 1.0e-9

    for eigenvalue in result.eigenvalues[4:]:
        assert eigenvalue**2 == pytest.approx(-result.gravity_gradient)


def test_linearized_matrix_matches_finite_difference_of_cr3bp_rhs() -> None:
    dynamics, geometry = _earth_moon_model()
    result = analyze_l1_local_stability(dynamics, geometry)
    equilibrium = (
        geometry.barycentric_x,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    step = 1.0e-7

    for column in range(6):
        plus = list(equilibrium)
        minus = list(equilibrium)
        plus[column] += step
        minus[column] -= step
        derivative_plus = dynamics.rhs(tuple(plus))
        derivative_minus = dynamics.rhs(tuple(minus))
        finite_difference = tuple(
            (a - b) / (2.0 * step)
            for a, b in zip(derivative_plus, derivative_minus, strict=True)
        )
        expected = tuple(row[column] for row in result.linearized_matrix)
        assert finite_difference == pytest.approx(expected, rel=2.0e-6, abs=2.0e-7)


def test_l1_spectrum_is_finite_for_sun_earth_mass_ratio() -> None:
    system = StarPlanetCR3BP(1.98847e30, 5.9722e24, 149_597_870_700.0)
    geometry = system.l1_geometry()
    dynamics = CR3BPDynamics(system.mass_parameter)
    result = analyze_l1_local_stability(dynamics, geometry)

    assert all(
        math.isfinite(value)
        for value in (
            result.gravity_gradient,
            result.planar_growth_rate,
            result.planar_oscillation_frequency,
            result.vertical_oscillation_frequency,
        )
    )
    assert result.planar_growth_rate > 0.0


def test_mismatched_mass_parameter_is_rejected() -> None:
    _, geometry = _earth_moon_model()
    with pytest.raises(ValueError, match="same mass parameter"):
        analyze_l1_local_stability(CR3BPDynamics(0.1), geometry)


def test_non_equilibrium_geometry_is_rejected() -> None:
    dynamics, geometry = _earth_moon_model()
    invalid = L1Geometry(
        mass_parameter=geometry.mass_parameter,
        barycentric_x=geometry.barycentric_x + 0.01,
        distance_from_primary=geometry.distance_from_primary + 0.01,
        distance_from_secondary=geometry.distance_from_secondary - 0.01,
        separation_m=geometry.separation_m,
    )
    with pytest.raises(ValueError, match="collinear L1 equation"):
        analyze_l1_local_stability(dynamics, invalid)
