"""Star--planet L1 geometry in the circular restricted three-body problem.

This module computes the collinear L1 equilibrium of two point-mass primaries.
It does not claim that a finite-mass third body can remain there, nor does it
infer long-term stability or observational evidence for an L1-associated object.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class L1Geometry:
    """Dimensionless and dimensional location of the star--planet L1 point.

    The barycentre is the origin and the star-to-planet axis is positive.
    Distances are measured from the star toward the planet.
    """

    mass_parameter: float
    barycentric_x: float
    distance_from_primary: float
    distance_from_secondary: float
    separation_m: float

    @property
    def barycentric_x_m(self) -> float:
        """L1 coordinate in metres relative to the system barycentre."""
        return self.barycentric_x * self.separation_m

    @property
    def distance_from_primary_m(self) -> float:
        """Distance from the star to L1, in metres."""
        return self.distance_from_primary * self.separation_m

    @property
    def distance_from_secondary_m(self) -> float:
        """Distance from the planet to L1, in metres."""
        return self.distance_from_secondary * self.separation_m


@dataclass(frozen=True, slots=True)
class StarPlanetCR3BP:
    """Circular restricted three-body approximation for a star--planet pair.

    primary_mass_kg is the stellar mass, secondary_mass_kg is the planet mass,
    and separation_m is the constant circular separation. The returned L1
    location is exact up to numerical root-finding within this idealized model.
    Eccentricity, inclination, additional planets, radiation pressure,
    finite-size effects, and the candidate body's mass are outside this model.
    """

    primary_mass_kg: float
    secondary_mass_kg: float
    separation_m: float

    def __post_init__(self) -> None:
        values = (self.primary_mass_kg, self.secondary_mass_kg, self.separation_m)
        if not all(math.isfinite(value) and value > 0.0 for value in values):
            raise ValueError("Masses and separation must be finite and positive.")

    @property
    def mass_parameter(self) -> float:
        """Return mu = m_planet / (m_star + m_planet)."""
        return self.secondary_mass_kg / (self.primary_mass_kg + self.secondary_mass_kg)

    def l1_geometry(self) -> L1Geometry:
        """Solve the collinear L1 equilibrium between the two primaries.

        In normalized CR3BP coordinates, the primaries are at -mu and 1-mu.
        The root solves d(Omega)/dx = 0 between them. Monotonicity of this
        equation on the interval makes bisection deterministic and robust.
        """
        mu = self.mass_parameter
        primary_fraction = 1.0 - mu

        def equilibrium_equation(x: float) -> float:
            from_primary = x + mu
            from_secondary = 1.0 - mu - x
            return (
                x
                - primary_fraction / (from_primary * from_primary)
                + mu / (from_secondary * from_secondary)
            )

        # Stay strictly inside the interval so singular endpoints are never
        # evaluated. Scaling epsilon with mu also handles small planets.
        epsilon = min(1.0e-8, 0.1 * mu)
        left = -mu + epsilon
        right = 1.0 - mu - epsilon
        f_left = equilibrium_equation(left)
        f_right = equilibrium_equation(right)
        if not (f_left < 0.0 < f_right):
            raise ArithmeticError("Could not bracket the L1 equilibrium root.")

        for _ in range(200):
            midpoint = left + 0.5 * (right - left)
            if midpoint == left or midpoint == right:
                break
            f_midpoint = equilibrium_equation(midpoint)
            if f_midpoint < 0.0:
                left = midpoint
            else:
                right = midpoint
            if right - left <= 4.0 * math.ulp(max(abs(midpoint), 1.0)):
                break

        root = left + 0.5 * (right - left)
        return L1Geometry(
            mass_parameter=mu,
            barycentric_x=root,
            distance_from_primary=root + mu,
            distance_from_secondary=1.0 - mu - root,
            separation_m=self.separation_m,
        )
