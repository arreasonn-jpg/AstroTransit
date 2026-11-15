"""Linear local stability analysis for the star--planet L1 point.

The analysis is the first-order variational model of the idealized CR3BP at
its collinear L1 equilibrium. It is not a nonlinear long-term stability
certificate and does not include finite-mass candidate feedback or control.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from astrotransit.dynamics.cr3bp import CR3BPDynamics
from astrotransit.dynamics.l1 import L1Geometry


Matrix6 = tuple[
    tuple[float, float, float, float, float, float],
    tuple[float, float, float, float, float, float],
    tuple[float, float, float, float, float, float],
    tuple[float, float, float, float, float, float],
    tuple[float, float, float, float, float, float],
    tuple[float, float, float, float, float, float],
]


@dataclass(frozen=True, slots=True)
class L1LocalStability:
    """Linearized spectral properties at a collinear L1 equilibrium."""

    mass_parameter: float
    barycentric_x: float
    gravity_gradient: float
    omega_xx: float
    omega_yy: float
    omega_zz: float
    planar_growth_rate: float
    planar_oscillation_frequency: float
    vertical_oscillation_frequency: float
    linearized_matrix: Matrix6

    @property
    def characteristic_polynomial_coefficients(self) -> tuple[float, float]:
        """Return (c2, c0) for lambda^4 + c2*lambda^2 + c0 = 0."""
        return -self.gravity_gradient, (
            1.0 + self.gravity_gradient - 2.0 * self.gravity_gradient**2
        )

    @property
    def eigenvalues(self) -> tuple[complex, complex, complex, complex, complex, complex]:
        """Return the six linear eigenvalues in normalized inverse-time units."""
        growth = self.planar_growth_rate
        planar = self.planar_oscillation_frequency
        vertical = self.vertical_oscillation_frequency
        return (
            complex(growth, 0.0),
            complex(-growth, 0.0),
            complex(0.0, planar),
            complex(0.0, -planar),
            complex(0.0, vertical),
            complex(0.0, -vertical),
        )

    @property
    def spectral_class(self) -> str:
        """Return the linear spectral classification."""
        return "saddle-center-center"


def analyze_l1_local_stability(
    dynamics: CR3BPDynamics,
    geometry: L1Geometry,
) -> L1LocalStability:
    """Analyze the first-order CR3BP dynamics at a supplied L1 geometry.

    The geometry must belong to the same mass parameter as dynamics and
    satisfy the collinear L1 equilibrium equation.
    """
    values = (
        geometry.mass_parameter,
        geometry.barycentric_x,
        geometry.distance_from_primary,
        geometry.distance_from_secondary,
        geometry.separation_m,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("L1 geometry values must all be finite.")
    if not 0.0 < geometry.mass_parameter < 1.0:
        raise ValueError("L1 geometry mass_parameter must be between 0 and 1.")
    if geometry.separation_m <= 0.0:
        raise ValueError("L1 geometry separation must be positive.")
    if geometry.distance_from_primary <= 0.0 or geometry.distance_from_secondary <= 0.0:
        raise ValueError("L1 distances from both primaries must be positive.")
    if not math.isclose(
        geometry.mass_parameter,
        dynamics.mass_parameter,
        rel_tol=1.0e-12,
        abs_tol=1.0e-15,
    ):
        raise ValueError("L1 geometry and dynamics must use the same mass parameter.")
    if not math.isclose(
        geometry.distance_from_primary + geometry.distance_from_secondary,
        1.0,
        rel_tol=0.0,
        abs_tol=1.0e-10,
    ):
        raise ValueError("Normalized L1 distances must sum to the primary separation.")
    if not math.isclose(
        geometry.barycentric_x,
        geometry.distance_from_primary - geometry.mass_parameter,
        rel_tol=0.0,
        abs_tol=1.0e-10,
    ):
        raise ValueError("L1 barycentric coordinate is inconsistent with its distances.")

    mu = dynamics.mass_parameter
    x = geometry.barycentric_x
    r1 = geometry.distance_from_primary
    r2 = geometry.distance_from_secondary
    equilibrium_residual = x - (1.0 - mu) / (r1 * r1) + mu / (r2 * r2)
    if abs(equilibrium_residual) > 1.0e-8:
        raise ValueError("Supplied geometry does not satisfy the collinear L1 equation.")

    gradient = (1.0 - mu) / (r1**3) + mu / (r2**3)
    discriminant = 9.0 * gradient**2 - 4.0 * gradient - 4.0
    constant_term = 1.0 + gradient - 2.0 * gradient**2
    if not math.isfinite(discriminant) or discriminant <= 0.0 or constant_term >= 0.0:
        raise ArithmeticError("L1 spectral roots do not have the expected saddle-center structure.")

    root_discriminant = math.sqrt(discriminant)
    positive_lambda_squared = 0.5 * (gradient + root_discriminant)
    negative_lambda_squared = 0.5 * (gradient - root_discriminant)
    if positive_lambda_squared <= 0.0 or negative_lambda_squared >= 0.0:
        raise ArithmeticError("Could not resolve one real and one imaginary planar eigenvalue pair.")

    omega_xx = 1.0 + 2.0 * gradient
    omega_yy = 1.0 - gradient
    omega_zz = -gradient
    matrix: Matrix6 = (
        (0.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        (omega_xx, 0.0, 0.0, 0.0, 2.0, 0.0),
        (0.0, omega_yy, 0.0, -2.0, 0.0, 0.0),
        (0.0, 0.0, omega_zz, 0.0, 0.0, 0.0),
    )
    return L1LocalStability(
        mass_parameter=mu,
        barycentric_x=x,
        gravity_gradient=gradient,
        omega_xx=omega_xx,
        omega_yy=omega_yy,
        omega_zz=omega_zz,
        planar_growth_rate=math.sqrt(positive_lambda_squared),
        planar_oscillation_frequency=math.sqrt(-negative_lambda_squared),
        vertical_oscillation_frequency=math.sqrt(gradient),
        linearized_matrix=matrix,
    )
