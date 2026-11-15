"""Numerical and physical-contract tests for star--planet L1 geometry."""

from __future__ import annotations

import math

import pytest

from astrotransit.dynamics.l1 import StarPlanetCR3BP


def test_earth_sun_l1_is_between_primaries_and_near_earth() -> None:
    system = StarPlanetCR3BP(
        primary_mass_kg=1.98847e30,
        secondary_mass_kg=5.9722e24,
        separation_m=149_597_870_700.0,
    )
    result = system.l1_geometry()

    assert 0.0 < result.distance_from_primary < 1.0
    assert 0.0 < result.distance_from_secondary < 1.0
    assert result.distance_from_primary + result.distance_from_secondary == pytest.approx(
        1.0, abs=1e-13
    )
    # The Sun--Earth L1 distance is approximately 1.5 million km.
    assert result.distance_from_secondary_m == pytest.approx(1.5e9, rel=0.08)
    assert result.barycentric_x_m == pytest.approx(
        result.distance_from_primary_m - result.mass_parameter * result.separation_m,
        rel=1e-12,
    )


def test_l1_moves_closer_to_secondary_as_planet_mass_decreases() -> None:
    separation = 1.0e11
    low_mass = StarPlanetCR3BP(1.0e30, 1.0e24, separation).l1_geometry()
    high_mass = StarPlanetCR3BP(1.0e30, 1.0e27, separation).l1_geometry()

    assert low_mass.distance_from_secondary < high_mass.distance_from_secondary


@pytest.mark.parametrize(
    ("primary_mass", "secondary_mass", "separation"),
    [
        (0.0, 1.0, 1.0),
        (1.0, -1.0, 1.0),
        (1.0, 1.0, 0.0),
        (math.inf, 1.0, 1.0),
        (1.0, math.nan, 1.0),
    ],
)
def test_nonphysical_inputs_are_rejected(
    primary_mass: float,
    secondary_mass: float,
    separation: float,
) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        StarPlanetCR3BP(primary_mass, secondary_mass, separation)


def test_equal_mass_binary_has_l1_at_barycentre() -> None:
    result = StarPlanetCR3BP(1.0, 1.0, 10.0).l1_geometry()

    assert result.mass_parameter == pytest.approx(0.5)
    assert result.barycentric_x == pytest.approx(0.0, abs=1e-14)
    assert result.distance_from_primary == pytest.approx(0.5)
    assert result.distance_from_secondary == pytest.approx(0.5)
