"""Regression tests for normalized CR3BP dynamics and its Jacobi integral."""

from __future__ import annotations

import math

import pytest

from astrotransit.dynamics.cr3bp import CR3BPDynamics
from astrotransit.dynamics.l1 import StarPlanetCR3BP


def test_l1_geometry_is_a_rotating_frame_equilibrium() -> None:
    mu = 0.0121505856
    dynamics = CR3BPDynamics(mu)
    geometry = StarPlanetCR3BP(1.0 - mu, mu, 1.0).l1_geometry()
    derivative = dynamics.rhs((geometry.barycentric_x, 0.0, 0.0, 0.0, 0.0, 0.0))

    assert max(abs(value) for value in derivative) < 2.0e-8


def test_jacobi_constant_is_conserved_by_rk4_with_refinement() -> None:
    dynamics = CR3BPDynamics(0.0121505856)
    initial = (0.72, 0.08, 0.015, -0.04, 0.12, 0.01)
    initial_c = dynamics.jacobi_constant(initial)

    coarse = dynamics.propagate_rk4(initial, duration=0.5, steps=250)
    fine = dynamics.propagate_rk4(initial, duration=0.5, steps=500)
    coarse_drift = max(abs(dynamics.jacobi_constant(state) - initial_c) for state in coarse)
    fine_drift = max(abs(dynamics.jacobi_constant(state) - initial_c) for state in fine)

    assert fine_drift < coarse_drift
    assert fine_drift < 2.0e-8


def test_rhs_matches_rotating_frame_coriolis_terms() -> None:
    dynamics = CR3BPDynamics(0.1)
    state = (0.3, 0.2, 0.1, 0.04, -0.03, 0.02)
    derivative = dynamics.rhs(state)
    ax, ay, az = dynamics.acceleration(*state[:3], *state[3:5])

    assert derivative == pytest.approx((0.04, -0.03, 0.02, ax, ay, az))


@pytest.mark.parametrize("mu", [0.0, 1.0, -0.1, math.nan, math.inf])
def test_invalid_mass_parameter_is_rejected(mu: float) -> None:
    with pytest.raises(ValueError, match="mass_parameter"):
        CR3BPDynamics(mu)


def test_primary_singularity_is_rejected() -> None:
    dynamics = CR3BPDynamics(0.1)
    with pytest.raises(ValueError, match="singularity"):
        dynamics.jacobi_constant((-0.1, 0.0, 0.0, 0.0, 0.0, 0.0))


@pytest.mark.parametrize(
    ("duration", "steps"),
    [(0.0, 10), (-1.0, 10), (1.0, 0), (1.0, -2), (math.inf, 10)],
)
def test_invalid_propagation_controls_are_rejected(duration: float, steps: int) -> None:
    dynamics = CR3BPDynamics(0.1)
    with pytest.raises(ValueError):
        dynamics.propagate_rk4((0.3, 0.2, 0.1, 0.0, 0.0, 0.0), duration, steps)
